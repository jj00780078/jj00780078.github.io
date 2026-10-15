# -*- coding: utf-8 -*-
"""
秒看TV (fpctz.com) Python Spider —— WebTV / 苹果CMS v10 模板(x_t_10) HTML 抓取版
站点: https://www.fpctz.com/
兼容: FongMi/TV (T3) / CatTV / 影巢 等 TVBox 类框架

站点特征(已实测):
  - 该站未开放标准苹果CMS JSON API, 列表/详情均为服务端渲染(webtv 模板)
  - 列表:    /webtv/{type}.html            分页: /webtv/{type}/page/{n}.html
  - 二级分类: /webtv/{type}/class/{子类}.html
  - 其它筛选: /webtv/{type}/year/{年}.html   /webtv/{type}/by/{time|hits|score}.html
  - 详情:    /movie/{id}.html
             · 简介:  <h2>剧情简介</h2><p>...</p>
             · 年份/地区/类型/导演/主演: <div class="rl-facts"> 内 <b> 文本
             · 备注(状态): <span class="rl-tag"> (HD中字 / 第212集 ...)
             · 评分:  <div class="rl-status"> 内 "评分 <b>X.X</b>"
             · 选集:  rl-lines + rl-eps (每集 /video/{id}/{from}/{ep}.html)
  - 播放:    /video/{id}/{from}/{ep}.html   (内联 var player_xxxx = {... "url":"m3u8直链"} )
  - 搜索:    站点 /search/{词}.html 后端已失效(对任意词都返回同一批热门固定列表),
             故本爬虫采用「站点路由结果按标题过滤 + 并行扫描一级分类首页兜底」做最佳匹配
  - 直链优先, 无需第三方解析站; 播放直接返回 m3u8/mp4 直链(parse=0)以加速起播
"""

import sys
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

sys.path.append('..')

# ===== 兼容导入(同影巢.py): 运行时用框架基类, 本地用 fallback =====
try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass
    # 本地调试用 Session, 复用 TCP 连接(keep-alive)以加速连续请求
    _SESSION = _rq.Session()
    _SESSION.headers.update({"Accept-Encoding": "gzip, deflate"})

    class Spider:
        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 12)
            r = _SESSION.get(url, headers=headers, timeout=timeout, verify=False, **kw)
            r.encoding = 'utf-8'
            return r

# ============================================================
# 常量
# ============================================================

HOST = "https://www.fpctz.com"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

# 一级分类(nav 顺序, type_id 对应 webtv 路径)
CLASSES = [
    {"type_name": "电影", "type_id": "1"},
    {"type_name": "电视剧", "type_id": "2"},
    {"type_name": "短剧", "type_id": "3"},
    {"type_name": "动漫", "type_id": "4"},
    {"type_name": "综艺", "type_id": "5"},
    {"type_name": "网飞", "type_id": "48"},
]
_TIDS = [c["type_id"] for c in CLASSES]

# 二级分类(各一级分类共用同一套)
_CLASS_VALUES = ["冒险", "剧情", "动作", "古装", "喜剧", "悬疑", "惊悚",
                 "武侠", "爱情", "犯罪", "科幻", "穿越", "谍战", "逆袭", "都市"]
_YEAR_VALUES = ["2026", "2025", "2024", "2023", "2022", "2021", "2020",
                "2019", "2018", "2017", "2016", "2015"]
_BY_VALUES = [{"n": "最新", "v": "time"},
              {"n": "最热", "v": "hits"},
              {"n": "评分", "v": "score"}]


def _build_filters():
    cls = [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in _CLASS_VALUES]
    yrs = [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in _YEAR_VALUES]
    f = {}
    for c in CLASSES:
        # 二级分类筛选: 行名为「分类」, 含 剧情/动作/科幻 ... 等子类
        f[c["type_id"]] = [
            {"key": "class", "name": "分类", "value": cls},
            {"key": "year", "name": "年份", "value": yrs},
            {"key": "by", "name": "排序", "value": _BY_VALUES},
        ]
    return f


FILTERS = _build_filters()

# 正则
CARD_RE = re.compile(
    r'class="rl-card"[^>]*href="(/movie/(\d+)\.html)"\s+title="([^"]*)"'
    r'(?:.*?)(?:src|data-original)="([^"]*)"', re.S)
LINE_RE = re.compile(
    r'rl-lines"><a[^>]*href="(/video/\d+/\d+/\d+\.html)"[^>]*>([^<]*)</a>'
    r'</div>\s*<div class="rl-eps">(.*?)</div>', re.S)
EP_RE = re.compile(r'href="(/video/\d+/\d+/\d+\.html)"\s+title="([^"]*)"')
PLAYER_RE = re.compile(r'var player_[A-Za-z0-9_]+\s*=\s*(\{[^{}]*\})')

