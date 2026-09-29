# -*- coding: utf-8 -*-
# ============ 看客TV源 v1.1 (71us模板v7.5套写) | 2026-09-10 ============
# v1.1: 分类动态化(Category接口) + 类型/年份/地区/排序筛选(flitter) + 翻页缓存预取 + 详情缓存 + UA净化
# 站点: 看客APK com.izpetb.owx (com.shenma.tvlauncher) | 密钥体系全解档案: /sdcard/破解/kanke/KEYCHAIN.md
# 密钥链: azapp1.json(COS)→baseUrl → set.php → miyao/rck/pgdz (init自动刷新, 失效可重跑)
# 接口: {pgdz}/api.php/localhost/(So搜索 | vod列表/详情); 列表/搜索/player 响应 RC4(miyao) 解密
# 播放: POST {curl}/Client{N}/?url={hex} (form: app=10000&key=RC4("&account=..&series=剧名-集名&edition=2.9", rck))
#       → RC4(miyao) → {"url":m3u8直链, "UserAgent":UA, "Client":N}
# 母版: /sdcard/破解/参考样本/71us模板v7.5.py (md5 a0ca1aaa) | 交付: py_compile+555契约+模拟T4全链已过
import sys, re, json, time, base64, hashlib, threading, http.server, socket, struct
from urllib.parse import urljoin, quote, unquote
from concurrent.futures import ThreadPoolExecutor
import requests

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

# ============ ★ CONFIG ============
HOSTS = ['http://43.248.117.149:1234']  # ★ 内容服务器(pgdz兜底, init自动刷新; 失效重跑引导链)
CURL = 'http://43.248.117.45:99'  # ★ 取流服务器(兜底, init自动刷新)
APPJSON = 'https://app-1361125462.cos.ap-guangzhou.myqcloud.com/azapp1.json'  # ★ 引导入口
UA = 'okhttp/4.9.0'  # ★ 站方API UA
CATEGORIES = {'movie': '电影', 'tvplay': '电视剧', 'tvshow': '综艺', 'comic': '动漫', 'oumeiju': '海外剧', 'hanguoju': '4K', 'movie_4k': '少儿', 'movie_ZB': '同步课堂'}
PK = '520720ygq'  # ★ miyao兜底(init刷新)
RCK = 'GN8ZGa4DmaHQrHhSTyQ3FwnhCQt68EXQ'  # ★ rck兜底(init刷新)
REFERER = ''  # ★ 播放/资源防盗链Referer(空=用self.base)
PIC_REFERER = ''  # ★ 图片防盗链Referer(空=无)
FD_ZONE = 0  # ★ 分片区段(71us .fd协议用, 无则0)
PROBE = 0  # ★ 详情多线路实测排序开关 1/0 (本链取流即验, 无需)
SITE_KEY = 'kanke'  # ★ 壳源标识(海阔setVideoFlags回调时上报, 调试多源用)
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'  # ★ isVideoFormat判定扩展名(竖线分隔)
MAX_PAGE = 500  # ★ 分页上限防预加载风暴

