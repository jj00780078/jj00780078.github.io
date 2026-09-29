#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
欧乐影院 https://www.olevod.com
API: https://api.olelive.com  (_vv 签名)
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse

try:
    import requests
except ImportError:
    requests = None

sys.path.append('../../')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""):
            pass


class Spider(BaseSpider):
    def __init__(self):
        self.siteUrl = 'https://www.olevod.com'
        self.api = 'https://api.olelive.com'
        self.static = 'https://static.olelive.com/'
        self.userAgent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        self.channels = {
            '1': {'name': '电影', 'type_id': '1'},
            '2': {'name': '电视剧', 'type_id': '2'},
            '14': {'name': '短剧', 'type_id': '14'},
            '3': {'name': '综艺', 'type_id': '3'},
            '4': {'name': '动漫', 'type_id': '4'},
        }

    def getName(self):
        return '欧乐影院'

    def init(self, extend=""):
        if not extend:
            return
        try:
            if isinstance(extend, str) and extend.startswith('http'):
                self.api = extend.rstrip('/')
            elif isinstance(extend, str) and extend.strip().startswith('{'):
                ext = json.loads(extend)
                if ext.get('api'):
                    self.api = str(ext['api']).rstrip('/')
                if ext.get('host'):
                    self.siteUrl = str(ext['host']).rstrip('/')
        except Exception:
            pass

    def _vv(self):
        ts = str(int(time.time()))
        rows = ['', '', '', '']
        for ch in ts:
            bits = bin(ord(ch))[2:]
            rows[0] += bits[2:3] if len(bits) > 2 else ''
            rows[1] += bits[3:4] if len(bits) > 3 else ''
            rows[2] += bits[4:5] if len(bits) > 4 else ''
            rows[3] += bits[5:] if len(bits) > 5 else ''
        parts = []
        for row in rows:
            if not row:
                parts.append('000')
                continue
            hx = format(int(row, 2), 'x')
            while len(hx) < 3:
                hx = '0' + hx
            parts.append(hx)
        n = hashlib.md5(ts.encode('utf-8')).hexdigest()
        return (
            n[0:3] + parts[0] +
            n[6:11] + parts[1] +
            n[14:19] + parts[2] +
            n[22:27] + parts[3] +
            n[30:]
        )

    def fetch(self, url, headers=None, params=None):
        if headers is None:
            headers = {
                'User-Agent': self.userAgent,
                'Referer': self.siteUrl + '/',
                'Origin': self.siteUrl,
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
        try:
            if requests:
                resp = requests.get(url, headers=headers, params=params, timeout=15)
                return resp
            full = url
            if params:
                full += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
            from urllib.request import Request, urlopen
            raw = urlopen(Request(full, headers=headers), timeout=15).read()

            class R:
                def __init__(self, raw):
                    self.text = raw.decode('utf-8', 'ignore')
                    self.status_code = 200
                    self.content = raw

                def json(self):
                    return json.loads(self.text)

            return R(raw)
        except Exception as e:
            print('请求失败: %s, %s' % (url, e))
            return None

    def fetch_json(self, url):
        sep = '&' if '?' in url else '?'
        full = url + sep + '_vv=' + self._vv()
        resp = self.fetch(full)
        if not resp:
            return {}
        try:
            return resp.json()
        except Exception:
            text = getattr(resp, 'text', '') or ''
            m = re.search(r'\{[\s\S]+\}', text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return {}
            return {}

    def fetch_text(self, url):
        resp = self.fetch(url, headers={
            'User-Agent': self.userAgent,
            'Referer': self.siteUrl + '/',
            'Accept': 'text/html,application/xhtml+xml',
        })
        return getattr(resp, 'text', '') if resp else ''

    def _pic(self, p):
        if not p:
            return ''
        p = str(p)
        if p.startswith('http'):
            return p
        return self.static + p.lstrip('/')

    def _parseVideoItem(self, item):
        if not isinstance(item, dict):
            return None
        vid = str(item.get('id') or item.get('vod_id') or '')
        if not vid:
            return None
        remarks = (
            item.get('remarks')
            or item.get('vod_remarks')
            or item.get('continu')
            or item.get('updateInfo')
            or ''
        )
        return {
            'vod_id': vid,
            'vod_name': item.get('name') or item.get('vod_name') or vid,
            'vod_pic': self._pic(
                item.get('picThumb') or item.get('pic') or item.get('vod_pic') or ''
            ),
            'vod_remarks': str(remarks),
        }

    def _list_api(self, type_id, pg, limit=24):
        pg = int(pg or 1)
        # 接口单页实际约 12 条，limit 参数影响有限
        url = '%s/v1/pub/vod/list/true/3/0/0/%s/0/0/update/%s/%s' % (
            self.api, type_id, pg, limit
        )
        data = self.fetch_json(url)
        if data.get('code') not in (0, '0', None) and not (data.get('data') or {}).get('list'):
            # 重试一次新签名
            data = self.fetch_json(url)
        body = data.get('data') or {}
        items = body.get('list') or []
        videos = []
        for x in items:
            v = self._parseVideoItem(x)
            if v:
                videos.append(v)
        total = int(body.get('total') or 0)
        per = max(len(videos), 12) if videos else limit
        pagecount = max(1, (total + per - 1) // per) if total else (pg + 1 if len(videos) >= 10 else pg)
        return videos, pagecount, total or len(videos)

    def homeContent(self, filter):
        classes = [{'type_id': k, 'type_name': v['name']} for k, v in self.channels.items()]
        return {'class': classes, 'filters': {}}

    def homeVideoContent(self):
        videos = []
        try:
            data = self.fetch_json(self.api + '/v1/pub/vod/newest/1/24')
            items = ((data.get('data') or {}).get('list')) or []
            for x in items:
                v = self._parseVideoItem(x)
                if v:
                    videos.append(v)
            if not videos:
                videos, _, _ = self._list_api('1', 1, 24)
        except Exception as e:
            print('获取首页视频失败: %s' % e)
        return {'list': videos[:24]}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        videos, pagecount, total = [], pg, 0
        try:
            info = self.channels.get(str(tid), {'type_id': str(tid)})
            type_id = info.get('type_id', str(tid))
            videos, pagecount, total = self._list_api(type_id, pg, 24)
        except Exception as e:
            print('获取分类内容失败: %s' % e)
        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount,
            'limit': 24,
            'total': total,
        }

    def searchContent(self, key, quick, pg=1):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg=1):
        pg = int(pg or 1)
        videos = []
        try:
            q = urllib.parse.quote(str(key or ''))
            data = self.fetch_json(
                '%s/v1/pub/index/search/%s/vod/0/%s/24' % (self.api, q, pg)
            )
            outer = data.get('data') or {}
            items = []
            # data.data 为分组数组
            blocks = outer.get('data')
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict) and b.get('list'):
                        items.extend(b.get('list') or [])
            if not items:
                items = outer.get('list') or []
            for x in items:
                v = self._parseVideoItem(x)
                if v:
                    videos.append(v)
        except Exception as e:
            print('搜索失败: %s' % e)
        return {
            'list': videos,
            'page': pg,
            'pagecount': pg + 1 if len(videos) >= 12 else pg,
            'limit': 24,
            'total': len(videos),
        }

    def _ep_parts(self, eps):
        parts = []
        for ep in eps or []:
            if not isinstance(ep, dict):
                if isinstance(ep, str) and '$' in ep:
                    parts.append(ep)
                continue
            if ep.get('vip') is True:
                # VIP 作为备选线路名
                u = ep.get('url') or ''
                if not u and isinstance(ep.get('vip_urls'), list) and ep['vip_urls']:
                    u = ep['vip_urls'][0].get('url') or ''
                if u:
                    title = ep.get('title') or ep.get('name') or 'VIP'
                    parts.append('%s$%s' % (title, u))
                continue
            title = ep.get('title') or ep.get('name') or '播放'
            u = ep.get('url') or ''
            if u:
                parts.append('%s$%s' % (title, u))
        return parts

    def detailContent(self, ids):
        vid = str((ids or [''])[0])
        try:
            data = self.fetch_json('%s/v1/pub/vod/detail/%s/true' % (self.api, vid))
            info = data.get('data') or {}
            if not info:
                data = self.fetch_json('%s/v1/pub/vod/detail/%s/true' % (self.api, vid))
                info = data.get('data') or {}
            name = info.get('name') or info.get('vod_name') or vid
            pic = self._pic(info.get('pic') or info.get('picThumb') or info.get('vod_pic') or '')
            remarks = info.get('remarks') or info.get('vod_remarks') or ''
            content = info.get('content') or info.get('vod_content') or info.get('blurb') or ''
            actor = info.get('actor') or info.get('vod_actor') or ''
            director = info.get('director') or info.get('vod_director') or ''
            if isinstance(actor, list):
                actor = ' '.join(str(x) for x in actor)
            if isinstance(director, list):
                director = ' '.join(str(x) for x in director)

            play_from, play_urls = [], []
            urls = info.get('urls') or []
            free = [e for e in urls if not e.get('vip')]
            vip = [e for e in urls if e.get('vip')]
            if not free and not vip:
                # 有的结构把清晰度放 vip_urls
                free = urls

            parts = self._ep_parts(free if free else urls)
            if parts:
                play_from.append('欧乐')
                play_urls.append('#'.join(parts))
            # VIP 线路（若有独立地址）
            vip_parts = []
            for ep in urls:
                if not isinstance(ep, dict):
                    continue
                for vu in (ep.get('vip_urls') or []):
                    if isinstance(vu, dict) and vu.get('url'):
                        vip_parts.append(
                            '%s$%s' % (vu.get('title') or ep.get('title') or 'VIP', vu.get('url'))
                        )
            if vip_parts and vip_parts != parts:
                play_from.append('欧乐VIP')
                play_urls.append('#'.join(vip_parts))

            groups = info.get('play_list') or info.get('vod_play_list') or []
            if groups and not play_urls:
                for g in groups:
                    flag = g.get('from') or g.get('name') or '线路'
                    eps = g.get('urls') or g.get('list') or []
                    p2 = self._ep_parts(eps)
                    if p2:
                        play_from.append(flag)
                        play_urls.append('#'.join(p2))

            if not play_urls:
                play_from = ['欧乐']
                play_urls = ['播放$%s/index.php/vod/play/id/%s.html' % (self.siteUrl, vid)]

            return {'list': [{
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': remarks,
                'vod_actor': actor,
                'vod_director': director,
                'vod_content': str(content).replace('\n\n', '\n').strip(),
                'vod_play_from': '$$$'.join(play_from),
                'vod_play_url': '$$$'.join(play_urls),
            }]}
        except Exception as e:
            print('获取详情失败: %s' % e)
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        header = {
            'User-Agent': self.userAgent,
            'Referer': self.siteUrl + '/',
            'Origin': self.siteUrl,
        }
        play_url = str(id or '')
        if self.isVideoFormat(play_url) and play_url.startswith('http'):
            return {'parse': 0, 'jx': '0', 'url': play_url, 'header': header}

        # 页面播放
        if play_url.startswith('http') and 'olevod' in play_url:
            html = self.fetch_text(play_url)
            m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\})', html or '')
            if m:
                raw = m.group(1)
                try:
                    js = json.loads(raw.replace("'", '"'))
                    u = (js.get('url') or '').replace('\\/', '/')
                    if u:
                        if self.isVideoFormat(u):
                            return {'parse': 0, 'jx': '0', 'url': u, 'header': header}
                        return {'parse': 1, 'jx': '1', 'url': u, 'header': header}
                except Exception:
                    um = re.search(r'"url"\s*:\s*"([^"]+)"', raw)
                    if um:
                        u = um.group(1).replace('\\/', '/')
                        return {
                            'parse': 0 if self.isVideoFormat(u) else 1,
                            'jx': '0' if self.isVideoFormat(u) else '1',
                            'url': u,
                            'header': header,
                        }
            m3 = re.search(r'https?://[^\s"\']+\.m3u8[^\s"\']*', html or '')
            if m3:
                return {'parse': 0, 'jx': '0', 'url': m3.group(0).replace('\\/', '/'), 'header': header}

        if play_url.isdigit():
            data = self.fetch_json('%s/v1/pub/vod/detail/%s/true' % (self.api, play_url))
            urls = ((data.get('data') or {}).get('urls')) or []
            for ep in urls:
                u = (ep or {}).get('url') or ''
                if u and not ep.get('vip'):
                    return {'parse': 0, 'jx': '0', 'url': u, 'header': header}
            if urls:
                u = (urls[0] or {}).get('url') or ''
                if u:
                    return {'parse': 0, 'jx': '0', 'url': u, 'header': header}

        return {
            'parse': 1,
            'jx': '1',
            'url': play_url if play_url.startswith('http') else (
                self.siteUrl + '/index.php/vod/play/id/' + play_url + '.html'
            ),
            'header': header,
        }

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        if any(x in u for x in ('.mp4', '.m3u8', '.flv', '.mpd')):
            return True
        if 'olemovienews.com' in u or 'olelive.com' in u:
            return True
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None


if __name__ == '__main__':
    spider = Spider()
    print(json.dumps(spider.homeContent(True), ensure_ascii=False, indent=2))
    r = spider.categoryContent('1', 1, {}, {})
    print('list', len(r['list']), r['list'][0] if r['list'] else None)
    if r['list']:
        d = spider.detailContent([r['list'][0]['vod_id']])
        print('detail', d['list'][0]['vod_name'], d['list'][0]['vod_play_url'][:100])
        token = d['list'][0]['vod_play_url'].split('#')[0].split('$')[-1]
        print(json.dumps(spider.playerContent('欧乐', token, []), ensure_ascii=False)[:200])
