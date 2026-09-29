# -*- coding: utf-8 -*-
"""
龙江影院 (https://ljvod.com) - TVBox 爬虫源 (maccms, tpl13 模板)
================================================================
接口：homeContent / categoryContent(含二级分类筛选) / detailContent(懒加载)
      / playerContent(按需解析 m3u8 直链 + 下一集预取) / searchContent

站点特性（已实测确认）：
1. 详情路由 /show/{短码}/ 与播放路由 /play/{vid}-{sid}-{nid}/ 均使用
   maccms 混淆短码，数字 id / 拼音 slug 均不可直达，必须从页面解析
2. 播放链路：详情页 -> 播放页内 player_xxxx JSON，其 url 字段即真实
   m3u8 直链，且 JSON 自带 url_next（下一集直链），可零成本预取
3. 分类页：/type/{id}/（第1页），翻页 /type/{id}-{n}/，总数可从
   分页区"尾页"链接提取；一级分类页为聚合页，二级分类页才是列表页
4. 搜索：/search/{kw}-------------/ 搜索页可用，直接解析即可得到短码；
   maccms suggest 接口(id=1)可做存在性快速校验与关键词补全
5. m3u8 直链无防盗链，播放 header 携带 UA/Referer 双保险

性能优化（加载 + 播放双提速）：
- 多级缓存：首页10分钟 / 分类5分钟 / 详情5分钟(失败30秒) / 搜索3分钟 / 播放15分钟
- 全链路短超时(8s/5s/4s) + 快速重试(0.2s) + 429限流等待(2s)
- 连接池复用(HTTPAdapter) + keep-alive + gzip 自动解压
- 详情页懒加载：不再预解析所有集数 m3u8，秒开
- playerContent 按需解析 + 缓存，命中后立即后台预取下一集(url_next)
- 播放多源回退：主源失效时并行尝试详情页其他线路(量子等)
"""

import re
import json
import time
import threading
import sys
from urllib.parse import quote, urlencode

import requests
from requests.adapters import HTTPAdapter

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    ThreadPoolExecutor = None
    as_completed = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except ImportError:
    _BaseSpider = None


# ============================================================
# 常量
# ============================================================
HOST = "https://ljvod.com"

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

# 超时（秒）
TIMEOUT_PAGE = 8
TIMEOUT_API = 5
TIMEOUT_PLAY = 4

# 缓存 TTL（秒）
TTL_HOME = 600
TTL_CAT = 300
TTL_DETAIL_OK = 300
TTL_DETAIL_EMPTY = 30
TTL_SEARCH = 180
TTL_PLAY = 900

# 一级分类（type id 为 maccms 数字，模板稳定）
# 结构：一级分类 -> 二级分类（类型筛选）
CATS = [
    {"id": "1", "name": "电影", "subs": [
        ("5", "动作片"), ("6", "喜剧片"), ("7", "爱情片"),
        ("8", "科幻片"), ("9", "恐怖片"), ("10", "剧情片"),
        ("11", "战争片"), ("22", "纪录片"), ("33", "动画片"),
    ]},
    {"id": "2", "name": "连续剧", "subs": [
        ("12", "国产剧"), ("13", "香港剧"), ("14", "台湾剧"),
        ("15", "日本剧"), ("16", "韩国剧"), ("17", "欧美剧"),
        ("18", "海外剧"), ("19", "泰国剧"),
    ]},
    {"id": "3", "name": "综艺", "subs": [
        ("23", "内地综艺"), ("24", "港台综艺"),
        ("25", "日韩综艺"), ("26", "欧美综艺"),
    ]},
    {"id": "4", "name": "动漫", "subs": [
        ("28", "国产动漫"), ("29", "港台动漫"),
        ("30", "日韩动漫"), ("31", "欧美动漫"), ("32", "海外动漫"),
    ]},
    {"id": "27", "name": "短剧", "subs": []},
    {"id": "20", "name": "理论片", "subs": []},
]


def _build_filters(cat):
    """构建筛选器：类型(二级分类) / 排序"""
    subs = [{"n": name, "v": slug} for slug, name in cat["subs"]]
    filters = [{
        "key": "class", "name": "类型",
        "value": [{"n": "全部", "v": ""}] + subs,
    }]
    filters.append({
        "key": "by", "name": "排序",
        "value": [
            {"n": "最新", "v": ""},
            {"n": "最热", "v": "hot"},
            {"n": "推荐", "v": "rec"},
        ],
    })
    return filters


