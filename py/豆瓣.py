#!/usr/bin/env python3
# coding=utf-8
# !/usr/bin/python
"""
豆瓣影视 (douban) —— TVBox / 影视仓 Python 爬虫 (T4 py)
功能  : 首页推荐 / 分类浏览+翻页 / 搜索 / 详情(评分/导演/演员/简介) / 播放解析
依赖  : 无第三方强依赖(有 requests 用 requests, 否则回退 urllib)

数据层(豆瓣公开接口, 无需鉴权):
  - 列表/搜索 : https://movie.douban.com/j/search_subjects
                type=movie|tv, tag=热门/最新/经典/豆瓣高分/动作/喜剧/科幻/悬疑/爱情/恐怖/...
                或 new_search_subjects?tags=电视剧/综艺/动漫/纪录片
  - 详情      : https://m.douban.com/rexxar/api/v2/subject/{id}?ck=null

播放层(豆瓣本身不提供播放地址, 内置"白嫖者联盟"资源站搜索兜底):
  - 详情时用片名+年份在 /v1/suggest 搜索同片资源 → /v1/catalog/{id}/episodes 拿选集
  - 播放时 player.baipiaozhe.com/v1/playback/resolve/{token}
    官方线路 resolve_ticket → 带 ?ps= 换票出实时 m3u8, 失败自动退回第三方线路
  - 换资源站: init(extend) 传自定义 JSON { "bpz": "https://新站" }
"""

import json
import re
import sys
import time
import urllib.parse

sys.path.append('..')

# ---- TVBox 运行环境提供 base.spider; 本地调试时降级为空基类 ----
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# ---- 豆瓣 ----
DB_LIST = 'https://movie.douban.com/j/search_subjects'
DB_NEW = 'https://movie.douban.com/j/new_search_subjects'
DB_REXXAR = 'https://m.douban.com/rexxar/api/v2/subject/%s?ck=null'
DB_COLLECTION = 'https://m.douban.com/rexxar/api/v2/subject_collection/%s/items'

# 剧集类分类 -> rexxar collection 名
DT_COL = {'电视剧': 'tv_hot', '综艺': 'show_hot', '纪录片': 'tv_documentary'}

# ---- 播放资源站(白嫖者联盟) ----
BPZ_SITE = 'https://bpz.app'
BPZ_PLAY = 'https://player.baipiaozhe.com'
BPZ_KEY = 'f39d73aa7a6426203cdee1ef17b31d3b7ea8c23f4c59c62a3a8aa0f39ee5e79d'

# ==================== 主分类 + 筛选器 ====================
# 主分类: 电影 / 电视剧 / 综艺 / 动漫 / 纪录片
# 子分类通过 TVBox 筛选器选择, 不一股脑堆在分类列表
MAIN_CATS = [
    ('movie', '电影'),
    ('tv', '电视剧'),
    ('anime', '动漫'),
    ('variety', '综艺'),
    ('documentary', '纪录片'),
]

MOVIE_TAGS = {
    '综合': ['Top250', '热门', '最新', '经典', '豆瓣高分', '可播放', '冷门佳片', '华语', '欧美'],
    '类型': ['剧情', '喜剧', '动作', '爱情', '科幻', '动画', '悬疑', '惊悚', '恐怖',
           '犯罪', '同性', '音乐', '歌舞', '传记', '历史', '战争', '西部', '奇幻',
           '冒险', '灾难', '武侠', '运动', '家庭', '儿童'],
    '地区': ['大陆', '香港', '台湾', '美国', '法国', '英国', '日本', '韩国', '德国',
           '意大利', '西班牙', '印度', '泰国', '俄罗斯', '伊朗', '加拿大', '澳大利亚', '北欧'],
    '年代': ['2024', '2022', '2021', '2010年代', '2000年代', '90年代', '80年代', '70年代'],
}
TV_TAGS = ['古装', '谍战', '年代', '偶像', '商战', '家庭', '情景', '历史', '战争',
           '犯罪', '奇幻', '武侠', '爱情', '剧情', '喜剧']
