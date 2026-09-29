import re, requests, json, time, hashlib
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from base.spider import Spider

HOST = 'https://yun2s2lxsduo22.top'
UA = 'Mozilla/5.0'
WS = 'yda81x6d9ad3c4s'
XC = '8f3d2a1c7b6e5d4c9a0b1f2e3d4c5b6a'
F = 'WF-9e14d752872961ca1f5f125a6607c2712535b8d8b5c1294423c2da8436a41000'
SK = 'WEB-df5526941b0e3165d0a8485119ca3628b45f2b4a5c4b888bf01645a7060e1638'
PKG = 'com.web.player.6c3b998c'
TYPES = {'1': '电影', '2': '剧集', '3': '动漫', '4': '综艺'}

def _sign(ts):
    s = 'finger=' + F + '&id=' + PKG + '&nonce=' + '0' * 32 + '&sk=' + SK + '&time=' + str(ts) + '&v=1'
    return hashlib.sha256(s.encode()).hexdigest().upper()

def _vint(n):
    b = bytearray()
    while True:
        x = n & 0x7f
        n >>= 7
        if n:
            b.append(x | 0x80)
        else:
            b.append(x)
            return bytes(b)

def _pb(url, vf, ts):
    u = url.encode()
    v = vf.encode()
    return b'\x0a' + _vint(len(u)) + u + b'\x12' + _vint(len(v)) + v + b'\x18' + _vint(ts) + b'\x22\x20' + b'0' * 32 + b'\x2a\x40' + _sign(ts).encode() + b'\x32\x17' + PKG.encode() + b'\x38\x01'

