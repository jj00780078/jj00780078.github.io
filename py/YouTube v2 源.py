# -*- coding: utf-8 -*-
"""YouTube TVBox 源（InnerTube 协议）

数据通道：YouTube 官方客户端内部接口 youtubei/v1（WEB 客户端取列表/搜索/详情）。
播放通道：VISIONOS 取 HLS 清单（音画合流，最高 4K）为主线；ANDROID 取 itag18 直链
          为第二线（实测：新视频在 VISIONOS/VR 报“请登录确认不是机器人”时，
          ANDROID 仍直出明文直链且可 Range 实下）；ANDROID_VR 为第三线。
两条播放线均由站方直接下发带签名地址，无加密参数、无需解签。

分类以用户要的为主：动漫 / 短剧 / 电视剧 / 电影 / 新闻在前，其余首页 / Shorts / 音乐 / 影视 /
直播 / 游戏 / 播客 / 体育 / 时尚 / 学习在后；动漫、短剧、电影、新闻为站内搜索主题流。
登录（可选，不用个人 API Key，也不用在源里填密码）：ext 里给 cookie，即浏览器里
已登录账号的 YouTube Cookie（见使用说明，Cookie 只填在你自己手机的配置里，不要发给别人），
登录后首页分类里自动多出 订阅 / 历史 / 媒体库三项；不给 cookie 时这三项不出现，
其余公开分类与播放照常走匿名通道。
ext 可选：{"hl": "zh-CN", "gl": "US"} 语言与内容地区；{"cookie": "SID=...; SAPISID=...; ..."} 登录。
"""
import hashlib
import json
import re
import time
import urllib.request
import urllib.error

try:
    from base.spider import BaseSpider
except Exception:  # 无壳自检回退
    class BaseSpider:
        def __init__(self):
            pass


API = 'https://www.youtube.com/youtubei/v1/'
KEY_WEB = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
KEY_AND = 'AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w'
UA_WEB = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
UA_VIS = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
          '(KHTML, like Gecko) Version/18.0 Safari/605.1.15')
UA_VR = ('com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; '
         'eureka-user Build/SQ3A.220605.009.A1) gzip')
UA_AND = ('com.google.android.youtube/20.10.80 (Linux; U; Android 13; Pixel 7) gzip')

CLIENT_WEB = {'clientName': 'WEB', 'clientVersion': '2.20241127.01.00', 'userAgent': UA_WEB}
CLIENT_VIS = {'clientName': 'VISIONOS', 'clientVersion': '1.02', 'deviceMake': 'Apple',
              'deviceModel': 'Apple Vision Pro', 'userAgent': UA_VIS,
              'osName': 'visionOS', 'osVersion': '2.0'}
CLIENT_VR = {'clientName': 'ANDROID_VR', 'clientVersion': '1.65.10', 'deviceMake': 'Oculus',
             'deviceModel': 'Quest 3', 'androidSdkVersion': 32, 'userAgent': UA_VR,
             'osName': 'Android', 'osVersion': '12L'}
CLIENT_AND = {'clientName': 'ANDROID', 'clientVersion': '20.10.80', 'androidSdkVersion': 30,
              'userAgent': UA_AND, 'osName': 'Android', 'osVersion': '13'}
CLIENT_NUM = {'WEB': 1, 'VISIONOS': 101, 'ANDROID_VR': 28, 'ANDROID': 3}
CLIENT_KEY = {'WEB': KEY_WEB, 'VISIONOS': KEY_WEB, 'ANDROID_VR': KEY_AND, 'ANDROID': KEY_AND}
CLIENT_OBJ = {'WEB': CLIENT_WEB, 'VISIONOS': CLIENT_VIS, 'ANDROID_VR': CLIENT_VR, 'ANDROID': CLIENT_AND}
CLIENT_UA = {'WEB': UA_WEB, 'VISIONOS': UA_VIS, 'ANDROID_VR': UA_VR, 'ANDROID': UA_AND}

SHORTS_SP = 'EgIYAQ%3D%3D'  # 搜索过滤器：仅 Shorts

CLASSES = [
    {'type_id': 'preset:动漫', 'type_name': '动漫'},
    {'type_id': 'preset:短剧', 'type_name': '短剧'},
    {'type_id': 'preset:电视剧', 'type_name': '电视剧'},
    {'type_id': 'preset:电影', 'type_name': '电影'},
    {'type_id': 'preset:新闻', 'type_name': '新闻'},
    {'type_id': 'home', 'type_name': '首页'},
    {'type_id': 'shorts', 'type_name': 'Shorts'},
    {'type_id': 'channel:UC-9-kyTW8ZkZNDHQJ6FgpwQ', 'type_name': '音乐'},
    {'type_id': 'browse:FEstorefront', 'type_name': '影视'},
    {'type_id': 'channel:UC4R8DWoMoI7CAwX8_LjQHig', 'type_name': '直播'},
    {'type_id': 'channel:UCOpNcN46UbXVtpKMrmU4Abg', 'type_name': '游戏'},
    {'type_id': 'browse:FEpodcasts_destination|qgcCCAE%3D', 'type_name': '播客'},
    {'type_id': 'preset:体育', 'type_name': '体育'},
    {'type_id': 'preset:时尚', 'type_name': '时尚'},
    {'type_id': 'preset:学习', 'type_name': '学习'},
]
# 登录后才追加的分类（browseId 与 WEB browse 同路，无登录时返回空，故平时不列出）
LOGIN_CLASSES = [
    {'type_id': 'browse:FEsubscriptions', 'type_name': '订阅'},
    {'type_id': 'browse:FEhistory', 'type_name': '历史'},
    {'type_id': 'browse:FElibrary', 'type_name': '媒体库'},
]

VID_RE = re.compile(r'^[\w-]{11}$')
DUR_RE = re.compile(r'^\d{1,2}:\d{2}(:\d{2})?$')
VIDEO_KINDS = ('videoRenderer', 'gridVideoRenderer', 'compactVideoRenderer',
               'videoCardRenderer', 'reelItemRenderer', 'tileRenderer',
               'gridMovieRenderer', 'lockupViewModel')
SHORTS_KINDS = ('shortsLockupViewModel', 'reelItemRenderer')


def _txt(node):
    """InnerTube 文本节点 -> 字符串（simpleText / runs / content 三种形态）。"""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ''
    if node.get('simpleText'):
        return node['simpleText']
    if node.get('content'):
        return node['content']
    runs = node.get('runs')
    if isinstance(runs, list):
        return ''.join(r.get('text', '') for r in runs if isinstance(r, dict))
    return ''


