# -*- coding: utf-8 -*-
"""
青鸟影视 Python Spider — 兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)
站点: https://qndjy.com/

数据源（Laravel 自研 API，非苹果CMS）:
  - 首页 / 详情 / 搜索 : HTML 解析
  - 分类列表           : POST /api/vod（JSON，每页48条，支持服务端筛选）
  - 播放地址           : POST /api/vod_url/{vid}/{jid}（直接返回 m3u8 直链）

分类体系:
  - 一级分类: 1电影 / 2电视剧 / 3动漫 / 4综艺
  - 二级分类: 5动作片 6喜剧片 7爱情片 8科幻片 9恐怖片 10剧情片 11战争片
              12悬疑片 13犯罪片 14惊悚片 15冒险片 16纪录片 17动画片 18微影视
              33伦理片 19其他片 / 20国产剧 21港台剧 22日韩剧 23欧美剧 24其他剧
              25国产动漫 26日韩动漫 27欧美动漫 28其他动漫
              29大陆综艺 30日韩综艺 31港台综艺 32欧美综艺
  - 筛选: 二级分类走独立 cid（如 5=动作片 20=国产剧），
           地区/年份/排序走 area/year/sort 服务端筛选（实测确认）

加载速度优化:
  - WAF 预热: 首次请求先 GET 首页拿 cookie(XSRF-TOKEN/laravel_session)，否则
    POST /api/vod 会被 WAF 403 拦截（必现问题，已修复）
  - requests.Session 连接复用 + gzip 自动解压，避免重复握手
  - 多级缓存: 首页 10 分钟 / 分类(含筛选组合) 5 分钟 / 详情成功 5 分钟
    （失败仅 30 秒，避免缓存空结果）/ 搜索 3 分钟 / 播放地址 15 分钟
  - 分类直接用 JSON API（48条/次，远快于 HTML 解析）
  - 全链路短超时: 页面 8s、API 5s；失败快速重试(0.3s)，429 限流等 2s
  - 详情页只解析站源+剧集，播放地址懒加载 + 后台线程预取（点播秒开）

播放速度优化:
  - 播放 API 直接返回 m3u8 直链 → parse=0 直连播放，无需第三方解析器
  - 播放地址 15 分钟缓存：重复点播/切集零等待
  - 详情返回后后台预取默认线路第 1 集直链，用户点播放直接命中缓存
  - 多线路冗余: 当前线路失败时并发探测其他线路/剧集，一条失效自动切换
  - 直链携带 Referer/Origin/UA 防防盗链
"""

import sys
import json
import re
import time
import threading
from urllib.parse import quote

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:  # 极老 Python 兜底
    ThreadPoolExecutor = None
    as_completed = None

# requests 必须模块级无条件导入（真机壳子 base.spider 导入成功时也要有 _rq）
try:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass
except Exception:
    _rq = None

try:
    sys.path.append('..')
    from base.spider import Spider
except ImportError:
    class Spider:
        """壳子外运行（本地测试/桌面环境）时的兜底实现"""
        def fetch(self, url, headers=None, timeout=15, **kw):
            if _rq is None:
                return None
            r = _rq.get(url, headers=headers, timeout=timeout, verify=False, **kw)
            r.encoding = "utf-8"
            return r


# ============================================================
# 常量
# ============================================================

HOST = "https://qndjy.com"
UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)

# 超时（秒）
TIMEOUT_PAGE = 8      # 整页 HTML（首页/详情/搜索）
TIMEOUT_API = 5       # JSON API（分类/播放）
# 缓存 TTL（秒）
TTL_HOME = 600        # 首页
TTL_CAT = 300         # 分类（含筛选组合）
TTL_DETAIL_OK = 300   # 详情成功
TTL_DETAIL_EMPTY = 30 # 详情失败（短缓存防抖）
TTL_SEARCH = 180      # 搜索
TTL_PLAY = 900        # 播放地址

# 一级分类（贴合用户叫法：电视剧）
CLASSES_MAIN = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "动漫"},
    {"type_id": "4", "type_name": "综艺"},
]

