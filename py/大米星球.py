# -*- coding: utf-8 -*-
import gzip
import html
import io
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zlib

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

class Spider(BaseSpider):
    HOST = "https://dmxq22.com"

    def init(self, extend=""):
        pass

    def _get_ssl_ctx(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _decompress(self, raw_bytes, content_encoding=""):
        if not raw_bytes:
            return ""
        if raw_bytes[:2] == b"\x1f\x8b" or "gzip" in content_encoding.lower():
            try:
                return gzip.GzipFile(fileobj=io.BytesIO(raw_bytes)).read().decode("utf-8", "ignore")
            except Exception:
                pass
        if "deflate" in content_encoding.lower():
            try:
                return zlib.decompress(raw_bytes, -zlib.MAX_WBITS).decode("utf-8", "ignore")
            except Exception:
                try:
                    return zlib.decompress(raw_bytes).decode("utf-8", "ignore")
                except Exception:
                    pass
        try:
            return raw_bytes.decode("utf-8", "ignore")
        except Exception:
            return raw_bytes.decode("gbk", "ignore")

    def _fetch_html(self, url, headers=None):
        if hasattr(self, "fetch"):
            try:
                req_headers = {
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                    "Referer": self.HOST + "/"
                }
                if headers:
                    req_headers.update(headers)
                resp = self.fetch(url, headers=req_headers, timeout=5)
                if resp.status_code == 200:
                    return 200, resp.url, resp.text
            except Exception:
                pass

        req_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.HOST + "/"
        }
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers)
        try:
            res = urllib.request.urlopen(req, context=self._get_ssl_ctx(), timeout=6)
            final_url = res.geturl()
            status_code = res.getcode()
            encoding_header = res.headers.get("Content-Encoding", "")
            raw_data = res.read()
            content = self._decompress(raw_data, encoding_header)
            return status_code, final_url, content
        except Exception as e:
            return 500, url, str(e)

    def homeContent(self, filter):
        result = {}
        classes = [
            {"type_id": "today", "type_name": "今日更新"},
            {"type_id": "netflix", "type_name": "Netflix"},
            {"type_id": "20", "type_name": "电影"},
            {"type_id": "21", "type_name": "电视剧"},
            {"type_id": "22", "type_name": "动漫"},
            {"type_id": "23", "type_name": "综艺"},
            {"type_id": "36", "type_name": "短剧"},
            {"type_id": "35", "type_name": "福利"}
        ]

        common_by = [
            {"n": "全部排序", "v": ""},
            {"n": "时间排序", "v": "time"},
            {"n": "人气排序", "v": "hits"},
            {"n": "评分排序", "v": "score"}
        ]

        area_movie_tv = [
            {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "日本", "v": "日本"},
            {"n": "韩国", "v": "韩国"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"},
            {"n": "德国", "v": "德国"}, {"n": "印度", "v": "印度"}, {"n": "泰国", "v": "泰国"},
            {"n": "丹麦", "v": "丹麦"}, {"n": "瑞典", "v": "瑞典"}, {"n": "巴西", "v": "巴西"},
            {"n": "加拿大", "v": "加拿大"}, {"n": "俄罗斯", "v": "俄罗斯"}, {"n": "意大利", "v": "意大利"},
            {"n": "比利时", "v": "比利时"}, {"n": "爱尔兰", "v": "爱尔兰"}, {"n": "西班牙", "v": "西班牙"},
            {"n": "澳大利亚", "v": "澳大利亚"}
        ]

        lang_movie_tv = [
            {"n": "全部", "v": ""}, {"n": "英语", "v": "英语"}, {"n": "法语", "v": "法语"},
            {"n": "国语", "v": "国语"}, {"n": "粤语", "v": "粤语"}, {"n": "日语", "v": "日语"},
            {"n": "韩语", "v": "韩语"}, {"n": "泰语", "v": "泰语"}, {"n": "德语", "v": "德语"},
            {"n": "俄语", "v": "俄语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "丹麦语", "v": "丹麦语"},
            {"n": "波兰语", "v": "波兰语"}, {"n": "瑞典语", "v": "瑞典语"}, {"n": "印地语", "v": "印地语"},
            {"n": "挪威语", "v": "挪威语"}, {"n": "意大利语", "v": "意大利语"}, {"n": "西班牙语", "v": "西班牙语"}
        ]

        year_list = [
            {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
            {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"},
            {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"},
            {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "2010", "v": "2010"},
            {"n": "2009", "v": "2009"}, {"n": "2008", "v": "2008"}, {"n": "2007", "v": "2007"},
            {"n": "2006", "v": "2006"}, {"n": "2005", "v": "2005"}, {"n": "2004", "v": "2004"},
            {"n": "2003", "v": "2003"}, {"n": "2002", "v": "2002"}, {"n": "2001", "v": "2001"},
            {"n": "2000", "v": "2000"}, {"n": "90年代", "v": "90年代"}, {"n": "80年代", "v": "80年代"},
            {"n": "70年代", "v": "70年代"}, {"n": "更早", "v": "更早"}
        ]

        class_movie = [
            {"n": "全部", "v": ""}, {"n": "Netflix", "v": "Netflix"}, {"n": "仙侠", "v": "仙侠"},
            {"n": "剧情", "v": "剧情"}, {"n": "科幻", "v": "科幻"}, {"n": "动作", "v": "动作"},
            {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "冒险", "v": "冒险"},
            {"n": "儿童", "v": "儿童"}, {"n": "歌舞", "v": "歌舞"}, {"n": "音乐", "v": "音乐"},
            {"n": "奇幻", "v": "奇幻"}, {"n": "动画", "v": "动画"}, {"n": "恐怖", "v": "恐怖"},
            {"n": "惊悚", "v": "惊悚"}, {"n": "丧尸", "v": "丧尸"}, {"n": "战争", "v": "战争"},
            {"n": "传记", "v": "传记"}, {"n": "纪录", "v": "纪录"}, {"n": "犯罪", "v": "犯罪"},
            {"n": "悬疑", "v": "悬疑"}, {"n": "西部", "v": "西部"}, {"n": "灾难", "v": "灾难"},
            {"n": "古装", "v": "古装"}, {"n": "武侠", "v": "武侠"}, {"n": "家庭", "v": "家庭"},
            {"n": "短片", "v": "短片"}, {"n": "校园", "v": "校园"}, {"n": "文艺", "v": "文艺"},
            {"n": "运动", "v": "运动"}, {"n": "青春", "v": "青春"}, {"n": "同性", "v": "同性"},
            {"n": "励志", "v": "励志"}, {"n": "人性", "v": "人性"}, {"n": "美食", "v": "美食"},
            {"n": "女性", "v": "女性"}, {"n": "治愈", "v": "治愈"}, {"n": "历史", "v": "历史"},
            {"n": "真人秀", "v": "真人秀"}, {"n": "脱口秀", "v": "脱口秀"}
        ]

        class_tv = [
            {"n": "全部", "v": ""}, {"n": "Netflix", "v": "Netflix"}, {"n": "短剧", "v": "短剧"},
            {"n": "剧情", "v": "剧情"}, {"n": "网剧", "v": "网剧"}, {"n": "丧尸", "v": "丧尸"},
            {"n": "仙侠", "v": "仙侠"}, {"n": "穿越", "v": "穿越"}, {"n": "惊悚", "v": "惊悚"},
            {"n": "恐怖", "v": "恐怖"}, {"n": "言情", "v": "言情"}, {"n": "科幻", "v": "科幻"},
            {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
            {"n": "偶像", "v": "偶像"}, {"n": "都市", "v": "都市"}, {"n": "军旅", "v": "军旅"},
            {"n": "谍战", "v": "谍战"}, {"n": "罪案", "v": "罪案"}, {"n": "宫廷", "v": "宫廷"},
            {"n": "冒险", "v": "冒险"}, {"n": "儿童", "v": "儿童"}, {"n": "歌舞", "v": "歌舞"},
            {"n": "音乐", "v": "音乐"}, {"n": "奇幻", "v": "奇幻"}, {"n": "动画", "v": "动画"},
            {"n": "战争", "v": "战争"}, {"n": "传记", "v": "传记"}, {"n": "记录", "v": "记录"},
            {"n": "犯罪", "v": "犯罪"}, {"n": "悬疑", "v": "悬疑"}, {"n": "西部", "v": "西部"},
            {"n": "灾难", "v": "灾难"}, {"n": "古装", "v": "古装"}, {"n": "武侠", "v": "武侠"},
            {"n": "家庭", "v": "家庭"}, {"n": "短片", "v": "短片"}, {"n": "校园", "v": "校园"},
            {"n": "文艺", "v": "文艺"}, {"n": "运动", "v": "运动"}, {"n": "青春", "v": "青春"},
            {"n": "同性", "v": "同性"}, {"n": "励志", "v": "励志"}, {"n": "人性", "v": "人性"},
            {"n": "美食", "v": "美食"}, {"n": "女性", "v": "女性"}, {"n": "治愈", "v": "治愈"},
            {"n": "历史", "v": "历史"}, {"n": "真人秀", "v": "真人秀"}, {"n": "脱口秀", "v": "脱口秀"}
        ]

        class_anime = [
            {"n": "全部", "v": ""}, {"n": "Netflix", "v": "Netflix"}, {"n": "热血", "v": "热血"},
            {"n": "科幻", "v": "科幻"}, {"n": "美少女", "v": "美少女"}, {"n": "魔幻", "v": "魔幻"},
            {"n": "经典", "v": "经典"}, {"n": "励志", "v": "励志"}, {"n": "少儿", "v": "少儿"},
            {"n": "冒险", "v": "冒险"}, {"n": "搞笑", "v": "搞笑"}, {"n": "推理", "v": "推理"},
            {"n": "恋爱", "v": "恋爱"}, {"n": "治愈", "v": "治愈"}, {"n": "幻想", "v": "幻想"},
            {"n": "校园", "v": "校园"}, {"n": "动物", "v": "动物"}, {"n": "机战", "v": "机战"},
            {"n": "亲子", "v": "亲子"}, {"n": "儿歌", "v": "儿歌"}, {"n": "运动", "v": "运动"},
            {"n": "悬疑", "v": "悬疑"}, {"n": "怪物", "v": "怪物"}, {"n": "战争", "v": "战争"},
            {"n": "益智", "v": "益智"}, {"n": "青春", "v": "青春"}, {"n": "童话", "v": "童话"},
            {"n": "竞技", "v": "竞技"}, {"n": "动作", "v": "动作"}, {"n": "社会", "v": "社会"},
            {"n": "友情", "v": "友情"}, {"n": "真人版", "v": "真人版"}, {"n": "电影版", "v": "电影版"},
            {"n": "OVA版", "v": "OVA版"}, {"n": "TV版", "v": "TV版"}, {"n": "新番动画", "v": "新番动画"},
            {"n": "完结动画", "v": "完结动画"}
        ]

        class_short = [
            {"n": "全部", "v": ""}, {"n": "古代", "v": "古代"}, {"n": "现代", "v": "现代"},
            {"n": "穿越", "v": "穿越"}, {"n": "玄幻", "v": "玄幻"}, {"n": "霸总", "v": "霸总"},
            {"n": "英雄救美", "v": "英雄救美"}, {"n": "未婚妻", "v": "未婚妻"}, {"n": "师姐", "v": "师姐"},
            {"n": "绝美", "v": "绝美"}, {"n": "逆袭", "v": "逆袭"}, {"n": "幻想", "v": "幻想"},
            {"n": "美女", "v": "美女"}, {"n": "爱情", "v": "爱情"}, {"n": "甜宠", "v": "甜宠"},
            {"n": "虐恋", "v": "虐恋"}, {"n": "爽剧", "v": "爽剧"}, {"n": "搞笑", "v": "搞笑"},
            {"n": "情感", "v": "情感"}, {"n": "动漫", "v": "动漫"}, {"n": "萌宝", "v": "萌宝"},
            {"n": "抖音", "v": "抖音"}, {"n": "快手", "v": "快手"}, {"n": "都市", "v": "都市"},
            {"n": "言情", "v": "言情"}, {"n": "重生", "v": "重生"}, {"n": "乡村", "v": "乡村"},
            {"n": "神医", "v": "神医"}
        ]

        class_zongyi = [
            {"n": "全部", "v": ""}, {"n": "Netflix", "v": "Netflix"}, {"n": "脱口秀", "v": "脱口秀"},
            {"n": "真人秀", "v": "真人秀"}, {"n": "选秀", "v": "选秀"}, {"n": "八卦", "v": "八卦"},
            {"n": "访谈", "v": "访谈"}, {"n": "情感", "v": "情感"}, {"n": "生活", "v": "生活"},
            {"n": "晚会", "v": "晚会"}, {"n": "搞笑", "v": "搞笑"}, {"n": "音乐", "v": "音乐"},
            {"n": "时尚", "v": "时尚"}, {"n": "游戏", "v": "游戏"}, {"n": "少儿", "v": "少儿"},
            {"n": "体育", "v": "体育"}, {"n": "纪实", "v": "纪实"}, {"n": "科教", "v": "科教"},
            {"n": "曲艺", "v": "曲艺"}, {"n": "歌舞", "v": "歌舞"}, {"n": "财经", "v": "财经"},
            {"n": "汽车", "v": "汽车"}, {"n": "播报", "v": "播报"}, {"n": "其他", "v": "其他"}
        ]

        filters = {
            "20": [
                {"key": "class", "name": "剧情", "value": class_movie},
                {"key": "area", "name": "地区", "value": area_movie_tv},
                {"key": "lang", "name": "语言", "value": lang_movie_tv},
                {"key": "year", "name": "年份", "value": year_list},
                {"key": "by", "name": "排序", "value": common_by}
            ],
            "21": [
                {"key": "class", "name": "剧情", "value": class_tv},
                {"key": "area", "name": "地区", "value": area_movie_tv},
                {"key": "lang", "name": "语言", "value": lang_movie_tv},
                {"key": "year", "name": "年份", "value": year_list},
                {"key": "by", "name": "排序", "value": common_by}
            ],
            "22": [
                {"key": "class", "name": "剧情", "value": class_anime},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "日本", "v": "日本"},
                    {"n": "欧美", "v": "欧美"}, {"n": "其他", "v": "其他"}
                ]},
                {"key": "lang", "name": "语言", "value": [
                    {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
                    {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"},
                    {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}
                ]},
                {"key": "year", "name": "年份", "value": year_list},
                {"key": "by", "name": "排序", "value": common_by}
            ],
            "23": [
                {"key": "class", "name": "剧情", "value": class_zongyi},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "韩国", "v": "韩国"},
                    {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"},
                    {"n": "其它", "v": "其它"}
                ]},
                {"key": "lang", "name": "语言", "value": [
                    {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
                    {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"},
                    {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}
                ]},
                {"key": "year", "name": "年份", "value": year_list},
                {"key": "by", "name": "排序", "value": common_by}
            ],
            "36": [
                {"key": "class", "name": "剧情", "value": class_short},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                    {"n": "韩国", "v": "韩国"}, {"n": "美国", "v": "美国"}, {"n": "日本", "v": "日本"},
                    {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"}, {"n": "德国", "v": "德国"},
                    {"n": "台湾", "v": "台湾"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
                    {"n": "其他", "v": "其他"}
                ]},
                {"key": "lang", "name": "语言", "value": [
                    {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
                    {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"},
                    {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}
                ]},
                {"key": "year", "name": "年份", "value": [
                    {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                    {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"},
                    {"n": "2020", "v": "2020"}, {"n": "10年代", "v": "10年代"}, {"n": "00年代", "v": "00年代"},
                    {"n": "90年代", "v": "90年代"}, {"n": "80年代", "v": "80年代"}, {"n": "更早", "v": "更早"}
                ]},
                {"key": "by", "name": "排序", "value": common_by}
            ],
            "35": [
                {"key": "by", "name": "排序", "value": common_by}
            ]
        }

        result["class"] = classes
        result["filters"] = filters
        return result

    def homeVideoContent(self):
        return self.categoryContent("20", "1", False, {})

    def _clean_img_url(self, img_url):
        if not img_url:
            return ""
        raw = html.unescape(img_url.strip())
        final_url = ""

        if "baidu.com" in raw:
            final_url = raw
        else:
            if raw.startswith("//"):
                raw_full = "https:" + raw
            elif raw.startswith("/"):
                raw_full = self.HOST + raw
            else:
                raw_full = raw

            final_url = "https://gimg0.baidu.com/gimg/app=2001&n=0&g=0n&fmt=jpeg&src=" + urllib.parse.quote(raw_full, safe="")

        if final_url.startswith("http://"):
            final_url = "https://" + final_url[7:]

        return final_url

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": int(pg) if pg else 1, "pagecount": 999, "limit": 20, "total": 9999}
        if not extend:
            extend = {}

        c_page = str(pg) if pg else "1"
        c_by = extend.get("by", "")
        c_class = extend.get("class", "")
        c_area = extend.get("area", "")

        url_class = urllib.parse.quote(c_class) if c_class else ""
        url_area = urllib.parse.quote(c_area) if c_area else ""

        if tid == "today":
            req_url = "%s/label/week.html" % self.HOST
        elif tid == "netflix":
            req_url = "%s/vodshow/20---Netflix-----%s---.html" % (self.HOST, c_page)
        else:
            has_sub_filter = bool(url_area or url_class or c_by)
            if not has_sub_filter:
                req_url = "%s/vodshow/%s--------%s---.html" % (self.HOST, tid, c_page)
            else:
                req_url = "%s/vodshow/%s-%s-%s-%s-----%s---.html" % (
                    self.HOST, tid, url_area, c_by, url_class, c_page
                )

        code, final_url, html_text = self._fetch_html(req_url)
        vod_list = []

        anchor_matches = re.findall(
            r'(<a[^>]+href=[\'"][^\'"]*voddetail/(\d+)\.html[\'"][^>]*>[\s\S]*?<img[\s\S]*?</a>)',
            html_text, re.I
        )

        for full_a, vid in anchor_matches:
            name = ""
            a_title = re.search(r'title=[\'"]([^\'"]+)[\'"]', full_a[:full_a.find('>') + 1])
            if a_title:
                t = a_title.group(1).strip()
                if t and t != "大米星球":
                    name = t

            if not name:
                img_alt = re.search(r'<img[^>]+alt=[\'"]([^\'"]+)[\'"]', full_a, re.I)
                if img_alt:
                    t = img_alt.group(1).strip()
                    if t and t != "大米星球":
                        name = t

            if not name or name == "大米星球":
                continue

            pic = ""
            for pat in [r'data-original=[\'"]([^\'"]+)[\'"]', r'data-src=[\'"]([^\'"]+)[\'"]', r'src=[\'"]([^\'"]+)[\'"]']:
                img_m = re.search(pat, full_a, re.I)
                if img_m:
                    raw_p = img_m.group(1).strip()
                    if not any(x in raw_p.lower() for x in ["loading", "load.gif", "icon.png", "frosted.png", "colour-bg", "logo"]):
                        pic = self._clean_img_url(raw_p)
                        break

            rem_m = re.search(r'<span[^>]*>([\s\S]*?)</span>', full_a)
            raw_rem = re.sub(r'<[^>]+>', '', rem_m.group(1)).strip() if rem_m else ""
            remarks = "蝴蝶影视 | %s" % raw_rem if raw_rem else "蝴蝶影视"

            vod_list.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks
            })

        seen = set()
        clean_list = []
        for item in vod_list:
            if item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                clean_list.append(item)

        result["list"] = clean_list
        return result

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        detail_url = "%s/voddetail/%s.html" % (self.HOST, vod_id)
        code, final_url, html_text = self._fetch_html(detail_url)

        title_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html_text, re.I)
        vod_name = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ""

        pic_m = re.search(r'class=[\'"][^\'"]*detail-pic[\'"][\s\S]*?<img[^>]+src=[\'"]([^\'"]+)[\'"]', html_text, re.I)
        if not pic_m:
            pic_m = re.search(r'<img[^>]+class=[\'"][^\'"]*lazy[^\'"]*[\'"][^>]+data-original=[\'"]([^\'"]+)[\'"]', html_text, re.I)
        vod_pic = self._clean_img_url(pic_m.group(1).strip()) if pic_m else ""

        desc_m = re.search(r'<div[^>]+class=[\'"][^\'"]*content[^\'"]*[\'"][^>]*>([\s\S]*?)</div>', html_text, re.I)
        desc = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip() if desc_m else ""

        tab_names = re.findall(r'<div[^>]+class=[\'"][^\'"]*module-tab-item[^\'"]*[\'"][^>]*>[\s\S]*?<span>([\s\S]*?)</span>', html_text, re.I)
        if not tab_names:
            tab_names = re.findall(r'<a[^>]+data-toggle=[\'"]tab[\'"][^>]*>([\s\S]*?)</a>', html_text, re.I)

        play_lists = re.findall(r'<div[^>]+class=[\'"][^\'"]*module-play-list[^\'"]*[\'"]>([\s\S]*?)</div>', html_text, re.I)
        if not play_lists:
            play_lists = re.findall(r'<ul[^>]+class=[\'"][^\'"]*playlist[^\'"]*[\'"]>([\s\S]*?)</ul>', html_text, re.I)

        play_from = []
        play_url = []

        if play_lists:
            for i, p_list_html in enumerate(play_lists):
                t_name = tab_names[i].strip() if i < len(tab_names) else ("线路%d" % (i + 1))
                t_name = re.sub(r'<[^>]+>', '', t_name).strip()
                ep_matches = re.findall(r'<a[^>]+href=[\'"]([^\'"]*vodplay/(\d+-\d+-\d+)\.html)[\'"][^>]*>[\s\S]*?<span>([\s\S]*?)</span>', p_list_html, re.I)
                if not ep_matches:
                    ep_matches = re.findall(r'<a[^>]+href=[\'"]([^\'"]*vodplay/(\d+-\d+-\d+)\.html)[\'"][^>]*>([\s\S]*?)</a>', p_list_html, re.I)

                ep_strs = []
                for ep_href, ep_id, ep_title in ep_matches:
                    ep_name = re.sub(r'<[^>]+>', '', ep_title).strip()
                    ep_strs.append("%s$%s" % (ep_name, ep_id))

                if ep_strs:
                    play_from.append(t_name if t_name else ("大米星球%d" % (i + 1)))
                    play_url.append("#".join(ep_strs))

        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_bg": vod_pic,
            "vod_background": vod_pic,
            "type_name": "蝴蝶专区",
            "vod_year": "2026",
            "vod_area": "大米",
            "vod_remarks": "蝴蝶影视",
            "vod_actor": "🦋 TG群: @tvshare23",
            "vod_director": "🦋 蝴蝶影视",
            "vod_content": "🦋 官方频道: @tvshare23\n" + desc,
            "vod_play_from": "$$$".join(play_from) if play_from else "大米星球",
            "vod_play_url": "$$$".join(play_url) if play_url else "正片$1"
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_page_url = "%s/vodplay/%s.html" % (self.HOST, id)
        code, final_url, html_text = self._fetch_html(play_page_url)

        real_url = ""
        parse_flag = 0

        # 精准正则闭合匹配：杜绝 Extra data 导致 json.loads 崩溃
        url_match = re.search(r'var\s+player_aaaa\s*=\s*\{[\s\S]*?["\']url["\']\s*:\s*["\']([^"\']+)["\']', html_text)
        if url_match:
            real_url = url_match.group(1).strip()
            # 兼容去除 JSON 转义斜杠
            real_url = real_url.replace("\\/", "/")
            encrypt_m = re.search(r'["\']encrypt["\']\s*:\s*(\d+)', html_text)
            if encrypt_m:
                enc = encrypt_m.group(1)
                if enc == "1":
                    real_url = urllib.parse.unquote(real_url)
                elif enc == "2":
                    try:
                        import base64
                        real_url = base64.b64decode(real_url).decode("utf-8", "ignore")
                    except Exception:
                        pass
        else:
            player_json_m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\});', html_text)
            if player_json_m:
                try:
                    p_data = json.loads(player_json_m.group(1))
                    real_url = p_data.get("url", "").replace("\\/", "/")
                except Exception:
                    pass

        if real_url and any(x in real_url.lower() for x in [".m3u8", ".mp4", ".flv"]):
            parse_flag = 0
            # 协议降级：针对自签名/证书过期的切片 CDN 降级为 HTTP，避开 iOS TLS SecTrust 拦截
            bad_ssl_domains = ["rrcdnbf2.com", "ifznedy1.com", "m3u8.tv"]
            if any(dom in real_url.lower() for dom in bad_ssl_domains):
                if real_url.startswith("https://"):
                    real_url = "http://" + real_url[8:]

            if ".m3u8" not in real_url.lower():
                sep = "&" if "?" in real_url else "?"
                real_url = real_url + sep + "format=.m3u8"
        else:
            parse_flag = 1

        return {
            "parse": parse_flag,
            "playUrl": "",
            "url": real_url if real_url else play_page_url,
            "header": {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
                "Referer": self.HOST + "/"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        result = {"list": []}
        c_page = str(pg) if pg else "1"
        enc_key = urllib.parse.quote(key)
        search_url = "%s/vodsearch/%s----------%s---.html" % (self.HOST, enc_key, c_page)
        code, final_url, html_text = self._fetch_html(search_url)

        anchor_matches = re.findall(
            r'(<a[^>]+href=[\'"][^\'"]*voddetail/(\d+)\.html[\'"][^>]*>[\s\S]*?<img[\s\S]*?</a>)',
            html_text, re.I
        )

        vod_list = []
        for full_a, vid in anchor_matches:
            name = ""
            a_title = re.search(r'title=[\'"]([^\'"]+)[\'"]', full_a[:full_a.find('>') + 1])
            if a_title:
                t = a_title.group(1).strip()
                if t and t != "大米星球":
                    name = t

            if not name:
                img_alt = re.search(r'<img[^>]+alt=[\'"]([^\'"]+)[\'"]', full_a, re.I)
                if img_alt:
                    t = img_alt.group(1).strip()
                    if t and t != "大米星球":
                        name = t

            if not name or name == "大米星球":
                continue

            pic = ""
            for pat in [r'data-original=[\'"]([^\'"]+)[\'"]', r'data-src=[\'"]([^\'"]+)[\'"]', r'src=[\'"]([^\'"]+)[\'"]']:
                img_m = re.search(pat, full_a, re.I)
                if img_m:
                    raw_p = img_m.group(1).strip()
                    if not any(x in raw_p.lower() for x in ["loading", "load.gif", "icon.png", "frosted.png", "colour-bg", "logo"]):
                        pic = self._clean_img_url(raw_p)
                        break

            rem_m = re.search(r'<span[^>]*>([\s\S]*?)</span>', full_a)
            raw_rem = re.sub(r'<[^>]+>', '', rem_m.group(1)).strip() if rem_m else ""
            remarks = "蝴蝶影视 | %s" % raw_rem if raw_rem else "蝴蝶影视"

            vod_list.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks
            })

        seen = set()
        clean_list = []
        for item in vod_list:
            if item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                clean_list.append(item)

        result["list"] = clean_list
        return result

    def action(self, action):
        return None

    def liveContent(self):
        return {}

    def localProxy(self, params):
        return [200, "text/plain", ""]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass