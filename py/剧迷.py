# -*- coding: utf-8 -*-
"""
=================================================
  刁民制作，仅供测试，测试完毕请于24小时删除。
=================================================

Gimy 劇迷 TVBox / OK影视 / 影视仓 标准 Python 源。

站点: https://gimytv.biz (MacCMS / Zanpian 主题)

特点:
1. 支持 首页/分类/搜索/详情/播放 全流程。
2. 播放解析 player_aaaa 配置里的 m3u8 直链, 通过 cookie 传递 sid 选择播放源。
3. 多线路多剧集支持, 播放源按速度排序 (快的靠前)。
4. 底部筛选器: 支持年份、排序筛选。
5. 兼容 FongMi/TV (T3) & WebHomeTV / PeekPro (T4)。
"""

import sys
import json
import re
import base64
import time
from urllib.parse import quote

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq

    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    """
    Gimy 劇迷 Spider
    MacCMS / Zanpian 主题, HTML 解析
    """

    host = 'https://gimytv.biz'

    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    # 分类列表
    classes = [
        {'type_name': '電影', 'type_id': '1'},
        {'type_name': '電視劇', 'type_id': '2'},
        {'type_name': '綜藝', 'type_id': '3'},
        {'type_name': '動漫', 'type_id': '4'},
        {'type_name': '短劇', 'type_id': '25'},
        {'type_name': '韓劇', 'type_id': '15'},
        {'type_name': '美劇', 'type_id': '16'},
        {'type_name': '日劇', 'type_id': '20'},
        {'type_name': '台劇', 'type_id': '14'},
        {'type_name': '港劇', 'type_id': '22'},
        {'type_name': '海外劇', 'type_id': '21'},
        {'type_name': '紀錄片', 'type_id': '23'},
        {'type_name': '動作片', 'type_id': '6'},
        {'type_name': '喜劇片', 'type_id': '7'},
        {'type_name': '愛情片', 'type_id': '8'},
        {'type_name': '科幻片', 'type_id': '9'},
        {'type_name': '恐怖片', 'type_id': '10'},
        {'type_name': '劇情片', 'type_id': '11'},
        {'type_name': '戰爭片', 'type_id': '12'},
        {'type_name': '動畫電影', 'type_id': '24'},
    ]

    # 播放源速度优先级 (数字越小越快, 基于实际测速结果)
    _speed_priority = {
        'HYun': 1, 'JYun': 2, 'GYun': 3, 'DYun': 4,
        'BYun': 5, 'FYun': 6, 'NYun': 7, 'MYun': 8,
        'ZYun': 9, 'DTYun': 10, 'SYun': 11, 'WYun': 12,
        'IKYun': 13, 'SZyun': 14, 'JSYun': 15, 'Uyun': 16,
    }

    # 筛选器选项
    _filter_year = [
        {'n': '全部', 'v': ''},
        {'n': '2026', 'v': '2026'},
        {'n': '2025', 'v': '2025'},
        {'n': '2024', 'v': '2024'},
        {'n': '2023', 'v': '2023'},
        {'n': '2022', 'v': '2022'},
    ]

    _filter_by = [
        {'n': '默认', 'v': ''},
        {'n': '最新上线', 'v': 'time_add'},
        {'n': '最多播放', 'v': 'hits'},
        {'n': '本周热播', 'v': 'hits_week'},
        {'n': '最新更新', 'v': 'time'},
    ]

    # ===================================================================
    #  基础方法
    # ===================================================================

    def getName(self):
        return 'Gimy劇迷'

    def init(self, extend=''):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''

    def isVideoFormat(self, url):
        return any(x in url for x in ['.m3u8', '.mp4', '.flv', '.avi', '.mkv'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ===================================================================
    #  请求封装
    # ===================================================================

    def _fetch_html(self, path, cookies=None):
        """获取页面 HTML, 支持 cookies"""
        url = path if path.startswith('http') else self.host + path
        kw = {'headers': self.header, 'timeout': 15}
        if cookies:
            kw['cookies'] = cookies
        r = self.fetch(url, **kw)
        return r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')

    # ===================================================================
    #  图片代理
    # ===================================================================

    def _wrap_pic(self, pic_url):
        """将图片 URL 包装为 localProxy 代理 URL"""
        if not pic_url:
            return ''
        if '127.0.0.1' in pic_url or 'proxy' in pic_url:
            return pic_url
        if pic_url.startswith('/'):
            pic_url = self.host + pic_url
        try:
            encoded = base64.urlsafe_b64encode(pic_url.encode('utf-8')).decode('utf-8')
            return 'http://127.0.0.1:9978/proxy?do=img&url=' + encoded
        except Exception:
            return pic_url

    # ===================================================================
    #  首页
    # ===================================================================

    def homeContent(self, filter):
        """返回分类列表和筛选器配置"""
        filters = {}
        for c in self.classes:
            tid = c['type_id']
            filters[tid] = [
                {'key': 'by', 'name': '排序', 'value': self._filter_by},
                {'key': 'year', 'name': '年份', 'value': self._filter_year},
            ]
        return {'class': self.classes, 'filters': filters}

    def homeVideoContent(self):
        try:
            html = self._fetch_html('/')
            vod_list = self._parse_cards(html)
            return {'list': vod_list[:30]}
        except Exception:
            return {'list': []}

    # ===================================================================
    #  分类内容
    # ===================================================================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)

            # 解析筛选器参数
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            by = ext.get('by', '')
            year = ext.get('year', '')

            # 构建 vodshow URL
            # 格式: /vodshow/{tid}-{class}-{by}-{area}-{lang}-{letter}-{?}-{?}-{page}-{?}-{?}-{year}.html
            # 共12个字段, 位置: 0=tid, 2=by, 8=page, 11=year
            fields = [str(tid), '', str(by), '', '', '', '', '', str(pg), '', '', str(year)]
            url = '/vodshow/' + '-'.join(fields) + '.html'

            html = self._fetch_html(url)
            vod_list = self._parse_cards(html)
            pagecount = self._parse_pagecount(html)

            return {
                'page': pg,
                'pagecount': pagecount,
                'limit': len(vod_list),
                'total': pagecount * 30 if pagecount < 999 else 99999,
                'list': vod_list,
            }
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}

    def _parse_pagecount(self, html):
        """从分页 HTML 中解析总页数"""
        try:
            # 找 /vodshow/xxx--------数字--- 中的最大数字 (分页位置在字段8)
            nums = re.findall(r'/vodshow/\d+--[\w]*--------(\d+)---', html)
            if nums:
                return max(int(n) for n in nums)
            # 找 /vodtype/xxx-数字.html 中的最大数字
            nums2 = re.findall(r'/vodtype/\d+-(\d+)\.html', html)
            if nums2:
                return max(int(n) for n in nums2)
            # 找页码文本
            info = re.search(r'共\s*(\d+)\s*[頁页]', html)
            if info:
                return int(info.group(1))
            # 如果有 "下一頁" 链接, 说明还有更多页
            if '下一頁' in html or 'next' in html.lower():
                return 999
        except Exception:
            pass
        return 1

    # ===================================================================
    #  详情页
    # ===================================================================

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            html = self._fetch_html('/voddetail/%s.html' % vod_id)

            # 标题
            vod_name = ''
            title_match = re.search(r'<title>(.*?)</title>', html, re.S)
            if title_match:
                vod_name = title_match.group(1).strip()
                vod_name = re.sub(r'\s*線上看.*$', '', vod_name)
                vod_name = re.sub(r'\s*\|\s*Gimy.*$', '', vod_name)

            # 描述
            vod_content = ''
            desc = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
            if desc:
                vod_content = desc.group(1)

            # 封面图
            vod_pic = ''
            og = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
            if og:
                vod_pic = og.group(1)
            if not vod_pic:
                bg = re.search(r'background:\s*url\((/upload/[^)]+\.(?:jpg|png|webp))\)', html)
                if bg:
                    vod_pic = bg.group(1)
            if not vod_pic:
                pic_m = re.search(r'data-original="(/upload/[^"]+\.(?:jpg|png|webp))"', html)
                if pic_m:
                    vod_pic = pic_m.group(1)
            if vod_pic and vod_pic.startswith('/'):
                vod_pic = self.host + vod_pic
            vod_pic = self._wrap_pic(vod_pic)

            # 年份
            vod_year = ''
            year_m = re.search(r'(\d{4})', html[:5000])
            if year_m:
                vod_year = year_m.group(1)

            # 类别
            vod_class = ''
            class_m = re.search(r'類別：([^<]+)', html)
            if class_m:
                vod_class = class_m.group(1).strip()

            # 地区
            vod_area = ''
            area_m = re.search(r'地區：([^<]+)', html)
            if area_m:
                vod_area = re.sub(r'<[^>]+>', '', area_m.group(1)).strip()

            # 演员
            vod_actor = ''
            actor_m = re.search(r'主演：\s*</[^>]+>\s*(.*?)(?:</div>|<br|</li)', html, re.S)
            if actor_m:
                vod_actor = re.sub(r'<[^>]+>', '', actor_m.group(1)).strip()

            # 导演
            vod_director = ''
            director_m = re.search(r'導演：\s*</[^>]+>\s*(.*?)(?:</div>|<br|</li)', html, re.S)
            if director_m:
                vod_director = re.sub(r'<[^>]+>', '', director_m.group(1)).strip()

            # 提取播放源和剧集
            play_from_list = []
            play_url_list = []

            # 解析播放源: 按 playlist-mobile 分割
            blocks = html.split('playlist-mobile')
            for block in blocks[1:]:
                # 提取源名
                src_m = re.search(r'<a[^>]*>([^<]+)</a>', block[:200])
                if not src_m:
                    continue
                source_name = src_m.group(1).strip()

                # 提取 sid
                sid_m = re.search(r'con_playlist_(\d+)', block[:300])
                sid = sid_m.group(1) if sid_m else ''

                # 截取到 </ul> 之前的内容
                ul_end = block.find('</ul>')
                if ul_end > 0:
                    ul_content = block[:ul_end]
                else:
                    ul_content = block[:500]

                # 提取剧集
                ep_links = re.findall(
                    r'href="(/video/(\d+)-(\d+)\.html(?:#sid=(\d+))?)"[^>]*>([^<]*)',
                    ul_content
                )
                if not ep_links:
                    continue

                episodes = []
                seen_eps = set()
                for url, vid, ep_num, ep_sid, ep_name in ep_links:
                    clean_name = ep_name.strip()
                    if not clean_name or clean_name in seen_eps:
                        continue
                    seen_eps.add(clean_name)
                    play_id = '%s-%s-%s' % (vid, ep_num, ep_sid or sid)
                    episodes.append('%s$%s' % (clean_name, play_id))

                if episodes:
                    play_from_list.append(source_name)
                    play_url_list.append('#'.join(episodes))

            # 如果没有找到播放源, 尝试备用方案
            if not play_from_list:
                all_play_links = re.findall(
                    r'href="(/video/(\d+)-(\d+)\.html(?:#sid=(\d+))?)"[^>]*>([^<]*)',
                    html
                )
                if all_play_links:
                    episodes = []
                    seen_eps = set()
                    for url, vid, ep_num, sid, ep_name in all_play_links:
                        clean_name = ep_name.strip()
                        if not clean_name or clean_name in seen_eps:
                            continue
                        seen_eps.add(clean_name)
                        play_id = '%s-%s-%s' % (vid, ep_num, sid or '1')
                        episodes.append('%s$%s' % (clean_name, play_id))
                    if episodes:
                        play_from_list.append('Gimy')
                        play_url_list.append('#'.join(episodes))

            # 按速度排序播放源 (快的靠前)
            if play_from_list:
                paired = list(zip(play_from_list, play_url_list))
                paired.sort(key=lambda x: self._speed_priority.get(x[0], 999))
                play_from_list = [p[0] for p in paired]
                play_url_list = [p[1] for p in paired]

            vod = {
                'vod_id': vod_id,
                'vod_name': vod_name,
                'vod_pic': vod_pic,
                'type_name': vod_class or 'Gimy',
                'vod_year': vod_year,
                'vod_area': vod_area,
                'vod_actor': vod_actor,
                'vod_director': vod_director,
                'vod_content': vod_content,
                'vod_remarks': '',
                'vod_play_from': '$$$'.join(play_from_list) if play_from_list else 'Gimy',
                'vod_play_url': '$$$'.join(play_url_list) if play_url_list else '',
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    # ===================================================================
    #  搜索
    # ===================================================================

    def searchContent(self, key, quick, pg=1):
        try:
            pg = int(pg or 1)
            encoded_key = quote(key)
            if pg == 1:
                search_path = '/vodsearch/%s-------------.html' % encoded_key
            else:
                search_path = '/vodsearch/%s----------%d---.html' % (encoded_key, pg)
            html = self._fetch_html(search_path)
            vod_list = self._parse_cards(html)

            return {
                'list': vod_list[:30],
                'page': pg,
            }
        except Exception:
            return {'list': [], 'page': 1}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    # ===================================================================
    #  播放
    # ===================================================================

    def playerContent(self, flag, id, vipFlags):
        try:
            play_id = str(id or '')

            # 解析播放 ID: vid-ep-sid
            parts = play_id.split('-')
            if len(parts) >= 3:
                vid, ep, sid = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                vid, ep, sid = parts[0], parts[1], '1'
            else:
                return {'parse': 1, 'url': play_id}

            # 访问播放页获取 player_aaaa
            # 关键: 必须通过 cookie 传递 sid, 否则服务器始终返回默认源
            play_url = '/video/%s-%s.html' % (vid, ep)
            cookies = {'sid': str(sid)}
            html = self._fetch_html(play_url, cookies=cookies)

            # 解析 player_aaaa JSON
            pa = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</', html, re.S)
            if pa:
                try:
                    data = json.loads(pa.group(1))
                    m3u8_url = data.get('url', '')
                    if m3u8_url and ('.m3u8' in m3u8_url or '.mp4' in m3u8_url):
                        return {
                            'parse': 0,
                            'url': m3u8_url,
                            'header': {
                                'User-Agent': self.header['User-Agent'],
                                'Referer': self.host + '/',
                            },
                        }
                except Exception:
                    pass

            # 尝试直接从页面提取 m3u8
            m3u8 = re.search(r'"url"\s*:\s*"(https?:[^"]*\.(?:m3u8|mp4)[^"]*)"', html)
            if m3u8:
                m3u8_url = m3u8.group(1).replace('\\/', '/')
                return {
                    'parse': 0,
                    'url': m3u8_url,
                    'header': {
                        'User-Agent': self.header['User-Agent'],
                        'Referer': self.host + '/',
                    },
                }

            # 解析失败, 交给通用解析
            return {
                'parse': 1,
                'url': self.host + play_url,
                'header': {'User-Agent': self.header['User-Agent']},
            }
        except Exception:
            return {}

    # ===================================================================
    #  本地代理 (图片代理)
    # ===================================================================

    def localProxy(self, param):
        """本地代理: 处理图片加载"""
        try:
            if isinstance(param, str):
                from urllib.parse import parse_qs
                param_dict = parse_qs(param)
            else:
                param_dict = param

            do = param_dict.get('do', '')
            if isinstance(do, list):
                do = do[0] if do else ''

            if do == 'img':
                url = param_dict.get('url', '')
                if isinstance(url, list):
                    url = url[0] if url else ''

                if url:
                    try:
                        url = base64.urlsafe_b64decode(url).decode('utf-8')
                    except Exception:
                        pass

                    if url:
                        headers = {
                            'User-Agent': self.header['User-Agent'],
                            'Referer': self.host + '/',
                            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                        }
                        r = self.fetch(url, headers=headers, timeout=15)
                        content_type = ''
                        if hasattr(r, 'headers'):
                            ct = r.headers.get('Content-Type', '')
                            if ct and 'image' in ct:
                                content_type = ct
                        if not content_type:
                            if '.png' in url:
                                content_type = 'image/png'
                            elif '.webp' in url:
                                content_type = 'image/webp'
                            elif '.gif' in url:
                                content_type = 'image/gif'
                            else:
                                content_type = 'image/jpeg'
                        content = r.content if hasattr(r, 'content') else r.text.encode('utf-8')
                        return [200, content_type, content, {}]
        except Exception:
            pass
        return [404, 'text/plain', '', {}]

    # ===================================================================
    #  卡片解析
    # ===================================================================

    def _parse_cards(self, html):
        """解析视频卡片列表"""
        vod_list = []

        # 匹配卡片: <a class="video-pic loading" data-original="..." href="/voddetail/xxx.html" title="...">
        pattern = (
            r'<a\s+class="video-pic[^"]*"\s+'
            r'data-original="([^"]*)"\s+'
            r'href="(/voddetail/(\d+)\.html)"\s+'
            r'title="([^"]*)"[^>]*>(.*?)</a>'
        )
        matches = re.findall(pattern, html, re.S)

        seen = set()
        for pic, url, vid, name, inner in matches:
            if vid in seen:
                continue
            seen.add(vid)

            pic_url = pic
            if pic_url and pic_url.startswith('/'):
                pic_url = self.host + pic_url
            pic_url = self._wrap_pic(pic_url)

            # 从卡片内部提取备注 (正片/HD/更新至xx集)
            remark = ''
            note_m = re.search(r'class="note[^"]*"[^>]*>([^<]+)', inner)
            if note_m:
                remark = note_m.group(1).strip()

            vod_list.append({
                'vod_id': vid,
                'vod_name': name.strip(),
                'vod_pic': pic_url,
                'vod_remarks': remark,
            })

        # 如果上面没匹配到, 尝试备用模式
        if not vod_list:
            pattern2 = (
                r'href="(/voddetail/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*>.*?'
                r'data-original="([^"]*)"'
            )
            matches2 = re.findall(pattern2, html, re.S)
            for url, vid, name, pic in matches2:
                if vid in seen:
                    continue
                seen.add(vid)
                pic_url = pic
                if pic_url and pic_url.startswith('/'):
                    pic_url = self.host + pic_url
                pic_url = self._wrap_pic(pic_url)
                vod_list.append({
                    'vod_id': vid,
                    'vod_name': name.strip(),
                    'vod_pic': pic_url,
                    'vod_remarks': '',
                })

        return vod_list
