# coding=utf-8
"""
5LxTV - TVBox / OK影视 / 影视仓 / BieCuiLe Python Spider
站点：https://5lxtv.com

修复记录（2026-11-16）
1. [核心] 播放修复
   站点加了「防一键下载」：m3u8 不再写进 HTML，改成点播放时请求
   /api/play/<slug>?t=<时间戳>&n=<签名> 才返回清单，金钥走 /api/hlskey。
   原脚本只在 HTML 里正则找 .m3u8/.mp4，永远找不到 → 回退 parse=1 丢给通用解析器
   → BieCuiLe 里一直转圈 / 提示无法播放。
   现在：先从播放页取出 slug / t / n，再请求带 &hls=1 的接口
   （响应头 Content-Type: application/vnd.apple.mpegurl），把这条地址直连播放。
2. 列表解析改成按卡片块解析，标题 / 封面 / 集数不再错位、不再按顺序瞎猜。
3. 详情页选集改用 aio-chips 区块解析，不再把推荐位的其他剧当成集数。
4. 分类改成站点真实路径（/ai-drama、/censored ...），原 ?t= 参数站点不认。
5. 搜索统一走 /search?q=，支持翻页。
6. 请求统一带 UA/Referer、失败重试；单点异常不再往外抛。

若某些播放器只认 .m3u8 结尾的地址，可在源配置 extend 里传 {"proxy": 1}，
改用内置 localProxy 转本地分发的同一条清单（不同客户端支持度不同，默认关闭）。
"""

import re
import gzip
import json
import time
import base64
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getName(self): return ""
        def init(self, extend=""): pass
        def homeContent(self, filter=None): return {}
        def homeVideoContent(self): return {}
        def categoryContent(self, tid, pg, filter=None, extend=None): return {}
        def detailContent(self, ids): return {}
        def searchContent(self, key, quick=False, pg="1"): return {}
        def playerContent(self, flag, id, vipFlags=None): return {}
        def localProxy(self, param): return [404, "text/plain", ""]
        def getDependence(self): return ""
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False


