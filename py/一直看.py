#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "一直看"
        self.hosts = ["https://1zk.me", "https://1zk.top", "https://1zk.app", "https://54kk.net"]
        self._host_idx = 0
        self.siteUrl = self.hosts[0]
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.xorKey = "film_hmos_2024"
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
        if "siteUrl" in self.options:
            self.siteUrl = self.options["siteUrl"].rstrip("/")
        return True

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "55287.mp4")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _switch_host(self):
        self._host_idx = (self._host_idx + 1) % len(self.hosts)
        self.siteUrl = self.hosts[self._host_idx]

    def _fetch(self, path, data=None, headers_extra=None):
        req_data = None
        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        if headers_extra:
            headers.update(headers_extra)

        if data is not None:
            if isinstance(data, dict):
                req_data = json.dumps(data).encode("utf-8")
                headers["Content-Type"] = "application/json;charset=UTF-8"
            elif isinstance(data, (bytes, str)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        for host_attempt in range(len(self.hosts)):
            full_url = self.siteUrl + path if path.startswith("/") else path
            headers["Referer"] = self.siteUrl + "/"

            for retry in range(2):
                try:
                    req = urllib.request.Request(full_url, data=req_data, headers=headers)
                    with self.opener.open(req, timeout=10) as resp:
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
                        return {"code": resp.getcode(), "text": text, "bytes": raw, "err": ""}
                except urllib.error.HTTPError as e:
                    if e.code in (451, 403, 429) and retry == 0:
                        continue
                    err_txt = ""
                    try:
                        err_txt = e.read().decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                    return {"code": e.code, "text": err_txt, "bytes": b"", "err": str(e)}
                except Exception as e:
                    if retry == 0:
                        continue
                    break

            self._switch_host()

        return {"code": -1, "text": "", "bytes": b"", "err": "all_hosts_failed"}

    def homeContent(self, filter):
        classes = [
            {"type_name": "🔥 热门推荐", "type_id": "trending"},
            {"type_name": "📅 最近更新", "type_id": "released"},
            {"type_name": "📈 播放趋势", "type_id": "recently"},
            {"type_name": "🤖 Ai短剧", "type_id": "137"},
            {"type_name": "🇨🇳 华语专区", "type_id": "59"},
            {"type_name": "🇯🇵 东瀛专区", "type_id": "60"},
            {"type_name": "🇺🇸 欧美精选", "type_id": "61"},
            {"type_name": "🔞 经典三级", "type_id": "62"}
        ]
        filters = {}
        if filter:
            sub_map = {
                "137": [{"n": "全部", "v": "137"}, {"n": "成人短剧", "v": "138"}],
                "59": [
                    {"n": "全部", "v": "59"},
                    {"n": "国产精选", "v": "129"},
                    {"n": "网红黑料", "v": "130"},
                    {"n": "主播直播", "v": "131"},
                    {"n": "探花系列", "v": "132"},
                    {"n": "制服诱惑", "v": "133"},
                    {"n": "美女系列", "v": "134"},
                    {"n": "家庭伦理", "v": "135"}
                ],
                "60": [
                    {"n": "全部", "v": "60"},
                    {"n": "中文字幕", "v": "105"},
                    {"n": "精选无码", "v": "106"},
                    {"n": "全家乱操", "v": "107"},
                    {"n": "人妻NTR", "v": "108"},
                    {"n": "强奸系列", "v": "109"},
                    {"n": "FC2素人", "v": "110"},
                    {"n": "群P大乱交", "v": "111"},
                    {"n": "巨乳美乳", "v": "112"},
                    {"n": "办公室性侵", "v": "113"},
                    {"n": "稚嫩学生妹", "v": "114"},
                    {"n": "黑鬼巨根", "v": "115"},
                    {"n": "SM系列", "v": "116"},
                    {"n": "电车痴汉", "v": "117"},
                    {"n": "家政妇", "v": "118"},
                    {"n": "风俗娘", "v": "119"},
                    {"n": "时间停止", "v": "120"}
                ],
                "61": [
                    {"n": "全部", "v": "61"},
                    {"n": "欧美精选", "v": "121"},
                    {"n": "户外搭讪", "v": "122"},
                    {"n": "美女自慰", "v": "123"},
                    {"n": "成人剧情", "v": "124"},
                    {"n": "黑人大屌", "v": "125"},
                    {"n": "群P大作战", "v": "126"},
                    {"n": "欧美重口", "v": "127"}
                ],
                "62": [
                    {"n": "全部", "v": "62"},
                    {"n": "经典三级", "v": "128"}
                ]
            }

            year_opts = [{"n": "全部", "v": ""}]
            for yr in range(2026, 1999, -1):
                year_opts.append({"n": str(yr), "v": str(yr)})
            for dec in range(1990, 1969, -10):
                year_opts.append({"n": "%s年代" % str(dec)[2:], "v": "%ss" % dec})
            year_opts.append({"n": "更早", "v": "older"})

            sort_opts = [
                {"n": "最近更新", "v": "recent"},
                {"n": "按年份", "v": "release_date"},
                {"n": "热门", "v": "hot"},
                {"n": "热度", "v": "views"}
            ]

            common_filters = [
                {
                    "key": "year",
                    "name": "年份",
                    "init": "",
                    "value": year_opts
                },
                {
                    "key": "sort",
                    "name": "排序",
                    "init": "recent",
                    "value": sort_opts
                }
            ]

            for c in classes:
                cid = c["type_id"]
                if cid in ("trending", "released", "recently"):
                    continue
                c_filter = []
                if cid in sub_map:
                    c_filter.append({
                        "key": "sub_cat",
                        "name": "子分类",
                        "init": cid,
                        "value": sub_map[cid]
                    })
                c_filter.extend(common_filters)
                filters[cid] = c_filter

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        vod_list = []
        res = self._fetch("/api/v1/films/home")
        if res.get("code") == 200 and res.get("text"):
            try:
                j_obj = json.loads(res.get("text"))
                data = j_obj.get("data", {})
                sections = [("trendingFilms", "热门"), ("releasedFilms", "最新"), ("recentlyFilms", "热播")]
                seen_ids = set()
                for sec_key, tag in sections:
                    for item in data.get(sec_key, []):
                        fid = item.get("id")
                        if fid and fid not in seen_ids:
                            seen_ids.add(fid)
                            cat_info = item.get("category", {})
                            cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else tag
                            vod_list.append({
                                "vod_id": str(fid),
                                "vod_name": item.get("title", ""),
                                "vod_pic": item.get("cover_url", ""),
                                "vod_remarks": format_remarks("蝴蝶影视", cat_name),
                                "style": {"type": "rect", "ratio": 1.78}
                            })
            except Exception:
                pass
        return {"list": vod_list}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        page_size = 20
        raw_tid = str(tid).strip()

        tab_home_map = {
            "trending": ("trendingFilms", "热门推荐", "sortBy=sort_order&sortOrder=DESC&isRecommend=true"),
            "released": ("releasedFilms", "最近更新", "sortBy=created_at&sortOrder=DESC"),
            "recently": ("recentlyFilms", "播放趋势", "sortBy=play_count&sortOrder=DESC")
        }

        if raw_tid in tab_home_map:
            home_key, default_lbl, page_query = tab_home_map[raw_tid]
            if page == 1:
                home_res = self._fetch("/api/v1/films/home")
                if home_res.get("code") == 200 and home_res.get("text"):
                    try:
                        h_obj = json.loads(home_res.get("text"))
                        h_list = h_obj.get("data", {}).get(home_key, [])
                        if h_list:
                            vod_list = []
                            for item in h_list:
                                fid = item.get("id")
                                if fid:
                                    cat_info = item.get("category", {})
                                    cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else default_lbl
                                    vod_list.append({
                                        "vod_id": str(fid),
                                        "vod_name": item.get("title", ""),
                                        "vod_pic": item.get("cover_url", ""),
                                        "vod_remarks": format_remarks("蝴蝶影视", cat_name),
                                        "style": {"type": "rect", "ratio": 1.78}
                                    })
                            return {
                                "page": 1,
                                "pagecount": 99,
                                "limit": len(vod_list),
                                "total": 999,
                                "list": vod_list
                            }
                    except Exception:
                        pass

            api_path = "/api/v1/films?status=published&page=%d&pageSize=%d&%s" % (page, page_size, page_query)
            res = self._fetch(api_path)
            vod_list = []
            total = 0
            page_count = 1
            if res.get("code") == 200 and res.get("text"):
                try:
                    j_obj = json.loads(res.get("text"))
                    data = j_obj.get("data", {})
                    items = data.get("list", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
                    page_count = data.get("totalPages", 1) if isinstance(data, dict) else 1
                    for item in items:
                        fid = item.get("id")
                        if fid:
                            cat_info = item.get("category", {})
                            cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else default_lbl
                            vod_list.append({
                                "vod_id": str(fid),
                                "vod_name": item.get("title", ""),
                                "vod_pic": item.get("cover_url", ""),
                                "vod_remarks": format_remarks("蝴蝶影视", cat_name),
                                "style": {"type": "rect", "ratio": 1.78}
                            })
                except Exception:
                    pass

            return {
                "page": page,
                "pagecount": max(page_count, 1),
                "limit": page_size,
                "total": total,
                "list": vod_list
            }

        target_id = raw_tid
        sort_val = ""
        year_raw = ""

        if extend and isinstance(extend, dict):
            if extend.get("sub_cat"):
                target_id = str(extend.get("sub_cat")).strip()
            if extend.get("sort"):
                sort_val = str(extend.get("sort")).strip()
            if extend.get("year"):
                year_raw = str(extend.get("year")).strip()

        if not sort_val:
            sort_val = "recent"

        query_params = [
            "page=%d" % page,
            "pageSize=%d" % page_size,
            "sort=%s" % quote(sort_val)
        ]

        if year_raw:
            if year_raw.isdigit():
                query_params.append("year=%s" % year_raw)
            elif year_raw.endswith("s") and year_raw[:-1].isdigit():
                base_year = int(year_raw[:-1])
                query_params.append("yearStart=%d" % base_year)
                query_params.append("yearEnd=%d" % (base_year + 9))
            elif year_raw == "older":
                query_params.append("yearStart=0")
                query_params.append("yearEnd=1969")

        param_str = "&".join(query_params)
        api_path = "/api/v1/categories/%s/films?%s" % (target_id, param_str)

        res = self._fetch(api_path)
        vod_list = []
        total = 0
        page_count = 1

        if res.get("code") == 200 and res.get("text"):
            try:
                j_obj = json.loads(res.get("text"))
                data = j_obj.get("data", {})
                if isinstance(data, dict):
                    items = data.get("list", [])
                    total = data.get("total", len(items))
                    page_count = data.get("totalPages", 1)
                elif isinstance(data, list):
                    items = data
                    total = len(items)
                    page_count = 1
                else:
                    items = []

                for item in items:
                    fid = item.get("id")
                    if fid:
                        cat_info = item.get("category", {})
                        cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else "正片"
                        vod_list.append({
                            "vod_id": str(fid),
                            "vod_name": item.get("title", ""),
                            "vod_pic": item.get("cover_url", ""),
                            "vod_remarks": format_remarks("蝴蝶影视", cat_name),
                            "style": {"type": "rect", "ratio": 1.78}
                        })
            except Exception:
                pass

        if page_count < 1:
            page_count = 1

        return {
            "page": page,
            "pagecount": page_count,
            "limit": page_size,
            "total": total,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_id = str(raw_id).strip()

        res = self._fetch("/api/v1/films/%s" % target_id)
        if res.get("code") != 200 or not res.get("text"):
            return {"list": []}

        try:
            j_obj = json.loads(res.get("text"))
            data = j_obj.get("data", {})
            title = data.get("title", "正片")
            pic = data.get("cover_url", "")
            cat_name = data.get("category", {}).get("name", "") if isinstance(data.get("category"), dict) else ""
            desc = data.get("description", "") or "海量高清短视频在线观看，每日极速更新。"

            play_urls = []
            ep_count = data.get("episode_count", 1)
            if ep_count and ep_count > 1:
                for ep in range(1, ep_count + 1):
                    play_urls.append("第%d集$%s@%d" % (ep, target_id, ep))
            else:
                play_urls.append("正片$%s@1" % target_id)

            full_desc = (
                "【🔥 官方交流群: %s】\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "• 分类: %s\n"
                "• 简介: %s"
            ) % (self.tgGroup, cat_name or "精选", desc)

            vod = {
                "vod_id": target_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": format_remarks("蝴蝶影视", cat_name or "全集"),
                "vod_content": full_desc,
                "vod_play_from": "蝴蝶专线",
                "vod_play_url": "#".join(play_urls)
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        raw_val = str(id).strip()
        parts = raw_val.split("@")
        film_id = parts[0]
        ep_num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

        payload = {
            "episode": ep_num,
            "source": "direct"
        }
        res = self._fetch("/api/v1/films/%s/play" % film_id, data=payload)
        real_url = ""

        if res.get("code") == 200 and res.get("text"):
            try:
                j_obj = json.loads(res.get("text"))
                real_url = j_obj.get("data", {}).get("playUrl", "")
            except Exception:
                pass

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        return {
            "parse": 0,
            "playUrl": "",
            "url": real_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        page_size = 20
        encoded_kw = quote(str(key).strip())
        api_path = "/api/v1/films?keyword=%s&page=%d&pageSize=%d" % (encoded_kw, page, page_size)

        res = self._fetch(api_path)
        vod_list = []
        total = 0
        page_count = 1

        if res.get("code") == 200 and res.get("text"):
            try:
                j_obj = json.loads(res.get("text"))
                data = j_obj.get("data", {})
                if isinstance(data, dict):
                    items = data.get("list", [])
                    total = data.get("total", len(items))
                    page_count = data.get("totalPages", 1)
                elif isinstance(data, list):
                    items = data
                    total = len(items)
                else:
                    items = []

                for item in items:
                    fid = item.get("id")
                    if fid:
                        cat_info = item.get("category", {})
                        cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else ""
                        vod_list.append({
                            "vod_id": str(fid),
                            "vod_name": item.get("title", ""),
                            "vod_pic": item.get("cover_url", ""),
                            "vod_remarks": format_remarks("蝴蝶影视", cat_name or "匹配"),
                            "style": {"type": "rect", "ratio": 1.78}
                        })
            except Exception:
                pass

        if page_count < 1:
            page_count = 1

        return {
            "page": page,
            "pagecount": page_count,
            "limit": page_size,
            "total": total,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]