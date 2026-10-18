# -*- coding: utf-8 -*-
# ============================================================
#  源站名称: 57吃瓜网 (57duanju.org)
#  目标频道: /aichengduanju/ 成人AI短剧 / 全部吃瓜频道
#  协议类型: 四壳通用 (ok影视/Fongmi/webhome/影视仓) 13接口, 标准库 urllib
#            (移动端 Chaquopy 无 requests 亦可运行)
#  版本状态: v1.4
#  修复记录
#   v1.4: 封面图片改用 localProxy 代理 (127.0.0.1:9978)，解决 s.chigua.media
#         防盗链导致的绿A占位符问题；localProxy 同时兼容字符串/字典参数格式
#   v1.3: 重写 _parse_list 兼容两种卡片结构（AI短剧/其他分类）
#         修复非AI分类内容为空问题
#   v1.2: 封面直接返回原始URL（临时方案）
#   v1.1: homeContent补list键；homeVideoContent独立返回；init签名适配四壳
#   v1.0: 初始开发
#  站点要点
#   - 频道: hot/aichengduanju/jrcg/mrds/wanghong/video/cheating/live/society/star
#   - 分页: /{频道}/{n}/ (部分频道不分页, 自动从HTML提取)
#   - 排序: /aichengduanju/?sort=hot|trending
#   - 搜索: /search/?q=关键词
#   - 详情: <video data-hls-src="...m3u8" data-fallback-src="...mp4">, 图集页无 video
#   - 防盗链: s.chigua.media 全部资源须带 Referer, 封面/m3u8/ts 经 localProxy(127.0.0.1:9978) 代理
#   - 备用域: 57duanju.net / 57cg4.com 主域失败自动切换
#  广告预检: m3u8 内容干净无广告分片, 直接透传, localProxy 专职防盗链代理
# ============================================================
import re
import gzip
import zlib
import json
import ssl
import urllib.request
from urllib.parse import quote, unquote, urljoin

try:
    from base.spider import Spider
except Exception:
    Spider = object

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
_HOSTS = ['https://57duanju.org', 'https://57duanju.net', 'https://57cg4.com']
_REFER = 'https://57duanju.org/'
_PROXY_BASE = 'http://127.0.0.1:9978/'
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_NAV = {
    'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
               'image/avif,image/webp,*/*;q=0.8'),
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.6',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
    'Upgrade-Insecure-Requests': '1',
}
_CHANNELS = [
    ('hot', '热门'),
    ('aichengduanju', '成人AI短剧'),
    ('jrcg', '今日吃瓜'),
    ('mrds', '每日大赛'),
    ('wanghong', '网红黑料'),
    ('video', '网黄合集'),
    ('cheating', '出轨劈腿'),
    ('live', '直播擦边'),
    ('society', '社会事件'),
    ('star', '明星八卦'),
]


def clean(text):
    if not text:
        return ''
    return re.sub(r'\s+', ' ', text).strip()


