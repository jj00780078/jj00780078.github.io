# -*- coding: utf-8 -*-
"""
剧圈圈 TVBox/猫影视爬虫插件 — https://www.jqqzx.one/
苹果CMS v10 + mxtheme 模板

路由:
  首页         /
  分类         /type/{dianying,juji,dongman,zongyi,duanju}.html
  分类筛选库   /vodshow/id/{类型名}.html
  筛选         /vodshow/id/{类型名}/class/{class}/area/{area}/year/{year}/page/{page}.html
  详情         /vod/{id}.html
  播放         /play/{id}-{sid}-{nid}.html
  搜索API      /index.php/ajax/suggest?mid=1&wd={kw}&page={page}

播放解析(v2 修复):
  1. GET /play/{id}-{sid}-{nid}.html 提取 player_aaaa.url (站点加密串)
  2. POST /jx/api.php (vid=加密串) 拿到 sign 加密的 url
  3. 本地复刻站点 sign() 解密 (md5('test') 异或 + 字母替换), 直接返回真实 m3u8
  4. 解密失败时降级为 parse=1 嗅探模式
"""

import re
import json
import time
import base64
import hashlib
import warnings
import threading
from urllib.parse import urljoin, quote

try:
    warnings.filterwarnings("ignore")
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    from requests.adapters import HTTPAdapter

    class Spider:
        def __init__(self):
            self._session = _rq.Session()
            adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)

        def fetch(self, url, headers=None, timeout=15, **kw):
            headers = headers or {}
            headers.setdefault("User-Agent", UA)
            return self._session.get(url, headers=headers, timeout=timeout, verify=False, **kw)

        def destroy(self):
            try:
                self._session.close()
            except Exception:
                pass