# 全部分类 + 筛选器
ALL_CLASSES = [{"type_id": c["id"], "type_name": c["name"], "filter": 1} for c in CATS]
ALL_FILTERS = {c["id"]: _build_filters(c) for c in CATS}


# ============================================================
# Spider 主类
# ============================================================
_Base = _BaseSpider if _BaseSpider is not None else object


class Spider(_Base):
    siteUrl = HOST
    headers = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': HOST + '/',
    }

    # ===== 初始化 =====
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.headers['Connection'] = 'keep-alive'
        self.session.verify = False
        adapter = HTTPAdapter(
            pool_connections=20, pool_maxsize=40,
            max_retries=0, pool_block=False,
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # 缓存容器 + 锁
        self._lock = threading.Lock()
        self._home_cache = []
        self._home_cache_time = 0
        self._cat_cache = {}
        self._detail_cache = {}
        self._search_cache = {}
        self._play_cache = {}
        self._prefetching = set()

    def init(self, extend=""):
        self.extend = extend or ""

    # ===== 网络工具 =====
    def _get(self, url, referer='', timeout=TIMEOUT_PAGE):
        headers = {'Connection': 'keep-alive'}
        if referer:
            headers['Referer'] = referer
        for attempt in range(2):
            try:
                r = self.session.get(url, timeout=timeout, headers=headers)
                if r.status_code == 429:
                    time.sleep(2.0)
                    continue
                r.raise_for_status()
                r.encoding = 'utf-8'
                return r
            except Exception:
                if attempt == 0:
                    time.sleep(0.2)
                else:
                    return None
        return None

    def _get_text(self, url, referer='', timeout=TIMEOUT_PAGE):
        r = self._get(url, referer, timeout)
        return r.text if r is not None else ""

    # ===== 缓存 =====
    @staticmethod
    def _cache_get(cache, key, ttl=None):
        item = cache.get(key)
        if item and time.time() - item[0] < (ttl if ttl is not None else item[2]):
            return item[1]
        return None

    @staticmethod
    def _cache_set(cache, key, value, ttl=TTL_CAT):
        if len(cache) > 512:
            cache.clear()
        cache[key] = (time.time(), value, ttl)

    # ===== HTML 解析 =====
    @staticmethod
    def _soup(html):
        if not html or BeautifulSoup is None:
            return None
        try:
            return BeautifulSoup(html, 'lxml')
        except Exception:
            try:
                return BeautifulSoup(html, 'html.parser')
            except Exception:
                return None

    @staticmethod
    def _abs(u):
        u = (u or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return HOST + u
        if not u.startswith('http'):
            return HOST + '/' + u
        return u

    @staticmethod
    def _extract_id(href):
        # 详情链接 /show-{短码}/，短码由 maccms 混淆生成（4字符左右）
        m = re.search(r'/show-([^/]+)/', (href or '').strip())
        return m.group(1) if m else None

    @staticmethod
    def _clean_name(raw):
        if not raw:
            return raw
        return re.sub(r'\s*[（(]\s*\d{4}\s*[）)]\s*$', '', raw.strip())

    @staticmethod
    def _pick_pic(el):
        if el is None:
            return ''
        inner = el.select_one('.poster .lazyload') or el.select_one('.lazyload')
        if inner is not None:
            val = str(inner.get('data-original') or '').strip()
            if val:
                return Spider._abs(val)
        for attr in ('data-original', 'data-src', 'src'):
            val = str(el.get(attr) or '').strip()
            if val:
                return Spider._abs(val)
        return ''

    @staticmethod
    def _pick_remarks(a):
        """备注：优先卡片 .pic-text .time，其次标题正则"""
        box = a.find_parent('li') or a
        time_el = box.select_one('.pic-text .time')
        if time_el is not None:
            t = time_el.get_text(strip=True)
            if t:
                return t
        title = str(a.get('title') or '') + str(a.get_text(' ', strip=True))
        m = re.search(
            r'(更新至[^\s]{0,12}|更新到[^\s]{0,12}|全\d+集|全集'
            r'|已完结|正片|HD中字|HD国语|TC中字)', title
        )
        return m.group(1) if m else ''

    def _parse_cards(self, html, limit=36):
        """通用卡片解析（首页 / 分类 / 搜索共用）"""
        if not html:
            return []
        soup = self._soup(html)
        if soup is None:
            return []
        items = {}
        for a in soup.select('a[href*="/show-"]'):
            href = str(a.get('href') or '')
            vid = self._extract_id(href)
            title = str(a.get('title') or '').strip()
            if not title:
                h4 = a.select_one('h4')
                title = h4.get_text(' ', strip=True) if h4 else ''
            title = self._clean_name(title)
            if not vid or not title or vid in items:
                continue
            pic = self._pick_pic(a)
            if not pic:
                continue  # 跳过无图条目（文字列表行）
            items[vid] = {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': self._pick_remarks(a),
            }
        return list(items.values())[:limit]

    # ============================================================
    # 首页
    # ============================================================
    def _fetch_home(self):
        html = self._get_text(HOST)
        cards = self._parse_cards(html, limit=60)
        if cards:
            with self._lock:
                self._home_cache = cards
                self._home_cache_time = int(time.time())
        return cards

    def homeContent(self, filter=False):
        now = int(time.time())
        vod_list = []
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                vod_list = self._home_cache[:60]
        if not vod_list:
            vod_list = self._fetch_home()[:60]
        return {
            "class": ALL_CLASSES,
            "filters": ALL_FILTERS,
            "list": vod_list,
        }

    def homeVideoContent(self):
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                return {"list": self._home_cache[:60]}
        return {"list": self._fetch_home()[:60]}

    # ============================================================
    # 分类列表
    # ============================================================
    def _empty_category(self, page=1):
        return {"list": [], "page": page, "pagecount": 1, "limit": 36, "total": 0}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg or 1))
            sub = ''
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}
                sub = str(ext.get('class') or '').strip()

            # 二级分类（类型筛选）命中时使用二级 type id
            type_id = sub or str(tid)

            ckey = "%s|%d" % (type_id, page)
            cached = self._cache_get(self._cat_cache, ckey, TTL_CAT)
            if cached is not None:
                return cached

            url = f"{HOST}/type-{type_id}/" if page == 1 else f"{HOST}/type-{type_id}-{page}/"

            html = self._get_text(url)
            if not html:
                return self._empty_category(page)

            # 分页总数：优先"尾页"链接，其次"当前/总数"
            pagecount = 1
            m = re.search(r'href="/type-\d+?-(\d+)/"[^>]*title="尾页"', html)
            if m:
                pagecount = int(m.group(1))
            else:
                m = re.search(r'>(\d+)/(\d+)<', html)
                if m:
                    pagecount = int(m.group(2))
            pagecount = max(pagecount, page)

            vod_list = self._parse_cards(html, limit=36)

            result = {
                "list": vod_list,
                "page": page,
                "pagecount": pagecount,
                "limit": 36,
                "total": pagecount * 36,
            }
            self._cache_set(self._cat_cache, ckey, result, TTL_CAT)
            return result
        except Exception:
            return self._empty_category(page)

    # ============================================================
    # 详情页（懒加载）
    # ============================================================
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vid = str(ids[0]).split(',')[0].strip()
        if not vid:
            return {"list": []}

        cached = self._cache_get(self._detail_cache, vid, None)
        if cached is not None:
            return cached

        result = self._fetch_detail(vid)
        ttl = TTL_DETAIL_OK if result.get("list") else TTL_DETAIL_EMPTY
        self._cache_set(self._detail_cache, vid, result, ttl)

        if result.get("list"):
            self._prefetch_first_play(result["list"][0])
        return result

    def _fetch_detail(self, vid):
        html = self._get_text(f"{HOST}/show-{vid}/")
        if not html:
            return {"list": []}
        soup = self._soup(html)
        if soup is None:
            return {"list": []}

        # --- 基本信息 ---
        name = ''
        type_name = ''
        h1 = soup.select_one('h1.title')
        if h1 is not None:
            labels = [a.get_text(strip=True) for a in h1.select('a.label')]
            if labels:
                type_name = '/'.join(labels)
            name_el = h1.select_one('span.font20')
            if name_el is not None:
                name = self._clean_name(name_el.get_text(' ', strip=True))
            if not name:
                name = self._clean_name(h1.get_text(' ', strip=True))
        if not name:
            t1 = soup.select_one('.info h1') or soup.title
            if t1 is not None:
                name = self._clean_name(t1.get_text(' ', strip=True))

        pic = self._pick_pic(soup.select_one('.vod-desc .poster'))

        # --- 元信息（主演/导演/类型/语言/地区/年份） ---
        meta = {}
        key_map = {'导演': 'director', '主演': 'actor', '类型': 'type',
                   '语言': 'lang', '地区': 'area', '年份': 'year', '状态': 'remarks'}
        for li in soup.select('.vod-desc .info ul li'):
            text = li.get_text(' ', strip=True)
            for label, key in key_map.items():
                if text.startswith(label) and not meta.get(key):
                    val = text[len(label):].strip(' ：:')
                    if val:
                        meta[key] = val
        director = meta.get('director', '')
        actor = meta.get('actor', '')
        area = meta.get('area', '')
        lang = meta.get('lang', '')
        year = meta.get('year', '')

        # --- 简介 ---
        content = ''
        intro = soup.select_one('.intro span')
        if intro is not None:
            content = intro.get_text(' ', strip=True)
        if not content:
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc is not None:
                content = str(meta_desc.get('content') or '').strip()[:300]

        remarks = meta.get('remarks', '')
        if not remarks:
            remarks = self._pick_remarks_from_text(html)

        # --- 播放源与集数 ---
        play_groups = []
        for box in soup.select('.wi-play-list-box'):
            head = box.select_one('.wi-play-list-head h2.title')
            src_name = head.get_text(strip=True) if head is not None else '线路'
            eps = []
            seen = set()
            for a in box.select('a.wi-play-list-btn[href*="/play-"]'):
                ep_url = self._abs(str(a.get('href') or ''))
                if not ep_url or ep_url in seen:
                    continue  # 头部快捷按钮与列表按钮会重复，按 URL 去重
                seen.add(ep_url)
                ep_name = a.get_text(strip=True) or '播放'
                eps.append((ep_name, ep_url))
            if eps:
                play_groups.append((src_name, eps))

        play_from, play_url = '', ''
        for src_name, eps in play_groups:
            ep_parts = [f"{n}${u}" for n, u in eps]
            play_from = (play_from + '$$$' + src_name) if play_from else src_name
            play_url = (play_url + '$$$' + '#'.join(ep_parts)) if play_url else '#'.join(ep_parts)

        detail = {
            "vod_id": vid,
            "vod_name": name or f"视频{vid}",
            "vod_pic": pic or HOST,
            "type_name": type_name,
            "vod_remarks": remarks or '',
            "vod_year": year,
            "vod_area": area,
            "vod_lang": lang,
            "vod_director": director,
            "vod_actor": actor,
            "vod_content": content,
            "vod_play_from": play_from or '默认',
            "vod_play_url": play_url or '',
        }
        return {"list": [detail]}

    @staticmethod
    def _pick_remarks_from_text(html):
        m = re.search(
            r'(更新至\s*[\d]+集|更新到\s*[\d]+集|连载至\s*[\d]+集|全[\d]+集'
            r'|已完结|全集|正片|HD中字|HD国语|TC中字)', html
        )
        return m.group(1) if m else ''

    # ============================================================
    # 播放解析（m3u8 直链 + 下一集预取 + 多源回退）
    # ============================================================
    def _resolve_play(self, play_url):
        cached = self._cache_get(self._play_cache, play_url, TTL_PLAY)
        if cached:
            return cached
        real = ''
        try:
            text = self._get_text(play_url, referer=HOST + '/', timeout=TIMEOUT_PLAY)
            if text:
                m = re.search(r'var\s+player_\w+\s*=\s*(\{.*?\})\s*[;<]', text, re.S)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        u = (data.get('url') or '').replace('\\/', '/').strip()
                        if u:
                            real = self._abs(u)
                        # 播放页自带下一集直链，一并缓存实现秒切集
                        nxt = (data.get('url_next') or '').replace('\\/', '/').strip()
                        if nxt:
                            self._cache_set(
                                self._play_cache, play_url + '#next',
                                self._abs(nxt), TTL_PLAY,
                            )
                    except Exception:
                        pass
                if not real:
                    m2 = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', text)
                    if m2:
                        real = self._abs(m2.group(1).replace('\\/', '/'))
                if not real:
                    m3 = re.search(r'"url"\s*:\s*"(https?://[^"]+)"', text)
                    if m3:
                        u = m3.group(1).replace('\\/', '/').strip()
                        if '.m3u8' in u or '.mp4' in u:
                            real = self._abs(u)
        except Exception:
            real = ''
        if real:
            self._cache_set(self._play_cache, play_url, real, TTL_PLAY)
        return real

    def _first_play_url(self, vod):
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            for item in seg.split("#"):
                parts = item.split("$", 1)
                if len(parts) == 2 and parts[1]:
                    return parts[1]
        return None

    def _prefetch(self, play_url):
        """后台预取指定播放页的 m3u8（去重 + 并发保护）"""
        if not play_url:
            return
        with self._lock:
            if self._cache_get(self._play_cache, play_url, TTL_PLAY) or play_url in self._prefetching:
                return
            self._prefetching.add(play_url)

        def _job():
            try:
                self._resolve_play(play_url)
            except Exception:
                pass
            finally:
                with self._lock:
                    self._prefetching.discard(play_url)

        threading.Thread(target=_job, daemon=True).start()

    def _prefetch_first_play(self, vod):
        """详情返回后，后台预取第一集 + 其下一集(url_next 自带)"""
        target = self._first_play_url(vod)
        if not target:
            return

        def _job():
            try:
                m3u8 = self._resolve_play(target)
                if m3u8:
                    self._prefetch_next(target)
            except Exception:
                pass
            finally:
                with self._lock:
                    self._prefetching.discard(target)

        with self._lock:
            if target in self._prefetching:
                return
            self._prefetching.add(target)
        threading.Thread(target=_job, daemon=True).start()

    def _prefetch_next(self, play_url):
        """确保下一集 m3u8 已缓存（url_next 通常在解析当前集时已顺带缓存）"""
        if self._cache_get(self._play_cache, play_url + '#next', TTL_PLAY):
            return
        try:
            text = self._get_text(play_url, referer=HOST + '/', timeout=TIMEOUT_PLAY)
            if not text:
                return
            m = re.search(r'var\s+player_\w+\s*=\s*(\{.*?\})\s*[;<]', text, re.S)
            if not m:
                return
            data = json.loads(m.group(1))
            nxt = (data.get('url_next') or '').replace('\\/', '/').strip()
            if nxt:
                nxt = self._abs(nxt)
                self._cache_set(self._play_cache, play_url + '#next', nxt, TTL_PLAY)
        except Exception:
            pass

    def _play_payload(self, playurl):
        is_m3u8 = '.m3u8' in playurl.lower()
        return {
            "parse": 0,
            "playUrl": "",
            "url": playurl,
            "header": {
                "User-Agent": UA,
                "Referer": HOST + "/",
                "Origin": HOST,
            },
            "format": "application/x-mpegURL" if is_m3u8 else "",
            "contentType": "application/x-mpegURL" if is_m3u8 else "",
        }

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}
        play_url = self._abs(str(id))

        cached = self._cache_get(self._play_cache, play_url, TTL_PLAY)
        if cached:
            self._prefetch_next(play_url)
            return self._play_payload(cached)

        m3u8 = self._resolve_play(play_url)
        if m3u8:
            self._prefetch_next(play_url)
            return self._play_payload(m3u8)

        # 主源失效：并行尝试详情页其他线路
        alts = self._alt_play_urls(play_url)
        if alts and ThreadPoolExecutor is not None:
            try:
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futs = [ex.submit(self._resolve_play, u) for u in alts]
                    for f in as_completed(futs, timeout=TIMEOUT_PLAY):
                        u = f.result(timeout=TIMEOUT_PLAY)
                        if u:
                            self._cache_set(self._play_cache, play_url, u, TTL_PLAY)
                            return self._play_payload(u)
            except Exception:
                pass
        else:
            for u in alts:
                m = self._resolve_play(u)
                if m:
                    self._cache_set(self._play_cache, play_url, m, TTL_PLAY)
                    return self._play_payload(m)

        return {
            "parse": 1,
            "playUrl": "",
            "url": play_url,
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }

    def _alt_play_urls(self, play_url, limit=6):
        """从详情缓存中提取当前集在其他线路的播放地址"""
        m = re.search(r'/play-([^/]+)-(\d+)-(\d+)/', play_url)
        if not m:
            return []
        vid, sid, nid = m.group(1), m.group(2), m.group(3)
        cached = self._cache_get(self._detail_cache, vid, TTL_DETAIL_OK)
        if not cached or not cached.get("list"):
            return []
        vod = cached["list"][0]
        out = []
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            for item in seg.split("#"):
                parts = item.split("$", 1)
                if len(parts) == 2 and parts[1]:
                    u = parts[1]
                    if u != play_url and f"-{sid}-{nid}/" in u:
                        out.append(u)
                        if len(out) >= limit:
                            return out
        return out

    # ============================================================
    # 搜索（搜索页解析为主 + suggest 补全 + 分类爬取兜底）
    # ============================================================
    def _search_suggest(self, kw):
        """suggest 接口：返回数字 id 无法直达详情，仅用于关键词补全校验"""
        try:
            text = self._get_text(
                f"{HOST}/index.php/ajax/suggest?mid=1&wd={quote(kw)}",
                referer=HOST + '/', timeout=TIMEOUT_API,
            )
            if not text or not text.strip().startswith('{'):
                return None
            data = json.loads(text)
            if data.get('code') != 1:
                return None
            return [str(it.get('name') or '') for it in data.get('list') or []]
        except Exception:
            return None

    def _search_page(self, kw, page):
        """站内搜索页：/search-{kw}-------------/，直接得到可用的短码"""
        page_suffix = f"-{page}" if page > 1 else ""
        url = f"{HOST}/search-{kw}{page_suffix}-------------/"
        html = self._get_text(url, referer=HOST + '/', timeout=TIMEOUT_API)
        if not html:
            return None
        # 无结果时该模板降级展示“热门推荐”，必须确认是真正的搜索结果页
        if 'System Error' in html or not re.search(r'<title>[^<]*搜索结果[^<]*</title>', html):
            return None
        cards = self._parse_cards(html, limit=36)
        if cards:
            pagecount = 1
            m = re.search(r'href="/search[^"]*?-(\d+)-------------/"[^>]*title="尾页"', html)
            if m:
                pagecount = int(m.group(1))
            return {"list": cards, "pagecount": pagecount}
        return None

    def _search_by_scrape(self, raw, page):
        """兜底：分类爬取 + 分词模糊匹配（搜索页/suggest 均失效时）"""
        if page > 1:
            return None
        pages = (1, 2, 3)  # 控制请求量，避免触发风控

        def _fetch_cat(args):
            type_id, p = args
            url = f"{HOST}/type-{type_id}/" if p == 1 else f"{HOST}/type-{type_id}-{p}/"
            html = self._get_text(url, timeout=TIMEOUT_API)
            return self._parse_cards(html, limit=36)

        all_cards = []
        if ThreadPoolExecutor is not None:
            tasks = [(c['id'], p) for c in CATS for p in pages]
            with ThreadPoolExecutor(max_workers=3) as ex:
                futs = [ex.submit(_fetch_cat, t) for t in tasks]
                for f in as_completed(futs, timeout=TIMEOUT_API * 4):
                    try:
                        all_cards.extend(f.result(timeout=TIMEOUT_API))
                    except Exception:
                        continue
        else:
            for c in CATS:
                for p in pages:
                    try:
                        time.sleep(0.3)
                        url = f"{HOST}/type-{c['id']}/" if p == 1 else f"{HOST}/type-{c['id']}-{p}/"
                        html = self._get_text(url, timeout=TIMEOUT_API)
                        all_cards.extend(self._parse_cards(html, limit=36))
                    except Exception:
                        continue

        matched = self._filter_by_keyword(all_cards, raw, limit=24)
        # 去重（同 vid 只保留一个，多分类页会重复）
        seen, dedup = set(), []
        for it in matched:
            if it.get('vod_id') not in seen:
                seen.add(it.get('vod_id'))
                dedup.append(it)
        return {'list': dedup} if dedup else None

    @staticmethod
    def _filter_by_keyword(cards, raw, limit=24):
        """分词模糊匹配 + 排序"""
        raw = (raw or '').lower().replace(' ', '').strip()
        if not raw:
            return cards[:limit]
        if len(raw) <= 2:
            tokens = [raw]
        else:
            tokens = [raw[i:i + 2] for i in range(0, len(raw) - 1)]
        tokens += list(raw)

        def score(name):
            name = (name or '').lower().replace(' ', '')
            if not name:
                return 0
            if raw in name:
                return 100
            return sum(1 for t in tokens if t in name)

        matched = [(score(c.get('vod_name') or ''), c) for c in cards]
        matched = [c for s, c in matched if s > 0]
        matched.sort(key=lambda c: score(c.get('vod_name') or ''), reverse=True)
        return matched[:limit]

    def searchContent(self, keyword, quick=False, pg=1):
        """多策略搜索：站内搜索页 -> suggest 关键词修正 -> 分类爬取兜底"""
        raw = (keyword or '').strip().lower()
        if not raw:
            return {"list": [], "msg": "请输入搜索关键词"}
        kw = quote(raw)

        page = int(pg or 1)
        ckey = "%s|%s" % (page, raw)
        cached = self._cache_get(self._search_cache, ckey, TTL_SEARCH)
        if cached is not None:
            return cached

        # 策略0：站内搜索页（成功率最高，直出短码）
        result = self._search_page(kw, page)
        if not result:
            time.sleep(1.0)  # 该站有短时风控，连续请求需错峰
            result = self._search_page(kw, page)
        if not result:
            time.sleep(2.0)
            result = self._search_page(kw, page)

        # 策略1：suggest 补全关键词后精确搜索（轻量，1次suggest + 至多3次搜索页）
        if not result:
            names = self._search_suggest(raw)
            if names:
                # 优先选择包含原关键词的候选名，避免关联词替换丢结果
                candidates = [n for n in names if raw in str(n).lower()] or names
                for nm in candidates[:3]:
                    nm = str(nm).strip()
                    if nm and nm.lower() != raw:
                        time.sleep(1.0)
                        r2 = self._search_page(quote(nm), page)
                        if r2:
                            result = r2
                            break

        # 策略2：分类爬取兜底（最后手段，按需才触发）
        if not result:
            result = self._search_by_scrape(raw, page)

        if result and result.get("list"):
            self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
            return result

        result = {"list": [], "msg": "未找到相关内容，请尝试其他关键词或通过分类浏览"}
        self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
        return result

    # ============================================================
    # 本地代理 & 清理
    # ============================================================
    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def close(self):
        self.destroy()


