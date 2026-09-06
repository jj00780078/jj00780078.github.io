#coding=utf-8
#!/usr/bin/python
"""
基于原 apiv19ytb.py，只做了 3 处最小改动来修复 1 分钟断流：
1. _decrypt_nsig：移动端客户端 n 参数原样保留，不强行 JS 变换
2. _call_player_api：删掉 IOS/ANDROID/MWEB，只用 4 个安全客户端
3. _client_preset：钉死 ANDROID_VR 版本 1.65.10

其余所有逻辑与原文件完全一致，不做任何额外过滤或改动。
"""

import re
import os
import sys
import json
import html
import time
import threading
from urllib.parse import quote, unquote, parse_qs, urlencode, urlparse, urlunparse, urljoin

import requests
from base.spider import Spider

sys.path.append('..')

# ---------- 日志路径 ----------
DEBUG_LOG = '/storage/emulated/0/Download/logs/ytb_debug.txt'
def _ensure_log_dir():
    try:
        log_dir = os.path.dirname(DEBUG_LOG)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
    except:
        pass
_ensure_log_dir()

def debug_log(message, data=None):
    try:
        log_dir = os.path.dirname(DEBUG_LOG)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        if data is not None:
            if isinstance(data, (dict, list)):
                line += ' ' + json.dumps(data, ensure_ascii=False, default=str)
            else:
                line += ' ' + str(data)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

# ==================== 分类配置 ====================
YOUTUBE_CLASSES = [
    {"type_name": "推荐", "type_id": "YouTube 直播 24小時"},
    {"type_id": "YouTube 新聞 Live", "type_name": "新闻直播"},
    {"type_id": "劇集", "type_name": "剧集"},
    {"type_id": "電影", "type_name": "电影"},
    {"type_id": "动画片", "type_name": "动画片"},
    {"type_id": "綜藝", "type_name": "综艺"},
    {"type_id": "短劇", "type_name": "短剧"},
    {"type_id": "紀錄片", "type_name": "纪录片"},
    {"type_id": "體育", "type_name": "体育"},
    {"type_id": "音樂", "type_name": "音乐"},
    {"type_id": "放松", "type_name": "放松"},
    {"type_id": "時尚潮流", "type_name": "时尚潮流"},
    {"type_id": "宇宙", "type_name": "科普"},
    {"type_id": "科技", "type_name": "科技"},
    {"type_id": "解說", "type_name": "解说"},
    {"type_id": "神秘", "type_name": "神秘"},
    {"type_id": "4K", "type_name": "4K"},
    {"type_id": "16K HDR", "type_name": "16K HDR"},
    {"type_id": "LIST:自媒體 We Media,零度解说 @lingdujieshuo,老高與小茉 @laogao,李子柒 Liziqi @cnliziqi,康1+1 @user-mr5bh4bk8z,不良林,涌哥侃侃 @ygkkk,悟空的日常,Learn English with EnglishClass101.com,Speak English With Vanessa,Tangerine Academy,听笙阁 @tingshengge,李永樂老師 @TchLiyongle,滇西小哥 @dianxixiaoge,脑洞乌托邦 @NDWTB,自说自话的总裁 @STBoss,老肉雜談 @老肉雜談,老饭骨 @LaoFanGu,小高姐的 Magic Ingredients @MagicIngredients,小穎美食 @XiaoYingFood,primitivetechnology9550 @primitivetechnology9550,Mr Beast@MrBeast,Airforceproud95 @Airforceproud95,TheGreatWar @TheGreatWar,Mark Rober @MarkRober", "type_name": "自媒体"}
]

CATEGORY_FILTERS = {}