HOST = "https://www.jqqzx.one"
UA = ("Mozilla/5.0 (Linux; Android 12; M2007J22C) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

# 主分类
CLASSES = [
    {"type_name": "电影", "type_id": "dianying"},
    {"type_name": "剧集", "type_id": "juji"},
    {"type_name": "动漫", "type_id": "dongman"},
    {"type_name": "综艺", "type_id": "zongyi"},
    {"type_name": "短剧", "type_id": "duanju"},
]

# 二级分类筛选条件
FILTERS = {
    "dianying": [
        {"key": "class", "name": "类型", "value": [
            {"n": "全部", "v": ""},
            {"n": "动作片", "v": "动作片"},
            {"n": "喜剧片", "v": "喜剧片"},
            {"n": "爱情片", "v": "爱情片"},
            {"n": "科幻片", "v": "科幻片"},
            {"n": "恐怖片", "v": "恐怖片"},
            {"n": "剧情片", "v": "剧情片"},
            {"n": "战争片", "v": "战争片"},
            {"n": "动画片", "v": "动画片"},
        ]},
        {"key": "area", "name": "地区", "value": [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"},
            {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"},
            {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "泰国", "v": "泰国"},
            {"n": "英国", "v": "英国"},
            {"n": "法国", "v": "法国"},
            {"n": "德国", "v": "德国"},
            {"n": "意大利", "v": "意大利"},
            {"n": "西班牙", "v": "西班牙"},
            {"n": "印度", "v": "印度"},
            {"n": "加拿大", "v": "加拿大"},
            {"n": "其他", "v": "其他"},
        ]},
        {"key": "year", "name": "年份", "value": [
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
            {"n": "2014", "v": "2014"},
            {"n": "2013", "v": "2013"},
            {"n": "2012", "v": "2012"},
            {"n": "2011", "v": "2011"},
            {"n": "2010", "v": "2010"},
        ]},
    ],
    "juji": [
        {"key": "class", "name": "类型", "value": [
            {"n": "全部", "v": ""},
            {"n": "国产剧", "v": "国产剧"},
            {"n": "港台剧", "v": "港台剧"},
            {"n": "日韩剧", "v": "日韩剧"},
            {"n": "欧美剧", "v": "欧美剧"},
            {"n": "泰国剧", "v": "泰国剧"},
        ]},
        {"key": "area", "name": "地区", "value": [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"},
            {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "美国", "v": "美国"},
            {"n": "泰国", "v": "泰国"},
            {"n": "英国", "v": "英国"},
            {"n": "其他", "v": "其他"},
        ]},
        {"key": "year", "name": "年份", "value": [
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
        ]},
    ],
    "dongman": [
        {"key": "area", "name": "地区", "value": [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"},
            {"n": "日本", "v": "日本"},
            {"n": "韩国", "v": "韩国"},
            {"n": "美国", "v": "美国"},
            {"n": "其他", "v": "其他"},
        ]},
        {"key": "year", "name": "年份", "value": [
            {"n": "全部", "v": ""},
            {"n": "2026", "v": "2026"},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
        ]},
    ],
    "zongyi": [
        {"key": "area", "name": "地区", "value": [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"},
            {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "美国", "v": "美国"},
            {"n": "其他", "v": "其他"},
        ]},
        {"key": "lang", "name": "语言", "value": [
            {"n": "全部", "v": ""},
            {"n": "国语", "v": "国语"},
            {"n": "粤语", "v": "粤语"},
            {"n": "英语", "v": "英语"},
            {"n": "韩语", "v": "韩语"},
            {"n": "日语", "v": "日语"},
            {"n": "其他", "v": "其他"},
        ]},
        {"key": "year", "name": "年份", "value": [
            {"n": "全部", "v": ""},
            {"n": "2026", "v": "2026"},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
        ]},
    ],
    "duanju": [
        {"key": "class", "name": "剧情", "value": [
            {"n": "全部", "v": ""},
        ]},
    ],
}

LIST_PAGE_SIZE = 40
HOME_PAGE_SIZE = 24
LIST_CACHE_TTL = 60
DETAIL_CACHE_TTL = 300
HOME_CACHE_TTL = 30
SEARCH_CACHE_TTL = 30
CIRCUIT_FAILS = 3
CIRCUIT_COOLDOWN = 30


def _urlencode(s):
    return quote(s or "", safe="")


# ---------------------------------------------------------------------------
# 播放地址解密（复刻站点 /jx/player.php 的 customStrDecode + sign 逻辑）
# 流程: play 页 player_aaaa.url(加密) -> POST /jx/api.php -> sign 解密 -> 真实 m3u8
# ---------------------------------------------------------------------------

def _md5_hex(s):
    if isinstance(s, str):
        try:
            s = s.encode("utf-8")
        except Exception:
            pass
    return hashlib.md5(s).hexdigest()


def _b64decode_str(s):
    """base64 解码为文本, 失败返回空串"""
    try:
        raw = base64.b64decode(s)
        if isinstance(raw, str):
            return raw
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _jqq_custom_str_decode(s):
    """站点 customStrDecode: b64解码 -> 与 md5('test') 逐字符异或 -> b64解码"""
    key = _md5_hex("test")
    try:
        raw = base64.b64decode(s)
    except Exception:
        return ""
    code = []
    for i in range(len(raw)):
        c = raw[i]
        if isinstance(c, str):
            c = ord(c)
        code.append(chr(c ^ ord(key[i % len(key)])))
    return _b64decode_str("".join(code))


def _jqq_de_string(a, b, c):
    """站点 deString: 密文中在 b 数组里的字母替换为 b[a.index(字母)]"""
    out = []
    b_set = set(b)
    a_len = len(a)
    b_len = len(b)
    for ch in c:
        is_alpha = ("a" <= ch <= "z") or ("A" <= ch <= "Z")
        if is_alpha and ch in b_set:
            try:
                idx = a.index(ch)
            except ValueError:
                out.append(ch)
                continue
            out.append(b[idx] if 0 <= idx < b_len else ch)
        else:
            out.append(ch)
    return "".join(out)


def _jqq_sign_decrypt(s):
    """站点 sign(): 解密 /jx/api.php 返回的加密 url"""
    try:
        m = _jqq_custom_str_decode(s)
        if not m:
            return ""
        parts = m.split("/")
        if len(parts) < 3:
            return ""
        a = json.loads(_b64decode_str(parts[1]))
        b = json.loads(_b64decode_str(parts[0]))
        body = "/".join(parts[2:])
        c = _b64decode_str(body)
        if not a or not b or not c:
            return ""
        return _jqq_de_string(a, b, c)
    except Exception as e:
        print("[剧圈圈] sign解密异常: " + str(e))
        return ""


def _strip(txt):
    return re.sub(r"\s+", " ", txt or "").strip()


def _unescape(txt):
    if not txt:
        return ""
    try:
        import html as _html
        return _html.unescape(txt)
    except Exception:
        return re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), txt)


