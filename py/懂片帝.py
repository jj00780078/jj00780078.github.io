# -*- coding: utf-8 -*-
"""
目标站: 懂片帝AI (dongpian1.com)
模板: 影视聚合搜索 / 爬虫播放
站点类型: 综合影视 (电影/电视剧/动漫/综艺/短剧)
核心逻辑: 调用 HMAC-SHA256 签名 JSON API, 提取视频信息和真实播放链接
线路机制:
  - /v1/playback/resolve/{token} 返回全部播放线路 (line_options)
    * 官方源: url 形如 resolve://rpt1.<ticket>, 需 POST /v1/playback/resolve-line 换取真实地址
    * 资源源: url 直接为 https m3u8 直链, 可直接播放
  - 线路名称取自站点真实 label (如 "1080P-官方V"、"红牛资源" 等), 全部写出
速度优化:
  - 详情/剧集/线路解析结果按 TTL 缓存, 避免重复请求
  - 播放时仅解析所选线路 (懒解析), 直链线路零额外请求
  - 剧集一次拉全, 分页无需逐页请求
支持: 首页, 一/二级分类, 搜索, 详情, 播放
"""
import re
import sys
import json
import time
import hmac
import hashlib
import os
import urllib.parse

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://dongpian1.com"
        # API 签名密钥 (从前端 JS 提取)
        self.api_secret = "8b9a908a05eac640e1ee06f52acaa741bfe4ba9e004eeffdbeb635e532e06666"
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.site_url + "/",
            'Origin': self.site_url,
        }
        self.default_pic = "https://pic.rmb.bdstatic.com/bjh/user/default.png"
        # 一级分类映射: content_kind -> 中文名
        self.categories = {
            "movie": "电影",
            "series": "电视剧",
            "anime": "动漫",
            "variety": "综艺",
            "short_drama": "短剧",
        }
        # 二级分类筛选: 类型 (站点原生支持中文 genre 值)
        self.genre_options = [
            ("全部", ""), ("动作", "动作"), ("喜剧", "喜剧"), ("爱情", "爱情"),
            ("科幻", "科幻"), ("悬疑", "悬疑"), ("惊悚", "惊悚"), ("恐怖", "恐怖"),
            ("剧情", "剧情"), ("犯罪", "犯罪"), ("冒险", "冒险"), ("奇幻", "奇幻"),
            ("战争", "战争"), ("古装", "古装"), ("武侠", "武侠"), ("家庭", "家庭"),
            ("动画", "动画"), ("纪录", "纪录"), ("真人秀", "真人秀"), ("脱口秀", "脱口秀"),
            ("国产", "国产"), ("港剧", "港剧"), ("韩剧", "韩剧"), ("美剧", "美剧"),
            ("日剧", "日剧"), ("短剧", "短剧"), ("逆袭", "逆袭"), ("甜宠", "甜宠"),
        ]
        # 二级分类筛选: 地区
        self.area_options = [
            ("全部", ""), ("中国大陆", "中国大陆"), ("中国香港", "中国香港"),
            ("中国台湾", "中国台湾"), ("美国", "美国"), ("韩国", "韩国"),
            ("日本", "日本"), ("英国", "英国"), ("法国", "法国"), ("泰国", "泰国"),
            ("印度", "印度"), ("其他", "其他"),
        ]
        # 二级分类筛选: 年份
        self.year_options = [("全部", "")] + [(str(y), str(y)) for y in range(2027, 2019, -1)]

        # 缓存: 详情/剧集/线路解析 (TTL 秒), 避免重复请求, 提升加载与播放速度
        self._cache = {}
        self._cache_ttl_detail = 600
        self._cache_ttl_resolve = 300

    # ========== 基础请求 ==========

    def _sign_headers(self, method, path_with_search):
        """生成 API 签名请求头

        签名串格式: {METHOD}\n{pathname}{search}\n{timestamp}\n{nonce}
        算法: HMAC-SHA256(密钥, 签名串) -> hex
        """
        ts = str(int(time.time() * 1000))
        nonce = os.urandom(16).hex()
        msg = "{0}\n{1}\n{2}\n{3}".format(method, path_with_search, ts, nonce)
        sig = hmac.new(self.api_secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            **self.headers,
            'x-ai-movie-timestamp': ts,
            'x-ai-movie-nonce': nonce,
            'x-ai-movie-signature': sig,
        }

    def _api_get(self, path):
        """调用签名 GET API 并返回解析后的 JSON 字典"""
        url = self.site_url + path
        headers = self._sign_headers("GET", path)
        try:
            resp = self.fetch(url, headers=headers)
            if not resp:
                return {}
            return json.loads(resp.text)
        except Exception:
            return {}

    def _api_post(self, path, payload):
        """调用签名 POST API 并返回解析后的 JSON 字典"""
        url = self.site_url + path
        headers = self._sign_headers("POST", path)
        headers['Content-Type'] = 'application/json; charset=utf-8'
        try:
            resp = self.fetch(url, headers=headers, data=json.dumps(payload, ensure_ascii=False))
            if not resp:
                return {}
            return json.loads(resp.text)
        except Exception:
            return {}

    # ========== 缓存（速度优化） ==========

    def _cache_get(self, key):
        """读取缓存项, 过期则视为未命中"""
        item = self._cache.get(key)
        if not item:
            return None
        if item[0] < time.time():
            self._cache.pop(key, None)
            return None
        return item[1]

    def _cache_set(self, key, value, ttl):
        self._cache[key] = (time.time() + ttl, value)

    # ========== 卡片解析 ==========

    def _parse_card(self, card):
        """将 API 卡片对象转换为 vod 字典 (列表页通用)"""
        vid = card.get("id", "") or ""
        name = card.get("title", "") or ""
        pic = card.get("poster_url", "") or ""
        remark = card.get("remarks", "") or ""
        year = card.get("year", "")
        if year:
            year = str(year)
        else:
            year = ""
        area = card.get("area", "") or ""
        genres = card.get("genres", [])
        type_name = " / ".join(genres[:3]) if genres else ""
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic if pic else self.default_pic,
            "vod_remarks": remark,
            "vod_year": year,
            "vod_area": area,
            "vod_type": type_name,
        }

    def _is_valid_video_url(self, url):
        """过滤掉明显不是视频直链的地址（如封面图片）"""
        if not url:
            return False
        url_lower = url.lower()
        for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]:
            if ext in url_lower:
                return False
        return True

    # ========== 工具方法 ==========

    def _normalize_vid(self, vid):
        """规范化视频 ID: 兼容卡片 id 与详情页相对路径"""
        vid = (vid or "").strip()
        if "/v1/catalog/" in vid:
            vid = vid.split("/v1/catalog/")[-1]
        if vid.startswith("variant:"):
            vid = vid.split(":", 1)[-1]
        return vid

    def _get_detail(self, vid):
        """获取详情 + 全部剧集 (带缓存)

        详情接口: /v1/catalog/{id}/detail
        剧集接口: /v1/catalog/{id}/episodes?limit=1000 (一次拉全)
        """
        vid = self._normalize_vid(vid)
        cache_key = "detail:{0}".format(vid)
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        detail = self._api_get("/v1/catalog/{0}/detail".format(urllib.parse.quote(vid)))
        if not detail or "id" not in detail:
            # 兼容旧式详情接口
            detail = self._api_get("/v1/catalog/{0}".format(urllib.parse.quote(vid)))
        if not detail or "id" not in detail:
            return None

        episodes = detail.get("episodes") or []
        if not episodes:
            ep_data = self._api_get(
                "/v1/catalog/{0}/episodes?limit=1000&offset=0".format(urllib.parse.quote(vid))
            )
            episodes = ep_data.get("episodes") or []

        result = (detail, episodes)
        self._cache_set(cache_key, result, self._cache_ttl_detail)
        return result

    def _get_line_options(self, token):
        """获取某集可用的全部播放线路 (带缓存)

        同一部剧的各集线路基本一致, 用首集 token 取一次即可
        """
        cache_key = "resolve:{0}".format(token)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        resolve_data = self._api_get(
            "/v1/playback/resolve/{0}".format(urllib.parse.quote(token))
        )
        line_options = resolve_data.get("line_options", []) or []
        # 过滤掉无 url 的线路
        valid = []
        for opt in line_options:
            if opt.get("url"):
                valid.append(opt)
        self._cache_set(cache_key, valid, self._cache_ttl_resolve)
        return valid

    def _sort_lines(self, line_options, selected_provider=""):
        """线路排序: 用户选中线路最前, 官方 resolve_ticket 优先, 资源类直链其次, 其余按权重

        返回可播放的优先线路列表
        """

        def line_rank(opt):
            kind = opt.get("url_kind", "")
            name = (opt.get("provider_name") or "").lower()
            if kind == "resolve_ticket":
                return 2
            if "资源" in name:
                return 0
            return 1

        def is_selected(opt):
            pid = opt.get("id") or opt.get("playback_source_id") or ""
            if selected_provider and pid == selected_provider:
                return True
            if selected_provider and opt.get("provider_id") == selected_provider:
                return True
            if selected_provider and opt.get("play_from") == selected_provider:
                return True
            return False

        return sorted(
            line_options,
            key=lambda x: (not is_selected(x), -line_rank(x), -x.get("preference_weight", 0))
        )

    def _play_header(self):
        """播放直链时需要携带的请求头"""
        return {
            'User-Agent': self.headers['User-Agent'],
            'Referer': self.site_url + "/",
        }

    # ========== 首页 ==========

    def homeContent(self, filter):
        """获取首页内容: 一级分类(含二级筛选) + 推荐视频"""
        categories = []
        for kind, name in self.categories.items():
            categories.append({
                "type_id": kind,
                "type_name": name,
                "filter": [
                    {
                        "key": "genre",
                        "name": "类型",
                        "value": [{"n": n, "v": v} for n, v in self.genre_options],
                    },
                    {
                        "key": "area",
                        "name": "地区",
                        "value": [{"n": n, "v": v} for n, v in self.area_options],
                    },
                    {
                        "key": "year",
                        "name": "年份",
                        "value": [{"n": n, "v": v} for n, v in self.year_options],
                    },
                ],
            })

        data = self._api_get("/v1/feed/home?scope=public&mode=page&sections=6&cards=15")
        videos = []
        seen = set()
        for sec in data.get("sections", []):
            for card in sec.get("cards", []):
                vid = card.get("id", "")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                videos.append(self._parse_card(card))
                if len(videos) >= 30:
                    break
            if len(videos) >= 30:
                break

        return {"class": categories, "list": videos, "filters": {}}

    def homeVideoContent(self):
        """获取首页推荐视频列表"""
        data = self._api_get("/v1/feed/home?scope=public&mode=page&sections=6&cards=15")
        videos = []
        seen = set()
        for sec in data.get("sections", []):
            for card in sec.get("cards", []):
                vid = card.get("id", "")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                videos.append(self._parse_card(card))
                if len(videos) >= 30:
                    break
            if len(videos) >= 30:
                break
        return {"list": videos}

    # ========== 分类(含二级筛选) ==========

    def _tid_to_kind(self, tid):
        """TVBox 可能传中文 type_name 作为 tid, 映射回站点 kind 参数"""
        mapping = {
            "电影": "movie",
            "电视剧": "series",
            "动漫": "anime",
            "综艺": "variety",
            "短剧": "short_drama",
        }
        return mapping.get(tid, tid)

    def _apply_filters(self, params, extend):
        """从 extend 字典中提取有效筛选参数, 过滤掉 '全部' / 空字符串 / None"""
        if not extend:
            return
        for fk in ("genre", "area", "year"):
            fv = extend.get(fk)
            if fv and str(fv).strip() and str(fv).strip() != "全部":
                params[fk] = str(fv).strip()

    def categoryContent(self, tid, pg, filter, extend):
        """获取分类列表

        tid:     一级分类标识 (TVBox 可能传中文 type_name, 如 "电影")
        pg:      页码
        filter:  TVBox 框架传入的布尔值/字典, 此处不直接使用
        extend:  筛选字典, 如 {"genre": "\u52a8\u4f5c", "area": "\u4e2d\u56fd\u5927\u9646", "year": "2026"}
        """
        page = int(pg) if pg else 1
        limit = 30
        kind = self._tid_to_kind(tid)
        params = {
            "kind": kind,
            "sort": "trending",
            "page": str(page),
            "limit": str(limit),
        }
        self._apply_filters(params, extend)
        path = "/v1/browse/catalog?" + urllib.parse.urlencode(params)
        data = self._api_get(path)

        cards = data.get("cards", []) or []
        videos = [self._parse_card(c) for c in cards if c.get("id")]

        pagecount = self._estimate_pagecount(kind, extend, page, limit, cards)
        total = pagecount * limit

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": limit,
            "total": total,
        }

    def _estimate_pagecount(self, tid, extend, page, limit, cards):
        """估算总页数: 本页不足一页则结束; 否则探测下一页 (带缓存, 避免重复请求)"""
        if len(cards) < limit:
            return page
        probe = self._build_catalog_path(tid, extend, page + 1, 1)
        return page + 1 if self._has_next_page(probe) else page

    def _has_next_page(self, probe_path):
        """探测下一页是否有数据, 结果缓存 60 秒"""
        key = "probe:" + probe_path
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        probe_data = self._api_get(probe_path)
        has_next = bool(probe_data.get("cards"))
        self._cache_set(key, has_next, 60)
        return has_next

    def _build_catalog_path(self, tid, extend, page, limit):
        params = {
            "kind": tid,
            "sort": "trending",
            "page": str(page),
            "limit": str(limit),
        }
        self._apply_filters(params, extend)
        return "/v1/browse/catalog?" + urllib.parse.urlencode(params)

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        """搜索内容

        key: 搜索关键词
        pg: 页码
        使用站点真实搜索: query_mode=fast_v3 + search_fields=all
        """
        page = int(pg) if pg else 1
        limit = 30
        params = {
            "q": key,
            "query_mode": "fast_v3",
            "search_fields": "all",
            "page": str(page),
            "limit": str(limit),
        }
        path = "/v1/browse/catalog?" + urllib.parse.urlencode(params)
        data = self._api_get(path)

        cards = data.get("cards", []) or []
        videos = [self._parse_card(c) for c in cards if c.get("id")]

        pagecount = self._estimate_search_pagecount(key, page, limit, cards)
        total = pagecount * limit

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": limit,
            "total": total,
        }

    def _estimate_search_pagecount(self, key, page, limit, cards):
        """估算搜索总页数 (探测结果带缓存)"""
        if len(cards) < limit:
            return page
        params = {
            "q": key,
            "query_mode": "fast_v3",
            "search_fields": "all",
            "page": str(page + 1),
            "limit": "1",
        }
        probe_path = "/v1/browse/catalog?" + urllib.parse.urlencode(params)
        return page + 1 if self._has_next_page(probe_path) else page

    # ========== 详情 ==========

    def detailContent(self, ids):
        """获取视频详情 (含全部线路与选集)

        ids[0]: 卡片 ID (av_ 开头长字符串)
        播放源: 取首集 token 的 resolve 结果, 全部线路写入 vod_play_from
        剧集地址: 每集以 "集名$token@@线路id" 形式占位, 播放时按所选线路解析
        """
        if not ids:
            return {"list": []}

        vid = ids[0]
        got = self._get_detail(vid)
        if not got:
            return {"list": []}
        detail, episodes = got

        # 基本信息
        title = detail.get("title", "") or ""
        pic = detail.get("poster_url", "") or self.default_pic
        content = detail.get("description", "") or ""
        actors = detail.get("actors", [])
        actor = " / ".join(actors[:20]) if actors else ""
        directors = detail.get("directors", [])
        director = " / ".join(directors[:10]) if directors else ""
        year = str(detail.get("year", "")) if detail.get("year") else ""
        area = detail.get("area", "") or ""
        genres = detail.get("genres", [])
        type_name = " / ".join(genres[:5]) if genres else ""

        # 播放源与选集
        play_from = []
        play_url = []

        def extract_episodes(episodes, line_id):
            """根据线路 id 生成 "集名$token@@线路id" 播放列表"""
            ep_list = []
            suffix = "@@{0}".format(line_id) if line_id else ""
            for ep in episodes:
                ep_title = ep.get("title", "") or ""
                if not ep_title:
                    num = ep.get("number")
                    if num is not None:
                        ep_title = "第{0}集".format(num)
                    else:
                        ep_title = "播放"
                token = ep.get("token", "")
                if not token:
                    continue
                ep_list.append("{0}${1}{2}".format(ep_title, token, suffix))
            return ep_list

        # 用第一集 token 预拉取线路列表 (同一部剧各集线路一致)
        first_token = ""
        for ep in episodes:
            if ep.get("token"):
                first_token = ep.get("token")
                break

        valid_lines = []
        if first_token:
            line_options = self._get_line_options(first_token)
            valid_lines = self._sort_lines(line_options)

        if valid_lines:
            for line in valid_lines:
                line_name = line.get("label") or line.get("provider_name") or "默认线路"
                line_id = line.get("id") or line.get("playback_source_id") or ""
                play_from.append(line_name)
                ep_list = extract_episodes(episodes, line_id)
                if ep_list:
                    play_url.append("#".join(ep_list))
                else:
                    play_url.append("")

        # 无线路数据兜底
        if not play_from:
            play_from.append("默认线路")
            ep_list = extract_episodes(episodes, "")
            if ep_list:
                play_url.append("#".join(ep_list))
            else:
                play_url.append("播放${0}/player/{1}".format(self.site_url, vid))

        result = [{
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area,
            "vod_type": type_name,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]
        return {"list": result}

    # ========== 播放 ==========

    def playerContent(self, flag, id, vipFlags):
        """获取播放链接

        id 格式: 集名$episode_token@@线路id (从 vod_play_url 拆分而来)
        flag: 当前选中的播放源名称 (对应线路 label, 如 "1080P-官方V")
        逻辑:
          1) 从 id 中拆出 token 与用户指定的线路 id
          2) GET /v1/playback/resolve/{token} 获取所有线路 (缓存)
          3) 优先使用指定线路; 无效则按权重自动 fallback
          4) m3u8/mp4 直链线路直接返回
          5) resolve_ticket 官方线路 POST resolve-line 换取真实地址
        """
        raw_id = id
        if "$" in raw_id:
            raw_id = raw_id.split("$")[-1]
        raw_id = raw_id.strip()

        token = raw_id
        selected_line = ""
        if "@@" in token:
            token, selected_line = token.split("@@", 1)
        token = token.strip()

        if not token:
            return {"parse": 1, "url": id, "header": self.headers}

        # 直链直接返回 (资源类线路)
        if token.startswith("http") and ('.m3u8' in token or '.mp4' in token):
            return {
                "parse": 0,
                "url": token,
                "header": self._play_header(),
            }

        # 非 token 则交给嗅探
        if not token.startswith("YJ-"):
            return {"parse": 1, "url": token, "header": self.headers}

        line_options = self._get_line_options(token)
        if not line_options:
            return {"parse": 1, "url": id, "header": self.headers}

        sorted_lines = self._sort_lines(line_options, selected_line)

        # 遍历尝试, 直到拿到可用真实地址
        for line in sorted_lines:
            raw_url = line.get("url", "")
            if not raw_url:
                continue
            url_kind = line.get("url_kind", "")

            # 资源类直链 (url_kind 为 m3u8/mp4 等且为 http)
            if (url_kind in ["m3u8", "mp4", "hls"] or "m3u8" in raw_url) and raw_url.startswith("http"):
                if self._is_valid_video_url(raw_url):
                    self._cache_line_url(token, line, raw_url)
                    return {
                        "parse": 0,
                        "url": raw_url,
                        "header": self._play_header(),
                    }

            # resolve_ticket 类型: 换取真实地址 (仅解析本次选中的线路, 保证播放速度)
            if url_kind == "resolve_ticket" or raw_url.startswith("resolve://"):
                ticket = raw_url.replace("resolve://", "")
                if not ticket:
                    continue
                payload = {
                    "ticket": ticket,
                    "line": line.get("playback_source_id", ""),
                    "provider_id": line.get("provider_id", ""),
                    "play_from": line.get("play_from", ""),
                }
                try:
                    line_data = self._api_post("/v1/playback/resolve-line", payload)
                    line_info = line_data.get("line", {})
                    real_url = line_info.get("url", "")
                except Exception:
                    continue
                if real_url and self._is_valid_video_url(real_url):
                    self._cache_line_url(token, line, real_url)
                    return {
                        "parse": 0,
                        "url": real_url,
                        "header": self._play_header(),
                    }

        # 兜底: 所有线路均失败则回到站点播放页 webview 嗅探
        return {
            "parse": 1,
            "url": "{0}/player/{1}".format(self.site_url, self._normalize_vid(token.replace("YJ-", ""))),
            "header": self.headers
        }

    def _cache_line_url(self, token, line, url):
        """缓存已解析的线路地址 (token + 线路id -> 真实URL), 同集同线路不再重复解析"""
        line_id = line.get("id") or line.get("playback_source_id") or ""
        if line_id:
            self._cache_set("line:{0}:{1}".format(token, line_id), url, 300)