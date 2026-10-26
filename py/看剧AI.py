#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看剧AI (https://ai.kanju25.com) 蜘蛛源 —— 接口版，无需浏览器。

站点是 Vite + React 的纯前后端分离站点（看剧AI / KANJU.AI），HTML 里只有挂载点，
所有数据来自同源 JSON 接口，因此本源完全不解析页面。

一、接口签名（这是唯一的门槛）
    每个 /v1/* 请求都要带三个头，缺一个就是 401 invalid_request_signature：

        x-ai-movie-timestamp : Date.now() 毫秒，字符串
        x-ai-movie-nonce     : 16 字节随机数 hex
        x-ai-movie-signature : HMAC-SHA256(secret, 待签串) hex

    待签串四行，用 \n 连接：

        <METHOD 大写>
        <pathname><search>
        <timestamp>
        <nonce>

    例：GET /v1/feed/home 签的是 "GET\n/v1/feed/home\n1792662736553\nd5a3..."。
    secret 取自主 JS 常量（movie-card-runtime-*.js 里的 ci）。
    另有四个可选头，带上更贴近真实：client-name / client-version / build-version /
    protocol-version，缺了也能通过。

二、路由 → 接口对应
    首页推荐   GET /v1/feed/home                         8 个分区
    分类筛选   GET /v1/browse/catalog                    kind/area/genre/year/q/page
        kind 取英文：movie series short_drama anime variety documentary sports adult
        area / genre 用中文原值（中国大陆、古装、韩国…），实测与 kind 组合生效
        搜索 = q + intent=catalog_search，没有独立搜索端点
        intent 枚举只有 catalog_search / similar_search / latest_catalog / uncertain
        limit 不要超过 50，实测 60 会被打回默认 20，本源固定 24
    详情       GET /v1/catalog/{variant_id}/detail
    剧集       GET /v1/catalog/{variant_id}/episodes?limit=200&offset=0
               limit 上限 200，每集的关键字段是 token

三、播放链路（两步）
    1) GET /v1/playback/resolve/{episode_token}?view=compact
       → line_options[]，每条线路含 url / url_kind / selected / default_priority
       url 两种形态：
         http(s)://...  + url_kind=m3u8|mp4        → 可直接播的明文 m3u8
         resolve://<ticket> + url_kind=resolve_ticket → 必须再解析一次
    2) POST /v1/playback/resolve-line?view=compact
       body = {"ticket": "<第一步 url 去掉 resolve:// 前缀>"}
       → line.url 才是真实地址

    坑：排在最前面的"官方"线路解析出来不一定是视频。实测会命中
    Content-Type: image/jpeg 的封面图（token_scenario=series_intro_zero），
    直接喂播放器就是加载失败。所以本源不迷信顺序，而是：
       * 挑出全部 http 直链并发预检（只读前若干字节，必须是 #EXTM3U 或视频类型）
       * 预检全挂才回头逐个换 resolve 线路
       * 结果按 token 缓存 30 分钟，来回切集不重复探测

四、关于 mpv / 嗅探壳
    本源最终一律返回 parse=0 的明文绝对 m3u8，不依赖任何 JS，
    WebView / 浏览器内核不是必需项。第三方 CDN 分片多为绝对地址，
    偶发的相对 2000k/hls/mixed.m3u8、enc.key 也在 mpv 标准处理范围内。
"""

import re
import os
import ssl
import json
import time
import gzip
import hmac
import zlib
import random
import hashlib
import threading
import urllib.request
import urllib.error
import urllib.parse
from http import cookiejar

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key):
            return None

        def setCache(self, key, value):
            return "fail"

        def delCache(self, key):
            return "fail"


# ---------------------------------------------------------------- 配置

API_HOSTS = ["https://ai.kanju25.com", "https://kanju.ai", "https://kanju25.com"]

SIGN_SECRET = "557d0e4ae929f438da6bd84412374e6086b8af09b3fed54bf22601d5bf8c54a0"

CLIENT_NAME = "dianyingtiantang-frontend"
CLIENT_VERSION = "1.0.0"
BUILD_VERSION = "dianyingtiantang-v2026.10.21.6-redis-lifecycle-b85b39a9cc04-web"
PROTOCOL_VERSION = "2026-07-05.library-v2.playback-v1"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

PAGE_SIZE = 24
EPISODE_LIMIT = 200

API_TIMEOUT = 18
PROBE_TIMEOUT = 9
PROBE_WORKERS = 8
PROBE_LINES = 10
RESOLVE_LINES = 4

PLAY_TTL = 1800
PLAY_MAX = 160

AREA_LIST = ["中国大陆", "中国香港", "中国台湾", "美国", "韩国", "日本",
             "泰国", "英国", "法国", "德国", "印度", "西班牙", "意大利",
             "加拿大", "澳大利亚", "俄罗斯", "新加坡"]

GENRE_LIST = ["古装", "爱情", "喜剧", "悬疑", "恐怖", "动作", "科幻", "犯罪",
              "剧情", "家庭", "武侠", "历史", "战争", "冒险", "奇幻", "动画",
              "青春", "校园", "职场", "医疗", "警匪", "传记", "歌舞", "纪录片"]

YEAR_LIST = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"]

KIND_ZONES = [
    ("latest", "", "最新"),
    ("series", "series", "电视剧"),
    ("movie", "movie", "电影"),
    ("short_drama", "short_drama", "短剧"),
    ("anime", "anime", "动漫"),
    ("variety", "variety", "综艺"),
    ("documentary", "documentary", "纪录片"),
    ("sports", "sports", "体育"),
]

KIND_NAMES = {
    "movie": "电影", "series": "剧集", "short_drama": "短剧", "anime": "动漫",
    "variety": "综艺", "documentary": "纪录片", "sports": "体育", "adult": "限制级",
}


# ---------------------------------------------------------------- 工具

def _now_ms():
    return int(time.time() * 1000)


def _nonce(size=16):
    try:
        return os.urandom(size).hex()
    except Exception:
        stub = "%s%s%s" % (time.time(), random.random(), id(object()))
        return hashlib.sha256(stub.encode()).hexdigest()[:size * 2]


def _hmac_hex(secret, msg):
    try:
        return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    except Exception:
        return ""


def _sign_headers(method, path):
    ts = str(_now_ms())
    nonce = _nonce()
    msg = "%s\n%s\n%s\n%s" % (str(method or "GET").upper(), path, ts, nonce)
    return {
        "x-ai-movie-timestamp": ts,
        "x-ai-movie-nonce": nonce,
        "x-ai-movie-signature": _hmac_hex(SIGN_SECRET, msg),
    }


def _clean(text):
    if text is None:
        return ""
    s = str(text)
    for ch in ("\r", "\n", "\t"):
        s = s.replace(ch, " ")
    return re.sub(r"\s{2,}", " ", s).strip()


def _take(items, limit=8, sep="、"):
    out = []
    for it in items or []:
        if isinstance(it, str) and re.search(r"[、,，/　]| {2,}| ", it):
            parts = re.split(r"[、,，/　]|\s{1,}", it)
        else:
            parts = [it]
        for p in parts:
            s = _clean(p)
            if s and s not in out:
                out.append(s)
            if len(out) >= limit:
                return sep.join(out)
    return sep.join(out)


def _pic_of(card):
    for k in ("poster_url", "carousel_url", "backdrop_url"):
        v = card.get(k)
        if isinstance(v, str) and v.strip().startswith(("http://", "https://")):
            return v.strip()
    return ""


def _remarks_of(card):
    for k in ("remarks", "episode_progress_text"):
        s = _clean(card.get(k))
        if s:
            return s
    avail = card.get("availability") or {}
    s = _clean(avail.get("label"))
    if s:
        return s
    kind = card.get("content_kind")
    if kind:
        return KIND_NAMES.get(str(kind), str(kind))
    return ""


def _variant_of(card):
    for k in ("selected_variant_id", "variant_id", "default_variant_id", "id"):
        v = card.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _fixed_int(value, default=1):
    try:
        n = int(re.sub(r"\D", "", str(value or "")) or default)
    except Exception:
        n = default
    return n if n > 0 else default


def _of_extend(extend):
    if isinstance(extend, dict):
        return extend
    if isinstance(extend, str) and extend.strip().startswith("{"):
        try:
            got = json.loads(extend)
        except Exception:
            got = {}
        return got if isinstance(got, dict) else {}
    return {}


# ---------------------------------------------------------------- HTTP

def _mk_ssl():
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        return None


def _decompress(raw, enc):
    enc = (enc or "").lower()
    if not raw:
        return raw
    try:
        if "br" in enc:
            try:
                import brotli
                return brotli.decompress(raw)
            except Exception:
                return raw
        if "gzip" in enc:
            return gzip.decompress(raw)
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except Exception:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
    except Exception:
        return raw
    return raw


def _decode(raw):
    if raw is None:
        return ""
    for cs in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(cs)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


class _Http(object):

    def __init__(self):
        self._cj = cookiejar.CookieJar()
        self._ssl = _mk_ssl()
        self._lock = threading.Lock()
        self._opener = None

    def _op(self):
        if self._opener is not None:
            return self._opener
        with self._lock:
            if self._opener is not None:
                return self._opener
            handlers = [urllib.request.HTTPCookieProcessor(self._cj)]
            if self._ssl is not None:
                handlers.append(urllib.request.HTTPSHandler(context=self._ssl))
            self._opener = urllib.request.build_opener(*handlers)
            return self._opener

    def request(self, url, method="GET", headers=None, body=None,
                timeout=API_TIMEOUT, referer=""):
        method = str(method or "GET").upper()
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")

        base = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        }
        if referer:
            base["Referer"] = referer
        if body is not None:
            base["Content-Type"] = "application/json"
            base["Content-Length"] = str(len(body))
        for k, v in (headers or {}).items():
            if v:
                base[k] = v

        req = urllib.request.Request(url, data=body, headers=base, method=method)
        try:
            with self._op().open(req, timeout=timeout) as resp:
                raw = resp.read()
                rh = dict(resp.headers.items())
                code = resp.getcode()
        except urllib.error.HTTPError as e:
            try:
                raw = e.read()
            except Exception:
                raw = b""
            rh = dict(e.headers.items()) if e.headers else {}
            code = e.code
        except Exception as e:
            return (0, {}, b"", "%s: %s" % (type(e).__name__, str(e)[:80]))

        low = {}
        for k, v in rh.items():
            low[k.lower()] = v
        raw = _decompress(raw, low.get("content-encoding", ""))
        return (code, low, raw, "")

    def head_read(self, url, headers=None, limit=512, referer=""):
        base = {"User-Agent": UA, "Connection": "close"}
        if referer:
            base["Referer"] = referer
        for k, v in (headers or {}).items():
            if v:
                base[k] = v
        req = urllib.request.Request(url, headers=base, method="GET")
        try:
            with self._op().open(req, timeout=PROBE_TIMEOUT) as resp:
                code = resp.getcode()
                low = {}
                for k, v in dict(resp.headers.items()).items():
                    low[k.lower()] = v
                head = _decompress(resp.read(limit), low.get("content-encoding", ""))
                return (code, low, head, "")
        except urllib.error.HTTPError as e:
            return (e.code, dict(e.headers.items()) if e.headers else {}, b"", "")
        except Exception as e:
            return (0, {}, b"", "%s: %s" % (type(e).__name__, str(e)[:60]))


HTTP = _Http()

_HOST_STATE = {"cur": API_HOSTS[0], "bad": {}, "lock": threading.Lock()}


def _host():
    return _HOST_STATE["cur"]


def _host_fail(host):
    with _HOST_STATE["lock"]:
        _HOST_STATE["bad"][host] = time.time()
        alive = [h for h in API_HOSTS
                 if time.time() - _HOST_STATE["bad"].get(h, 0) > 300]
        if alive and alive[0] != _HOST_STATE["cur"]:
            _HOST_STATE["cur"] = alive[0]


# ---------------------------------------------------------------- 接口

def _api_path(method, path, body=None, expect_json=True):
    last = ""
    for _ in range(2):
        host = _host()
        heads = _sign_headers(method, path)
        code, low, raw, err = HTTP.request(
            host + path, method=method, headers=heads, body=body,
            timeout=API_TIMEOUT, referer=host + "/")
        if code == 0:
            last = err or "网络不可达"
            _host_fail(host)
            continue
        if code >= 500:
            last = "http=%s" % code
            _host_fail(host)
            continue
        if code == 401 or code == 403:
            last = "签名被拒 http=%s" % code
            return (code, None, last)
        if not expect_json:
            return (code, raw, "")
        try:
            return (code, json.loads(_decode(raw)), "")
        except Exception as e:
            return (code, None, "返回非 JSON: %s" % str(e)[:80])
    return (0, None, last or "全部域名不可用")


def _get_browse(params):
    parts = []
    for k, v in params.items():
        if v not in (None, "", 0):
            parts.append("%s=%s" % (k, urllib.parse.quote(str(v), safe="")))
    path = "/v1/browse/catalog"
    if parts:
        path = path + "?" + "&".join(parts)
    code, data, err = _api_path("GET", path)
    if data is None:
        return {"list": [], "pagecount": 1, "err": err or ("http=%s" % code)}
    cards = data.get("cards") or []
    pg = data.get("pagination") or {}
    page = _fixed_int(pg.get("page"), 1)
    total = _fixed_int(pg.get("total"), 0)
    if pg.get("has_more"):
        ceil = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 0
        pagecount = max(page + 1, ceil, 2)
    else:
        pagecount = page
    return {"list": cards, "pagecount": pagecount, "total": total}


def _get_home_feed(n_sec=8):
    code, data, err = _api_path("GET", "/v1/feed/home?scope=public")
    if data is None:
        return []
    out = []
    for sec in data.get("sections") or []:
        cards = [c for c in (sec.get("cards") or []) if _variant_of(c)]
        if not cards:
            continue
        out.append({"title": _clean(sec.get("title")) or "推荐", "cards": cards})
        if len(out) >= n_sec:
            break
    return out


def _get_detail(vid):
    code, data, err = _api_path("GET", "/v1/catalog/%s/detail" % vid)
    if data is None:
        return None
    return data


def _get_episodes(vid):
    path = "/v1/catalog/%s/episodes?limit=%d&offset=0" % (vid, EPISODE_LIMIT)
    code, data, err = _api_path("GET", path)
    if data is None:
        return []
    eps = data.get("episodes") or []
    page = data.get("episode_pagination") or {}
    if page.get("has_more") and eps:
        off = len(eps)
        for _ in range(8):
            more = "/v1/catalog/%s/episodes?limit=%d&offset=%d" % (vid, EPISODE_LIMIT, off)
            code2, data2, err2 = _api_path("GET", more)
            got = (data2 or {}).get("episodes") or []
            if not got:
                break
            eps.extend(got)
            off += len(got)
            if not (data2.get("episode_pagination") or {}).get("has_more"):
                break
    return eps


def _card_to_vod(card):
    vid = _variant_of(card)
    if not vid:
        return None
    return {
        "vod_id": vid,
        "vod_name": _clean(card.get("title") or card.get("normalized_title")),
        "vod_pic": _pic_of(card),
        "vod_remarks": _remarks_of(card),
    }


# ---------------------------------------------------------------- 取流

_PLAY_CACHE = {}
_PLAY_LOCK = threading.Lock()


def _is_media_head(code, low, head):
    if code != 200:
        return False
    ct = (low.get("content-type") or "").lower()
    if any(k in ct for k in ("image", "text/html", "application/json")):
        return False
    body = head.lstrip()
    if body[:7] == b"#EXTM3U":
        return True
    if any(k in ct for k in ("mpegurl", "video/", "octet-stream", "application/vnd")):
        return True
    if ct.startswith("audio/"):
        return True
    if b"ftyp" in body[:32]:
        return True
    if body[:4] == b"\x47\x40\x00\x10":
        return True
    return False


def _probe(url):
    code, low, head, err = HTTP.head_read(url, limit=512)
    ok = _is_media_head(code, low, head)
    return (ok, code, (low.get("content-type") or "")[:40], err)


def _host_of(url):
    try:
        return urllib.parse.urlsplit(str(url)).hostname or ""
    except Exception:
        return ""


def _probe_rank(lines, prefer_host=""):
    picked = []
    for lo in lines:
        u = str(lo.get("url") or "")
        if not u.startswith(("http://", "https://")):
            continue
        score = 0
        if prefer_host and _host_of(u) == prefer_host:
            score -= 500
        if lo.get("selected"):
            score -= 30
        if lo.get("default_priority"):
            score -= 20
        kind = str(lo.get("url_kind") or "")
        if kind == "m3u8":
            score -= 6
        elif kind == "mp4":
            score -= 2
        try:
            score -= min(int(lo.get("preference_weight") or 0) // 100, 20)
        except Exception:
            pass
        picked.append((score, len(picked), u, lo))
    picked.sort(key=lambda x: (x[0], x[1]))
    return [p[2] for p in picked[:PROBE_LINES]]


_LINE_WIN = {"host": "", "ts": 0.0, "hits": {}}


def _remember_line(url):
    host = _host_of(url)
    if not host:
        return
    now = time.time()
    _LINE_WIN["hits"][host] = _LINE_WIN["hits"].get(host, 0) + 1
    if len(_LINE_WIN["hits"]) > 64:
        _LINE_WIN["hits"].clear()
    if host != _LINE_WIN["host"] or now - _LINE_WIN["ts"] > 900:
        _LINE_WIN["host"] = host
    _LINE_WIN["ts"] = now


def _prefer_host():
    if time.time() - _LINE_WIN["ts"] > 900:
        return ""
    return _LINE_WIN["host"]


def _best_from_direct(lines):
    urls = _probe_rank(lines, _prefer_host())
    if not urls:
        return ("", "无直链线路")
    try:
        import concurrent.futures as cf
        ex = cf.ThreadPoolExecutor(max_workers=min(PROBE_WORKERS, len(urls)))
        try:
            tasks = {ex.submit(_probe, u): u for u in urls}
            try:
                for fut in cf.as_completed(tasks, timeout=PROBE_TIMEOUT + 8):
                    try:
                        res = fut.result()
                    except Exception:
                        continue
                    if res[0]:
                        return (tasks[fut], "")
            except Exception:
                pass
            for u, res in zip(urls, [t.result() for t in tasks]):
                if res[0]:
                    return (u, "")
        finally:
            try:
                ex.shutdown(wait=False)
            except Exception:
                pass
    except Exception:
        for u in urls:
            if _probe(u)[0]:
                return (u, "")
    return ("", "全部直链预检失败")


def _resolve_ticket(ticket):
    code, data, err = _api_path(
        "POST", "/v1/playback/resolve-line?view=compact",
        body={"ticket": ticket})
    if data is None:
        return ("", err or ("http=%s" % code))
    line = data.get("line") or {}
    u = str(line.get("url") or "")
    if not u:
        return ("", "解析返回为空")
    return (u, "")


def _pick_stream(token):
    code, data, err = _api_path(
        "GET", "/v1/playback/resolve/%s?view=compact" % token)
    if data is None:
        return ("", "", err or ("http=%s" % code))

    lines = data.get("line_options") or []
    if not lines:
        return ("", "", "无可用线路")

    best, reason = _best_from_direct(lines)
    if best:
        return (best, "", "")

    tickets = []
    for lo in lines:
        u = str(lo.get("url") or "")
        if u.startswith("resolve://"):
            tickets.append(u[len("resolve://"):])
    for tk in tickets[:RESOLVE_LINES]:
        url, why = _resolve_ticket(tk)
        if not url:
            continue
        ok, code2, ct, err2 = _probe(url)
        if ok:
            return (url, "", "")
    if tickets:
        url, why = _resolve_ticket(tickets[0])
        if url:
            return (url, "", "")
    return ("", "", reason or "全部线路不可用")


def _play_url(token):
    with _PLAY_LOCK:
        hit = _PLAY_CACHE.get(token)
        if hit and time.time() - hit[0] < PLAY_TTL:
            return hit[1]
    url, skip, err = _pick_stream(token)
    del skip
    if url:
        _remember_line(url)
        with _PLAY_LOCK:
            if len(_PLAY_CACHE) > PLAY_MAX:
                now = time.time()
                for k in [k for k, v in _PLAY_CACHE.items()
                          if now - v[0] > PLAY_TTL]:
                    _PLAY_CACHE.pop(k, None)
                while len(_PLAY_CACHE) > PLAY_MAX:
                    try:
                        _PLAY_CACHE.pop(next(iter(_PLAY_CACHE)), None)
                    except Exception:
                        _PLAY_CACHE.clear()
                        break
            _PLAY_CACHE[token] = (time.time(), url)
    return url


# ---------------------------------------------------------------- 主体

class Spider(SpiderBase):

    def __init__(self):
        self.name = "看剧AI"
        self.host = _host()

    # ---- 框架接口

    def getName(self):
        return self.name

    def init(self, extend=""):
        print("[看剧AI] 初始化完成 %s（接口签名版）" % _host())

        def _warm():
            for host in list(API_HOSTS):
                heads = _sign_headers("GET", "/v1/runtime/bootstrap")
                code, low, raw, err = HTTP.request(
                    host + "/v1/runtime/bootstrap", headers=heads,
                    timeout=10, referer=host + "/")
                if code == 200 and raw:
                    with _HOST_STATE["lock"]:
                        _HOST_STATE["cur"] = host
                    print("[看剧AI] 域名连通 %s" % host)
                    return
                print("[看剧AI] 域名不可用 %s (%s)" % (host, code or err[:60]))
            print("[看剧AI] 全部域名不可用，请检查网络")

        try:
            threading.Thread(target=_warm, daemon=True).start()
        except Exception:
            pass
        return True

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|m4v|ts|mkv)(\?|$)", str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            with _PLAY_LOCK:
                _PLAY_CACHE.clear()
        except Exception:
            pass

    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name}
                   for tid, _kind, name in KIND_ZONES]
        filters = {}
        for tid, kind, _name in KIND_ZONES:
            blocks = [{"key": "area", "name": "地区",
                       "value": [{"n": "全部", "v": ""}] +
                                [{"n": a, "v": a} for a in AREA_LIST]}]
            if kind in ("series", "movie", "anime", "documentary", "short_drama"):
                blocks.append({"key": "genre", "name": "类型",
                               "value": [{"n": "全部", "v": ""}] +
                                        [{"n": g, "v": g} for g in GENRE_LIST]})
            blocks.append({"key": "year", "name": "年份",
                           "value": [{"n": "全部", "v": ""}] +
                                    [{"n": y, "v": y} for y in YEAR_LIST]})
            filters[tid] = blocks
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        videos = []
        for sec in _get_home_feed():
            for card in sec["cards"]:
                v = _card_to_vod(card)
                if v and v["vod_id"] not in [x["vod_id"] for x in videos]:
                    videos.append(v)
        print("[看剧AI] 首页推荐 %d 条" % len(videos))
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        page = _fixed_int(pg, 1)
        tid = str(tid or "latest")
        ext = _of_extend(extend)

        kind = ""
        for z_tid, z_kind, _name in KIND_ZONES:
            if z_tid == tid:
                kind = z_kind
                break

        params = {"page": page, "limit": PAGE_SIZE}
        if kind:
            params["kind"] = kind
        for key in ("area", "genre", "year"):
            val = _clean(ext.get(key))
            if val and val != "全部":
                params[key] = val

        got = _get_browse(params)
        videos = []
        for card in got["list"]:
            v = _card_to_vod(card)
            if v:
                videos.append(v)
        print("[看剧AI] 分类 %s 第%d页 -> %d 条" % (tid, page, len(videos)))
        return {
            "list": videos,
            "page": page,
            "pagecount": got.get("pagecount") or 1,
            "limit": PAGE_SIZE,
            "total": got.get("total") or len(videos),
        }

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = _clean(raw)
        m = re.search(r"(av_[0-9A-Za-z_\-]+)", vid)
        if m:
            vid = m.group(1)

        det = _get_detail(vid)
        if det is None:
            return {"list": []}

        picks = det.get("variants") or []
        chosen = None
        for it in picks:
            if it.get("selected") or it.get("default"):
                chosen = it.get("variant_id") or it.get("id")
                break
        if chosen:
            vid = chosen
        elif picks and not det.get("episodes"):
            for it in picks:
                if it.get("has_playback"):
                    vid = it.get("variant_id") or it.get("id")
                    det = _get_detail(vid) or det
                    break

        eps = det.get("episodes") or []
        want = _fixed_int(det.get("available_episode_count"), len(eps))
        if not eps or (want and len(eps) < want):
            eps = _get_episodes(vid)

        urls = []
        for ep in eps:
            token = str(ep.get("token") or "").strip()
            if not token:
                continue
            title = _clean(ep.get("title")) or ("第%s集" % ep.get("number"))
            urls.append("%s$%s" % (title, token))

        if urls:
            play_from = "看剧AI"
            play_url = "#".join(urls)
        else:
            play_from = "看剧AI"
            play_url = ""

        actors = _take(det.get("actors"), 12)
        directors = _take(det.get("directors"), 4)
        genres = _take(det.get("genres"), 6, " / ")
        area = _clean(det.get("area"))
        year = str(det.get("year") or "")
        desc = _clean(det.get("description") or det.get("overview"))

        lines = []
        if directors:
            lines.append("导演：" + directors)
        if actors:
            lines.append("主演：" + actors)
        head = []
        if genres:
            head.append(genres)
        if area:
            head.append(area)
        if year:
            head.append(year)
        if head:
            lines.insert(0, " · ".join(head))
        if desc:
            lines.append(desc)
        content = "\n".join(lines)

        vod = {
            "vod_id": vid,
            "vod_name": _clean(det.get("title")),
            "vod_pic": _pic_of(det),
            "vod_remarks": _remarks_of(det) or _clean(
                det.get("episode_progress_text")),
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actors,
            "vod_director": directors,
            "vod_content": content,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        print("[看剧AI] 详情 %s -> %d 集" % (vod["vod_name"][:20], len(urls)))
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        page = _fixed_int(pg, 1)
        kw = _clean(key)
        if not kw:
            return {"list": [], "page": page, "pagecount": 1, "total": 0}
        got = _get_browse({"q": kw, "intent": "catalog_search",
                           "page": page, "limit": PAGE_SIZE})
        videos = []
        for card in got["list"]:
            v = _card_to_vod(card)
            if v:
                videos.append(v)
        print("[看剧AI] 搜索 %r 第%d页 -> %d 条" % (kw, page, len(videos)))
        return {
            "list": videos,
            "page": page,
            "pagecount": got.get("pagecount") or 1,
            "limit": PAGE_SIZE,
            "total": got.get("total") or len(videos),
        }

    def playerContent(self, flag, id, vipFlags):
        token = _clean(id)
        if not token:
            return {}

        header = {"User-Agent": UA}

        if self.isVideoFormat(token):
            return {"parse": 0, "url": token, "header": header,
                    "headers": header, "playUrl": ""}

        m = re.search(r"(av_[0-9A-Za-z_\-]+)", token)
        if m:
            token = m.group(1)

        url = _play_url(token)
        if url:
            print("[看剧AI] 取流成功 -> %s" % url[:110])
            return {"parse": 0, "url": url, "header": header,
                    "headers": header, "playUrl": ""}

        hdr = dict(header)
        hdr["Referer"] = _host() + "/"
        print("[看剧AI] 取流失败 token=%s" % token[:60])
        return {"parse": 1, "url": "", "header": hdr, "headers": hdr, "playUrl": ""}