class Spider(BaseSpider):

    # 站点常见分类（/channels 抓取失败时用这份兜底）
    FALLBACK_CATS = [
        ("ai-drama", "成人短劇"),
        ("censored", "有碼A片"),
        ("decensored", "無碼破解"),
        ("chinese", "中文字幕"),
        ("selfie", "偷拍盜攝"),
        ("cuckold", "綠帽NTR"),
        ("exclusive", "國產AV"),
        ("anime", "動漫"),
        ("cos", "Cosplay"),
        ("western", "歐美"),
        ("fc2", "FC2"),
        ("of", "OnlyFans"),
    ]

    CARD_RE = re.compile(r'<a\b[^>]*href="/videos/([^"#?]+)"[^>]*>(.*?)</a>', re.S)
    CHIP_RE = re.compile(r'<a\b([^>]*?)href="/videos/([^"#?]+)"([^>]*?)>(.*?)</a>', re.S)

    def getName(self):
        return "5LxTV"

    def init(self, extend=""):
        self.host = "https://5lxtv.com"
        self.ua = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")
        self.timeout = 15
        self.headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6",
            "Referer": self.host + "/",
        }
        self.use_proxy = False
        self._cache = {}
        try:
            cfg = extend if isinstance(extend, dict) else json.loads(extend or "{}")
            if isinstance(cfg, dict):
                if cfg.get("site"):
                    self.host = str(cfg.get("site")).rstrip("/")
                self.use_proxy = bool(cfg.get("proxy"))
        except Exception:
            pass

    def getDependence(self):
        return ""

    # ------------------------------------------------------------------ 基础

    def _request(self, url, referer=None, retry=2):
        for i in range(retry):
            try:
                headers = dict(self.headers)
                if referer:
                    headers["Referer"] = referer
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    if "gzip" in (resp.headers.get("Content-Encoding") or "").lower():
                        try:
                            raw = gzip.decompress(raw)
                        except Exception:
                            pass
                    charset = resp.headers.get_content_charset() or "utf-8"
                    return raw.decode(charset, "ignore")
            except Exception:
                if i + 1 < retry:
                    time.sleep(0.4)
        return ""

    def _cached(self, key, loader, ttl=300):
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = loader()
        self._cache[key] = (now, value)
        return value

    def _url(self, u, base=None):
        if not u:
            return ""
        u = str(u).strip().replace("\\/", "/")
        u = u.replace("&amp;", "&")
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return urllib.parse.urljoin(base or (self.host + "/"), u)

    def _clean(self, s):
        s = str(s or "")
        s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
        s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
        s = re.sub(r"<[^>]+>", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    def _abs_pic(self, u, base=None):
        u = self._url(u, base)
        if not u:
            return ""
        return u

    def _tid_path(self, tid):
        tid = str(tid or "").strip()
        if not tid or tid in ("all", "全部", "latest"):
            return "latest"
        if tid.startswith("http"):
            return tid
        return tid.lstrip("/")

    # ------------------------------------------------------------- 分类与首页

    def _categories(self):
        def load():
            text = self._request(self.host + "/channels")
            skip = {"latest", "actors", "tags", "ranking", "channels", "install",
                    "favorites", "policy", "2257", "terms", "abuse", "backup",
                    "search", "ai"}
            cats, seen = [], set()
            for m in re.finditer(r'<a\s+href="/([a-z0-9][a-z0-9\-]*)"[^>]*>([^<]{1,24})</a>',
                                 text or ""):
                tid, name = m.group(1), self._clean(m.group(2))
                if tid in skip or not name or tid in seen:
                    continue
                seen.add(tid)
                cats.append((tid, name))
            return cats

        cats = self._cached("cats", load, 86400)
        return cats or list(self.FALLBACK_CATS)

    def homeContent(self, filter=None):
        classes = [{"type_id": "latest", "type_name": "全部"}]
        for tid, name in self._categories():
            if tid == "latest":
                continue
            classes.append({"type_id": tid, "type_name": name})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("latest", "1")

    # ---------------------------------------------------------------- 列表解析

    def _items(self, text, base):
        out, seen = [], set()
        for m in self.CARD_RE.finditer(text or ""):
            slug = m.group(1).strip("/")
            block = m.group(2)
            if not slug or slug in seen or len(block) < 40:
                continue
            seen.add(slug)

            title = ""
            mt = re.search(r'<div class="[^"]*(?:line-clamp|mt-1\.5)[^"]*"[^>]*>(.*?)</div>',
                           block, re.S)
            if mt:
                title = self._clean(mt.group(1))
            if not title:
                mt = re.search(r'<img[^>]+alt="([^"]+)"', block)
                if mt:
                    title = self._clean(mt.group(1))
            if not title:
                title = slug

            pic = ""
            mi = re.search(r'<img[^>]+>', block)
            if mi:
                tag = mi.group(0)
                mm = re.search(r'(?:data-src|data-original|data-lazy-src|src)="([^"]+)"', tag)
                if mm:
                    pic = self._abs_pic(mm.group(1), base)

            remarks = ""
            mr = re.search(r'>\s*(\d+)\s*集\s*<', block)
            if mr:
                remarks = mr.group(1) + "集"
            else:
                mr = re.search(r'(更新中|已完結|已完结)', block)
                if mr:
                    remarks = mr.group(1)

            out.append({
                "vod_id": slug,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return out

    def categoryContent(self, tid, pg, filter=None, extend=None):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1

        try:
            path = self._tid_path(tid)
            url = path if path.startswith("http") else self.host + "/" + path
            if page > 1:
                url += ("&" if "?" in url else "?") + "page=" + str(page)

            text = self._request(url)
            videos = self._items(text, url)

            max_page = page
            for n in re.findall(r'[?&]page=(\d+)', text or ""):
                try:
                    max_page = max(max_page, int(n))
                except Exception:
                    pass
            if not videos:
                max_page = page

            return {
                "page": page,
                "pagecount": max_page,
                "limit": len(videos) or 20,
                "total": len(videos) * max(max_page, 1),
                "list": videos,
            }
        except Exception:
            return {"page": page, "pagecount": page, "limit": 20, "total": 0, "list": []}

    # ---------------------------------------------------------------- 详情解析

    def _page_url(self, vid):
        vid = str(vid or "").strip()
        if vid.startswith("http"):
            return vid, vid.rstrip("/").split("/")[-1]
        return self.host + "/videos/" + urllib.parse.quote(vid.strip("/")), vid

    def _family(self, slug):
        m = re.match(r'^(.*?)-(\d+)([a-z]?)$', slug or "")
        if m:
            return m.group(1) + "-" + m.group(3)
        return slug or ""

    def detailContent(self, ids):
        try:
            vid = ids[0] if isinstance(ids, (list, tuple)) else ids
            if not vid:
                return {"list": []}
            page_url, slug = self._page_url(vid)
            text = self._request(page_url)

            title = ""
            m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
            if m:
                title = self._clean(m.group(1))
            if not title:
                m = re.search(r'<title[^>]*>(.*?)</title>', text, re.S)
                title = self._clean(m.group(1)) if m else slug
            base_title = re.sub(r'\s*[·\-]\s*第\s*\d+\s*集\s*$', '', title).strip() or title or slug

            pic = ""
            m = re.search(r'poster="([^"]+)"', text)
            if m:
                pic = self._abs_pic(m.group(1), page_url)
            if not pic:
                m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                              text, re.I)
                if m:
                    pic = self._abs_pic(m.group(1), page_url)
            if not pic:
                for mm in re.finditer(r'<img[^>]+src="([^"]+)"', text or ""):
                    u = self._abs_pic(mm.group(1), page_url)
                    if re.search(r'\.(jpg|jpeg|png|webp)(\?|$)', u, re.I):
                        pic = u
                        break

            desc = ""
            m = re.search(r'<p class="aio-sd-t"[^>]*>(.*?)</p>', text, re.S)
            if m:
                desc = self._clean(m.group(1))
            if not desc:
                m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                              text, re.I | re.S)
                if m:
                    desc = self._clean(m.group(1))

            episodes = self._episodes(text, slug)

            parts = []
            for no, eid in episodes:
                parts.append("第%02d集$%s" % (no, eid))
            line = "#".join(parts) if parts else ("全集$" + slug)
            # 线路1 直连签名接口；线路2 交给客户端自带嗅探，播不了可切换
            play_url = line + "$$$" + line

            return {"list": [{
                "vod_id": slug,
                "vod_name": base_title,
                "vod_pic": pic,
                "vod_content": desc or base_title,
                "vod_remarks": ("%d集" % len(episodes)) if len(episodes) > 1 else "",
                "vod_year": "",
                "vod_area": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_play_from": "5LxTV直連$$$5LxTV代理",
                "vod_play_url": play_url,
            }]}
        except Exception:
            return {"list": []}

    def _episodes(self, text, slug):
        """选集：优先解析 aio-chips 区块，避免把推荐位其他剧当成集数"""
        text = text or ""
        episodes = []
        seen = set()

        block = ""
        m = re.search(r'id="aio-chips"[^>]*>(.*?)</div>', text, re.S)
        if m:
            block = m.group(1)

        if block:
            for am in self.CHIP_RE.finditer(block):
                attrs = (am.group(1) or "") + " " + (am.group(3) or "")
                eid = am.group(2).strip("/")
                if not eid or eid in seen:
                    continue
                label = ""
                tm = re.search(r'title="第\s*(\d+)\s*集"', attrs)
                if tm:
                    label = tm.group(1)
                if not label:
                    inner = self._clean(am.group(4))
                    if re.fullmatch(r'\d{1,3}', inner or ""):
                        label = inner
                if not label:
                    label = str(len(episodes) + 1)
                try:
                    no = int(label)
                except Exception:
                    no = len(episodes) + 1
                seen.add(eid)
                episodes.append((no, eid))

        if not episodes:
            episodes = [(1, slug)]

        episodes.sort(key=lambda x: x[0])
        # 重新编号，避免站点重播/花絮造成的乱序空号
        return [(i + 1, e[1]) for i, e in enumerate(episodes)]

    # ---------------------------------------------------------------- 搜索

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        try:
            url = self.host + "/search?q=" + urllib.parse.quote(str(key or ""))
            if page > 1:
                url += "&page=" + str(page)
            text = self._request(url)
            videos = self._items(text, url)
            max_page = page
            for n in re.findall(r'[?&]page=(\d+)', text or ""):
                try:
                    max_page = max(max_page, int(n))
                except Exception:
                    pass
            return {
                "list": videos,
                "page": page,
                "pagecount": max_page if videos else 1,
                "limit": len(videos) or 20,
                "total": len(videos),
            }
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

    # ---------------------------------------------------------------- 播放

    def _play_api(self, text, page_url):
        """从播放页里取出签名，拼出真正的 m3u8 接口地址"""
        text = text or ""
        m = re.search(
            r'var\s+slug\s*=\s*["\']([^"\']+)["\'][\s\S]{0,400}?'
            r'var\s+t\s*=\s*(\d+)[\s\S]{0,400}?'
            r'var\s+n\s*=\s*["\']([^"\']+)["\']',
            text)
        if m:
            slug, ts, sign = m.group(1), m.group(2), m.group(3)
        else:
            ms = re.search(r'var\s+slug\s*=\s*["\']([^"\']+)["\']', text)
            mt = re.search(r'var\s+t\s*=\s*(\d+)', text)
            mn = re.search(r'var\s+n\s*=\s*["\']([^"\']+)["\']', text)
            if not (mt and mn):
                return ""
            slug = ms.group(1) if ms else page_url.rstrip("/").split("/")[-1]
            ts, sign = mt.group(1), mn.group(1)

        # hls=1 让接口直接回清单（Content-Type: application/vnd.apple.mpegurl）
        # 末尾 &f=play.m3u8 是给只按地址后缀判断格式的播放器看的，站点会忽略该参数
        return "%s/api/play/%s?t=%s&n=%s&hls=1&f=play.m3u8" % (
            self.host,
            urllib.parse.quote(slug),
            ts,
            urllib.parse.quote(sign),
        )

    # ------------------------------------------------------------ 本地代理

    def _b64(self, s):
        return base64.urlsafe_b64encode(str(s or "").encode("utf-8")).decode("ascii").rstrip("=")

    def _unb64(self, s):
        s = str(s or "")
        s += "=" * (-len(s) % 4)
        try:
            return base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8")
        except Exception:
            return ""

    def _proxy_url(self, kind, target, referer):
        return ("http://127.0.0.1:9978/proxy?do=py&type=%s&u=%s&r=%s"
                % (kind, self._b64(target), self._b64(referer)))

    def _rewrite_m3u8(self, text, referer):
        """把金钥地址换成本地代理（金钥接口强制校验 Referer，代理端补上）"""
        out = []
        for line in (text or "").splitlines():
            if "#EXT-X-KEY" in line or "#EXT-X-MAP" in line:
                def _sub(m):
                    return 'URI="%s"' % self._proxy_url("key", m.group(1), referer)
                line = re.sub(r'URI="([^"]+)"', _sub, line)
            out.append(line)
        return "\n".join(out)

    def _build_proxy_m3u8(self, api, referer):
        text = self._request(api, referer=referer)
        if not text or "#EXTM3U" not in text:
            return ""
        return self._rewrite_m3u8(text, referer)

    def _direct_media(self, text, page_url):
        """兜底：页面若直接给 m3u8/mp4 直链则取出来"""
        patterns = [
            r'''["'](https?://[^"'<>\s]+\.(?:m3u8|mp4)(?:\?[^"'<>\s]*)?)["']''',
            r'''["'](//[^"'<>\s]+\.(?:m3u8|mp4)(?:\?[^"'<>\s]*)?)["']''',
            r'''(?:file|src|play_url|videoUrl|contentUrl)\s*["']?\s*[:=]\s*["']([^"'<>\s]+)''',
        ]
        for pat in patterns:
            for m in re.findall(pat, text or "", re.I):
                u = self._url(m, page_url)
                if re.search(r'\.(m3u8|mp4)(\?|$)', u, re.I):
                    return u
        m = re.search(r'<(?:video|source)[^>]+src="([^"]+)"', text or "", re.I)
        if m:
            u = self._url(m.group(1), page_url)
            if u:
                return u
        return ""

    def playerContent(self, flag, id, vipFlags=None):
        try:
            page_url, slug = self._page_url(id)
            headers = {
                "User-Agent": self.ua,
                "Referer": page_url,
                "Origin": self.host,
            }
            flag = str(flag or "")

            # 线路2：本地代理，清单与金钥都由这里带着 Referer 去取
            if "代理" in flag:
                text = self._request(page_url)
                api = self._play_api(text, page_url)
                if api and self._build_proxy_m3u8(api, page_url):
                    return {"parse": 0, "jx": 0,
                            "url": self._proxy_url("m3u8", api, page_url),
                            "header": headers}

            # 备用：交回播放页让客户端自己嗅探
            if "備用" in flag or "备用" in flag:
                return {"parse": 1, "jx": 1, "url": page_url, "header": headers}

            # 线路1：直连签名接口（播放器需带上上面这组 header）
            text = self._request(page_url)
            api = self._play_api(text, page_url)
            if api:
                return {"parse": 0, "jx": 0, "url": api, "header": headers}

            media = self._direct_media(text, page_url)
            if media:
                return {"parse": 0, "jx": 0, "url": media, "header": headers}

            return {"parse": 1, "jx": 1, "url": page_url, "header": headers}
        except Exception:
            try:
                page_url, _ = self._page_url(id)
            except Exception:
                page_url = ""
            return {"parse": 1, "jx": 1, "url": page_url,
                    "header": {"User-Agent": self.ua}}

    def localProxy(self, param):
        """本地代理：
        type=key  → 带 Referer 取 AES 金钥（站点强制校验 Referer）
        type=m3u8 → 取回清单，把金钥地址改写成走本代理后再返回
        """
        try:
            if not isinstance(param, dict):
                raw = str(param or "")
                qs = urllib.parse.parse_qs(raw.split("?", 1)[-1])
                param = dict((k, v[0]) for k, v in qs.items())

            kind = param.get("type") or "m3u8"
            target = self._unb64(param.get("u") or param.get("url") or "")
            referer = self._unb64(param.get("r") or "") or (self.host + "/")

            if not target:
                return [404, "text/plain", ""]

            if kind == "key":
                req = urllib.request.Request(target, headers={
                    "User-Agent": self.ua,
                    "Referer": referer,
                    "Origin": self.host,
                })
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return [200, "application/octet-stream", resp.read()]

            text = self._request(target, referer=referer)
            if not text or "#EXTM3U" not in text:
                return [502, "text/plain", ""]
            return [200, "application/vnd.apple.mpegurl",
                    self._rewrite_m3u8(text, referer).encode("utf-8")]
        except Exception as e:
            return [500, "text/plain", str(e)[:200]]

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv)(\?|$)', url or "", re.I))

    def manualVideoCheck(self):
        return False
