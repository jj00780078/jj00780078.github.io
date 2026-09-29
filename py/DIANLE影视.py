# -*- coding: utf-8 -*-
"""
宝妈付业影视 (www.baomafuye.com) - TVBox 爬虫源 (maccms)
========================================================
接口：homeContent / categoryContent(含二级分类+筛选) / detailContent / playerContent / searchContent

站点特性（已实测确认）：
1. 必须伪装移动端 UA，gzip 压缩响应
2. 播放链路：详情页 /mafdt/{id}.html -> 播放页 /mafpy/{id}-{sid}-{nid}.html
   -> 播放页内 player_xxxx JSON 的 url 字段即真实 m3u8 直链
3. 分类页：/mafsw/{tid}-----------.html(第1页)，翻页 /mafsw/{tid}--------{n}---.html
4. 二级分类是独立 tid：电影1[6动作 7喜剧 8爱情 9科幻 10恐怖 11剧情 12战争 13纪录
   14悬疑 15犯罪 16奇幻 31动画 32预告]，电视剧2[17国产 18港台 20日韩 21欧美 22海外]
   综艺3[23大陆 24日韩 25欧美 26港台]，动漫4[27国产 28日韩 29欧美 30其他]，短剧5无子类
5. 筛选 URL 为 11 横杠占位：地区位1(-{area}) / 排序位2(--{by}) / 年份位11(-----------{year})
   实测：地区与排序互斥（不能同选），年份可与任一组合
6. 搜索：/mafsc/{关键词}-------------.html(第1页)，翻页 /mafsc/{关键词}----------{n}---.html

核心优化：
- 多级缓存：首页10分钟 / 分类5分钟 / 详情5分钟(失败30秒) / 搜索3分钟 / 播放15分钟
- 全链路短超时(8s/5s/4s) + 快速重试(0.3s) + 429限流等待(2s)
- 连接池复用(HTTPAdapter) + gzip 自动解压 + HTTPS 校验关闭
- 详情懒加载：不预解析集数 m3u8，playerContent 按需解析 + 缓存 + 后台预取下一集
"""

import re
import json
import time
import threading
from urllib.parse import quote, unquote

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
HOST = "https://www.baomafuye.com"

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

# 分类表（maccms 数字 tid，硬编码避免广告注入干扰）
# 结构：一级分类 tid -> 二级分类 tid/名称
CATS = [
    {"id": "1", "name": "电影", "subs": [
        ("6", "动作片"), ("7", "喜剧片"), ("8", "爱情片"),
        ("9", "科幻片"), ("10", "恐怖片"), ("11", "剧情片"),
        ("12", "战争片"), ("13", "纪录片"), ("14", "悬疑片"),
        ("15", "犯罪片"), ("16", "奇幻片"), ("31", "动画片"),
        ("32", "预告片"),
    ]},
    {"id": "2", "name": "电视剧", "subs": [
        ("17", "国产剧"), ("18", "港台剧"), ("20", "日韩剧"),
        ("21", "欧美剧"), ("22", "海外剧"),
    ]},
    {"id": "3", "name": "综艺", "subs": [
        ("23", "大陆综艺"), ("24", "日韩综艺"),
        ("25", "欧美综艺"), ("26", "港台综艺"),
    ]},
    {"id": "4", "name": "动漫", "subs": [
        ("27", "国产动漫"), ("28", "日韩动漫"),
        ("29", "欧美动漫"), ("30", "其他动漫"),
    ]},
    {"id": "5", "name": "短剧", "subs": []},
]

# 地区（与站点筛选一致）
AREAS = [
    "大陆", "香港", "台湾", "美国", "法国", "英国",
    "日本", "韩国", "德国", "泰国", "印度", "意大利",
    "西班牙", "加拿大", "其他",
]

# 年份（站点提供 2026-2010）
YEARS = [str(y) for y in range(2026, 2009, -1)]

# 排序
ORDERS = [
    {"n": "时间", "v": "time"},
    {"n": "人气", "v": "hits"},
    {"n": "评分", "v": "score"},
]


def _build_filters(cat):
    """构建筛选器：类型(二级分类) / 地区 / 年份 / 排序"""
    subs = [{"n": name, "v": slug} for slug, name in cat["subs"]]
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
        "value": [{"n": "全部", "v": ""}] + list(ORDERS),
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

        self._warm_thread = None

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

    # ===== HTML 解析工具 =====
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
        m = re.search(r'/mafdt/(\d+)\.html$', (href or '').strip())
        return m.group(1) if m else None

    @staticmethod
    def _pick_pic(el):
        if el is None:
            return ''
        for attr in ('data-original', 'data-src', 'src'):
            val = str(el.get(attr) or '').strip()
            if val and 'load.gif' not in val:
                return Spider._abs(val)
        style = str(el.get('style') or '')
        m = re.search(r'background-image:\s*url\(([^)]+)\)', style)
        if m:
            return Spider._abs(m.group(1).strip().strip('"').strip("'"))
        return ''

    @staticmethod
    def _clean_name(raw):
        if not raw:
            return raw
        return re.sub(r'\s*[（(]\s*\d{4}\s*[）)]\s*$', '', raw.strip())

    # ===== 列表卡片解析（首页/分类/搜索通用）=====
    def _parse_cards(self, html, limit=72):
        if not html:
            return []
        soup = self._soup(html)
        if soup is None:
            return []
        items = {}

        # --- 方式1：搜索结果页（.module-search-item）---
        for item in soup.select('.module-search-item'):
            try:
                # 详情链接（优先 h3 里的标题链接）
                a = item.select_one('h3 a[href*="/mafdt/"]') \
                    or item.select_one('.video-serial[href*="/mafdt/"]') \
                    or item.select_one('a[href*="/mafdt/"]')
                if not a:
                    continue
                href = str(a.get('href') or '')
                vid = self._extract_id(href)
                if not vid or vid in items:
                    continue
                # 标题
                title = str(a.get('title') or '').strip()
                if not title:
                    title = a.get_text(strip=True)
                if not title:
                    h3 = item.select_one('h3')
                    if h3:
                        title = h3.get_text(strip=True)
                if not title:
                    continue
                # 图片
                pic = ''
                img = (item.select_one('.module-item-pic img')
                       or item.select_one('.module-item-cover img')
                       or item.select_one('.video-cover img'))
                if img:
                    pic = self._pick_pic(img)
                # 备注
                remarks = ''
                st = (item.select_one('.video-serial')
                      or item.select_one('.module-item-text'))
                if st:
                    remarks = st.get_text(strip=True)
                if not remarks:
                    m = re.search(
                        r'(更新至[^\s]{0,12}|更新到[^\s]{0,12}|全\d+集|全集'
                        r'|已完结|正片|HD中字|HD国语|TC中字|第\d+集)', title
                    )
                    if m:
                        remarks = m.group(1)
                items[vid] = {
                    'vod_id': vid,
                    'vod_name': self._clean_name(title),
                    'vod_pic': pic,
                    'vod_remarks': remarks,
                }
            except Exception:
                continue
            if len(items) >= limit:
                break

        if items:
            return list(items.values())[:limit]

        # --- 方式2：首页/分类页（.module-item 内 a.module-item-pic 等）---
        selectors = [
            'a.module-item-pic[href*="/mafdt/"]',
            'a[href*="/mafdt/"]',
        ]
        for selector in selectors:
            links = soup.select(selector)
            if not links:
                continue
            for a in links:
                href = str(a.get('href') or '')
                vid = self._extract_id(href)
                if not vid or vid in items:
                    continue
                title = str(a.get('title') or '').strip()
                if not title:
                    title = a.get_text(strip=True)
                if not title:
                    continue
                pic = self._pick_pic(a.find('img')) or self._pick_pic(a)
                if not pic:
                    # 搜索页：图片在 .module-item-pic div 内（不在详情链接 a 内）
                    node = a
                    for _ in range(4):
                        parent = node.find_parent('div')
                        if parent is None:
                            break
                        node = parent
                        img = (node.select_one('.module-item-pic img')
                               or node.select_one('.module-item-cover img'))
                        if img:
                            pic = self._pick_pic(img)
                            break
                remarks = ''
                # 备注在卡片容器内（.module-item 或含 video-serial 的父级）
                box = a
                for _ in range(4):
                    parent = box.find_parent('div')
                    if parent is None:
                        break
                    box = parent
                    cls = box.get('class') or []
                    if 'module-item' in cls or box.select_one('.video-serial') is not None:
                        break
                st = (box.select_one('.module-item-text')
                      or box.select_one('.video-serial'))
                if st:
                    remarks = st.get_text(strip=True)
                if not remarks:
                    m = re.search(
                        r'(更新至[^\s]{0,12}|更新到[^\s]{0,12}|全\d+集|全集'
                        r'|已完结|正片|HD中字|HD国语|TC中字|第\d+集)', title
                    )
                    if m:
                        remarks = m.group(1)
                items[vid] = {
                    'vod_id': vid,
                    'vod_name': self._clean_name(title),
                    'vod_pic': pic,
                    'vod_remarks': remarks,
                }
        return list(items.values())[:limit]

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter=False):
        vod_list = []
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                vod_list = self._home_cache[:96]
        if not vod_list:
            try:
                html = self._get_text(HOST)
                vod_list = self._parse_cards(html, limit=96)
                if vod_list:
                    with self._lock:
                        self._home_cache = vod_list
                        self._home_cache_time = int(time.time())
            except Exception:
                pass
        return {
            "class": ALL_CLASSES,
            "filters": ALL_FILTERS,
            "list": vod_list,
        }

    def homeVideoContent(self):
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                return {"list": self._home_cache[:96]}
        try:
            html = self._get_text(HOST)
            vod_list = self._parse_cards(html, limit=96)
            if vod_list:
                with self._lock:
                    self._home_cache = vod_list
                    self._home_cache_time = int(time.time())
            return {"list": vod_list[:96]}
        except Exception:
            return {"list": []}

    # ============================================================
    # 分类列表（含二级分类/筛选）
    # ============================================================
    def _empty_category(self, page=1):
        return {"list": [], "page": page, "pagecount": 1, "limit": 72, "total": 0}

    @staticmethod
    def _build_list_url(tid, area='', by='', year='', page=1):
        """构造分类/筛选 URL。

        站点筛选 URL 为 11 横杠占位：
        - 地区位1: -{area}  排序位2: --{by}  年份位11: -----------{year}
        - 分页位9: --------{page}---
        - 实测地区与排序互斥，年份可与任一组合
        """
        prefix = str(tid)
        used = 0
        if area:
            prefix += '-' + quote(area)
            used = 1
        elif by:
            prefix += '--' + quote(by)
            used = 2
        mid_total = 11 - used
        if page > 1:
            mid = '-' * (mid_total - 3)
            tail = f"{mid}{page}---"
        else:
            tail = '-' * mid_total
        if year:
            tail += quote(year)
        return f"{HOST}/mafsw/{prefix}{tail}.html"

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

            # 二级分类（class）是独立 tid，直接替换主 tid
            sub_tid = (ext.get('class') or '').strip()
            real_tid = sub_tid if sub_tid else str(tid)
            area = (ext.get('area') or '').strip()
            year = (ext.get('year') or '').strip()
            by = (ext.get('by') or '').strip()
            if by not in ('time', 'hits', 'score'):
                by = ''

            ckey = "%s|%d|%s|%s|%s|%s" % (real_tid, page, area, year, by, sub_tid)
            cached = self._cache_get(self._cat_cache, ckey, TTL_CAT)
            if cached is not None:
                return cached

            url = self._build_list_url(real_tid, area=area, by=by, year=year, page=page)
            html = self._get_text(url)
            if not html:
                return self._empty_category(page)

            vod_list = self._parse_cards(html, limit=72)

            # 页数：从分页链接推断（末页数字）
            pagecount = 1
            nums = [int(x) for x in re.findall(
                r'/mafsw/[^"\'<>]*--------(\d+)---\.html', html)]
            if nums:
                pagecount = max(nums)

            result = {
                "list": vod_list,
                "page": page,
                "pagecount": pagecount,
                "limit": 72,
                "total": pagecount * 72,
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
            self._prefetch_play(result["list"][0])
        return result

    def _fetch_detail(self, vid):
        html = self._get_text(f"{HOST}/mafdt/{vid}.html")
        if not html:
            return {"list": []}
        soup = self._soup(html)
        if soup is None:
            return {"list": []}

        # --- 基本信息 ---
        name = ''
        h1 = soup.select_one('h1.page-title')
        if h1:
            name = self._clean_name(h1.get_text(strip=True))
        if not name:
            t1 = soup.select_one('h1') or soup.title
            if t1:
                name = self._clean_name(t1.get_text(strip=True))

        pic = ''
        img = soup.select_one('.video-cover .module-item-pic img') \
            or soup.select_one('.module-item-pic img')
        if img:
            pic = self._pick_pic(img)

        # --- 导演 / 主演 / 备注 ---
        director, actor, remarks = '', '', ''
        for items in soup.select('.video-info-items'):
            label_el = items.select_one('.video-info-itemtitle')
            if label_el is None:
                continue
            label = (label_el.get_text(strip=True) or '').rstrip('：:')
            val = items.get_text(' ', strip=True)
            val = val[len(label_el.get_text(strip=True)):].strip().lstrip('：: ').strip()
            val = re.sub(r'\s*/\s*$', '', val)
            if label == '导演':
                director = val
            elif label == '主演':
                actor = val
            elif label == '备注':
                remarks = val

        # --- 年份 / 类型 / 地区（video-info-aux 标签）---
        year = ''
        type_name = ''
        area = ''
        aux = soup.select_one('.video-info-aux')
        if aux is not None:
            for a in aux.select('a[href*="/mafsc/"]'):
                href = str(a.get('href') or '')
                txt = a.get_text(strip=True)
                if not txt:
                    continue
                if re.search(r'-------------\d{4}\.html$', href):
                    year = txt
                elif href.startswith('/mafsc/----'):
                    type_name = txt
                elif href.startswith('/mafsc/--'):
                    area = txt

        # --- 简介 ---
        content = ''
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta:
            c = str(meta.get('content') or '').strip()
            m = re.search(r'剧情讲述[:：](.{10,})', c)
            if m:
                content = m.group(1).strip()
            if not content and c:
                content = c[:200]

        # --- 播放源与集数 ---
        # 源名：module-tab-item 顺序即 sid 顺序（取 span 文本，排除集数 small）
        src_names = []
        for t in soup.select('.module-tab-item'):
            span = t.select_one('span')
            nm = span.get_text(strip=True) if span else t.get_text(strip=True)
            if nm:
                src_names.append(nm)
        if not src_names:
            src_names = ['默认线路']

        # 集数：仅取选集区块(.sort-item)内的播放链接，按 sid 分组，nid 去重
        groups = {}
        for a in soup.select('.sort-item a[href*="/mafpy/"]'):
            m = re.search(r'/mafpy/\d+-(\d+)-(\d+)\.html', str(a.get('href') or ''))
            if not m:
                continue
            sid, nid = int(m.group(1)), int(m.group(2))
            ep = a.select_one('span')
            ep_name = ep.get_text(strip=True) if ep else ''
            if not ep_name:
                ep_name = re.sub(r'^播放', '', (a.get('title') or '').strip())
            if not ep_name:
                continue
            groups.setdefault(sid, {})
            if nid not in groups[sid]:
                groups[sid][nid] = ep_name

        play_from, play_url = '', ''
        for sid in sorted(groups):
            eps = groups[sid]
            src_name = src_names[sid - 1] if sid - 1 < len(src_names) else f"线路{sid}"
            ep_parts = []
            for nid in sorted(eps):
                u = f"{HOST}/mafpy/{vid}-{sid}-{nid}.html"
                ep_parts.append(f"{eps[nid]}${u}")
            if not ep_parts:
                continue
            play_from = (play_from + '$$$' + src_name) if play_from else src_name
            play_url = (play_url + '$$$' + '#'.join(ep_parts)) if play_url else '#'.join(ep_parts)

        detail = {
            "vod_id": vid,
            "vod_name": name or f"视频{vid}",
            "vod_pic": pic or HOST,
            "type_name": type_name,
            "vod_remarks": remarks,
            "vod_year": year,
            "vod_area": area,
            "vod_director": director,
            "vod_actor": actor,
            "vod_content": content,
            "vod_play_from": play_from or '默认',
            "vod_play_url": play_url or '',
        }
        return {"list": [detail]}

    # ============================================================
    # 播放解析
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

    def _prefetch_play(self, vod):
        target = self._first_play_url(vod)
        if not target:
            return
        with self._lock:
            if self._cache_get(self._play_cache, target, TTL_PLAY) or target in self._prefetching:
                return
            self._prefetching.add(target)

        def _job():
            try:
                self._resolve_play(target)
            except Exception:
                pass
            finally:
                with self._lock:
                    self._prefetching.discard(target)

        threading.Thread(target=_job, daemon=True).start()

    def _prefetch_next(self, play_url):
        # 从播放 URL 提取 vid（详情缓存 key）
        m = re.search(r'/mafpy/(\d+)-\d+-\d+\.html', play_url)
        if not m:
            return
        vid = m.group(1)
        cached = self._cache_get(self._detail_cache, vid, TTL_DETAIL_OK)
        if not cached or not cached.get("list"):
            return
        vod = cached["list"][0]
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            items = seg.split("#")
            for i, item in enumerate(items):
                parts = item.split("$", 1)
                if len(parts) == 2 and self._abs(parts[1]) == play_url:
                    if i + 1 < len(items):
                        next_parts = items[i + 1].split("$", 1)
                        if len(next_parts) == 2 and next_parts[1]:
                            next_url = self._abs(next_parts[1])
                            with self._lock:
                                if (self._cache_get(self._play_cache, next_url, TTL_PLAY)
                                        or next_url in self._prefetching):
                                    return
                                self._prefetching.add(next_url)

                            def _job(url=next_url):
                                try:
                                    self._resolve_play(url)
                                except Exception:
                                    pass
                                finally:
                                    with self._lock:
                                        self._prefetching.discard(url)

                            threading.Thread(target=_job, daemon=True).start()
                    return

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
        m = re.search(r'/mafpy/(\d+)-\d+-\d+\.html', play_url)
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
    # 搜索
    # ============================================================
    def searchContent(self, key, quick=False):
        if not key:
            return {"list": []}
        key = key.strip()
        # 防止 double-encode：部分 TVBox 版本会传 URL 编码的 key
        if '%' in key:
            try:
                dec = unquote(key)
                if dec and dec != key:
                    key = dec.strip()
            except Exception:
                pass
        if not key:
            return {"list": []}

        cached = self._cache_get(self._search_cache, key, TTL_SEARCH)
        if cached is not None:
            return cached

        result = {"list": []}
        try:
            wd = quote(key)
            # 第1页
            url = f"{HOST}/mafsc/{wd}-------------.html"
            html = self._get_text(url, referer=HOST + '/')
            if html:
                result = {"list": self._parse_cards(html, limit=60)}
                # 若第1页结果不足 30，继续翻页补充
                if len(result["list"]) < 30:
                    more = self._search_more_pages(wd, result["list"])
                    result = {"list": more}
            # 站内搜索无结果 -> 分类爬取兜底（分词模糊匹配）
            if not result["list"]:
                result = {"list": self._search_fallback(key)}
        except Exception:
            result = {"list": []}

        self._cache_set(self._search_cache, key, result, TTL_SEARCH)
        return result

    def _search_more_pages(self, wd, base, max_pages=5):
        items = list(base)
        seen = {v["vod_id"] for v in items}
        for p in range(2, max_pages + 1):
            if len(items) >= 60:
                break
            try:
                url = f"{HOST}/mafsc/{wd}----------{p}---.html"
                html = self._get_text(url, referer=HOST + '/')
                cards = self._parse_cards(html, limit=36)
                if not cards:
                    break
                for v in cards:
                    if v["vod_id"] not in seen:
                        seen.add(v["vod_id"])
                        items.append(v)
            except Exception:
                break
        return items[:60]

    def searchContentVideo(self, key, quick=False):
        """TVBox 全局搜索入口：与 searchContent 逻辑一致，
        部分 TVBox 版本全局搜索调用 searchContentVideo 而非 searchContent。"""
        return self.searchContent(key, quick)

    def _search_fallback(self, key):
        """搜索兜底：站内搜索无结果时，把关键词拆成 2 字滑窗词，
        逐个走站内搜索合并结果（比爬分类页精准、请求少）。
        只搜中文滑窗词 + 英文词（≥3 字母），避免 URL 编码残留等垃圾词。"""
        k = key.strip()
        if not k:
            return []
        toks = []
        for t in re.findall(r'[\u4e00-\u9fff]+', k):
            if len(t) >= 2:
                toks.append(t[:2])
                if len(t) > 2:
                    toks.append(t[-2:])
        toks += [t for t in re.findall(r'[A-Za-z]{3,}', k)]
        if not toks:
            return []

        items, seen = [], set()
        for t in dict.fromkeys(toks):
            if len(items) >= 60:
                break
            try:
                wd = quote(t)
                url = f"{HOST}/mafsc/{wd}-------------.html"
                html = self._get_text(url, referer=HOST + '/')
                if not html:
                    continue
                for v in self._parse_cards(html, limit=36):
                    if v["vod_id"] not in seen:
                        seen.add(v["vod_id"])
                        items.append(v)
            except Exception:
                continue
        return items[:60]


# ============================================================
# 本地调试（非 TVBox 环境直接运行）
# ============================================================
if __name__ == '__main__':
    sp = Spider()
    sp.init()

    print("=== homeContent ===")
    home = sp.homeContent()
    print("分类:", [(c["type_id"], c["type_name"]) for c in home["class"]])
    print("首页影片:", [(v["vod_name"], v["vod_remarks"]) for v in home["list"][:5]])

    print("\n=== categoryContent(电影) ===")
    cat = sp.categoryContent('1', '1', False, {})
    print("电影第1页:", [(v["vod_name"], v["vod_remarks"]) for v in cat["list"][:3]], "总页:", cat["pagecount"])

    print("\n=== categoryContent(电影->动作片) ===")
    cat2 = sp.categoryContent('1', '1', False, {"class": "6"})
    print("动作片:", [v["vod_name"] for v in cat2["list"][:3]])

    print("\n=== categoryContent(电影+大陆+2026+第2页) ===")
    cat3 = sp.categoryContent('1', '2', False, {"area": "大陆", "year": "2026"})
    print("电影+大陆+2026 p2:", [v["vod_name"] for v in cat3["list"][:3]])

    print("\n=== detailContent ===")
    det = sp.detailContent([cat["list"][0]["vod_id"]])
    d = det["list"][0]
    print("片名:", d["vod_name"], "| 年份:", d["vod_year"], "| 地区:", d["vod_area"])
    print("导演:", d["vod_director"][:30], "| 主演:", d["vod_actor"][:30])
    print("备注:", d["vod_remarks"], "| 类型:", d["type_name"])
    print("源:", d["vod_play_from"][:60])
    print("首集:", d["vod_play_url"][:120])

    print("\n=== playerContent ===")
    pid = d["vod_play_url"].split("#")[0].split("$")[1]
    play = sp.playerContent('', pid, [])
    print("播放结果:", play.get("url", "")[:120])

    print("\n=== searchContent ===")
    s = sp.searchContent("战")
    print("搜索'战':", [(v["vod_name"], v["vod_remarks"]) for v in s["list"][:5]], "共", len(s["list"]), "条")