# 二级分类（cid -> 所属一级分类）
CLASSES_SUB = [
    {"type_id": "5", "type_name": "动作片", "parent": "1"},
    {"type_id": "6", "type_name": "喜剧片", "parent": "1"},
    {"type_id": "7", "type_name": "爱情片", "parent": "1"},
    {"type_id": "8", "type_name": "科幻片", "parent": "1"},
    {"type_id": "9", "type_name": "恐怖片", "parent": "1"},
    {"type_id": "10", "type_name": "剧情片", "parent": "1"},
    {"type_id": "11", "type_name": "战争片", "parent": "1"},
    {"type_id": "12", "type_name": "悬疑片", "parent": "1"},
    {"type_id": "13", "type_name": "犯罪片", "parent": "1"},
    {"type_id": "14", "type_name": "惊悚片", "parent": "1"},
    {"type_id": "15", "type_name": "冒险片", "parent": "1"},
    {"type_id": "16", "type_name": "纪录片", "parent": "1"},
    {"type_id": "17", "type_name": "动画片", "parent": "1"},
    {"type_id": "18", "type_name": "微影视", "parent": "1"},
    {"type_id": "33", "type_name": "伦理片", "parent": "1"},
    {"type_id": "19", "type_name": "其他片", "parent": "1"},
    {"type_id": "20", "type_name": "国产剧", "parent": "2"},
    {"type_id": "21", "type_name": "港台剧", "parent": "2"},
    {"type_id": "22", "type_name": "日韩剧", "parent": "2"},
    {"type_id": "23", "type_name": "欧美剧", "parent": "2"},
    {"type_id": "24", "type_name": "其他剧", "parent": "2"},
    {"type_id": "25", "type_name": "国产动漫", "parent": "3"},
    {"type_id": "26", "type_name": "日韩动漫", "parent": "3"},
    {"type_id": "27", "type_name": "欧美动漫", "parent": "3"},
    {"type_id": "28", "type_name": "其他动漫", "parent": "3"},
    {"type_id": "29", "type_name": "大陆综艺", "parent": "4"},
    {"type_id": "30", "type_name": "日韩综艺", "parent": "4"},
    {"type_id": "31", "type_name": "港台综艺", "parent": "4"},
    {"type_id": "32", "type_name": "欧美综艺", "parent": "4"},
]

# 全部分类（仅一级：电影/电视剧/动漫/综艺，二级作为"类型"筛选项）
CLASSES = CLASSES_MAIN

# 地区 / 年份 / 排序 筛选值（服务端筛选，取值与站内一致）
_AREAS = [
    "大陆", "香港", "台湾", "美国", "法国", "英国",
    "日本", "韩国", "德国", "泰国", "印度", "新加坡", "其他",
]
_YEARS = [str(y) for y in range(2026, 2005, -1)]


def _filters(cid):
    """按分类构建筛选器：一级分类带"类型"(值为二级分类 cid)，二级分类只带地区/年份/排序"""
    filters = []
    # 服务端无类型筛选参数，二级分类必须用独立 cid 请求；
    # 因此"类型"筛选项的 value 直接放二级分类的 type_id，收到后替换 cid
    subs = [(s["type_name"], s["type_id"]) for s in CLASSES_SUB if s["parent"] == cid]
    if subs:
        filters.append({
            "key": "class", "name": "类型",
            "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": v} for n, v in subs],
        })
    filters.append({
        "key": "area", "name": "地区",
        "value": [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in _AREAS],
    })
    filters.append({
        "key": "year", "name": "年份",
        "value": [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in _YEARS],
    })
    filters.append({
        "key": "by", "name": "排序",
        "value": [
            {"n": "最新", "v": "time"},
            {"n": "最热", "v": "hits"},
            {"n": "评分", "v": "score"},
        ],
    })
    return filters


FILTERS = {c["type_id"]: _filters(c["type_id"]) for c in CLASSES}


# ============================================================
# Spider 主类
# ============================================================

class Spider(Spider):

    def getName(self):
        return "青鸟影视"

    # ===== 初始化 =====
    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ""
        else:
            self.extend = extend or ""

        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "application/json, text/plain, */*",
        }

        # 网络层：优先 requests.Session（连接复用 + cookie 保持）
        self._session = None
        if _rq is not None:
            try:
                self._session = _rq.Session()
                self._session.headers.update(self.header)
                self._session.headers["X-Requested-With"] = "XMLHttpRequest"
                self._session.verify = False
            except Exception:
                self._session = None

        # 缓存容器 + 锁
        self._lock = threading.Lock()
        self._warmed = False              # WAF cookie 是否已预热
        self._home_cache = []             # 首页卡片列表
        self._home_cache_time = 0
        self._cat_cache = {}              # 分类缓存: key -> (ts, value, ttl)
        self._detail_cache = {}           # 详情缓存
        self._search_cache = {}           # 搜索缓存
        self._play_cache = {}             # 播放地址缓存: (vid,jid) -> (ts, url, ttl)
        self._prefetching = {}            # 正在后台预取的 (vid,jid)

    # ===== 网络工具 =====
    def _rsp_text(self, rsp):
        if rsp is None:
            return ""
        try:
            return rsp.text
        except Exception:
            try:
                return rsp.content.decode("utf-8", "ignore")
            except Exception:
                return ""

    def _request(self, method, url, data=None, timeout=TIMEOUT_PAGE):
        """统一请求：GET/POST，429 限流与异常自动重试一次，返回文本或空串"""
        for attempt in range(2):
            r = None
            code = 200
            try:
                if method == "POST":
                    if self._session is not None:
                        r = self._session.post(url, data=data, timeout=timeout)
                    elif _rq is not None:
                        # 壳子 fetch 不支持 POST 时直接用 requests（无 cookie，可能 403）
                        r = _rq.post(url, headers=self.header, data=data,
                                     timeout=timeout, verify=False)
                else:
                    if self._session is not None:
                        r = self._session.get(url, timeout=timeout)
                    else:
                        r = self.fetch(url, headers=self.header, timeout=timeout)
                code = getattr(r, "status_code", 200) if r is not None else 0
            except Exception:
                code = 0

            if r is not None and code != 429:
                text = self._rsp_text(r)
                if text:
                    return text
            # 429 限流：多等一下再重试；其他失败/空响应：快速重试
            time.sleep(2.0 if code == 429 else 0.3)
        return ""

    def _get(self, url, timeout=TIMEOUT_PAGE):
        return self._request("GET", url, timeout=timeout)

    def _post(self, url, data=None, timeout=TIMEOUT_API):
        return self._request("POST", url, data=data, timeout=timeout)

    def _post_json(self, url, data=None, timeout=TIMEOUT_API):
        text = self._post(url, data=data, timeout=timeout)
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    def _get_json(self, url, timeout=TIMEOUT_API):
        text = self._get(url, timeout=timeout)
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    def _match(self, pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1) if m else ""

    def _strip_tags(self, s):
        return re.sub(r"<[^>]+>", "", s or "").strip()

    def _norm_url(self, u):
        """图片/链接协议归一化：// -> https:，/ -> 站内绝对路径"""
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return HOST + u
        return u

    # ===== WAF 预热（关键）=====
    def _warm(self):
        """
        WAF 要求先 GET 首页拿 cookie(XSRF-TOKEN/laravel_session)，
        否则 POST /api/vod、/api/vod_url 会返回 403。
        预热的同时把首页数据顺手写入缓存，一箭双雕。
        """
        if self._session is None:
            return
        with self._lock:
            if self._warmed:
                return
            self._warmed = True
        try:
            html = self._request("GET", HOST + "/", timeout=TIMEOUT_PAGE)
            cards = self._parse_cards(html)
            if cards:
                with self._lock:
                    self._home_cache = cards[:60]
                    self._home_cache_time = int(time.time())
        except Exception:
            pass

    # ===== 缓存 =====
    def _cache_get(self, cache, key, ttl=None):
        item = cache.get(key)
        if item and time.time() - item[0] < (ttl if ttl is not None else item[2]):
            return item[1]
        return None

    def _cache_set(self, cache, key, value, ttl=TTL_CAT):
        # 简单防膨胀：超过 512 项整体清一次（TTL 短，可接受）
        if len(cache) > 512:
            cache.clear()
        cache[key] = (time.time(), value, ttl)

    # ===== 卡片解析 =====
    def _parse_cards(self, html):
        """解析 videoul 卡片列表 -> TVBox 卡片 dict 列表"""
        cards = []
        if not html:
            return cards
        # <a href="/news/123.html" class="videoul-a">...lay-src="pic"...
        # ...videoul-tips1">备注</span>...videoul-title">名称</p>
        pattern = re.compile(
            r'<a[^>]*href="/news/(\d+)\.html"[^>]*class="videoul-a">'
            r'.*?lay-src="([^"]+)".*?'
            r'videoul-tips1">([^<]*)</span>.*?'
            r'videoul-title">([^<]*)</p>',
            re.S,
        )
        for vid, pic, state, name in pattern.findall(html):
            cards.append({
                "vod_id": vid,
                "vod_name": name.strip(),
                "vod_pic": self._norm_url(pic),
                "vod_remarks": state.strip() or "HD",
            })
        return cards

    def _card(self, v):
        """API 视频对象 -> TVBox 卡片（备注优先 状态 > 评分 > 年份）"""
        remarks = (v.get("state") or "").strip()
        if not remarks:
            score = (v.get("score") or "").strip()
            if score:
                try:
                    if float(score) > 0:
                        remarks = score + "分"
                except Exception:
                    remarks = ""
            if not remarks and v.get("year"):
                remarks = str(v.get("year"))
        if not remarks:
            remarks = "HD"
        return {
            "vod_id": str(v.get("id", "")),
            "vod_name": v.get("name", ""),
            "vod_pic": self._norm_url(v.get("pic")),
            "vod_remarks": remarks,
        }

    # ============================================================
    # 首页
    # ============================================================

    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def _fetch_home(self):
        """抓取并解析首页，写入缓存"""
        html = self._get(HOST + "/", timeout=TIMEOUT_PAGE)
        cards = self._parse_cards(html)
        with self._lock:
            self._home_cache = cards[:60]
            self._home_cache_time = int(time.time())
        return cards[:60]

    def homeVideoContent(self):
        """首页推荐，带 10 分钟缓存；未命中时走 WAF 预热（顺手填充缓存）"""
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                return {"list": self._home_cache[:60]}

        self._warm()

        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                return {"list": self._home_cache[:60]}
        return {"list": self._fetch_home()[:60]}

    # ============================================================
    # 分类列表（二级分类 + 服务端筛选 + 组合缓存）
    # ============================================================

    def _empty_category(self, page=1):
        return {"page": page, "pagecount": 1, "limit": 48, "total": 0, "list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg or 1))

            # 解析 extend 筛选参数（class/area/year/by）
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            # 组合缓存：同一分类+页码+筛选组合 5 分钟内不重复请求
            ckey = "%s|%d|%s" % (str(tid), page,
                                 json.dumps(ext, ensure_ascii=False, sort_keys=True))
            cached = self._cache_get(self._cat_cache, ckey, TTL_CAT)
            if cached is not None:
                return cached

            params = {"cid": str(tid), "page": str(page)}
            # 类型筛选 = 二级分类 cid：直接替换分类参数（实测：服务端只认 cid，
            # class/type_id 等筛选参数均被忽略，不替换会永远返回一级分类全量）
            cls = ext.get("class")
            if cls:
                params["cid"] = str(cls)
            for k in ("area", "year"):
                if ext.get(k):
                    params[k] = str(ext[k])
            if ext.get("by"):
                params["sort"] = str(ext["by"])

            data = self._post_json(HOST + "/api/vod", data=params, timeout=TIMEOUT_API)
            if not data or data.get("code") != 1:
                return self._empty_category(page)

            d = data.get("data") or {}
            vods = [self._card(v) for v in d.get("list", [])]
            pagecount = max(1, int(d.get("pagejs", 1)))

            result = {
                "list": vods,
                "page": page,
                "pagecount": pagecount,
                "limit": 48,
                "total": int(d.get("nums", 0)),
            }
            self._cache_set(self._cat_cache, ckey, result, TTL_CAT)
            return result
        except Exception:
            return self._empty_category(page)

    # ============================================================
    # 详情页
    # ============================================================

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])
        if not vod_id:
            return {"list": []}

        # 详情缓存：成功 5 分钟，失败 30 秒（防抖）
        cached = self._cache_get(self._detail_cache, vod_id, None)
        if cached is not None:
            return cached

        result = self._fetch_detail(vod_id)
        ttl = TTL_DETAIL_OK if result.get("list") else TTL_DETAIL_EMPTY
        self._cache_set(self._detail_cache, vod_id, result, ttl)

        # 后台预取默认线路第 1 集播放地址 -> 点播秒开
        if result.get("list"):
            self._prefetch_play(result["list"][0])
        return result

    def _fetch_detail(self, vod_id):
        """抓取并解析详情页，返回 TVBox 详情 dict"""
        html = self._get(HOST + "/news/" + vod_id + ".html", timeout=TIMEOUT_PAGE)
        if not html:
            return {"list": []}

        # 线路/剧集: 新版页面无 <li data-id> 站源节点，
        # 用 <ul class="play-ji-ul" id="zu-N"> 识别（多线路会有多个 ul）
        zu_pat = re.compile(
            r'<ul[^>]*class="play-ji-ul[^"]*"[^>]*id="zu-(\d+)"[^>]*>(.*?)</ul>', re.S
        )
        li_pat = re.compile(
            r'<a[^>]*href="/play/(\d+)/(\d+)\.html"[^>]*>([^<]*)</a>'
        )
        zu_blocks = zu_pat.findall(html)
        if not zu_blocks:
            return {"list": []}

        play_from = []
        play_url = []
        multi = len(zu_blocks) > 1
        for idx, (zid, block) in enumerate(zu_blocks, 1):
            eps = []
            for vid, jid, name in li_pat.findall(block):
                eps.append("%s$%s|%s" % (name.strip() or "播放", vid, jid))
            if eps:
                play_from.append("线路%d" % idx if multi else "正片")
                play_url.append("#".join(eps))

        if not play_from:
            return {"list": []}

        # 详情字段
        title = self._match(r'<h3[^>]*>(.*?)<span', html, re.S) or self._match(
            r'<div class="pageHead-text">([^<]+)</div>', html
        )
        pic = self._match(r'lay-src="([^"]+\.(?:jpg|jpeg|png|webp))"', html)
        actor = self._match(r'主演：([^<]+)', html)
        director = self._match(r'导演：([^<]+)', html)
        desc = self._match(
            r'<div class="vod-info-text">.*?<span>简介：</span>(.*?)<div', html, re.S
        )
        meta = self._match(r'<p>([^<]*•[^<]*)</p>', html)

        vod = {
            "vod_id": vod_id,
            "vod_name": self._strip_tags(title) or vod_id,
            "vod_pic": self._norm_url(pic),
            "vod_actor": self._strip_tags(actor),
            "vod_director": self._strip_tags(director),
            "vod_content": self._strip_tags(desc)[:500],
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": "",
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        if meta:
            parts = [p.strip() for p in meta.split("•")]
            if len(parts) >= 1:
                vod["vod_year"] = parts[0]
            if len(parts) >= 2:
                vod["vod_area"] = parts[1]
            if len(parts) >= 3:
                vod["vod_remarks"] = parts[2]
        return {"list": [vod]}

    # ============================================================
    # 搜索
    # ============================================================

    def searchContent(self, key, quick, pg="1"):
        try:
            key = (key or "").strip()
            if not key:
                return {"list": []}

            # 搜索缓存 3 分钟（key 含页码，避免跨页误命中）
            ckey = "%s|%s" % (pg or "1", key)
            cached = self._cache_get(self._search_cache, ckey, TTL_SEARCH)
            if cached is not None:
                return cached

            url = HOST + "/search.html?key=" + quote(key, safe="")
            if pg and pg != "1":
                url += "&page=" + str(pg)
            html = self._get(url, timeout=TIMEOUT_PAGE)
            vods = self._parse_cards(html)

            result = {"list": vods}
            self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
            return result
        except Exception:
            return {"list": []}

    # ============================================================
    # 播放解析（直链优先 + 缓存 + 冗余切换）
    # ============================================================

    def _first_target(self, vod):
        """取默认线路第 1 个剧集的 (vid, jid)"""
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            for item in seg.split("#"):
                m = re.match(r'^[^$]*\$(\d+)\|(\d+)$', item.strip())
                if m:
                    return m.group(1), m.group(2)
        return None

    def _alt_targets(self, vod_id, cur_vid, cur_jid, limit=6):
        """从详情缓存收集其他线路/剧集的 (vid, jid)，供失效切换"""
        cached = self._cache_get(self._detail_cache, vod_id, TTL_DETAIL_OK)
        if not cached or not cached.get("list"):
            return []
        vod = cached["list"][0]
        out, seen = [], set()
        cur = (str(cur_vid), str(cur_jid))
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            for item in seg.split("#"):
                m = re.match(r'^[^$]*\$(\d+)\|(\d+)$', item.strip())
                if m:
                    k = (m.group(1), m.group(2))
                    if k == cur or k in seen:
                        continue
                    seen.add(k)
                    out.append(k)
                    if len(out) >= limit:
                        return out
        return out

    def _play_direct(self, vid, jid):
        """请求一条线路的 m3u8 直链，成功则写入播放缓存"""
        data = self._post_json(
            HOST + "/api/vod_url/%s/%s" % (vid, jid), timeout=TIMEOUT_API
        )
        if data and data.get("code") == 1:
            playurl = ((data.get("data") or {}).get("playurl") or "").replace("\\/", "/")
            if playurl:
                self._cache_set(self._play_cache, (vid, jid), playurl, TTL_PLAY)
                return playurl
        return ""

    def _prefetch_play(self, vod):
        """后台线程预取默认线路第 1 集直链（点播秒开）"""
        if self._session is None:
            return
        target = self._first_target(vod)
        if not target:
            return
        vid, jid = target
        with self._lock:
            if self._play_cache.get((vid, jid)) or self._prefetching.get((vid, jid)):
                return
            self._prefetching[(vid, jid)] = True

        def _job():
            try:
                self._play_direct(vid, jid)
            except Exception:
                pass
            finally:
                with self._lock:
                    self._prefetching.pop((vid, jid), None)

        threading.Thread(target=_job, daemon=True).start()

    def _play_payload(self, playurl):
        """组装直连播放结果（parse=0 秒开）"""
        is_m3u8 = ".m3u8" in playurl.lower()
        return {
            "parse": 0,
            "playUrl": "",
            "url": playurl,
            "header": {
                "User-Agent": UA,
                "Referer": HOST + "/",
                "Origin": HOST,
            },
            "format": "application/x-mpegURL" if is_m3u8 else "",
            "contentType": "application/x-mpegURL" if is_m3u8 else "",
        }

    def _play_page_fallback(self, vid, jid):
        """直链失败：返回原站播放页，交给壳子嗅探"""
        return {
            "parse": 1,
            "playUrl": "",
            "url": "https://qndjy.com/play/%s/%s.html" % (vid, jid),
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}

        # id 格式: "57450|1143508"（详情页构造）
        parts = str(id).split("|")
        vid = parts[0]
        jid = parts[1] if len(parts) > 1 else ""
        if not jid:
            return self._play_page_fallback(vid, jid)

        # 1) 命中缓存：重复点播/切集秒回
        cached = self._cache_get(self._play_cache, (vid, jid), TTL_PLAY)
        if cached:
            return self._play_payload(cached)

        # 2) 当前线路直取
        playurl = self._play_direct(vid, jid)
        if playurl:
            return self._play_payload(playurl)

        # 3) 冗余切换：当前线路失效，并发探测其他线路/剧集，取最快成功者
        alts = self._alt_targets(vid, vid, jid)
        if alts and ThreadPoolExecutor is not None:
            try:
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futs = [ex.submit(self._play_direct, v, j) for v, j in alts]
                    for f in as_completed(futs, timeout=TIMEOUT_API):
                        u = f.result(timeout=TIMEOUT_API)
                        if u:
                            self._cache_set(self._play_cache, (vid, jid), u, TTL_PLAY)
                            return self._play_payload(u)
            except Exception:
                pass
        else:
            for v, j in alts:
                u = self._play_direct(v, j)
                if u:
                    self._cache_set(self._play_cache, (vid, jid), u, TTL_PLAY)
                    return self._play_payload(u)

        # 4) 全部失败：回退原站播放页嗅探
        return self._play_page_fallback(vid, jid)

    # ===== 本地代理 =====
    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    # ===== 清理 =====
    def destroy(self):
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass

    def close(self):
        self.destroy()
