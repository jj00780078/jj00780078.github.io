#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://www.kuaigan47.top"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self.catIdMap = {
            "chuanmei": "454"
        }

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getName(self):
        return "快感研究所"

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "top_banner", "55287.mp4", "native-ad", "stat.php")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", "streamhls", "master.m3u8", ".flv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _fetch(self, target_url, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "bytes": raw, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "bytes": b"", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": last_err, "final_url": target_url}

    def _get_category_id(self, slug):
        if slug in self.catIdMap:
            return self.catIdMap[slug]
        cat_page_url = "%s/category/%s/" % (self.siteUrl, slug)
        res = self._fetch(cat_page_url)
        html = res.get("text", "")
        m = re.search(r'data-category-id=["\'](\d+)["\']', html)
        if m:
            cat_id = m.group(1).strip()
            self.catIdMap[slug] = cat_id
            return cat_id
        return ""

    def _build_filter_group(self, key_name, label_name, tags_list):
        opts = [{"n": "全部", "v": ""}]
        for t in tags_list:
            opts.append({"n": t, "v": t})
        return {
            "key": key_name,
            "name": label_name,
            "init": "",
            "value": opts
        }

    def homeContent(self, filter):
        classes = [
            {"type_name": "国产传媒", "type_id": "chuanmei"},
            {"type_name": "探花交友", "type_id": "tanhua"},
            {"type_name": "网曝黑料", "type_id": "heiliao"},
            {"type_name": "绿帽出轨", "type_id": "lvmao"},
            {"type_name": "国产乱伦", "type_id": "gcluanlun"},
            {"type_name": "主播自拍", "type_id": "zhubo"},
            {"type_name": "户外露出", "type_id": "huwai"},
            {"type_name": "福利姬", "type_id": "fuliji"},
            {"type_name": "中文字幕", "type_id": "zhongwen"},
            {"type_name": "无码破解", "type_id": "wuma"},
            {"type_name": "熟女人妻", "type_id": "renqi"},
            {"type_name": "巨乳美乳", "type_id": "juru"},
            {"type_name": "少女萝莉", "type_id": "luoli"},
            {"type_name": "强奸乱伦", "type_id": "qiangjian"},
            {"type_name": "SM调教", "type_id": "smtiaojiao"},
            {"type_name": "VR视角", "type_id": "vr"},
            {"type_name": "剧情演绎", "type_id": "juqing"},
            {"type_name": "制服诱惑", "type_id": "zhifu"},
            {"type_name": "欧美视频", "type_id": "oumei"},
            {"type_name": "成人动漫", "type_id": "dongman"},
            {"type_name": "三级伦理", "type_id": "lunli"},
            {"type_name": "AI换脸", "type_id": "huanlian"},
            {"type_name": "AV解说", "type_id": "jieshuo"},
            {"type_name": "女同性恋", "type_id": "nvtong"}
        ]

        filters = {}
        if filter:
            role_tags = [
                "探花", "学生", "人妻", "老师", "少妇", "阿姨", "学妹", "护士", "空姐", "校花",
                "姐姐", "女友", "主播", "技师", "足浴店", "妈妈", "闺蜜", "老婆", "同事", "处女",
                "母子", "兄妹", "父女", "熟女", "萝莉", "少女", "妹妹", "女上司", "按摩师", "女神",
                "秘书", "美容师", "后妈", "丈母娘", "儿媳", "女仆", "兔女郎", "外围", "楼凤", "绿茶",
                "厂妹", "模特", "嫩模", "保姆", "辅导员", "伴娘"
            ]
            action_tags = [
                "乱伦", "调教", "绿帽", "偷情", "勾引", "乳交", "内射", "颜射", "口爆", "双飞",
                "强推", "吞精", "出轨", "多p", "深喉", "自慰", "打飞机", "嫖娼", "失禁", "足交",
                "露出", "户外", "偷拍", "野战", "约炮", "面试", "潜规则", "强制", "按摩", "骑乘",
                "3p", "口交", "淫语", "凌辱", "跳蛋", "轮奸", "潮吹", "羞耻", "迷奸", "下药",
                "灌醉", "仙人跳", "绿奴", "字母圈", "冰火", "毒龙", "门事件", "裸贷", "磕炮", "连麦"
            ]
            body_tags = [
                "巨乳", "长腿", "美乳", "丰满", "大奶", "大屁股", "蜜桃臀", "娇小", "翘臀", "苗条",
                "白嫩", "微胖", "高挑", "粉嫩", "肥臀", "紧致", "平乳", "爆乳", "e奶", "美臀",
                "巨臀", "孕妇", "无毛", "一线天", "名器", "极品", "骨感", "水多", "紧逼", "黑木耳",
                "蝴蝶唇", "白虎", "反差"
            ]
            cloth_tags = [
                "黑丝", "JK", "眼镜", "丝袜", "蕾丝", "女仆", "白丝", "双马尾", "肉丝", "高跟",
                "瑜伽裤", "短裙", "免脱", "兔女郎", "紧身裤", "包臀裙", "开档", "吊带袜", "丁字裤", "情趣内衣",
                "校服", "内裤", "紧身裙", "泳装", "迷你裙", "长靴", "制服", "旗袍", "运动服", "汉服",
                "厂服", "护士服", "空姐服", "吊带", "网袜", "渔网袜", "职业装", "睡衣", "肚兜"
            ]
            scene_tags = [
                "酒店", "浴室", "车载", "教室", "办公室", "厕所", "电梯", "公园", "电影院", "宿舍",
                "医院", "阳台", "公交车", "地铁", "更衣室", "出租屋", "宾馆", "民宿", "车震", "野外",
                "楼梯间", "KTV", "会所", "洗浴中心", "按摩店", "试衣间", "网吧", "厂房", "库房", "厨房"
            ]

            filter_template = [
                {
                    "key": "sort",
                    "name": "排序",
                    "init": "latest",
                    "value": [{"n": "最新", "v": "latest"}, {"n": "热门", "v": "daily"}]
                },
                self._build_filter_group("role", "角色", role_tags),
                self._build_filter_group("action", "行为", action_tags),
                self._build_filter_group("body", "身材", body_tags),
                self._build_filter_group("cloth", "服饰", cloth_tags),
                self._build_filter_group("scene", "场景", scene_tags)
            ]

            for c in classes:
                filters[c["type_id"]] = filter_template

        result = {"class": classes}
        if filter:
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        slug = str(tid).strip("/")
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1

        ext = extend or {}
        sort = ext.get("sort", "latest")
        if not sort:
            sort = "latest"

        active_tags = []
        for tag_key in ("role", "action", "body", "cloth", "scene"):
            v = ext.get(tag_key, "").strip()
            if v:
                active_tags.append(v)

        cat_id = self._get_category_id(slug)
        if not cat_id:
            return {"page": page, "pagecount": page, "limit": 20, "total": 0, "list": []}

        api_url = "%s/factory/api/category.php?id=%s&field=category_id&sort=%s&page=%s" % (
            self.siteUrl, cat_id, quote(sort), page
        )
        for t in active_tags:
            api_url += "&tags[]=" + quote(t)

        res = self._fetch(api_url, referer="%s/category/%s/" % (self.siteUrl, slug))
        
        cards = []
        pagecount = page
        total = 0

        try:
            data_json = json.loads(res.get("text", ""))
            if data_json.get("status") == "success":
                raw_list = data_json.get("data", [])
                pagination = data_json.get("pagination", {})
                total = int(pagination.get("totalHits", 0))
                limit = int(pagination.get("limit", 20))
                pagecount = (total + limit - 1) // limit if limit > 0 else 1

                for item in raw_list:
                    raw_url = item.get("url", "")
                    title = item.get("title", "")
                    cover = item.get("cover_image_url", "")
                    if cover and cover.startswith("//"):
                        cover = "https:" + cover
                    elif cover and cover.startswith("/"):
                        cover = self.siteUrl + cover

                    cards.append({
                        "vod_id": raw_url,
                        "vod_name": html_lib.unescape(title),
                        "vod_pic": cover,
                        "vod_remarks": format_remarks("蝴蝶影视", "正片"),
                        "style": {"type": "rect", "ratio": 1.78}
                    })
        except Exception:
            pass

        return {
            "page": page,
            "pagecount": max(1, pagecount),
            "limit": 20,
            "total": total,
            "list": cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        detail_url = raw_id
        if not detail_url.startswith("http"):
            detail_url = self.siteUrl + ("" if detail_url.startswith("/") else "/") + detail_url

        res = self._fetch(detail_url)
        detail_html = res.get("text", "")

        t_m = re.search(r"<title>(.*?)</title>", detail_html, re.I | re.S)
        title = t_m.group(1).strip() if t_m else "超清正片"
        if " - 快感研究所" in title:
            title = title.replace(" - 快感研究所", "").strip()

        m3u8_links = re.findall(r'https?://(?:(?!localhost|127\.0\.0\.1)[^\s"\'\$<>])+\.m3u8[^\s"\'\$<>]*', detail_html)
        mp4_links = re.findall(r'https?://(?:(?!localhost|127\.0\.0\.1)[^\s"\'\$<>])+\.mp4[^\s"\'<>]*', detail_html)

        play_url = ""
        if m3u8_links:
            real_m3u8 = m3u8_links[0].replace("\\u002F", "/").replace("\\/", "/")
            if ".m3u8" not in real_m3u8.lower():
                sep = "&" if "?" in real_m3u8 else "?"
                real_m3u8 = real_m3u8 + sep + "format=.m3u8"
            play_url = "超清正片$%s" % real_m3u8
        elif mp4_links:
            play_url = "超清正片$%s" % mp4_links[0]
        else:
            iframe_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', detail_html, re.I)
            if iframe_m:
                cand = iframe_m.group(1).strip()
                if cand.startswith("//"):
                    cand = "https:" + cand
                elif not cand.startswith("http"):
                    cand = urllib.parse.urljoin(self.siteUrl, cand)
                play_url = "解析播放$%s" % cand
            else:
                play_url = "直链直出$%s" % detail_url

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": title,
                "vod_pic": "",
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": format_remarks("蝴蝶影视", "正片"),
                "vod_content": "🦋 蝴蝶影视专线直连 | 4K原生超清秒播 | 官方交流群: @tvshare23",
                "vod_play_from": "蝴蝶专线",
                "vod_play_url": play_url
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }
        return {
            "parse": 0 if (".m3u8" in url or ".mp4" in url) else 1,
            "playUrl": "",
            "url": url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1

        search_url = "%s/search.php?q=%s" % (self.siteUrl, quote(key))
        res = self._fetch(search_url)
        html = res.get("text", "")

        cat_id_m = re.search(r'data-category-id=["\'](\d+)["\']', html)
        cat_id = cat_id_m.group(1).strip() if cat_id_m else "1"

        api_url = "%s/factory/api/category.php?id=%s&field=search&keyword=%s&page=%s" % (
            self.siteUrl, cat_id, quote(key), page
        )
        api_res = self._fetch(api_url, referer=search_url)

        cards = []
        try:
            data_json = json.loads(api_res.get("text", ""))
            if data_json.get("status") == "success":
                for item in data_json.get("data", []):
                    cover = item.get("cover_image_url", "")
                    if cover and cover.startswith("//"):
                        cover = "https:" + cover
                    elif cover and cover.startswith("/"):
                        cover = self.siteUrl + cover

                    cards.append({
                        "vod_id": item.get("url", ""),
                        "vod_name": html_lib.unescape(item.get("title", "")),
                        "vod_pic": cover,
                        "vod_remarks": format_remarks("蝴蝶影视", "正片"),
                        "style": {"type": "rect", "ratio": 1.78}
                    })
        except Exception:
            pass

        return {
            "page": page,
            "pagecount": page if not cards else page + 1,
            "limit": 20,
            "total": len(cards),
            "list": cards
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]