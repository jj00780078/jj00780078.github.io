# -*- coding: utf-8 -*-
"""
小霸王游戏源 (www.yikm.net) - TVBox 爬虫源（云游风格 · 点开即玩）
==============================================================
接口：homeContent / categoryContent(含筛选) / detailContent(兜底) / playerContent(兜底) / searchContent

与普通影视源最大的不同 —— 动作协议（借鉴云游源）：
- 列表项的 vod_id 不是数字 id，而是动作 JSON：
    {"actionId":"browser","type":"browser","title":"小游戏","url":游戏网页,"header":{...},"textZoom":100}
  + vod_tag: 'action'
- 支持动作协议的播放器（影视仓 / takagen99 Box 等）点开列表项后，
  会直接调起内置浏览器(WebView)打开游戏网页，JS 模拟器随之运行 —— 点开即玩！
- 全程没有 m3u8/mp4 视频流，不走视频嗅探（这就是"点开即玩"与"嗅探失败"的分水岭）

站点特性（已实测确认）：
1. 怀旧游戏站，列表页 /nes?tag=..&e=..&page=..，每页约20个
2. 平台 e 值（实测有效）：e=2 GBA / e=3 MD / e=4 FC高清 / e=5 SFC / e=6 DOS / e=7 NDS
   tag 平台：tag=0 FC / tag=9 街机
3. 类型筛选用全局数字 tag（实测有效）：tag=2动作冒险 3飞行射击 4格斗 5棋牌 6射击 7运动比赛 8小游戏 10角色扮演
   （参考云游源的中文 tag 筛选实测无效，已替换为数字 tag）
   修复记录：筛选器 v 值原本是纯数字，播放器点二级分类后会把 v 值当新 tid 调用
   （如 categoryContent('2')），导致拼出无效 URL 显示"暂无数据"。已把 v 值改为完整
   URL 路径模板（如 /nes?tag=2&e=0&page=），并兼容纯数字 tid、extend.class 完整路径
   等多种播放器调用流派，所有平台×二级分类实测均有内容。
4. 搜索：GET /search?name=关键词
5. 额外提供"定制"分类：内置一批热门网页游戏直达（原神云游戏/4399/小霸王/魂斗罗等）

核心优化（速度）：
- 连接池复用(requests.Session + HTTPAdapter) + gzip 自动解压 + 短超时(6s/4s) + 快速重试
- 多级缓存：分类5分钟 / 搜索3分钟 / 定制列表常驻
- 列表解析单请求完成，无二次请求
"""

import re
import json
import time
import sys
import threading
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except ImportError:
    _BaseSpider = None


# ============================================================
# 常量
# ============================================================
HOST = "https://www.yikm.net"

# 全局请求头（参考云游源，移动端 Chrome UA 确保游戏页正常加载）
UA = (
    "Mozilla/5.0 (Linux; Android 8.0; Pixel 2 Build/OPD3.170816.012) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 "
    "Mobile Safari/537.36"
)

# 超时（秒）
TIMEOUT_PAGE = 6
TIMEOUT_API = 4

# 缓存 TTL（秒）
TTL_CAT = 300
TTL_SEARCH = 180

# 动作协议 header（随每个 vod_id 下发，让内置浏览器带上移动 UA 与防广告跳转头）
ACTION_HEADER = {
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': UA,
}

# 平台分类（type_id 即列表 URL 模板，page= 处拼页码）
# 结构：type_id / type_name / type_flag（照云游源）
PLATFORMS = [
    {"id": "/nes?tag=0&e=0&page=", "name": "FC",      "flag": "[CFS]2-00-S"},
    {"id": "/nes?tag=&e=5&page=",  "name": "SFC",     "flag": "[CFS]2-00-S"},
    {"id": "/nes?tag=9&e=&page=",  "name": "街机",     "flag": "[CFS]2-00-S"},
    {"id": "/nes?tag=&e=2&page=",  "name": "GBA",     "flag": "[CFS]2-00-S"},
    {"id": "/nes?tag=&e=7&page=",  "name": "NDS",     "flag": "[CFS]2-00-S"},
    {"id": "/nes?tag=&e=3&page=",  "name": "MD",      "flag": "[CFS]2-00-S"},
    {"id": "/nes?tag=&e=6&page=",  "name": "DOS",     "flag": "[CFS]2-00-S"},
    {"id": "/nes?tag=&e=4&page=",  "name": "FC高清",   "flag": "[CFS]2-00-S"},
]

