

import sys
import json
import time
import base64

try:
    from urllib.parse import quote, unquote
except Exception:
    from urllib import quote, unquote

from base.spider import Spider

try:
    from Crypto.Cipher import AES
except Exception:
    from Cryptodome.Cipher import AES


class Spider(Spider):

    # ---- 站点常量 ----
    GATEWAY = "https://pl5kjl.jas49cht5sqrwet.xyz/fast-endecode/main/request"
    GATEWAY_POOL = [
        "https://pl5kjl.jas49cht5sqrwet.xyz/fast-endecode/main/request",
        "https://pl5kjl.m93abv5upsv4s8f.xyz/fast-endecode/main/request",
        "https://api.y7hvaad8g.xyz/fast-endecode/main/request",
    ]

    # time%10 -> AES key（index 2 稳定可用，固定使用）
    KEYS = {
        0: "G7i3OPcfNhBnAYpc",
        1: "84UZNK33cSVylz6Y",
        2: "jeSWRcTwHyAKwJDB",
        3: "i1hvJx9vuRt5zEBS",
        4: "1Yy1KOa75R7cnmkg",
        6: "T0RVp7KIPamrtQ33",
        8: "ugvseZc5Kkj8ecmV",
        9: "G7i3OPcfNhBnAYpc",
    }
    REM = 2  # 固定使用 time%10==2 对应的密钥

    ADS_CODE = "DFH"

    # 播放线路（vuex.app.allConfig.h5_play_line）
    PLAY_LINES = [
        ("国线1", "https://rr.rxjhwl.com"),
        ("国线2", "https://ww.wealwelloa.com"),
        ("国线3", "https://cc.cloudworki.com"),
        ("国线4", "https://gg.gmdalian.com"),
        ("海线1", "https://allmusiclub.almusiclub.com"),
    ]

    PIC_BASE = "https://qv1tx2.shoupingxz.com"

    UA = ("Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

    # 专题分类（id -> title），作为 categoryContent 的分类来源
    THEMES = [
        ("27", "国产精选"), ("9", "主播剧情"), ("26", "业余素人"),
        ("47", "第一视角"), ("7", "欧美精选"), ("35", "日韩精选"),
        ("41", "粉嫩处女"), ("66", "偷窥偷拍监控"), ("50", "网爆偷拍泄密"),
        ("39", "AV精选"), ("40", "职业探花"), ("55", "网红裸舞"),
        ("59", "抖音风合集"), ("36", "动漫精选"), ("67", "街拍街射"),
        ("42", "明星AI换脸"), ("15", "经典老片"), ("16", "成人综艺"),
        ("24", "恐怖科幻伦理"), ("19", "官方推荐"),
    ]

    def init(self, extend=""):
        self._jwt = None
        self._jwt_ts = 0
        self._access = None
        self._access_ts = 0
        return

    def _rnd(self, n):
        import random
        cs = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(random.choice(cs) for _ in range(n))

    def getName(self):
        return "xx9"

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    # ================= 加密辅助 =================
    def _pad(self, b):
        n = 16 - (len(b) % 16)
        return b + bytes([n]) * n

    def _unpad(self, b):
        if not b:
            return b
        return b[:-b[-1]]

    def _enc(self, obj, key):
        raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        c = AES.new(key.encode('utf-8'), AES.MODE_ECB)
        return base64.b64encode(c.encrypt(self._pad(raw))).decode()

    def _dec(self, b64, key):
        c = AES.new(key.encode('utf-8'), AES.MODE_ECB)
        raw = self._unpad(c.decrypt(base64.b64decode(b64)))
        return raw.decode('utf-8')

    def _mktime(self):
        t = int(time.time() * 1000)
        return t - (t % 10) + self.REM

    # ================= 网关请求 =================
    def _call(self, uri, method, params=None, body=None, use_jwt=True, use_access=False, _retry=True):
        key = self.KEYS[self.REM]
        t = self._mktime()
        plain = {"method": method, "uri": uri}
        if body is not None:
            plain["body"] = body
        else:
            plain["params"] = params if params is not None else {}
        payload = {"data": self._enc(plain, key), "time": t}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.UA,
            "Origin": "https://xx9.com",
            "Referer": "https://xx9.com/",
        }
        if use_jwt:
            jwt = self._get_jwt()
            if jwt:
                headers["jwtToken"] = jwt
        if use_access:
            acc = self._get_access()
            if acc:
                headers["accessToken"] = acc

        text = None
        for gw in self.GATEWAY_POOL:
            try:
                rsp = self.post(gw, json=payload, headers=headers)
                text = rsp.text
                if text:
                    break
            except Exception:
                continue
        if not text:
            return {}
        try:
            j = json.loads(text)
        except Exception:
            return {}
        # 响应可能是明文，也可能是 {data:<密文>, time:..} 加密包
        if isinstance(j, dict) and isinstance(j.get("data"), str) and j.get("data") and ("time" in j):
            try:
                j = json.loads(self._dec(j["data"], key))
            except Exception:
                return j
        # accessToken 为空(1032)/过期(1019) -> 刷新后重试一次
        if use_access and _retry and isinstance(j, dict):
            code = str(j.get("code") or "")
            if code in ("1032", "1019"):
                self._access = None
                self._access_ts = 0
                return self._call(uri, method, params=params, body=body,
                                  use_jwt=use_jwt, use_access=use_access, _retry=False)
        return j

    def _get_jwt(self):
        now = time.time()
        if self._jwt and (now - self._jwt_ts) < 3600:
            return self._jwt
        try:
            r = self._call("app/jwt-token", 1, params={"adsCode": self.ADS_CODE}, use_jwt=False)
            jwt = r.get("result") if isinstance(r, dict) else None
            if jwt:
                self._jwt = jwt
                self._jwt_ts = now
        except Exception:
            pass
        return self._jwt

    def _get_access(self):
        now = time.time()
        # accessToken 缓存 30 分钟
        if self._access and (now - self._access_ts) < 1800:
            return self._access
        try:
            body = {
                "osType": "h5",
                "sign": self._rnd(32),
                "machineCode": "chrome",
                "version": "xx9.com",
            }
            r = self._call("user/register/free", 2, body=body, use_jwt=True, use_access=False)
            res = r.get("result") if isinstance(r, dict) else None
            acc = res.get("accessToken") if isinstance(res, dict) else None
            if acc:
                self._access = acc
                self._access_ts = now
        except Exception:
            pass
        return self._access

    # ================= 工具 =================
    def _abs_pic(self, p):
        if not p:
            return ""
        if p.startswith("http"):
            return p
        return self.PIC_BASE + p

    def _pic(self, p):
        # 图片 CDN 在部分客户端网络/证书环境下 Glide 直连失败，
        # 走爬虫本地代理（localProxy）由 self.fetch 带 header + verify=False 取回。
        u = self._abs_pic(p)
        if not u:
            return ""
        try:
            base = self.getProxyUrl()
        except Exception:
            base = None
        if not base:
            return u
        return base + "&url=" + quote(u, safe="") + "&type=img"

    def _vod_list_item(self, it):
        vid = it.get("id") or it.get("vodId")
        title = it.get("title") or ""
        pic = self._pic(it.get("vodPic") or it.get("gif") or "")
        dur = it.get("vodDuration")
        remark = ""
        if isinstance(dur, int) and dur > 0:
            m, s = divmod(dur, 60)
            remark = "%d:%02d" % (m, s)
        tags = it.get("tags")
        if not remark and isinstance(tags, list) and tags:
            remark = " ".join(tags[:3])
        return {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
        }

    def _search(self, params):
        r = self._call("cms/vod/search", 2, params=params)
        data = r.get("data") if isinstance(r, dict) else None
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("list") or data.get("records") or []
        total = r.get("total") if isinstance(r, dict) else 0
        return items, (total or 0)

    # ================= 首页 =================
    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.THEMES]
        filters = {}
        sort_filter = {
            "key": "sort",
            "name": "排序",
            "value": [
                {"n": "最新", "v": "1"},
                {"n": "最热", "v": "2"},
            ],
        }
        for tid, _ in self.THEMES:
            filters[tid] = [sort_filter]
        result = {
            "class": classes,
            "filters": filters,
        }
        try:
            result["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            result["list"] = []
        return result

    def homeVideoContent(self):
        items, _ = self._search({
            "themeIds": self.THEMES[0][0],
            "page": 1, "pageSize": 30,
            "explore": False, "sortType": 1,
        })
        return {"list": [self._vod_list_item(it) for it in items]}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        sort_type = 1
        if isinstance(extend, dict):
            sv = extend.get("sort")
            if sv:
                try:
                    sort_type = int(sv)
                except Exception:
                    sort_type = 1
        page_size = 30
        items, total = self._search({
            "themeIds": str(tid),
            "page": page, "pageSize": page_size,
            "explore": False, "sortType": sort_type,
        })
        vod = [self._vod_list_item(it) for it in items]
        pagecount = 9999
        if total:
            pagecount = (int(total) + page_size - 1) // page_size
        return {
            "list": vod,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": int(total) if total else len(vod),
        }

    # ================= 详情 =================
    def detailContent(self, ids):
        vid = ids[0]
        r = self._call("cms/vod/detail/%s" % vid, 1, params={"needCdnAuth": True}, use_access=True)
        res = r.get("result") if isinstance(r, dict) else None
        if isinstance(res, dict):
            vod = res.get("vod", res)
        else:
            vod = res if isinstance(res, dict) else {}
        if not vod:
            return {"list": []}

        title = vod.get("title") or ""
        pic = self._pic(vod.get("vodPic") or "")
        intro = vod.get("vodIntro") or ""
        tags = vod.get("tags")
        if isinstance(tags, list):
            tag_str = ",".join(tags)
        else:
            tag_str = ""
        dur = vod.get("vodDuration")
        remark = ""
        if isinstance(dur, int) and dur > 0:
            m, s = divmod(dur, 60)
            remark = "时长 %d:%02d" % (m, s)

        full = vod.get("vodFullPlayUrl")
        n_parts = len(full) if isinstance(full, list) and full else 1

        # 每条线路一个 from，剧集用 # 分隔，播放 id 编码为 "vid|addrIndex"
        froms = []
        urls = []
        for name, _domain in self.PLAY_LINES:
            eps = []
            if n_parts <= 1:
                eps.append("正片$%s|0" % vid)
            else:
                for i in range(n_parts):
                    eps.append("P%d$%s|%d" % (i + 1, vid, i))
            froms.append(name)
            urls.append("#".join(eps))

        vod_obj = {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
            "vod_content": intro or tag_str,
            "vod_tag": tag_str,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod_obj]}

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        items, _ = self._search({
            "title": key,
            "page": page, "pageSize": 30,
            "explore": False, "sortType": 1,
        })
        return {"list": [self._vod_list_item(it) for it in items]}

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        # id 形如 "vid|addrIndex"；flag 为线路名，用于选择域名
        vid = id
        idx = 0
        if "|" in id:
            vid, sidx = id.split("|", 1)
            try:
                idx = int(sidx)
            except Exception:
                idx = 0

        domain = None
        for name, dom in self.PLAY_LINES:
            if name == flag:
                domain = dom
                break
        if not domain:
            domain = self.PLAY_LINES[0][1]

        play_url = ""
        try:
            r = self._call("cms/vod/detail/%s" % vid, 1, params={"needCdnAuth": True}, use_access=True)
            res = r.get("result") if isinstance(r, dict) else None
            vod = res.get("vod", res) if isinstance(res, dict) else {}
            full = vod.get("vodFullPlayUrl")
            addr = None
            if isinstance(full, list) and full:
                if idx >= len(full):
                    idx = 0
                addr = full[idx].get("addr")
            if not addr:
                addr = vod.get("preview")
            if addr:
                play_url = domain + addr
        except Exception:
            play_url = ""

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": self.UA,
                "Referer": "https://xx9.com/",
            },
        }

    def _img_mime(self, b):
        if not b or len(b) < 12:
            return None
        if b[:4] == b"\x89PNG":
            return "image/png"
        if b[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if b[:6] in (b"GIF89a", b"GIF87a"):
            return "image/gif"
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "image/webp"
        return None

    def localProxy(self, param):
        # 图片代理：CDN 返回的是加密二进制（首字节=XOR key，其余字节 ^ key），
        # Glide 无法直接解码，故由爬虫端抓取后解密并透传。
        url = None
        if isinstance(param, dict):
            url = param.get("url")
        if url:
            try:
                url = unquote(url)
            except Exception:
                pass
        if not url:
            return [404, "text/plain", b""]
        headers = {
            "User-Agent": self.UA,
            "Referer": "https://xx9.com/",
        }
        try:
            rsp = self.fetch(url, headers=headers)
            raw = getattr(rsp, "content", None)
            if raw is None:
                raw = rsp.text.encode("utf-8", "ignore")
            # 原始已是明文图片则直接用，否则按 XOR 方案解密
            mime = self._img_mime(raw)
            if mime:
                return [200, mime, raw]
            if raw and len(raw) > 1:
                key = raw[0]
                table = bytes(i ^ key for i in range(256))
                img = raw[1:].translate(table)
                mime = self._img_mime(img)
                if mime:
                    return [200, mime, img]
            # 解密失败兜底：原样返回，交给客户端尝试
            return [200, "image/jpeg", raw]
        except Exception:
            return [404, "text/plain", b""]