# 详情页字段
INTRO_RE = re.compile(r'<h2>剧情简介</h2>\s*<p>([^<]*)</p>')
TAG_RE = re.compile(r'class="rl-tag[^"]*">([^<]*)</span>')
SCORE_RE = re.compile(r'评分\s*<b>([\d.]+)</b>')
FACTS_RE = {
    "year": re.compile(r'年份：<b>(\d{4})</b>'),
    "area": re.compile(r'地区：<b>([^<]*)</b>'),
    "type": re.compile(r'类型：<b>(?:<a[^>]*>)?([^<]*?)(?:</a>)?</b>'),
    "director": re.compile(r'导演：<b>([^<]*)</b>'),
    "actor": re.compile(r'主演：<b>([^<]*)</b>'),
}


# ============================================================
# Spider 主类
# ============================================================

class Spider(Spider):

    def getName(self):
        return "秒看TV"

    # ===== 初始化 =====
    def init(self, extend=""):
        self.extend = extend or ""
        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",   # 服务端压缩, 减小传输体积以加速
        }
        self._home_cache = []
        self._home_cache_time = 0

    # ===== 网络/文本工具 =====
    def _text(self, url, timeout=12):
        try:
            rsp = self.fetch(url, headers=self.header, timeout=timeout)
            try:
                return rsp.text
            except Exception:
                return rsp.content.decode('utf-8', 'ignore')
        except Exception:
            return ""

    def _abs(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return HOST + url
        return url

    # ===== 列表卡片解析 =====
    def _parse_cards(self, html):
        out = []
        for m in CARD_RE.finditer(html):
            out.append({
                "vod_id": m.group(2),
                "vod_name": m.group(3).strip(),
                "vod_pic": self._abs(m.group(4)),
                "vod_remarks": "",
            })
        return out

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        """首页推荐: 取电影最新一页, 5 分钟缓存"""
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 300:
            return {"list": self._home_cache}
        vods = self._parse_cards(self._text(HOST + "/webtv/1.html"))[:60]
        self._home_cache = vods
        self._home_cache_time = now
        return {"list": vods}

    # ============================================================
    # 分类列表
    # ============================================================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1

            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            # 组装 webtv 路径: type -> class -> year -> by -> page
            parts = ["/webtv/" + str(tid)]
            if ext.get("class"):
                parts.append("/class/" + quote(str(ext["class"]), safe=""))
            if ext.get("year"):
                parts.append("/year/" + quote(str(ext["year"]), safe=""))
            if ext.get("by"):
                parts.append("/by/" + quote(str(ext["by"]), safe=""))
            if page > 1:
                parts.append("/page/" + str(page))
            url = HOST + "".join(parts) + ".html"

            vods = self._parse_cards(self._text(url, timeout=12))
            return {
                "list": vods,
                "page": page,
                "pagecount": 9999,
                "limit": 60,
                "total": 999999,
            }
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 60, "total": 0, "list": []}

    # ============================================================
    # 详情页
    # ============================================================
    @staticmethod
    def _clean_intro(text):
        """清洗站点自动生成的 SEO 简介, 尽量保留真实剧情"""
        if not text:
            return ""
        text = text.strip()
        # 真实剧情通常位于 "欢迎收藏本站" 之后
        i = text.find("欢迎收藏本站")
        if i >= 0:
            after = text[i + len("欢迎收藏本站"):].strip("。， ")
            if after:
                return after[:400]
        # 否则取 "热搜相关" 之前的描述段, 并去掉 "关于《...》的最新口碑与演职员表：" 前缀
        pre = text.split("热搜相关")[0].strip("。， ")
        pre = re.sub(r'^关于《[^》]*》的最新口碑与演职员表：.*?分。', '', pre)
        return pre[:400]

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vid = str(ids[0])
        html = self._text(HOST + "/movie/" + vid + ".html", timeout=12)
        if not html:
            return {"list": []}

        # 线路 + 选集(统一命名为 第N集, 单集影片用「正片」)
        play_from, play_url = [], []
        for blk in LINE_RE.finditer(html):
            line_name = blk.group(2).strip()
            eps = []
            for em in EP_RE.finditer(blk.group(3)):
                ep_url = self._abs(em.group(1))
                eps.append(ep_url)
            if eps:
                total = len(eps)
                named = []
                for idx, ep_url in enumerate(eps, 1):
                    ep_name = "正片" if total == 1 else ("第%d集" % idx)
                    named.append("%s$%s" % (ep_name, ep_url))
                play_from.append(line_name)
                play_url.append("#".join(named))

        if not play_url:
            return {"list": []}

        # 基本信息
        name = ""
        m = re.search(r'<h1>([^<]+)</h1>', html)
        if m:
            name = m.group(1).strip()
        else:
            m = re.search(r'<title>([^<]+)</title>', html)
            if m:
                name = m.group(1).split("在线观看")[0].strip()

        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]*)"', html)
        if m:
            pic = self._abs(m.group(1))

        # 年份 / 地区 / 类型 / 导演 / 主演
        year = FACTS_RE["year"].search(html)
        area = FACTS_RE["area"].search(html)
        vtype = FACTS_RE["type"].search(html)
        director = FACTS_RE["director"].search(html)
        actor = FACTS_RE["actor"].search(html)

        # 备注(状态): HD中字 / 第212集 ...
        remarks = ""
        mt = TAG_RE.search(html)
        if mt:
            remarks = mt.group(1).strip()

        # 评分
        score = ""
        ms = SCORE_RE.search(html)
        if ms:
            score = ms.group(1).strip()

        # 简介
        content = self._clean_intro(INTRO_RE.search(html).group(1) if INTRO_RE.search(html) else "")

        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_year": year.group(1) if year else "",
            "vod_area": area.group(1).strip() if area else "",
            "vod_remarks": remarks or (vtype.group(1).strip() if vtype else "HD"),
            "vod_actor": actor.group(1).strip() if actor else "",
            "vod_director": director.group(1).strip() if director else "",
            "vod_content": (("评分：" + score + "\n") if score else "") + content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    # ============================================================
    # 搜索(站点后端失效 -> 路由过滤 + 并行扫描兜底)
    # ============================================================
    def _scan_categories(self, kw):
        """并行抓取一级分类前 2 页, 按标题包含关键词匹配(站点无搜索 API 时的最佳兜底)"""
        urls = []
        for t in _TIDS:
            urls.append(HOST + "/webtv/" + t + ".html")
            urls.append(HOST + "/webtv/" + t + "/page/2.html")
        try:
            with ThreadPoolExecutor(max_workers=8) as ex:
                htmls = list(ex.map(lambda u: self._text(u, timeout=10), urls))
        except Exception:
            htmls = [self._text(u, timeout=10) for u in urls]

        out = []
        for h in htmls:
            if not h:
                continue
            for m in CARD_RE.finditer(h):
                if kw in m.group(3):
                    out.append({
                        "vod_id": m.group(2),
                        "vod_name": m.group(3).strip(),
                        "vod_pic": self._abs(m.group(4)),
                        "vod_remarks": "",
                    })
        return out

    def searchContent(self, key, quick, pg="1"):
        kw = (key or "").strip()
        if not kw:
            return {"list": []}
        try:
            # 1) 站点搜索路由(返回热门固定列表) -> 仅保留标题命中的
            route = self._parse_cards(
                self._text(HOST + "/search/" + quote(kw, safe="") + ".html", timeout=12))
            route_hits = [c for c in route if kw in c["vod_name"]]

            # 2) 并行扫描一级分类首页兜底(真实匹配)
            scan_hits = self._scan_categories(kw)

            # 合并去重, 优先站点路由命中
            seen, merged = set(), []
            for c in route_hits + scan_hits:
                if c["vod_id"] in seen:
                    continue
                seen.add(c["vod_id"])
                merged.append(c)

            if merged:
                return {"list": merged}

            # 均无匹配: 退回站点热门列表, 避免完全空白(标注非精准结果)
            return {"list": route[:20] if route else []}
        except Exception:
            return {"list": []}

    # ============================================================
    # 播放解析(直链优先, parse=0 加速起播)
    # ============================================================
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}

        play_url = str(id)
        referer = HOST + "/"
        if play_url.startswith("/"):
            play_url = HOST + play_url
            referer = play_url   # 用播放页作 Referer, 提升 CDN 命中率

        html = self._text(play_url, timeout=10)
        m = PLAYER_RE.search(html)
        if m:
            try:
                obj = json.loads(m.group(1))
                media = (obj.get("url") or "").strip()
                if media:
                    is_m3u8 = ".m3u8" in media.lower()
                    return {
                        "parse": 0,                 # 直链直放, 不做嗅探, 起播更快
                        "playUrl": "",
                        "url": media,
                        "header": {
                            "User-Agent": UA,
                            "Referer": referer,
                            "Accept": "*/*",
                        },
                        "format": "application/x-mpegURL" if is_m3u8 else "",
                        "contentType": "application/x-mpegURL" if is_m3u8 else "",
                    }
            except Exception:
                pass

        # 兜底: 交给壳子嗅探
        return {
            "parse": 1,
            "playUrl": "",
            "url": play_url,
            "header": {"User-Agent": UA, "Referer": referer},
        }

    # ===== 本地代理 =====
    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    # ===== 清理 =====
    def destroy(self):
        pass

    def close(self):
        self.destroy()