class Spider(Spider):
    def init(self, extend=""):
        self.s = requests.Session()
        self.s.headers.update({'web-sign': WS, 'X-Client': XC, 'User-Agent': UA})
        self._lcache = {}
        self._lts = 0
        self._cats = {}
        try:
            self.s.post(HOST + '/api.php/web/account/login', json={'username': 'admin', 'password': '123456'}, timeout=10, verify=False)
        except:
            pass

    def _probe(self, pid, vf):
        try:
            ck = self.s.cookies.get('yunduo_web_session', '')
            r = requests.post(HOST + '/api.php/web/decode/url', data=_pb(pid, vf, int(time.time() * 1000)), headers={'Content-Type': 'application/x-protobuf', 'User-Agent': UA, 'web-sign': WS, 'X-Client': XC, 'Cookie': 'yunduo_web_session=' + ck}, timeout=8, verify=False)
            return bool(re.search(r'https?://[^\s\x00-\x1f"\']+', r.text))
        except:
            return False

    def _norm(self, v):
        if isinstance(v, list):
            return ','.join([str(x) for x in v])
        return str(v or '')

    def _items(self, lst):
        out = []
        for v in lst:
            out.append({'vod_id': str(v.get('vod_id')), 'vod_name': v.get('vod_name'), 'vod_pic': v.get('vod_pic', ''), 'vod_remarks': v.get('vod_remarks', '')})
        return out

    def homeContent(self, filter=False):
        r = self.s.get(HOST + '/api.php/web/index/home', timeout=15, verify=False)
        d = r.json().get('data', {})
        cats = [{'type_id': str(c['type_id']), 'type_name': c['type_name']} for c in d.get('categories', [])]
        self._cats = {str(c['type_id']): c['type_name'] for c in d.get('categories', [])}
        vids = []
        for c in d.get('categories', []):
            for v in c.get('videos', [])[:6]:
                vids.append({'vod_id': str(v.get('vod_id')), 'vod_name': v.get('vod_name'), 'vod_pic': v.get('vod_pic', ''), 'vod_remarks': v.get('vod_remarks', '')})
        return {'class': cats, 'list': vids}

    def homeVideoContent(self):
        r = self.s.get(HOST + '/api.php/web/filter/vod?type_name=' + quote('电影') + '&page=1&sort=hits', timeout=15, verify=False)
        return {'list': self._items(r.json().get('data', []))}

    def categoryContent(self, tid, pg, filter=False, extend=""):
        name = self._cats.get(str(tid), TYPES.get(str(tid), '电影'))
        r = self.s.get(HOST + '/api.php/web/filter/vod?type_name=' + quote(name) + '&page=' + str(pg) + '&sort=hits', timeout=15, verify=False)
        return {'list': self._items(r.json().get('data', [])), 'page': int(pg), 'pagecount': 999, 'limit': 24, 'total': 99999}

    def detailContent(self, ids):
        vid = str(ids[0])
        r = self.s.get(HOST + '/api.php/web/vod/get_detail?vod_id=' + vid, timeout=15, verify=False)
        d = r.json().get('data', [])
        if not d:
            return {'list': []}
        v = d[0]
        pfs = v.get('vod_play_from', '').split('$$$')
        segs = v.get('vod_play_url', '').split('$$$')
        if len(pfs) > 1 and len(pfs) == len(segs):
            now = time.time()
            if now - self._lts > 180 or vid not in self._lcache:
                ok = {}
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = {}
                    for i, src in enumerate(pfs):
                        sg = segs[i] if i < len(segs) else ''
                        pid0 = sg.split('#')[0].split('$')[1] if '$' in sg else ''
                        if pid0:
                            futs[ex.submit(self._probe, pid0, src)] = i
                    for f in futs:
                        ok[futs[f]] = f.result()
                order = sorted(range(len(pfs)), key=lambda i: (not ok.get(i, False), i))
                self._lcache[vid] = order
                self._lts = now
            else:
                order = self._lcache[vid]
            pfs = [pfs[i] for i in order]
            segs = [segs[i] for i in order]
        return {'list': [{'vod_id': vid, 'vod_name': v.get('vod_name'), 'vod_pic': v.get('vod_pic', ''), 'vod_remarks': self._norm(v.get('vod_remarks')), 'vod_year': self._norm(v.get('vod_year')), 'vod_area': self._norm(v.get('vod_area')), 'vod_director': self._norm(v.get('vod_director')), 'vod_actor': self._norm(v.get('vod_actor')), 'vod_content': re.sub(r'<[^>]+>', '', self._norm(v.get('vod_content'))), 'vod_play_from': '$$$'.join(pfs), 'vod_play_url': '$$$'.join(segs)}]}

    def searchContent(self, key, quick=False):
        r = self.s.get(HOST + '/api.php/web/search/index?wd=' + quote(key) + '&page=1&limit=15', timeout=15, verify=False)
        return {'list': self._items(r.json().get('data', []))}

    def playerContent(self, flag, id, vipFlags):
        vf = flag if flag and flag != '线路' else (id.split('-')[0] if '-' in id else flag)
        if vf == 'qqqq':
            vf = 'BBA'
        u = ''
        for _ in range(2):
            try:
                r = self.s.post(HOST + '/api.php/web/decode/url', data=_pb(id, vf, int(time.time() * 1000)), headers={'Content-Type': 'application/x-protobuf'}, timeout=15, verify=False)
                m = re.search(r'https?://[^\s\x00-\x1f"\']+', r.text)
                u = m.group(0) if m else ''
                if u:
                    break
            except:
                break
        if not u:
            return {'parse': 0, 'url': ''}
        try:
            r2 = requests.get(u, headers={'User-Agent': UA}, timeout=10, verify=False)
            if r2.status_code == 200:
                ct = r2.headers.get('Content-Type', '')
                if 'mpegurl' in ct or 'm3u8' in ct or 'mp4' in ct or 'octet-stream' in ct or r2.text.startswith('#EXTM3U'):
                    u = r2.url
        except:
            pass
        if 'quark.cn' in u:
            return {'parse': 0, 'url': u, 'header': {'Referer': 'https://pan.quark.cn/', 'User-Agent': UA}}
        if 'mgtv.com' in u:
            return {'parse': 0, 'url': u, 'header': {'User-Agent': UA}}
        return {'parse': 0, 'url': u}

    def localProxy(self, param):
        return [200, 'text/plain', '']

    def _pagecount(self):
        return 999

    def _get(self, url):
        return self.s.get(url, timeout=15, verify=False).text