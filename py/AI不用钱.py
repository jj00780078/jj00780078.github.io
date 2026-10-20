# coding=utf-8
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
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

import re, time, json, base64, http.cookiejar, urllib.request
from urllib.parse import quote, urljoin, urlparse

class Spider(BaseSpider):
    def getName(self):
        return "AI不用钱"

    def init(self, extend=""):
        # 入口可能是随机子域，主域更稳
        self.host = "https://aibyq.cc"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
        }
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj))

    def getDependence(self):
        return ""

    def _req(self, path, method="GET", data=None, headers=None, retry=2):
        url = path if path.startswith("http") else self.host + path
        hdrs = dict(self.headers)
        if headers:
            hdrs.update(headers)
        body = None
        if data is not None:
            body = data if isinstance(data, (bytes, bytearray)) else (
                data.encode() if isinstance(data, str) else json.dumps(data).encode()
            )
            hdrs.setdefault("Content-Type", "application/json")
        last = None
        for i in range(retry + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
                with self._opener.open(req, timeout=18) as resp:
                    return resp.read().decode("utf-8", "ignore")
            except Exception as e:
                last = e
                time.sleep(0.3)
        return ""

    def _get(self, path):
        return self._req(path)

    def _unescape(self, s):
        try:
            import html as H
            return H.unescape(s or "")
        except Exception:
            return s or ""

    def homeContent(self, filter=None):
        classes = [
            {"type_id": "aidj/AIchengrenduanju", "type_name": "AI成人短剧"},
            {"type_id": "aidj/AIchengrenmanju", "type_name": "AI成人漫剧"},
            {"type_id": "aidj/AImogai", "type_name": "AI魔改"},
            {"type_id": "aidj/AIhuanlian", "type_name": "AI换脸"},
            {"type_id": "home", "type_name": "首页推荐"},
        ]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("home", "1")

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = str(pg or "1")
        tid = str(tid).strip("/")
        if tid == "home":
            path = "/home/" if pg == "1" else f"/home/page/{pg}/"
        else:
            path = f"/{tid}/" if pg == "1" else f"/{tid}/page/{pg}/"
        html = self._get(path)
        if not html:
            return {"page": int(pg), "pagecount": 1, "limit": 0, "total": 0, "list": []}
        videos = self._parse_list(html)
        pages = re.findall(r"/page/(\d+)/", html)
        nums = [int(x) for x in pages if str(x).isdigit() and int(x) < 500]
        pagecount = max(nums) if nums else (int(pg) + 1 if len(videos) >= 12 else int(pg))
        return {
            "page": int(pg),
            "pagecount": pagecount,
            "limit": 24,
            "total": pagecount * 24,
            "list": videos,
        }

    def _parse_list(self, html):
        videos = []
        seen = set()
        for m in re.finditer(r'href="(/detail/(\d+)/\s*)"', html):
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            chunk = html[m.start():m.start() + 500]
            chunkb = html[max(0, m.start() - 100):m.start() + 600]
            name = ""
            for pat in [r'title="([^"]+)"', r'alt="([^"]+)"']:
                tm = re.search(pat, chunkb)
                if tm:
                    name = self._unescape(tm.group(1)).strip()
                    break
            if not name:
                # text after link in nav-style
                tm = re.search(r'href="/detail/%s/"[^>]*>\s*([^<\n]{2,60})' % vid, html)
                if tm:
                    name = self._unescape(tm.group(1)).strip()
            pic = ""
            pm = re.search(r'(?:data-original|data-src|src)="(https?://[^"]+|/upload/[^"]+)"', chunkb)
            if pm:
                pic = pm.group(1)
                if pic.startswith("/"):
                    pic = self.host + pic
            if any(k in name for k in ("幼女", "儿童", "小学生")):
                continue
            videos.append({
                "vod_id": vid,
                "vod_name": name or vid,
                "vod_pic": pic,
                "vod_remarks": "",
            })
        return videos

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        html = self._get(f"/detail/{vid}/")
        if not html:
            return {"list": []}
        name = ""
        m = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
        if m:
            name = self._unescape(m.group(1)).strip()
        if not name:
            m = re.search(r"<title>([^<]+)</title>", html)
            if m:
                name = self._unescape(m.group(1)).split("-")[0].strip()
        pic = ""
        m = re.search(r'(?:data-original|data-src|src)="(https?://media\.[^"]+|/upload/vod/[^"]+)"', html)
        if m:
            pic = m.group(1)
            if pic.startswith("/"):
                pic = self.host + pic
        # episodes
        eps = []
        seen = set()
        for m in re.finditer(r'href="(/play/(\d+)-(\d+)-(\d+)/\s*)"[^>]*>([^<]*)', html):
            path, a, b, c, label = m.group(1), m.group(2), m.group(3), m.group(4), self._unescape(m.group(5)).strip()
            key = f"{a}-{b}-{c}"
            if key in seen:
                continue
            seen.add(key)
            if not label or "立即" in label:
                label = f"第{c}集"
            eps.append((int(c), label, key))
        eps.sort(key=lambda x: x[0])
        if not eps:
            eps = [(1, "第1集", f"{vid}-1-1")]
        play_url = "#".join([f"{t}${k}" for _, t, k in eps])
        return {
            "list": [{
                "vod_id": vid,
                "vod_name": name or vid,
                "vod_pic": pic,
                "vod_content": name,
                "vod_play_from": "线路1",
                "vod_play_url": play_url,
            }]
        }

    def searchContent(self, key, quick=False, pg="1"):
        pg = str(pg or "1")
        q = quote(key)
        # site search pattern: /search/------------{kw}-/
        if pg == "1":
            path = f"/search/------------{q}-/"
        else:
            path = f"/search/------------{q}-/page/{pg}/"
        html = self._get(path)
        videos = self._parse_list(html or "")
        pages = re.findall(r"/page/(\d+)/", html or "")
        nums = [int(x) for x in pages if str(x).isdigit() and int(x) < 500]
        pagecount = max(nums) if nums else 1
        return {
            "list": videos,
            "page": int(pg),
            "pagecount": pagecount,
            "limit": 24,
            "total": pagecount * 24,
        }

    def _player_data(self, play_key):
        # play_key like 2838-1-1
        html = self._get(f"/play/{play_key}/")
        m = re.search(r"var player_data\s*=\s*(\{.+?\})\s*;?\s*</script>", html or "", re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

    def _huangguo_url(self, hg_id, ep, referer):
        api = f"/huangguo.php?ac=play&id={quote(str(hg_id))}&ep={quote(str(ep))}&_={int(time.time())}"
        text = self._req(api, headers={"Referer": referer, "Accept": "application/json"})
        if not text:
            return ""
        try:
            d = json.loads(text)
        except Exception:
            return ""
        if d.get("code") != 1 or not d.get("url"):
            return ""
        url = d["url"]
        if url.startswith("/"):
            url = self.host + url
        return url

    def _decode_proxy_e(self, url):
        # optional: expand base64 e= to real m3u8 if needed
        m = re.search(r"[?&]e=([A-Za-z0-9_\-]+)", url or "")
        if not m:
            return url
        try:
            raw = m.group(1)
            pad = "=" * ((4 - len(raw) % 4) % 4)
            real = base64.urlsafe_b64decode(raw + pad).decode("utf-8", "ignore")
            if real.startswith("http"):
                return real
        except Exception:
            pass
        return url

    def playerContent(self, flag, id, vipFlags=None):
        raw = id or ""
        header = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.host + "/",
        }
        if raw.startswith("http"):
            return {"parse": 0, "jx": 0, "url": raw, "header": header}
        play_key = raw.strip("/")
        if play_key.isdigit():
            play_key = f"{play_key}-1-1"
        referer = f"{self.host}/play/{play_key}/"
        header["Referer"] = referer
        pdata = self._player_data(play_key)
        url_field = (pdata.get("url") or "").strip()
        frm = (pdata.get("from") or "").strip()
        play_url = ""
        if "|" in url_field and (frm == "huangguo" or url_field.replace("|", "").isdigit()):
            parts = url_field.split("|")
            hg_id, ep = parts[0], parts[1] if len(parts) > 1 else "1"
            play_url = self._huangguo_url(hg_id, ep, referer)
        elif url_field.startswith("http"):
            play_url = url_field
        elif url_field.startswith("/"):
            play_url = self.host + url_field
        if not play_url:
            return {"parse": 0, "jx": 0, "url": "", "header": header}
        # prefer site proxy (rewrites keys/segments)
        if hasattr(self, "getProxyUrl") and self.getProxyUrl() and (
            "m3u8" in play_url or "hgmedia.php" in play_url
        ):
            base = self.getProxyUrl()
            proxy = base + ("&" if "?" in base else "?") + "url=" + quote(play_url, safe="") + "&type=m3u8"
            return {"parse": 0, "jx": 0, "url": proxy, "header": header}
        return {"parse": 0, "jx": 0, "url": play_url, "header": header}

    def localProxy(self, param):
        try:
            url = param.get("url") if isinstance(param, dict) else str(param or "")
            if not url:
                return [404, "text/plain", ""]
            text = self._req(url, headers={"Referer": self.host + "/", "Accept": "*/*"})
            if not text:
                return [502, "text/plain", "fetch failed"]
            if "#EXT-X-STREAM-INF" in text and "#EXTINF" not in text:
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and (".m3u8" in line or line.startswith("/")):
                        sub = line if line.startswith("http") else urljoin(url, line)
                        text = self._req(sub, headers={"Referer": self.host + "/"})
                        url = sub
                        break
            cleaned = self._clean_m3u8(text or "", url)
            return [200, "application/vnd.apple.mpegurl", cleaned]
        except Exception as e:
            return [500, "text/plain", str(e)[:200]]

    def _clean_m3u8(self, content, base_url=""):
        if not content or "#EXTM3U" not in content:
            return content
        parsed = urlparse(base_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        base_dir = base_url.rsplit("/", 1)[0] + "/"
        out = []
        for line in content.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#EXT-X-KEY") or s.startswith("#EXT-X-MAP"):
                mk = re.search(r'URI="([^"]+)"', s)
                if mk:
                    uri = mk.group(1)
                    if uri.startswith("/"):
                        s = s.replace(f'URI="{uri}"', f'URI="{base_origin + uri}"')
                    elif not uri.startswith("http"):
                        s = s.replace(f'URI="{uri}"', f'URI="{urljoin(base_dir, uri)}"')
                out.append(s)
            elif s.startswith("#"):
                out.append(s)
            else:
                if s.startswith("http"):
                    out.append(s)
                elif s.startswith("/"):
                    out.append(base_origin + s)
                else:
                    out.append(urljoin(base_dir, s))
        return "\n".join(out)

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4)(\?|$)", url or "", re.I) or "hgmedia.php" in (url or ""))

    def manualVideoCheck(self):
        return False
