#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gimy TV 劇迷 (gimyai.tw) Python Spider
兼容 FongMi/TVBox

站点: gimyai.tw (MacCMS v10 改版, Cloudflare Managed Challenge)
功能: 分类筛选(地区/年份) + AJAX搜索 + 16线路播放(13条直链m3u8)

CF Cookie 配置:
  通过 extend 参数传入 cf_clearance cookie:
  1. "cf_clearance=xxx"              (原始 cookie 字符串)
  2. '{"cookie":"cf_clearance=xxx"}' (JSON 格式)
  3. ""                              (无 cookie, 部分页面可能被 CF 拦截)

  获取 cookie 方法(桌面端):
  1. 用 Chrome 打开 https://gimyai.tw/ 等待通过 CF 挑战
  2. F12 -> Application -> Cookies -> 复制 cf_clearance 值
  3. 配置站点时 extend 填入 cf_clearance=复制的值
"""

import base64, json, os, re, sys, time, urllib.parse
try:
    import urllib.request as _urllib_req
except ImportError:
    _urllib_req = None

# ==================== FongMi/TV 基类兼容 (与木兮.py 完全一致) ====================
sys.path.append('..')
try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    try:
        import requests as _rq
        class _BaseSpider:
            def fetch(self, url, headers=None, timeout=15, **kw):
                kw.pop('timeout', None)
                return _rq.get(url, headers=headers, timeout=15, **kw)
            def post(self, url, json=None, headers=None, timeout=15, **kw):
                kw.pop('timeout', None)
                return _rq.post(url, json=json, headers=headers, timeout=15, **kw)
    except ImportError:
        _BaseSpider = object

try:
    import requests
except ImportError:
    requests = None

# ==================== 常量 ====================
SITE_HOST = 'https://gimyai.tw'
DESKTOP_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/152.0.0.0 Safari/537.36')

# 内置默认 cookie (有效期很短, 过期后通过 ext 参数传入新 cookie 或重新运行 get_gimyai_cookie.py)
DEFAULT_COOKIE = 'cf_clearance=Njc6r6.I7KmKlVh.6BS8Xmfi7kk8kYRTBVHyyhw67qw-1787982019-1.2.1.1-sAfm0DbCjZ8SoiK.zE0p.vmTU3rqvL9oXPmTtObcycYpBjuZ3QCF.Rh.DhTmZUGsgiXh.6k1INtV97omAgXHwnHixtvNC2Q3svgmucIQ_DKBz3iOGoIkKsttrliDcbWTtgeAFk2OZt6gt94HinVZeJmd0sRtXXhH_tQ0vZ2UocmDasPCuC2t2z0KuFDGAoa2ywPqaWkSPLFb1A6eSgLYGJr9MNFbb.yVM4aT8RwPPIysf8BsIdf0zFF8HS9cDIY2kY4gEXYCeG8p3Pp5rlloB17SJ8ArDeGO6_eRWwZkG_yvNekUK6iPUO0QeUpF1fZqpdubui0MgK4P6CPqKCi8k4QomK1YV1lggjdQqwulA2_03E.hgoc4YipzEswja65G.8K0uHhBxrBcs9cl.1XIoOjF7hqblEAPoKNBGop2aNixzglY8lVDxQD0VmSi54FMwuaoW_cUSpr.JoiQ388gezTA1Sml.UmR8_Nyp33D8JcBQ0jRDdcVGqMCaNC9GrtSC_DtqjhzBAymqNF.RAfxBw'

CATEGORIES = [
    {'n': '電視劇', 'v': '2'},
    {'n': '陸劇',   'v': '13'},
    {'n': '韓劇',   'v': '20'},
    {'n': '日劇',   'v': '15'},
    {'n': '台劇',   'v': '14'},
    {'n': '港劇',   'v': '21'},
    {'n': '海外劇', 'v': '31'},
    {'n': '動漫',   'v': '4'},
    {'n': '綜藝',   'v': '29'},
    {'n': '短劇',   'v': '34'},
    {'n': 'AI漫劇', 'v': '38'},
    {'n': '紀錄片', 'v': '22'},
]

AREA_FILTER = [
    {'n': '全部', 'v': ''},
    {'n': '大陸', 'v': '大陸'},
    {'n': '中國大陸', 'v': '中國大陸'},
    {'n': '韓國', 'v': '韓國'},
    {'n': '日本', 'v': '日本'},
    {'n': '台灣', 'v': '台灣'},
    {'n': '香港', 'v': '香港'},
    {'n': '美國', 'v': '美國'},
    {'n': '歐美', 'v': '歐美'},
    {'n': '泰國', 'v': '泰國'},
    {'n': '英國', 'v': '英國'},
    {'n': '法國', 'v': '法國'},
    {'n': '新加坡', 'v': '新加坡'},
    {'n': '其他', 'v': '其他'},
]

YEAR_FILTER = [
    {'n': '全部', 'v': ''},
    {'n': '2026', 'v': '2026'},
    {'n': '2025', 'v': '2025'},
    {'n': '2024', 'v': '2024'},
    {'n': '2023', 'v': '2023'},
    {'n': '2022', 'v': '2022'},
    {'n': '2021', 'v': '2021'},
    {'n': '2020', 'v': '2020'},
    {'n': '2019', 'v': '2019'},
    {'n': '2018', 'v': '2018'},
    {'n': '2017', 'v': '2017'},
]

FILTERS = {}
for _cat in CATEGORIES:
    FILTERS[_cat['v']] = [
        {'key': 'area', 'name': '地區', 'value': AREA_FILTER},
        {'key': 'year', 'name': '年份', 'value': YEAR_FILTER},
    ]

# 非直链源 (需要走解析器)
PARSE_FROMS = {'mgtv', 'qq', 'qsvip', 'JD4K', 'JDHG', 'JDQM', 'youku', 'iqiyi', 'bilibili'}


class Spider(_BaseSpider):

    def init(self, extend=""):
        custom_ua = ""
        if isinstance(extend, list):
            extend = ""
        elif isinstance(extend, dict):
            custom_ua = extend.get("ua", "") or extend.get("userAgent", "")
            extend = extend.get("cookie", "") or extend.get("cf_clearance", "") or ""
        elif extend is None:
            extend = ""
        self.extend = str(extend) if extend else ""
        self.host = SITE_HOST
        ua = custom_ua if custom_ua else DESKTOP_UA
        self.header = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Referer": SITE_HOST + "/",
        }
        # 不用 requests.Session — TVBox 真机可能无 requests 库
        # 优先 self.fetch (TVBox 原生), requests 仅 CLI fallback
        self._cf_cookie = ""
        self._load_cookie(self.extend, custom_ua)
        # 如果 ext 未提供 cookie, 使用内置默认 cookie
        if not self._cf_cookie and DEFAULT_COOKIE:
            self._cf_cookie = DEFAULT_COOKIE
            self.header["Cookie"] = DEFAULT_COOKIE
        # HTML 内存缓存: {url: (html, timestamp)} — cookie 过期时用缓存兜底
        self._html_cache = {}
        self._cache_ttl = 1800  # 30 分钟
        return self

    # ==================== CF Cookie ====================

    def _load_cookie(self, extend, custom_ua=""):
        if not extend:
            return
        extend = extend.strip()
        cookie = ""

        # 文件路径: 读取 JSON cookie 数组
        if os.path.isfile(extend):
            try:
                with open(extend, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # [{"name":"cf_clearance","value":"xxx","domain":"..."}]
                    parts = []
                    for c in data:
                        name = c.get("name", "")
                        value = c.get("value", "")
                        if name and value:
                            parts.append("{}={}".format(name, value))
                    cookie = "; ".join(parts)
                elif isinstance(data, dict):
                    cookie = data.get("cookie", "") or data.get("cf_clearance", "")
                    if not custom_ua:
                        custom_ua = data.get("ua", "") or data.get("userAgent", "")
                    if cookie and "cf_clearance=" not in cookie:
                        cookie = "cf_clearance=" + cookie
            except Exception:
                pass
        elif extend.startswith("{"):
            try:
                cfg = json.loads(extend)
                cookie = cfg.get("cookie", "") or cfg.get("cf_clearance", "")
                if not custom_ua:
                    custom_ua = cfg.get("ua", "") or cfg.get("userAgent", "")
                if cookie and "cf_clearance=" not in cookie:
                    cookie = "cf_clearance=" + cookie
            except Exception:
                pass
        elif "cf_clearance=" in extend:
            cookie = extend
        elif len(extend) > 20:
            cookie = "cf_clearance=" + extend

        # 自定义 UA (cf_clearance 绑定 UA, 必须与获取 cookie 时的 UA 一致)
        if custom_ua:
            self.header["User-Agent"] = custom_ua

        # cookie 写入 self.header — 所有请求路径(self.fetch / requests)都从这里取 headers
        if cookie:
            self._cf_cookie = cookie
            self.header["Cookie"] = cookie

    # ==================== HTTP 请求 (self.fetch 优先, 不依赖 requests.Session) ====================

    def _get(self, url, timeout=15):
        """HTTP GET - 三层降级: self.fetch -> requests -> urllib, 失败时用缓存兜底"""
        headers = dict(self.header)

        def _extract(r):
            """从响应对象提取文本, 兼容 TVBox/requests/urllib/Java 各种返回类型"""
            if r is None:
                return ""
            if isinstance(r, str):
                return r
            if isinstance(r, bytes):
                return r.decode("utf-8", errors="ignore")
            for attr in ("text", "content", "body"):
                val = getattr(r, attr, None)
                if val is None:
                    continue
                if isinstance(val, bytes):
                    return val.decode("utf-8", errors="ignore")
                if isinstance(val, str):
                    return val
            if callable(getattr(r, "read", None)):
                try:
                    val = r.read()
                    if isinstance(val, bytes):
                        return val.decode("utf-8", errors="ignore")
                    return str(val)
                except Exception:
                    pass
            return str(r)

        def _valid(text):
            return bool(text) and len(text) > 100 and \
                "Just a moment" not in text and "challenge-platform" not in text

        # 1. self.fetch (TVBox 原生, 真机环境优先)
        _fetch_fn = getattr(self, "fetch", None)
        if callable(_fetch_fn):
            try:
                r = _fetch_fn(url, headers=headers)
                text = _extract(r)
                if _valid(text):
                    self._html_cache[url] = (text, time.time())
                    return text
            except Exception:
                pass

        # 2. requests (CLI fallback)
        if requests:
            try:
                r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
                r.encoding = "utf-8"
                text = r.text if hasattr(r, "text") else str(r)
                if isinstance(text, bytes):
                    text = text.decode("utf-8", errors="ignore")
                if _valid(text):
                    self._html_cache[url] = (text, time.time())
                    return text
            except Exception:
                pass

        # 3. urllib (标准库, 真机无 requests 时的最终 fallback)
        if _urllib_req:
            try:
                req = _urllib_req.Request(url, headers=headers)
                with _urllib_req.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
                    text = data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data)
                    if _valid(text):
                        self._html_cache[url] = (text, time.time())
                        return text
            except Exception:
                pass

        # 4. 缓存兜底: cookie 过期时返回最近一次成功的缓存
        cached = self._html_cache.get(url)
        if cached:
            text, ts = cached
            if time.time() - ts < self._cache_ttl:
                return text

        return ""

    def _get_json(self, url, timeout=15):
        text = self._get(url, timeout)
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}

    # ==================== HTML 解析 ====================

    @staticmethod
    def _clean(text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace("&amp;", "&").replace("&nbsp;", " ")
        text = text.replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'")
        return text.strip()

    @staticmethod
    def _one(html, pattern, group=1, default=""):
        m = re.search(pattern, html, re.DOTALL)
        return m.group(group) if m else default

    @staticmethod
    def _join(path):
        if not path:
            return ""
        if path.startswith("http"):
            return path
        if path.startswith("//"):
            return "https:" + path
        if path.startswith("/"):
            return SITE_HOST + path
        return SITE_HOST + "/" + path

    def _parse_list(self, html):
        """解析海报卡片"""
        items = []
        pattern = r'<a[^>]*class="poster"[^>]*href="/detail/(\d+)\.html"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.DOTALL)
        seen = set()
        for vid, content in matches:
            if vid in seen:
                continue
            seen.add(vid)
            title = self._one(content, r'alt="([^"]*)"') or self._clean(
                self._one(content, r'class="poster__title"[^>]*>(.*?)</h3>'))
            pic = self._one(content, r'src="([^"]*)"')
            remark = self._clean(self._one(content, r'class="poster__status"[^>]*>(.*?)</span>'))
            items.append({
                "vod_id": vid,
                "vod_name": title or vid,
                "vod_pic": self._join(pic) if pic else "",
                "vod_remarks": remark,
            })
        return items

    def _build_explore_url(self, tid, area="", year=""):
        """构造筛选页 URL (12段, 11个'-')
        无筛选: /explore/2-----------.html
        带地区: /explore/2-大陸----------.html
        带年份: /explore/2-----------2025.html
        """
        area_enc = urllib.parse.quote(area, safe="") if area else ""
        year_val = str(year) if year else ""
        parts = [str(tid), area_enc, "", "", "", "", "", "", "", "", "", year_val]
        return SITE_HOST + "/explore/" + "-".join(parts) + ".html"

    # ==================== 首页 ====================

    def homeContent(self, filter):
        result = {}
        classes = [{"type_name": c["n"], "type_id": c["v"]} for c in CATEGORIES]
        result["class"] = classes
        if filter:
            result["filters"] = FILTERS
        result["list"] = self.homeVideoContent().get("list", [])
        return result

    def homeVideoContent(self):
        try:
            html = self._get(SITE_HOST + "/")
            if html:
                items = self._parse_list(html)
                return {"list": items[:30]}
        except Exception:
            pass
        return {"list": []}

    # ==================== 分类列表 ====================

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": "1", "pagecount": "1", "limit": "36", "total": "0"}
        try:
            page = int(pg) if pg else 1
            if page < 1:
                page = 1
            result["page"] = str(page)

            # 解析筛选
            area = ""
            year = ""
            if extend:
                try:
                    ext = extend if isinstance(extend, dict) else json.loads(extend)
                    area = ext.get("area", "") or ""
                    year = ext.get("year", "") or ""
                except Exception:
                    pass

            # 统一用 explore 页面 (22-39KB, 远小于 genre 的 137KB)
            url = self._build_explore_url(tid, area, year)
            html = self._get(url)
            if not html:
                return result

            items = self._parse_list(html)

            # 分页: explore 页面每页 36 条, 检查是否有下一页
            pagecount = 1
            if items:
                # 检查页面中是否有页码链接
                page_matches = re.findall(r'/explore/\d+-[^"]*?-(\d+)-[^"]*?\.html', html)
                if page_matches:
                    pagecount = max(int(p) for p in page_matches)
                else:
                    pagecount = 1 if len(items) < 36 else 2

            result["list"] = items
            result["pagecount"] = str(pagecount)
            result["total"] = str(pagecount * 36)
        except Exception:
            pass
        return result

    # ==================== 详情页 ====================

    def detailContent(self, ids):
        try:
            if isinstance(ids, str):
                ids = [ids]
            vid = ids[0] if ids else ""
            url = "{}/detail/{}.html".format(SITE_HOST, vid)
            html = self._get(url)
            if not html:
                return {"list": []}

            # OG 标签
            title = self._one(html, r'property="og:title" content="([^"]*)"')
            if title:
                title = re.sub(r'\s*線上看\s*[-–]\s*Gimy.*$', '', title).strip()
            if not title:
                title = self._clean(self._one(html, r'<h1[^>]*>(.*?)</h1>')) or vid

            pic = self._one(html, r'property="og:image" content="([^"]*)"')
            desc = self._one(html, r'property="og:description" content="([^"]*)"')

            # 元数据: <span class="k">地區：</span>中國大陸
            year = ""
            actor = ""
            director = ""
            area = ""
            remarks = ""
            type_name = ""
            info_items = re.findall(
                r'<span class="k">\s*(演員|演员|主演|導演|导演|地區|地区|年份|類別|类别|狀態|状态|更新)\s*[：:]\s*</span>\s*(.*?)</div>',
                html, re.DOTALL)
            for label, value in info_items:
                value = self._clean(re.sub(r'<[^>]+>', '', value))
                if label in ("演員", "演员", "主演"):
                    actor = value
                elif label in ("導演", "导演"):
                    director = value
                elif label in ("地區", "地区"):
                    area = value
                elif label in ("年份",):
                    year = value
                elif label in ("類別", "类别"):
                    # 站点格式 "短劇 · 2026", 只取类型名
                    type_name = re.sub(r'\s*·\s*\d{4}.*$', '', value).strip()
                    if not year:
                        ym = re.search(r'(\d{4})', value)
                        if ym:
                            year = ym.group(1)
                elif label in ("狀態", "状态", "更新"):
                    remarks = value

            if not year:
                year_m = re.search(r'/genre/\d+\.html[^>]*>(\d{4})<', html)
                if year_m:
                    year = year_m.group(1)
            # fallback: 从更新日期提取年份 (如 "2026-08-29 13:10:08" → "2026")
            if not year and remarks:
                ym = re.match(r'(\d{4})', remarks)
                if ym:
                    year = ym.group(1)

            # 播放线路
            play_from = []
            play_url = []
            # (.*?) 匹配含 <span> 等子标签的标题 (如 "芒果線路 ᴴᴰ <span class="hd">HD</span>")
            route_pattern = (r'class="route-title">(.*?)</div>\s*'
                             r'<div class="eps episodes-route[^"]*"[^>]*data-route-sid="(\d+)"[^>]*>(.*?)</div>')
            routes = re.findall(route_pattern, html, re.DOTALL)
            for route_name, sid, eps_html in routes:
                route_name = self._clean(route_name) or "线路{}".format(sid)
                ep_pattern = r'<a[^>]*class="ep"[^>]*href="/play/(\d+)-(\d+)-(\d+)\.html"[^>]*>(.*?)</a>'
                eps = re.findall(ep_pattern, eps_html, re.DOTALL)
                if not eps:
                    continue
                ep_list = []
                for e_vid, e_sid, e_nid, e_name in eps:
                    e_name = self._clean(e_name) or "第{}集".format(e_nid)
                    ep_list.append("{}${}-{}-{}".format(e_name, e_vid, e_sid, e_nid))
                if ep_list:
                    play_from.append(route_name)
                    play_url.append("#".join(ep_list))

            return {"list": [{
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._join(pic) if pic else "",
                "vod_year": year,
                "vod_area": area,
                "vod_actor": actor,
                "vod_director": director,
                "vod_class": type_name,
                "vod_content": desc,
                "vod_remarks": remarks,
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            }]}
        except Exception:
            return {"list": []}

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
            if page < 1:
                page = 1
            keyword = urllib.parse.quote(key, safe="")
            url = "{}/index.php/ajax/suggest?mid=1&wd={}&limit=20&page={}".format(
                SITE_HOST, keyword, page)
            data = self._get_json(url)
            if not data or data.get("code") != 1:
                return {"list": []}
            items = []
            for item in data.get("list", []):
                items.append({
                    "vod_id": str(item.get("id", "")),
                    "vod_name": item.get("name", ""),
                    "vod_pic": item.get("pic", ""),
                    "vod_remarks": "",
                })
            return {"list": items}
        except Exception:
            return {"list": []}

    # ==================== 播放解析 ====================

    def playerContent(self, flag, id, vipFlags):
        url = ""
        try:
            play_id = str(id)
            url = "{}/play/{}.html".format(SITE_HOST, play_id)
            html = self._get(url)
            if not html:
                return {"parse": 1, "url": url, "header": {"User-Agent": self.header["User-Agent"]}}

            m = re.search(r'var\s+player_data\s*=\s*(\{[^<]+?\})\s*;?\s*</script>', html, re.DOTALL)
            if not m:
                m = re.search(r'player_data\s*=\s*(\{[^<]+\})', html)
            if not m:
                # Fallback: player_data 提取失败时, 直接从 HTML 扫描 m3u8/mp4 URL
                direct_match = re.search(r'(https?://[^\s"\'<>\\]+(?:\.m3u8|\.mp4))', html)
                if direct_match:
                    play_url = direct_match.group(1)
                    return {
                        "parse": 0,
                        "playUrl": "",
                        "url": play_url,
                        "header": {"User-Agent": self.header["User-Agent"], "Referer": SITE_HOST + "/"},
                        "format": "application/x-mpegURL" if ".m3u8" in play_url else "",
                    }
                return {"parse": 1, "url": url, "header": {"User-Agent": self.header["User-Agent"]}}

            try:
                pd = json.loads(m.group(1))
            except Exception:
                # JSON 解析失败, 从 player_data 原始字符串中提取 URL
                url_match = re.search(r'"url"\s*:\s*"(https?://[^"]+)"', m.group(1))
                if url_match:
                    play_url = url_match.group(1)
                    if ".m3u8" in play_url or ".mp4" in play_url:
                        return {
                            "parse": 0,
                            "playUrl": "",
                            "url": play_url,
                            "header": {"User-Agent": self.header["User-Agent"], "Referer": SITE_HOST + "/"},
                            "format": "application/x-mpegURL" if ".m3u8" in play_url else "",
                        }
                return {"parse": 1, "url": url, "header": {"User-Agent": self.header["User-Agent"]}}
            play_url = pd.get("url", "")
            play_from = pd.get("from", "")
            encrypt = int(pd.get("encrypt", 0))

            if encrypt == 1:
                play_url = urllib.parse.unquote(play_url)
            elif encrypt == 2:
                try:
                    play_url = urllib.parse.unquote(base64.b64decode(play_url).decode("utf-8"))
                except Exception:
                    pass

            if not play_url:
                return {"parse": 1, "url": url, "header": {"User-Agent": self.header["User-Agent"]}}

            # 只有 .m3u8 / .mp4 才是直链, 其他 (如 mgtv 页面链接) 需要解析器
            is_direct = ".m3u8" in play_url.lower() or ".mp4" in play_url.lower()

            if is_direct:
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": {"User-Agent": self.header["User-Agent"], "Referer": SITE_HOST + "/"},
                    "format": "application/x-mpegURL" if ".m3u8" in play_url else "",
                }
            else:
                if play_from == "qsvip":
                    parse_url = "https://v.attzy.com/ap/qs/?url=" + urllib.parse.quote(play_url, safe="")
                elif play_from == "JD4K":
                    parse_url = "https://v.attzy.com/ap/jd/?url=" + urllib.parse.quote(play_url, safe="")
                else:
                    parse_url = "https://v.attzy.com/ap/lb/?url=" + urllib.parse.quote(play_url, safe="")
                return {
                    "parse": 1,
                    "playUrl": "",
                    "url": parse_url,
                    "header": {"User-Agent": self.header["User-Agent"], "Referer": SITE_HOST + "/"},
                }
        except Exception:
            return {"parse": 1, "url": url, "header": {"User-Agent": self.header.get("User-Agent", "")}}

    def isVideoFormat(self, url):
        if not url:
            return False
        return any(e in url.lower() for e in (
            ".m3u8", ".mp4", ".flv", ".avi", ".mkv", ".mov", ".wmv", ".ts"))

    def localProxy(self, param):
        pass

    def destroy(self):
        pass


# ==================== 模块级函数 (FongMi/TV) ====================

_spider = None


def init(extend=""):
    global _spider
    if _spider is None:
        _spider = Spider()
    _spider.init(extend)


def getName():
    return "Gimy TV 劇迷"


def isVideoFormat(url):
    return _spider.isVideoFormat(url) if _spider else False


def manualVideoCheck():
    return None


def ignoreBgWorkflow():
    return False


def getDependence():
    return []


def homeContent(filter):
    if _spider is None:
        init("")
    return _spider.homeContent(filter) if _spider else {"class": [], "list": []}


def homeVideoContent():
    if _spider is None:
        init("")
    return _spider.homeVideoContent() if _spider else {"list": []}


def categoryContent(tid, pg, filter, extend):
    if _spider is None:
        init("")
    return _spider.categoryContent(tid, pg, filter, extend) if _spider else {
        "list": [], "page": "1", "pagecount": "1", "limit": "36", "total": "0"}


def detailContent(ids):
    if _spider is None:
        init("")
    return _spider.detailContent(ids) if _spider else {"list": []}


def searchContent(key, quick, pg="1"):
    if _spider is None:
        init("")
    return _spider.searchContent(key, quick, pg) if _spider else {"list": []}


def playerContent(flag, id, vipFlags):
    if _spider is None:
        init("")
    return _spider.playerContent(flag, id, vipFlags) if _spider else {
        "parse": 0, "url": "", "header": {}}


def localProxy(param):
    return _spider.localProxy(param) if _spider else None


def destroy():
    if _spider:
        _spider.destroy()


# ==================== CLI 测试 ====================

if __name__ == "__main__":
    import os
    os.environ.setdefault("PYTHONUTF8", "1")

    try:
        import warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        warnings.filterwarnings("ignore")
    except Exception:
        pass

    print("=" * 60)
    print("Gimy TV 劇迷 (gimyai.tw) - TVBox Spider CLI Test")
    print("=" * 60)

    # 尝试加载 cookie
    cookie_file = r"C:\tmp\gimyai_cookies.json"
    cookie_str = ""
    if os.path.exists(cookie_file):
        cookie_str = cookie_file
        print("[Cookie] 从文件加载: {}".format(cookie_file))
    else:
        print("[Cookie] 未找到 cookie 文件, 尝试无 cookie 访问")

    s = Spider()
    s.init(cookie_str)

    # 1. 首页
    print("\n[homeContent] 测试首页...")
    home = s.homeContent(1)
    print("  分类数: {}".format(len(home.get("class", []))))
    print("  推荐数: {}".format(len(home.get("list", []))))
    if home.get("list"):
        first = home["list"][0]
        print("  首条: {} ({}) {}".format(
            first.get("vod_name", ""), first.get("vod_id", ""),
            first.get("vod_remarks", "")))

    # 2. 分类浏览
    print("\n[categoryContent] 测试電視劇分类(第1页)...")
    cat = s.categoryContent("2", "1", 0, "")
    print("  列表数: {}".format(len(cat.get("list", []))))
    print("  页码: {}/{}".format(cat.get("page", ""), cat.get("pagecount", "")))
    if cat.get("list"):
        first = cat["list"][0]
        print("  首条: {} ({}) {}".format(
            first.get("vod_name", ""), first.get("vod_id", ""),
            first.get("vod_remarks", "")))

    # 3. 分类+筛选
    print("\n[categoryContent] 测试陸劇+大陸+2025...")
    cat2 = s.categoryContent("13", "1", 0, json.dumps({"area": "大陸", "year": "2025"}))
    print("  列表数: {}".format(len(cat2.get("list", []))))
    print("  页码: {}/{}".format(cat2.get("page", ""), cat2.get("pagecount", "")))

    # 4. 搜索
    print("\n[searchContent] 测试搜索 '花開'...")
    search = s.searchContent("花開", 0, "1")
    print("  结果数: {}".format(len(search.get("list", []))))
    if search.get("list"):
        first = search["list"][0]
        print("  首条: {} ({})".format(first.get("vod_name", ""), first.get("vod_id", "")))

    # 5. 详情 + 播放
    test_vid = ""
    if cat.get("list"):
        test_vid = cat["list"][0]["vod_id"]
    elif search.get("list"):
        test_vid = search["list"][0]["vod_id"]

    if test_vid:
        print("\n[detailContent] 测试详情 vid={}...".format(test_vid))
        detail = s.detailContent([test_vid])
        if detail.get("list"):
            vod = detail["list"][0]
            print("  标题: {}".format(vod.get("vod_name", "")))
            print("  封面: {}".format(vod.get("vod_pic", "")[:60]))
            print("  简介: {}".format(vod.get("vod_content", "")[:80]))
            print("  线路: {}".format(vod.get("vod_play_from", "").replace("$$$", " | ")))

            play_url = vod.get("vod_play_url", "")
            if play_url:
                lines = play_url.split("$$$")
                line_names = vod.get("vod_play_from", "").split("$$$")
                for i, line_url in enumerate(lines[:3]):
                    line_name = line_names[i] if i < len(line_names) else "线路{}".format(i)
                    first_ep = line_url.split("#")[0] if "#" in line_url else line_url
                    ep_name = first_ep.split("$")[0] if "$" in first_ep else ""
                    play_id = first_ep.split("$")[1] if "$" in first_ep else ""

                    print("\n[playerContent] 测试 {} - {}...".format(line_name, ep_name))
                    if play_id:
                        play = s.playerContent(line_name, play_id, [])
                        print("  parse: {}".format(play.get("parse", "")))
                        print("  url: {}...".format(str(play.get("url", ""))[:100]))
        else:
            print("  无数据")

    print("\n" + "=" * 60)
    print("CLI 测试完成")
    print("=" * 60)
