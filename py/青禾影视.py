# -*- coding: utf-8 -*-
# 青禾影视 (movie.qhdaohang.cn) 正则解析模式 py源
import sys
import re
import json
import html as html_lib
import requests
from urllib.parse import quote, urljoin

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        self.host = "https://movie.qhdaohang.cn"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.timeout = (8, 20)
        # 分类配置
        self.classes = [
            {"type_id": "20", "type_name": "电影"},
            {"type_id": "37", "type_name": "电视剧"},
            {"type_id": "56", "type_name": "下饭剧"},
            {"type_id": "43", "type_name": "动漫"},
            {"type_id": "45", "type_name": "综艺"},
            {"type_id": "55", "type_name": "短剧"},
            {"type_id": "47", "type_name": "B站"},
        ]
        # 各分类的子类型筛选
        self.sub_types = {
            "20": [("53", "Netflix电影"), ("21", "动作片"), ("22", "喜剧片"), ("23", "爱情片"), ("24", "科幻片"), ("25", "恐怖片"), ("26", "剧情片"), ("27", "战争片"), ("28", "惊悚片"), ("29", "犯罪片"), ("30", "冒险篇"), ("31", "动画片"), ("32", "悬疑片"), ("33", "武侠片"), ("34", "奇幻片"), ("35", "纪录片"), ("36", "其他片")],
            "37": [("54", "Netflix自制剧"), ("38", "国产剧"), ("39", "港台剧"), ("40", "欧美剧"), ("41", "日韩剧"), ("42", "其他剧")],
            "43": [("44", "动漫")],
            "45": [("46", "综艺")],
            "47": [("48", "番剧"), ("49", "国创"), ("50", "电影"), ("51", "电视剧")],
            "56": [("57", "下饭剧"), ("58", "下饭番")],
            "55": [],
        }
        # 地区筛选
        self.areas = [("", "全部"), ("大陆", "大陆"), ("美国", "美国"), ("香港", "香港"), ("台湾", "台湾"), ("日本", "日本"), ("韩国", "韩国"), ("其他", "其他")]
        # 排序筛选
        self.sorts = [("", "最新"), ("hits", "最热"), ("score", "评分")]
        # 年份筛选
        self.years = [("", "全部")] + [(str(y), str(y)) for y in range(2026, 2015, -1)]

    def getName(self):
        return "青禾影视"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|avi|mkv|mov|ts)(\?|$)', url or "", re.I))

    def manualVideoCheck(self):
        return False

    # ---------- 工具函数 ----------
    def get(self, url):
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text if r.status_code == 200 else ""
        except requests.RequestException:
            return ""

    def _pagecount(self, html, page, tid=None, class_id=None):
        links = re.findall(r'href=["\']([^"\']+)["\'][^>]*>(?:下一页|末页|\d+)', html or "", re.I)
        nums = []
        for link in links:
            m = re.search(r'(?:vodtype/[^/-]+-|vodshow/[^-]+(?:-[^-]*)*-)(\d+)\.html$', link)
            if m: nums.append(int(m.group(1)))
        return max([page] + nums)

    def post(self, url, data):
        try:
            r = self.session.post(url, data=data, timeout=self.timeout)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text if r.status_code == 200 else ""
        except requests.RequestException:
            return ""

    def match(self, text, rule):
        m = re.search(rule, text or "", re.S)
        return m.group(1) if m else ""

    def clean(self, text):
        text = html_lib.unescape(re.sub(r"<[^>]+>", "", text or ""))
        return re.sub(r"\s+", " ", text).strip()

    def fix(self, url):
        if not url or str(url).startswith("data:"):
            return ""
        return urljoin(self.host + "/", str(url).strip())

    def _attr(self, block, name):
        m = re.search(r"(?:^|\s)" + re.escape(name) + r"=[\"']([^\"']+)", block, re.I)
        return html_lib.unescape(m.group(1)) if m else ""

    def parseList(self, html):
        """解析 MacCMS 卡片；兼容属性顺序和 src/data-src 懒加载。"""
        res, seen = [], set()
        for m in re.finditer(r'<a\b[^>]*\bhref=["\']([^"\']*?/vodplay/(\d+)-1-1\.html)["\'][^>]*>[\s\S]*?</a>', html or "", re.I):
            block, vid = m.group(0), m.group(2)
            if vid in seen:
                continue
            title = self._attr(block, "title") or self.clean(self.match(block, r'<(?:div|span)[^>]*class=["\'][^"\']*time-titl[^"\']*["\'][^>]*>(.*?)</'))
            img = self._attr(block, "data-src") or self._attr(block, "data-original") or self._attr(block, "src")
            if not title:
                continue
            seen.add(vid)
            res.append({"vod_id": vid, "vod_name": self.clean(title), "vod_pic": self.fix(img),
                        "vod_remarks": self.clean(self.match(block, r'class=["\'][^"\']*public-list-prb[^"\']*["\'][^>]*>(.*?)</span>'))})
        return res

    def _ext(self, extend):
        """解析extend参数为dict"""
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                import json
                return json.loads(extend)
            except Exception:
                return {}
        return {}

    def _filter_url(self, tid, page, ext):
        """根据筛选参数构造URL
        12字段格式: [class, area, sort, '', '', letter, '', '', page, '', '', year]
        """
        class_id = str(ext.get("class") or "").strip()
        area = str(ext.get("area") or "").strip()
        sort = str(ext.get("sort") or "").strip()
        year = str(ext.get("year") or "").strip()

        # 没有选择子类型时，用vodtype URL
        if not class_id:
            if page > 1:
                return self.host + "/vodtype/%s-%d.html" % (tid, page)
            return self.host + "/vodtype/%s.html" % tid

        # 有子类型时，用vodshow URL（12字段）
        fields = [class_id, area, sort, "", "", "", "", "", str(page), "", "", year]
        return self.host + "/vodshow/%s.html" % "-".join(fields)

    # ---------- 标准方法 ----------
    def homeContent(self, filter):
        filters = {}
        for c in self.classes:
            tid = c["type_id"]
            fl = []
            # 类型筛选
            subs = self.sub_types.get(tid, [])
            if subs:
                fl.append({
                    "key": "class",
                    "name": "类型",
                    "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": v} for v, n in subs],
                })
            # 地区筛选
            fl.append({
                "key": "area",
                "name": "地区",
                "value": [{"n": n, "v": v} for v, n in self.areas],
            })
            # 排序筛选
            fl.append({
                "key": "sort",
                "name": "排序",
                "value": [{"n": n, "v": v} for v, n in self.sorts],
            })
            # 年份筛选
            fl.append({
                "key": "year",
                "name": "年份",
                "value": [{"n": n, "v": v} for v, n in self.years],
            })
            filters[tid] = fl
        return {"class": self.classes, "filters": filters}

    def homeVideoContent(self):
        html = self.get(self.host + "/")
        return {"list": self.parseList(html)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(str(pg or "1"))
        except Exception:
            page = 1
        page = max(page, 1)
        ext = self._ext(extend)
        url = self._filter_url(tid, page, ext)
        html = self.get(url)
        lst = self.parseList(html)
        # 只依据当前页的有效分页链接；站点页面一页实际 40 条，未知总数不伪造 total
        pagecount = self._pagecount(html, page, tid, str(ext.get("class") or "").strip())
        return {"page": page, "pagecount": pagecount, "limit": len(lst), "total": 0, "list": lst}

    def detailContent(self, ids):
        vid = str(ids[0])
        html = self.get(self.host + "/voddetail/%s.html" % vid)
        if not html:
            return {"list": []}

        # 标题
        name = self.clean(self.match(html, r'class="[^"]*this-desc-title[^"]*"[^>]*>(.*?)</'))
        if not name:
            name = self.clean(self.match(html, r"<title>[《]?([^《》_|-]+)"))

        # 封面（背景图）
        pic = ""
        bg = re.search(r"background-image:\s*url\(['\"]?(https?://[^'\")]+)['\"]?\)", html)
        if bg:
            pic = bg.group(1)
        if not pic:
            pic = self.fix(self.match(html, r'data-src="([^"]+\.(?:jpg|png|webp))"'))

        # 详情页实际结构为 <em>年份：</em>内容，不能把标签文字放在 </em> 前
        def info(label):
            return self.clean(self.match(html, r'<em[^>]*>\s*' + re.escape(label) + r'[：:]\s*</em>(.*?)(?:</li>|$)'))
        year = info('年份')
        area = info('地区')
        actor = info('主演')
        director = info('导演')
        remarks = info('状态')
        desc = info('简介')

        # 播放线路和剧集列表
        play_from = []
        play_url = []
        eps_areas = re.findall(r'<ul[^>]*class=["\'][^"\']*anthology-list-play[^"\']*["\'][^>]*>([\s\S]*?)</ul>', html, re.I)
        for i, area_html in enumerate(eps_areas):
            eps = []
            for m in re.finditer(r'<a[^>]*href=["\']/vodplay/(\d+)-(\d+)-(\d+)\.html["\'][^>]*>([\s\S]*?)</a>', area_html, re.I):
                item_vid, line, ep = m.group(1), m.group(2), m.group(3)
                title = self.clean(m.group(4)) or ("第%s集" % ep)
                play_path = "/vodplay/%s-%s-%s.html" % (item_vid, line, ep)
                if play_path not in [x.split("$", 1)[-1] for x in eps]:
                    eps.append(title + "$" + play_path)
            if eps:
                play_from.append("线路%d" % (i + 1)); play_url.append("#".join(eps))

        # 如果没找到剧集列表，尝试从播放页链接提取
        if not play_url:
            eps = []
            for m in re.finditer(r'href=["\']/vodplay/(%s)-(\d+)-(\d+)\.html["\'][^>]*>([\s\S]*?)</a>' % re.escape(vid), html, re.I):
                item_vid, line, ep = m.group(1), m.group(2), m.group(3)
                title = self.clean(m.group(4)) or ("第%s集" % ep)
                play_path = "/vodplay/%s-%s-%s.html" % (item_vid, line, ep)
                if play_path not in [e.split("$", 1)[-1] for e in eps]: eps.append(title + "$" + play_path)
            if eps: play_from.append("线路1"); play_url.append("#".join(eps))

        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": remarks,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": desc,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(str(pg or "1"))
        except Exception:
            page = 1
        page = max(page, 1)
        # 搜索用POST
        # MacCMS 搜索分页由 URL 承载，POST 只会固定返回第一页
        if page == 1:
            url = self.host + "/vodsearch/-------------.html"
            html = self.post(url, {"wd": key})
        else:
            url = self.host + "/vodsearch/" + quote(str(key), safe="") + "----------%d---.html" % page
            html = self.get(url)
        return {"list": self.parseList(html), "page": page, "pagecount": self._pagecount(html, page), "limit": 0, "total": 0}

    def playerContent(self, flag, id, vipFlags):
        # id是播放页路径，如 /vodplay/181605-1-1.html
        url = id if str(id).startswith("http") else self.host + str(id)
        html = self.get(url)
        play_url = ""
        # 先提取player_aaaa完整JSON，再取url
        m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S | re.I)
        if m:
            try:
                obj = json.loads(m.group(1))
                play_url = str(obj.get("url") or "").replace("\\/", "/")
            except (ValueError, TypeError):
                um = re.search(r'"url"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', m.group(1))
                if um: play_url = um.group(1).replace("\\/", "/")
        # 降级：直接找带http的url
        if not play_url:
            m = re.search(r'"url"\s*:\s*"(https?:\\?/\\?/[^"]+)"', html)
            if m:
                play_url = m.group(1).replace("\\/", "/")
        # 如果是视频平台链接，需要parse=1
        if play_url and not self.isVideoFormat(play_url):
            return {
                "parse": 1,
                "playUrl": "",
                "url": play_url,
                "header": self.headers,
            }
        return {
            "parse": 0 if play_url else 1,
            "playUrl": "",
            "url": play_url,
            "header": self.headers,
        }

    def localProxy(self, param):
        # 本源不需要代理：站点图片和播放均由宿主直连，拒绝空壳代理。
        return [404, "text/plain", ""]

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass
        return "正在Destroy"