# 类型筛选（v 值是完整列表 URL 模板，page= 处拼页码；数字 tag 实测有效）
GAME_TYPES = [
    ("/nes?tag=2&e=0&page=",  "动作冒险"),
    ("/nes?tag=3&e=0&page=",  "飞行射击"),
    ("/nes?tag=4&e=0&page=",  "格斗"),
    ("/nes?tag=5&e=0&page=",  "棋牌"),
    ("/nes?tag=6&e=0&page=",  "射击"),
    ("/nes?tag=7&e=0&page=",  "运动比赛"),
    ("/nes?tag=8&e=0&page=",  "小游戏"),
    ("/nes?tag=10&e=0&page=", "角色扮演"),
]

# 定制分类：内置热门网页游戏直达（照云游源 myGame）
CUSTOM_GAMES = [
    {"name": "原神启动！", "url": "https://ys.mihoyo.com/cloud/m/",
     "pic": "https://pan.uvqzu.cn/f/4Z1ue/IMG_20260305_170950.jpg"},
    {"name": "星穹铁道", "url": "https://sr.mihoyo.com/cloud/m/#/",
     "pic": "https://pan.uvqzu.cn/f/Q6ktP/IMG_20260305_171855.jpg"},
    {"name": "好游快爆", "url": "https://m.3839.com/wap.html",
     "pic": "https://pan.uvqzu.cn/f/01jtP/m.baidu.com_1162231158.png"},
    {"name": "TapTap", "url": "https://www.taptap.cn/",
     "pic": "https://pan.uvqzu.cn/f/xpqhX/m.baidu.com_01172723iyvp.png"},
    {"name": "网易云游戏", "url": "https://cg.163.com/#/game/recommend?tab_id=66051b810d5fa1f0204c294f",
     "pic": "https://pan.uvqzu.cn/f/nAyHZ/IMG_20260305_175247.jpg"},
    {"name": "抖音", "url": "https://www.douyin.com/?is_from_mobile_home=1",
     "pic": "https://pan.uvqzu.cn/f/3lJuW/m.baidu.com_e2ecc9605e2f97e1135d87cab2ddcf08.jpeg"},
    {"name": "拼多多", "url": "https://mobile.yangkeduo.com/",
     "pic": "https://pan.uvqzu.cn/f/4ZrSe/IMG_20260305_183229.png"},
    {"name": "淘宝", "url": "https://main.m.taobao.com/",
     "pic": "https://pan.uvqzu.cn/f/Nw5HW/IMG_20260305_182200.jpg"},
    {"name": "京东", "url": "https://m.jd.com/",
     "pic": "https://pan.uvqzu.cn/f/janHj/IMG_20260305_181852.png"},
    {"name": "野草助手", "url": "https://www.yecao.net/",
     "pic": "https://pan.uvqzu.cn/f/JKPcD/m.baidu.com_20231207112652564.png"},
    {"name": "永劫无间", "url": "https://cloudgame.ds.163.com/yjwj",
     "pic": "https://pan.szfx.top/view.php/2c4445e75e023e2dd5b0439253957c77.jpg"},
    {"name": "梦幻西游", "url": "https://xyh5.163.com/game/?channel=netease",
     "pic": "https://pan.szfx.top/view.php/52902e10204e7b07dbc69f6e3fdec9ab.jpg"},
    {"name": "赛尔号", "url": "https://s.61.com/",
     "pic": "https://pan.szfx.top/view.php/f56ac1ae1dd1a49041199a6719fd9234.png"},
    {"name": "刘明野的工具箱", "url": "https://tools.liumingye.cn/",
     "pic": "https://pan.szfx.top/view.php/1dcefe9108bee4a51f0d8e59cffe7a04.png"},
    {"name": "4399小游戏", "url": "https://h.4399.com/",
     "pic": "https://pan.szfx.top/view.php/b5f614076f8a9df19e3cdd1d01bdf09a.png"},
    {"name": "一千个小游戏", "url": "https://fuun.fun/",
     "pic": "https://pan.szfx.top/view.php/8191c07bb1631cde242a61aa97d7fbe5.jpg"},
    {"name": "小霸王游戏机", "url": "https://www.yikm.net",
     "pic": "https://pan.szfx.top/view.php/4d88e211d22818b011d68073353f0d3d.jpg"},
    {"name": "红色警戒2", "url": "https://ra2web.com/",
     "pic": "https://pan.szfx.top/view.php/80ff902afb37581accc402666382a9fb.jpg"},
    {"name": "X的世界", "url": "https://bloxd.io",
     "pic": "https://pan.szfx.top/view.php/0f6ff96aa13b4bb6c3adba724df6e34d.png"},
    {"name": "贪吃蛇", "url": "http://slither.io/",
     "pic": "https://pan.szfx.top/view.php/8818a2e27a1c6fa9a6d702e579ad9d1b.jpg"},
    {"name": "斗地主(人机)", "url": "https://www.haiwaiqipai.com/games/doudizhus/index.html",
     "pic": "https://www.haiwaiqipai.com/img/DouDiZhu.jpg"},
    {"name": "五子棋", "url": "https://wuziqi.hongton.com",
     "pic": "https://wuziqi.hongton.com/img/stype/init-bg.png"},
    {"name": "俄罗斯方块", "url": "https://v2fy.com/game/tetris/",
     "pic": "https://i-1-uc129.zswxy.cn/2023/0223/5d809bdb026646478a97a938f7b3300c.png"},
    {"name": "魂斗罗(美版)", "url": "https://www.yikm.net/play?id=4137",
     "pic": "https://img.1990i.com/fcpic/sj/436a.png"},
    {"name": "马里奥", "url": "https://www.yikm.net/play?id=3175",
     "pic": "https://img.1990i.com/fcpic/3175.png"},
    {"name": "拳皇97", "url": "https://www.yikm.net/play?id=4481",
     "pic": "https://img.1990i.com/fcpic/4481.png"},
]

