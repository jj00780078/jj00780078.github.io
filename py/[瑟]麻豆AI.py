# -*- coding: utf-8 -*-
"""
麻豆传媒AI (madouai.xyz) Python Spider
兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)
"""
import sys
import json
import time
from urllib.parse import quote

sys.path.append('..')

try:
   from base.spider import Spider
except ImportError:
   import requests as rq
   class Spider:
       def fetch(self, url, headers=None, **kw):
           kw.pop('timeout', None)
           r = rq.get(url, headers=headers, timeout=15, **kw)
           r.encoding = 'utf-8'
           return r


class Spider(Spider):
   HOST = 'https://www.madouai.xyz'
   API_BASE = '/api/v1'

   # 虚拟父分类：把某个子分类抽出来独立成父分类
   VIRTUAL_MENUS = [
       {'tid': '100', 'name': '麻豆原创AI', 'cat_id': '6'},
   ]

   def getName(self):
       return "麻豆传媒AI"

   def init(self, extend=''):
       if isinstance(extend, list):
           self.extend = ''
       else:
           self.extend = extend or ''
       self.host = self.HOST
       self.header = {
           'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36',
           'Accept': 'application/json, text/plain, */*',
           'Accept-Language': 'zh-CN,zh;q=0.9',
           'Referer': self.host + '/',
       }
       self._home_cache = []
       self._home_cache_time = 0
       self._classes = None
       self._filters = None
       self._menu_default_cat = {}   # menuId -> default categoryId
       self._menu_cat_map = {}       # menuId -> [categoryId, ...]

   def _url(self, path):
       if not path:
           return self.host
       if path.startswith('http'):
           return path
       return self.host + path if path.startswith('/') else self.host + '/' + path

   def _api(self, path, params=None, timeout=15):
       try:
           url = self.host + self.API_BASE + path
           if params:
               query = '&'.join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
               url = f"{url}?{query}"
           rsp = self.fetch(url, headers=self.header, timeout=timeout)
           try:
               rsp.encoding = 'utf-8'
           except Exception:
               pass
           data = rsp.json()
           if int(data.get('code', 0)) == 200:
               return data.get('data')
           return None
       except Exception:
           return None

   def _video_to_vod(self, item):
       vid = str(item.get('id', ''))
       title = item.get('title', '')
       cover = item.get('coverUrl', '')
       if cover and not cover.startswith('http'):
           cover = self.host + cover
       duration = item.get('durationSec', 0)
       remarks = item.get('categoryName', '')
       if duration:
           m, s = divmod(int(duration), 60)
           remarks = f"{m:02d}:{s:02d}" + (f" | {remarks}" if remarks else "")
       return {
           'vod_id': vid,
           'vod_name': title,
           'vod_pic': cover,
           'vod_remarks': remarks,
       }

   def _video_to_detail(self, item):
       vid = str(item.get('id', ''))
       title = item.get('title', '')
       cover = item.get('coverUrl', '')
       if cover and not cover.startswith('http'):
           cover = self.host + cover

       video_url = item.get('videoUrl', '')
       if video_url:
           if video_url.endswith('.m3u8'):
               video_url = self.host + '/api/v1/m3u8/proxy?path=' + quote(video_url, safe='')
           elif not video_url.startswith('http'):
               video_url = self.host + '/' + video_url

       content = item.get('description') or item.get('content') or ''
       author = item.get('authorName', '')
       duration = item.get('durationSec', 0)
       remarks = ''
       if duration:
           m, s = divmod(int(duration), 60)
           remarks = f"{m:02d}:{s:02d}"

       play_url = f"播放${video_url}" if video_url else ''
       return {
           'vod_id': vid,
           'vod_name': title,
           'vod_pic': cover,
           'type_name': item.get('categoryName', ''),
           'vod_year': '',
           'vod_area': '',
           'vod_remarks': remarks,
           'vod_actor': author,
           'vod_director': '',
           'vod_content': content[:500] if content else '',
           'vod_play_from': '默认线路',
           'vod_play_url': play_url,
       }

   def _parse_list_response(self, data, pg):
       videos = []
       total = 0
       pagecount = 1
       if data and isinstance(data, dict):
           items = data.get('items') or []
           total = data.get('total', len(items))
           pagecount = data.get('totalPages', 1)
           for item in items:
               v = self._video_to_vod(item)
               if v.get('vod_id'):
                   videos.append(v)
       return {
           'list': videos,
           'page': pg,
           'pagecount': pagecount or 1,
           'limit': 20,
           'total': total or len(videos),
       }

   # ========== 分类与筛选器 ==========
   def _load_menus(self):
       if self._classes is not None:
           return self._classes

       categories = self._api('/categories', timeout=10) or []
       menus = self._api('/menus', timeout=10) or []

       classes = []
       filters = {}
       self._menu_default_cat = {}
       self._menu_cat_map = {}

       # 按 menu 分组 category
       cat_by_menu = {}
       for c in categories:
           if c.get('type') != 'video' or not c.get('enabled', True):
               continue
           mid = c.get('menuId')
           cid = c.get('id')
           if mid and cid:
               if mid not in cat_by_menu:
                   cat_by_menu[mid] = []
               cat_by_menu[mid].append({
                   'n': c.get('name', ''),
                   'v': str(cid),
               })

       # 虚拟父分类要抽出的 cat_id 集合
       virtual_cat_ids = {vm['cat_id'] for vm in self.VIRTUAL_MENUS}

       # 构建真实 menu 的分类（保留原始顺序）
       real_classes = []
       for m in menus:
           mid = m.get('id')
           name = m.get('name', '')
           mtype = m.get('type', '')
           if not mid or not name or mtype != 'video':
               continue

           tid = str(mid)
           real_classes.append({'type_id': tid, 'type_name': name, 'order': mid})

           # 过滤掉被抽走的子分类
           raw_cats = cat_by_menu.get(mid, [])
           filtered_cats = [c for c in raw_cats if c['v'] not in virtual_cat_ids]
           self._menu_cat_map[mid] = [c['v'] for c in filtered_cats]

           # 默认子分类：优先非 27 的
           if filtered_cats:
               default = None
               for c in filtered_cats:
                   if c['v'] != '27':
                       default = c['v']
                       break
               if not default:
                   default = filtered_cats[0]['v']
               self._menu_default_cat[mid] = default

           flt = []
           if filtered_cats:
               cat_list = [{'n': '全部', 'v': ''}] + filtered_cats
               flt.append({'key': 'cat', 'name': '子分类', 'value': cat_list})
           filters[tid] = flt

       # 组装最终分类顺序：第一个真实 menu -> 虚拟分类 -> 剩余真实 menu
       classes = []
       if real_classes:
           classes.append(real_classes[0])  # 原创精选
       for vm in self.VIRTUAL_MENUS:
           vtid = vm['tid']
           vname = vm['name']
           classes.append({'type_id': vtid, 'type_name': vname})
           # 虚拟父分类：不要子分类筛选器
           filters[vtid] = []
       # 剩余真实 menu
       for rc in real_classes[1:]:
           classes.append({'type_id': rc['type_id'], 'type_name': rc['type_name']})

       self._classes = classes
       self._filters = filters
       return classes

   def _get_filters(self):
       if self._filters is None:
           self._load_menus()
       return self._filters or {}

   # ========== 首页 ==========
   def homeContent(self, filter):
       return {
           'class': self._load_menus(),
           'filters': self._get_filters(),
       }

   def homeVideoContent(self):
       now = int(time.time())
       if self._home_cache and now - self._home_cache_time < 300:
           return {'list': self._home_cache[:72]}

       videos = []
       seen = set()

       # 精选内容不变：从真实 menu 里取不同子分类（不包含虚拟分类 cat=6）
       pick_cats = []
       for mid, cats in self._menu_cat_map.items():
           for cid in cats:
               if cid != '27':
                   pick_cats.append(cid)
                   break
           if len(pick_cats) >= 3:
               break

       for cid in pick_cats:
           try:
               data = self._api('/videos', {'page': 1, 'limit': 24, 'categoryId': cid}, timeout=10)
               if data:
                   for item in data.get('items') or []:
                       v = self._video_to_vod(item)
                       vid = v.get('vod_id')
                       if vid and vid not in seen:
                           seen.add(vid)
                           videos.append(v)
                       if len(videos) >= 72:
                           break
           except Exception:
               continue
           if len(videos) >= 72:
               break

       # 兜底补全站最新
       if len(videos) < 72:
           try:
               data = self._api('/videos', {'page': 1, 'limit': 72}, timeout=10)
               if data:
                   for item in data.get('items') or []:
                       v = self._video_to_vod(item)
                       vid = v.get('vod_id')
                       if vid and vid not in seen:
                           seen.add(vid)
                           videos.append(v)
                       if len(videos) >= 72:
                           break
           except Exception:
               pass

       self._home_cache = videos[:72]
       self._home_cache_time = now
       return {'list': self._home_cache}

   # ========== 分类列表 ==========
   def categoryContent(self, tid, pg, filter, extend):
       pg = int(pg or 1)
       ext = {}
       if extend:
           if isinstance(extend, dict):
               ext = extend
           elif isinstance(extend, str):
               try:
                   ext = json.loads(extend)
               except Exception:
                   ext = {}

       params = {'page': pg, 'limit': 20}

       # 虚拟父分类处理：直接查绑定的 categoryId，不读 extend
       virtual_map = {vm['tid']: vm['cat_id'] for vm in self.VIRTUAL_MENUS}
       if tid in virtual_map:
           params['categoryId'] = virtual_map[tid]
       else:
           cat_id = ext.get('cat', '')
           if cat_id:
               params['categoryId'] = cat_id
           else:
               menu_id = int(tid) if tid and str(tid).isdigit() else 0
               default_cat = self._menu_default_cat.get(menu_id)
               if default_cat:
                   params['categoryId'] = default_cat

       data = self._api('/videos', params, timeout=15)
       if data and data.get('items'):
           return self._parse_list_response(data, pg)

       return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

   # ========== 详情页 ==========
   def detailContent(self, ids):
       if isinstance(ids, str):
           ids = [ids]
       vid = ids[0]

       data = self._api(f'/videos/{vid}', timeout=15)
       if data and isinstance(data, dict) and data.get('id'):
           return {'list': [self._video_to_detail(data)]}

       data = self._api(f'/posts/{vid}', timeout=15)
       if data and isinstance(data, dict) and data.get('id'):
           return {'list': [self._video_to_detail(data)]}

       return {'list': []}

   # ========== 搜索 ==========
   def searchContent(self, key, quick, pg='1'):
       pg = int(pg or 1)
       params = {'keyword': key, 'page': pg, 'limit': 20}
       data = self._api('/videos', params, timeout=15)
       if data and data.get('items'):
           return self._parse_list_response(data, pg)
       return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

   # ========== 播放解析 ==========
   def playerContent(self, flag, id, vipFlags):
       if not id:
           return {'parse': 1, 'playUrl': '', 'url': ''}

       url = id if str(id).startswith('http') else self._url(id)

       if '.m3u8' in url:
           return {
               'parse': 0,
               'playUrl': '',
               'url': url,
               'header': {
                   'User-Agent': self.header['User-Agent'],
                   'Referer': self.host + '/',
               },
               'format': 'application/x-mpegURL',
           }

       if '.mp4' in url:
           return {
               'parse': 0,
               'playUrl': '',
               'url': url,
               'header': {
                   'User-Agent': self.header['User-Agent'],
                   'Referer': self.host + '/',
               },
           }

       return {'parse': 1, 'playUrl': '', 'url': url, 'header': self.header}

   def localProxy(self, param):
       import requests as _rq
       raw_url = param.get('url') or param.get('u') or ''
       if not raw_url:
           return [200, 'text/plain', b'no url', '']
       headers = {
           'User-Agent': self.header['User-Agent'],
           'Referer': self.host + '/',
       }
       try:
           r = _rq.get(raw_url, headers=headers, timeout=30)
           ct = r.headers.get('content-type') or 'application/octet-stream'
           return [200, ct, r.content, '']
       except Exception:
           return [500, 'text/plain', b'proxy error', '']

   def destroy(self):
       pass

   def close(self):
       self.destroy()