# ============================================================
# 本地测试
# ============================================================
if __name__ == '__main__':
    s = Spider()
    action = sys.argv[1] if len(sys.argv) > 1 else 'home'
    if action == 'home':
        print(json.dumps(s.homeContent(), ensure_ascii=False)[:1000])
    elif action == 'category':
        tid = sys.argv[2] if len(sys.argv) > 2 else '1'
        pg = sys.argv[3] if len(sys.argv) > 3 else '1'
        cl = sys.argv[4] if len(sys.argv) > 4 else ''
        print(json.dumps(
            s.categoryContent(tid, pg, False, {'class': cl} if cl else {}),
            ensure_ascii=False
        )[:1000])
    elif action == 'detail':
        vid = sys.argv[2] if len(sys.argv) > 2 else 'LCsO'
        r = s.detailContent(vid)
        d = r['list'][0] if r.get('list') else {}
        print(json.dumps(d, ensure_ascii=False)[:1000])
    elif action == 'play':
        pid = sys.argv[2] if len(sys.argv) > 2 else ''
        print(json.dumps(s.playerContent('', pid, []), ensure_ascii=False)[:600])
    elif action == 'search':
        kw = sys.argv[2] if len(sys.argv) > 2 else '狂飙'
        print(json.dumps(s.searchContent(kw), ensure_ascii=False)[:800])