# 全部分类 + 筛选器
ALL_CLASSES = (
    [{"type_id": "定制", "type_name": "定制", "type_flag": "2-00-S"}]
    + [{"type_id": p["id"], "type_name": p["name"], "type_flag": p["flag"]} for p in PLATFORMS]
)

# 每个平台的类型筛选器（数字 tag 全局生效，统一给每个平台配上）
_FILTER_VALUE = [{"n": "全部", "v": ""}] + [{"n": n, "v": t} for t, n in GAME_TYPES]
ALL_FILTERS = {}
for p in PLATFORMS:
    ALL_FILTERS[p["id"]] = [{"key": "class", "name": "类型", "value": _FILTER_VALUE}]


def _browser_vod(url, name, pic='', header=None):
    """构造动作协议条目：vod_id = 浏览器动作 JSON（点开即用内置浏览器打开网页）"""
    action = {
        "actionId": "browser",
        "type": "browser",
        "title": "小游戏",
        "url": url,
        "textZoom": 100,
        "header": header or ACTION_HEADER,
    }
    return {
        "vod_id": json.dumps(action, ensure_ascii=False),
        "vod_name": name,
        "vod_pic": pic,
        "vod_tag": "action",
    }


# ============================================================
# Spider 主类
# ============================================================
_Base = _BaseSpider if _BaseSpider is not None else object