def _walk(node):
    """深度优先遍历 JSON 树，逐个产出 dict 节点。"""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            for x in _walk(v):
                yield x
    elif isinstance(node, list):
        for i in node:
            for x in _walk(i):
                yield x


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self._state_ready = False

    # ---------- 基础 ----------
    def _lazy(self):
        if not self._state_ready:
            self.hl = 'zh-CN'
            self.gl = 'US'
            self.cookie = ''
            self._streams = {}   # stream_key -> {'tokens': {page: token|None}, 'mode': {...}}
            self._state_ready = True

    def init(self, extend=''):
        self._lazy()
        try:
            ext = json.loads(extend) if isinstance(extend, str) and extend else (extend or {})
        except Exception:
            ext = {}
        if isinstance(ext, dict):
            if ext.get('hl'):
                self.hl = str(ext['hl'])
            if ext.get('gl'):
                self.gl = str(ext['gl'])
            ck = ext.get('cookie') or ext.get('cookies') or ''
            if isinstance(ck, dict):
                ck = '; '.join('%s=%s' % (k, v) for k, v in ck.items())
            if isinstance(ck, str) and ck.strip():
                # 只接受 Cookie 头形态，丢掉可能混进来的换行与 Cookie: 前缀
                ck = ck.strip().replace('\n', ' ').replace('\r', ' ')
                if ck.lower().startswith('cookie:'):
                    ck = ck[7:].strip()
                self.cookie = ck
        return ''

    def _auth_headers(self):
        # 仅 WEB 列表/搜索/详情通道带登录态；播放双线（VISIONOS/VR）保持匿名，
        # 避免换客户端后签名地址与登录态绑定不一致导致播不动。
        headers = {}
        if getattr(self, 'cookie', ''):
            headers['Cookie'] = self.cookie
            m = re.search(r'(?:^|;\s*)SAPISID=([^;\s]+)', self.cookie)
            if m:
                ts = str(int(time.time()))
                digest = hashlib.sha1(('%s %s https://www.youtube.com' % (ts, m.group(1))).encode()).hexdigest()
                headers['Authorization'] = 'SAPISIDHASH %s_%s' % (ts, digest)
                headers['Origin'] = 'https://www.youtube.com'
                headers['X-Goog-AuthUser'] = '0'
        return headers

    def getName(self):
        return 'YouTube'

    def destroy(self):
        return ''

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ---------- 网络 ----------
    def _innertube(self, path, client_name, extra=None, tries=2, auth='auto'):
        self._lazy()
        client = dict(CLIENT_OBJ[client_name])
        client['hl'] = self.hl
        client['gl'] = self.gl
        body = {'context': {'client': client}}
        if extra:
            body.update(extra)
        data = json.dumps(body).encode('utf-8')
        url = '%s%s?key=%s&prettyPrint=false' % (API, path, CLIENT_KEY[client_name])
        last = None
        for _ in range(tries):
            hdrs = {
                'Content-Type': 'application/json',
                'User-Agent': client.get('userAgent', UA_WEB),
                'X-YouTube-Client-Name': str(CLIENT_NUM[client_name]),
                'X-YouTube-Client-Version': client.get('clientVersion', ''),
            }
            if auth is True or (auth == 'auto' and client_name == 'WEB'):
                hdrs.update(self._auth_headers())
            req = urllib.request.Request(url, data=data, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode('utf-8', 'ignore'))
            except Exception as e:
                last = e
                time.sleep(0.6)
        if last:
            raise last
        return {}

    def _player(self, vid, client_name, auth='auto'):
        return self._innertube('player', client_name, {
            'videoId': vid,
            'playbackContext': {'contentPlaybackContext': {'signatureTimestamp': 20073}},
        }, auth=auth)

    def _usable_play(self, r, client_name):
        sd = (r or {}).get('streamingData') or {}
        hls = sd.get('hlsManifestUrl') or ''
        if hls:
            return hls, {'User-Agent': CLIENT_UA[client_name]}
        fmts = [f for f in (sd.get('formats') or []) if f.get('url')]
        fmts.sort(key=lambda f: (0 if f.get('itag') == 22 else 1 if f.get('itag') == 18 else 2))
        if fmts:
            return fmts[0]['url'], {'User-Agent': CLIENT_UA[client_name]}
        hls = sd.get('hlsManifestUrl') or ''
        if hls:
            return hls, {'User-Agent': CLIENT_UA[client_name]}
        return None

    # ---------- 条目提取 ----------
    def _thumb(self, sources):
        best, bw = '', -1
        for t in sources or []:
            if isinstance(t, dict) and t.get('url'):
                w = t.get('width', 0) or 0
                if w >= bw:
                    best, bw = t['url'], w
        return best

    def _subtree_vid(self, sub):
        for n in _walk(sub):
            we = n.get('watchEndpoint')
            if isinstance(we, dict) and VID_RE.match(str(we.get('videoId', ''))):
                return we['videoId']
            ct = n.get('continuationCommand')
            if isinstance(ct, dict):
                pass
            for k in ('videoId', 'contentId'):
                v = n.get(k)
                if isinstance(v, str) and VID_RE.match(v):
                    return v
        return ''

    def _item_from(self, kind, sub):
        vid = ''
        title = ''
        pic = ''
        remarks = ''
        if kind == 'lockupViewModel':
            if sub.get('contentType') not in ('LOCKUP_CONTENT_TYPE_VIDEO', None):
                # 播放列表/频道等非视频 lockup 不进列表；影视分类的电影 lockup 无 contentType 时放行靠 videoId 形态校验
                if sub.get('contentType'):
                    return None
            vid = sub.get('contentId') or ''
            if not (isinstance(vid, str) and VID_RE.match(vid)):
                return None
            meta = (sub.get('metadata') or {}).get('lockupMetadataViewModel') or {}
            title = _txt((meta.get('title') or {}))
            img = sub.get('contentImage') or {}
            pics = []
            tv = img.get('thumbnailViewModel') or {}
            if tv:
                pics = ((tv.get('image') or {}).get('sources')) or []
            if not pics:
                pv = (img.get('collectionThumbnailViewModel') or {}).get('primaryThumbnail') or {}
                pics = (((pv.get('thumbnailViewModel') or {}).get('image') or {}).get('sources')) or []
            pic = self._thumb(pics)
            # 时长徽标在 contentImage 的 overlays 里
            for n in _walk(img):
                t = _txt(n.get('text') if isinstance(n, dict) else None)
                if t and DUR_RE.match(t.strip()):
                    remarks = t.strip()
                    break
            if not remarks:
                rows = meta.get('metadataRows') or []
                parts = []
                for row in rows:
                    for p in (row.get('metadataParts') or []):
                        parts.append(_txt(p.get('text') or {}))
                remarks = ' · '.join(x for x in parts if x)[:40]
        elif kind == 'shortsLockupViewModel':
            vid = self._subtree_vid(sub)
            if not vid:
                return None
            title = sub.get('accessibilityText') or ''
            title = re.sub(r'\s*[-–]\s*(play Short|播放 Short).*$', '', title).strip()
            if not title:
                title = _txt(sub.get('title') or {})
            pic = self._thumb(((sub.get('thumbnail') or {}).get('sources')) or [])
            remarks = 'Shorts'
        else:
            vid = sub.get('videoId') or self._subtree_vid(sub)
            if not (isinstance(vid, str) and VID_RE.match(vid)):
                return None
            title = _txt(sub.get('title') or {}) or _txt(sub.get('headline') or {})
            pic = self._thumb(((sub.get('thumbnail') or {}).get('thumbnails')) or [])
            lt = _txt(sub.get('lengthText') or {})
            if lt:
                remarks = lt
            badges = json.dumps(sub.get('badges') or [], ensure_ascii=False)
            owner = _txt(sub.get('ownerText') or {})
            vc = _txt(sub.get('viewCountText') or {}) or _txt(sub.get('shortViewCountText') or {})
            if 'LIVE' in badges or '直播' in badges or '正在观看' in vc:
                remarks = '直播'
            elif not remarks and (vc or owner):
                remarks = ' · '.join(x for x in (owner, vc) if x)[:40]
        if not vid or not title:
            return None
        if not pic:
            pic = 'https://i.ytimg.com/vi/%s/hqdefault.jpg' % vid
        return {'vod_id': vid, 'vod_name': title.strip(), 'vod_pic': pic,
                'vod_remarks': remarks}

    def _harvest(self, data, kinds=VIDEO_KINDS):
        out, seen = [], set()

        def rec(node):
            if isinstance(node, dict):
                for k in kinds:
                    if k in node and isinstance(node[k], dict):
                        item = self._item_from(k, node[k])
                        if item and item['vod_id'] not in seen:
                            seen.add(item['vod_id'])
                            out.append(item)
                for v in node.values():
                    rec(v)
            elif isinstance(node, list):
                for i in node:
                    rec(i)

        rec(data)
        return out

    def _continuation(self, data):
        tokens = []
        for n in _walk(data):
            cir = n.get('continuationItemRenderer')
            if isinstance(cir, dict):
                tok = (((cir.get('continuationEndpoint') or {}).get('continuationCommand') or {}).get('token'))
                if tok:
                    tokens.append(tok)
        if tokens:
            return tokens[-1]
        for n in _walk(data):
            cc = n.get('continuationCommand')
            if isinstance(cc, dict) and cc.get('token'):
                tokens.append(cc['token'])
        return tokens[-1] if tokens else ''

    # ---------- 数据流（分页） ----------
    def _stream_state(self, key, mode):
        st = self._streams.get(key)
        if not st:
            st = {'mode': mode, 'tokens': {1: None}, 'seen': set()}
            self._streams[key] = st
        return st

    def _fetch_page(self, key, mode, pg):
        """mode: ('browse', browseId, params) / ('search', query, sp) / ('shorts',) / ('home',)"""
        self._lazy()
        st = self._stream_state(key, mode)
        mode = st['mode']
        pg = int(pg)
        if pg == 1:
            # 同一流内重复进首頁时清掉已见集，否则第二次进分类只剩去重后的零星条目
            st['seen'] = set()
        token = st['tokens'].get(pg)
        if pg > 1 and token is None and pg not in st['tokens']:
            return [], False
        kind = mode[0]
        if kind == 'home':
            extra = {'browseId': 'FEwhat_to_watch'}
            if token:
                extra = {'continuation': token}
            data = self._innertube('browse', 'WEB', extra)
            items = self._harvest(data)
            if not items and pg == 1:
                # 个性化首页对无身份请求可能为空：回退到热门搜索流，保证分类不空
                st['mode'] = ('search', '热门', '')
                return self._fetch_page(key, st['mode'], 1)
        elif kind == 'browse':
            extra = {'browseId': mode[1]}
            if len(mode) > 2 and mode[2]:
                extra['params'] = mode[2]
            if token:
                extra = {'continuation': token}
            data = self._innertube('browse', 'WEB', extra)
            items = self._harvest(data)
            if kind == 'browse' and mode[1].startswith('FEstorefront'):
                items = self._harvest(data, VIDEO_KINDS)
        elif kind in ('search', 'preset'):
            extra = {'query': mode[1]}
            if len(mode) > 2 and mode[2]:
                extra['params'] = mode[2]
            if token:
                extra = {'continuation': token}
            data = self._innertube('search', 'WEB', extra)
            items = self._harvest(data)
        elif kind == 'shorts':
            extra = {'query': '热门', 'params': SHORTS_SP}
            if token:
                extra = {'continuation': token}
            data = self._innertube('search', 'WEB', extra)
            items = self._harvest(data, SHORTS_KINDS)
            if not items:
                items = [it for it in self._harvest(data) if it.get('vod_remarks') == 'Shorts']
        else:
            return [], False
        nxt = self._continuation(data)
        if nxt:
            st['tokens'][pg + 1] = nxt
        # 站方流在翻页时偶有条目漂移/重出，按流去重保证不给用户重复条目
        fresh = [it for it in items if it['vod_id'] not in st['seen']]
        st['seen'].update(it['vod_id'] for it in fresh)
        return fresh, bool(nxt)

    def _page_result(self, key, mode, pg):
        try:
            items, has_next = self._fetch_page(key, mode, pg)
        except Exception:
            items, has_next = [], False
        return {'list': items, 'page': int(pg), 'pagecount': 9999 if has_next else int(pg),
                'limit': len(items), 'total': 999999 if has_next else len(items)}

    def _mode_of(self, tid):
        if tid == 'home':
            return ('home',)
        if tid == 'shorts':
            return ('shorts',)
        if tid.startswith('channel:'):
            return ('browse', tid.split(':', 1)[1], '')
        if tid.startswith('browse:'):
            rest = tid.split(':', 1)[1]
            if '|' in rest:
                bid, params = rest.split('|', 1)
            else:
                bid, params = rest, ''
            return ('browse', bid, params)
        if tid.startswith('preset:'):
            return ('search', tid.split(':', 1)[1], '')
        return ('search', tid, '')

    # ---------- 壳接口 ----------
    def homeContent(self, filter=None):
        self._lazy()
        classes = list(CLASSES)
        if getattr(self, 'cookie', ''):
            classes = classes[:5] + list(LOGIN_CLASSES) + classes[5:]
        return {'class': classes, 'filters': {}}

    def homeVideoContent(self):
        return self._page_result('home', ('home',), 1)

    def categoryContent(self, tid, pg, filter=None, extend=None):
        return self._page_result('cat:' + str(tid), self._mode_of(str(tid)), pg)

    def searchContent(self, key, quick, pg='1'):
        return self._page_result('search:' + str(key), ('search', str(key), ''), pg)

    def detailContent(self, ids):
        self._lazy()
        vid = str(ids[0]) if ids else ''
        vod = {'vod_id': vid, 'vod_name': vid, 'vod_pic': 'https://i.ytimg.com/vi/%s/hqdefault.jpg' % vid,
               'vod_remarks': '', 'vod_actor': '', 'vod_content': '', 'type_name': 'YouTube'}
        try:
            r = self._player(vid, 'WEB')
            vd = r.get('videoDetails') or {}
            if vd:
                vod['vod_name'] = vd.get('title') or vid
                vod['vod_actor'] = vd.get('author') or ''
                vod['vod_content'] = (vd.get('shortDescription') or '')[:800]
                thumbs = ((vd.get('thumbnail') or {}).get('thumbnails')) or []
                if thumbs:
                    vod['vod_pic'] = self._thumb(thumbs)
                ls = int(vd.get('lengthSeconds') or 0)
                if ls:
                    vod['vod_remarks'] = '%d:%02d' % (ls // 60, ls % 60)
                if vd.get('isLiveContent'):
                    vod['vod_remarks'] = '直播'
        except Exception:
            pass
        if vod['vod_name'] == vid:
            try:
                req = urllib.request.Request(
                    'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=%s&format=json' % vid,
                    headers={'User-Agent': UA_WEB})
                with urllib.request.urlopen(req, timeout=20) as r:
                    oe = json.loads(r.read().decode('utf-8', 'ignore'))
                vod['vod_name'] = oe.get('title') or vid
                vod['vod_actor'] = oe.get('author_name') or ''
                if oe.get('thumbnail_url'):
                    vod['vod_pic'] = oe['thumbnail_url']
            except Exception:
                pass
        vod['vod_play_from'] = 'HLS高清$$$360p直链'
        vod['vod_play_url'] = '正片$%s$$$正片$%s' % (vid, vid)
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        self._lazy()
        vid = str(id)
        # 选 HLS 线先试 HLS，选 360p 线先试直链；任一线失败都向其余线回落，
        # 这样 VISIONOS 被机器人校验挡住的新视频仍能经 ANDROID 直链播出。
        if flag == '360p直链':
            order = ['ANDROID', 'ANDROID_VR', 'VISIONOS']
        else:
            order = ['VISIONOS', 'ANDROID', 'ANDROID_VR']
        for auth in ('auto', True):
            if auth is True and not getattr(self, 'cookie', ''):
                break
            for client_name in order:
                try:
                    r = self._player(vid, client_name, auth=auth)
                except Exception:
                    continue
                got = self._usable_play(r, client_name)
                if got:
                    url, header = got
                    return {'parse': 0, 'playUrl': '', 'url': url, 'header': header}
        return {'parse': 0, 'playUrl': '', 'url': '', 'header': {}}


    # ── 全协议补齐(2026-10-23, 原业务逻辑未动) ──
    def getDependence(self):
        return []

    def localProxy(self, param=None):
        # 全协议四项式 [status, mime, body, headers]; 本源原未走 proxy:// 链,
        # 此为契约补齐: 直取目标字节回传(带浏览器 UA 与目标站 Referer)。
        import urllib.parse as _up
        import urllib.request as _ur
        try:
            p = param
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except Exception:
                    p = dict(_up.parse_qsl(p))
            if not isinstance(p, dict):
                p = {}
            target = p.get("url") or p.get("u") or ""
            if isinstance(target, list):
                target = target[0] if target else ""
            target = _up.unquote(str(target or "").strip())
            if not target.startswith("http"):
                return [404, "text/plain", b"bad url", {}]
            _o = _up.urlparse(target)
            _req = _ur.Request(target, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Referer": "%s://%s/" % (_o.scheme, _o.netloc)})
            with _ur.urlopen(_req, timeout=20) as _r:
                return [_r.status, _r.headers.get("Content-Type") or "application/octet-stream", _r.read(), {}]
        except Exception:
            return [502, "text/plain", b"proxy error", {}]

    def action(self, action=None):
        return {}