# ============ AES 纯Python引擎(Crypto不可用时降级) ============
SBOX = [99, 124, 119, 123, 242, 107, 111, 197, 48, 1, 103, 43, 254, 215, 171, 118, 202, 130, 201, 125, 250, 89, 71, 240, 173, 212, 162, 175, 156, 164, 114, 192, 183, 253, 147, 38, 54, 63, 247, 204, 52, 165, 229, 241, 113, 216, 49, 21, 4, 199, 35, 195, 24, 150, 5, 154, 7, 18, 128, 226, 235, 39, 178, 117, 9, 131, 44, 26, 27, 110, 90, 160, 82, 59, 214, 179, 41, 227, 47, 132, 83, 209, 0, 237, 32, 252, 177, 91, 106, 203, 190, 57, 74, 76, 88, 207, 208, 239, 170, 251, 67, 77, 51, 133, 69, 249, 2, 127, 80, 60, 159, 168, 81, 163, 64, 143, 146, 157, 56, 245, 188, 182, 218, 33, 16, 255, 243, 210, 205, 12, 19, 236, 95, 151, 68, 23, 196, 167, 126, 61, 100, 93, 25, 115, 96, 129, 79, 220, 34, 42, 144, 136, 70, 238, 184, 20, 222, 94, 11, 219, 224, 50, 58, 10, 73, 6, 36, 92, 194, 211, 172, 98, 145, 149, 228, 121, 231, 200, 55, 109, 141, 213, 78, 169, 108, 86, 244, 234, 101, 122, 174, 8, 186, 120, 37, 46, 28, 166, 180, 198, 232, 221, 116, 31, 75, 189, 139, 138, 112, 62, 181, 102, 72, 3, 246, 14, 97, 53, 87, 185, 134, 193, 29, 158, 225, 248, 152, 17, 105, 217, 142, 148, 155, 30, 135, 233, 206, 85, 40, 223, 140, 161, 137, 13, 191, 230, 66, 104, 65, 153, 45, 15, 176, 84, 187, 22]
IS = [0] * 256
for _i, _v in enumerate(SBOX):
    IS[_v] = _i
RCON = [1, 2, 4, 8, 16, 32, 64, 128, 27, 54, 108, 216, 171, 77]
G2 = [0] * 256
G3 = [0] * 256
for _i in range(256):
    _t = _i << 1
    if _i & 128:
        _t ^= 0x11b
    G2[_i] = _t
    G3[_i] = G2[_i] ^ _i


