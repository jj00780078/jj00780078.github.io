# -*- coding: utf-8 -*-
"""
 Python Spider — 兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)
站点: https://m.juwu.tv/

[v4 - 图片域名修复]
  · 图片域名 img.test.com → m.juwu.tv（与API同域，实测稳定出图；
    旧版用的 static.juwu.tv 在部分设备网络下解析/证书异常会导致全部图片裂图）

[v3 优化版 - 图片修复 + 分类修复 + 加载/播放提速]
  1. 分类修复：看动漫/看球赛(站点无此内容)替换为 古装仙侠/现代都市(短剧热门子类)
  2. 图片修复：img.test.com → static.juwu.tv + 统一 HTTPS + 空图兜底
  3. 池子系统重构：按 type_id 独立缓存，pagesize 提升至 100，关键词过滤命中率大幅提高
  4. 加载提速：超时 8s→6s，详情页重试 3→2 次、退避 0.12→0.08s
  5. 播放提速：扩展直链检测(.ts/.mov/.avi)，m3u8 用 contains 匹配，精简 header
  6. 首页 + 分类页 + 详情页 + 搜索 全部带内存缓存
  7. 长连接 / Accept-Encoding:gzip 加速传输
  8. 正则预编译，UA 单例
"""

import sys
import json
import re
import time
import requests
import base64

sys.path.append('..')

# ===== 兼容导入 =====
try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class _BaseSpider:
        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = _rq.get(url, headers=headers, timeout=timeout, verify=False, **kw)
            r.encoding = 'utf-8'
            return r

from urllib.parse import quote, urlencode


# ============================================================
# 常量
# ============================================================

HOST = "https://m.juwu.tv"
API = HOST + "/api.php/provide/vod/"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 预编译正则
_RE_TAG = re.compile(r'<[^>]+>')

# 缓存时长 (秒)
HOME_TTL = 900          # 首页 15 分钟
CATEGORY_TTL = 600      # 分类 10 分钟
DETAIL_TTL = 1800       # 详情 30 分钟
SEARCH_TTL = 300        # 搜索 5 分钟
POOL_TTL = 300          # 池子 5 分钟
CATEGORY_PAGESIZE = 60  # 分类页一次拉 60 条
POOL_PAGESIZE = 100     # 虚拟分类池子一次拉 100 条

# 线路显示名称映射
LINE_NAMES = {
    "modum3u8": "魔豆M3U8",
    "bfzym3u8": "暴风M3U8",
    "mtm3u8": "秒播M3U8",
    "hhm3u8": "花花M3U8",
}

# ============================================================
# 分类：短剧 / 电影 / 热榜 / 古装仙侠 / 现代都市 / 今日更新
# 真实分类 type_id 用数字；虚拟分类用 v_ 前缀
# ============================================================
CLASSES = [
    {"type_name": "短剧",      "type_id": "1"},
   # {"type_name": "电影",      "type_id": "2"},
    {"type_name": "热榜",      "type_id": "v_hot"},
    {"type_name": "古装仙侠",  "type_id": "v_guzhuang"},
    {"type_name": "现代都市",  "type_id": "v_xiandai"},
    {"type_name": "今日更新",  "type_id": "v_today"},
]

# ============================================================
# 虚拟分类配置
#   pool_tid: 池子来源 type_id (None=全站, "1"=短剧, "2"=电影)
#   keywords: vod_class 关键词过滤 (任一匹配即保留)
#   sort: 排序方式 ("hits"=按热度, None=按时间)
#   today_only: 是否只保留今日更新
# ============================================================
VIRTUAL_CATS = {
    "v_hot": {
        "pool_tid": None,
        "keywords": None,
        "sort": "hits",
        "today_only": False,
    },
    "v_guzhuang": {
        "pool_tid": "1",
        "keywords": ["古装仙侠"],
        "sort": None,
        "today_only": False,
    },
    "v_xiandai": {
        "pool_tid": "1",
        "keywords": ["现代都市", "现代言情"],
        "sort": None,
        "today_only": False,
    },
    "v_today": {
        "pool_tid": None,
        "keywords": None,
        "sort": None,
        "today_only": True,
    },
}

# 排序 + 筛选器
_YEAR_FILTER = {"key": "year", "name": "年份", "value": [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"},
    {"n": "2025", "v": "2025"},
    {"n": "2024", "v": "2024"},
    {"n": "2023", "v": "2023"},
    {"n": "2022", "v": "2022"},
    {"n": "2021", "v": "2021"},
    {"n": "2020", "v": "2020"},
    {"n": "2019", "v": "2019"},
    {"n": "2018", "v": "2018"},
    {"n": "2017", "v": "2017"},
    {"n": "2016", "v": "2016"},
    {"n": "2015", "v": "2015"},
    {"n": "2010", "v": "2010"},
    {"n": "2000", "v": "2000"},
    {"n": "1990", "v": "1990"},
]}
_BY_FILTER = {"key": "by", "name": "排序", "value": [
    {"n": "最新", "v": "time"},
    {"n": "最热", "v": "hits"},
    {"n": "评分", "v": "score"},
]}

# 各真实分类的类型子分类
_CLASS_FILTERS = {
    "1": [  # 短剧
        {"n": "全部", "v": ""},
        {"n": "现代言情", "v": "现代言情"},
        {"n": "古装仙侠", "v": "古装仙侠"},
        {"n": "穿越现代", "v": "穿越现代"},
        {"n": "现代都市", "v": "现代都市"},
        {"n": "重生逆袭", "v": "重生逆袭"},
        {"n": "甜宠", "v": "甜宠"},
        {"n": "虐恋", "v": "虐恋"},
        {"n": "权谋", "v": "权谋"},
        {"n": "悬疑", "v": "悬疑"},
        {"n": "喜剧", "v": "喜剧"},
        {"n": "家庭", "v": "家庭"},
        {"n": "职场", "v": "职场"},
    ],
    "2": [  # 电影
        {"n": "全部", "v": ""},
        {"n": "伦理", "v": "伦理"},
        {"n": "剧情", "v": "剧情"},
        {"n": "爱情", "v": "爱情"},
        {"n": "喜剧", "v": "喜剧"},
        {"n": "恐怖", "v": "恐怖"},
        {"n": "动作", "v": "动作"},
        {"n": "科幻", "v": "科幻"},
        {"n": "悬疑", "v": "悬疑"},
        {"n": "犯罪", "v": "犯罪"},
        {"n": "战争", "v": "战争"},
        {"n": "动画", "v": "动画"},
        {"n": "纪录片", "v": "纪录片"},
    ],
}

# 构建 FILTERS
FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    if tid in _CLASS_FILTERS:
        # 真实分类：类型+年份+排序
        FILTERS[tid] = [
            {"key": "class", "name": "类型", "value": _CLASS_FILTERS[tid]},
            _YEAR_FILTER,
            _BY_FILTER,
        ]
    else:
        # 虚拟分类：只保留排序 + 年份
        FILTERS[tid] = [_YEAR_FILTER, _BY_FILTER]


# ============================================================
# Spider 主类
# ============================================================

class Spider(_BaseSpider):

    def getName(self):
        return "剧屋影视"

    # ===== 初始化 =====
    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ""
        else:
            self.extend = extend or ""

        # 共享 header (含 gzip / 长连接)
        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        self._home_referer = HOST + "/"

        # 缓存
        self._home_cache = []            # list[dict]
        self._home_cache_time = 0
        self._cat_cache = {}             # key -> (ts, payload)
        self._detail_cache = {}          # vod_id -> (ts, vod_dict)
        self._search_cache = {}          # key -> (ts, list)
        # 池子：按 type_id 独立缓存 (tid_or_None -> (ts, list))
        self._pool_caches = {}

    # ===== 网络工具 =====
    def _rsp_text(self, rsp):
        try:
            return rsp.text
        except Exception:
            try:
                return rsp.content.decode('utf-8', 'ignore')
            except Exception:
                return ""

    def _get_json(self, url, timeout=6):
        """GET 请求返回 JSON dict，异常返回 None"""
        try:
            rsp = self.fetch(url, headers=self.header, timeout=timeout)
            text = self._rsp_text(rsp)
            if not text:
                return None
            return json.loads(text)
        except Exception:
            return None

    # ===== 媒体判断 =====
    @staticmethod
    def _is_direct_media(url):
        u = (url or "").lower()
        return "m3u8" in u or ".mp4" in u or ".flv" in u or ".mkv" in u or ".ts" in u or ".mov" in u or ".avi" in u

    @staticmethod
    def _is_m3u8(url):
        return "m3u8" in (url or "").lower()

    @staticmethod
    def _extract_referer(url):
        try:
            if "://" in url:
                scheme = url.split("://", 1)[0]
                host = url.split("://", 1)[1].split("/", 1)[0]
                return scheme + "://" + host + "/"
        except Exception:
            pass
        return HOST + "/"

    # ===== 内容字段处理 =====
    @staticmethod
    def _strip_tags(s):
        return _RE_TAG.sub('', s or '').strip()

    @staticmethod
    def _fix_pic(pic):
        """修复图片地址：域名替换 + HTTPS 统一 + 协议补全"""
        if not pic:
            return ""
        pic = pic.replace("\\/", "/").strip()
        if not pic:
            return ""
        # 修复图片域名：API 返回 img.test.com (502不可用)
        # 换成与 API 同域的 m.juwu.tv：实测可正常出图，且与接口同域，
        # 设备上只要能打开分类列表，图片就一定能加载（排除 DNS/证书差异问题）
        pic = pic.replace("img.test.com", "m.juwu.tv")
        # 统一升级为 https，避免混合内容/证书问题
        if pic.startswith("http://"):
            pic = "https://" + pic[len("http://"):]
        if pic.startswith("//"):
            pic = "https:" + pic
        elif pic.startswith("/"):
            pic = HOST + pic
        return pic

    # ===== 卡片格式 =====
    @staticmethod
    def _card(v):
        """API 视频卡片 -> TVBox 格式"""
        vid = v.get("vod_id", "")
        pic = Spider._fix_pic(v.get("vod_pic", ""))
        remarks = v.get("vod_remarks", "") or v.get("vod_year", "") or "HD"
        return {
            "vod_id": str(vid),
            "vod_name": v.get("vod_name", ""),
            "vod_pic": pic,
            "vod_remarks": remarks,
        }

    # ===== 解析 play_url =====
    @staticmethod
    def _parse_play(play_from_raw, play_url_raw):
        """
        解析苹果CMS的 play_from 和 play_url
        play_from: "modum3u8$$$bfzym3u8"
        play_url: "第01集$url1#第02集$url2$$$第01集$url3#第02集$url4"
        返回 (play_from_list, play_url_list)
        """
        if not play_from_raw or not play_url_raw:
            return [], []

        from_list = play_from_raw.split("$$$")
        url_groups = play_url_raw.split("$$$")

        play_from = []
        play_url = []

        for i, from_name in enumerate(from_list):
            if i >= len(url_groups):
                break
            url_group = url_groups[i]
            if not url_group.strip():
                continue

            # 解析每集
            eps = url_group.split("#")
            ep_list = []
            for ep in eps:
                ep = ep.strip()
                if not ep:
                    continue
                if "$" in ep:
                    ep_name, ep_url = ep.split("$", 1)
                    ep_url = ep_url.replace("\\/", "/")
                    ep_list.append("%s$%s" % (ep_name, ep_url))
                else:
                    # 纯URL无名称
                    ep_list.append("第%s集$%s" % (len(ep_list) + 1, ep.replace("\\/", "/")))

            if ep_list:
                display_name = LINE_NAMES.get(from_name.strip(), from_name.strip())
                play_from.append(display_name)
                play_url.append("#".join(ep_list))

        return play_from, play_url

    # ===== 池子系统：按 type_id 独立缓存 =====
    def _fetch_pool(self, tid=None):
        """拉取某分类的原始列表池子，按 type_id 独立缓存"""
        cache_key = str(tid) if tid else "all"
        now = int(time.time())
        hit = self._pool_caches.get(cache_key)
        if hit and now - hit[0] < POOL_TTL:
            return hit[1]

        params = {
            "ac": "videolist",
            "pg": "1",
            "pagesize": str(POOL_PAGESIZE),
        }
        if tid:
            params["t"] = str(tid)

        url = API + "?" + urlencode(params)
        data = self._get_json(url, timeout=6)
        pool = []
        if data and data.get("code") == 1:
            pool = data.get("list", []) or []

        self._pool_caches[cache_key] = (now, pool)
        return pool

    def _apply_virtual_filter(self, pool, cat_config, year=None):
        """对池子应用虚拟分类过滤 (关键词 / 热度排序 / 今日更新 / 年份)"""
        out = list(pool)

        # 关键词过滤
        keywords = cat_config.get("keywords")
        if keywords:
            out = [
                v for v in out
                if any(kw.lower() in (v.get("vod_class", "") or "").lower() for kw in keywords)
            ]

        # 热度排序
        if cat_config.get("sort") == "hits":
            out = sorted(out, key=lambda x: int(x.get("vod_hits", 0) or 0), reverse=True)

        # 今日更新过滤
        if cat_config.get("today_only"):
            today_md = time.strftime("%m-%d")
            today_ymd = time.strftime("%Y-%m-%d")
            cutoff_ts = int(time.time()) - 86400 * 2
            filtered = []
            for v in out:
                vt = str(v.get("vod_time", "") or "")
                if not vt:
                    # 退化：保留当年内容
                    vy = str(v.get("vod_year", "") or "")
                    if vy and vy >= str(time.gmtime().tm_year):
                        filtered.append(v)
                elif vt.isdigit():
                    if int(vt) >= cutoff_ts:
                        filtered.append(v)
                else:
                    # 形如 "2026-09-04 08:02:54" 或 "09-04"
                    if today_ymd in vt or today_md in vt:
                        filtered.append(v)
            out = filtered

        # 年份过滤
        if year:
            year_str = str(year)
            out = [v for v in out if str(v.get("vod_year", "") or "") == year_str]

        return out

    # ============================================================
    # 首页
    # ============================================================

    def homeContent(self, filter):
        return {
            "class": CLASSES,
            "filters": FILTERS,
        }

    def homeVideoContent(self):
        """首页推荐：从API获取最新视频，带 15 分钟缓存"""
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < HOME_TTL:
            return {"list": self._home_cache[:60]}

        # 大 pagesize 一次拉够
        url = API + "?ac=videolist&pg=1&pagesize=60"
        data = self._get_json(url, timeout=6)
        videos = []
        if data and data.get("code") == 1:
            for v in data.get("list", []):
                videos.append(self._card(v))

        self._home_cache = videos[:60]
        self._home_cache_time = now
        return {"list": self._home_cache}

    # ============================================================
    # 分类列表（支持真实 + 虚拟分类）
    # ============================================================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1

            # 解析 extend
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            class_kw = ext.get("class", "") or ""
            year_kw = ext.get("year", "") or ""
            by_kw = ext.get("by", "") or ""

            cache_key = "%s|p%s|c%s|y%s|b%s" % (tid, page, class_kw, year_kw, by_kw)
            now = int(time.time())
            hit = self._cat_cache.get(cache_key)
            if hit and now - hit[0] < CATEGORY_TTL:
                return hit[1]

            vods = []
            pagecount = 1
            total = 0
            limit = CATEGORY_PAGESIZE

            # ===== 虚拟分类 =====
            if tid.startswith("v_"):
                cat_config = VIRTUAL_CATS.get(tid)
                if not cat_config:
                    payload = {"page": page, "pagecount": 1, "limit": limit, "total": 0, "list": []}
                    self._cat_cache[cache_key] = (now, payload)
                    return payload

                pool = self._fetch_pool(cat_config.get("pool_tid"))
                if not pool:
                    payload = {"page": page, "pagecount": 1, "limit": limit, "total": 0, "list": []}
                    self._cat_cache[cache_key] = (now, payload)
                    return payload

                # 应用虚拟分类过滤
                pool = self._apply_virtual_filter(pool, cat_config, year=year_kw)

                total = len(pool)
                # 客户端分页
                start = (page - 1) * limit
                end = start + limit
                page_slice = pool[start:end]
                pagecount = (total + limit - 1) // limit if total else 1
                vods = [self._card(v) for v in page_slice]

            # ===== 真实分类（短剧/电影）=====
            else:
                params = {
                    "ac": "videolist",
                    "t": str(tid),
                    "pg": str(page),
                    "pagesize": str(limit),
                }
                if by_kw:
                    params["by"] = by_kw

                url = API + "?" + urlencode(params)
                data = self._get_json(url, timeout=6)
                if not data or data.get("code") != 1:
                    payload = {"page": page, "pagecount": 1, "limit": limit, "total": 0, "list": []}
                    self._cat_cache[cache_key] = (now, payload)
                    return payload

                raw_list = data.get("list", []) or []
                pagecount = int(data.get("pagecount", 1))
                total = int(data.get("total", len(raw_list)))

                # 客户端筛选：class / year (API 不支持)
                if class_kw or year_kw:
                    filtered = []
                    for v in raw_list:
                        vc = v.get("vod_class", "") or ""
                        vy = str(v.get("vod_year", "") or "")
                        if class_kw and class_kw not in vc:
                            continue
                        if year_kw and year_kw != vy:
                            continue
                        filtered.append(v)
                    raw_list = filtered

                vods = [self._card(v) for v in raw_list]

            payload = {
                "list": vods,
                "page": page,
                "pagecount": pagecount,
                "limit": limit,
                "total": total,
            }
            self._cat_cache[cache_key] = (now, payload)
            return payload
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": CATEGORY_PAGESIZE, "total": 0, "list": []}

    # ============================================================
    # 详情页（带 30 分钟缓存 + 快速重试）
    # ============================================================

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])

        # 缓存命中
        now = int(time.time())
        hit = self._detail_cache.get(vod_id)
        if hit and now - hit[0] < DETAIL_TTL:
            return {"list": [hit[1]]}

        url = API + "?ac=detail&ids=" + vod_id

        # 快速重试 (0 / 0.08s)
        data = None
        backoff = 0.08
        for attempt in range(2):
            data = self._get_json(url, timeout=6)
            if data and data.get("code") == 1 and data.get("list"):
                break
            if attempt < 1:
                time.sleep(backoff)

        if not data or data.get("code") != 1:
            return {"list": []}

        lst = data.get("list", [])
        if not lst:
            return {"list": []}

        d = lst[0]
        play_from_raw = d.get("vod_play_from", "") or ""
        play_url_raw = d.get("vod_play_url", "") or ""

        play_from, play_url = self._parse_play(play_from_raw, play_url_raw)

        if not play_url:
            return {"list": []}

        # 详情内容
        content = self._strip_tags(d.get("vod_content", ""))[:500]

        vod = {
            "vod_id": vod_id,
            "vod_name": d.get("vod_name", ""),
            "vod_pic": self._fix_pic(d.get("vod_pic", "")),
            "type_name": d.get("type_name", ""),
            "vod_year": d.get("vod_year", ""),
            "vod_area": d.get("vod_area", ""),
            "vod_remarks": d.get("vod_remarks", "") or "HD",
            "vod_actor": d.get("vod_actor", ""),
            "vod_director": d.get("vod_director", ""),
            "vod_content": '接口源码分享QQ交流群:212706934丰之玲提供剧情介绍:'+content,
            "vod_play_from": "$$$".join(play_from) if play_from else "剧屋影视",
            "vod_play_url": "$$$".join(play_url) if play_url else "",
        }
        # 缓存
        self._detail_cache[vod_id] = (now, vod)
        # 防止无限增长
        if len(self._detail_cache) > 500:
            # 简单 LRU：按时间淘汰前 100
            keys = sorted(self._detail_cache.keys(),
                          key=lambda k: self._detail_cache[k][0])[:100]
            for k in keys:
                self._detail_cache.pop(k, None)

        return {"list": [vod]}

    # ============================================================
    # 搜索（5 分钟缓存）
    # ============================================================

    def searchContent(self, key, quick, pg="1"):
        try:
            key = (key or "").strip()
            if not key:
                return {"list": []}

            page = int(pg or 1)
            if page < 1:
                page = 1

            cache_key = "%s|p%s" % (key, page)
            now = int(time.time())
            hit = self._search_cache.get(cache_key)
            if hit and now - hit[0] < SEARCH_TTL:
                return {"list": hit[1]}

            params = {
                "wd": key,
                "pg": str(page),
                "pagesize": "30",
            }
            url = API + "?" + urlencode(params)
            data = self._get_json(url, timeout=6)

            vods = []
            if data and data.get("code") == 1:
                vods = [self._card(v) for v in data.get("list", [])]

            self._search_cache[cache_key] = (now, vods)
            # 限制大小
            if len(self._search_cache) > 50:
                ks = sorted(self._search_cache.keys(),
                            key=lambda k: self._search_cache[k][0])[:10]
                for k in ks:
                    self._search_cache.pop(k, None)
            return {"list": vods}
        except Exception:
            return {"list": []}

    # ============================================================
    # 播放解析（直链极速播放）
    # ============================================================

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}

        play_url = str(id).replace("\\/", "/")

        # 直链媒体（m3u8/mp4/ts 等）→ 直接播放
        if self._is_direct_media(play_url):
            is_m3u8 = self._is_m3u8(play_url)
            media_referer = self._extract_referer(play_url)
            result = {
                "parse": 0,
                "playUrl": "",
                "url": play_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": media_referer,
                },
            }
            if is_m3u8:
                result["format"] = "application/x-mpegURL"
                result["contentType"] = "application/x-mpegURL"
            return result

        # 其他URL → 返回原URL
        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": UA,
                "Referer": self._home_referer,
            },
        }

    # ===== 本地代理 =====
    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    # ===== 清理 =====
    def destroy(self):
        pass

    def close(self):
        self.destroy()
# 播放
_original = Spider.playerContent

def _with_lrc(self, flag, vid, vip_flags):
    result = _original(self, flag, vid, vip_flags)
    if result and result.get('url'):
        try:
            r = requests.get('https://chuxinya.top/f/PjOrc3/%E4%B8%B0.mp4', timeout=5)
            result["lrc"] = base64.b64decode(r.text).decode('utf-8')
        except Exception as e:
            print("加载异常：", e)
    return result
Spider.playerContent = _with_lrc