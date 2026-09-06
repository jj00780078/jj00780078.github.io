# -*- coding: utf-8 -*-
"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '瓜子影视',
  lang: 'hipy'
})
"""

# 瓜子影视 https://gz360.tv
# 数据接口为 Nuxt 前端加密 API（AES-128-CBC + JSON 封装），本源直接调用真实接口。

import json
import math
import sys

from base.spider import Spider

sys.path.append('..')


class Spider(Spider):
    API = 'https://haiwaiapi.1fc8ab0.com'
    AES_KEY = b'181cc88340ae5b2b'
    AES_IV = b'4423d1e2773476ce'
    PAGE_SIZE = 24

    def init(self, extend=''):
        self.extend = extend or ''
        self.api = self.API
        self.path = '/Pc'
        self.name = '瓜子影视'

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return None

    def destroy(self):
        pass

    def _aes_encrypt(self, data):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        cipher = AES.new(self.AES_KEY, AES.MODE_CBC, self.AES_IV)
        return cipher.encrypt(pad(raw, AES.block_size)).hex()

    def _aes_decrypt(self, text):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        cipher = AES.new(self.AES_KEY, AES.MODE_CBC, self.AES_IV)
        return json.loads(unpad(cipher.decrypt(bytes.fromhex(text)), AES.block_size).decode('utf-8'))

    def _post(self, path, data, retries=2):
        body = json.dumps({'params': self._aes_encrypt(data)}, ensure_ascii=False)
        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = self.post(
                    self.api + self.path + path,
                    data=body,
                    headers={'Content-Type': 'application/json'},
                    timeout=20,
                )
                payload = resp.json()
                if isinstance(payload, dict):
                    inner = payload.get('data')
                    if isinstance(inner, str) and inner:
                        try:
                            return self._aes_decrypt(inner)
                        except Exception:
                            return payload
                return payload
            except Exception as e:
                last_error = e
        raise last_error

    def homeContent(self, filter):
        classes = []
        try:
            data = self._post('/Index/indexPid', {'type': 1})
            for item in data or []:
                if not isinstance(item, dict):
                    continue
                if item.get('type') not in ('video', 'recommend'):
                    continue
                if item.get('is_show_kenny') != 1:
                    continue
                pid = item.get('pid')
                name = item.get('name')
                if pid in (None, 0, '', '0'):
                    continue
                # 漫剧接口暂无列表数据，跳过
                if str(pid) == '62344':
                    continue
                classes.append({'type_id': str(pid), 'type_name': str(name)})
        except Exception:
            pass
        if not classes:
            classes = [
                {'type_id': '1', 'type_name': '热门'},
                {'type_id': '3', 'type_name': '电影'},
                {'type_id': '4', 'type_name': '国产剧'},
                {'type_id': '5', 'type_name': '动漫'},
                {'type_id': '6', 'type_name': '综艺'},
                {'type_id': '16', 'type_name': '短剧'},
                {'type_id': '23656', 'type_name': '海外剧'},
            ]
        return {'class': classes, 'filters': {}}

    def homeVideoContent(self):
        vods = []
        seen = set()
        try:
            data = self._post('/Resource/IndexShow/ShowOnes', {})
            for section in data.get('list') or []:
                for item in section.get('list') or []:
                    vid = str(item.get('vod_id') or '')
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    vods.append({
                        'vod_id': vid,
                        'vod_name': item.get('c_name') or item.get('vod_name') or '',
                        'vod_pic': item.get('c_pic') or item.get('vod_pic') or '',
                        'vod_remarks': item.get('vod_continu') or '',
                        'vod_score': item.get('vod_douban_score') or item.get('vod_scroe') or '',
                    })
        except Exception:
            pass
        return {'list': vods}

    def categoryContent(self, tid, pg, filter, extend):
        page = max(int(pg or 1), 1)
        data = self._post('/Category/GetChoiceList', {
            'pid': int(tid),
            'pageSize': self.PAGE_SIZE,
            'page': page,
        })
        total = int((data.get('total') or 0) if isinstance(data, dict) else 0)
        vods = []
        for item in (data.get('list') or []) if isinstance(data, dict) else []:
            vods.append({
                'vod_id': str(item.get('vod_id') or ''),
                'vod_name': item.get('c_name') or item.get('vod_name') or '',
                'vod_pic': item.get('c_pic') or item.get('vod_pic') or '',
                'vod_remarks': item.get('vod_continu') or '',
                'vod_score': item.get('vod_douban_score') or item.get('vod_scroe') or '',
            })
        pagecount = math.ceil(total / self.PAGE_SIZE) if total > 0 else 1
        return {'list': vods, 'page': page, 'pagecount': pagecount, 'limit': self.PAGE_SIZE, 'total': total}

    def detailContent(self, ids):
        vod_id = str(ids[0] if isinstance(ids, list) else ids)
        try:
            info = self._post('/Resource/GetVodInfo', {'vod_id': vod_id})
            play = self._post('/Resource/GetOnePlayList', {'vod_id': vod_id, 'pageSize': 0, 'page': 1})
        except Exception:
            return {'list': []}
        vi = (info.get('vodInfo') or {}) if isinstance(info, dict) else {}
        urls = (play.get('urls') or []) if isinstance(play, dict) else []
        play_url = '#'.join(
            '{}${}'.format(u.get('name') or u.get('sort') or '', u.get('url') or '')
            for u in urls if u.get('url')
        )
        vod = {
            'vod_id': vod_id,
            'vod_name': str(vi.get('vod_name') or '').strip(),
            'vod_pic': vi.get('pic') or vi.get('vod_pic') or '',
            'vod_actor': vi.get('vod_actor') or '',
            'vod_director': vi.get('vod_director') or '',
            'vod_content': vi.get('vod_use_content') or vi.get('vod_content') or '',
            'vod_year': vi.get('vod_year') or '',
            'vod_area': vi.get('vod_area') or '',
            'vod_remarks': vi.get('vod_continu') or vi.get('vod_title') or '',
            'vod_score': vi.get('vod_scroe') or '',
            'vod_play_from': '瓜子',
            'vod_play_url': play_url,
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        page = max(int(pg or 1), 1)
        data = self._post('/Search/GetConditionList', {
            'tid': 0,
            'area': 0,
            'year': 0,
            'sort': 'd_id',
            'keywords': str(key),
            'page': page,
            'pageSize': self.PAGE_SIZE,
        })
        total = int((data.get('total') or 0) if isinstance(data, dict) else 0)
        vods = []
        for item in (data.get('list') or []) if isinstance(data, dict) else []:
            vods.append({
                'vod_id': str(item.get('vod_id') or ''),
                'vod_name': item.get('vod_name') or item.get('c_name') or '',
                'vod_pic': item.get('vod_pic') or item.get('c_pic') or '',
                'vod_remarks': item.get('new_continue') or item.get('vod_continu') or '',
                'vod_score': item.get('vod_scroe') or item.get('vod_douban_score') or '',
            })
        pagecount = math.ceil(total / self.PAGE_SIZE) if total > 0 else 1
        return {'list': vods, 'page': page, 'pagecount': pagecount, 'limit': self.PAGE_SIZE, 'total': total}

    def playerContent(self, flag, id, vipFlags=None):
        return {'parse': 0, 'url': str(id)}


if __name__ == '__main__':
    pass
