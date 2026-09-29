import re
import json
import requests
from urllib.parse import quote, urlsplit, parse_qs
from html import unescape
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.name = "华人影院"
        self.host = "https://huarw.com"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 Chrome/150.0.0.0 Mobile",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        # 顶层分类 -> (type_id, 展示名)
        self.units = {
            "dianying": "电影",
            "dianshiju": "电视剧",
            "zongyi": "综艺",
            "dongman": "动漫",
            "duanju": "短剧"
        }
        # 各分类下的拼音子分类 (filters 的 class 值)
        self.class_py = {
            "dianying": {
                "喜剧片": "xijupian", "动作片": "dongzuopian", "剧情片": "juqingpian",
                "爱情片": "aiqingpian", "科幻片": "kehuanpian", "恐怖片": "kongbupian",
                "动画片": "donghuapian", "战争片": "zhanzhengpian",
            },
            "dianshiju": {
                "国产剧": "guochangju", "欧美剧": "oumeiju", "日本剧": "ribenju",
                "韩国剧": "hanguoju", "海外剧": "haiwaiju",
            },
            "zongyi": {
                "大陆综艺": "daluzongyi", "欧美综艺": "oumeizongyi", "日韩综艺": "rihanzongyi",
            },
            "dongman": {
                "国产动漫": "guochandongman", "海外动漫": "haiwaidongman",
                "欧美动漫": "oumeidongman", "日韩动漫": "rihandongman",
            },
            "duanju": {
                "重生短剧": "chongshengduanju", "穿越短剧": "chuanyueduanju",
                "复仇短剧": "fuchouduanju", "神豪短剧": "shenhaoduanju",
            },
        }
        self.years = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"]
        self.areas = ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "泰国", "印度", "其他"]
        self.langs = ["国语", "英语", "粤语", "韩语", "日语"]
        self.areas_tv = ["大陆", "香港", "台湾", "美国", "日本", "韩国", "泰国", "其他"]
        self.arts = ["大陆", "日本", "欧美"]

    def init(self, extend=""):
        try:
            if extend:
                cfg = json.loads(extend)
                if cfg.get("host"):
                    self.host = str(cfg.get("host")).rstrip("/")
                    self.header["Referer"] = self.host + "/"
        except Exception:
            pass

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r'\.(m3u8|mp4|ts|flv)(\?|$)', url)) or 'm3u8' in url

    def isTextFormat(self, url):
        return False

    def localProxy(self, param):
        return {}

    def fix_url(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    def _get(self, path, headers=None):
        url = path if path.startswith("http") else self.host + path
        request_headers = dict(self.header)
        request_headers.update(headers or {})
        for _ in range(2):
            try:
                r = requests.get(url, headers=request_headers, timeout=20, verify=False)
                if r.status_code == 200 and r.text:
                    return r.text
            except Exception:
                continue
        return ""

    def _cards(self, html):
        cards = []
        seen = set()
        chunks = re.split(r'(?=class="public-list-box)', html)
        for c in chunks:
            if 'href="/movie/' not in c:
                continue
            try:
                mid = re.search(r'href="/movie/(\d+)"', c)
                if not mid:
                    continue
                mid = mid.group(1)
                if mid in seen:
                    continue
                nm = re.search(r'<h3>\s*<a[^>]*>([^<]+)</a>', c)
                if not nm:
                    nm = re.search(r'title="([^"]+)"', c)
                if not nm:
                    nm = re.search(r'alt="([^"]+?)封面图"', c)
                if not nm:
                    nm = re.search(r'class="slide-info-title hide">([^<]+)<', c)
                pc = re.search(r'data-src="(//[^"]+|https?://[^"]+)"', c)
                if not pc:
                    pc = re.search(r"background-image:\s*url\('([^']+)'", c)
                rm = re.search(r'public-list-prb[^>]*>\s*([^<]+?)\s*<', c)
                if not rm:
                    rm = re.search(r'cdn-data-src="(//[^"]+|https?://[^"]+)"', c)
                cards.append({
                    "vod_id": mid,
                    "vod_name": nm.group(1).strip() if nm else mid,
                    "vod_pic": self.fix_url(pc.group(1)) if pc else "",
                    "vod_remarks": rm.group(1).strip() if rm else ""
                })
                seen.add(mid)
            except Exception:
                continue
        return cards

    def homeContent(self, filter):
        cates = [{"type_id": k, "type_name": v} for k, v in self.units.items()]
        html = self._get("/show/dianying")
        cards = self._cards(html)[:24]
        return {"class": cates, "list": cards, "filters": self._filters()}

    def homeVideoContent(self):
        html = self._get("/show/dianying")
        return {"list": self._cards(html)[:12]}

    def _filters(self):
        """筛选走 /show/{拼音分类} (避开被 CF 拦截的 /search/)。"""
        fs = {}
        for tid, cname in self.units.items():
            vals = [{"n": "全部", "v": ""}]
            for name in self.class_py.get(tid, {}):
                vals.append({"n": name, "v": name})
            flt = [{"key": "class", "name": "分类", "value": vals}]
            flt.append({"key": "year", "name": "年份",
                        "value": [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in self.years]})
            ar = self.arts if tid == "dongman" else (self.areas_tv if tid != "dianying" else self.areas)
            flt.append({"key": "area", "name": "地区",
                        "value": [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in ar]})
            flt.append({"key": "lang", "name": "语言",
                        "value": [{"n": "全部", "v": ""}] + [{"n": l, "v": l} for l in self.langs]})
            flt.append({"key": "by", "name": "排序", "value": [
                {"n": "最新", "v": "time"}, {"n": "最热", "v": "hits"}, {"n": "评分", "v": "score"}]})
            fs[tid] = flt
        return fs

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        extend = extend or {}
        # 决定列表基底路径:
        #  - 有 class 筛选 -> /show/{拼音子分类}
        #  - 否则 -> /show/{顶层分类}
        cls_name = extend.get("class")
        py = self.class_py.get(str(tid), {}).get(cls_name, "") if cls_name else ""
        base = ("/show/%s" % py) if py else ("/show/%s" % str(tid))
        # 追加筛选段: year/area/lang 任意组合 + by 排序
        for key, val in (("year", extend.get("year")), ("area", extend.get("area")),
                         ("lang", extend.get("lang"))):
            if val:
                base += "/%s/%s" % (key, quote(str(val)))
        if extend.get("by"):
            base += "/by/%s" % extend["by"]
        base += "/page/%d" % pg
        cards = self._cards(self._get(base))
        pagecount = pg if len(cards) < 20 else pg + 1
        total = pg * 20
        return {"list": cards, "page": pg, "pagecount": pagecount,
                "limit": 20, "total": total}

    def detailContent(self, ids):
        mid = str(ids[0]).split('-')[0]
        html = self._get("/movie/%s" % mid)
        vod = {"vod_id": mid, "vod_name": mid, "vod_pic": "", "vod_remarks": "",
               "vod_year": "", "vod_area": "", "vod_actor": "", "vod_director": "",
               "vod_content": "", "type_name": ""}
        try:
            nm = re.search(r'<h1 class="seo-h1">([^<]+)</h1>', html)
            if nm:
                vod["vod_name"] = nm.group(1).strip()
            pc = re.search(r'(?:data-src|src)="(//[^"]+|https?://[^"]+/upload/vod/[^"]+)"', html)
            if pc:
                vod["vod_pic"] = self.fix_url(pc.group(1))
            yr = re.search(r'href="/show/[^"]*?year/(\d{4})"', html)
            if yr:
                vod["vod_year"] = yr.group(1)
            ar = re.search(r'href="/show/[^"]*?area/([^"]+)"', html)
            if ar:
                vod["vod_area"] = unquote(ar.group(1))
            rm = re.search(r'备注\s*:\s*([^<]{1,24})', html)
            if rm:
                vod["vod_remarks"] = rm.group(1).strip()
            dr = re.search(r'导演\s*:\s*([^/]{1,60})/', html)
            if dr:
                vod["vod_director"] = dr.group(1).strip()
            ac = re.search(r'演员\s*:\s*([^<]{1,200})', html)
            if ac:
                vod["vod_actor"] = ac.group(1).strip()
            de = re.search(r'id="height_limit"[^>]*>([^<]{10,2000})<', html)
            if de:
                vod["vod_content"] = de.group(1).strip()
            ld = re.search(r'"description"\s*:\s*"([^"]{10,2000})"', html)
            if not vod["vod_content"] and ld:
                vod["vod_content"] = ld.group(1)
        except Exception:
            pass
        # 线路tab标签: swiper-slide 顺序
        tabs = []
        for attrs, body in re.findall(r'<a\b([^>]*)>(.*?)</a>', html, re.S | re.I):
            if 'swiper-slide' not in attrs or not re.search(r'class=["\'][^"\']*\bbadge\b', body):
                continue
            body = re.sub(r'<span\b[^>]*>.*?</span>', '', body, flags=re.S | re.I)
            label = unescape(re.sub(r'<[^>]+>', '', body)).strip()
            if label:
                tabs.append(label)
        # 集链接: href + data-play-sid 为准 (集href自带线路号,勿按tab序配)
        lines = {}
        order = []
        for attrs, body in re.findall(r'<a\b([^>]*)>(.*?)</a>', html, re.S | re.I):
            attributes = {k.lower(): unescape(v) for k, _, v in
                          re.findall(r'([\w-]+)\s*=\s*(["\'])(.*?)\2', attrs, re.S)}
            href = attributes.get('href', '')
            match = re.fullmatch(r'/play/(\d+)-(\d+)(?:-(\d+))?/?', urlsplit(href).path)
            if not match:
                continue
            vid, second, third = match.groups()
            if third:
                sid = second
                pid = '%s-%s-%s' % (vid, sid, third)
            else:
                sid = attributes.get('data-play-sid', '')
                if not sid.isdigit():
                    continue
                pid = '%s-%s?sid=%s' % (vid, second, sid)
            name = attributes.get('data-play-name') or unescape(re.sub(r'<[^>]+>', '', body)).strip()
            if not name:
                name = '第%s集' % (third or second)
            name = name.replace('$', '＄').replace('#', '＃')
            if sid not in lines:
                lines[sid] = []
                order.append(sid)
            lines[sid].append((pid, name))
        froms = []
        urls = []
        for i, ln in enumerate(order):
            nm = tabs[i] if i < len(tabs) else ("线路%d" % (i + 1))
            nm = nm.strip() or ("线路%d" % (i + 1))
            eps = lines[ln]
            seen = set()
            seg = []
            for pid, en in eps:
                if pid in seen:
                    continue
                seen.add(pid)
                seg.append("%s$%s" % (en.strip(), pid))
            froms.append(nm)
            urls.append("#".join(seg))
        vod["vod_play_from"] = "$$$".join(froms)
        vod["vod_play_url"] = "$$$".join(urls)
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        path = "/search/wd/%s" % quote(str(key))
        if pg > 1:
            path += "/page/%d" % pg
        cards = self._cards(self._get(path))
        return {"list": cards, "page": pg,
                "pagecount": pg if len(cards) < 10 else pg + 1,
                "limit": 10, "total": pg * 10}

    def playerContent(self, flag, id, vipFlags=None):
        parts = urlsplit(str(id))
        pid = parts.path
        play_headers = {"User-Agent": self.header["User-Agent"], "Referer": self.host + "/"}
        sid = parse_qs(parts.query).get("sid", [""])[0]
        if re.fullmatch(r"\d+-\d+", pid) and sid.isdigit():
            play_headers["Cookie"] = "mac_play_sid_%s=%s" % (pid.split('-')[0], sid)
        html = self._get("/play/%s" % pid, headers=play_headers)
        url = ""
        frm = ""
        try:
            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*;?\s*</script>', html, re.S)
            if m:
                d = json.loads(re.sub(r',(\s*[}\]]])', r'\1', m.group(1)))
                url = str(d.get("url") or "")
                frm = str(d.get("from") or "")
        except Exception:
            pass
        if not url:
            return {"parse": 1, "playUrl": "", "url": self.host + "/play/" + pid, "jx": 0,
                    "header": play_headers}
        return {"parse": 0, "playUrl": "", "url": url, "jx": 0,
                "header": play_headers}