class Spider(_Base):
    siteUrl = HOST
    headers = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': HOST + '/',
    }

    # ===== 初始化 =====
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.headers['Connection'] = 'keep-alive'
        self.session.verify = False
        adapter = HTTPAdapter(
            pool_connections=20, pool_maxsize=40,
            max_retries=0, pool_block=False,
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self._lock = threading.Lock()
        self._cat_cache = {}
        self._search_cache = {}

    def init(self, extend=""):
        self.extend = extend or ""

    # ===== 网络工具 =====
    def _get(self, url, referer='', timeout=TIMEOUT_PAGE):
        headers = {'Connection': 'keep-alive'}
        if referer:
            headers['Referer'] = referer
        for attempt in range(2):
            try:
                r = self.session.get(url, timeout=timeout, headers=headers)
                if r.status_code == 429:
                    time.sleep(2.0)
                    continue
                r.raise_for_status()
                r.encoding = 'utf-8'
                return r
            except Exception:
                if attempt == 0:
                    time.sleep(0.2)
                else:
                    return None
        return None

    def _get_text(self, url, referer='', timeout=TIMEOUT_PAGE):
        r = self._get(url, referer, timeout)
        return r.text if r is not None else ""

    # ===== 缓存 =====
    @staticmethod
    def _cache_get(cache, key, ttl):
        item = cache.get(key)
        if item and time.time() - item[0] < ttl:
            return item[1]
        return None

    @staticmethod
    def _cache_set(cache, key, value, ttl):
        if len(cache) > 512:
            cache.clear()
        cache[key] = (time.time(), value, ttl)

    # ===== HTML 解析 =====
    @staticmethod
    def _soup(html):
        if not html or BeautifulSoup is None:
            return None
        try:
            return BeautifulSoup(html, 'lxml')
        except Exception:
            try:
                return BeautifulSoup(html, 'html.parser')
            except Exception:
                return None

    @staticmethod
    def _abs(u):
        u = (u or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return HOST + u
        if not u.startswith('http'):
            return HOST + '/' + u
        return u

    def _parse_cards(self, html, limit=40):
        """列表/搜索共用的游戏卡片解析（.card-blog 结构），输出动作协议条目"""
        if not html:
            return []
        soup = self._soup(html)
        if soup is None:
            return []
        out = []
        for card in soup.select('.row .col-md-3.col-xs-6 .card-blog'):
            a = card.select_one('h4 a')
            if a is None:
                a = card.select_one('a[href]')
            if a is None:
                continue
            name = a.get_text(strip=True)
            url = self._abs(str(a.get('href') or ''))
            if not name or not url or 'javascript' in url:
                continue
            pic = ''
            img = card.select_one('.card-image img')
            if img is not None:
                pic = self._abs(str(img.get('src') or ''))
            out.append(_browser_vod(url, name, pic))
            if len(out) >= limit:
                break
        return out

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter=False):
        return {
            "class": ALL_CLASSES,
            "filters": ALL_FILTERS,
            "list": [],
        }

    def homeVideoContent(self):
        # 首页推荐：定制分类的热门网页游戏（点开即玩）
        return {"list": [_browser_vod(g["url"], g["name"], g.get("pic", "")) for g in CUSTOM_GAMES[:20]]}

    # ============================================================
    # 分类列表
    # ============================================================
    def _empty_category(self, page=1):
        return {"list": [], "page": page, "pagecount": 1, "limit": 40, "total": 0}

    def _custom_list(self, pg):
        """定制分类：内置热门网页游戏直达（点开即用浏览器打开）"""
        if pg and int(pg) > 1:
            return {"list": []}
        return {"list": [_browser_vod(g["url"], g["name"], g.get("pic", "")) for g in CUSTOM_GAMES]}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg or 1))
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            # 定制分类：返回内置直达列表
            if str(tid).strip() == '定制':
                return self._custom_list(page)

            # 用户自定义搜索（部分播放器通过 extend.custom 透传）
            if ext.get('custom'):
                return self.searchContent(str(ext['custom']), quick=True, pg=page)

            # 构造列表 URL：优先级 extend.class(完整路径) > tid 是完整路径 > tid 是平台路径
            # （播放器点二级分类后，可能把筛选 v 值(完整路径)当新 tid 传入，也可能放进 extend.class）
            type_path = (ext.get('class') or '').strip()
            if type_path:
                url = HOST + type_path + str(page)
            else:
                # 兜底：纯数字 tid（如 '2'）映射到完整路径模板
                raw_tid = str(tid).strip()
                if not raw_tid.startswith('/nes?'):
                    for tpl, _name in GAME_TYPES:
                        if tpl.startswith('/nes?tag=' + raw_tid + '&') or raw_tid == tpl:
                            url = HOST + tpl + str(page)
                            break
                    else:
                        url = HOST + raw_tid + str(page)
                else:
                    url = HOST + raw_tid + str(page)

            ckey = "%s|%d|%s" % (url, page, type_path)
            cached = self._cache_get(self._cat_cache, ckey, TTL_CAT)
            if cached is not None:
                return cached

            html = self._get_text(url)
            if not html:
                return self._empty_category(page)

            vod_list = self._parse_cards(html)
            # 附加固定项（照云游源）
            vod_list.append(_browser_vod("https://www.crazygames.com", "crazygames", ''))
            vod_list.append(_browser_vod("https://poki.com/zh", "poki", ''))

            result = {
                "list": vod_list,
                "page": page,
                "pagecount": 10,
                "limit": 40,
                "total": 400,
            }
            self._cache_set(self._cat_cache, ckey, result, TTL_CAT)
            return result
        except Exception:
            return self._empty_category(page)

    # ============================================================
    # 详情（动作协议源无需详情页；兜底返回，避免部分播放器报错）
    # ============================================================
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vid = str(ids[0]) if ids else ''
        try:
            action = json.loads(vid)
            url = action.get("url") or ""
            name = action.get("title") or "小游戏"
        except Exception:
            url = vid
            name = vid
        if not url:
            return {"list": []}
        detail = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": '',
            "type_name": "小游戏",
            "vod_remarks": "点开即玩",
            "vod_year": '',
            "vod_area": '',
            "vod_lang": '',
            "vod_director": '',
            "vod_actor": '',
            "vod_content": f"{name} 点开即用浏览器打开游玩",
            "vod_play_from": "在线玩",
            "vod_play_url": f"在线玩${url}",
        }
        return {"list": [detail]}

    # ============================================================
    # 播放（兜底：网页在线玩，交给支持网页的播放器）
    # ============================================================
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}
        url = str(id)
        if url.startswith('http'):
            return {
                "parse": 1,
                "playUrl": "",
                "url": url,
                "header": ACTION_HEADER,
            }
        return {"parse": 0, "playUrl": "", "url": url, "header": ACTION_HEADER}

    # ============================================================
    # 搜索（站内搜索，结果同样是动作协议）
    # ============================================================
    def searchContent(self, keyword, quick=False, pg=1):
        kw = quote((keyword or '').strip())
        if not kw:
            return {"list": [], "msg": "请输入搜索关键词"}

        page = int(pg or 1)
        ckey = "%s|%s" % (page, (keyword or '').strip().lower())
        cached = self._cache_get(self._search_cache, ckey, TTL_SEARCH)
        if cached is not None:
            return cached

        url = f"{HOST}/search?name={kw}"
        html = self._get_text(url, referer=HOST + '/', timeout=TIMEOUT_API)
        if html:
            vod_list = self._parse_cards(html)
            if vod_list:
                result = {"list": vod_list, "page": page}
                self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
                return result

        result = {"list": [], "msg": "未找到相关游戏，请尝试其他关键词或通过分类浏览", "page": page}
        self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
        return result

    # ============================================================
    # 清理
    # ============================================================
    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def close(self):
        self.destroy()


