# -*- coding: utf-8 -*-
"""
红果短剧 TVBox Python 源。

extend 可填写播放桥地址，例如：
  http://192.168.1.4:9979
或 JSON：
  {"bridge":"http://192.168.1.4:9979"}
"""
import json
import re
import sys
import time
from urllib.parse import quote, urlencode

import requests

sys.path.append("../../")
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass


class Spider(Spider):
    site = "https://hongguoduanju.com"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    category_map = {
        "热门": "sort_type=1",
        "最新": "sort_type=2",
        "都市": "background=cate_1",
        "现代": "background=cate_757",
        "古代": "background=cate_758",
        "乡村": "background=cate_11",
        "职场": "background=cate_127",
        "校园": "background=cate_4",
        "悬疑": "topic=cate_165",
        "喜剧": "topic=cate_303",
        "重生": "setting=cate_36",
        "穿越": "setting=cate_37",
    }

    def __init__(self):
        self.bridge = "http://192.168.1.4:9979"
        self._cache = {}

    def getName(self):
        return "红果短剧"

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.bridge = str(extend.get("bridge") or self.bridge).rstrip("/")
        elif extend:
            text = str(extend).strip()
            try:
                data = json.loads(text)
                self.bridge = str(data.get("bridge") or self.bridge).rstrip("/")
            except Exception:
                if text.startswith("http"):
                    self.bridge = text.rstrip("/")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    def _get(self, url):
        response = requests.get(url, headers=self.headers, timeout=25)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    def _router_data(self, url):
        cached = self._cache.get(url)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        html = self._get(url)
        match = re.search(
            r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>",
            html,
            re.S,
        )
        if not match:
            raise RuntimeError("页面数据格式已变化")
        data = json.loads(match.group(1))
        self._cache[url] = (time.time(), data)
        return data

    @staticmethod
    def _vod(item):
        tags = item.get("tags") or []
        if isinstance(tags, list):
            tags = " · ".join(str(x) for x in tags[:3])
        count = item.get("episode_cnt") or len(item.get("vid_list") or [])
        remark = ("全%s集" % count) if count else str(tags or "")
        return {
            "vod_id": str(item.get("series_id") or ""),
            "vod_name": str(item.get("series_name") or ""),
            "vod_pic": str(item.get("series_cover") or ""),
            "vod_remarks": remark,
        }

    def _category_items(self, query):
        url = self.site + "/category?" + query
        data = self._router_data(url)
        page = data.get("loaderData", {}).get("category_page", {})
        items = page.get("recommendList") or []
        if not items:
            items = page.get("categoryData", {}).get("recommendList") or []
        seen = set()
        result = []
        for item in items:
            sid = str(item.get("series_id") or "")
            if sid and sid not in seen:
                seen.add(sid)
                result.append(item)
        return result

    def homeContent(self, filter):
        return {
            "class": [
                {"type_name": name, "type_id": query}
                for name, query in self.category_map.items()
            ],
            "list": self.homeVideoContent().get("list", []),
        }

    def homeVideoContent(self):
        try:
            items = self._category_items("sort_type=1")[:30]
            return {"list": [self._vod(x) for x in items]}
        except Exception as exc:
            print("红果首页读取失败:", exc)
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        per_page = 30
        try:
            items = self._category_items(str(tid))
            start = (page - 1) * per_page
            chunk = items[start:start + per_page]
            page_count = max(1, (len(items) + per_page - 1) // per_page)
            return {
                "list": [self._vod(x) for x in chunk],
                "page": page,
                "pagecount": page_count,
                "limit": per_page,
                "total": len(items),
            }
        except Exception as exc:
            print("红果分类读取失败:", exc)
            return {"list": [], "page": page, "pagecount": page}

    def detailContent(self, ids):
        series_id = str(ids[0])
        url = self.site + "/detail?series_id=" + quote(series_id)
        try:
            data = self._router_data(url)
            detail = data.get("loaderData", {}).get("detail_page", {})
            series = detail.get("seriesDetail") or {}
            vids = series.get("vid_list") or []
            episodes = [
                "第%d集$%s" % (index + 1, vid)
                for index, vid in enumerate(vids)
                if str(vid)
            ]
            tags = series.get("tags") or []
            if isinstance(tags, list):
                tags = ",".join(str(x) for x in tags)
            vod = {
                "vod_id": series_id,
                "vod_name": str(series.get("series_name") or "红果短剧"),
                "vod_pic": str(series.get("series_cover") or ""),
                "type_name": str(tags),
                "vod_remarks": "全%s集" % (series.get("episode_cnt") or len(vids)),
                "vod_content": str(series.get("series_intro") or ""),
                "vod_play_from": "红果",
                "vod_play_url": "#".join(episodes),
            }
            return {"list": [vod]}
        except Exception as exc:
            print("红果详情读取失败:", exc)
            return {"list": []}

    def searchContent(self, key, quick, pg=1):
        page = max(1, int(pg or 1))
        per_page = 30
        try:
            items = self._category_items("sort_type=1")
            keyword = str(key).strip().lower()
            matches = [
                x for x in items
                if keyword in str(x.get("series_name") or "").lower()
                or keyword in str(x.get("series_intro") or "").lower()
            ]
            start = (page - 1) * per_page
            return {
                "list": [self._vod(x) for x in matches[start:start + per_page]],
                "page": page,
            }
        except Exception as exc:
            print("红果搜索失败:", exc)
            return {"list": [], "page": page}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, pid, vipFlags):
        url = self.bridge + "/play?" + urlencode({"vid": str(pid)})
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.site + "/",
            },
        }

    def localProxy(self, params):
        return None