ANIME_TAGS = ['热血', '恋爱', '搞笑', '奇幻', '科幻', '冒险', '日常', '治愈',
              '校园', '推理', '机战', '运动']
VARIETY_TAGS = ['真人秀', '脱口秀', '访谈', '舞蹈', '旅行', '美食', '亲子',
                '游戏', '竞技', '搞笑', '生活', '音乐']
DOC_TAGS = ['人文', '自然', '地理', '科学', '考古', '宇宙', '科技', '美食',
            '动物', '人物', '探索', '医疗']


def _filter_ops(tags):
    """['a','b'] -> [{'n':'全部','v':''}, {'n':'a','v':'a'}, ...]"""
    return [{'n': '全部', 'v': ''}] + [{'n': t, 'v': t} for t in tags]


FILTERS = {
    'movie': [
        {'key': 'tag', 'name': '综合', 'value': _filter_ops(MOVIE_TAGS['综合'])},
        {'key': 'type', 'name': '类型', 'value': _filter_ops(MOVIE_TAGS['类型'])},
        {'key': 'area', 'name': '地区', 'value': _filter_ops(MOVIE_TAGS['地区'])},
        {'key': 'year', 'name': '年代', 'value': _filter_ops(MOVIE_TAGS['年代'])},
    ],
    'tv': [{'key': 'type', 'name': '类型', 'value': _filter_ops(TV_TAGS)}],
    'anime': [{'key': 'type', 'name': '类型', 'value': _filter_ops(ANIME_TAGS)}],
    'variety': [{'key': 'type', 'name': '类型', 'value': _filter_ops(VARIETY_TAGS)}],
    'documentary': [{'key': 'type', 'name': '类型', 'value': _filter_ops(DOC_TAGS)}],
}