# ============================================================
# 本地测试
# ============================================================
if __name__ == '__main__':
    s = Spider()
    action = sys.argv[1] if len(sys.argv) > 1 else 'home'
    if action == 'home':
        print(json.dumps(s.homeContent(), ensure_ascii=False)[:600])
    elif action == 'category':
        tid = sys.argv[2] if len(sys.argv) > 2 else '定制'
        pg = sys.argv[3] if len(sys.argv) > 3 else '1'
        cl = sys.argv[4] if len(sys.argv) > 4 else ''
        r = s.categoryContent(tid, pg, False, {'class': cl} if cl else {})
        print("list=%d" % len(r.get('list', [])))
        for it in r.get('list', [])[:5]:
            try:
                act = json.loads(it['vod_id'])
                print(" -", it['vod_name'], "|", act.get('url', '')[:60], "| tag:", it.get('vod_tag'))
            except Exception:
                print(" -", it['vod_name'], "|", it['vod_id'][:60])
    elif action == 'search':
        kw = sys.argv[2] if len(sys.argv) > 2 else '魂斗罗'
        r = s.searchContent(kw)
        print("list=%d" % len(r.get('list', [])))
        for it in r.get('list', [])[:5]:
            try:
                act = json.loads(it['vod_id'])
                print(" -", it['vod_name'], "|", act.get('url', '')[:60])
            except Exception:
                print(" -", it['vod_name'])
    elif action == 'detail':
        vid = sys.argv[2] if len(sys.argv) > 2 else '{"actionId":"browser","type":"browser","title":"小游戏","url":"https://www.yikm.net/play?id=4137","header":{"User-Agent":"x"}}'
        print(json.dumps(s.detailContent(vid), ensure_ascii=False)[:500])
    s.close()
