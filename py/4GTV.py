# -*- coding: utf-8 -*-
# 4GTV - 绿豆 TVBox Python 版

import sys
sys.path.append('..')

import base64
import datetime
import hashlib
import html
import json
import re
import ssl
import time
import urllib.request
from base.spider import Spider


class Spider(Spider):
    def __init__(self):
        self.api1 = 'https://api2.4gtv.tv/TV/GetChannelUrl'
        self.api2 = 'https://api2.4gtv.tv/App/GetChannelUrl2'
        self.list_api = 'https://api2.4gtv.tv/Channel/GetAllChannel2/TV'
        self.web = 'https://www.4gtv.tv'
        self.plain_key = '7F3DD6981A72707B12A8C0CC80A3C96B75B9057AD55F1AE1'
        self.ua = 'Dalvik/2.1.0 (Linux; U; Android 13; Android TV Build/TP1A.220624.014)'
        self.channels = []
        # 静态分类兜底：即使壳内首次联网失败，也不会显示空白首页。
        self.classes = [

            {'type_id': '綜合', 'type_name': '綜合'},
            {'type_id': '音樂綜藝', 'type_name': '音樂綜藝'},
            {'type_id': '兒童與青少年', 'type_name': '兒童與青少年'},
            {'type_id': '新聞財經', 'type_name': '新聞財經'},
            {'type_id': '運動健康生活', 'type_name': '運動健康生活'},
            {'type_id': '戲劇', 'type_name': '戲劇'},
            {'type_id': '電影', 'type_name': '電影'},
        ]
        self.cache_time = 0
        self.play_cache = {}

    def init(self, extend=''):
        return None

    def getName(self):
        return '4GTV'

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv)(\?|$)', str(url or ''), re.I))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def _auth(self):
        day = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')
        raw = (day + self.plain_key).encode('utf-8')
        return base64.b64encode(hashlib.sha512(raw).digest()).decode('ascii')

    def _headers(self, json_body=False):
        h = {
            'Host': 'api2.4gtv.tv',
            'User-Agent': self.ua,
            'fsDEVICE': 'TV',
            'fsVERSION': '1.5.4',
            '4GTV_AUTH': self._auth(),
        }
        if json_body:
            h['Content-Type'] = 'application/json'
        return h

    def _request_json(self, url, payload=None):
        headers = self._headers(payload is not None)
        # 优先使用 TVBox Python 运行环境自带请求方法，与绿豆/OK影视兼容。
        try:
            if payload is None:
                resp = self.fetch(url, headers=headers, timeout=12)
            elif hasattr(self, 'post'):
                resp = self.post(url, json=payload, headers=headers, timeout=12)
            else:
                resp = self.fetch(url, data=json.dumps(payload), headers=headers, timeout=12)
            text = getattr(resp, 'text', '') or getattr(resp, 'content', b'')
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='ignore')
            if text:
                return json.loads(text)
        except Exception as e:
            print('4GTV壳内请求失败，尝试标准请求:', url, e)

        # 桌面 Python 或不提供 self.fetch 的环境使用 urllib 兜底。
        try:
            data = None
            if payload is not None:
                data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method='POST' if data is not None else 'GET')
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                raw = resp.read().decode('utf-8', errors='ignore')
            return json.loads(raw) if raw else {}
        except Exception as e:
            print('4GTV请求失败:', url, e)
            return {}

    def _request_text(self, url):
        headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/150.0.0.0 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': self.web + '/channel',
        }
        try:
            resp = self.fetch(url, headers=headers, timeout=12)
            text = getattr(resp, 'text', '') or getattr(resp, 'content', b'')
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='ignore')
            if text:
                return text
        except Exception as e:
            print('4GTV壳内网页请求失败，尝试标准请求:', url, e)

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ssl._create_unverified_context(), timeout=12) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print('4GTV网页请求失败:', url, e)
            return ''

    def _group_name(self, raw):
        parts = re.split(r'[^\u4e00-\u9fa5a-zA-Z0-9]+', str(raw or ''))
        name = next((x.strip() for x in parts if x.strip()), '未分类')
        if name in ('現場直擊', '國會頻道'):
            return '新聞財經'
        return name

    def _priority(self, asset):
        asset = str(asset or '')
        if asset.lower().startswith('litv-'):
            return 0
        if asset.lower().startswith('4gtv-4gtv'):
            return 1
        return 2

    def _load_channels(self, force=False):
        if self.channels and not force and time.time() - self.cache_time < 6 * 3600:
            return True
        j = self._request_json(self.list_api)
        rows = j.get('Data') if isinstance(j, dict) else None
        if not isinstance(rows, list):
            return bool(self.channels)

        groups = {}
        for ch in rows:
            name = str(ch.get('fsNAME') or '未知频道')
            cid = ch.get('fnID')
            asset = ch.get('fs4GTV_ID')
            if cid is not None and asset and '東森購物' not in name:
                groups.setdefault(name, []).append(ch)

        kept = []
        for name, items in groups.items():
            if name in ('TVBS', 'TVBS新聞'):
                media = next((x for x in items if 'media' in str(x.get('fs4GTV_ID', '')).lower()), None)
                if media:
                    kept.append(media)
                    continue
            kept.append(min(items, key=lambda x: self._priority(x.get('fs4GTV_ID'))))

        category_order = []
        clean = []
        for ch in kept:
            group = self._group_name(ch.get('fsTYPE_NAME'))
            if group not in category_order:
                category_order.append(group)
            clean.append({
                'id': str(ch.get('fnID')),
                'asset': str(ch.get('fs4GTV_ID')),
                'name': str(ch.get('fsNAME') or '未知频道'),
                'group': group,
                # OK影视的卡片是海报比例，优先用频道封面，避免横向 Logo 被放大裁切。
                'pic': str(ch.get('fsHEAD_FRAME') or ch.get('fsLOGO_MOBILE') or
                           ch.get('fsLOGO_PC') or ''),
                'set': str((ch.get('lstSETs') or ['1'])[0]),
                'free': bool(ch.get('fcFREE')),
                'overseas': bool(ch.get('fcOVERSEAS')),
            })
        self.channels = clean
        if category_order:
            self.classes = [{'type_id': x, 'type_name': x} for x in category_order]
        self.cache_time = time.time()
        return True

    def _vod(self, ch):
        play_id = ch['id'] + '|' + ch['asset'] + '|' + ch.get('set', '1')
        if not ch.get('free', True):
            remarks = '付费频道'
        elif ch.get('overseas'):
            remarks = '海外可播'
        else:
            remarks = '限台湾'
        return {
            'vod_id': play_id,
            'vod_name': ch['name'],
            'vod_pic': ch.get('pic', ''),
            'vod_remarks': remarks,
        }

    def homeContent(self, filter):
        self._load_channels()
        return {'class': self.classes}

    def homeVideoContent(self):
        self._load_channels()
        return {'list': [self._vod(x) for x in self.channels[:30]]}

    def categoryContent(self, tid, pg, filter, extend):
        self._load_channels()
        page = max(1, int(pg or 1))
        size = 60
        rows = [x for x in self.channels if x['group'] == str(tid)]
        start = (page - 1) * size
        videos = [self._vod(x) for x in rows[start:start + size]]
        pagecount = max(1, (len(rows) + size - 1) // size)
        return {
            'list': videos,
            'page': page,
            'pagecount': pagecount,
            'limit': size,
            'total': len(rows),
        }

    def searchContent(self, key, quick, pg='1'):
        self._load_channels()
        wd = str(key or '').strip().lower()
        rows = [x for x in self.channels if wd in x['name'].lower()] if wd else []
        return {'list': [self._vod(x) for x in rows], 'page': 1, 'pagecount': 1,
                'limit': len(rows), 'total': len(rows)}

    def detailContent(self, ids):
        play_id = str(ids[0] if isinstance(ids, list) else ids)
        self._load_channels()
        parts = play_id.split('|')
        ch = next((x for x in self.channels if len(parts) >= 2 and
                   x['id'] == parts[0] and x['asset'] == parts[1]), None)
        name = ch['name'] if ch else '4GTV直播'
        pic = ch.get('pic', '') if ch else ''
        vod = {
            'vod_id': play_id,
            'vod_name': name,
            'vod_pic': pic,
            'vod_remarks': '直播',
            'vod_content': '4GTV直播频道',
            'vod_play_from': '4GTV',
            'vod_play_url': '直播$' + play_id,
        }
        return {'list': [vod]}

    def _play_urls(self, api, cid, asset):
        payload = {
            'fnCHANNEL_ID': int(cid),
            'fsASSET_ID': asset,
            'fsDEVICE_TYPE': 'tv',
            'clsAPP_IDENTITY_VALIDATE_ARUS': {'fsVALUE': ''},
        }
        j = self._request_json(api, payload)
        data = j.get('Data') if isinstance(j, dict) else None
        urls = data.get('flstURLs') if isinstance(data, dict) else None
        return urls if isinstance(urls, list) else []

    def _select_url(self, urls, asset, api2=False, cid=0):
        if api2 and int(cid) == 57 and urls:
            return urls[0]
        candidates = [x for x in urls if isinstance(x, str) and '-mozai.4gtv.tv' in x]
        if not candidates:
            candidates = [x for x in urls if isinstance(x, str) and x.startswith('http')]
        if not candidates:
            return ''
        url = candidates[0]
        if api2 and 'live' in asset and 'index.m3u8' in url:
            url = url.replace('index.m3u8', '1080.m3u8')
        return url

    def _decode_js_string(self, value):
        value = html.unescape(str(value or ''))
        try:
            # 官网常用 \/、\u0026 等 JavaScript 转义。
            return json.loads('"' + value.replace('"', '\\"') + '"')
        except Exception:
            return value.replace('\\/', '/').replace('\\u0026', '&')

    def _web_play_url(self, cid, asset, set_id='1'):
        page = '%s/channel/%s?set=%s&ch=%s' % (self.web, asset, set_id or '1', cid)
        text = self._request_text(page)
        if not text:
            return ''

        # 成功时官网服务端直接把 flstURLs 写入页面；地区受限时只有
        # resultsErrMessage='02' 和 resultsSuccess=false。
        success = re.search(r'resultsSuccess\s*=\s*true', text, re.I)
        if not success:
            err = re.search(r'resultsErrMessage\s*=\s*[\'\"]([^\'\"]+)', text, re.I)
            if err:
                print('4GTV网页播放受限, code:', err.group(1))
            return ''

        patterns = [
            r'flstURLs\s*=\s*[\'\"](.*?)[\'\"]\s*;',
            r'[\'\"]flstURLs[\'\"]\s*:\s*[\'\"](.*?)[\'\"]',
        ]
        raw = ''
        for pattern in patterns:
            m = re.search(pattern, text, re.I | re.S)
            if m:
                raw = self._decode_js_string(m.group(1))
                break
        if not raw:
            return ''
        urls = [x.strip() for x in raw.split(',') if x.strip().startswith('http')]
        return self._select_url(urls, asset, False, cid)

    def playerContent(self, flag, id, vipFlags):
        play_id = str(id or '')
        if '|' not in play_id:
            return {'parse': 0, 'jx': 0, 'url': ''}
        parts = play_id.split('|')
        cid = parts[0]
        asset = parts[1] if len(parts) > 1 else ''
        set_id = parts[2] if len(parts) > 2 else '1'
        cache = self.play_cache.get(play_id)
        if cache and time.time() < cache[1]:
            target = cache[0]
        else:
            # 用户本地官网可正常播放时，网页服务端下发的地址最可靠。
            target = self._web_play_url(cid, asset, set_id)
            if not target:
                urls = self._play_urls(self.api1, cid, asset)
                target = self._select_url(urls, asset, False, cid)
            if not target:
                urls = self._play_urls(self.api2, cid, asset)
                target = self._select_url(urls, asset, True, cid)
            if target:
                ttl = 600 if asset.startswith('fast-') else 3600
                self.play_cache[play_id] = (target, time.time() + ttl)
        return {
            'parse': 0,
            'jx': 0,
            'url': target or '',
            'header': {'User-Agent': self.ua, 'Referer': 'https://www.4gtv.tv/'},
        }