# ==================== 核心提取类 ====================
class YouTubeLite:
    """普通视频提取"""
    def __init__(self, session, headers=None, config=None):
        self.session = session
        self.headers = headers or {}
        self.config = config or {}
        self.player_cache = {}
        self.extract_cache = {}
        self.sig_plan_cache = {}
        self._last_api_ctx = {}
        self.extract_cache_ttl = int(self.config.get('extract_cache_ttl') or 300)

    def extract(self, url_or_id, force=False):
        video_id = self.extract_video_id(url_or_id)
        cached = self.extract_cache.get(video_id)
        now = time.time()
        if not force and cached and cached.get('expires', 0) > now:
            return cached.get('data')
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        page_resp = self._get(watch_url)
        page = page_resp.text
        ytcfg = self._extract_ytcfg(page) or {}
        player_response = self._extract_initial_player_response(page) or {}
        player_url = self._extract_player_url(page)
        api_key = ytcfg.get('INNERTUBE_API_KEY') or self._search(r'"INNERTUBE_API_KEY":"([^"]+)"', page)
        visitor_data = self._extract_visitor_data(ytcfg, player_response)
        context = ytcfg.get('INNERTUBE_CONTEXT') or {
            'client': {'clientName': 'WEB', 'clientVersion': '2.20240310.01.00', 'hl': 'en', 'gl': 'US'}
        }
        self._last_api_ctx[video_id] = {
            'api_key': api_key,
            'context': context,
            'visitor_data': visitor_data,
            'referer': watch_url,
            'player_url': player_url,
        }
        responses = []
        if player_response:
            if not player_response.get('_client_name'):
                player_response = dict(player_response)
                player_response['_client_name'] = 'WEB'
                player_response['_client_ua'] = (self.headers or {}).get('User-Agent')
            responses.append(player_response)
        if api_key:
            api_responses = self._call_player_api(video_id, api_key, context, watch_url, visitor_data)
            if not isinstance(api_responses, list):
                api_responses = [api_responses] if api_responses else []
            responses.extend([x for x in api_responses if x])
        if not responses:
            raise Exception('未获取到任何播放器响应')
        data = self._build_data(video_id, responses, player_url)
        self.extract_cache[video_id] = {'data': data, 'expires': time.time() + self.extract_cache_ttl}
        return data

    def refresh(self, video_id, prefer_client=None):
        ctx = self._last_api_ctx.get(video_id) or {}
        api_key = ctx.get('api_key')
        if not api_key:
            return self.extract(video_id, force=True)
        try:
            if prefer_client:
                responses = self._call_player_api_single(
                    video_id, api_key, prefer_client,
                    ctx.get('referer') or f'https://www.youtube.com/watch?v={video_id}',
                    ctx.get('visitor_data'),
                    base_context=ctx.get('context'),
                ) or []
            else:
                responses = self._call_player_api(
                    video_id, api_key, ctx.get('context'),
                    ctx.get('referer') or f'https://www.youtube.com/watch?v={video_id}',
                    ctx.get('visitor_data'),
                ) or []
            responses = [x for x in responses if x]
            if not responses:
                return self.extract(video_id, force=True)
            return self._build_data(video_id, responses, ctx.get('player_url') or '')
        except Exception as e:
            debug_log('refresh failed, fallback full extract', {'video_id': video_id, 'error': repr(e)})
            return self.extract(video_id, force=True)

    def _build_data(self, video_id, responses, player_url):
        player_response = next((x for x in responses if (x.get('playabilityStatus') or {}).get('status') == 'OK'), responses[0] if responses else {})
        status = (player_response.get('playabilityStatus') or {}).get('status')
        streaming = player_response.get('streamingData') or {}
        if status and status not in ('OK', 'LIVE_STREAM_OFFLINE') and not streaming:
            reason = (player_response.get('playabilityStatus') or {}).get('reason') or status
            raise Exception(f'YouTube 不可播放: {reason}')
        details = player_response.get('videoDetails') or {}
        formats, source_counts, cipher_count = self._collect_formats(responses, player_url)
        if not formats:
            raise Exception('未获取到可用播放地址')
        hls_url = ''
        for r in (responses or []):
            sd = (r or {}).get('streamingData') or {}
            if sd.get('hlsManifestUrl'):
                hls_url = sd['hlsManifestUrl']
                break
        return {
            'id': video_id,
            'title': details.get('title') or video_id,
            'duration': int(details.get('lengthSeconds') or 0),
            'formats': formats,
            'hls_url': hls_url,
        }

    def _collect_formats(self, responses, player_url):
        raw_formats = []
        seen_raw = set()
        source_counts = []
        _client_rank = {'ANDROID_VR': 0, 'WEB_EMBEDDED_PLAYER': 1, 'TVHTML5_SIMPLY_EMBEDDED_PLAYER': 2, 'WEB': 3, 'ANDROID': 8, 'IOS': 9, 'MWEB': 10}
        sorted_responses = sorted(
            responses,
            key=lambda r: _client_rank.get((r or {}).get('_client_name') or '', 9)
        )
        for response in sorted_responses:
            response = response or {}
            response_streaming = response.get('streamingData') or {}
            source_raw = (response_streaming.get('formats') or []) + (response_streaming.get('adaptiveFormats') or [])
            source_counts.append({'formats': len(response_streaming.get('formats') or []), 'adaptive': len(response_streaming.get('adaptiveFormats') or [])})
            for raw in source_raw:
                key = (raw.get('itag'), raw.get('url') or raw.get('signatureCipher') or raw.get('cipher') or raw.get('mimeType'))
                if key not in seen_raw:
                    seen_raw.add(key)
                    raw = raw.copy()
                    raw['_client_name'] = response.get('_client_name')
                    raw['_client_ua'] = response.get('_client_ua')
                    raw_formats.append(raw)
        formats = []
        cipher_count = 0
        for raw in raw_formats:
            if raw.get('signatureCipher') or raw.get('cipher'):
                cipher_count += 1
            item = self._normalize_format(raw, player_url)
            if item and item.get('url'):
                formats.append(item)
        return formats, source_counts, cipher_count

    @staticmethod
    def extract_video_id(text):
        text = str(text or '').strip()
        for pattern in [
            r'(?:v=|/v/|/embed/|/shorts/|youtu\.be/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        raise Exception('无法识别 YouTube 视频 ID')

    def _client_name_id(self, client_name):
        return {
            'WEB': 1, 'MWEB': 2, 'ANDROID': 3, 'IOS': 5,
            'TVHTML5': 7, 'ANDROID_VR': 28,
            'WEB_EMBEDDED_PLAYER': 56, 'WEB_REMIX': 67,
        }.get(client_name, 1)

    # ========== ★ 修复 1：_client_preset 钉死 ANDROID_VR 版本 ==========
    def _client_preset(self, client_name, base_context=None):
        presets = {
            'ANDROID_VR': {'client': {'clientName': 'ANDROID_VR', 'clientVersion': '1.65.10', 'deviceMake': 'Oculus', 'deviceModel': 'Quest 3', 'androidSdkVersion': 32, 'userAgent': 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip', 'osName': 'Android', 'osVersion': '12L', 'hl': 'en', 'gl': 'US'}},
            'WEB_EMBEDDED': {'client': {'clientName': 'WEB_EMBEDDED_PLAYER', 'clientVersion': '1.20240310.01.00', 'clientScreen': 'EMBED', 'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36', 'hl': 'en', 'gl': 'US'}},
            'TVHTML5': {'client': {'clientName': 'TVHTML5_SIMPLY_EMBEDDED_PLAYER', 'clientVersion': '2.0', 'userAgent': 'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version', 'hl': 'en', 'gl': 'US'}},
            'WEB_SAFARI': {'client': {'clientName': 'WEB', 'clientVersion': '2.20240101.00.00', 'userAgent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15', 'hl': 'en', 'gl': 'US'}},
            'ANDROID': {'client': {'clientName': 'ANDROID', 'clientVersion': '21.02.35', 'androidSdkVersion': 30, 'userAgent': 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip', 'osName': 'Android', 'osVersion': '11', 'hl': 'en', 'gl': 'US'}},
            'IOS': {'client': {'clientName': 'IOS', 'clientVersion': '21.02.3', 'deviceMake': 'Apple', 'deviceModel': 'iPhone16,2', 'userAgent': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)', 'osName': 'iPhone', 'osVersion': '18.3.2.22D82', 'hl': 'en', 'gl': 'US'}},
            'MWEB': {'client': {'clientName': 'MWEB', 'clientVersion': '2.20260115.01.00', 'userAgent': 'Mozilla/5.0 (iPad; CPU OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1,gzip(gfe)', 'hl': 'en', 'gl': 'US'}},
        }
        if client_name == 'WEB' and base_context:
            return base_context
        key = client_name
        if client_name in ('WEB_EMBEDDED_PLAYER',):
            key = 'WEB_EMBEDDED'
        elif client_name in ('TVHTML5_SIMPLY_EMBEDDED_PLAYER',):
            key = 'TVHTML5'
        elif client_name == 'WEB':
            key = 'WEB_SAFARI' if 'WEB_SAFARI' in presets else client_name
        return presets.get(key) or presets.get(client_name) or base_context or presets['ANDROID_VR']

    def _extract_visitor_data(self, ytcfg, player_response):
        return (
            self.config.get('visitor_data')
            or ytcfg.get('VISITOR_DATA')
            or (((ytcfg.get('INNERTUBE_CONTEXT') or {}).get('client') or {}).get('visitorData'))
            or ((player_response.get('responseContext') or {}).get('visitorData'))
        )

    def _get_po_token(self, client_name, context='gvs'):
        tokens = self.config.get('po_token') or self.config.get('po_tokens') or {}
        if isinstance(tokens, str):
            return tokens
        if isinstance(tokens, dict):
            return tokens.get(f'{client_name}.{context}') or tokens.get(client_name) or tokens.get(context)
        return None

    def _video_codec_priority(self, item):
        mime = (item.get('mimeType') or '').lower()
        codecs = (item.get('codecs') or '').lower()
        if 'vp9.2' in mime or 'vp09.02' in codecs:
            return 4
        if 'vp9' in mime or 'vp09' in codecs:
            return 3
        if 'avc' in codecs or 'h264' in codecs:
            return 2
        if 'av01' in codecs:
            return 1
        return 0

    def _is_hdr_video(self, item):
        mime = (item.get('mimeType') or '').lower()
        codecs = (item.get('codecs') or '').lower()
        color = item.get('colorInfo') or {}
        return 'vp9.2' in mime or 'vp09.02' in codecs or bool(color.get('hdrMetadataInfo'))

    def _is_risky_best_video(self, item):
        codecs = (item.get('codecs') or '').lower()
        return 'av01' in codecs

    def choose_playable(self, formats, quality=None):
        all_videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        candidates = all_videos[:]
        if quality == '4k':
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 2160]
        elif quality == '2k':
            candidates = [x for x in candidates if 1440 <= int(x.get('height') or 0) < 2160]
        elif quality == '1080p':
            candidates = [x for x in candidates if 1000 <= int(x.get('height') or 0) < 1440]
        elif quality == 'best':
            safe_candidates = [x for x in candidates if not self._is_risky_best_video(x)]
            if safe_candidates:
                candidates = safe_candidates
        else:
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 1080]
        if not candidates and quality == 'best':
            candidates = all_videos
        if not candidates:
            return None
        candidates.sort(key=lambda x: (
            self._video_codec_priority(x),
            int(x.get('height') or 0),
            int(x.get('bitrate') or 0)
        ), reverse=True)
        return candidates[0]

    def choose_audio(self, formats):
        candidates = [x for x in formats if x.get('acodec') != 'none' and x.get('vcodec') == 'none']
        if not candidates:
            return None
        candidates.sort(key=lambda x: (1 if x.get('ext') == 'mp4' else 0, int(x.get('bitrate') or 0)), reverse=True)
        return candidates[0]

    # ========== ★ 修复 2：_call_player_api 只请求 4 个安全客户端 ==========
    def _call_player_api(self, video_id, api_key, context, referer, visitor_data=None, sts=None):
        clients = [
            {'client': {'clientName': 'ANDROID_VR', 'clientVersion': '1.65.10', 'deviceMake': 'Oculus', 'deviceModel': 'Quest 3', 'androidSdkVersion': 32, 'userAgent': 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip', 'osName': 'Android', 'osVersion': '12L', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'WEB_EMBEDDED_PLAYER', 'clientVersion': '1.20240310.01.00', 'clientScreen': 'EMBED', 'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'TVHTML5_SIMPLY_EMBEDDED_PLAYER', 'clientVersion': '2.0', 'userAgent': 'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'WEB', 'clientVersion': '2.20240101.00.00', 'userAgent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15', 'hl': 'en', 'gl': 'US'}},
        ]
        results = []
        fallback = None
        for ctx in clients:
            client_name = (ctx.get('client') or {}).get('clientName')
            try:
                url = f'https://www.youtube.com/youtubei/v1/player?key={api_key}&prettyPrint=false'
                payload = {
                    'context': ctx,
                    'videoId': video_id,
                    'playbackContext': {'contentPlaybackContext': {'html5Preference': 'HTML5_PREF_WANTS', **({'signatureTimestamp': sts} if sts else {})}},
                    'contentCheckOk': True,
                    'racyCheckOk': True,
                }
                client = ctx.get('client') or {}
                headers = {
                    'Referer': referer,
                    'X-YouTube-Client-Name': str(self._client_name_id(client.get('clientName'))),
                    'X-YouTube-Client-Version': client.get('clientVersion') or '',
                }
                if visitor_data:
                    headers['X-Goog-Visitor-Id'] = visitor_data
                client_ua = client.get('userAgent')
                if client_ua:
                    headers['User-Agent'] = client_ua
                data = self._post_json(url, payload, headers=headers)
                streaming = data.get('streamingData') or {}
                if streaming:
                    data['_client_name'] = client_name
                    data['_client_ua'] = client_ua
                    results.append(data)
                if fallback is None:
                    fallback = data
            except Exception as e:
                debug_log('player api client error', {'client': client_name, 'error': repr(e)})
                continue
        return results or ([fallback] if fallback else [])

    def _call_player_api_single(self, video_id, api_key, client_name, referer, visitor_data=None, sts=None, base_context=None):
        ctx = self._client_preset(client_name, base_context)
        client = ctx.get('client') or {}
        client_name = client.get('clientName') or client_name
        try:
            url = f'https://www.youtube.com/youtubei/v1/player?key={api_key}&prettyPrint=false'
            payload = {
                'context': ctx,
                'videoId': video_id,
                'playbackContext': {'contentPlaybackContext': {'html5Preference': 'HTML5_PREF_WANTS', **({'signatureTimestamp': sts} if sts else {})}},
                'contentCheckOk': True,
                'racyCheckOk': True,
            }
            headers = {
                'Referer': referer,
                'X-YouTube-Client-Name': str(self._client_name_id(client_name)),
                'X-YouTube-Client-Version': client.get('clientVersion') or '',
            }
            if visitor_data:
                headers['X-Goog-Visitor-Id'] = visitor_data
            client_ua = client.get('userAgent')
            if client_ua:
                headers['User-Agent'] = client_ua
            data = self._post_json(url, payload, headers=headers)
            streaming = data.get('streamingData') or {}
            if streaming:
                data['_client_name'] = client_name
                data['_client_ua'] = client_ua
                return [data]
        except Exception as e:
            debug_log('player api single error', {'client': client_name, 'error': repr(e)})
        return []

    def _normalize_format(self, fmt, player_url):
        media_url = fmt.get('url')
        if not media_url:
            cipher = fmt.get('signatureCipher') or fmt.get('cipher')
            if cipher:
                media_url = self._decrypt_signature_cipher(cipher, player_url)
        if not media_url:
            return None
        client_name = fmt.get('_client_name')
        media_url = self._decrypt_nsig(media_url, player_url, client_name)
        po_token = self._get_po_token(client_name, 'gvs') if client_name else None
        if po_token:
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}pot={quote(po_token)}'
        mime = fmt.get('mimeType') or ''
        ext = 'mp4' if 'mp4' in mime else 'webm' if 'webm' in mime else 'unknown'
        codecs = self._search(r'codecs="([^"]+)"', mime) or ''
        has_audio = mime.startswith('audio/') or any(x in codecs for x in ('mp4a', 'opus', 'vorbis'))
        has_video = mime.startswith('video/') or any(x in codecs for x in ('avc', 'vp9', 'av01', 'h264'))
        headers = (fmt.get('http_headers') or {}).copy()
        if fmt.get('_client_ua'):
            headers['User-Agent'] = fmt.get('_client_ua')
        return {
            'itag': fmt.get('itag'), 'url': media_url, 'mimeType': mime,
            'client': fmt.get('_client_name'), 'ext': ext,
            'width': fmt.get('width') or 0, 'height': fmt.get('height') or 0,
            'fps': fmt.get('fps') or 0, 'bitrate': fmt.get('bitrate') or fmt.get('averageBitrate') or 0,
            'contentLength': fmt.get('contentLength'),
            'initRange': fmt.get('initRange') or {}, 'indexRange': fmt.get('indexRange') or {},
            'codecs': codecs, 'quality': fmt.get('qualityLabel') or fmt.get('quality'),
            'colorInfo': fmt.get('colorInfo') or {},
            'vcodec': codecs if has_video else 'none',
            'acodec': codecs if has_audio else 'none',
            'headers': headers,
        }

    def _build_format_headers(self, fmt, client_name=None, client_ua=None):
        headers = (fmt.get('http_headers') or {}).copy()
        ua = (fmt.get('headers') or {}).get('User-Agent') or fmt.get('_client_ua') or client_ua
        if ua:
            headers['User-Agent'] = ua
        return headers

    def _decrypt_signature_cipher(self, cipher, player_url):
        data = parse_qs(cipher)
        media_url = unquote(data.get('url', [''])[0])
        sig = unquote(data.get('s', [''])[0])
        sp = data.get('sp', ['sig'])[0]
        if not media_url:
            return ''
        if sig:
            decoded = self._decrypt_sig(sig, player_url)
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}{sp}={quote(decoded)}'
        return media_url

    def _decrypt_sig(self, sig, player_url):
        cache_key = player_url or ''
        if cache_key in self.sig_plan_cache:
            plan = self.sig_plan_cache.get(cache_key)
        else:
            code = self._get_player_code(player_url)
            plan = self._extract_sig_plan(code)
            self.sig_plan_cache[cache_key] = plan
        if not plan:
            return sig
        arr = list(sig)
        for op, arg in plan:
            if op == 'reverse':
                arr.reverse()
            elif op in ('slice', 'splice'):
                arr = arr[int(arg):]
            elif op == 'swap' and arr:
                j = int(arg) % len(arr)
                arr[0], arr[j] = arr[j], arr[0]
        return ''.join(arr)

    # ========== ★ 修复 3：_decrypt_nsig 移动端客户端 n 参数原样保留 ==========
    def _decrypt_nsig(self, media_url, player_url, client_name=None):
        try:
            parsed = urlparse(media_url)
            query = parse_qs(parsed.query)
            n_value = query.get('n', [None])[0]
            if not n_value:
                return media_url

            # ★★★ 移动端客户端 n 是明文，强行 JS 变换会让 URL 在 30-40 秒后失效 ★★★
            if client_name and client_name in (
                'ANDROID_VR', 'ANDROID', 'IOS',
                'WEB_EMBEDDED_PLAYER', 'WEB_EMBEDDED',
                'TVHTML5_SIMPLY_EMBEDDED_PLAYER', 'TVHTML5',
            ):
                return media_url

            n_func = None
            cache_key = f'nfunc_{player_url}'
            if player_url and cache_key in self.player_cache:
                cached = self.player_cache.get(cache_key)
                if callable(cached):
                    n_func = cached
            elif player_url:
                code = self._get_player_code(player_url)
                if code:
                    n_func = self._extract_n_function(code)
                    self.player_cache[cache_key] = n_func

            if n_func:
                try:
                    new_n = n_func(n_value)
                    if new_n and new_n != n_value:
                        new_query = {}
                        for k, v_list in query.items():
                            new_query[k] = [new_n] if k == 'n' else v_list
                        new_query_str = urlencode(new_query, doseq=True)
                        new_parsed = parsed._replace(query=new_query_str)
                        new_path = new_parsed.path
                        path_match = re.search(r'/n/([^/]+)', parsed.path)
                        if path_match:
                            new_path = parsed.path.replace(f"/n/{path_match.group(1)}", f"/n/{new_n}", 1)
                        fixed = urlunparse(new_parsed._replace(path=new_path))
                        return fixed
                except Exception as e:
                    debug_log('n transform error', {'error': repr(e), 'client': client_name})

            return media_url
        except Exception as e:
            debug_log('n decrypt error', repr(e))
            return media_url

    def _get_player_code(self, player_url):
        if not player_url:
            return ''
        if player_url in self.player_cache:
            return self.player_cache[player_url]
        if player_url.startswith('//'):
            player_url = 'https:' + player_url
        elif player_url.startswith('/'):
            player_url = 'https://www.youtube.com' + player_url
        try:
            code = self._get(player_url).text
        except Exception:
            code = ''
        self.player_cache[player_url] = code
        return code

    def _extract_sig_plan(self, code):
        if not code:
            return None
        name = None
        for pattern in [
            r'\.sig\|\|([a-zA-Z0-9_$]+)\(',
            r'"signature",\s*([a-zA-Z0-9_$]+)\(',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\);',
        ]:
            m = re.search(pattern, code)
            if m:
                name = m.group(1)
                break
        if not name:
            return None
        body = self._extract_js_function_body(code, name)
        if not body:
            return None
        helper = self._search(r'([a-zA-Z0-9_$]+)\.[a-zA-Z0-9_$]+\(a,\d+\)', body)
        helper_map = self._extract_helper_object(code, helper) if helper else {}
        plan = []
        for part in body.split(';'):
            if 'reverse()' in part:
                plan.append(('reverse', 0))
                continue
            m = re.search(r'\.slice\((\d+)\)', part)
            if m:
                plan.append(('slice', int(m.group(1))))
                continue
            m = re.search(r'\.splice\(0,(\d+)\)', part)
            if m:
                plan.append(('splice', int(m.group(1))))
                continue
            m = re.search(r'([a-zA-Z0-9_$]+)\.([a-zA-Z0-9_$]+)\(a,(\d+)\)', part)
            if m and m.group(1) == helper:
                op = helper_map.get(m.group(2))
                if op:
                    plan.append((op, int(m.group(3))))
        return plan or None

    def _extract_helper_object(self, code, name):
        if not name:
            return {}
        m = re.search(r'var\s+' + re.escape(name) + r'=\{(.+?)\};', code, re.S) or re.search(re.escape(name) + r'=\{(.+?)\};', code, re.S)
        if not m:
            return {}
        result = {}
        for method, body in re.findall(r'([a-zA-Z0-9_$]+):function\([a-z,]+\)\{(.*?)\}', m.group(1)):
            if '.reverse(' in body:
                result[method] = 'reverse'
            elif '.splice(' in body:
                result[method] = 'splice'
            elif '.slice(' in body:
                result[method] = 'slice'
            elif 'a[0]' in body and 'length' in body:
                result[method] = 'swap'
        return result

    def _extract_n_function(self, code):
        if not code:
            return None
        name = None
        index = None
        for pattern in [
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)(?:\[(\d+)\])?\([a-zA-Z0-9]\)',
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)\(b\)',
            r'b=String\.fromCharCode\(110\),c=a\.get\(b\)\)&&\(c=([a-zA-Z0-9_$]+)(?:\[(\d+)\])?\([a-zA-Z0-9]\)',
            r'&&\(b="nn"\[\+[a-zA-Z0-9_$.]+\],c=a\.get\(b\)\)&&\(c=([a-zA-Z0-9_$]+)(?:\[(\d+)\])?\([a-zA-Z0-9]\)',
            r'=([a-zA-Z0-9_$]+)(?:\[(\d+)\])?\([a-zA-Z]\),[a-zA-Z0-9_$]+\.set\("n",',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{var b=a\.split\(""\)',
            r'function\s+([a-zA-Z0-9_$]+)\(a\)\{var b=a\.split\(""\)',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\)',
        ]:
            m = re.search(pattern, code, re.DOTALL)
            if m:
                name = m.group(1)
                if m.lastindex and m.lastindex >= 2 and m.group(2):
                    try:
                        index = int(m.group(2))
                    except (ValueError, TypeError):
                        index = None
                break
        if not name:
            return None
        if index is not None:
            array_pattern = r'var\s+' + re.escape(name) + r'\s*=\s*\[([^\]]+)\]'
            am = re.search(array_pattern, code)
            if am:
                items = am.group(1).split(',')
                if index < len(items):
                    real_name = items[index].strip().strip('"\'')
                    name = real_name
        body = self._extract_js_function_body(code, name)
        if not body:
            return None
        helper_name = self._search(r'([a-zA-Z0-9_$]+)\.[a-zA-Z0-9_$]+\(a,\d+\)', body)
        helper_map = {}
        if helper_name:
            helper_map = self._extract_helper_object(code, helper_name)
        if helper_map:
            plan = []
            for part in body.split(';'):
                part = part.strip()
                if not part or part.startswith('var ') or part.startswith('a=') or 'return' in part:
                    continue
                if 'reverse()' in part:
                    plan.append(('reverse', 0))
                    continue
                m = re.search(r'\.slice\((\d+)\)', part)
                if m:
                    plan.append(('slice', int(m.group(1))))
                    continue
                m = re.search(r'\.splice\(0,(\d+)\)', part)
                if m:
                    plan.append(('splice', int(m.group(1))))
                    continue
                m = re.search(r'([a-zA-Z0-9_$]+)\.([a-zA-Z0-9_$]+)\(a,(\d+)\)', part)
                if m and m.group(1) == helper_name:
                    op = helper_map.get(m.group(2))
                    if op:
                        plan.append((op, int(m.group(3))))
            if plan:
                def transform_plan(value):
                    arr = list(value)
                    for op, arg in plan:
                        if op == 'reverse':
                            arr.reverse()
                        elif op in ('slice', 'splice'):
                            arr = arr[arg:]
                        elif op == 'swap' and arr:
                            j = arg % len(arr)
                            arr[0], arr[j] = arr[j], arr[0]
                    return ''.join(arr) or value
                return transform_plan
        def transform(value):
            arr = list(value)
            for part in body.split(';'):
                part = part.strip()
                if not part:
                    continue
                if 'reverse()' in part:
                    arr.reverse()
                    continue
                m = re.search(r'\.slice\((\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
                    continue
                m = re.search(r'\.splice\(0,(\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
                    continue
                m = re.search(r'a\[([^\]]+)\]\s*=\s*a\[([^\]]+)\]', part)
                if m:
                    try:
                        idx1 = self._eval_js_index(m.group(1), len(arr))
                        idx2 = self._eval_js_index(m.group(2), len(arr))
                        if idx1 is not None and idx2 is not None:
                            arr[idx1], arr[idx2] = arr[idx2], arr[idx1]
                    except Exception:
                        pass
                    continue
            return ''.join(arr) or value
        return transform

    def _eval_js_index(self, expr, arr_len):
        expr = expr.strip()
        if expr.isdigit() or (expr.startswith('-') and expr[1:].isdigit()):
            return int(expr) % arr_len if arr_len > 0 else 0
        m = re.match(r'a\.length\s*-\s*(\d+)', expr)
        if m:
            return (arr_len - int(m.group(1))) % arr_len
        m = re.match(r'(\d+)\s*%\s*a\.length', expr)
        if m:
            return int(m.group(1)) % arr_len if arr_len > 0 else 0
        return None

    def _extract_js_function_body(self, code, name):
        starts = []
        for pattern in [
            r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{',
            re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
            r'var\s+' + re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
        ]:
            m = re.search(pattern, code)
            if m:
                starts.append(m.end() - 1)
        if not starts:
            return ''
        start = starts[0]
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(code)):
            ch = code[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch in ('"', "'", '`'):
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return code[start + 1:i]
        return ''

    def _extract_ytcfg(self, text):
        m = re.search(r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;', text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    def _extract_initial_player_response(self, text):
        return self._extract_json_after(text, 'ytInitialPlayerResponse')

    def _extract_json_after(self, text, marker):
        pos = text.find(marker)
        if pos < 0:
            return None
        start = text.find('{', pos)
        if start < 0:
            return None
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch == '"':
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None

    def _extract_player_url(self, text):
        for pattern in [
            r'"jsUrl":"([^"]+)"',
            r'"PLAYER_JS_URL":"([^"]+)"',
            r'(/s/player/[^"\\]+/base\.js)',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1).replace('\\/', '/')
        return ''

    @staticmethod
    def _search(pattern, text, default=None):
        m = re.search(pattern, text or '', re.S)
        return m.group(1) if m else default


# ==================== 直播提取类 ====================
class YouTubeLiveLite:
    def __init__(self, session, headers=None, config=None):
        self.session = session
        self.headers = headers or {}
        self.config = config or {}
        self.cache = {}
        self.cache_ttl = int(self.config.get('live_cache_ttl') or 45)

    def extract_video_id(self, text):
        text = str(text or '').strip()
        for pattern in [
            r'(?:v=|/v/|/embed/|/shorts/|youtu\.be/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$',
        ]:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        raise Exception('无法识别 YouTube 视频 ID')

    def extract_live(self, url_or_id):
        video_id = self.extract_video_id(url_or_id)
        now = time.time()
        cached = self.cache.get(video_id)
        if cached and cached.get('expires', 0) > now:
            return cached.get('data')
        watch_url = f'https://www.youtube.com/watch?v={video_id}'
        response = self._get(watch_url)
        page = response.text
        player_response = self._extract_initial_player_response(page) or {}
        ytcfg = self._extract_ytcfg(page) or {}
        api_key = ytcfg.get('INNERTUBE_API_KEY') or self._search(r'"INNERTUBE_API_KEY":"([^"]+)"', page)
        visitor_data = self._extract_visitor_data(ytcfg, player_response)
        status_obj = player_response.get('playabilityStatus') or {}
        streaming = player_response.get('streamingData') or {}
        details = player_response.get('videoDetails') or {}
        page_hls_url = streaming.get('hlsManifestUrl') or ''
        api_data = None
        if api_key:
            api_data = self._call_player_api(video_id, api_key, ytcfg, watch_url, visitor_data)
            if api_data:
                api_streaming = api_data.get('streamingData') or {}
                api_details = api_data.get('videoDetails') or {}
                api_hls_url = api_streaming.get('hlsManifestUrl') or ''
                if api_hls_url:
                    streaming = api_streaming
                elif not page_hls_url and api_streaming:
                    streaming = api_streaming
                if api_details:
                    details = api_details
                status_obj = api_data.get('playabilityStatus') or status_obj
        if not (streaming.get('hlsManifestUrl') or '') and page_hls_url:
            streaming = dict(streaming or {})
            streaming['hlsManifestUrl'] = page_hls_url
        hls_url = streaming.get('hlsManifestUrl') or ''
        is_live = bool(details.get('isLiveContent') or hls_url)
        status = status_obj.get('status') or ''
        reason = status_obj.get('reason') or ''
        title = details.get('title') or video_id
        data = {
            'id': video_id, 'title': title, 'is_live': is_live,
            'status': status, 'reason': reason, 'hls_url': hls_url,
            'duration': int(details.get('lengthSeconds') or 0),
        }
        self.cache[video_id] = {'data': data, 'expires': time.time() + self.cache_ttl}
        return data

    def _get(self, url, **kwargs):
        headers = self.headers.copy()
        headers.update(kwargs.pop('headers', {}) or {})
        response = self.session.get(url, headers=headers, timeout=kwargs.pop('timeout', 15), **kwargs)
        response.raise_for_status()
        return response

    def _post_json(self, url, payload, headers=None):
        final_headers = self.headers.copy()
        final_headers.update({'Content-Type': 'application/json', 'Origin': 'https://www.youtube.com'})
        if headers:
            final_headers.update({k: v for k, v in headers.items() if v})
        response = self.session.post(url, json=payload, headers=final_headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def _call_player_api(self, video_id, api_key, ytcfg, referer, visitor_data=None):
        context = ytcfg.get('INNERTUBE_CONTEXT') or {
            'client': {'clientName': 'WEB', 'clientVersion': '2.20240310.01.00', 'hl': 'en', 'gl': 'US'}
        }
        clients = [
            {'client': {'clientName': 'ANDROID', 'clientVersion': '21.02.35', 'androidSdkVersion': 30, 'userAgent': 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip', 'osName': 'Android', 'osVersion': '11', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'IOS', 'clientVersion': '21.02.3', 'deviceMake': 'Apple', 'deviceModel': 'iPhone16,2', 'userAgent': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)', 'osName': 'iPhone', 'osVersion': '18.3.2.22D82', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'MWEB', 'clientVersion': '2.20260115.01.00', 'userAgent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1', 'hl': 'en', 'gl': 'US'}},
            context,
        ]
        for ctx in clients:
            client = ctx.get('client') or {}
            client_name = client.get('clientName') or 'WEB'
            try:
                url = f'https://www.youtube.com/youtubei/v1/player?key={quote(api_key)}&prettyPrint=false'
                headers = {
                    'Referer': referer,
                    'X-YouTube-Client-Name': str(self._client_name_id(client_name)),
                    'X-YouTube-Client-Version': client.get('clientVersion') or '',
                }
                if visitor_data:
                    headers['X-Goog-Visitor-Id'] = visitor_data
                if client.get('userAgent'):
                    headers['User-Agent'] = client.get('userAgent')
                payload = {
                    'context': ctx,
                    'videoId': video_id,
                    'contentCheckOk': True,
                    'racyCheckOk': True,
                }
                data = self._post_json(url, payload, headers=headers)
                streaming = data.get('streamingData') or {}
                if streaming.get('hlsManifestUrl'):
                    data['_client_name'] = client_name
                    return data
            except Exception as e:
                debug_log('live api client error', {'client': client_name, 'error': repr(e)})
        return None

    def _extract_visitor_data(self, ytcfg, player_response):
        return (
            self.config.get('visitor_data')
            or ytcfg.get('VISITOR_DATA')
            or (((ytcfg.get('INNERTUBE_CONTEXT') or {}).get('client') or {}).get('visitorData'))
            or ((player_response.get('responseContext') or {}).get('visitorData'))
        )

    def _extract_ytcfg(self, text):
        m = re.search(r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;', text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    def _extract_initial_player_response(self, text):
        return self._extract_json_after(text, 'ytInitialPlayerResponse')

    def _extract_json_after(self, text, marker):
        pos = text.find(marker)
        if pos < 0:
            return None
        start = text.find('{', pos)
        if start < 0:
            return None
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch == '"':
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None

    @staticmethod
    def _search(pattern, text, default=None):
        m = re.search(pattern, text or '', re.S)
        return m.group(1) if m else default

    def _client_name_id(self, client_name):
        return {
            'WEB': 1, 'MWEB': 2, 'ANDROID': 3, 'IOS': 5,
            'TVHTML5': 7, 'ANDROID_VR': 28,
            'WEB_EMBEDDED_PLAYER': 56, 'WEB_REMIX': 67,
        }.get(client_name, 1)


# ==================== 主 Spider 类 ====================
class Spider(Spider):
    def getName(self):
        return 'YouTube 视频+直播（修复版）'

    def init(self, extend):
        try:
            self.extendDict = json.loads(extend) if extend else {}
        except Exception:
            self.extendDict = {}

        self.session = requests.Session()
        self.session.trust_env = True

        self.proxy_str = None
        proxy = self.extendDict.get('proxy')
        if proxy:
            if isinstance(proxy, str):
                if not proxy.startswith('http://') and not proxy.startswith('https://'):
                    proxy = 'http://' + proxy
                self.session.proxies = {'http': proxy, 'https': proxy}
                self.proxy_str = proxy.replace('http://', '').replace('https://', '')
            elif isinstance(proxy, dict):
                proxies = {}
                for k, v in proxy.items():
                    if k in ('http', 'https') and v:
                        if not v.startswith('http://') and not v.startswith('https://'):
                            v = 'http://' + v
                        proxies[k] = v
                if proxies:
                    self.session.proxies = proxies
                    self.proxy_str = (proxies.get('https') or proxies.get('http') or '').replace('http://', '').replace('https://', '')
                else:
                    self._auto_detect_proxy()
            else:
                self._auto_detect_proxy()
        else:
            self._auto_detect_proxy()

        self._load_cookies()

        self.yt_classes = YOUTUBE_CLASSES
        self.yt_filters = CATEGORY_FILTERS

        self.header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.youtube.com/'
        }
        self.session.headers.update(self.header)

        self.yt_video = YouTubeLite(self.session, self.header, self.extendDict)
        self.yt_live = YouTubeLiveLite(self.session, self.header, self.extendDict)
        self.search_page_cache = {}
        self.live_search_cache = {}
        self.hls_url_cache = {}
        self.hls_proxy_enabled = self.extendDict.get('hls_proxy', True) is not False
        self._hls_key_seq = 0
        self.direct_segments = str(self.extendDict.get('seg') or 'proxy').lower() == 'direct'

        self.media_fresh_cache = {}
        self.media_fresh_ttl = int(self.extendDict.get('media_refresh_ttl') or 300)
        self.media_force_refresh_sec = int(self.extendDict.get('media_force_refresh_sec') or 600)
        self._media_locks = {}
        self._media_locks_lock = threading.Lock()
        self._proxy_refresh_ts = {}
        self._proxy_fail_count = {}
        self._proxy_min_refresh_interval = float(self.extendDict.get('proxy_min_refresh_interval') or 10)

    def _parse_cookie_string(self, raw):
        count = 0
        for part in (raw or '').split(';'):
            part = part.strip()
            if not part or '=' not in part:
                continue
            name, value = part.split('=', 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            if name.startswith('#') or name in ('TRUE', 'FALSE'):
                continue
            self.session.cookies.set(name, value, domain='.youtube.com', path='/')
            count += 1
        return count

    def _load_cookies(self):
        cookie_src = (
            self.extendDict.get('cookie')
            or self.extendDict.get('cookies')
            or self.extendDict.get('cookiefile')
            or self.extendDict.get('cookies_file')
        )
        if not cookie_src:
            default_paths = [
                '/storage/emulated/0/Download/cookies.txt',
                '/storage/emulated/0/Download/ytb_cookies.txt',
                '/storage/emulated/0/Download/youtube_cookies.txt',
                os.path.join(os.path.dirname(__file__), 'cookies.txt'),
                os.path.join(os.path.dirname(__file__), 'ytb_cookies.txt'),
            ]
            for p in default_paths:
                if os.path.isfile(p):
                    cookie_src = p
                    break
        if not cookie_src:
            return False
        try:
            if os.path.isfile(str(cookie_src)):
                with open(str(cookie_src), 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                is_netscape = (
                    content.startswith('#') or '\t' in content
                    or '	' in content or 'Netscape' in content[:200]
                )
                if is_netscape:
                    try:
                        from http.cookiejar import MozillaCookieJar
                        jar = MozillaCookieJar(str(cookie_src))
                        jar.load(ignore_discard=True, ignore_expires=True)
                        count = 0
                        for c in jar:
                            domain = (c.domain or '')
                            if 'youtube.com' in domain or 'google.com' in domain:
                                self.session.cookies.set_cookie(c)
                                count += 1
                        if count > 0:
                            return True
                    except Exception as e:
                        debug_log('Netscape 解析失败', repr(e))
                if '=' in content and ';' in content:
                    count = self._parse_cookie_string(content)
                    if count > 0:
                        return True
                return False
            if isinstance(cookie_src, str) and '=' in cookie_src:
                count = self._parse_cookie_string(cookie_src)
                if count > 0:
                    return True
                return False
            if isinstance(cookie_src, dict):
                for k, v in cookie_src.items():
                    self.session.cookies.set(str(k), str(v), domain='.youtube.com', path='/')
                return True
        except Exception as e:
            debug_log('cookie 加载失败', repr(e))
            return False
        return False

    def _auto_detect_proxy(self):
        proxy_list = [
            "http://127.0.0.1:2080", "http://127.0.0.1:7890", "http://127.0.0.1:10809",
            "http://127.0.0.1:10172", "http://127.0.0.1:20172", "http://127.0.0.1:7891",
            "http://127.0.0.1:10808", "http://127.0.0.1:1087", "http://127.0.0.1:3128",
            "http://127.0.0.1:1080", "http://127.0.0.1:8080", "http://127.0.0.1:9090"
        ]
        for p in proxy_list:
            try:
                test_proxies = {'http': p, 'https': p}
                r = requests.get('https://www.youtube.com', proxies=test_proxies, timeout=2)
                if r.status_code < 400:
                    self.session.proxies = test_proxies
                    self.proxy_str = p.replace('http://', '').replace('https://', '')
                    return
            except Exception:
                continue
        self.session.proxies = {}
        self.proxy_str = ''

    def _get_media_lock(self, video_id):
        with self._media_locks_lock:
            if video_id not in self._media_locks:
                self._media_locks[video_id] = threading.Lock()
            return self._media_locks[video_id]

    def _get_url_expire(self, url):
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            expire = query.get('expire', ['0'])[0]
            return int(expire) if expire and expire.isdigit() else 0
        except Exception:
            return 0

    def _fresh_media_data(self, video_id, ttl=None, current_url=None, force=False, prefer_client=None):
        ttl = self.media_fresh_ttl if ttl is None else ttl
        lock = self._get_media_lock(video_id)
        with lock:
            now = time.time()
            cached = self.media_fresh_cache.get(video_id)
            need_refresh = bool(force)
            if not cached:
                need_refresh = True
            else:
                url_expire = cached.get('url_expire', 0)
                if url_expire > 0 and url_expire - now > 180:
                    need_refresh = False
                elif cached.get('expires', 0) <= now:
                    need_refresh = True
                elif url_expire > 0 and url_expire - now < 180:
                    need_refresh = True
                refreshed_at = cached.get('refreshed_at', 0)
                if (not url_expire) and refreshed_at and (now - refreshed_at) >= self.media_force_refresh_sec:
                    need_refresh = True
                if current_url:
                    cur_expire = self._get_url_expire(current_url)
                    if cur_expire > 0 and cur_expire - now < 180:
                        need_refresh = True
                    elif cur_expire > 0 and cur_expire - now > 180:
                        need_refresh = False
            if not need_refresh:
                return cached.get('data')
            try:
                data = self.yt_video.refresh(video_id, prefer_client=prefer_client)
            except Exception:
                data = self.yt_video.extract(video_id, force=True)
            formats = data.get('formats', [])
            if prefer_client and cached and cached.get('data'):
                old_formats = cached['data'].get('formats') or []
                new_keys = {(f.get('client'), f.get('itag')) for f in formats}
                merged = list(formats)
                for f in old_formats:
                    key = (f.get('client'), f.get('itag'))
                    if key not in new_keys:
                        merged.append(f)
                data = dict(data)
                data['formats'] = merged
                formats = merged
            earliest_expire = float('inf')
            for f in formats:
                exp = self._get_url_expire(f.get('url', ''))
                if exp > 0 and exp < earliest_expire:
                    earliest_expire = exp
            self.media_fresh_cache[video_id] = {
                'data': data,
                'expires': now + ttl,
                'url_expire': earliest_expire if earliest_expire != float('inf') else 0,
                'refreshed_at': now,
            }
            return data

    def _can_force_refresh(self, vid, force_first=False):
        now = time.time()
        last = self._proxy_refresh_ts.get(vid) or 0
        interval = getattr(self, '_proxy_min_refresh_interval', 10) or 10
        if force_first and (now - last) >= 1.0:
            self._proxy_refresh_ts[vid] = now
            return True
        if now - last < interval:
            return False
        self._proxy_refresh_ts[vid] = now
        return True

    # ========== 分类 / 搜索 ==========
    def homeContent(self, filter):
        result = {'class': self.yt_classes}
        if filter:
            video_filters = {}
            for c in self.yt_classes:
                cid = c['type_id']
                if cid in self.yt_filters:
                    video_filters[cid] = self.yt_filters[cid]
            result['filters'] = video_filters
        return result

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, cid, page, filter, ext):
        page = int(page or 1)
        filters = ext if isinstance(ext, dict) else {}
        if self._is_live_category(cid):
            keyword = self._build_live_keyword(cid, filters)
            videos, has_more = self._search_live_page(keyword, page)
        else:
            keyword = self._build_video_keyword(cid, filters)
            videos, has_more = self._search_video_page(keyword, page)
        return {
            'list': videos, 'page': page,
            'pagecount': page + 1 if has_more else page,
            'limit': len(videos), 'total': len(videos)
        }

    def searchContent(self, key, quick, pg=1):
        page = int(pg or 1)
        keyword = str(key or '').strip()
        videos_v, _ = self._search_video_page(keyword, page)
        live_keyword = f'{keyword} live' if 'live' not in keyword.lower() and '直播' not in keyword else keyword
        videos_l, _ = self._search_live_page(live_keyword, page)
        seen = set()
        merged = []
        for v in videos_v + videos_l:
            if v['vod_id'] not in seen:
                seen.add(v['vod_id'])
                merged.append(v)
        return {
            'list': merged[:30], 'page': page,
            'pagecount': page + 1, 'limit': len(merged), 'total': len(merged)
        }

    def _is_live_category(self, cid):
        return 'live' in cid.lower() or '直播' in cid.lower()

    def _build_live_keyword(self, cid, filters=None):
        terms = [cid]
        if isinstance(filters, dict):
            for value in filters.values():
                term = self._normalize_filter_term(value)
                if term:
                    terms.append(term)
        keyword = ' '.join([x for x in terms if x]).strip()
        if 'live' not in keyword.lower() and '直播' not in keyword:
            keyword = f'{keyword} live'
        return keyword

    def _build_video_keyword(self, cid, filters=None):
        if cid.startswith('LIST:'):
            raw = cid[5:].strip()
            channels = [ch.strip() for ch in raw.split(',') if ch.strip()]
            terms = []
            for ch in channels:
                if ch.startswith('@'):
                    terms.append(f'channel:{ch}')
                else:
                    terms.append(f'"{ch}"')
            keyword = ' OR '.join(terms) if terms else ''
        else:
            keyword = cid
        if isinstance(filters, dict):
            for value in filters.values():
                term = self._normalize_filter_term(value)
                if term:
                    keyword += ' ' + term
        return keyword.strip()

    def _normalize_filter_term(self, value):
        if isinstance(value, (list, tuple)):
            return ' '.join([self._normalize_filter_term(item) for item in value if item])
        if isinstance(value, dict):
            return ' '.join([self._normalize_filter_term(item) for item in value.values() if item])
        return re.sub(r'\s+', ' ', str(value or '')).strip()[:180]

    def _search_cache_key(self, key):
        return re.sub(r'\s+', ' ', str(key or '')).strip().lower()

    def _search_video_page(self, key, page=1):
        page = max(1, int(page or 1))
        cache_key = self._search_cache_key(key)
        session = self.search_page_cache.get(cache_key)
        if page == 1 or not session:
            session = self._fetch_search_first_page(key)
            self.search_page_cache[cache_key] = session
        while len(session.get('pages', [])) < page and session.get('next'):
            data = self._fetch_search_continuation(session)
            videos = self._extract_videos_from_api(data, 30)
            session.setdefault('pages', []).append(videos)
            session['next'] = self._extract_continuation_token(data)
        pages = session.get('pages', [])
        videos = pages[page - 1] if len(pages) >= page else []
        has_more = bool(session.get('next')) or len(pages) > page
        return videos, has_more

    def _search_live_page(self, key, page=1):
        page = max(1, int(page or 1))
        cache_key = f'live_{self._search_cache_key(key)}'
        session = self.live_search_cache.get(cache_key)
        if page == 1 or not session:
            session = self._fetch_live_search_first_page(key)
            self.live_search_cache[cache_key] = session
        while len(session.get('pages', [])) < page and session.get('next'):
            data = self._fetch_search_continuation(session)
            videos = self._extract_live_videos_from_api(data, 30)
            session.setdefault('pages', []).append(videos)
            session['next'] = self._extract_continuation_token(data)
        pages = session.get('pages', [])
        videos = pages[page - 1] if len(pages) >= page else []
        has_more = bool(session.get('next')) or len(pages) > page
        return videos, has_more

    def _fetch_live_search_first_page(self, key):
        search_url = f'https://www.youtube.com/results?search_query={quote(str(key or ""))}&sp=EgJAAQ%253D%253D'
        r = self.session.get(search_url, timeout=10)
        html_str = r.text
        data = self.yt_video._extract_json_after(html_str, 'ytInitialData') or {}
        ytcfg = self.yt_video._extract_ytcfg(html_str) or {}
        api_key = ytcfg.get('INNERTUBE_API_KEY') or self.yt_video._search(r'"INNERTUBE_API_KEY":"([^"]+)"', html_str)
        context = ytcfg.get('INNERTUBE_CONTEXT') or {'client': {'clientName': 'WEB', 'clientVersion': '2.20240310.01.00', 'hl': 'zh-CN', 'gl': 'US'}}
        client = context.get('client') or {}
        return {
            'key': key, 'api_key': api_key, 'context': context,
            'client_name': client.get('clientName') or 'WEB',
            'client_version': client.get('clientVersion') or '2.20240310.01.00',
            'referer': search_url,
            'pages': [self._extract_live_videos_from_api(data, 30)],
            'next': self._extract_continuation_token(data),
        }

    def _fetch_search_first_page(self, key):
        search_url = f'https://www.youtube.com/results?search_query={quote(str(key or ""))}'
        r = self.session.get(search_url, timeout=10)
        html_str = r.text
        data = self.yt_video._extract_json_after(html_str, 'ytInitialData') or {}
        ytcfg = self.yt_video._extract_ytcfg(html_str) or {}
        api_key = ytcfg.get('INNERTUBE_API_KEY') or self.yt_video._search(r'"INNERTUBE_API_KEY":"([^"]+)"', html_str)
        context = ytcfg.get('INNERTUBE_CONTEXT') or {'client': {'clientName': 'WEB', 'clientVersion': '2.20240310.01.00', 'hl': 'zh-CN', 'gl': 'US'}}
        client = context.get('client') or {}
        return {
            'key': key, 'api_key': api_key, 'context': context,
            'client_name': client.get('clientName') or 'WEB',
            'client_version': client.get('clientVersion') or '2.20240310.01.00',
            'referer': search_url,
            'pages': [self._extract_videos_from_api(data, 30)],
            'next': self._extract_continuation_token(data),
        }

    def _fetch_search_continuation(self, session):
        token = session.get('next')
        api_key = session.get('api_key')
        if not token or not api_key:
            return {}
        url = f'https://www.youtube.com/youtubei/v1/search?key={quote(api_key)}'
        headers = self.header.copy()
        headers.update({
            'Content-Type': 'application/json',
            'Origin': 'https://www.youtube.com',
            'Referer': session.get('referer') or 'https://www.youtube.com/',
            'X-YouTube-Client-Name': '1',
            'X-YouTube-Client-Version': session.get('client_version') or '2.20240310.01.00',
        })
        payload = {'context': session.get('context') or {}, 'continuation': token}
        r = self.session.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def _extract_continuation_token(self, data):
        tokens = []
        def scan(obj):
            if isinstance(obj, dict):
                for key in ('continuationEndpoint', 'continuationItemRenderer'):
                    if key in obj:
                        token = obj[key].get('continuationCommand', {}).get('token')
                        if token:
                            tokens.append(token)
                for value in obj.values():
                    scan(value)
            elif isinstance(obj, list):
                for value in obj:
                    scan(value)
        scan(data)
        return tokens[0] if tokens else ''

    def _extract_videos_from_api(self, data, limit=30):
        videos = []
        seen = set()
        def scan(obj):
            if len(videos) >= limit:
                return
            if isinstance(obj, dict):
                for key in ('videoRenderer', 'compactVideoRenderer', 'gridVideoRenderer'):
                    if key in obj:
                        item = self._parse_renderer(obj[key], is_live=False)
                        if item and item['vod_id'] not in seen:
                            seen.add(item['vod_id'])
                            videos.append(item)
                for value in obj.values():
                    scan(value)
            elif isinstance(obj, list):
                for value in obj:
                    scan(value)
        scan(data)
        return videos[:limit]

    def _extract_live_videos_from_api(self, data, limit=30):
        videos = []
        seen = set()
        def scan(obj):
            if len(videos) >= limit:
                return
            if isinstance(obj, dict):
                for key in ('videoRenderer', 'compactVideoRenderer', 'gridVideoRenderer'):
                    if key in obj:
                        item = self._parse_renderer(obj[key], is_live=True)
                        if item and item['vod_id'] not in seen:
                            seen.add(item['vod_id'])
                            videos.append(item)
                for value in obj.values():
                    scan(value)
            elif isinstance(obj, list):
                for value in obj:
                    scan(value)
        scan(data)
        return videos[:limit]

    def _parse_renderer(self, renderer, is_live=False):
        try:
            vid = renderer.get('videoId')
            if not vid:
                nav = renderer.get('navigationEndpoint') or {}
                vid = (nav.get('watchEndpoint') or {}).get('videoId')
            if not vid:
                return None
            title_obj = renderer.get('title') or renderer.get('headline') or {}
            title = title_obj.get('simpleText') or ''.join([x.get('text', '') for x in title_obj.get('runs', [])]) or 'YouTube Video'
            dur = (renderer.get('lengthText') or {}).get('simpleText') or ''
            remarks = '直播' if is_live else (dur if dur else '视频')
            return {
                'vod_id': vid,
                'vod_name': html.unescape(title),
                'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={vid}',
                'vod_remarks': remarks
            }
        except Exception:
            return None

    def _get_video_title(self, vid):
        try:
            r = self.session.get(f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json', timeout=5)
            return r.json().get('title') or vid
        except Exception:
            return vid

    def _safe_title(self, title):
        if not title:
            return 'video'
        return re.sub(r'[#$@%&!?*|\\/:<>]', ' ', title)[:60]

    def _get_quality_label(self, height):
        if height >= 2160: return '4K'
        elif height >= 1440: return '2K'
        elif height >= 1080: return '1080P'
        elif height >= 720: return '720P'
        elif height >= 480: return '480P'
        elif height >= 360: return '360P'
        else: return f'{height}P'

    # ========== detailContent ==========
    def detailContent(self, did):
        video_id = did[0]
        try:
            live_data = self.yt_live.extract_live(video_id)
            is_live = live_data.get('is_live') or bool(live_data.get('hls_url'))
            title = live_data.get('title') or video_id
            status = '直播中' if is_live else '未开播'
        except Exception as e:
            is_live = False
            title = self._get_video_title(video_id) or video_id
            status = '视频'

        play_sources = []
        play_urls = []

        if is_live:
            hls_url = live_data.get('hls_url')
            if hls_url:
                variants = self._parse_hls_master(hls_url)
                if variants:
                    for v in variants:
                        height = v['height']
                        label = self._get_quality_label(height)
                        cache_key = f'live_{video_id}_{height}'
                        self.setCache(cache_key, {'url': v['url'], 'expires': time.time() + 300})
                        play_sources.append(label)
                        play_urls.append(f'{label}${video_id}@live_{height}')
                else:
                    play_sources.append('直播')
                    play_urls.append(f'直播${video_id}@live')
            else:
                play_sources.append('直播')
                play_urls.append(f'直播${video_id}@live')
        else:
            try:
                data = self.yt_video.extract(video_id)
                formats = data.get('formats', [])
                video_streams = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
                height_groups = {}
                for f in video_streams:
                    h = int(f.get('height', 0))
                    if h <= 0: continue
                    height_groups.setdefault(h, []).append(f)
                for h in sorted(height_groups.keys(), reverse=True):
                    items = height_groups[h]
                    sdr_items = [x for x in items if not self.yt_video._is_hdr_video(x)]
                    hdr_items = [x for x in items if self.yt_video._is_hdr_video(x)]
                    sdr_item = max(sdr_items, key=lambda x: int(x.get('bitrate') or 0)) if sdr_items else None
                    hdr_item = max(hdr_items, key=lambda x: int(x.get('bitrate') or 0)) if hdr_items else None
                    label_base = self._get_quality_label(h)
                    if sdr_item:
                        play_sources.append(f'{label_base} SDR')
                        play_urls.append(f'{label_base} SDR${video_id}@{h}_sdr')
                    if hdr_item:
                        play_sources.append(f'{label_base} HDR')
                        play_urls.append(f'{label_base} HDR${video_id}@{h}_hdr')
                if not play_sources:
                    raise Exception('No video streams found')
            except Exception as e:
                debug_log('detail get formats error', {'video_id': video_id, 'error': repr(e)})
                play_sources.append('最高画质')
                play_urls.append(f'最高画质${video_id}@best')

        related = []
        try:
            r = self.session.get(f'https://www.youtube.com/watch?v={video_id}', timeout=10)
            related = self._extract_videos_from_api(
                self.yt_video._extract_json_after(r.text, 'ytInitialData') or {}, 20
            )
        except Exception:
            pass

        if related:
            related_urls = []
            for v in related:
                if v.get('vod_id') != video_id:
                    related_urls.append(f"{self._safe_title(v['vod_name'])}${v['vod_id']}@best")
            if related_urls:
                play_sources.append('相关推荐')
                play_urls.append('#'.join(related_urls))

        vod = {
            'vod_id': video_id,
            'vod_name': title,
            'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={video_id}',
            'vod_remarks': status,
            'vod_play_from': '$$$'.join(play_sources),
            'vod_play_url': '$$$'.join(play_urls)
        }
        return {'list': [vod]}

    # ========== playerContent ==========
    def playerContent(self, flag, pid, vipFlags):
        raw_pid = pid.split('$')[-1]
        if '@' in raw_pid:
            video_id, quality_or_type = raw_pid.rsplit('@', 1)
        else:
            video_id, quality_or_type = raw_pid, 'best'

        if quality_or_type == 'live':
            return self._play_live(video_id)
        elif quality_or_type.startswith('live_'):
            height_str = quality_or_type.split('_')[1]
            if height_str.isdigit():
                return self._play_live_by_height(video_id, int(height_str))
            else:
                return self._play_live(video_id)
        else:
            if quality_or_type.endswith('_sdr') or quality_or_type.endswith('_hdr'):
                parts = quality_or_type.rsplit('_', 1)
                if len(parts) == 2 and parts[1] in ('sdr', 'hdr'):
                    height_str, hdr_flag = parts
                    if height_str.isdigit():
                        return self._play_video_by_height_and_type(video_id, int(height_str), hdr_flag)
            if quality_or_type.isdigit():
                return self._play_video_by_height_and_type(video_id, int(quality_or_type), 'sdr')
            else:
                quality = quality_or_type if quality_or_type in ('best', '4k', '2k', '1080p') else 'best'
                return self._play_video(video_id, quality)

    def _play_headers_for_item(self, item):
        h = {}
        try:
            h.update(self.header or {})
        except Exception:
            pass
        item_h = (item or {}).get('headers') or {}
        h.update(item_h)
        ua = item_h.get('User-Agent') or (item or {}).get('_client_ua')
        if not ua:
            client = (item or {}).get('client') or ''
            if client == 'ANDROID_VR':
                ua = 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip'
            elif client in ('WEB_EMBEDDED_PLAYER', 'WEB_EMBEDDED'):
                ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            elif client in ('TVHTML5_SIMPLY_EMBEDDED_PLAYER', 'TVHTML5'):
                ua = 'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version'
        if ua:
            h['User-Agent'] = ua
        h['Accept'] = '*/*'
        h['Accept-Encoding'] = 'identity'
        h.pop('Origin', None)
        if (item or {}).get('client') in ('ANDROID_VR', 'ANDROID', 'IOS', 'WEB_EMBEDDED_PLAYER', 'TVHTML5_SIMPLY_EMBEDDED_PLAYER'):
            h.pop('Referer', None)
        return h

    def _play_video_by_height_and_type(self, video_id, target_height, hdr_type):
        try:
            data = self.yt_video.extract(video_id)
            formats = data.get('formats', []) or []

            # HLS 优先
            hls_url = data.get('hls_url') or ''
            if hls_url:
                try:
                    if getattr(self, 'hls_proxy_enabled', True):
                        play_url = self._cache_hls_url(hls_url, video_id, 'master')
                    else:
                        play_url = hls_url
                    return {
                        'parse': 0, 'jx': 0,
                        'url': play_url,
                        'header': self.header,
                        'format': 'application/x-mpegURL',
                    }
                except Exception:
                    pass

            client_order = {
                'ANDROID_VR': 0, 'WEB_EMBEDDED_PLAYER': 1,
                'TVHTML5_SIMPLY_EMBEDDED_PLAYER': 2, 'WEB': 3,
                'ANDROID': 8, 'IOS': 9, 'MWEB': 10,
            }

            def _is_progressive(f):
                if not f or not f.get('url'):
                    return False
                vc, ac = f.get('vcodec'), f.get('acodec')
                if vc not in (None, '', 'none') and ac not in (None, '', 'none'):
                    return True
                return False

            # progressive 直链
            progressive = [f for f in formats if _is_progressive(f)]
            min_accept = 720 if int(target_height) >= 720 else max(360, int(target_height) - 120)
            prog_ok = [f for f in progressive if int(f.get('height') or 0) >= min_accept]
            if prog_ok:
                prog_ok.sort(key=lambda x: (
                    int(x.get('height') or 0),
                    -client_order.get(x.get('client') or '', 9),
                    int(x.get('bitrate') or 0),
                ), reverse=True)
                selected = prog_ok[0]
                return {
                    'parse': 0, 'jx': 0,
                    'url': selected['url'],
                    'header': self._play_headers_for_item(selected),
                }

            # DASH 分离流
            video_streams = [
                f for f in formats
                if f.get('vcodec') not in (None, '', 'none') and f.get('acodec') in (None, '', 'none')
            ]
            is_hdr_wanted = (hdr_type == 'hdr')
            hdr_candidates = [f for f in video_streams if self.yt_video._is_hdr_video(f) == is_hdr_wanted]
            candidates = hdr_candidates if hdr_candidates else video_streams

            height_groups = {}
            for f in candidates:
                h = int(f.get('height') or 0)
                if h > 0:
                    height_groups.setdefault(h, []).append(f)

            available_heights = sorted(height_groups.keys(), reverse=True)
            selected_height = None
            if target_height in height_groups:
                selected_height = target_height
            else:
                lower = [h for h in available_heights if h <= target_height]
                if lower:
                    selected_height = max(lower)
                elif available_heights:
                    selected_height = min(available_heights)

            if not selected_height or selected_height not in height_groups:
                return {
                    'parse': 1, 'jx': 0,
                    'url': f'https://www.youtube.com/watch?v={video_id}',
                    'header': self.header,
                }

            final_candidates = height_groups[selected_height]
            final_candidates.sort(key=lambda x: (
                client_order.get(x.get('client') or '', 9),
                -(int(x.get('bitrate') or 0)),
            ))
            selected_video = final_candidates[0]
            preferred_client = selected_video.get('client') or ''

            audio_candidates = [
                f for f in formats
                if f.get('acodec') not in (None, '', 'none') and f.get('vcodec') in (None, '', 'none')
            ]
            same_client_audio = [f for f in audio_candidates if f.get('client') == preferred_client]
            pool = same_client_audio if same_client_audio else audio_candidates
            pool.sort(key=lambda x: (
                client_order.get(x.get('client') or '', 9),
                -(int(x.get('bitrate') or 0)),
            ))
            audio = pool[0] if pool else None

            cache_key = f'yt_{video_id}_{target_height}_{hdr_type}'
            if audio:
                self.setCache(cache_key, {
                    'video_tracks': [selected_video],
                    'video_url': selected_video['url'],
                    'audio_url': audio['url'],
                    'video_item': selected_video,
                    'audio_item': audio,
                    'all_formats': formats,
                    'duration': data.get('duration') or 0,
                    'expires': time.time() + 3600,
                    'mode': 'dash',
                })
                return {
                    'parse': 0, 'jx': 0,
                    'url': f'http://127.0.0.1:9978/proxy?do=py&type=mpd&vid={video_id}&quality={target_height}_{hdr_type}',
                    'format': 'application/dash+xml',
                }
            return {
                'parse': 0, 'jx': 0,
                'url': selected_video['url'],
                'header': self._play_headers_for_item(selected_video),
            }
        except Exception as e:
            debug_log('_play_video_by_height_and_type error', {
                'video_id': video_id, 'height': target_height, 'type': hdr_type, 'error': repr(e),
            })
            return {
                'parse': 1, 'jx': 0,
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'header': self.header,
            }

    def _play_live_by_height(self, video_id, target_height):
        cache_key = f'live_{video_id}_{target_height}'
        cached = self.getCache(cache_key)
        if cached and cached.get('url'):
            variant_url = cached['url']
            if self.hls_proxy_enabled:
                play_url = self._cache_hls_url(variant_url, video_id, 'master')
            else:
                play_url = variant_url
            return {
                'parse': 0, 'jx': 0,
                'url': play_url,
                'header': self.header,
                'format': 'application/x-mpegURL'
            }
        else:
            return self._play_live(video_id)

    def _play_live(self, video_id):
        try:
            data = self.yt_live.extract_live(video_id)
            hls_url = data.get('hls_url') or ''
            if not hls_url:
                raise Exception(data.get('reason') or '未获取到直播 HLS 地址')
            play_url = hls_url
            if self.hls_proxy_enabled:
                play_url = self._cache_hls_url(hls_url, video_id, 'master')
            return {
                'parse': 0, 'jx': 0,
                'url': play_url,
                'header': self.header,
                'format': 'application/x-mpegURL'
            }
        except Exception as e:
            debug_log('_play_live error', {'video_id': video_id, 'error': repr(e)})
            return {'parse': 1, 'jx': 1, 'url': f'https://www.youtube.com/embed/{video_id}?autoplay=1'}

    def _play_video(self, video_id, quality):
        try:
            data = self.yt_video.extract(video_id)
            formats = data.get('formats') or []

            # HLS 优先
            hls_url = data.get('hls_url') or ''
            if hls_url:
                try:
                    play_url = self._cache_hls_url(hls_url, video_id, 'master') if getattr(self, 'hls_proxy_enabled', True) else hls_url
                    return {
                        'parse': 0, 'jx': 0,
                        'url': play_url,
                        'header': self.header,
                        'format': 'application/x-mpegURL',
                    }
                except Exception:
                    pass

            progressive = [
                f for f in formats
                if f.get('url') and f.get('vcodec') not in (None, '', 'none')
                and f.get('acodec') not in (None, '', 'none')
            ]
            if quality == '4k':
                prog = [f for f in progressive if int(f.get('height') or 0) >= 1440] or progressive
            elif quality == '2k':
                prog = [f for f in progressive if int(f.get('height') or 0) >= 1080] or progressive
            elif quality == '1080p':
                prog = [f for f in progressive if int(f.get('height') or 0) >= 720] or []
            else:
                prog = [f for f in progressive if int(f.get('height') or 0) >= 720] or progressive

            if prog:
                prog.sort(key=lambda x: (int(x.get('height') or 0), int(x.get('bitrate') or 0)), reverse=True)
                playable = prog[0]
                return {
                    'parse': 0, 'jx': 0,
                    'url': playable['url'],
                    'header': self._play_headers_for_item(playable),
                }

            playable = self.yt_video.choose_playable(formats, quality)
            if playable:
                audio = self.yt_video.choose_audio(formats)
                cache_key = f'yt_{video_id}_{quality}'
                if audio and (playable.get('acodec') in (None, '', 'none')):
                    self.setCache(cache_key, {
                        'video_url': playable['url'],
                        'audio_url': audio['url'],
                        'video_item': playable,
                        'audio_item': audio,
                        'duration': data.get('duration') or 0,
                        'expires': time.time() + 3600,
                        'mode': 'dash',
                    })
                    return {
                        'parse': 0, 'jx': 0,
                        'url': f'http://127.0.0.1:9978/proxy?do=py&type=mpd&vid={video_id}&quality={quality}',
                        'format': 'application/dash+xml',
                    }
                return {
                    'parse': 0, 'jx': 0,
                    'url': playable['url'],
                    'header': self._play_headers_for_item(playable),
                }
            raise Exception(f'没有可直接播放的 {quality} 视频流格式')
        except Exception as e:
            debug_log('_play_video error', repr(e))
            return {
                'parse': 1, 'jx': 0,
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'header': self.header,
            }

    def _parse_hls_master(self, master_url):
        try:
            r = self.session.get(master_url, headers=self.header, timeout=10)
            r.raise_for_status()
            lines = r.text.splitlines()
            variants = []
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.startswith('#EXT-X-STREAM-INF'):
                    bandwidth = re.search(r'BANDWIDTH=(\d+)', line)
                    resolution = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                    height = int(resolution.group(2)) if resolution else 0
                    width = int(resolution.group(1)) if resolution else 0
                    bw = int(bandwidth.group(1)) if bandwidth else 0
                    if i + 1 < len(lines):
                        url_line = lines[i+1].strip()
                        if not url_line.startswith('#'):
                            full_url = urljoin(master_url, url_line)
                            variants.append({
                                'height': height, 'width': width,
                                'bandwidth': bw, 'url': full_url
                            })
                    i += 2
                else:
                    i += 1
            variants.sort(key=lambda x: x['height'], reverse=True)
            return variants
        except Exception as e:
            debug_log('parse hls master error', {'master_url': master_url, 'error': repr(e)})
            return []

    # ========== 本地代理（保持原样） ==========
    def localProxy(self, params):
        if params.get('do') != 'py':
            return None
        typ = params.get('type')
        if typ == 'mpd':
            return self._proxy_mpd(params)
        if typ == 'media':
            return self._proxy_media(params)
        if typ == 'single':
            return self._proxy_single(params)
        if typ == 'image':
            return self._proxy_image(params)
        if typ == 'hls':
            return self._proxy_hls(params)
        return None

    def _cdn_get(self, url, headers=None, stream=False, timeout=15, **kwargs):
        req_headers = {}
        if headers:
            req_headers.update(headers)
        proxies = getattr(self.session, 'proxies', None) or {}
        return requests.get(
            url, headers=req_headers, stream=stream,
            timeout=timeout, proxies=proxies, cookies={}, **kwargs
        )

    def _proxy_image(self, params):
        vid = params.get('vid')
        if not vid:
            return [400, 'text/plain', '缺少 video id']
        for quality in ['maxresdefault.jpg', 'hqdefault.jpg', 'mqdefault.jpg', 'sddefault.jpg', 'default.jpg']:
            img_url = f'https://img.youtube.com/vi/{vid}/{quality}'
            try:
                r = self._cdn_get(img_url, headers={'User-Agent': self.header.get('User-Agent', '')}, timeout=10)
                if r.status_code == 200 and len(r.content) > 1000:
                    content_type = r.headers.get('content-type', 'image/jpeg')
                    return [200, content_type, r.content, {'Cache-Control': 'max-age=86400'}]
            except Exception:
                continue
        return [404, 'text/plain', '图片获取失败']

    def _proxy_single(self, params):
        vid = params.get('vid')
        quality = params.get('quality') or 'best'
        data = self.getCache(f'yt_{vid}_{quality}') if vid else None
        if not data:
            return [404, 'text/plain', '播放缓存已过期或不存在']
        target_url = data.get('video_url')
        media_item = data.get('video_item') or {}
        if not target_url:
            return [404, 'text/plain', '播放地址不存在']

        pinned_client = media_item.get('client') or 'ANDROID_VR'
        pinned_itag = media_item.get('itag')

        def pick_url(fresh_data, client_name):
            formats = (fresh_data or {}).get('formats') or []
            progressive = [
                f for f in formats
                if f.get('url') and f.get('vcodec') not in (None, '', 'none')
                and f.get('acodec') not in (None, '', 'none')
            ]
            if pinned_itag is not None:
                for f in progressive:
                    if f.get('client') == client_name and f.get('itag') == pinned_itag:
                        return f.get('url'), f
                for f in progressive:
                    if f.get('itag') == pinned_itag:
                        return f.get('url'), f
            if progressive:
                progressive.sort(key=lambda x: int(x.get('height') or 0), reverse=True)
                same = [f for f in progressive if f.get('client') == client_name]
                chosen = same[0] if same else progressive[0]
                return chosen.get('url'), chosen
            return None, None

        try:
            cur_exp = self._get_url_expire(target_url)
            now_ts = time.time()
            if cur_exp > 0 and cur_exp - now_ts < 60:
                fresh = self._fresh_media_data(vid, current_url=target_url, prefer_client=pinned_client)
                new_url, new_item = pick_url(fresh, pinned_client)
                if new_url:
                    target_url = new_url
                    media_item = new_item
                    data['video_url'] = target_url
                    data['video_item'] = media_item
                    self.setCache(f'yt_{vid}_{quality}', data)
        except Exception as e:
            debug_log('proxy_single soft refresh failed', {'vid': vid, 'error': repr(e)})

        def build_headers(item):
            return self._play_headers_for_item(item)

        range_header = params.get('range') or params.get('Range')
        headers = build_headers(media_item)
        if range_header:
            headers['Range'] = range_header

        last_error = None
        clients_to_try = [pinned_client]
        for c in ('ANDROID_VR', 'WEB_EMBEDDED', 'TVHTML5'):
            if c not in clients_to_try:
                clients_to_try.append(c)

        first_attempt = True
        for client_try in clients_to_try:
            for same_client_round in range(2):
                try:
                    if not first_attempt:
                        allow = self._can_force_refresh(vid, force_first=(same_client_round == 0 and client_try == pinned_client))
                        if not allow:
                            time.sleep(0.3)
                        else:
                            self.media_fresh_cache.pop(vid, None)
                            fresh = self._fresh_media_data(vid, ttl=0, force=True, prefer_client=client_try)
                            new_url, new_item = pick_url(fresh, client_try)
                            if new_url:
                                target_url = new_url
                                media_item = new_item
                                headers = build_headers(media_item)
                                if range_header:
                                    headers['Range'] = range_header
                            else:
                                break

                    first_attempt = False
                    r = self._cdn_get(target_url, headers=headers, stream=True, timeout=45)
                    content_type = r.headers.get('content-type', 'video/mp4')
                    resp_headers = {
                        'Content-Type': content_type,
                        'Accept-Ranges': 'bytes',
                        'Cache-Control': 'no-cache',
                    }
                    if r.headers.get('content-range'):
                        resp_headers['Content-Range'] = r.headers.get('content-range')
                    if r.headers.get('content-length'):
                        resp_headers['Content-Length'] = r.headers.get('content-length')

                    if r.status_code in (403, 404):
                        r.close()
                        time.sleep(0.2)
                        continue
                    if r.status_code in (200, 206):
                        data['video_url'] = target_url
                        data['video_item'] = media_item
                        self.setCache(f'yt_{vid}_{quality}', data)
                    return [r.status_code, content_type, r.content, resp_headers]
                except Exception as e:
                    last_error = e
                    time.sleep(0.2)
                    continue
            pinned_client = client_try
        return [500, 'text/plain', f'代理播放失败: {str(last_error)}']

    def _proxy_mpd(self, params):
        vid = params.get('vid')
        quality = params.get('quality') or '1080p'
        data = self.getCache(f'yt_{vid}_{quality}') if vid else None
        if not data:
            return [404, 'text/plain', '视频缓存已过期或不存在']
        video_url = data.get('video_url')
        audio_url = data.get('audio_url')
        duration = data.get('duration') or 0
        video_item = data.get('video_item') or {}
        audio_item = data.get('audio_item') or {}
        media_base = f'http://127.0.0.1:9978/proxy?do=py&type=media&vid={vid}&quality={quality}'
        duration_pt = f"PT{int(duration or 0)}S"
        video_mime = (video_item.get('mimeType') or 'video/webm').split(';')[0]
        audio_mime = (audio_item.get('mimeType') or 'audio/mp4').split(';')[0]
        video_init = video_item.get('initRange') or {}
        video_index = video_item.get('indexRange') or {}
        audio_init = audio_item.get('initRange') or {}
        audio_index = audio_item.get('indexRange') or {}
        mpd = f'''<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="{duration_pt}" minBufferTime="PT1.5S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">
  <Period id="1" start="PT0S">
    <AdaptationSet mimeType="{html.escape(video_mime)}" startWithSAP="1" segmentAlignment="true" scanType="progressive">
      <Representation id="v{video_item.get('itag', 1)}" bandwidth="{video_item.get('bitrate', 1000000)}" codecs="{html.escape(video_item.get('codecs') or '')}" height="{video_item.get('height', 0)}" width="{video_item.get('width', 0)}">
        <BaseURL>{html.escape(media_base + '&track=video')}</BaseURL>
        <SegmentBase indexRange="{video_index.get('start', '0')}-{video_index.get('end', '0')}"><Initialization range="{video_init.get('start', '0')}-{video_init.get('end', '0')}"/></SegmentBase>
      </Representation>
    </AdaptationSet>
'''
        if audio_url:
            mpd += f'''    <AdaptationSet mimeType="{html.escape(audio_mime)}" startWithSAP="1" segmentAlignment="true" lang="und">
      <Representation id="a{audio_item.get('itag', 1)}" bandwidth="{audio_item.get('bitrate', 128000)}" codecs="{html.escape(audio_item.get('codecs') or '')}" audioSamplingRate="44100">
        <BaseURL>{html.escape(media_base + '&track=audio')}</BaseURL>
        <SegmentBase indexRange="{audio_index.get('start', '0')}-{audio_index.get('end', '0')}"><Initialization range="{audio_init.get('start', '0')}-{audio_init.get('end', '0')}"/></SegmentBase>
      </Representation>
    </AdaptationSet>
'''
        mpd += '  </Period>\n</MPD>'
        return [200, 'application/dash+xml', mpd]

    def _proxy_media(self, params):
        vid = params.get('vid')
        quality = params.get('quality') or '1080p'
        track = params.get('track')
        data = self.getCache(f'yt_{vid}_{quality}') if vid else None
        if not data or track not in ('video', 'audio'):
            return [404, 'text/plain', '媒体不存在']
        cached_item = data.get('video_item') if track == 'video' else data.get('audio_item')
        pinned_client = (cached_item or {}).get('client') or 'ANDROID_VR'
        pinned_itag = (cached_item or {}).get('itag')
        pinned_height = int((cached_item or {}).get('height') or 0)

        def pick_url(fresh_data, client_name, itag=None, height=0):
            formats = (fresh_data or {}).get('formats') or []
            if track == 'video':
                pool = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('url')]
            else:
                pool = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url')]
            if not pool:
                return None, None
            if itag is not None and client_name:
                for f in pool:
                    if f.get('client') == client_name and f.get('itag') == itag:
                        return f.get('url'), f
            if client_name:
                same = [f for f in pool if f.get('client') == client_name]
                if height > 0 and track == 'video':
                    same_h = [f for f in same if int(f.get('height') or 0) == height]
                    if same_h:
                        chosen = max(same_h, key=lambda x: int(x.get('bitrate') or 0))
                        return chosen.get('url'), chosen
                if same:
                    chosen = max(same, key=lambda x: int(x.get('bitrate') or 0))
                    return chosen.get('url'), chosen
            if itag is not None:
                for f in pool:
                    if f.get('itag') == itag:
                        return f.get('url'), f
            chosen = max(pool, key=lambda x: int(x.get('bitrate') or 0))
            return chosen.get('url'), chosen

        target_url = data.get('video_url') if track == 'video' else data.get('audio_url')
        media_item = cached_item
        try:
            cur_exp = self._get_url_expire(target_url or '')
            now_ts = time.time()
            if target_url and cur_exp > 0 and cur_exp - now_ts < 60:
                fresh = self._fresh_media_data(vid, current_url=target_url, prefer_client=pinned_client)
                new_url, new_item = pick_url(fresh, pinned_client, pinned_itag, pinned_height)
                if new_url:
                    target_url = new_url
                    media_item = new_item
                    if track == 'video':
                        data['video_url'] = target_url
                        data['video_item'] = media_item
                    else:
                        data['audio_url'] = target_url
                        data['audio_item'] = media_item
                    self.setCache(f'yt_{vid}_{quality}', data)
        except Exception as e:
            debug_log('proxy_media soft refresh failed', {'vid': vid, 'error': repr(e)})

        if not target_url:
            return [404, 'text/plain', f'{track} 流不存在']

        def build_headers(item):
            h = self._play_headers_for_item(item)
            return h

        range_header = params.get('range') or params.get('Range')
        headers = build_headers(media_item)
        if range_header:
            headers['Range'] = range_header

        last_error = None
        clients_to_try = [pinned_client]
        for c in ('ANDROID_VR', 'WEB_EMBEDDED', 'TVHTML5'):
            if c not in clients_to_try:
                clients_to_try.append(c)

        for client_try in clients_to_try:
            for same_client_round in range(2):
                try:
                    if client_try != pinned_client or same_client_round > 0:
                        if not self._can_force_refresh(vid):
                            time.sleep(0.5)
                        else:
                            self.media_fresh_cache.pop(vid, None)
                            fresh = self._fresh_media_data(vid, ttl=0, force=True, prefer_client=client_try)
                            new_url, new_item = pick_url(fresh, client_try, pinned_itag, pinned_height)
                            if not new_url:
                                break
                            target_url = new_url
                            media_item = new_item
                            headers = build_headers(media_item)
                            if range_header:
                                headers['Range'] = range_header

                    r = self._cdn_get(target_url, headers=headers, stream=True, timeout=45)
                    content_type = r.headers.get('content-type', 'application/octet-stream')
                    resp_headers = {
                        'Content-Type': content_type,
                        'Accept-Ranges': 'bytes',
                        'Cache-Control': 'no-cache',
                    }
                    if r.headers.get('content-range'):
                        resp_headers['Content-Range'] = r.headers.get('content-range')
                    if r.headers.get('content-length'):
                        resp_headers['Content-Length'] = r.headers.get('content-length')

                    if r.status_code in (403, 404):
                        r.close()
                        continue

                    if r.status_code in (200, 206):
                        if track == 'video':
                            data['video_url'] = target_url
                            data['video_item'] = media_item
                        else:
                            data['audio_url'] = target_url
                            data['audio_item'] = media_item
                        self.setCache(f'yt_{vid}_{quality}', data)
                    return [r.status_code, content_type, r.content, resp_headers]
                except Exception as e:
                    last_error = e
                    time.sleep(0.2)
                    continue
            pinned_client = client_try

        return [500, 'text/plain', f'代理媒体失败: {str(last_error)}']

    # ========== HLS 代理 ==========
    HLS_TTL = {'master': 6 * 3600, 'playlist': 6 * 3600, 'media': 120, 'media_retry': 120}

    def _hls_ttl(self, kind):
        return self.HLS_TTL.get(kind, 180)

    def _prune_hls_cache(self):
        now = time.time()
        expired = [k for k, v in self.hls_url_cache.items() if v.get('expires', 0) < now]
        for k in expired:
            self.hls_url_cache.pop(k, None)

    def _cache_hls_url(self, target_url, video_id='', kind='media'):
        self._prune_hls_cache()
        self._hls_key_seq += 1
        key = f'{int(time.time() * 1000)}_{self._hls_key_seq}'
        self.hls_url_cache[key] = {
            'url': target_url,
            'video_id': video_id,
            'kind': kind,
            'expires': time.time() + self._hls_ttl(kind),
        }
        return f'http://127.0.0.1:9978/proxy?do=py&type=hls&key={quote(key)}'

    def _hls_headers(self, target_url, kind=None):
        if kind == 'media_retry':
            return {
                'User-Agent': 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip',
                'Accept': '*/*',
            }
        headers = self.header.copy()
        headers['Accept'] = '*/*'
        if kind in ('master', 'playlist'):
            headers['Origin'] = 'https://www.youtube.com'
            headers['Referer'] = 'https://www.youtube.com/'
        elif kind == 'media':
            headers['User-Agent'] = 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip'
            headers.pop('Origin', None)
            headers.pop('Referer', None)
        return headers

    def _rewrite_m3u8(self, text, base_url, video_id=''):
        output = []
        for line in (text or '').splitlines():
            stripped = line.strip()
            if not stripped:
                output.append(line)
                continue
            if stripped.startswith('#'):
                output.append(self._rewrite_m3u8_tag(line, base_url, video_id))
                continue
            absolute = urljoin(base_url, stripped)
            kind = 'playlist' if stripped.endswith('.m3u8') or '/hls_playlist/' in stripped else 'media'
            output.append(self._cache_hls_url(absolute, video_id, kind))
        return '\n'.join(output) + '\n'

    def _rewrite_m3u8_tag(self, line, base_url, video_id=''):
        def replace_uri(match):
            raw_url = match.group(1)
            absolute = urljoin(base_url, raw_url)
            proxied = self._cache_hls_url(absolute, video_id, 'media')
            return f'URI="{proxied}"'
        return re.sub(r'URI="([^"]+)"', replace_uri, line)

    def _proxy_hls(self, params):
        key = params.get('key') or ''
        item = self.hls_url_cache.get(key)
        if not item or item.get('expires', 0) < time.time():
            return [404, 'text/plain', 'HLS 缓存已过期']
        item['expires'] = time.time() + self._hls_ttl(item.get('kind'))
        target_url = item.get('url') or ''
        try:
            headers = self._hls_headers(target_url, item.get('kind'))
            response = self._cdn_get(target_url, headers=headers, stream=True, timeout=15)
            retried = False
            if item.get('kind') == 'media' and response.status_code == 403:
                retry_headers = self._hls_headers(target_url, 'media_retry')
                response.close()
                retried = True
                response = self._cdn_get(target_url, headers=retry_headers, stream=True, timeout=15)
            content_type = response.headers.get('content-type') or ''
            is_m3u8 = item.get('kind') in ('master', 'playlist') or 'mpegurl' in content_type.lower() or target_url.split('?')[0].endswith('.m3u8')
            if is_m3u8:
                text = response.text
                rewritten = self._rewrite_m3u8(text, target_url, item.get('video_id') or '')
                return [response.status_code, 'application/vnd.apple.mpegurl', rewritten, {'Content-Type': 'application/vnd.apple.mpegurl', 'Cache-Control': 'no-cache'}]
            resp_headers = {'Content-Type': content_type or 'application/octet-stream', 'Cache-Control': 'no-cache'}
            if response.headers.get('content-length'):
                resp_headers['Content-Length'] = response.headers.get('content-length')
            return [response.status_code, content_type or 'application/octet-stream', response.content, resp_headers]
        except Exception as e:
            debug_log('hls proxy error', {'key': key, 'error': repr(e)})
            return [500, 'text/plain', f'HLS 代理失败: {str(e)}']

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass