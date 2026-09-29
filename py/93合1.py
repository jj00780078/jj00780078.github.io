#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🦋 一锅端·12站实测固化版 — 遮天契约修复版
修复项：
  - 补 getDependence()
  - localProxy 返回四元组 [status, mime, body, header]
  - localProxy param 兼容 str/dict
  - 保持可无参实例化 / 可选 base.spider 降级
后端：https://av.telstra.com.cv 聚合 API
"""
import sys
import os
import re
import json
import base64
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

# ==============================================================
# 全量源站分类数据字典 (12 站实测更新 + 原始库全量保留，已剔除 avgood/baogua/nuomi)
# ==============================================================
SITES_CONFIG_DATA = {
    # --- 阶段一与二：已实测打通的核心 6 站 ---
    "asmrhoney": {"name": "ASMRHoney", "platform": "adult", "categories": [{"n": "最新更新", "v": "latest"}, {"n": "中文ASMR", "v": "lang_zh"}, {"n": "日语ASMR", "v": "lang_ja"}, {"n": "韩语ASMR", "v": "lang_ko"}, {"n": "英语ASMR", "v": "lang_en"}, {"n": "混合语言", "v": "lang_mixed"}, {"n": "舔耳", "v": "tag_ear_licking"}, {"n": "口腔音", "v": "tag_mouth_sounds"}, {"n": "触发音", "v": "tag_trigger_sounds"}, {"n": "角色扮演", "v": "tag_roleplay"}, {"n": "耳语", "v": "tag_whisper"}, {"n": "丝袜", "v": "tag_pantyhose"}, {"n": "刮擦", "v": "tag_scratching"}, {"n": "性感", "v": "tag_sexy"}, {"n": "SFW全年龄", "v": "tag_sfw"}, {"n": "NSFW", "v": "tag_nsfw"}, {"n": "耳吃", "v": "tag_eareating"}, {"n": "舌头", "v": "tag_tongue"}, {"n": "助眠", "v": "tag_sleep_aid"}, {"n": "呼吸音", "v": "tag_breathing"}, {"n": "足部", "v": "tag_feet"}, {"n": "亲吻", "v": "tag_kiss"}, {"n": "音频专辑", "v": "audio_albums"}, {"n": "音频单曲", "v": "audio_tracks"}]},
    "avxq": {"name": "AV星球", "platform": "adult", "categories": [{"n": "学生萝莉", "v": "66"}, {"n": "日本AV", "v": "44"}, {"n": "口交自慰", "v": "62"}, {"n": "群交多P", "v": "63"}, {"n": "强奸迷奸", "v": "67"}, {"n": "丝袜制服", "v": "68"}, {"n": "国产AV", "v": "46"}, {"n": "乱伦系列", "v": "45"}, {"n": "素人特摄", "v": "65"}, {"n": "探花约炮", "v": "47"}, {"n": "日韩精选", "v": "61"}, {"n": "VR专区", "v": "64"}, {"n": "主播大秀", "v": "48"}, {"n": "反差母狗", "v": "70"}, {"n": "国产传媒", "v": "50"}, {"n": "网曝吃瓜", "v": "49"}, {"n": "异域风情", "v": "71"}, {"n": "中文字幕", "v": "53"}, {"n": "偷拍偷窥", "v": "51"}, {"n": "色情动漫", "v": "55"}]},
    "b8xx6": {"name": "8XX6", "platform": "adult", "categories": [{"n": "国产", "v": "901179"}, {"n": "有码", "v": "911179"}, {"n": "无码", "v": "921179"}, {"n": "欧美", "v": "931179"}, {"n": "传媒", "v": "941179"}, {"n": "探花", "v": "951179"}, {"n": "中文", "v": "961179"}, {"n": "动漫", "v": "971179"}]},
    "cj": {"name": "初8影视", "platform": "drama", "categories": [{"n": "电影", "v": "1"}, {"n": "剧集", "v": "15"}, {"n": "动漫", "v": "30"}, {"n": "短剧", "v": "47"}, {"n": "综艺", "v": "24"}, {"n": "纪录片", "v": "63"}]},
    "imaoyou": {"name": "猫又影视", "platform": "drama", "categories": [{"n": "电影", "v": "1"}, {"n": "电视剧", "v": "2"}, {"n": "综艺", "v": "3"}, {"n": "动漫", "v": "4"}, {"n": "短剧", "v": "5"}]},
    "iyf": {"name": "爱壹帆影视", "platform": "drama", "categories": [{"n": "电影", "v": "1"}, {"n": "电视剧", "v": "2"}, {"n": "综艺", "v": "3"}, {"n": "动漫", "v": "4"}, {"n": "纪录片", "v": "5"}]},

    # --- 阶段三：实测打通的短剧与音频 6 站 ---
    "djuu": {"name": "DJ呦呦", "platform": "audio", "categories": [{"n": "热歌榜", "v": "1"}, {"n": "DJ舞曲", "v": "2"}, {"n": "英文DJ", "v": "3"}, {"n": "中文DJ", "v": "4"}]},
    "huangdou": {"name": "黄豆短剧", "platform": "short", "categories": [{"n": "全部短剧", "v": "all"}, {"n": "黄豆原创", "v": "yuandou"}, {"n": "魔改短剧", "v": "mod"}, {"n": "擦边短剧", "v": "caibian"}, {"n": "真人短剧", "v": "zhenren"}, {"n": "动漫", "v": "erciyuan"}, {"n": "影院", "v": "aiman"}, {"n": "贤者", "v": "zongyi"}, {"n": "黑料", "v": "heiliao"}]},
    "kuangbiao": {"name": "狂飙短剧", "platform": "short", "categories": [{"n": "成人短剧", "v": "adult_short"}, {"n": "正规短剧", "v": "normal_short"}, {"n": "短剧", "v": "t-5jxcit"}]},
    "xifu": {"name": "喜福短剧", "platform": "short", "categories": [{"n": "爽剧", "v": "3"}, {"n": "甜宠", "v": "6"}, {"n": "逆袭", "v": "5"}, {"n": "现代言情", "v": "1"}, {"n": "都市", "v": "4"}, {"n": "玄幻", "v": "23"}, {"n": "古代言情", "v": "16"}]},
    "xingya": {"name": "星芽短剧", "platform": "short", "categories": [{"n": "剧场", "v": "1"}, {"n": "新剧", "v": "3"}, {"n": "热播", "v": "2"}, {"n": "星选", "v": "7"}, {"n": "阳光", "v": "5"}]},
    "yidouge": {"name": "一兜糖短剧", "platform": "short", "categories": [{"n": "最新发布", "v": "1"}, {"n": "热播精选", "v": "2"}]},

    # --- 其余完整保留的备用站点库 ---
    "avtoday": {"name": "AVToday", "platform": "adult", "categories": [{"n": "中文字幕", "v": "中文字幕"}, {"n": "無碼", "v": "無碼"}, {"n": "FC2", "v": "FC2"}, {"n": "長腿", "v": "長腿"}, {"n": "巨乳", "v": "巨乳"}, {"n": "多人", "v": "多人"}, {"n": "素人", "v": "素人"}]},
    "hanime1": {"name": "hanime1动漫(源超时)", "platform": "anime", "categories": [{"n": "首页推荐", "v": "home"}, {"n": "最新", "v": "latest"}]},
    "jable": {"name": "Jable直播放", "platform": "adult", "categories": [{"n": "最近更新", "v": "latest-updates"}, {"n": "热门影片", "v": "hot"}, {"n": "最新上市", "v": "new-release"}, {"n": "中文字幕", "v": "chinese-subtitle"}, {"n": "角色剧情", "v": "roleplay"}, {"n": "制服诱惑", "v": "uniform"}, {"n": "丝袜美腿", "v": "pantyhose"}, {"n": "无码解放", "v": "uncensored"}]},
    "missav": {"name": "MissAV", "platform": "adult", "categories": [{"n": "国产", "v": "20"}, {"n": "日本有码", "v": "21"}, {"n": "日本无码", "v": "22"}, {"n": "中文字幕", "v": "28"}, {"n": "欧美", "v": "23"}, {"n": "动漫", "v": "24"}, {"n": "伦理", "v": "25"}]},
    "91porn": {"name": "91Porn", "platform": "adult", "categories": [{"n": "最新", "v": "watch"}, {"n": "91原创", "v": "ori"}, {"n": "当前最热", "v": "hot"}, {"n": "本月最热", "v": "top"}, {"n": "10分钟以上", "v": "long"}, {"n": "高清", "v": "hd"}]},
    "baxx": {"name": "8X8X", "platform": "adult", "categories": [{"n": "大陆", "v": "1"}, {"n": "日韩", "v": "2"}, {"n": "欧美", "v": "3"}, {"n": "动漫", "v": "4"}, {"n": "三级", "v": "5"}]},
    "chinax": {"name": "中国X站", "platform": "adult", "categories": [{"n": "国产传媒", "v": "domestic-media"}, {"n": "日本AV", "v": "japanese-av"}, {"n": "无码视频", "v": "uncensored-video"}, {"n": "中文字幕", "v": "chinese-subtitles"}]},
    "ddys": {"name": "高端视频", "platform": "adult", "categories": [{"n": "一区-日韩无码", "v": "12028759"}, {"n": "一区-中文字幕", "v": "12198759"}, {"n": "一区-国产自拍", "v": "12008759"}, {"n": "二区-91探花", "v": "12468839"}, {"n": "三区-国产精品", "v": "12038769"}]},
    "flt": {"name": "福利天堂", "platform": "adult", "categories": [{"n": "偷拍", "v": "1"}, {"n": "国产", "v": "6"}, {"n": "韩国", "v": "3"}, {"n": "无码", "v": "4"}, {"n": "动漫", "v": "5"}, {"n": "中文", "v": "7"}]},
    "tnaflix": {"name": "TNAFlix", "platform": "adult", "categories": [{"n": "最新视频", "v": "1"}, {"n": "Asian 亚洲", "v": "5"}, {"n": "Japanese 日本", "v": "34"}, {"n": "Hentai 动漫", "v": "30"}, {"n": "Homemade 自拍", "v": "31"}]},
    "youav": {"name": "YouAV", "platform": "adult", "categories": [{"n": "日本AV", "v": "22"}, {"n": "巨乳", "v": "20"}, {"n": "熟女人妻", "v": "21"}, {"n": "中文字幕", "v": "23"}, {"n": "少女蘿莉", "v": "24"}, {"n": "國產素人自拍", "v": "30"}]},
    "apilj": {"name": "辣椒资源", "platform": "adult", "categories": [{"n": "国产自拍", "v": "1"}, {"n": "欧美极品", "v": "2"}, {"n": "日韩无码", "v": "3"}, {"n": "AV明星", "v": "4"}, {"n": "中文字幕", "v": "20"}]},
    "fhzy": {"name": "番号资源", "platform": "adult", "categories": [{"n": "制服丝袜", "v": "1"}, {"n": "群交淫乱", "v": "2"}, {"n": "无码专区", "v": "3"}, {"n": "偷拍自拍", "v": "4"}, {"n": "中文字幕", "v": "6"}]},
    "jpzy": {"name": "极品资源", "platform": "adult", "categories": [{"n": "视频一区", "v": "1"}, {"n": "日韩无码", "v": "54"}, {"n": "国产精品", "v": "55"}, {"n": "自拍偷拍", "v": "60"}, {"n": "中文字幕", "v": "62"}]},
    "91md": {"name": "91麻豆", "platform": "adult", "categories": [{"n": "麻豆视频", "v": "1"}, {"n": "91制片厂", "v": "2"}, {"n": "天美传媒", "v": "3"}, {"n": "蜜桃传媒", "v": "4"}, {"n": "星空传媒", "v": "6"}]},
    "aosika": {"name": "奥斯卡资源", "platform": "adult", "categories": [{"n": "国产视频", "v": "20"}, {"n": "中文字幕", "v": "21"}, {"n": "国产传媒", "v": "22"}, {"n": "日本有码", "v": "23"}, {"n": "日本无码", "v": "24"}]},
    "ddzy": {"name": "滴滴资源", "platform": "adult", "categories": [{"n": "国产专区", "v": "20"}, {"n": "国产厂商", "v": "21"}, {"n": "日本无码", "v": "23"}, {"n": "中文字幕", "v": "25"}]},
    "douzy": {"name": "豆豆资源", "platform": "adult", "categories": [{"n": "国产视频", "v": "47"}, {"n": "国产传媒", "v": "48"}, {"n": "日本有码", "v": "53"}, {"n": "少妇人妻", "v": "74"}]},
    "heizy": {"name": "嘿嘿资源", "platform": "adult", "categories": [{"n": "国产视频", "v": "48"}, {"n": "国产自拍", "v": "49"}, {"n": "黑料吃瓜", "v": "54"}, {"n": "麻豆传媒", "v": "56"}]},
    "souav": {"name": "搜av资源", "platform": "adult", "categories": [{"n": "中文传媒", "v": "1"}, {"n": "国产", "v": "2"}, {"n": "欧美AV", "v": "3"}, {"n": "日本AV", "v": "4"}, {"n": "传媒-麻豆传媒", "v": "6"}]},
    "danaizi": {"name": "大奶子资源", "platform": "adult", "categories": [{"n": "视频一区", "v": "1"}, {"n": "精品推荐", "v": "20"}, {"n": "自拍偷拍", "v": "23"}, {"n": "制服丝袜", "v": "24"}]},
    "lsb": {"name": "老色逼资源", "platform": "adult", "categories": [{"n": "精品推荐", "v": "20"}, {"n": "国产精品", "v": "21"}, {"n": "日本有码", "v": "23"}, {"n": "中文字幕", "v": "25"}]},
    "yutu": {"name": "玉兔资源", "platform": "adult", "categories": [{"n": "精品推荐", "v": "20"}, {"n": "国产精品", "v": "21"}, {"n": "日本有码", "v": "23"}, {"n": "中文字幕", "v": "25"}]},
    "fqzy": {"name": "番茄资源", "platform": "adult", "categories": [{"n": "欧美精品", "v": "3"}, {"n": "偷拍自拍", "v": "6"}, {"n": "高清无码", "v": "13"}, {"n": "中文字幕", "v": "14"}]},
    "heiliao": {"name": "黑料资源", "platform": "adult", "categories": [{"n": "中文字幕", "v": "1"}, {"n": "日本有码", "v": "2"}, {"n": "日本无码", "v": "3"}, {"n": "自拍偷拍", "v": "29"}]},
    "hsck": {"name": "黄色仓库", "platform": "adult", "categories": [{"n": "国产区", "v": "1"}, {"n": "AV区", "v": "2"}, {"n": "欧美区", "v": "3"}, {"n": "日本无码", "v": "10"}]},
    "naixx": {"name": "奶香香资源", "platform": "adult", "categories": [{"n": "精品国产", "v": "1"}, {"n": "精品日韩", "v": "2"}, {"n": "日韩无码", "v": "28"}]},
    "slzy": {"name": "森林资源", "platform": "adult", "categories": [{"n": "精品推荐", "v": "20"}, {"n": "国产色情", "v": "22"}, {"n": "亚洲无码", "v": "24"}]},
    "thzy": {"name": "桃花资源", "platform": "adult", "categories": [{"n": "国产精品", "v": "6"}, {"n": "华语AV", "v": "7"}, {"n": "日本无码", "v": "25"}]},
    "jpx": {"name": "精品X资源", "platform": "adult", "categories": [{"n": "国产", "v": "1"}, {"n": "日本", "v": "2"}, {"n": "动漫", "v": "4"}, {"n": "高清无码", "v": "20"}]},
    "xingba": {"name": "杏吧资源", "platform": "adult", "categories": [{"n": "日韩无码", "v": "54"}, {"n": "国产主播", "v": "55"}, {"n": "中文字幕", "v": "62"}]},
    "subo2": {"name": "速播资源B", "platform": "adult", "categories": [{"n": "电影", "v": "1"}, {"n": "电视剧", "v": "2"}, {"n": "短剧", "v": "27"}]},
    "niuniuzy": {"name": "牛牛资源", "platform": "adult", "categories": [{"n": "电影", "v": "1"}, {"n": "电视剧", "v": "2"}, {"n": "国产剧", "v": "13"}]},
    "zuidapi": {"name": "最大资源", "platform": "adult", "categories": [{"n": "电影", "v": "1"}, {"n": "电视剧", "v": "2"}, {"n": "动作片", "v": "6"}]},
    "jszy": {"name": "极速资源", "platform": "adult", "categories": [{"n": "电视剧", "v": "1"}, {"n": "电影", "v": "2"}, {"n": "短剧", "v": "38"}]},
    "ffzy": {"name": "非凡资源", "platform": "adult", "categories": [{"n": "电影片", "v": "1"}, {"n": "连续剧", "v": "2"}, {"n": "短剧", "v": "36"}]},
    "xgzy": {"name": "西瓜资源", "platform": "adult", "categories": [{"n": "电影片", "v": "1"}, {"n": "连续剧", "v": "2"}, {"n": "短剧", "v": "36"}]},
    "jxzy": {"name": "量子资源", "platform": "adult", "categories": [{"n": "电影片", "v": "1"}, {"n": "连续剧", "v": "2"}, {"n": "短剧", "v": "46"}]},
    "tyyszy": {"name": "甜晕资源", "platform": "adult", "categories": [{"n": "电影", "v": "1"}, {"n": "电视剧", "v": "2"}, {"n": "短剧", "v": "54"}]}
}

# 顶层一级纯净文件夹分类契约（纯内存直出）[cite: 21]
TOP_CLASSES = [
    {"type_name": "全部", "type_id": "all", "type_flag": "1"},
    {"type_name": "短剧", "type_id": "short", "type_flag": "1"},
    {"type_name": "影视", "type_id": "drama", "type_flag": "1"},
    {"type_name": "成人", "type_id": "adult", "type_flag": "1"},
    {"type_name": "音频", "type_id": "audio", "type_flag": "1"},
    {"type_name": "动漫", "type_id": "anime", "type_flag": "1"}
]

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://av.telstra.com.cv"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

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
        return "🦋 一锅端·12站实测固化版"

    def getDependence(self):
        # 遮天/TVBox 契约：宿主可能在 init 前调用
        return []

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".mp3", ".m4a", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, target_url, referer="", headers_extra=None, timeout=8):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "headers": {}}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/") and not target_url.startswith("/upload"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        if headers_extra:
            headers.update(headers_extra)

        for _ in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=timeout) as resp:
                    raw = resp.read()
                    resp_headers = dict(resp.headers)
                    enc = resp_headers.get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        try:
                            raw = gzip.decompress(raw)
                        except Exception:
                            pass
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    return {"code": resp.getcode(), "text": raw.decode("utf-8", errors="ignore"), "bytes": raw, "headers": resp_headers}
            except urllib.error.HTTPError as e:
                return {"code": e.code, "text": "", "bytes": b"", "headers": dict(e.headers)}
            except Exception:
                continue

        return {"code": -1, "text": "", "bytes": b"", "headers": {}}

    def _universal_pic(self, src_key, raw_pic):
        """精准海报分流引擎：支持已打通 12 站直连与官方代理[cite: 21, 23]"""
        if not raw_pic:
            return "https://dummyimage.com/400x600/1e293b/ffffff.png&text=" + quote(src_key.upper())
        raw_pic = str(raw_pic).strip()

        # 修复初8影视 (cj) 的相对图片路径[cite: 23]
        if src_key == "cj" and raw_pic.startswith("/upload/"):
            return "https://cjysw.cc" + raw_pic

        if raw_pic.startswith("//"):
            raw_pic = "https:" + raw_pic
        elif raw_pic.startswith("/") and not raw_pic.startswith("/api/"):
            raw_pic = self.siteUrl + raw_pic

        # 实测合规且直连秒开的优质图床名单[cite: 21, 23]
        direct_pass_domains = [
            "asmrhoney.com", "cdn202511.com", "pic.892539.xyz", "cdn-xj.cc",
            "img.picbf.com", "hongniuzyimage.com", "cjysw.cc", "img.djuu.com",
            "cloudfront.net", "shorttv.online", "contentchina.com",
            "rongjuwh.cn", "images.weserv.nl"
        ]
        if any(d in raw_pic for d in direct_pass_domains):
            return raw_pic

        # 其余阻断站点走官方代理通道[cite: 21, 23]
        return "%s/api/v1/spiders/%s/proxy?type=img&url=%s" % (self.siteUrl, src_key, quote(raw_pic))

    def _format_remarks(self, brand="蝴蝶影视", meta=""):
        clean_meta = str(meta or "").strip()
        clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
        if clean_meta:
            return "%s | %s" % (brand, clean_meta)
        return brand

    def _get_spiders_for_plat(self, plat_id):
        """获取属于指定大类的站点列表；短剧优先健康源"""
        # 短剧优先顺序：实测有数据的靠前
        short_priority = ["huangdou", "kuangbiao", "yidouge", "xifu", "xingya"]
        matched = []
        for skey, sinfo in SITES_CONFIG_DATA.items():
            sp_plat = sinfo.get("platform")
            if plat_id == "all" or sp_plat == plat_id:
                matched.append({
                    "key": skey,
                    "name": sinfo.get("name", skey),
                    "cat_count": len(sinfo.get("categories", []))
                })
        if plat_id == "short":
            def _sk(item):
                try:
                    return short_priority.index(item["key"])
                except ValueError:
                    return 99
            matched.sort(key=_sk)
        return matched

    def homeContent(self, filter):
        return {"class": TOP_CLASSES, "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        tid_str = str(tid).strip("/")
        page = int(pg) if str(pg).isdigit() else 1

        # ==============================================================
        # 阶段一：处于顶层大类 -> 瀑布流只展现站点文件夹卡片[cite: 21]
        # ==============================================================
        if tid_str in ("all", "adult", "drama", "short", "anime", "audio"):
            plat_sites = self._get_spiders_for_plat(tid_str)
            folder_items = []

            for sp in plat_sites:
                skey = sp["key"]
                sname = sp["name"]
                cat_num = sp["cat_count"]

                # 初始进入站点默认指向第一个子分类[cite: 21]
                init_target = "site/" + skey
                s_cats = SITES_CONFIG_DATA.get(skey, {}).get("categories", [])
                if s_cats:
                    init_target = "site/%s/cat/%s" % (skey, quote(s_cats[0]["v"]))

                folder_items.append({
                    "vod_id": init_target,
                    "vod_name": "📁 " + sname,
                    "vod_pic": "https://dummyimage.com/400x600/1e293b/ffffff.png&text=" + quote(skey.upper()),
                    "vod_remarks": "%d个细分类" % cat_num,
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.78}
                })

            return {
                "page": 1,
                "pagecount": 1,
                "limit": len(folder_items),
                "total": len(folder_items),
                "list": folder_items
            }

        # ==============================================================
        # 阶段二：具体站点瀑布流 + 原地瞬切置顶卡[cite: 21]
        # ==============================================================
        src_key = "cj"
        target_sub_tid = ""

        clean_path = tid_str.replace("site/", "")
        if "/cat/" in clean_path:
            parts = clean_path.split("/cat/")
            src_key = parts[0]
            target_sub_tid = unquote(parts[1])
        else:
            src_key = clean_path

        site_info = SITES_CONFIG_DATA.get(src_key, {})
        valid_cats = site_info.get("categories", [])

        # 定位当前分类在列表中的索引位置[cite: 21]
        current_idx = 0
        if valid_cats:
            for idx, c in enumerate(valid_cats):
                if c["v"] == target_sub_tid:
                    current_idx = idx
                    break
            if not target_sub_tid:
                target_sub_tid = valid_cats[0]["v"]
            cur_cat_name = valid_cats[current_idx]["n"]
        else:
            cur_cat_name = "默认"
            target_sub_tid = target_sub_tid or "1"

        req_url = "%s/api/v1/spiders/%s/category?tid=%s&pg=%d" % (self.siteUrl, src_key, quote(str(target_sub_tid)), page)
        cat_res = self._fetch(req_url)
        vod_list = []

        # 首页置顶瞬切卡片 (vod_tag="folder")[cite: 21]
        if page == 1 and valid_cats and len(valid_cats) > 1:
            next_idx = (current_idx + 1) % len(valid_cats)
            next_cat = valid_cats[next_idx]
            next_cat_name = next_cat["n"]
            next_folder_id = "site/%s/cat/%s" % (src_key, quote(next_cat["v"]))

            vod_list.append({
                "vod_id": next_folder_id,
                "vod_name": "🔄【当前: %s】" % cur_cat_name,
                "vod_pic": "https://dummyimage.com/400x600/3b82f6/ffffff.png&text=SWITCH",
                "vod_remarks": "点我瞬切: %s (%d/%d)" % (next_cat_name, current_idx + 1, len(valid_cats)),
                "vod_tag": "folder",
                "style": {"type": "rect", "ratio": 1.78}
            })

        try:
            data = json.loads(cat_res.get("text", "{}"))
            items = data.get("list") or []

            # 兜底：若该子分类无数据，回退取 home 推荐列表[cite: 21]
            if not items and page == 1:
                home_res = self._fetch("%s/api/v1/spiders/%s/home" % (self.siteUrl, src_key))
                home_data = json.loads(home_res.get("text", "{}"))
                items = home_data.get("list") or []

            page_count = int(data.get("pagecount", 1)) if data.get("pagecount") else 1
            total = int(data.get("total", len(items))) if data.get("total") else len(items)

            for item in items:
                v_id = str(item.get("id") or item.get("vod_id") or "")
                v_name = item.get("name") or item.get("vod_name") or "未知片名"
                raw_pic = item.get("pic") or item.get("vod_pic") or ""
                pic = self._universal_pic(src_key, raw_pic)

                raw_meta = item.get("remarks") or item.get("vod_remarks") or item.get("duration") or item.get("vod_duration") or ""
                remarks = self._format_remarks("蝴蝶影视", raw_meta)

                packed_id = "%s@@%s" % (src_key, v_id)

                vod_list.append({
                    "vod_id": packed_id,
                    "vod_name": v_name,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

            return {
                "page": page,
                "pagecount": page_count if page_count > 0 else 1,
                "limit": len(vod_list),
                "total": total,
                "list": vod_list
            }
        except Exception:
            tip = [{
                "vod_id": "site/%s" % src_key,
                "vod_name": "⚠️ 源站暂无数据或超时",
                "vod_pic": "https://dummyimage.com/400x600/7f1d1d/ffffff.png&text=EMPTY",
                "vod_remarks": "请换其他源站",
                "vod_tag": "folder",
                "style": {"type": "rect", "ratio": 1.78}
            }]
            return {"page": 1, "pagecount": 1, "limit": 1, "total": 1, "list": tip}

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)

        # 拦截 folder 瞬切卡片[cite: 21]
        if str(raw_id).startswith("site/"):
            return self.categoryContent(raw_id, 1, None, None)

        src_key = "cj"
        real_id = raw_id
        if "@@" in raw_id:
            parts = raw_id.split("@@", 1)
            src_key = parts[0]
            real_id = parts[1]

        detail_url = "%s/api/v1/spiders/%s/detail?id=%s" % (self.siteUrl, src_key, quote(real_id))
        res = self._fetch(detail_url)

        try:
            v = json.loads(res.get("text", "{}"))
            if "list" in v and v["list"] and isinstance(v["list"], list):
                v = v["list"][0]
            elif "data" in v and isinstance(v["data"], dict):
                v = v["data"]
        except Exception:
            v = {}

        v_name = v.get("name") or v.get("vod_name") or real_id
        raw_pic = v.get("pic") or v.get("vod_pic") or ""
        v_pic = self._universal_pic(src_key, raw_pic)
        v_content = v.get("content") or v.get("vod_content") or "蝴蝶聚合源站极速穿透播放。"
        v_category = v.get("category") or v.get("type_name") or ""
        raw_meta = v.get("remarks") or v.get("vod_remarks") or ""
        v_remarks = self._format_remarks("蝴蝶影视", raw_meta)

        full_content = (
            "【🦋 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "【当前源站】: %s\n"
            "【影片类别】: %s\n"
            "%s"
        ) % (self.tgGroup, src_key.upper(), v_category, v_content)

        episodes = v.get("episodes") or []
        play_entries = []

        if episodes:
            for ep in episodes:
                ep_name = str(ep.get("name", "正片")).replace("$", "_").replace("#", "_")
                ep_val = str(ep.get("id") or ep.get("url") or real_id)
                play_entries.append("%s$%s@@%s@@%s" % (ep_name, src_key, real_id, quote(ep_val)))
        elif v.get("vod_play_url"):
            raw_play_urls = str(v.get("vod_play_url")).split("#")
            for sub_p in raw_play_urls:
                if "$" in sub_p:
                    ep_name, ep_val = sub_p.split("$", 1)
                else:
                    ep_name, ep_val = "正片", sub_p
                play_entries.append("%s$%s@@%s@@%s" % (
                    ep_name.replace("$", "_").replace("#", "_"), src_key, real_id, quote(ep_val)
                ))
        else:
            play_entries.append("正片$%s@@%s@@%s" % (src_key, real_id, real_id))

        play_from = "蝴蝶·%s" % src_key.upper()
        play_url_str = "#".join(play_entries)

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": v_name,
                "vod_pic": v_pic,
                "vod_type": v_category,
                "vod_remarks": v_remarks,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_content": full_content,
                "vod_play_from": play_from,
                "vod_play_url": play_url_str
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw_play_param = str(id).strip()

        src_key = "cj"
        real_id = raw_play_param
        ep_target = raw_play_param

        if "@@" in raw_play_param:
            parts = raw_play_param.split("@@")
            src_key = parts[0]
            real_id = parts[1]
            if len(parts) >= 3:
                ep_target = unquote(parts[2])

        clean_id = real_id
        if "/" in clean_id and not clean_id.startswith("http"):
            clean_id = clean_id.rstrip("/").split("/")[-1].replace(".html", "")

        # 优先使用选集中的 ep_target 作为 play 请求标识[cite: 23]
        play_param_id = ep_target if (ep_target.startswith("http") or "-" in ep_target or "|" in ep_target or "@" in ep_target) else clean_id
        play_api_url = "%s/api/v1/spiders/%s/play?id=%s" % (self.siteUrl, src_key, quote(play_param_id))
        play_res = self._fetch(play_api_url)

        final_url = ep_target
        header_dict = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }
        need_parse = 0

        try:
            play_json = json.loads(play_res.get("text", "{}"))
            if play_json.get("url"):
                final_url = str(play_json.get("url")).strip()
            # 严格透传官方防盗链签名 Header (含 imaoyou / iyf / xifu 等所有 x-aggr-sig)[cite: 23]
            if isinstance(play_json.get("header"), dict):
                header_dict.update(play_json.get("header"))
            need_parse = int(play_json.get("parse", 0))
        except Exception:
            pass

        # 针对初8影视 (cj) 嗅探页透传专属 Referer[cite: 23]
        if src_key == "cj":
            header_dict["Referer"] = "https://cjysw.cc/"

        # 针对喜福短剧透传来源 Referer[cite: 22, 23]
        if src_key == "xifu":
            header_dict["Referer"] = "https://minidrama.contentchina.com/"

        # 相对路径补齐基准站域名[cite: 21, 23]
        if final_url.startswith("/api/v1/spiders/"):
            final_url = self.siteUrl + final_url
            need_parse = 0

        # 标准音视频流直接放行 parse: 0[cite: 21, 23]
        if self.isVideoFormat(final_url) or any(k in final_url.lower() for k in (".mp3", ".m4a", ".aac", ".wav")):
            need_parse = 0

        return {
            "parse": need_parse,
            "playUrl": "",
            "url": final_url,
            "header": header_dict
        }

    def searchContent(self, key, quick, pg="1"):
        del quick
        page = int(pg) if str(pg).isdigit() else 1
        if page > 1:
            return {"page": page, "pagecount": page, "limit": 0, "total": 0, "list": []}

        # 优先聚合 12 个健康源站发起多源并发检索[cite: 23]
        search_targets = [
            "cj", "imaoyou", "iyf", "huangdou", "xifu", "xingya",
            "yidouge", "kuangbiao", "asmrhoney", "avxq", "b8xx6", "djuu"
        ]
        aggregated_list = []
        for s_key in search_targets:
            s_url = "%s/api/v1/spiders/%s/search?wd=%s&pg=1" % (self.siteUrl, s_key, quote(key))
            res = self._fetch(s_url, timeout=4)
            try:
                data = json.loads(res.get("text", "{}"))
                items = data.get("list") or []
                for item in items[:4]:
                    v_id = str(item.get("id") or item.get("vod_id") or "")
                    v_name = item.get("name") or item.get("vod_name") or ""
                    raw_pic = item.get("pic") or item.get("vod_pic") or ""
                    pic = self._universal_pic(s_key, raw_pic)
                    raw_meta = item.get("remarks") or item.get("vod_remarks") or ""
                    remarks = self._format_remarks("蝴蝶影视", raw_meta)
                    aggregated_list.append({
                        "vod_id": "%s@@%s" % (s_key, v_id),
                        "vod_name": "[%s] %s" % (s_key.upper(), v_name),
                        "vod_pic": pic,
                        "vod_remarks": remarks,
                        "style": {"type": "rect", "ratio": 1.78}
                    })
            except Exception:
                continue

        return {
            "page": page,
            "pagecount": 1,
            "limit": len(aggregated_list),
            "total": len(aggregated_list),
            "list": aggregated_list
        }

    def localProxy(self, params):
        # 遮天契约：param 可能是 dict 或 JSON 字符串；返回必须是四元组
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        if not isinstance(params, dict):
            params = {}
        url = params.get("url", "") or params.get("do", "")
        if not url:
            return [404, "text/plain; charset=utf-8", b"Missing url parameter", {}]
        res = self._fetch(url)
        body = res.get("bytes", b"") or b""
        code = res.get("code", 200) or 200
        mime = "image/jpeg"
        if body.startswith(b"\x89PNG"):
            mime = "image/png"
        elif body.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        elif body.startswith(b"GIF"):
            mime = "image/gif"
        elif body.startswith(b"RIFF") and b"WEBP" in body[:16]:
            mime = "image/webp"
        return [code, mime, body, {"Access-Control-Allow-Origin": "*"}]

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def destroy(self):
        self.options = {}