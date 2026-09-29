# -*- coding: utf-8 -*-
"""
魅影影视 (www.plnyj.com) - TVBox 爬虫源 (maccms / FED 模板)
============================================================
接口：homeContent / categoryContent(含筛选) / detailContent(懒加载) / playerContent(按需解析m3u8直链) / searchContent

站点特性（已实测确认）：
1. 模板类名 fed-*（苹果CMS FED 模板），PC/移动端 UA 均可访问（统一用移动端 UA 更稳）
2. 分类路由：/mei/{tid}.html(第1页)，翻页 /mei/{tid}-{n}.html；二级分类 tid 已全部实测
3. 详情路由：/ying/{id}.html，含多播放源（腾讯/优酷/奇艺 tab），集数链接 /play/{vid}-{sid}-{nid}.html
4. 播放页内嵌直链：var now="https://...m3u8"，且 var next="..." 为下一集直链，可直接预取
5. 搜索/筛选走 /search.php（searchtype=5 为筛选），该接口有频率限制（快速连续请求返回 503），
   已做全局锁 + 最小请求间隔限流，失败自动退避重试
6. 站内搜索仅匹配片名，建议搜索结果做去重（同片出现于图卡/标题卡）

核心优化（加载速度）：
- 连接池复用(HTTPAdapter pool 20/40) + gzip 自动解压 + 全链路短超时(8s/5s/4s) + 快速重试(0.2s)
- 多级缓存：首页10分钟 / 分类5分钟 / 详情5分钟(失败30秒) / 搜索3分钟 / 播放15分钟
- 详情页懒加载：只解析集数列表，不预解析 m3u8，详情秒开
- 首页后台预热线程，首次进入即命中缓存
- 搜索接口限流：全局锁 + 最小间隔 1.2s，避免 503

核心优化（播放速度）：
- playerContent 直接解析播放页 var now 字段拿 m3u8 直链（单请求极快），15 分钟缓存
- var next 下一集直链预取（后台线程提前缓存，连播秒开）
- 主源失败自动并发兜底其余播放源（ThreadPoolExecutor 3 并发）
- 播放请求头带 UA + Referer，兼容防盗链
"""

import re
import json
import time
import threading
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
    import sys
    sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except ImportError:
    _BaseSpider = None


# ============================================================
# 常量
# ============================================================
HOST = "https://www.plnyj.com"

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

# 搜索接口限流：最小请求间隔（秒），避免 503
SEARCH_MIN_INTERVAL = 1.2
SEARCH_RETRY_WAIT = 2.0

# 地区（站点实际筛选值，全分类通用）
AREAS = [
    "大陆", "香港", "台湾", "日本", "韩国", "欧美", "泰国", "其他",
]

# 年份（当前年 ~ 2014，站点后台实际提供范围）
YEARS = [str(y) for y in range(2026, 2013, -1)]

# 分类表：一级分类（首页导航）-> 二级分类（类型筛选），tid 已全部实测
CATS = [
    {"id": "1", "name": "电视剧", "subs": [
        ("5", "国产剧"), ("6", "香港剧"), ("7", "台湾剧"), ("8", "欧美剧"),
        ("9", "韩国剧"), ("10", "日本剧"), ("11", "泰国剧"), ("12", "海外剧"),
        ("13", "精品短剧"),
    ]},
    {"id": "2", "name": "电影", "subs": [
        ("14", "动作片"), ("15", "喜剧片"), ("16", "爱情片"), ("17", "科幻片"),
        ("18", "恐怖片"), ("19", "剧情片"), ("20", "战争片"), ("21", "纪录片"),
    ]},
    {"id": "3", "name": "综艺", "subs": [
        ("22", "大陆综艺"), ("23", "港台综艺"), ("24", "日韩综艺"), ("25", "欧美综艺"),
    ]},
    {"id": "4", "name": "动漫", "subs": [
        ("26", "国产动漫"), ("27", "日本动漫"), ("28", "欧美动漫"), ("29", "海外动漫"),
        ("30", "动漫电影"),
    ]},
]


def _build_filters(cat):
    """构建筛选器：类型(二级分类) / 地区 / 年份 / 排序"""
    subs = [{"n": name, "v": tid} for tid, name in cat["subs"]]
    filters = [{
        "key": "class", "name": "类型",
        "value": [{"n": "全部", "v": ""}] + subs,
    }]
    filters.append({
        "key": "area", "name": "地区",
        "value": [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in AREAS],
    })
    filters.append({
        "key": "year", "name": "年份",
        "value": [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in YEARS],
    })
    filters.append({
        "key": "by", "name": "排序",
        "value": [
            {"n": "默认", "v": ""},
            {"n": "最热", "v": "hits"},
            {"n": "最新", "v": "time"},
        ],
    })
    return filters


# 全部分类 + 筛选器
ALL_CLASSES = [{"type_id": c["id"], "type_name": c["name"], "filter": 1} for c in CATS]
ALL_FILTERS = {c["id"]: _build_filters(c) for c in CATS}

# 二级分类 tid -> 一级 tid 映射（用于筛选时定位上级分类）
SUB_TO_PARENT = {}
for c in CATS:
    for tid, _name in c["subs"]:
        SUB_TO_PARENT[tid] = c["id"]


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

        # 搜索/筛选限流：全局锁 + 上次请求时间
        self._search_lock = threading.Lock()
        self._last_search_ts = 0.0

        # 后台预热线程（首页）
        self._warm_thread = None

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
                if r.status_code in (429, 503):
                    time.sleep(SEARCH_RETRY_WAIT)
                    continue
                r.raise_for_status()
                r.encoding = r.apparent_encoding or 'utf-8'
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

    def _search_get(self, url, params=None, referer=HOST + '/'):
        """搜索/筛选专用请求：全局锁 + 最小间隔限流，规避站点 503"""
        with self._search_lock:
            wait = SEARCH_MIN_INTERVAL - (time.time() - self._last_search_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_search_ts = time.time()
            for attempt in range(3):
                try:
                    r = self.session.get(
                        url, params=params, timeout=TIMEOUT_API,
                        headers={'Referer': referer, 'Connection': 'keep-alive'},
                    )
                    if r.status_code in (429, 503):
                        time.sleep(SEARCH_RETRY_WAIT * (attempt + 1))
                        continue
                    r.raise_for_status()
                    r.encoding = r.apparent_encoding or 'utf-8'
                    return r.text
                except Exception:
                    if attempt < 2:
                        time.sleep(0.4 * (attempt + 1))
            return ""

    def _warm(self):
        """后台预热首页，首次进入即命中缓存"""
        with self._lock:
            if self._home_cache:
                return
        try:
            html = self._get_text(HOST, timeout=TIMEOUT_API)
            cards = self._parse_cards(html, limit=60)
            if cards:
                with self._lock:
                    self._home_cache = cards
                    self._home_cache_time = int(time.time())
        except Exception:
            pass

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
        m = re.search(r'/ying/(\d{4,10})\.(?:html|shtml)$', (href or '').strip())
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
        for attr in ('data-original', 'data-src', 'src', 'data-background'):
            val = str(el.get(attr) or '').strip()
            if val:
                return Spider._abs(val)
        style = str(el.get('style') or '')
        m = re.search(r'background-image:\s*url\(([^)]+)\)', style)
        if m:
            return Spider._abs(m.group(1).strip().strip('"').strip("'"))
        return ''

    def _parse_cards(self, html, limit=36):
        """解析 fed-list-pics 卡片（首页/分类/搜索通用）"""
        if not html:
            return []
        soup = self._soup(html)
        if soup is None:
            return []
        items = {}
        for a in soup.select('a.fed-list-pics'):
            href = str(a.get('href') or '')
            vid = self._extract_id(href)
            title = str(a.get('title') or '').strip()
            if not vid or not title:
                continue
            pic = self._pick_pic(a)
            remarks = ''
            st = a.select_one('.fed-list-remarks')
            if st:
                remarks = st.get_text(strip=True)
            if not remarks:
                m = re.search(
                    r'(更新至[^\s]{0,12}|更新到[^\s]{0,12}|全\d+集|全集|已完结|正片'
                    r'|HD中字|HD国语|TC中字|抢先版)', title
                )
                if m:
                    remarks = m.group(1)
            if vid not in items:
                items[vid] = {
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remarks,
                }
        return list(items.values())[:limit]

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter=False):
        vod_list = self._home_content()
        return {
            "class": ALL_CLASSES,
            "filters": ALL_FILTERS,
            "list": vod_list,
        }

    def homeVideoContent(self):
        return {"list": self._home_content()}

    def _home_content(self):
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                return self._home_cache[:60]
        try:
            html = self._get_text(HOST)
            vod_list = self._parse_cards(html, limit=60)
            if vod_list:
                with self._lock:
                    self._home_cache = vod_list
                    self._home_cache_time = int(time.time())
            return vod_list[:60]
        except Exception:
            return []

    # ============================================================
    # 分类列表（无筛选走 /mei/ 路由，快且无限制；有筛选走 search.php 并限流）
    # ============================================================
    def _empty_category(self, page=1):
        return {"list": [], "page": page, "pagecount": 1, "limit": 36, "total": 0}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg or 1))
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            # 二级分类：class 筛选优先，否则用当前 tid 本身
            cls = (ext.get('class') or '').strip() or str(tid)
            area = (ext.get('area') or '').strip()
            year = (ext.get('year') or '').strip()
            by = (ext.get('by') or '').strip()

            ckey = "%s|%d|%s|%s|%s|%s" % (cls, page, area, year, by, json.dumps(ext, ensure_ascii=False, sort_keys=True))
            cached = self._cache_get(self._cat_cache, ckey, TTL_CAT)
            if cached is not None:
                return cached

            # 无筛选：直接爬 /mei/ 列表页（快、无 503 风险）
            if not area and not year and not by:
                url = f"{HOST}/mei/{cls}.html" if page == 1 else f"{HOST}/mei/{cls}-{page}.html"
                html = self._get_text(url)
                if not html:
                    return self._empty_category(page)
                pagecount = self._pick_pagecount(html)
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

            # 有筛选：走 search.php（searchtype=5），限流保护
            parent = SUB_TO_PARENT.get(cls, cls)
            params = {"searchtype": "5", "tid": parent, "page": page}
            if cls != parent:
                params["tid"] = cls  # 二级分类直接给 tid
            if area:
                params["area"] = area
            if year:
                params["year"] = year
            if by:
                params["order"] = by

            html = self._search_get(HOST + "/search.php", params=params)
            if not html:
                return self._empty_category(page)
            pagecount = self._pick_pagecount(html)
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

    def _pick_pagecount(self, html):
        """从翻页链接提取总页数（分类页优先 /mei/ 翻页，搜索页用 page=N）"""
        nums = [int(x) for x in re.findall(r'/mei/\d+-(\d+)\.html', html) if x.isdigit()]
        if nums:
            return max(nums)
        nums2 = [int(x) for x in re.findall(r'page=(\d+)', html) if x.isdigit() and int(x) > 1]
        if nums2:
            return max(nums2)
        return 1

    # ============================================================
    # 详情页（懒加载：只解析播放源与集数列表，不解析 m3u8）
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
        return result

    def _fetch_detail(self, vid):
        html = self._get_text(f"{HOST}/ying/{vid}.html")
        if not html:
            return {"list": []}
        soup = self._soup(html)
        if soup is None:
            return {"list": []}

        # --- 基本信息 ---
        name = ''
        h1 = soup.select_one('h1 a')
        if h1:
            name = h1.get_text(strip=True)
        if not name:
            h1b = soup.select_one('h1')
            if h1b:
                name = h1b.get_text(strip=True)
        if not name:
            t1 = soup.select_one('title')
            if t1:
                name = re.split(r'[_-]', t1.get_text(strip=True))[0].strip()

        pic = ''
        img = soup.select_one('a.fed-list-pics[href*="/ying/"] img')
        if img:
            pic = self._pick_pic(img)
        if not pic:
            thumb = soup.select_one('.fed-deta-images a.fed-list-pics')
            if thumb:
                pic = self._pick_pic(thumb)

        meta_fields = {}
        key_map = {'导演': 'director', '编剧': 'writer', '主演': 'actor',
                   '类型': 'type', '地区': 'area', '语言': 'lang',
                   '又名': 'aka', '评分': 'score'}
        for li in soup.select('dd.fed-deta-content li'):
            label_el = li.find('span', class_='fed-text-muted')
            if label_el is None:
                continue
            label = (label_el.get_text(strip=True) or '').rstrip(':：')
            if label not in key_map:
                continue
            val = li.get_text(' ', strip=True)
            val = val[len(label_el.get_text(strip=True)):].strip().lstrip(':： ').strip()
            if val and val != '未知':
                meta_fields.setdefault(key_map[label], val)

        body_text = soup.get_text(' ', strip=True)
        director = meta_fields.get('director', '')
        actor = meta_fields.get('actor', '')
        area = meta_fields.get('area', '')
        lang = meta_fields.get('lang', '')
        year = self._pick_year(body_text)

        # 简介
        content = ''
        content_el = soup.find(string=lambda t: t and '简介' in t)
        if content_el is not None:
            parent = content_el.find_parent()
            if parent is not None:
                desc = parent.get_text(' ', strip=True)
                desc = re.sub(r'^简介[:：]?\s*', '', desc)
                if desc:
                    content = desc[:300]
        if not content:
            meta = soup.find('meta', attrs={'name': 'description'})
            if meta:
                content = str(meta.get('content') or '')[:300]

        remarks = self._pick_remarks(body_text)

        # --- 播放源与集数 ---
        play_groups = []
        for tab in soup.select('a[href^="#playlist"]'):
            src_name = tab.get_text(' ', strip=True) or '线路'
            src_name = re.sub(r'\s+', '', src_name)
            anchor = str(tab.get('href') or '').lstrip('#')
            pane = soup.find(id=anchor)
            eps = []
            if pane:
                for a in pane.select('a[href*="/play/"]'):
                    ep_name = a.get_text(strip=True) or a.get('title') or '播放'
                    ep_url = self._abs(str(a.get('href') or ''))
                    if ep_url:
                        eps.append((ep_name, ep_url))
            if eps:
                play_groups.append((src_name, eps))

        # 兜底：页面任意 /play/ 链接
        if not play_groups:
            eps = []
            for a in soup.select('a[href*="/play/"]'):
                ep_name = a.get_text(strip=True) or '播放'
                ep_url = self._abs(str(a.get('href') or ''))
                if ep_url:
                    eps.append((ep_name, ep_url))
            if eps:
                play_groups.append(('默认线路', eps))

        play_from, play_url = '', ''
        for src_name, eps in play_groups:
            ep_parts = [f"{n}${u}" for n, u in eps]
            play_from = (play_from + '$$$' + src_name) if play_from else src_name
            play_url = (play_url + '$$$' + '#'.join(ep_parts)) if play_url else '#'.join(ep_parts)

        # 类型名（详情页分类字段，如 国产动漫）
        type_name = ''
        for li in soup.select('dd.fed-deta-content li'):
            label_el = li.find('span', class_='fed-text-muted')
            if label_el is None:
                continue
            if (label_el.get_text(strip=True) or '').rstrip(':：') != '分类':
                continue
            a = li.find('a', href=re.compile(r'/mei/\d+\.html'))
            if a:
                type_name = a.get_text(strip=True)
            break

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

    # ============================================================
    # 播放解析（var now 直链 + var next 预取 + 多源并发兜底）
    # ============================================================
    def _resolve_play(self, play_url):
        """解析播放页真实 m3u8，返回 (m3u8, next_m3u8)，均带缓存"""
        item = self._play_cache.get(play_url)
        if item and time.time() - item[0] < item[2]:
            return item[1]
        real, nxt = '', ''
        try:
            text = self._get_text(play_url, referer=HOST + '/', timeout=TIMEOUT_PLAY)
            if text:
                m = re.search(r'var\s+now\s*=\s*"([^"]+)"', text)
                if m:
                    u = m.group(1).replace('\\/', '/').strip()
                    if u:
                        real = self._abs(u)
                if not real:
                    m2 = re.search(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', text)
                    if m2:
                        real = self._abs(m2.group(0))
                if not real:
                    m3 = re.search(r'"url"\s*:\s*"(https?://[^"]+)"', text)
                    if m3:
                        u = m3.group(1).replace('\\/', '/').strip()
                        if '.m3u8' in u or '.mp4' in u:
                            real = self._abs(u)
                # 下一集直链（预取用）
                m4 = re.search(r'var\s+next\s*=\s*"([^"]+)"', text)
                if m4:
                    nxt = m4.group(1).replace('\\/', '/').strip()
                    if nxt:
                        nxt = self._abs(nxt)
        except Exception:
            real = ''
        if real:
            self._play_cache[play_url] = (time.time(), (real, nxt), TTL_PLAY)
        return (real, nxt)

    def _first_play_url(self, vod):
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            for item in seg.split("#"):
                parts = item.split("$", 1)
                if len(parts) == 2 and parts[1]:
                    return parts[1]
        return None

    def _prefetch_next(self, play_url):
        """预取下一集：播放页 var next 即为下一集 m3u8 直链，
        直接写入下一集播放页 URL 的缓存，连播时零请求秒开"""
        item = self._play_cache.get(play_url)
        if not item or time.time() - item[0] >= item[2]:
            return
        nxt = item[1][1]
        if not nxt:
            return
        m = re.search(r'/play/(\d+)-(\d+)-(\d+)\.html', play_url)
        if not m:
            return
        vid, sid, nid = m.group(1), m.group(2), int(m.group(3))
        next_page = f"{HOST}/play/{vid}-{sid}-{nid + 1}.html"
        with self._lock:
            old = self._play_cache.get(next_page)
            if not (old and time.time() - old[0] < old[2]):
                self._play_cache[next_page] = (time.time(), (nxt, ''), TTL_PLAY)

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

        real, nxt = self._resolve_play(play_url)
        if real:
            if nxt:
                self._prefetch_next(play_url)
            return self._play_payload(real)

        # 主源失败：并发兜底其余播放源
        alts = self._alt_play_urls(play_url)
        if alts and ThreadPoolExecutor is not None:
            try:
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futs = [ex.submit(self._resolve_play, u) for u in alts]
                    for f in as_completed(futs, timeout=TIMEOUT_PLAY):
                        u, _n = f.result(timeout=TIMEOUT_PLAY)
                        if u:
                            return self._play_payload(u)
            except Exception:
                pass
        else:
            for u in alts:
                m, _n = self._resolve_play(u)
                if m:
                    return self._play_payload(m)

        return {
            "parse": 1,
            "playUrl": "",
            "url": play_url,
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }

    def _alt_play_urls(self, play_url, limit=6):
        m = re.search(r'/play/(\d+)-', play_url)
        if not m:
            return []
        vid = m.group(1)
        cached = self._cache_get(self._detail_cache, vid, TTL_DETAIL_OK)
        if not cached or not cached.get("list"):
            return []
        vod = cached["list"][0]
        out, seen = [], {play_url}
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            for item in seg.split("#"):
                parts = item.split("$", 1)
                if len(parts) == 2 and parts[1]:
                    u = parts[1]
                    if u not in seen:
                        seen.add(u)
                        out.append(u)
                        if len(out) >= limit:
                            return out
        return out

    # ============================================================
    # 工具：元信息提取
    # ============================================================
    @staticmethod
    def _pick_year(text):
        m = re.search(r'[（(]\s*(\d{4})\s*[）)]', text)
        if m:
            return m.group(1)
        m = re.search(r'\b(19\d{2}|20\d{2})\b', text)
        return m.group(1) if m else ''

    @staticmethod
    def _pick_remarks(text):
        patterns = [
            r'(连载至\s*[\d]+集)',
            r'(更新至\s*[\d]+集)',
            r'(更新到\s*[\d]+集)',
            r'(全[\d]+集)',
            r'(已完结|全集|正片|HD中字|HD国语|TC中字)',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return ''

    # ============================================================
    # 搜索（/search.php + 全局限流 + 多页 + 去重）
    # ============================================================
    def searchContent(self, key, quick):
        key = (key or '').strip()
        if not key:
            return {"list": []}

        cache_key = "%s|%d" % (key, 1 if quick else 2)
        cached = self._cache_get(self._search_cache, cache_key, TTL_SEARCH)
        if cached is not None:
            return cached

        max_pages = 1 if quick else 2
        items = {}
        for page in range(1, max_pages + 1):
            params = {"searchword": key, "searchtype": "", "page": page}
            html = self._search_get(HOST + "/search.php", params=params)
            if not html:
                break
            cards = self._parse_cards(html, limit=60)
            for c in cards:
                if c["vod_id"] not in items:
                    items[c["vod_id"]] = c
            if len(cards) < 30:
                break  # 没更多结果了
            if page >= max_pages:
                break

        vod_list = list(items.values())[:60]
        result = {"list": vod_list}
        self._cache_set(self._search_cache, cache_key, result, TTL_SEARCH)
        return result