class Spider(BaseSpider):
    # ==================== 生命周期 ====================
    def init(self, extend=""):
        """extend 可传 JSON: {"bpz": "https://新资源站", "play": "https://新播放站"}"""
        self.site = DB_LIST
        self.bpz = BPZ_SITE
        self.play = BPZ_PLAY
        try:
            if extend:
                ext = extend.strip()
                if ext.startswith('{'):
                    ext = json.loads(ext)
                    self.bpz = (ext.get('bpz') or BPZ_SITE).rstrip('/')
                    self.play = (ext.get('play') or BPZ_PLAY).rstrip('/')
                elif ext.startswith('http'):
                    self.bpz = ext.rstrip('/')
        except Exception:
            pass
        return self

    def getName(self):
        return '豆瓣影视'

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|mkv|flv|avi|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return ''

    def localProxy(self, param):
        return [200, "video/MP2T", {}, None]

    # ==================== 网络(豆瓣) ====================
    def _session(self):
        if not HAS_REQUESTS:
            return None
        se = getattr(self, '_se', None)
        if se is None:
            try:
                se = requests.Session()
                ad = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=0)
                se.mount('https://', ad)
                se.mount('http://', ad)
            except Exception:
                se = requests
            self._se = se
        return se

    def _get(self, url, headers=None, timeout=None, retry=3):
        ct, rt = timeout or (8, 20)
        for i in range(max(1, retry)):
            try:
                if HAS_REQUESTS:
                    r = self._session().get(url, headers=headers or {}, timeout=(ct, rt),
                                            allow_redirects=True)
                    if r.status_code >= 500:
                        raise IOError('http %d' % r.status_code)
                    return r.content.decode('utf-8', 'ignore')
                import urllib.request
                req = urllib.request.Request(url, headers=headers or {})
                return urllib.request.urlopen(req, timeout=rt).read().decode('utf-8', 'ignore')
            except Exception:
                if i + 1 < max(1, retry):
                    time.sleep(0.6 * (i + 1))
        return ''

    def _db_json(self, url, ref='https://movie.douban.com/', timeout=None, retry=2):
        body = self._get(url, headers={'User-Agent': UA, 'Referer': ref},
                         timeout=timeout, retry=retry)
        if not body:
            return None
        try:
            return json.loads(body)
        except Exception:
            return None

    # ==================== 首页 ====================
    def homeContent(self, filter):
        return {'class': [{'type_id': t, 'type_name': n} for t, n in MAIN_CATS],
                'filters': FILTERS}

    def homeVideoContent(self):
        d = self._db_json(DB_LIST + '?type=movie&tag=' + urllib.parse.quote('热门')
                          + '&page_limit=20&page_start=0')
        lst = []
        if d:
            for s in d.get('subjects', []):
                v = self._subject_to_vod(s)
                if v:
                    lst.append(v)
        return {'list': lst}

    @staticmethod
    def _subject_to_vod(s):
        sid = (s.get('url') or '').rstrip('/').rsplit('/', 1)[-1]
        if not sid or not s.get('title'):
            return None
        rate = s.get('rate') or ''
        return {
            'vod_id': sid,
            'vod_name': s.get('title', ''),
            'vod_pic': s.get('cover', ''),
            'vod_remarks': ('★%s' % rate) if rate else '',
            'vod_year': '',
            'type_name': s.get('type') or '',
        }

    # ==================== 分类(主分类 + 筛选器) ====================
    @staticmethod
    def _parse_filter_arg(f):
        """解析 TVBox 回传的筛选参数, 兼容: dict / JSON串 / Python字面量串 / Java Map toString({type=喜剧})"""
        if isinstance(f, dict):
            return f
        if not isinstance(f, str):
            return {}
        s = f.strip()
        if not s:
            return {}
        try:
            r = json.loads(s)
            return r if isinstance(r, dict) else {}
        except Exception:
            pass
        try:
            import ast
            r = ast.literal_eval(s)
            return r if isinstance(r, dict) else {}
        except Exception:
            pass
        # Java Map.toString(): {type=喜剧, area=}  /  {type=喜剧}
        out = {}
        for m in re.finditer(r'([^\s={},]+)\s*=\s*([^{},]*)', s):
            k, v = m.group(1).strip(), m.group(2).strip()
            if k:
                out[k] = v
        return out

    @staticmethod
    def _pick_filter(f):
        """从筛选 dict 取第一个非空值(已知 key 优先, 任意值兜底)"""
        for key in ('综合', '类型', '地区', '年代', 'tag', 'type', 'area', 'year'):
            v = f.get(key)
            if v is None:
                continue
            if isinstance(v, str):
                v = v.strip()
            elif isinstance(v, (list, tuple)):
                v = str(v[0]).strip() if v else ''
            else:
                v = str(v).strip()
            if v:
                return v
        for v in f.values():
            if isinstance(v, str):
                v = v.strip()
            elif isinstance(v, (list, tuple)):
                v = str(v[0]).strip() if v else ''
            else:
                v = str(v).strip()
            if v:
                return v
        return ''

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        tid = str(tid)
        # 筛选值可能经 filter 或 extend 参数回传, 两个都解析合并
        f = self._parse_filter_arg(filter)
        e = self._parse_filter_arg(extend)
        f.update(e)
        sel = self._pick_filter(f)

        # 电影: 综合/类型/地区/年代 -> 标签 或 Top250
        if tid == 'movie':
            if sel == 'Top250':
                return self._collection_page('movie_top250', pg)
            tag = sel or '热门'
            return self._tag_page(tag, pg)

        # 电视剧: 热门(tv_hot) 或 类型子类(按 type=tv 过滤)
        if tid == 'tv':
            if sel:
                return self._tag_filtered_page('tv', sel, pg, 50, mode='type')
            return self._collection_page('tv_hot', pg)

        # 动漫: tag=动漫 或 类型子类(动画过滤)
        if tid == 'anime':
            if sel:
                return self._tag_filtered_page('anime', sel, pg, 45, mode='genres')
            return self._tag_page('动漫', pg)

        # 综艺: show_hot 或 类型子类(真人秀/脱口秀过滤)
        if tid == 'variety':
            if sel:
                return self._tag_filtered_page('variety', sel, pg, 40, mode='genres')
            return self._collection_page('show_hot', pg)

        # 纪录片: tv_documentary 或 类型子类(纪录片过滤)
        if tid == 'documentary':
            if sel:
                return self._tag_filtered_page('documentary', sel, pg, 40, mode='genres')
            return self._collection_page('tv_documentary', pg)

        return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

    # ---------- 三种分页方式 ----------
    def _collection_page(self, col, pg):
        """rexxar collection: total 精确分页"""
        lst = []
        d = self._db_json(DB_COLLECTION % col + '?start=%d&count=20' % ((pg - 1) * 20),
                          ref='https://m.douban.com/')
        total = 0
        if d:
            total = d.get('total') or 0
            for it in d.get('subject_collection_items', []):
                v = self._coll_to_vod(it)
                if v:
                    lst.append(v)
        pagecount = max(1, (total + 19) // 20) if total else pg
        return {'list': lst, 'page': pg, 'pagecount': pagecount, 'limit': 20,
                'total': total}

    def _tag_page(self, tag, pg):
        """标签直出: j/search_subjects (当前页与下一页探测并行请求)"""
        lst = []
        try:
            from concurrent.futures import ThreadPoolExecutor
        except Exception:
            ThreadPoolExecutor = None
        def fetch(start, lim):
            return self._db_json(DB_LIST + '?type=movie&tag=%s&page_limit=%d&page_start=%d'
                                 % (urllib.parse.quote(tag), lim, start))

        if ThreadPoolExecutor:
            with ThreadPoolExecutor(max_workers=2) as ex:
                fut1 = ex.submit(fetch, (pg - 1) * 20, 20)
                fut2 = ex.submit(fetch, pg * 20, 1)  # 探测只需 1 条
                d = fut1.result()
                d2 = fut2.result()
        else:
            d = self._db_json(base + '&page_start=%d' % ((pg - 1) * 20))
            d2 = self._db_json(base + '&page_start=%d' % (pg * 20))
        if d:
            for s in d.get('subjects', []):
                v = self._subject_to_vod(s)
                if v:
                    lst.append(v)
        has_more = bool(d2 and d2.get('subjects'))
        total = (pg - 1) * 20 + len(lst)
        pagecount = pg + 1 if (has_more and lst) else pg
        return {'list': lst, 'page': pg, 'pagecount': pagecount, 'limit': 20,
                'total': total}

    def _tag_filtered_page(self, kind, tag, pg, batch, mode):
        """标签 + 详情类型过滤(动漫/综艺/纪录片/电视剧子类)"""
        if mode == 'type':
            kw = 'tv'
        else:
            kw = {'anime': '动画', 'variety': ('真人秀', '脱口秀'),
                  'documentary': '纪录片'}[kind]
        lst = self._tag_filtered(tag, kw, pg, batch, mode=mode)
        d2 = self._db_json(DB_LIST + '?type=movie&tag=' + urllib.parse.quote(tag)
                           + '&page_limit=1&page_start=%d' % (pg * batch))
        has_more = bool(d2 and d2.get('subjects'))
        total = (pg - 1) * 20 + len(lst)
        pagecount = pg + 1 if (has_more and lst) else pg
        return {'list': lst, 'page': pg, 'pagecount': pagecount, 'limit': 20,
                'total': total}

    def _tag_filtered(self, tag, kw, pg, batch, mode='genres'):
        """拉取标签列表 → 并发查 rexxar 详情 → 过滤
        mode='genres': kw 为 genres 关键词(动漫/综艺/纪录片)
        mode='type':   kw 为类型值如 'tv'(电视剧子类)
        性能优化: 高并发 + 短超时 + 详情缓存 + 凑够20条提前退出
        """
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
        except Exception:
            ThreadPoolExecutor = as_completed = None
        base = DB_LIST + '?type=movie&tag=' + urllib.parse.quote(tag) + '&page_limit=%d' % batch
        d = self._db_json(base + '&page_start=%d' % ((pg - 1) * batch), timeout=(5, 12))
        subs = (d or {}).get('subjects', [])
        if not subs:
            return []
        cache = getattr(self, '_det_cache', None)
        if cache is None:
            cache = {}
            self._det_cache = cache

        def check(s):
            sid = (s.get('url') or '').rstrip('/').rsplit('/', 1)[-1]
            det = cache.get(sid)
            if det is None:
                det = self._db_json(DB_REXXAR % sid, ref='https://m.douban.com/',
                                    timeout=(5, 10), retry=1)
                if det:
                    cache[sid] = det
            if not det:
                return None  # 详情失败降级丢弃
            g = det.get('genres') or []
            if mode == 'type':
                # 电视剧子类: type=tv 且排除动漫(type=tv 的动画剧, 如仙逆)
                ok = (det.get('type') or '') == kw and '动画' not in g
            elif isinstance(kw, str):
                ok = kw in g
            else:
                ok = any(k in g for k in kw)
            if not ok:
                return None
            rating = ((det.get('rating') or {}).get('value') or 0)
            pic = det.get('pic') or {}
            return {
                'vod_id': sid,
                'vod_name': det.get('title', ''),
                'vod_pic': pic.get('large') or pic.get('normal') or '',
                'vod_remarks': ('★%s' % rating) if rating else '',
                'vod_year': str(det.get('year') or ''),
                'type_name': '/'.join(g),
            }

        out = []
        if ThreadPoolExecutor:
            with ThreadPoolExecutor(max_workers=12) as ex:
                try:
                    for fut in as_completed([ex.submit(check, s) for s in subs]):
                        v = fut.result()
                        if v:
                            out.append(v)
                            if len(out) >= 20:
                                break  # 凑够一页提前退出
                finally:
                    try:
                        ex.shutdown(wait=False, cancel_futures=True)  # py3.9+
                    except TypeError:
                        pass
        else:
            for s in subs:
                v = check(s)
                if v:
                    out.append(v)
                    if len(out) >= 20:
                        break
        return out[:20]

    @staticmethod
    def _coll_to_vod(it):
        """rexxar subject_collection item -> TVBox vod 条目"""
        sid = it.get('id', '')
        title = it.get('title', '')
        if not sid or not title:
            return None
        rating = ((it.get('rating') or {}).get('value') or 0)
        eps = it.get('episodes_info') or ''
        return {
            'vod_id': str(sid),
            'vod_name': title,
            'vod_pic': (it.get('pic') or {}).get('large', ''),
            'vod_remarks': ('★%s %s' % (rating, eps)) if rating else eps,
            'vod_year': str(it.get('year') or ''),
            'type_name': '',
        }

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        key = str(key).strip()
        if not key:
            return {'list': []}
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        start = (pg - 1) * 20
        seen, lst = set(), []
        has_more = False

        # 1) rexxar 搜索(支持全名精确匹配, 分页)
        d = self._db_json('https://m.douban.com/rexxar/api/v2/search?q='
                          + urllib.parse.quote(key) + '&type=subject&start=%d&count=20' % start,
                          ref='https://m.douban.com/')
        for it in ((d or {}).get('subjects') or {}).get('items') or []:
            t = it.get('target') or {}
            sid = str(t.get('id') or '')
            title = t.get('title') or ''
            if not sid or not title or sid in seen:
                continue
            seen.add(sid)
            lst.append({
                'vod_id': sid,
                'vod_name': title,
                'vod_pic': '',
                'vod_remarks': str(t.get('year') or ''),
                'vod_year': str(t.get('year') or ''),
                'type_name': '',
            })
        if d:
            d2 = self._db_json('https://m.douban.com/rexxar/api/v2/search?q='
                               + urllib.parse.quote(key) + '&type=subject&start=%d&count=20'
                               % (start + 20), ref='https://m.douban.com/')
            has_more = bool(d2 and ((d2.get('subjects') or {}).get('items')))

        # 2) j/search_subjects 兜底(短词模糊, 仅第一页)
        if pg == 1:
            kw = urllib.parse.quote(key)
            for typ in ('movie', 'tv'):
                d = self._db_json(DB_LIST + '?type=%s&tag=%s&page_limit=20&page_start=0'
                                  % (typ, kw))
                if not d:
                    continue
                for s in d.get('subjects', []):
                    sid = (s.get('url') or '').rstrip('/').rsplit('/', 1)[-1]
                    if not sid or sid in seen:
                        continue
                    seen.add(sid)
                    v = self._subject_to_vod(s)
                    if v:
                        lst.append(v)

        def score(v):
            n = v.get('vod_name', '')
            if n == key:
                return 0
            if key in n:
                return 1
            return 2
        lst.sort(key=score)
        pagecount = pg + 1 if (has_more and lst) else pg
        return {'list': lst, 'page': pg, 'pagecount': pagecount,
                'limit': len(lst), 'total': len(lst)}

    # ==================== 详情 ====================
    def detailContent(self, ids):
        did = ids[0] if isinstance(ids, (list, tuple)) else ids
        did = str(did).strip()
        if not did:
            return {'list': []}

        # 1) 豆瓣元数据
        vod = self._douban_detail(did)
        if not vod:
            return {'list': []}

        # 2) 播放兜底: 片名+年份去资源站匹配
        play_url, play_from = '', ''
        vid = self._bpz_match(vod['vod_name'], vod.get('vod_year', ''))
        if vid:
            eps = self._bpz_episodes(vid)
            if eps:
                parts = []
                for ep in eps:
                    label = ep.get('title') or ('第%s集' % ep.get('number', ''))
                    label = str(label).replace('#', '').replace('$', '')
                    parts.append('%s$bpz://%s' % (label, ep.get('token', '')))
                play_str = '#'.join(parts)
                lines = self._probe_lines(eps[0].get('token', ''))
                play_from = '$$$'.join(lines)
                play_url = '$$$'.join([play_str] * len(lines))
            else:
                play_url = '第1集$db://none'
        else:
            play_url = '第1集$db://none'

        vod['vod_play_from'] = play_from or '豆瓣'
        vod['vod_play_url'] = play_url
        return {'list': [vod]}

    def _douban_detail(self, did):
        """豆瓣 rexxar 详情 -> TVBox vod 字段"""
        d = self._db_json(DB_REXXAR % did, ref='https://m.douban.com/')
        if not d or not d.get('title'):
            return None
        rating = (d.get('rating') or {}).get('value') or ''
        actors = [a.get('name', '') for a in (d.get('actors') or []) if a.get('name')]
        directors = [a.get('name', '') for a in (d.get('directors') or []) if a.get('name')]
        area = '/'.join(d.get('countries') or [])
        genres = '/'.join(d.get('genres') or [])
        pic = d.get('pic') or {}
        return {
            'vod_id': did,
            'vod_name': d.get('title', ''),
            'vod_pic': pic.get('large') or pic.get('normal') or '',
            'vod_year': str(d.get('year') or ''),
            'vod_area': area,
            'vod_actor': ','.join(actors),
            'vod_director': ','.join(directors),
            'vod_remarks': ('★%s' % rating) if rating else '',
            'type_name': genres,
            'vod_content': (d.get('intro') or '')[:2000],
            'vod_play_from': '',
            'vod_play_url': '',
        }

    # ==================== 播放资源站(白嫖者联盟) ====================
    @staticmethod
    def _rand_hex(n):
        try:
            import secrets
            return secrets.token_hex(n)
        except Exception:
            return ''.join('%02x' % ((int(time.time() * 1e9) + i) % 256) for i in range(n))

    @staticmethod
    def _sign(method, path, ts, nonce):
        msg = '%s\n%s\n%s\n%s' % (method, path, ts, nonce)
        try:
            import hmac
            import hashlib
            return hmac.new(BPZ_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
        except Exception:
            return ''

    def _bpz_headers(self, path):
        ts = str(int(time.time() * 1000))
        nonce = self._rand_hex(16)
        return {
            'x-ai-movie-timestamp': ts,
            'x-ai-movie-nonce': nonce,
            'x-ai-movie-signature': self._sign('GET', path, ts, nonce),
            'x-ai-movie-client-name': 'movie-search-frontend',
            'x-ai-movie-client-version': '1.0.0',
            'x-ai-movie-protocol-version': '2026-07-05.library-v2.playback-v1',
            'x-ai-movie-build-version': 'aimovie-v2026.08.15.5-150e53a6eed3',
            'User-Agent': UA,
        }

    def _bpz_get(self, path, params=None):
        if params:
            path = path + '?' + urllib.parse.urlencode(params)
        body = self._get(self.bpz + path, headers=self._bpz_headers(path))
        if not body:
            return None
        try:
            return json.loads(body)
        except Exception:
            return None

    def _bpz_match(self, title, year):
        """片名+年份 → 资源站 variant_id; 返回 None 表示无资源"""
        d = self._bpz_get('/v1/suggest', {'q': title, 'mode': 'search'})
        if not d:
            return None
        exact, loose = None, None
        for s in d.get('suggestions', []):
            lab = s.get('label', '')
            vid = (s.get('target') or {}).get('variant_id', '')
            if not vid:
                continue
            if lab == title:
                exact = vid
                plan = s.get('plan') or {}
                if year and str(plan.get('year', '')) == str(year):
                    return vid
            elif title and lab.startswith(title):
                loose = vid
        return exact or loose

    def _bpz_episodes(self, vid):
        """拉取资源站全部集数(48集/页自动翻页)"""
        eps = []
        offset = 0
        base = '/v1/catalog/' + urllib.parse.quote(vid, safe='') + '/episodes'
        while True:
            e = self._bpz_get(base, {'offset': str(offset), 'limit': '100'})
            if not e or not e.get('episodes'):
                break
            eps.extend(e['episodes'])
            pg = e.get('episode_pagination') or {}
            if not pg.get('has_more'):
                break
            offset = pg.get('offset', 0) + len(e['episodes'])
            if offset >= pg.get('total_count', 0):
                break
        return eps

    def _probe_lines(self, token):
        """探测可用线路名(4K/官方线路优先)"""
        d = self._resolve(token)
        if not d:
            return ['默认线路']

        def sort_key(lo):
            n = lo.get('provider_name') or ''
            if '4k' in n.lower():
                return 0
            if '官方' in n or '1080' in n or '高清' in n:
                return 1
            return 2

        ordered = sorted(d.get('line_options', []), key=sort_key)
        names, used, lines = [], {}, []
        for lo in ordered:
            n = lo.get('provider_name') or ''
            if n:
                names.append(n)
        if not names:
            return ['默认线路']
        for n in names:
            used[n] = used.get(n, 0) + 1
            lines.append('%s%d' % (n, used[n]) if used[n] > 1 else n)
        return lines

    def _resolve(self, token, ps=None):
        path = '/v1/playback/resolve/' + urllib.parse.quote(token, safe='')
        if ps:
            path += '?ps=' + urllib.parse.quote(ps, safe='')
        body = self._get(self.play + path, headers={'User-Agent': UA})
        if not body:
            return None
        try:
            return json.loads(body)
        except Exception:
            return None

    @staticmethod
    def _play_header(url):
        h = {'User-Agent': UA}
        try:
            host = urllib.parse.urlparse(url).hostname or ''
        except Exception:
            host = ''
        if any(k in host for k in ('bpz.app', 'baipiaozhe.com')):
            h['Referer'] = 'https://bpz.app/'
        return h

    # ==================== 播放解析 ====================
    def playerContent(self, flag, id, vipFlags):
        pid = str(id).strip()
        if pid.startswith('db://'):
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': {'User-Agent': UA}}
        token = pid[len('bpz://'):] if pid.startswith('bpz://') else pid

        result = {'parse': 0, 'playUrl': '', 'url': '', 'header': {'User-Agent': UA}}
        d = self._resolve(token)
        if not d:
            result['parse'] = 1
            result['url'] = '%s/v1/playback/resolve/%s' % (self.play, token)
            return result

        lines = d.get('line_options', [])

        # 0) 用户显式选择线路
        if flag and flag != '豆瓣':
            target = None
            for lo in lines:
                if lo.get('provider_name') == flag or lo.get('label') == flag:
                    target = lo
                    break
            if not target:
                f = str(flag)
                for lo in lines:
                    n = lo.get('provider_name', '')
                    if n and (f == n or f.startswith(n)):
                        target = lo
                        break
            if target:
                got = self._line_url(d, token, target)
                if got:
                    result['url'], result['header'] = got
                    return result

        # 1) 官方线路换票
        for lo in lines:
            if lo.get('url_kind') != 'resolve_ticket':
                continue
            got = self._line_url(d, token, lo)
            if got:
                result['url'], result['header'] = got
                return result

        # 2) 第三方 m3u8
        for lo in lines:
            u = lo.get('url', '')
            if lo.get('url_kind') == 'm3u8' and u.startswith('http'):
                result['url'] = u
                result['header'] = self._play_header(u)
                return result

        # 3) 嗅探兜底
        result['parse'] = 1
        result['url'] = '%s/v1/playback/resolve/%s' % (self.play, token)
        return result

    def _line_url(self, d, token, lo):
        """单条线路取真实播放地址; 返回 (url, header) 或 None"""
        u = lo.get('url', '')
        if lo.get('url_kind') == 'm3u8' and u.startswith('http'):
            return u, self._play_header(u)
        if lo.get('url_kind') == 'resolve_ticket':
            ps = lo.get('playback_source_id', '')
            if not ps:
                return None
            d2 = self._resolve(token, ps)
            if not d2:
                return None
            name = lo.get('provider_name', '')
            for lo2 in d2.get('line_options', []):
                if lo2.get('url_kind') not in ('m3u8', 'mp4'):
                    continue
                u2 = lo2.get('url', '')
                if not u2.startswith('http'):
                    continue
                if (lo2.get('provider_name') == name or
                        lo2.get('playback_source_id') == ps or
                        lo2.get('id') == lo.get('id')):
                    return u2, self._play_header(u2)
            for lo2 in d2.get('line_options', []):
                u2 = lo2.get('url', '')
                if lo2.get('url_kind') in ('m3u8', 'mp4') and u2.startswith('http'):
                    return u2, self._play_header(u2)
        return None


# ============================================================
# 本地自测:  python3 csp_douban.py
# ============================================================
if __name__ == '__main__':
    s = Spider().init('')
    print('== 分类 ==')
    print([c['type_name'] for c in s.homeContent(False)['class']])

    print('\n== 首页(豆瓣热门电影) ==')
    hv = s.homeVideoContent()['list']
    print('共%d条, 首条: %s' % (len(hv), hv[0] if hv else '空'))

    print('\n== 分类(电影 + 筛选: 豆瓣高分) ==')
    lst = s.categoryContent('movie', 1, {'综合': '豆瓣高分'}, {})['list']
    print('共%d条, 首条: %s' % (len(lst), lst[0] if lst else '空'))

    print('\n== 分类(动漫 + 筛选: 热血) ==')
    lst2 = s.categoryContent('anime', 1, {'类型': '热血'}, {})['list']
    print('共%d条, 首条: %s' % (len(lst2), lst2[0] if lst2 else '空'))

    print('\n== 搜索(火影) ==')
    r = s.searchContent('火影', True)['list']
    print('共%d条:' % len(r), [x['vod_name'] for x in r[:6]])

    print('\n== 详情(首页第一部) ==')
    did = hv[0]['vod_id'] if hv else '35811064'
    d = s.detailContent([did])['list'][0]
    print('%s | %s年 | %s | 导演:%s' % (d['vod_name'], d['vod_year'],
                                        d['vod_remarks'], d['vod_director'][:30]))
    print('简介: %s' % d['vod_content'][:60])
    print('线路(%d): %s' % (len(d['vod_play_from'].split('$$$')), d['vod_play_from'][:80]))
    pu = d['vod_play_url']
    if pu and 'db://' not in pu:
        print('选集: %d集, 第1集: %s' % (len(pu.split('#')), pu.split('#')[0][:50]))

    print('\n== 播放解析 ==')
    if pu and 'db://' not in pu:
        first = pu.split('$$$')[0].split('#')[0].split('$')[1]
        pr = s.playerContent(d['vod_play_from'].split('$$$')[0], first, '')
        print('url: %s' % pr['url'])
    else:
        print('(该片资源站无资源, 无播放地址)')