class Spider(Spider):
    _host_idx = 0

    def getName(self):
        return '57吃瓜'

    def getProxyUrl(self):
        """返回本地代理基础地址，供壳构造代理URL"""
        return _PROXY_BASE

    def isVideoFormat(self, url, *args):
        if not url:
            return False
        return ('.m3u8' in str(url)) or ('.mp4' in str(url)) or ('.ts' in str(url))

    def manualVideoCheck(self):
        return False

    def destroy(self, *args):
        pass

    def getDependence(self, *args):
        return ''

    def init(self, extend=""):
        if extend and isinstance(extend, str):
            try:
                ext = json.loads(extend)
                if isinstance(ext, dict):
                    site = ext.get('siteUrl') or ext.get('proxy') or ''
                    if site:
                        site = site.rstrip('/')
                        if site not in _HOSTS:
                            _HOSTS.insert(0, site)
            except Exception:
                pass

    def _http(self, url):
        last = None
        for i in range(len(_HOSTS)):
            idx = (self._host_idx + i) % len(_HOSTS)
            target = url
            if url.startswith(_HOSTS[0]):
                target = _HOSTS[idx] + url[len(_HOSTS[0]):]
            req = urllib.request.Request(target, headers=dict(_NAV, **{
                'User-Agent': _UA,
                'Referer': _REFER,
            }))
            try:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}),
                    urllib.request.HTTPSHandler(context=_CTX))
                resp = opener.open(req, timeout=15)
                data = resp.read()
                if resp.getcode() == 200:
                    enc = (resp.headers.get('Content-Encoding') or '').lower()
                    if enc == 'gzip' or data[:2] == b'\x1f\x8b':
                        try:
                            data = gzip.decompress(data)
                        except Exception:
                            pass
                    elif enc == 'deflate':
                        try:
                            data = zlib.decompress(data)
                        except Exception:
                            pass
                    self._host_idx = idx
                    return data
            except Exception as e:
                last = e
                continue
        return None

    def _html(self, url):
        data = self._http(url)
        if data is None:
            return ''
        return data.decode('utf-8', 'ignore')

    def _proxy_url(self, url):
        """将真实URL包装为 localProxy 代理URL"""
        if not url:
            return ''
        if url.startswith('http://127.0.0.1'):
            return url
        return _PROXY_BASE + quote(url, safe='')

    def _parse_list(self, html):
        """解析列表页，兼容两种卡片结构：
        1. AI短剧: href="/events/{id}/" 内含 h2 标题
        2. 其他分类: href="https://57cg4.com/events/{id}/" 标题在 img alt 中
        """
        items = []
        seen = set()
        
        # 先尝试匹配完整URL格式（其他分类）
        pattern1 = r'<a[^>]+href="https://[^"]+/events/(\d+)/"[^>]*>(.*?)</a>'
        for m in re.finditer(pattern1, html, re.S):
            vid = m.group(1)
            inner = m.group(2)
            if vid in seen:
                continue
            # 优先从 h2 提取标题
            h2 = re.search(r'<h2[^>]*>(.*?)</h2>', inner, re.S)
            name = clean(re.sub(r'<[^>]+>', '', h2.group(1))) if h2 else ''
            # 如果 h2 为空，尝试从 img alt 提取
            if not name:
                img_alt = re.search(r'<img[^>]+alt="([^"]+)"', inner, re.S)
                if img_alt:
                    name = clean(img_alt.group(1))
            if not name:
                continue
            imgs = re.findall(r'<img[^>]+src="([^"]+)"', inner, re.S)
            pic = ''
            for s in imgs:
                if 'uploads/' in s or 'logo' in s:
                    continue
                pic = s
                break
            seen.add(vid)
            items.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': self._proxy_url(pic),
                'vod_remarks': '',
            })
        
        # 如果没有匹配到，尝试相对路径格式（AI短剧）
        if not items:
            pattern2 = r'<a[^>]+href="(/events/(\d+)/)"[^>]*>(.*?)</a>'
            for m in re.finditer(pattern2, html, re.S):
                vid = m.group(2)
                inner = m.group(3)
                if vid in seen:
                    continue
                h2 = re.search(r'<h2[^>]*>(.*?)</h2>', inner, re.S)
                name = clean(re.sub(r'<[^>]+>', '', h2.group(1))) if h2 else ''
                if not name:
                    continue
                imgs = re.findall(r'<img[^>]+src="([^"]+)"', inner, re.S)
                pic = ''
                for s in imgs:
                    if 'uploads/' in s or 'logo' in s:
                        continue
                    pic = s
                    break
                seen.add(vid)
                items.append({
                    'vod_id': vid,
                    'vod_name': name,
                    'vod_pic': self._proxy_url(pic),
                    'vod_remarks': '',
                })
        
        return items

    def _parse_pagecount(self, html, tid, pg):
        nums = [int(x) for x in re.findall(r'/%s/(\d+)/' % re.escape(tid), html)]
        nums = [x for x in nums if x > 0]
        return max(nums) if nums else pg

    def homeContent(self, *args):
        try:
            return self._home()
        except Exception:
            return {'class': [], 'filters': {}, 'list': []}

    def homeVideoContent(self):
        try:
            html = self._html('%s/aichengduanju/' % _HOSTS[0])
            return {'list': self._parse_list(html)}
        except Exception:
            return {'list': []}

    def _home(self):
        html = self._html(_HOSTS[0] + '/aichengduanju/')
        classes = [{'type_id': t, 'type_name': n} for t, n in _CHANNELS]
        filters = {
            'aichengduanju': [{
                'key': 'sort', 'name': '排序',
                'value': [
                    {'n': '最新', 'v': ''},
                    {'n': '最热', 'v': 'hot'},
                    {'n': '飙升', 'v': 'trending'},
                ],
            }],
        }
        return {'class': classes, 'filters': filters, 'list': self._parse_list(html)}

    def categoryContent(self, *args):
        try:
            tid = str(args[0]) if len(args) > 0 else ''
            pg = int(args[1]) if len(args) > 1 and str(args[1]).isdigit() else 1
            flt = args[2] if len(args) > 2 else None
        except Exception:
            tid, pg, flt = '', 1, None
        page = pg if pg else 1
        url = '%s/%s/' % (_HOSTS[0], tid)
        if page > 1:
            url = '%s/%s/%d/' % (_HOSTS[0], tid, page)
        sort = ''
        if isinstance(flt, dict):
            v = flt.get('sort') or ''
            if str(v).strip() and str(v).strip() != '全部':
                sort = str(v).strip()
        if sort:
            url = url + ('&' if '?' in url else '?') + 'sort=' + quote(sort)
        html = self._html(url)
        items = self._parse_list(html)
        pagecount = self._parse_pagecount(html, tid, page)
        total = len(items) or 0
        return {
            'page': page, 'pagecount': pagecount, 'limit': len(items),
            'total': total, 'list': items,
        }

    def detailContent(self, *args):
        ids = args[0] if args else ''
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        vods = []
        seen = set()
        for vid in ids:
            vid = str(vid).strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            vod = self._detail_one(vid)
            if vod:
                vods.append(vod)
        return {'list': vods}

    def _detail_one(self, vid):
        if not re.match(r'^\d+$', vid):
            return None
        html = self._html('%s/events/%s/' % (_HOSTS[0], vid))
        if not html:
            return None
        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        name = clean(re.sub(r'<[^>]+>', '', h1.group(1))) if h1 else ''
        if not name:
            tm = re.search(r'<title[^>]*>(.*?)</title>', html, re.S)
            if tm:
                name = clean(re.sub(r'[-_]\s*57吃瓜网\s*$', '', tm.group(1)))
        post = re.search(r'<video[^>]+poster="([^"]+)"', html)
        pics = [s for s in re.findall(r'<img[^>]+src="([^"]+)"', html, re.S)
                if 'uploads/' not in s and '/logo' not in s]
        pic = post.group(1) if post else (pics[0] if pics else '')
        text = re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S)
        text = re.sub(r'<[^>]+>', '\n', text)
        text = re.sub(r'&nbsp;?', ' ', text, flags=re.I)
        text = re.sub(r'\n{2,}', '\n', text)
        start = text.find('首次曝光')
        if start < 0:
            start = 0
        end = text.find('猜你喜欢', start)
        if end < 0:
            end = len(text)
        content = clean(text[start:end])
        tags = ['#' + clean(x) for x in
                re.findall(r'<a[^>]+href="[^"]*/tags/[^"]+"[^>]*>#?([^<]+)</a>', html)]
        if tags:
            content = (content + '  标签：' + ' '.join(tags)).strip()
        vids = []
        for v in re.findall(r'<video[^>]*>', html):
            m3 = re.search(r'data-hls-src="([^"]+)"', v)
            fb = re.search(r'data-fallback-src="([^"]+)"', v)
            if m3:
                vids.append(m3.group(1))
            elif fb:
                vids.append(fb.group(1))
        seen_u = set()
        uniq = []
        for u in vids:
            if u and u not in seen_u:
                seen_u.add(u)
                uniq.append(u)
        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': self._proxy_url(pic),
            'vod_remarks': '',
            'vod_content': content,
        }
        if uniq:
            segs = []
            for i, u in enumerate(uniq, 1):
                segs.append('%s$%s' % ('正片' if len(uniq) == 1 else ('第%d集' % i), u))
            play_url = '#'.join(segs)
            vod['vod_play_from'] = '直连$$$代理'
            vod['vod_play_url'] = play_url + '$$$' + play_url
        else:
            vod['vod_play_from'] = ''
            vod['vod_play_url'] = ''
            vod['vod_remarks'] = '图集'
        return vod

    def searchContent(self, *args):
        try:
            key = str(args[0]) if len(args) > 0 else ''
            page = int(args[1]) if len(args) > 1 and str(args[1]).isdigit() else 1
        except Exception:
            key, page = '', 1
        html = self._html('%s/search/?q=%s' % (_HOSTS[0], quote(key)))
        items = self._parse_list(html)
        return {
            'page': page, 'pagecount': 1, 'limit': len(items),
            'total': len(items), 'list': items,
        }

    def playerContent(self, *args):
        try:
            flag = str(args[0]) if len(args) > 0 else ''
            vid = str(args[1]) if len(args) > 1 else ''
        except Exception:
            flag, vid = '', ''
        if not vid:
            return {'parse': 0, 'url': '', 'header': {}, 'jx': 0}
        if '代理' in flag:
            return {'parse': 0, 'url': self._proxy_url(vid), 'header': {}, 'jx': 0}
        return {
            'parse': 0, 'url': vid, 'jx': 0,
            'header': {
                'User-Agent': _UA,
                'Referer': _REFER,
                'Origin': 'https://57duanju.org',
            },
        }

    def localProxy(self, param):
        """本地代理：处理 m3u8/ts/mp4/图片 等资源的防盗链请求
        
        兼容多种壳的调用方式：
        1. ok影视壳: param = "http://127.0.0.1:9978/https%3A%2F%2F..." (完整URL字符串)
        2. Fongmi壳: param = {"url": "https%3A%2F%2F..."} (字典，含url键)
        3. 影视仓壳: param = "/https%3A%2F%2F..." (路径字符串)
        4. webhome壳: param = {"url": "BASE64", "ref": "BASE64"} (字典，base64编码)
        """
        try:
            url = ''
            
            # 处理字典参数（Fongmi/webhome/影视仓等）
            if isinstance(param, dict):
                # 优先从 url 键获取
                raw_url = param.get('url', '')
                # 尝试 base64 解码（webhome常用base64）
                if raw_url:
                    try:
                        import base64
                        # 尝试urlsafe_b64decode
                        padded = raw_url + '=' * (-len(raw_url) % 4)
                        decoded = base64.urlsafe_b64decode(padded).decode('utf-8', 'ignore')
                        if decoded.startswith('http'):
                            url = decoded
                        else:
                            url = unquote(raw_url)
                    except Exception:
                        url = unquote(str(raw_url))
                else:
                    # 尝试其他可能的键
                    for key in ['url', 'u', 'link', 'src']:
                        if key in param:
                            url = unquote(str(param[key]))
                            break
            
            # 处理字符串参数（ok影视壳等）
            elif isinstance(param, str):
                raw = param
                # 去掉本地代理前缀
                if raw.startswith('http://127.0.0.1:9978/'):
                    url = unquote(raw[22:])
                elif raw.startswith('/proxy'):
                    # /proxy?url=... 格式
                    match = re.search(r'url=([^&]+)', raw)
                    if match:
                        url = unquote(match.group(1))
                else:
                    # 直接是编码后的URL（可能带/前缀）
                    url = unquote(raw.lstrip('/'))
            
            if not url or not url.startswith('http'):
                return [404, 'text/plain', '']
            
            # 使用 _http 获取资源（自动带Referer）
            data = self._http(url)
            if data is None:
                return [404, 'text/plain', '']
            
            # 判断Content-Type
            url_lower = url.lower()
            if '.m3u8' in url_lower:
                # m3u8需要重写内部URL为代理地址
                lines = []
                for ln in data.decode('utf-8', 'ignore').splitlines():
                    s = ln.strip()
                    if s and not s.startswith('#'):
                        ts_abs = urljoin(url, s)
                        lines.append(_PROXY_BASE + quote(ts_abs, safe=''))
                    else:
                        lines.append(ln.rstrip())
                body = ('\n'.join(lines) + '\n').encode('utf-8')
                return [200, 'application/vnd.apple.mpegurl', body]
            elif url_lower.endswith('.ts'):
                return [200, 'video/mp2t', data]
            elif url_lower.endswith('.mp4'):
                return [200, 'video/mp4', data]
            elif url_lower.endswith('.webp'):
                return [200, 'image/webp', data]
            elif url_lower.endswith('.png'):
                return [200, 'image/png', data]
            elif url_lower.endswith(('.jpg', '.jpeg')):
                return [200, 'image/jpeg', data]
            elif url_lower.endswith('.gif'):
                return [200, 'image/gif', data]
            elif url_lower.endswith('.svg'):
                return [200, 'image/svg+xml', data]
            else:
                return [200, 'application/octet-stream', data]
                
        except Exception as e:
            return [404, 'text/plain', '']
