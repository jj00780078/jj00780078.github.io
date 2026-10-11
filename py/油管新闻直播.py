# -*- coding: utf-8 -*-
# 油管新闻直播 Py 源（TVBox / 影视类 App Spider 格式）
# 只用标准库 + App 自带的 self.fetch，无需额外安装模块
# 需要手机能访问 YouTube（App 走代理）
import re, sys, json
from urllib.parse import quote
from base.spider import Spider

sys.path.append('..')


class Spider(Spider):
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    headers = {
        'User-Agent': UA,
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cookie': 'CONSENT=YES+1; SOCS=CAI',
    }

    # 分类 = 频道。想加频道就照格式往下加：('显示名', '@频道handle')
    CHANNELS = [
        ('TVBS新闻', '@TVBSNEWS01'),
        ('东森新闻', '@newsebc'),
        ('中天新闻', '@中天新聞CtiNews'),
        ('民视新闻', '@FTV_News'),
        ('华视新闻', '@CtsTw'),
        ('台视新闻', '@TTV_NEWS'),
        ('寰宇新闻', '@globalnewstw'),
        ('CGTN', '@CGTN'),
        ('NHK World', '@NHKWORLDJAPAN'),
        ('半岛英语', '@aljazeeraenglish'),
        ('Sky News', '@SkyNews'),
        ('DW News', '@dwnews'),
        ('ABC News', '@ABCNews'),
        ('CNA亚洲新闻台', '@channelnewsasia'),
    ]

    def init(self, extend=''):
        pass

    def getName(self):
        return '油管新闻直播'

    # ---------------- 工具函数 ----------------
    def _get(self, url):
        return self.fetch(url, headers=self.headers, timeout=15).text

    def _initial_data(self, html):
        m = re.search(r'var ytInitialData\s*=\s*(\{.*?\});\s*</script>', html, re.S)
        return json.loads(m.group(1)) if m else {}

    def _walk(self, obj, key, out):
        if isinstance(obj, dict):
            if key in obj:
                out.append(obj[key])
            for v in obj.values():
                self._walk(v, key, out)
        elif isinstance(obj, list):
            for v in obj:
                self._walk(v, key, out)
        return out

    def _is_live(self, node):
        s = json.dumps(node, ensure_ascii=False)
        return ('BADGE_STYLE_LIVE' in s or 'BADGE_STYLE_TYPE_LIVE_NOW' in s
                or '"style": "LIVE"' in s or '"style":"LIVE"' in s)

    def _parse_items(self, data, only_live=True):
        vods, seen = [], set()
        # 新版页面结构
        for lv in self._walk(data, 'lockupViewModel', []):
            vid = lv.get('contentId', '')
            if not vid or vid in seen or len(vid) != 11:
                continue
            if only_live and not self._is_live(lv.get('contentImage', {})):
                continue
            try:
                title = lv['metadata']['lockupMetadataViewModel']['title']['content']
            except Exception:
                title = vid
            seen.add(vid)
            vods.append(self._vod(vid, title, '直播中'))
        # 旧版 / 搜索页结构
        for vr in self._walk(data, 'videoRenderer', []):
            vid = vr.get('videoId', '')
            if not vid or vid in seen:
                continue
            if only_live and not self._is_live(vr):
                continue
            t = vr.get('title', {})
            title = ''.join(r.get('text', '') for r in t.get('runs', [])) or t.get('simpleText', vid)
            seen.add(vid)
            vods.append(self._vod(vid, title, '直播中'))
        return vods

    def _vod(self, vid, title, remark=''):
        return {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg',
            'vod_remarks': remark,
        }

    # ---------------- 接口 ----------------
    def homeContent(self, filter):
        classes = [{'type_id': h, 'type_name': n} for n, h in self.CHANNELS]
        return {'class': classes}

    def homeVideoContent(self):
        return {'list': self._search('新闻 直播')[:30]}

    def categoryContent(self, tid, pg, filter, extend):
        if str(pg) != '1':
            return {'list': [], 'page': pg, 'pagecount': 1}
        try:
            data = self._initial_data(self._get(f'https://www.youtube.com/{quote(tid)}/streams'))
            vods = self._parse_items(data, only_live=True)
        except Exception:
            vods = []
        return {'list': vods, 'page': 1, 'pagecount': 1, 'limit': len(vods), 'total': len(vods)}

    def _search(self, key):
        # sp=EgJAAQ%3D%3D 只搜正在直播的视频
        try:
            html = self._get(f'https://www.youtube.com/results?search_query={quote(key)}&sp=EgJAAQ%253D%253D')
            return self._parse_items(self._initial_data(html), only_live=False)
        except Exception:
            return []

    def searchContent(self, key, quick, pg='1'):
        if str(pg) != '1':
            return {'list': [], 'page': pg}
        return {'list': self._search(key), 'page': 1}

    def detailContent(self, ids):
        vid = ids[0]
        title, desc, author = vid, '', ''
        try:
            html = self._get(f'https://www.youtube.com/watch?v={vid}')
            m = re.search(r'"videoDetails":\{"videoId":"[^"]+","title":"((?:[^"\\]|\\.)*)"', html)
            if m:
                title = json.loads('"%s"' % m.group(1))
            m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
            if m:
                desc = json.loads('"%s"' % m.group(1))[:300]
            m = re.search(r'"ownerChannelName":"((?:[^"\\]|\\.)*)"', html)
            if m:
                author = json.loads('"%s"' % m.group(1))
        except Exception:
            pass
        url, why = self._get_hls(vid)
        desc = ('【播放地址：获取成功】' if url else f'【播放地址获取失败：{why}】') + '\n' + desc
        vod = self._vod(vid, title, '直播')
        vod.update({
            'vod_director': author,
            'vod_content': desc,
            'vod_play_from': 'YouTube直播',
            'vod_play_url': f'{title}${vid}',
        })
        return {'list': [vod]}

    # 依次尝试的客户端：VR / iOS / 电视 / 安卓（谁能给出直播 m3u8 就用谁）
    CLIENTS = [
        ('ANDROID_VR', '28', '1.60.19',
         'com.google.android.apps.youtube.vr.oculus/1.60.19 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip',
         {'deviceMake': 'Oculus', 'deviceModel': 'Quest 3', 'androidSdkVersion': 32,
          'osName': 'Android', 'osVersion': '12L'}),
        ('IOS', '5', '20.10.4',
         'com.google.ios.youtube/20.10.4 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)',
         {'deviceMake': 'Apple', 'deviceModel': 'iPhone16,2', 'osName': 'iPhone',
          'osVersion': '18.3.2.22D82'}),
        ('TVHTML5', '7', '7.20250312.16.00',
         'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version', {}),
        ('ANDROID', '3', '20.10.38',
         'com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip',
         {'androidSdkVersion': 34, 'osName': 'Android', 'osVersion': '14'}),
    ]

    def _post_json(self, url, body, headers):
        data = json.dumps(body)
        try:
            return self.post(url, data=data, headers=headers, timeout=8).json()
        except Exception:
            # App 的 post 不可用时，退回标准库
            import urllib.request
            req = urllib.request.Request(url, data=data.encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode('utf-8'))

    def _get_hls(self, vid):
        """返回 (m3u8地址, 失败原因)"""
        reasons = []
        for name, cid, ver, ua, extra in self.CLIENTS:
            client = {'clientName': name, 'clientVersion': ver, 'hl': 'zh-CN', 'gl': 'US'}
            client.update(extra)
            hd = {'User-Agent': ua, 'Content-Type': 'application/json',
                  'X-YouTube-Client-Name': cid, 'X-YouTube-Client-Version': ver,
                  'Origin': 'https://www.youtube.com'}
            try:
                j = self._post_json('https://www.youtube.com/youtubei/v1/player?prettyPrint=false',
                                    {'videoId': vid, 'context': {'client': client}}, hd)
                url = j.get('streamingData', {}).get('hlsManifestUrl', '')
                if url:
                    return url, ''
                ps = j.get('playabilityStatus', {})
                reasons.append(f"{name}:{ps.get('status', '')} {ps.get('reason', '')}".strip())
            except Exception as e:
                reasons.append(f'{name}:{type(e).__name__} {str(e)[:60]}')
        # 最后再试网页
        try:
            html = self._get(f'https://www.youtube.com/watch?v={vid}')
            m = re.search(r'"hlsManifestUrl":"(.*?)"', html)
            if m:
                return m.group(1).replace('\\u0026', '&').replace('\\/', '/'), ''
            reasons.append('WEB:网页无m3u8')
        except Exception as e:
            reasons.append(f'WEB:{type(e).__name__}')
        return '', ' | '.join(reasons)

    def playerContent(self, flag, id, vipFlags):
        vid = id
        url, _ = self._get_hls(vid)
        if url:
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': url,
                    'header': {'User-Agent': self.UA}}
        # 拿不到 m3u8 时，让 App 用内置网页嗅探
        return {'parse': 1, 'jx': 0, 'playUrl': '', 'url': f'https://m.youtube.com/watch?v={vid}',
                'header': {'User-Agent': self.UA}}

    def liveContent(self, url):
        return ''

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def localProxy(self, param):
        pass

    def destroy(self):
        pass
