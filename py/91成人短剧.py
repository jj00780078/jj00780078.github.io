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

import re, time, json, urllib.request
from urllib.parse import quote, urljoin, urlparse

class Spider(BaseSpider):
    def getName(self):
        return "91成人短剧"

    def init(self, extend=""):
        self.host = "https://91crdjai.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
        }

    def getDependence(self):
        return ""

    def _get(self, path, retry=2):
        url = path if path.startswith("http") else self.host + path
        for i in range(retry + 1):
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.read().decode("utf-8", "ignore")
            except Exception:
                if i == retry:
                    return ""
                time.sleep(0.3)
        return ""

    def _unescape(self, s):
        try:
            import html as H
            return H.unescape(s or "")
        except Exception:
            return s or ""

    def homeContent(self, filter=None):
        classes = [
            {"type_id": "duanju", "type_name": "成人短剧"},
            {"type_id": "manju", "type_name": "成人漫剧"},
            {"type_id": "zhenrenju", "type_name": "真人剧"},
            {"type_id": "shipin", "type_name": "成人视频"},
        ]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("duanju", "1")

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = str(pg or "1")
        tid = str(tid)
        if pg == "1":
            path = f"/{tid}/"
        else:
            path = f"/{tid}/page/{pg}/"
        html = self._get(path)
        if not html:
            return {"page": int(pg), "pagecount": 1, "limit": 0, "total": 0, "list": []}
        videos = self._parse_list(html)
        pagecount = int(pg)
        pages = re.findall(r"/%s/page/(\d+)/" % re.escape(tid), html)
        if pages:
            pagecount = max(int(x) for x in pages if x.isdigit())
        elif len(videos) >= 15:
            pagecount = int(pg) + 1
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
        for m in re.finditer(
            r'href="https://91crdjai\.com/((?:duanju|manju|zhenrenju|shipin)/\d+-[^"]+)/"[^>]*'
            r'(?:data-track-item-name="([^"]*)")?',
            html,
        ):
            path = m.group(1).rstrip("/")
            name = self._unescape(m.group(2) or "").strip()
            if path in seen:
                continue
            # expand chunk for img/title
            chunk = html[m.start():m.start() + 900]
            if not name:
                am = re.search(r'alt="([^"]+)"', chunk)
                if am:
                    name = self._unescape(am.group(1)).strip()
            if not name:
                nm = re.search(r'data-track-item-name="([^"]+)"', chunk)
                if nm:
                    name = self._unescape(nm.group(1)).strip()
            pic = ""
            pm = re.search(r'data-src="(https://pic\.[^"]+)"', chunk)
            if not pm:
                pm = re.search(r'src="(https://pic\.[^"]+)"', chunk)
            if pm:
                pic = pm.group(1)
            if len(name) < 1:
                continue
            seen.add(path)
            videos.append({
                "vod_id": path,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "",
            })
        return videos

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        path = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip("/")
        html = self._get(f"/{path}/")
        if not html:
            return {"list": []}
        name = ""
        m = re.search(r"<title>([^<]+)</title>", html)
        if m:
            name = self._unescape(m.group(1))
            for sep in ["-成人", " 全集", "｜", " - "]:
                if sep in name:
                    name = name.split(sep)[0].strip()
        pic = ""
        m = re.search(r'(?:og:image"|data-src|src)="(https://(?:pic|expose)\.[^"]+\.(?:jpeg|jpg|png)[^"]*)"', html)
        if m:
            pic = m.group(1)
        # episodes from eps json or links
        eps = []
        # try eps array titles
        for m in re.finditer(r'"n"\s*:\s*(\d+)\s*,\s*"title"\s*:\s*"([^"]*)"', html):
            n, t = m.group(1), self._unescape(m.group(2))
            if (n, t) not in [(e.split("$")[0], "") for e in eps]:
                eps.append(f"{t or ('第'+n+'集')}${path}|{n}")
        # dedupe by n
        seen_n = set()
        play_parts = []
        for p in eps:
            n = p.split("$")[-1].split("|")[-1]
            if n in seen_n:
                continue
            seen_n.add(n)
            play_parts.append(p)
        if not play_parts:
            # links /path/1/
            for m in re.finditer(rf'href="https://91crdjai\.com/{re.escape(path)}/(\d+)/"', html):
                n = m.group(1)
                if n in seen_n:
                    continue
                seen_n.add(n)
                play_parts.append(f"第{n}集${path}|{n}")
        if not play_parts:
            play_parts = [f"第1集${path}|1"]
        return {
            "list": [{
                "vod_id": path,
                "vod_name": name or path,
                "vod_pic": pic,
                "vod_content": name,
                "vod_play_from": "线路1",
                "vod_play_url": "#".join(play_parts),
            }]
        }

    def searchContent(self, key, quick=False, pg="1"):
        pg = str(pg or "1")
        q = quote(key)
        path = f"/search/?q={q}" if pg == "1" else f"/search/?q={q}&page={pg}"
        # try alternate
        html = self._get(path)
        if not html or "card" not in html:
            html = self._get(f"/search/{q}/")
        videos = self._parse_list(html or "")
        return {
            "list": videos,
            "page": int(pg),
            "pagecount": 1,
            "limit": 24,
            "total": len(videos),
        }

    def _extract_play_src(self, html):
        if not html:
            return ""
        m = re.search(r'"current"\s*:\s*\{[^}]*?"src"\s*:\s*"(https?://[^"]+)"', html)
        if m:
            return m.group(1).replace("\\u0026", "&").encode().decode("unicode_escape") if "\\u" in m.group(1) else m.group(1).replace("\\u0026", "&")
        m = re.search(r'"src"\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"', html)
        if m:
            u = m.group(1).replace("\\u0026", "&")
            try:
                u = u.encode("utf-8").decode("unicode_escape")
            except Exception:
                pass
            return u.replace("\\u0026", "&")
        ms = re.findall(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', html)
        if ms:
            return ms[0].replace("\\u0026", "&")
        return ""

    def _fetch_media(self, url):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.host + "/",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception:
            return ""

    def _resolve_m3u8(self, url):
        if not url or ".m3u8" not in url:
            return url
        body = self._fetch_media(url)
        if not body:
            return url
        if "#EXTINF" in body and "#EXT-X-STREAM-INF" not in body:
            return url
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ".m3u8" in line:
                return line if line.startswith("http") else urljoin(url, line)
        return url

    def playerContent(self, flag, id, vipFlags=None):
        raw = id or ""
        header = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.host + "/",
        }
        if raw.startswith("http"):
            url = self._resolve_m3u8(raw)
        else:
            if "|" in raw:
                path, ep = raw.split("|", 1)
            else:
                path, ep = raw, "1"
            path = path.strip("/")
            html = self._get(f"/{path}/{ep}/")
            url = self._extract_play_src(html)
            if url:
                url = self._resolve_m3u8(url)
        if not url:
            return {"parse": 0, "jx": 0, "url": "", "header": header}
        if ".m3u8" in url and hasattr(self, "getProxyUrl") and self.getProxyUrl():
            base = self.getProxyUrl()
            proxy = base + ("&" if "?" in base else "?") + "url=" + quote(url, safe="") + "&type=m3u8"
            return {"parse": 0, "jx": 0, "url": proxy, "header": header}
        return {"parse": 0, "jx": 0, "url": url, "header": header}

    def localProxy(self, param):
        try:
            url = param.get("url") if isinstance(param, dict) else str(param or "")
            if not url:
                return [404, "text/plain", ""]
            body = self._fetch_media(url)
            if not body:
                return [502, "text/plain", "fetch failed"]
            if "#EXT-X-STREAM-INF" in body and "#EXTINF" not in body:
                for line in body.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and ".m3u8" in line:
                        sub = line if line.startswith("http") else urljoin(url, line)
                        body = self._fetch_media(sub)
                        url = sub
                        break
            cleaned = self._clean_m3u8(body or "", url)
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
            if s.startswith("#EXT-X-KEY"):
                mk = re.search(r'URI="([^"]+)"', s)
                if mk:
                    key_uri = mk.group(1)
                    if key_uri.startswith("/"):
                        s = s.replace(f'URI="{key_uri}"', f'URI="{base_origin + key_uri}"')
                    elif not key_uri.startswith("http"):
                        s = s.replace(f'URI="{key_uri}"', f'URI="{urljoin(base_dir, key_uri)}"')
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
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv)(\?|$)", url or "", re.I))

    def manualVideoCheck(self):
        return False