def _ke(k):
    nk = len(k) // 4
    nr = nk + 6
    w = [list(k[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = w[i - 1][:]
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w


def _enc(b, w):
    s = [[b[r + 4 * c] for c in range(4)] for r in range(4)]
    def add(r):
        for i in range(4):
            for j in range(4):
                s[i][j] ^= w[r * 4 + j][i]
    def sub():
        for i in range(4):
            for j in range(4):
                s[i][j] = SBOX[s[i][j]]
    def sh():
        for r in range(1, 4):
            s[r] = s[r][r:] + s[r][:r]
    def mx():
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = G2[a[0]] ^ G3[a[1]] ^ a[2] ^ a[3]
            s[1][c] = a[0] ^ G2[a[1]] ^ G3[a[2]] ^ a[3]
            s[2][c] = a[0] ^ a[1] ^ G2[a[2]] ^ G3[a[3]]
            s[3][c] = G3[a[0]] ^ a[1] ^ a[2] ^ G2[a[3]]
    add(0)
    nr = len(w) // 4 - 1
    for rnd in range(1, nr):
        sub()
        sh()
        mx()
        add(rnd)
    sub()
    sh()
    add(nr)
    return bytes(s[r][c] for c in range(4) for r in range(4))


def _gm(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        a = (a << 1) ^ 0x11b if a & 0x80 else a << 1
        b >>= 1
    return p & 0xff


def _dec(b, w):
    s = [[b[r + 4 * c] for c in range(4)] for r in range(4)]
    def add(r):
        for i in range(4):
            for j in range(4):
                s[i][j] ^= w[r * 4 + j][i]
    def isub():
        for i in range(4):
            for j in range(4):
                s[i][j] = IS[s[i][j]]
    def ish():
        for r in range(1, 4):
            s[r] = s[r][-r:] + s[r][:-r]
    def imx():
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = _gm(a[0], 14) ^ _gm(a[1], 11) ^ _gm(a[2], 13) ^ _gm(a[3], 9)
            s[1][c] = _gm(a[0], 9) ^ _gm(a[1], 14) ^ _gm(a[2], 11) ^ _gm(a[3], 13)
            s[2][c] = _gm(a[0], 13) ^ _gm(a[1], 9) ^ _gm(a[2], 14) ^ _gm(a[3], 11)
            s[3][c] = _gm(a[0], 11) ^ _gm(a[1], 13) ^ _gm(a[2], 9) ^ _gm(a[3], 14)
    nr = len(w) // 4 - 1
    add(nr)
    for rnd in range(nr - 1, 0, -1):
        ish()
        isub()
        add(rnd)
        imx()
    ish()
    isub()
    add(0)
    return bytes(s[r][c] for c in range(4) for r in range(4))


def aes_ecb(data, key, mode=1):
    w = _ke(key)
    out = b''
    if mode:
        pad = 16 - len(data) % 16
        data += bytes([pad]) * pad
        for i in range(0, len(data), 16):
            out += _enc(data[i:i + 16], w)
    else:
        for i in range(0, len(data), 16):
            out += _dec(data[i:i + 16], w)
        if out and 0 < out[-1] <= 16:
            out = out[:-out[-1]]
    return out


def aes_cbc(data, key, iv, enc=1):
    w = _ke(key)
    out = b''
    prev = iv
    if enc:
        pad = 16 - len(data) % 16
        data += bytes([pad]) * pad
        for i in range(0, len(data), 16):
            blk = bytes(data[i + j] ^ prev[j] for j in range(16))
            ct = _enc(blk, w)
            out += ct
            prev = ct
    else:
        for i in range(0, len(data), 16):
            blk = _dec(data[i:i + 16], w)
            out += bytes(blk[j] ^ prev[j] for j in range(16))
            prev = data[i:i + 16]
        if out and 0 < out[-1] <= 16:
            out = out[:-out[-1]]
    return out


# ============ RC4 引擎(本链核心: miyao/rck 全用途) ============
def _rc4(data, key):
    S = list(range(256))
    j = 0
    k = key.encode()
    for i in range(256):
        j = (j + S[i] + k[i % len(k)]) & 255
        S[i], S[j] = S[j], S[i]
    x = y = 0
    out = bytearray()
    for b in data:
        x = (x + 1) & 255
        y = (y + S[x]) & 255
        S[x], S[y] = S[y], S[x]
        out.append(b ^ S[(S[x] + S[y]) & 255])
    return bytes(out)


def rcd(s, key):
    try:
        return _rc4(bytes.fromhex(str(s).strip()), key).decode('utf-8', 'replace')
    except Exception:
        return ''


def rce(text, key):
    return _rc4(text.encode(), key).hex()


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')
        self.pgdz = HOSTS[0].rstrip('/')  # 内容服务器
        self.curl = CURL.rstrip('/')  # 取流服务器
        self.ua = UA
        self.pk = PK
        self.miyao = PK  # 主密钥(解列表/搜索/player/取流响应)
        self.rck = RCK  # 签名密钥(取流 key 参数)
        self.client = 1  # 取流 Client 编号
        self.ref = REFERER or self.base
        self.types = dict(CATEGORIES)
        self.filters = {}  # ★ {'1':[{'key':'class','name':'类型','value':[{'n':'剧情','v':'剧情'}]}]}
        self._pc = {}  # 线路probe缓存 {md5:[ts,froms,urls]}
        self._srv = None  # 本地代理线程(延迟启动)
        self._sv = {}  # 播放上下文 {hex:(剧名,集名)}
        self.sess = requests.Session()  # keep-alive 双保险
        self._ck = {}  # 翻页缓存 {(tid,pg,exs):(ts,data)}
        self._dk = {}  # 详情缓存 {vid:(ts,resp)}
        self._pfs = set()  # 预取在途
        self._ld()  # 引导链刷新(azapp1.json→set.php)
        self._lcat()  # 分类动态刷新(Category接口)
        self._lfil()  # 筛选动态刷新(flitter: 类型/年份/地区/排序)

    def _ld(self):
        try:
            r = self.fetch(APPJSON, headers={'User-Agent': self.ua}, timeout=8000)
            b = (r.text if hasattr(r, 'text') else str(r)).strip()
            if b and ':' in b and len(b) < 60 and ' ' not in b:
                self.curl = ('http://' + b).rstrip('/')
        except Exception:
            pass
        try:
            r2 = self.fetch(self.curl + '/extend/api/set.php?type=set', headers={'User-Agent': self.ua}, timeout=8000)
            j = json.loads(r2.text if hasattr(r2, 'text') else str(r2))
            j = j.get('data') or {}
            if j.get('miyao'):
                self.miyao = j['miyao']
            if j.get('rck'):
                self.rck = j['rck']
            if j.get('pgdz'):
                self.pgdz = j['pgdz'].rstrip('/')
        except Exception:
            pass

    def _lcat(self):
        try:
            h = self._get(self.pgdz + '/api.php/localhost/Category', timeout=8000)
            arr = []
            if h:
                t = h.strip()
                try:
                    a = json.loads(t)
                    arr = a if isinstance(a, list) else []
                except Exception:
                    a = json.loads(rcd(t, self.miyao))
                    arr = a if isinstance(a, list) else []
            nt = {}
            for x in arr:
                if not isinstance(x, dict):
                    continue
                en = str(x.get('type_en') or '').strip()
                nm = str(x.get('type_name') or '').strip()
                if en and nm and str(x.get('type_status') or '1') != '0':
                    nt[en] = nm
            if len(nt) >= 4:
                self.types = nt
        except Exception:
            pass

    def _lfil(self):
        try:
            h = self._get(self.pgdz + '/api.php/localhost/vod/?&ac=flitter', timeout=8000)
            if not h:
                return
            t = h.strip()
            try:
                j = json.loads(t)
                if not isinstance(j, dict):
                    raise ValueError('x')
            except Exception:
                j = json.loads(rcd(t, self.miyao))
            if not isinstance(j, dict):
                return
            fl = {}
            for tid, groups in j.items():
                gs = []
                for g in groups or []:
                    if not isinstance(g, dict):
                        continue
                    fd = str(g.get('field') or '').strip()
                    vs = g.get('values') or []
                    if not fd or not isinstance(vs, list) or not vs:
                        continue
                    gs.append({'key': fd, 'name': str(g.get('name') or fd),
                               'value': [{'n': str(v), 'v': str(v)} for v in vs]})
                if gs:
                    gs.append({'key': 'sort', 'name': '排序',
                               'value': [{'n': '综合', 'v': ''}, {'n': '热度优先', 'v': 'Hotdesc'},
                                         {'n': '评分最高', 'v': 'scoredesc'}, {'n': '最近更新', 'v': 'updatedesc'}]})
                    fl[str(tid)] = gs
            if fl:
                self.filters = fl
        except Exception:
            pass

    def _exs(self, ex):
        if not ex:
            return ''
        try:
            d = json.loads(ex) if isinstance(ex, str) else dict(ex)
        except Exception:
            d = {}
        ps = []
        for k in sorted(d.keys()):
            v = d.get(k)
            if v is None or str(v).strip() == '':
                continue
            ps.append('%s=%s' % (quote(str(k), safe=''), quote(str(v).strip(), safe='')))
        return '&'.join(ps)

    # ========== 容灾: 多HOST轮询 + requests双保险 ==========
    def _get(self, url, headers=None, timeout=12000):
        hd = headers or {'User-Agent': self.ua, 'Referer': self.ref}
        try:
            r = self.fetch(url, headers=hd, timeout=timeout)
            return r.text if hasattr(r, 'text') else str(r)
        except TypeError:
            try:
                r = self.fetch(url, headers=hd)
                return r.text if hasattr(r, 'text') else str(r)
            except Exception:
                pass
        except Exception:
            pass
        try:
            s = getattr(self, 'sess', None)
            if s is None:
                return ''
            r = s.get(url, headers=hd, timeout=max(4, int(timeout / 1000)))
            return r.text
        except Exception:
            return ''
    def _getj(self, url):
        h = self._get(url)
        if not h:
            return {}
        t = h.strip()
        try:
            j = json.loads(t)
            if isinstance(j, dict):
                return j
        except Exception:
            pass
        try:
            j = json.loads(rcd(t, self.miyao))
            return j if isinstance(j, dict) else {}
        except Exception:
            return {}

    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        return u  # 直连优先; 403时 playerContent/localProxy 兜底

    def _pagecount(self, h, cur=1):
        mx = cur
        for m in re.finditer(r'/(?:vodshow|s)/\d+[^"\']*?(\d+)(?:---|-)\.html|page=(\d+)', h):
            try:
                n = int(m.group(1) or m.group(2))
                if n > mx:
                    mx = n
            except:
                pass
        if re.search(r'下一页|class="[^"]*next[^"]*"', h):
            mx = max(mx, cur + 1)
        return mx

    # ========== 首页 ==========
    def homeContent(self, filter=False):
        r = {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()]}
        if self.filters:
            r['filters'] = self.filters
        r['list'] = self.homeVideoContent().get('list', [])
        return r

    def homeVideoContent(self):
        ck = ('movie', 1, '')
        c = self._ck.get(ck)
        if c and time.time() - c[0] < 300:
            return {'list': c[1].get('list', [])}
        d = self._cat_fetch('movie', 1, '')
        if d.get('list'):
            self._ck[ck] = (time.time(), d)
        return {'list': d.get('list', [])}

    # ========== 分类(JSON接口 + 筛选extend + 缓存预取动态翻页) ==========
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        t = str(tid).split('|')[0]
        exs = self._exs(extend)
        k = (t, pn, exs)
        c = self._ck.get(k)
        if c and time.time() - c[0] < 300:
            k2 = (t, pn + 1, exs)
            if pn < c[1].get('pagecount', 1) and k2 not in self._ck and k2 not in self._pfs:
                threading.Thread(target=self._pf, args=(t, pn + 1, exs), daemon=True).start()
            return c[1]
        d = self._cat_fetch(t, pn, exs)
        if d.get('list'):
            self._ck[k] = (time.time(), d)
            if pn < d.get('pagecount', 1):
                threading.Thread(target=self._pf, args=(t, pn + 1, exs), daemon=True).start()
            if len(self._ck) > 400:
                for kk in sorted(self._ck, key=lambda x: self._ck[x][0])[:120]:
                    self._ck.pop(kk, None)
        return d

    def _cat_fetch(self, t, pn, exs=''):
        url = self.pgdz + '/api.php/localhost/vod/?ac=list&class=' + quote(t) + ('&' + exs if exs else '') + '&page=' + str(pn)
        j = self._getj(url)
        items = self._items_j(j)
        try:
            tp = int(j.get('totalpage') or 1)
        except Exception:
            tp = 1
        return {'page': pn, 'pagecount': min(max(tp, 1), MAX_PAGE), 'limit': len(items) or 24,
                'total': j.get('videonum') or len(items), 'list': items}

    def _pf(self, t, pn, exs):
        k = (t, pn, exs)
        if k in self._pfs or k in self._ck:
            return
        self._pfs.add(k)
        try:
            d = self._cat_fetch(t, pn, exs)
            if d.get('list'):
                self._ck[k] = (time.time(), d)
        except Exception:
            pass
        self._pfs.discard(k)

    # ========== 详情(JSON接口 + player解密 + videolist多线路) ==========
    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        m = re.search(r'(\d+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        c = self._dk.get(vid)
        if c and time.time() - c[0] < 400:
            return c[1]
        j = self._getj(self.pgdz + '/api.php/localhost/vod/?ac=detail&ids=' + vid)
        if not j or not j.get('id'):
            return {'list': []}
        name = (j.get('title') or '').strip()
        shows = {}
        try:
            for x in json.loads(rcd(j.get('player') or '', self.miyao)):
                if isinstance(x, dict) and x.get('from'):
                    shows[x['from']] = x.get('show') or x['from']
        except Exception:
            pass
        pf, pu = [], []
        vl = j.get('videolist') or {}
        klist = list(vl.keys())
        klist.sort(key=lambda k: 0 if k == 'sdm3u8' else 1)
        for key2 in klist:
            eps = vl.get(key2)
            if not eps or not isinstance(eps, list):
                continue
            uu = []
            for ep in eps:
                if not isinstance(ep, dict):
                    continue
                u = (ep.get('url') or '').strip()
                if not u:
                    continue
                t = (ep.get('title') or '').strip().replace('$', '').replace('#', '') or '正片'
                self._sv[u] = (name, t)
                uu.append(t + '$' + u)
            if uu:
                pf.append(shows.get(key2) or key2)
                pu.append('#'.join(uu))
        if not pf:
            return {'list': []}

        def _js(x):
            if isinstance(x, list):
                return ','.join([str(v) for v in x if v])
            return x or ''

        r = {'list': [{'vod_id': vid, 'vod_name': name,
                       'vod_pic': self._pic(j.get('img_url') or j.get('img') or ''),
                       'vod_year': '', 'vod_area': _js(j.get('area')),
                       'vod_class': _js(j.get('type')),
                       'vod_director': _js(j.get('director'))[:200],
                       'vod_actor': _js(j.get('actor'))[:200],
                       'vod_content': (j.get('intro') or '')[:500],
                       'vod_remarks': (j.get('trunk') or '').strip(),
                       'vod_play_from': '$$$'.join(pf),
                       'vod_play_url': '$$$'.join(pu)}]}
        self._dk[vid] = (time.time(), r)
        return r

    # ========== 搜索(JSON接口) ==========
    def searchContent(self, key, quick=False, pg='1'):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        j = self._getj(self.pgdz + '/api.php/localhost/So/?ac=list&zm=' + quote(str(key)) + '&page=' + str(pn))
        return {'list': self._items_j(j), 'page': pn}

    # ========== 播放: Client{N}取流接口 → RC4(miyao) 真实m3u8 ==========
    def playerContent(self, flag, id, vipFlags=None):
        u = str(id or '').strip()
        if not u:
            return {'parse': 0, 'url': ''}
        if re.match(r'^https?://', u):
            return {'parse': 0, 'url': u}
        name, ep = self._sv.get(u, ('', ''))
        series = quote((name + '-' + ep) if (name or ep) else '')
        try:
            key = rce('&account=520720&password=520720&series=' + series + '&edition=2.9', self.rck)
        except Exception:
            key = ''
        full = self.curl + '/Client' + str(self.client or 1) + '/?url=' + u
        j = {}
        for _i in range(2):
            try:
                r = requests.post(full, data={'app': '10000', 'key': key}, headers={'User-Agent': self.ua}, timeout=15)
                j = json.loads(rcd(r.text.strip(), self.miyao))
            except Exception:
                j = {}
            if j.get('url'):
                break
            time.sleep(0.3)
        url = (j.get('url') or '').strip()
        ua = re.sub(r'[\r\n\t]+', '', (j.get('UserAgent') or '')).strip() or self.ua
        try:
            if int(j.get('Client') or 0):
                self.client = int(j.get('Client'))
        except Exception:
            pass
        return {'parse': 0, 'url': url, 'header': {'User-Agent': ua}, 'user_agent': ua}

    # ========== 四壳13接口扩展钩子(v7.5): isVideoFormat/manualVideoCheck/getDependence/destroy/progressVideo/setVideoFlags ==========
    def isVideoFormat(self, url):
        if not url:
            return False
        if '.m3u8' in url:
            return True
        return bool(re.search(r'\.(?:%s)(?:\?|$)' % (VIDEO_EXTS or 'm3u8|mp4|flv'), url, re.I))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return ''

    def destroy(self):
        for x in ('_ck', '_dk', '_pc', '_sv'):
            try:
                v = getattr(self, x, None)
                if isinstance(v, dict):
                    v.clear()
            except Exception:
                pass
        try:
            self._pfs.clear()
        except Exception:
            pass
        self._srv = None

    def progressVideo(self, speed, time, end):
        return False

    def setVideoFlags(self, siteKey, flags):
        try:
            self._siteKey = siteKey or SITE_KEY
            self._vflags = flags or {}
        except Exception:
            pass

    # ========== 本地代理(9979-9988): m3u8 KEY/分片重写 + 图片转码 ==========
    def localProxy(self, param):
        if isinstance(param, dict):
            p = param.get('url') or param.get('remote-url') or ''
        else:
            p = str(param)
            p = p.split('url=', 1)[-1] if 'url=' in p else p
        p = unquote(p) if '%' in p else p
        if re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', p, re.I):
            return self._img(p)
        if '.m3u8' in p:
            return self._rewrite_m3u8(p)
        try:
            r = self.fetch(p, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=20000)
            if hasattr(r, 'status_code') and r.status_code != 200:
                return {'code': r.status_code, 'content': b'', 'headers': {}}
            return {'code': 200, 'content': r.content, 'headers': {'Content-Type': r.headers.get('Content-Type', 'application/octet-stream')}}
        except:
            return {'code': 404, 'content': b'', 'headers': {}}

    def _rewrite_m3u8(self, url):
        try:
            r = self.fetch(url, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=20000)
            if hasattr(r, 'status_code') and r.status_code != 200:
                return {'code': r.status_code, 'content': b'', 'headers': {}}
            body = r.text if hasattr(r, 'text') else str(r)
        except:
            return {'code': 404, 'content': b'', 'headers': {}}
        base = url.rsplit('/', 1)[0] + '/'
        origin = re.match(r'https?://[^/]+', url)
        origin = origin.group(0) if origin else ''
        out = []
        for ln in body.splitlines():
            if ln.startswith('#EXT-X-KEY'):
                m = re.search(r'URI="([^"]+)"', ln)
                if m:
                    ku = m.group(1)
                    if ku.startswith('/'):
                        ku = origin + ku  # 根相对路径拼origin
                    elif not ku.startswith('http'):
                        ku = base + ku
                    ln = ln.replace('URI="%s"' % m.group(1), 'URI="%s"' % ('proxy?url=' + quote(ku, safe='')))
            elif ln.startswith('http'):
                ln = 'proxy?url=' + quote(ln, safe='')
            elif ln.startswith('/') and not ln.startswith('//'):
                ln = 'proxy?url=' + quote(origin + ln, safe='')
            out.append(ln)
        return {'code': 200, 'content': '\n'.join(out), 'headers': {'Content-Type': 'application/vnd.apple.mpegurl'}}

    def _img(self, u):
        try:
            r = requests.get(u, headers={'User-Agent': self.ua, 'Referer': PIC_REFERER or self.ref}, timeout=15)
            data, ct = r.content, r.headers.get('Content-Type', 'image/jpeg')
            if data[:4] == b'RIFF' or 'webp' in ct:
                try:
                    from PIL import Image
                    import io
                    buf = io.BytesIO()
                    Image.open(io.BytesIO(data)).convert('RGB').save(buf, 'JPEG', quality=85)
                    data, ct = buf.getvalue(), 'image/jpeg'
                except:
                    ct = 'image/webp'
            return {'code': 200, 'content': data, 'headers': {'Content-Type': ct}}
        except:
            return {'code': 404, 'content': b'', 'headers': {}}

    # ========== 列表解析(看客JSON: data[].nextlink含ids) ==========
    def _items_j(self, j):
        out = []
        for it in (j or {}).get('data') or []:
            if not isinstance(it, dict):
                continue
            m = re.search(r'ids=(\d+)', it.get('nextlink') or '')
            if not m:
                continue
            out.append({'vod_id': m.group(1), 'vod_name': (it.get('title') or '').strip(),
                        'vod_pic': self._pic(it.get('pic') or it.get('img') or ''),
                        'vod_remarks': (it.get('state') or '').strip()})
        return out