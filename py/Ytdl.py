# -*- coding: utf-8 -*-
"""
@File    : Ytdl.py
@Desc    : TVBox / FongMi (type: 3) YouTube Live & Video Resolver
"""
import json
import re
import urllib.parse
import urllib.request
from base import Spider


class Spider(Spider):
    def getName(self):
        return "Ytdl"

    def init(self, tid):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def action(self, action):
        pass

    def headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    # 1. 抓取文字直播源分類 (Lives 或 Sites 列表)
    def homeContent(self, filter):
        result = {}
        cateExtra = self.extend
        if not cateExtra:
            return result
        
        try:
            req = urllib.request.Request(cateExtra, headers=self.headers())
            with urllib.request.urlopen(req, timeout=10) as res:
                content = res.read().decode("utf-8", errors="ignore")

            classes = []
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    genre = line.split(",")[0].strip()
                    classes.append({"type_id": genre, "type_name": genre})

            result["class"] = classes
        except Exception as e:
            pass
        return result

    def homeVideoContent(self):
        return {}

    # 2. 解析類別下的 YouTube 直播頻道
    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        videos = []
        cateExtra = self.extend
        
        try:
            req = urllib.request.Request(cateExtra, headers=self.headers())
            with urllib.request.urlopen(req, timeout=10) as res:
                content = res.read().decode("utf-8", errors="ignore")

            current_genre = ""
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "#genre#" in line:
                    current_genre = line.split(",")[0].strip()
                    continue

                if current_genre == tid or not tid:
                    if "," in line:
                        parts = line.split(",")
                        name = parts[0].strip()
                        url = parts[1].strip()
                        if "youtube.com" in url or "youtu.be" in url:
                            videos.append({
                                "vod_id": url,
                                "vod_name": name,
                                "vod_pic": "https://img.youtube.com/vi/" + self.extract_yt_id(url) + "/hqdefault.jpg",
                                "vod_remarks": "YouTube Live"
                            })
        except Exception as e:
            pass

        result["list"] = videos
        result["page"] = 1
        result["pagecount"] = 1
        result["limit"] = len(videos)
        result["total"] = len(videos)
        return result

    def detailContent(self, ids):
        url = ids[0]
        vod = {
            "vod_id": url,
            "vod_name": "YouTube 直播串流",
            "vod_play_from": "YouTube",
            "vod_play_url": f"播放#{url}"
        }
        return {"list": [vod]}

    def searchContent(self, key, quick):
        return {}

    # 3. 核心功能：直接將 YouTube URL 提取並解析為真實的 m3u8 直播串流
    def playerContent(self, flag, id, vipFlags):
        result = {}
        yt_url = id
        
        try:
            req = urllib.request.Request(yt_url, headers=self.headers())
            with urllib.request.urlopen(req, timeout=10) as res:
                html = res.read().decode("utf-8", errors="ignore")

            # 提取 YouTube 頁面中的 hlsManifestUrl (.m3u8 串流位址)
            match = re.search(r'"hlsManifestUrl"\s*:\s*"(https://[^"]+\.m3u8)"', html)
            if match:
                m3u8_url = match.group(1).replace("\\/", "/")
                result["parse"] = 0  # 直連播放，無需二次解析
                result["playUrl"] = ""
                result["url"] = m3u8_url
                result["header"] = {
                    "User-Agent": self.headers()["User-Agent"]
                }
                return result

            # 備用提取邏輯 (針對部分的 JSON 變數)
            match_json = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.+?\});</script>', html)
            if match_json:
                data = json.loads(match_json.group(1))
                hls_url = data.get("streamingData", {}).get("hlsManifestUrl")
                if hls_url:
                    result["parse"] = 0
                    result["playUrl"] = ""
                    result["url"] = hls_url
                    result["header"] = {
                        "User-Agent": self.headers()["User-Agent"]
                    }
                    return result
        except Exception as e:
            pass

        result["parse"] = 1
        result["url"] = yt_url
        return result

    def extract_yt_id(self, url):
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
        return match.group(1) if match else ""