def _abs_url(url, base):
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return base + url
    return urljoin(base + "/", url)


class Spider(Spider):
    _RE_VOD_ITEM = re.compile(
        r'<a[^>]+href="(/vod/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>'
        r'[\s\S]*?<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]+)</div>'
        r'[\s\S]*?data-original="([^"]+)"'
    )
    _RE_VOD_ITEM_LOOSE = re.compile(
        r'<a[^>]+href="(/vod/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>'
        r'[\s\S]*?data-original="([^"]+)"'
    )
    _RE_VOD_TITLE_ONLY = re.compile(
        r'<a[^>]+href="(/vod/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*class="[^"]*module-poster-item[^"]*"'
    )
    _RE_PAGE_NUM = re.compile(r'/vodshow/id/[^/]+/page/(\d+)\.html')
    _RE_PAGE_NUM2 = re.compile(r'page/(\d+)\.html')
    _RE_DETAIL_TITLE = re.compile(r'<h1[^>]*>([^<]+)</h1>')
    _RE_DETAIL_PIC = re.compile(r'<div[^>]*class="[^"]*module-item-pic[^"]*"[^>]*>[\s\S]*?<img[^>]+data-original="([^"]+)"')
    _RE_DETAIL_PIC2 = re.compile(r'<img[^>]+data-original="([^"]+)"[^>]*alt="[^"]*"[^>]*class="[^"]*pic[^"]*"')
    _RE_INFO_ITEM = re.compile(
        r'<div[^>]*class="[^"]*module-info-item[^"]*"[^>]*>'
        r'[\s\S]*?<span[^>]*class="[^"]*module-info-item-title[^"]*"[^>]*>([^<]+)</span>'
        r'[\s\S]*?<div[^>]*class="[^"]*module-info-item-content[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>'
    )
    _RE_VOD_CONTENT = re.compile(r'<div[^>]*class="[^"]*module-info-introduction[^"]*"[^>]*>([\s\S]*?)</div>')
    _RE_PLAYLIST_BLOCK = re.compile(r'<div[^>]*class="[^"]*module-play-list[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>')
    _RE_PLAY_EP = re.compile(r'<a[^>]+href="(/play/(\d+-\d+-\d+)\.html)"[^>]*>([\s\S]*?)</a>')
    _RE_PLAYER_JSON = re.compile(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*(?:</script>|;|&)')
    _RE_HOME_MODULE = re.compile(r'<div[^>]*class="[^"]*module[^"]*"[^>]*>[\s\S]*?</div>\s*</div>\s*</div>')

    def getName(self):
        return "剧圈圈"

    def init(self, extend=""):
        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        try:
            import requests
            from requests.adapters import HTTPAdapter
            self._session = requests.Session()
            adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
            self._session.trust_env = False
        except Exception as e:
            print("[剧圈圈] requests 不可用, 回退到框架 fetch: " + str(e))
            self._session = None

        self._list_cache = {}
        self._detail_cache = {}
        self._home_cache = None
        self._search_cache = {}
        self._cache_lock = threading.Lock()
        self._cb_fails = 0
        self._cb_open_until = 0
        self._cb_lock = threading.Lock()

    def isVideoFormat(self, url):
        u = (url or "").lower().rstrip("?#")
        return any(u.endswith(ext) for ext in (".m3u8", ".mp4", ".flv", ".ts"))

    def destroy(self):
        sess = getattr(self, "_session", None)
        if sess is not None:
            try:
                sess.close()
            except Exception:
                pass

    def _circuit_allow(self):
        with self._cb_lock:
            if self._cb_open_until and time.time() < self._cb_open_until:
                return False
            return True

    def _circuit_record(self, ok):
        with self._cb_lock:
            if ok:
                self._cb_fails = 0
            else:
                self._cb_fails += 1
                if self._cb_fails >= CIRCUIT_FAILS:
                    self._cb_open_until = time.time() + CIRCUIT_COOLDOWN
                    print("[剧圈圈] 熔断 " + str(CIRCUIT_COOLDOWN) + "s")

    def _http_get(self, url, timeout=10):
        if not self._circuit_allow():
            return ""
        ok = False
        sess = getattr(self, "_session", None)
        if sess is not None and hasattr(sess, "get"):
            try:
                rsp = sess.get(url, headers=self.header, timeout=timeout, verify=False)
                sc = getattr(rsp, "status_code", 0)
                txt = getattr(rsp, "text", None) or ""
                if rsp is not None and sc == 200 and txt:
                    ok = True
                    return rsp.text
            except Exception as e:
                print("[剧圈圈] session 失败: " + url + " (" + str(e) + ")")
        try:
            rsp = self.fetch(url, headers=self.header, timeout=timeout)
            sc = getattr(rsp, "status_code", 0)
            txt = getattr(rsp, "text", None) or ""
            if rsp is not None and sc == 200 and txt:
                ok = True
                return rsp.text
        except Exception as e:
            print("[剧圈圈] fetch 失败: " + url + " (" + str(e) + ")")
        finally:
            self._circuit_record(ok)
        return ""

    def _http_get_json(self, url, timeout=10):
        html = self._http_get(url, timeout=timeout)
        if not html:
            return None
        try:
            return json.loads(html)
        except Exception as e:
            print("[剧圈圈] JSON解析失败: " + url + " (" + str(e) + ")")
            return None

    def _http_post(self, url, data, timeout=10):
        """POST 请求: requests session -> urllib 标准库 -> 框架 fetch, 全失败返回 None"""
        # 1) requests session
        sess = getattr(self, "_session", None)
        if sess is not None and hasattr(sess, "post"):
            try:
                rsp = sess.post(url, data=data, headers=self.header, timeout=timeout, verify=False)
                if getattr(rsp, "status_code", 0) == 200:
                    return rsp.text
                print("[剧圈圈] POST 状态异常: " + str(getattr(rsp, "status_code", 0)))
            except Exception as e:
                print("[剧圈圈] POST session 失败: " + url + " (" + str(e) + ")")
        # 2) urllib 标准库兜底 (不依赖第三方库)
        try:
            try:
                from urllib.request import Request as _Req, urlopen as _Uo
                from urllib.parse import urlencode as _Ue
            except ImportError:
                from urllib2 import Request as _Req, urlopen as _Uo
                from urllib import urlencode as _Ue
            body = _Ue(data)
            try:
                body = body.encode("utf-8")
            except Exception:
                pass
            req = _Req(url, data=body, headers=self.header)
            try:
                import ssl as _ssl
                ctx = _ssl._create_unverified_context()
                rsp = _Uo(req, timeout=timeout, context=ctx)
            except Exception:
                rsp = _Uo(req, timeout=timeout)
            raw = rsp.read()
            if not isinstance(raw, str):
                raw = raw.decode("utf-8", errors="replace")
            if raw:
                return raw
            print("[剧圈圈] POST urllib 返回空")
        except Exception as e:
            print("[剧圈圈] POST urllib 失败: " + url + " (" + str(e) + ")")
        # 3) 框架 fetch 兜底
        try:
            rsp = self.fetch(url, headers=self.header, timeout=timeout, data=data)
            if getattr(rsp, "status_code", 0) == 200:
                return rsp.text
        except Exception as e:
            print("[剧圈圈] POST fetch 失败: " + url + " (" + str(e) + ")")
        return None

    def _abs(self, url):
        return _abs_url(url, HOST)

    def _parse_vod(self, html):
        """解析视频列表，兼容多种HTML结构"""
        items = []
        seen = set()

        def _add(vid, name, pic, remark=""):
            if not vid or vid in seen:
                return
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": _strip(_unescape(name)),
                "vod_pic": self._abs(_unescape(pic)),
                "vod_remarks": _strip(_unescape(remark)),
            })

        # 严格匹配: 同时有备注和图片
        for m in self._RE_VOD_ITEM.finditer(html):
            _add(m.group(1), m.group(3), m.group(5), m.group(4))

        # 宽松匹配: 有图片但备注可能在其他位置
        for m in self._RE_VOD_ITEM_LOOSE.finditer(html):
            remark = ""
            nearby = html[m.end():m.end()+300]
            note_m = re.search(r'<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]+)</div>', nearby)
            if note_m:
                remark = note_m.group(1)
            _add(m.group(1), m.group(3), m.group(4), remark)

        # 兜底: 只有标题
        if not items:
            for m in self._RE_VOD_TITLE_ONLY.finditer(html):
                _add(m.group(1), m.group(3), "", "")

        return items

    def _pagecount(self, html, cur_page):
        mx = cur_page
        for pm in self._RE_PAGE_NUM.finditer(html):
            n = int(pm.group(1))
            if n > mx:
                mx = n
        for pm in self._RE_PAGE_NUM2.finditer(html):
            n = int(pm.group(1))
            if n > mx:
                mx = n
        m = re.search(r'class="[^"]*page[^"]*"[^>]*>.*?(\d+)</a>\s*<span[^>]*>尾页', html)
        if m:
            mx = max(mx, int(m.group(1)))
        return mx

    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        now = time.time()
        with self._cache_lock:
            if self._home_cache:
                ts, payload = self._home_cache
                if now - ts < HOME_CACHE_TTL:
                    return payload

        html = self._http_get(HOST + "/", timeout=6)
        if not html:
            return {"list": []}

        items = self._parse_vod(html)
        payload = {"list": items[:HOME_PAGE_SIZE]}

        with self._cache_lock:
            self._home_cache = (now, payload)
        return payload

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
            ext = extend or {}
            cls = str(ext.get("class", "") or "")
            area = str(ext.get("area", "") or "")
            year = str(ext.get("year", "") or "")
            lang = str(ext.get("lang", "") or "")
            use_tid = str(tid)

            cache_key = (use_tid, cls, area, year, lang, page)
            now = time.time()
            with self._cache_lock:
                hit = self._list_cache.get(cache_key)
                if hit and now - hit[0] < LIST_CACHE_TTL:
                    return hit[1]

            url = HOST + "/vodshow/id/" + use_tid
            if cls:
                url += "/class/" + _urlencode(cls)
            if area:
                url += "/area/" + _urlencode(area)
            if year:
                url += "/year/" + _urlencode(year)
            if lang:
                url += "/lang/" + _urlencode(lang)
            if page > 1:
                url += "/page/" + str(page) + ".html"
            else:
                url += ".html"

            html = self._http_get(url, timeout=7)
            if not html:
                print("[剧圈圈] categoryContent empty: " + url)
                return {"list": [], "page": page, "pagecount": 1, "limit": LIST_PAGE_SIZE, "total": 0}

            videos = self._parse_vod(html)
            pagecount = self._pagecount(html, page)
            if not videos:
                pagecount = max(1, page)

            payload = {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": len(videos) or LIST_PAGE_SIZE,
                "total": pagecount * LIST_PAGE_SIZE,
            }
            with self._cache_lock:
                self._list_cache[cache_key] = (now, payload)
            return payload
        except Exception as e:
            print("[剧圈圈] categoryContent 异常: " + str(e))
            return {"list": [], "page": 1, "pagecount": 1, "limit": LIST_PAGE_SIZE, "total": 0}

    def detailContent(self, ids):
        try:
            if isinstance(ids, (list, tuple)):
                ids = ids[0]
            vod_id = str(ids)
            now = time.time()
            with self._cache_lock:
                hit = self._detail_cache.get(vod_id)
                if hit and now - hit[0] < DETAIL_CACHE_TTL:
                    return hit[1]

            if vod_id.startswith("/"):
                url = HOST + vod_id
            else:
                url = HOST + "/vod/" + vod_id + ".html"

            html = self._http_get(url, timeout=8)
            if not html:
                return {"list": []}

            vod = {
                "vod_id": vod_id,
                "vod_name": "",
                "vod_pic": "",
                "vod_year": "",
                "vod_area": "",
                "vod_lang": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_class": "",
                "vod_content": "",
                "vod_play_from": "",
                "vod_play_url": "",
            }

            m = self._RE_DETAIL_TITLE.search(html)
            if m:
                vod["vod_name"] = _strip(_unescape(m.group(1)))

            m = self._RE_DETAIL_PIC.search(html)
            if not m:
                m = self._RE_DETAIL_PIC2.search(html)
            if m:
                pic = m.group(1)
                if pic and not pic.endswith("load.gif") and not pic.endswith("loading.gif"):
                    vod["vod_pic"] = self._abs(_unescape(pic).strip())

            for label, content in self._RE_INFO_ITEM.findall(html):
                label = _strip(label)
                text = _strip(re.sub(r"<[^>]+>", " ", content))
                if "主演" in label:
                    vod["vod_actor"] = text
                elif "导演" in label:
                    vod["vod_director"] = text
                elif "类型" in label:
                    vod["vod_class"] = text
                elif "地区" in label:
                    vod["vod_area"] = text
                elif "年份" in label:
                    vod["vod_year"] = text
                elif "语言" in label:
                    vod["vod_lang"] = text
                elif "更新" in label or "状态" in label:
                    vod["vod_remarks"] = text

            m = self._RE_VOD_CONTENT.search(html)
            if m:
                txt = re.sub(r"<[^>]*>", "", m.group(1))
                vod["vod_content"] = _strip(txt)[:500]

            play_from, play_url = self._collect_playlist(html)
            if play_from:
                vod["vod_play_from"] = "$$$".join(play_from)
                vod["vod_play_url"] = "$$$".join(play_url)

            payload = {"list": [vod]}
            with self._cache_lock:
                self._detail_cache[vod_id] = (now, payload)
            return payload
        except Exception as e:
            print("[剧圈圈] detailContent 异常: " + str(e))
            return {"list": []}

    def _collect_playlist(self, html):
        play_from, play_url = [], []
        blocks = self._RE_PLAYLIST_BLOCK.findall(html)
        if not blocks:
            return play_from, play_url

        for idx, chunk in enumerate(blocks, 1):
            eps_raw = []
            seen_paths = set()
            for em in self._RE_PLAY_EP.finditer(chunk):
                path = em.group(1)
                ep_name = _strip(_unescape(re.sub(r"<[^>]*>", "", em.group(3)))) or "正片"
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                nm = re.search(r"-(\d+)\.html$", path)
                nid = int(nm.group(1)) if nm else 0
                eps_raw.append((nid, ep_name, path))
            eps_raw.sort(key=lambda x: x[0])
            eps = [name + "$" + path for _, name, path in eps_raw]
            if eps:
                src_name = "线路" + str(idx) if len(blocks) > 1 else "播放"
                play_from.append(src_name)
                play_url.append("#".join(eps))
        return play_from, play_url

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
            cache_key = (key, page)
            now = time.time()
            with self._cache_lock:
                hit = self._search_cache.get(cache_key)
                if hit and now - hit[0] < SEARCH_CACHE_TTL:
                    return hit[1]

            kw = _urlencode(key)
            url = HOST + "/index.php/ajax/suggest?mid=1&wd=" + kw + "&page=" + str(page)
            data = self._http_get_json(url, timeout=8)

            if not data or data.get("code") != 1:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            videos = []
            for item in data.get("list", []):
                vid = str(item.get("id", ""))
                if not vid:
                    continue
                videos.append({
                    "vod_id": vid,
                    "vod_name": _strip(item.get("name", "")),
                    "vod_pic": self._abs(item.get("pic", "")),
                    "vod_remarks": "",
                })

            total = data.get("total", 0)
            limit = data.get("limit", 20)
            pagecount = data.get("pagecount", 1)

            payload = {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": limit,
                "total": total,
            }
            with self._cache_lock:
                self._search_cache[cache_key] = (now, payload)
            return payload
        except Exception as e:
            print("[剧圈圈] searchContent 异常: " + str(e))
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def _extract_player_aaaa(self, html):
        """提取 player_aaaa JSON, 正则失败时用大括号计数兜底"""
        if not html:
            return None
        m = self._RE_PLAYER_JSON.search(html)
        if m:
            try:
                json_str = m.group(1)
                brace_count = 0
                end_idx = 0
                for i, c in enumerate(json_str):
                    if c == '{':
                        brace_count += 1
                    elif c == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                return json.loads(json_str[:end_idx])
            except Exception as e:
                print("[剧圈圈] player_aaaa 正则解析异常: " + str(e))
        # 兜底: 定位 player_aaaa= 后逐字符数大括号
        try:
            idx = html.find("player_aaaa")
            if idx < 0:
                print("[剧圈圈] 页面无 player_aaaa (len=" + str(len(html)) + " head=" + _strip(re.sub(r"<[^>]*>", " ", html[:150])) + ")")
                return None
            brace_start = html.find("{", idx)
            if brace_start < 0:
                return None
            depth = 0
            for i in range(brace_start, len(html)):
                c = html[i]
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        return json.loads(html[brace_start:i + 1])
        except Exception as e:
            print("[剧圈圈] player_aaaa 兜底解析异常: " + str(e))
        return None

    def playerContent(self, flag, id, vipFlags):
        play_path = str(id or "")
        if not play_path:
            return {"parse": 0, "url": ""}

        if self.isVideoFormat(play_path):
            return {"parse": 0, "url": play_path, "header": {"User-Agent": UA, "Referer": HOST + "/"}}

        if "/play/" in play_path:
            if play_path.startswith("http"):
                play_url = play_path
            else:
                play_url = HOST + play_path

            html = self._http_get(play_url, timeout=10)
            if not html:
                print("[剧圈圈] play页请求为空: " + play_url)
            player = self._extract_player_aaaa(html)

            # ---- 新版解析: POST /jx/api.php 拿加密 url, sign 解密出真实 m3u8 ----
            if player:
                url_enc = player.get("url", "")
                if url_enc:
                    api_rsp = None
                    try:
                        api_rsp = self._http_post(
                            HOST + "/jx/api.php",
                            data={"vid": url_enc},
                            timeout=10,
                        )
                    except Exception as e:
                        print("[剧圈圈] api.php 请求异常: " + str(e))
                    if api_rsp:
                        try:
                            data = json.loads(api_rsp)
                        except Exception as e:
                            print("[剧圈圈] api.php 响应非JSON: " + str(api_rsp[:120]))
                            data = None
                        if data and data.get("code") == 200:
                            enc_url = (data.get("data") or {}).get("url", "")
                            real_url = _jqq_sign_decrypt(enc_url) if enc_url else ""
                            if real_url and real_url.startswith("http"):
                                return {
                                    "parse": 0,
                                    "url": real_url,
                                    "header": {
                                        "User-Agent": UA,
                                        "Referer": HOST + "/",
                                    },
                                }
                            print("[剧圈圈] sign解密结果无效: " + str(real_url[:80]))
                        elif data is not None:
                            print("[剧圈圈] api.php code=" + str(data.get("code")) + " rsp=" + str(api_rsp[:120]))
                    else:
                        print("[剧圈圈] api.php 无响应")
                else:
                    print("[剧圈圈] player_aaaa.url 为空, keys=" + str(list(player.keys())[:8]))

            # ---- 降级: 走原嗅探方式 ----
            print("[剧圈圈] 解析失败, 降级嗅探: " + play_url)
            return {
                "parse": 1,
                "url": play_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": HOST + "/",
                }
            }

        return {"parse": 0, "url": play_path, "header": {"User-Agent": UA, "Referer": HOST + "/"}}

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]
