#coding=utf-8
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox / 影视仓 Python 源脚本
站点: 独播库 (www.cqjmdzp.com)
技术栈: maccms (苹果CMS) + stui 速腾模板
URL特征: 所有路由带 vod 前缀 (/vodtype /vodshow /voddetail /vodsearch /vodplay)
策略: 优先使用 maccms JSON API,HTML 解析作为降级方案
"""

import sys
import re
import json
import requests
from urllib.parse import quote
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def __init__(self):
        super().__init__()
        # 站点配置
        self.site = 'https://www.cqjmdzp.com'
        self.api_url = f'{self.site}/api.php/provide/vod'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'{self.site}/'
        })
        # 分类配置 (与站点导航栏一致,含特色分类)
        self.cateManual = {
            '电影': '1',
            '电视剧': '2',
            '综艺': '3',
            '动漫': '4',
            '短剧': '20',
            '动画片': '35',
            '4K电影': '36',
            'Netflix': '37'
        }
        # URL 路由前缀 (独播库特征: 全部带 vod 前缀)
        self.url_prefix = {
            'type': '/vodtype',
            'show': '/vodshow',
            'detail': '/voddetail',
            'search': '/vodsearch',
            'play': '/vodplay'
        }
        # VIP 解析接口列表 (从解析地址文档中精选,按速度/无广告优先排序)
        # 格式: 接口地址以 ?url= 结尾,使用时拼接播放页 URL
        self.parse_urls = [
            # --- 秒播 / 无广告优先 ---
            'https://api.steak517.top/?url=',      # 秒播 无广告
            'https://api.8bjx.cn/?url=',            # 秒播 记忆播放
            'https://vip.52jiexi.top/?url=',        # 无广告 腾讯直解
            'https://jx.lfeifei.cn/?url=',          # 无广告
            'https://api.78sy.com/?url=',           # 无广告
            'https://jx.ikjiexi.com/?url=',         # 无广告
            'https://yparse.ik9.cc/?url=',          # 无广告
            'https://jx.parwix.com:4433/player/?url=',  # 无广告
            'https://jx.bozrc.com:4433/player/?url=',   # 无广告
            # --- 挺快 ---
            'https://www.33tn.cn/?url=',
            'https://jiexi.380k.com/?url=',
            'https://cn.bjbanshan.cn/jx.php?url=',
            'https://jx.mw0.cc/?url=',
            'https://www.80kjj.com/?url=',
            # --- 通用备用 ---
            'https://jx.elwtc.com/?url=',
            'https://jx.m3u8.tv/jiexi/?url=',
            'https://jx.aidouer.net/?url=',
            'https://jx.xmflv.com/?url=',
            'https://jx.du2.cc/?url=',
            'https://jx.1812.top/?url=',
        ]
        # 解析接口请求超时 (秒),单个接口超过此时间则跳过下一个
        self.parse_timeout = 8

    def init(self, extend=""):
        pass

    def getName(self):
        return "独播库"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    # ============================================================
    #  首页: 返回分类列表 + 首页推荐数据
    # ============================================================
    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': [], 'parse': 0, 'jx': 0}

        # 填充分类
        for k, v in self.cateManual.items():
            result['class'].append({
                'type_id': str(v),
                'type_name': k
            })

        # 填充筛选器
        result['filters'] = self._build_filters()

        # 获取首页推荐数据
        try:
            api_data = self._fetch_api_list(tid='1', page=1)
            if api_data:
                result['list'] = api_data
        except Exception as e:
            print(f'homeContent API error: {e}')
            try:
                result['list'] = self._parse_html_list('1', 1)
            except Exception as e2:
                print(f'homeContent HTML fallback error: {e2}')

        return result

    # ============================================================
    #  分类页: 分页获取分类下的影片列表 (支持筛选)
    # ============================================================
    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1
        if extend is None:
            extend = {}

        # 优先使用 JSON API
        try:
            vod_list, total, pagecount = self._fetch_api_list_paged(tid, page, extend)
            result['list'] = vod_list
            result['page'] = page
            result['pagecount'] = pagecount
            result['limit'] = len(vod_list)
            result['total'] = total
            return result
        except Exception as e:
            print(f'categoryContent API error: {e}')

        # 降级: HTML 解析
        try:
            vod_list = self._parse_html_list(tid, page, extend)
            result['list'] = vod_list
        except Exception as e2:
            print(f'categoryContent HTML fallback error: {e2}')

        result['page'] = page
        result['pagecount'] = page + 1 if len(result['list']) > 0 else page
        result['limit'] = len(result['list'])
        result['total'] = len(result['list'])
        return result

    # ============================================================
    #  详情页: 获取影片完整信息 + 播放线路与剧集
    # ============================================================
    def detailContent(self, ids):
        result = {'list': [], 'parse': 0, 'jx': 0}
        vid = ids[0] if ids else ''
        if not vid:
            return result

        # 优先使用 JSON API 获取详情
        try:
            vod = self._fetch_api_detail(vid)
            if vod:
                result['list'].append(vod)
                return result
        except Exception as e:
            print(f'detailContent API error: {e}')

        # 降级: HTML 解析
        try:
            vod = self._parse_html_detail(vid)
            if vod:
                result['list'].append(vod)
        except Exception as e2:
            print(f'detailContent HTML fallback error: {e2}')

        return result

    # ============================================================
    #  播放解析: 获取真实播放地址
    # ============================================================
    def playerContent(self, flag, id, vipFlags):
        result = {
            'parse': 0,
            'jx': 0,
            'header': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/120.0.0.0 Safari/537.36',
                'Referer': f'{self.site}/'
            }
        }

        try:
            play_url = id.strip()

            # 如果已经是直链 (m3u8/mp4) 直接返回
            if play_url.startswith('http') and re.search(r'\.(m3u8|mp4)', play_url):
                result['url'] = play_url
                result['parse'] = 0
                return result

            # 如果是相对路径,拼接站点地址
            if play_url and not play_url.startswith('http'):
                play_url = self.site + play_url

            # 请求播放页,提取真实地址
            r = self.session.get(play_url, timeout=15, verify=False)
            r.encoding = 'utf-8'
            html = r.text

            video_url = self._extract_video_url(html)

            if video_url:
                result['url'] = video_url
                result['parse'] = 0
            else:
                # 直链提取失败,尝试 VIP 解析接口轮询
                parsed_url = self._try_parse_urls(play_url)
                if parsed_url:
                    result['url'] = parsed_url
                    result['parse'] = 0
                else:
                    # 解析接口也失败,交给播放器嗅探
                    result['url'] = play_url
                    result['parse'] = 1

        except Exception as e:
            print(f'playerContent error: {e}')
            result['url'] = id if id.startswith('http') else self.site + id
            result['parse'] = 1

        return result

    # ============================================================
    #  搜索
    # ============================================================
    def searchContent(self, key, quick, pg='1'):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1

        # 优先使用 JSON API 搜索
        try:
            vod_list, total, pagecount = self._api_search(key, page)
            result['list'] = vod_list
        except Exception as e:
            print(f'searchContent API error: {e}')
            try:
                result['list'] = self._html_search(key, page)
            except Exception as e2:
                print(f'searchContent HTML fallback error: {e2}')

        result['page'] = page
        result['pagecount'] = page + 1 if len(result['list']) > 0 else page
        result['limit'] = len(result['list'])
        result['total'] = len(result['list'])
        return result

    def localProxy(self, params):
        return [200, "video/MP2T", {}, ""]

    # ============================================================
    #  === 筛选器构建 ===
    # ============================================================

    def _build_filters(self):
        """构建 maccms 标准筛选器,对应 12 段 URL 格式"""

        CLASS_OPTIONS = [
            {"n": "全部", "v": ""},
            {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
            {"n": "恐怖", "v": "恐怖"}, {"n": "动作", "v": "动作"},
            {"n": "科幻", "v": "科幻"}, {"n": "剧情", "v": "剧情"},
            {"n": "战争", "v": "战争"}, {"n": "警匪", "v": "警匪"},
            {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"},
            {"n": "奇幻", "v": "奇幻"}, {"n": "武侠", "v": "武侠"},
            {"n": "冒险", "v": "冒险"}, {"n": "枪战", "v": "枪战"},
            {"n": "悬疑", "v": "悬疑"}, {"n": "惊悚", "v": "惊悚"},
            {"n": "经典", "v": "经典"}, {"n": "青春", "v": "青春"},
            {"n": "文艺", "v": "文艺"}, {"n": "古装", "v": "古装"},
            {"n": "历史", "v": "历史"}, {"n": "运动", "v": "运动"},
            {"n": "农村", "v": "农村"}, {"n": "儿童", "v": "儿童"},
            {"n": "网络电影", "v": "网络电影"},
        ]
        AREA_OPTIONS = [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"},
            {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"},
            {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
            {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"},
            {"n": "印度", "v": "印度"}, {"n": "意大利", "v": "意大利"},
            {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"},
            {"n": "其他", "v": "其他"},
        ]
        LANG_OPTIONS = [
            {"n": "全部", "v": ""},
            {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
            {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"},
            {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"},
            {"n": "法语", "v": "法语"}, {"n": "德语", "v": "德语"},
            {"n": "其它", "v": "其它"},
        ]
        YEAR_OPTIONS = [{"n": "全部", "v": ""}] + \
            [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]
        LETTER_OPTIONS = [{"n": "全部", "v": ""}] + \
            [{"n": c, "v": c} for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + \
            [{"n": "0-9", "v": "0-9"}]
        SORT_OPTIONS = [
            {"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"},
            {"n": "评分", "v": "score"},
        ]

        COMMON_FILTERS = [
            {"key": "area", "name": "地区", "value": AREA_OPTIONS},
            {"key": "by", "name": "排序", "value": SORT_OPTIONS},
            {"key": "class", "name": "剧情", "value": CLASS_OPTIONS},
            {"key": "lang", "name": "语言", "value": LANG_OPTIONS},
            {"key": "letter", "name": "字母", "value": LETTER_OPTIONS},
            {"key": "year", "name": "年份", "value": YEAR_OPTIONS},
        ]

        filters = {}
        for tid in self.cateManual.values():
            filters[str(tid)] = COMMON_FILTERS
        return filters

    # ============================================================
    #  === maccms JSON API 方法 ===
    # ============================================================

    def _fetch_api_list(self, tid, page):
        """通过 API 获取列表 (简版)"""
        params = {'ac': 'list', 't': str(tid), 'pg': str(page)}
        r = self.session.get(self.api_url, params=params, timeout=15, verify=False)
        data = r.json()

        vod_list = []
        for item in data.get('list', []):
            vod_list.append({
                'vod_id': str(item.get('vod_id', '')),
                'vod_name': item.get('vod_name', ''),
                'vod_pic': item.get('vod_pic', ''),
                'vod_remarks': item.get('vod_remarks', '')
            })
        return vod_list

    def _fetch_api_list_paged(self, tid, page, extend=None):
        """通过 API 获取分页列表 (支持筛选参数)"""
        if extend is None:
            extend = {}

        params = {
            'ac': 'detail',
            't': str(tid),
            'pg': str(page)
        }
        # maccms API 支持筛选参数
        if extend.get('area'):
            params['area'] = extend['area']
        if extend.get('by'):
            params['by'] = extend['by']
        if extend.get('class'):
            params['class'] = extend['class']
        if extend.get('lang'):
            params['lang'] = extend['lang']
        if extend.get('letter'):
            params['letter'] = extend['letter']
        if extend.get('year'):
            params['year'] = extend['year']

        r = self.session.get(self.api_url, params=params, timeout=15, verify=False)
        data = r.json()

        vod_list = []
        for item in data.get('list', []):
            vod_list.append({
                'vod_id': str(item.get('vod_id', '')),
                'vod_name': item.get('vod_name', ''),
                'vod_pic': item.get('vod_pic', ''),
                'vod_remarks': item.get('vod_remarks', '')
            })

        pagecount = int(data.get('pagecount', page + 1))
        total = int(data.get('total', len(vod_list)))
        return vod_list, total, pagecount

    def _fetch_api_detail(self, vid):
        """通过 API 获取影片完整详情 (含播放地址)"""
        params = {'ac': 'detail', 'ids': str(vid)}
        r = self.session.get(self.api_url, params=params, timeout=15, verify=False)
        data = r.json()

        items = data.get('list', [])
        if not items:
            return None

        item = items[0]

        # 解析播放线路
        # maccms 格式: 线路名$$$线路名2$$$...
        # vod_play_url: 剧集1$地址1#剧集2$地址2$$$剧集1$地址1#...
        play_from = []
        play_url = []

        raw_play_from = item.get('vod_play_from', '')
        raw_play_url = item.get('vod_play_url', '')

        if raw_play_from and raw_play_url:
            lines_from = raw_play_from.split('$$$')
            lines_url = raw_play_url.split('$$$')

            for i, line_name in enumerate(lines_from):
                line_name = line_name.strip()
                if not line_name:
                    continue
                if i < len(lines_url):
                    play_from.append(line_name)
                    play_url.append(lines_url[i].strip())

        # 额外字段: 年份/地区/类型等
        vod_content = item.get('vod_content', '').strip()
        # 清理 HTML 标签
        if vod_content:
            vod_content = re.sub(r'<[^>]+>', '', vod_content).strip()

        vod = {
            'vod_id': str(item.get('vod_id', vid)),
            'vod_name': item.get('vod_name', ''),
            'vod_pic': item.get('vod_pic', ''),
            'type_name': item.get('vod_class', ''),
            'vod_year': item.get('vod_year', ''),
            'vod_area': item.get('vod_area', ''),
            'vod_remarks': item.get('vod_remarks', ''),
            'vod_actor': item.get('vod_actor', ''),
            'vod_director': item.get('vod_director', ''),
            'vod_content': vod_content,
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_url)
        }
        return vod

    def _api_search(self, key, page):
        """通过 API 搜索"""
        params = {'ac': 'detail', 'wd': key, 'pg': str(page)}
        r = self.session.get(self.api_url, params=params, timeout=15, verify=False)
        data = r.json()

        vod_list = []
        for item in data.get('list', []):
            vod_list.append({
                'vod_id': str(item.get('vod_id', '')),
                'vod_name': item.get('vod_name', ''),
                'vod_pic': item.get('vod_pic', ''),
                'vod_remarks': item.get('vod_remarks', '')
            })

        pagecount = int(data.get('pagecount', page + 1))
        total = int(data.get('total', len(vod_list)))
        return vod_list, total, pagecount

    # ============================================================
    #  === HTML 解析降级方法 ===
    # ============================================================

    def _build_show_url(self, tid, page, extend=None):
        """
        构建筛选列表 URL。
        独播库格式: /vodshow/{tid}-{area}-{by}-{class}-{lang}-{letter}-{year}-...---.html
        12 段格式: tid-area-by-class-lang-letter-year-star-tag-page-?-?-
        """
        if extend is None:
            extend = {}

        area = extend.get('area', '') or ''
        by = extend.get('by', '') or ''
        class_filter = extend.get('class', '') or ''
        lang = extend.get('lang', '') or ''
        letter = extend.get('letter', '') or ''
        year = extend.get('year', '') or ''

        has_filter = any([area, by, class_filter, lang, letter, year])

        if not has_filter:
            # 无筛选: 使用 /vodtype/{tid}-{page}.html 或 /vodtype/{tid}.html
            if page > 1:
                return f'{self.site}{self.url_prefix["type"]}/{tid}-{page}.html'
            return f'{self.site}{self.url_prefix["type"]}/{tid}.html'

        # 有筛选: 使用 12 段格式
        # 段位: tid-area-by-class-lang-letter-year-?-?-page-?-
        parts = [str(tid), area, by, class_filter, lang, letter, year, '', '', str(page)]
        url_parts = '-'.join(parts)
        return f'{self.site}{self.url_prefix["show"]}/{url_parts}---.html'

    def _parse_html_list(self, tid, page, extend=None):
        """HTML 解析分类列表 (stui 模板)"""
        url = self._build_show_url(tid, page, extend)
        r = self.session.get(url, timeout=15, verify=False)
        r.encoding = 'utf-8'
        doc = pq(r.text)

        vod_list = []

        # stui 模板: .stui-vodlist__box 内含封面链接和详情
        for box in doc('.stui-vodlist__box').items():
            a = box.find('.stui-vodlist__thumb')
            href = a.attr('href') or ''
            vid = self._extract_vid(href)
            if not vid:
                continue

            title = a.attr('title') or ''
            if not title:
                title = box.find('.stui-vodlist__detail h4 a').attr('title') or \
                        box.find('.stui-vodlist__detail h4 a').text() or ''
            title = title.strip()
            if not title:
                continue

            pic = a.attr('data-original') or ''
            pic = self._fix_url(pic)

            note = box.find('.pic-text').eq(0).text().strip()

            vod_list.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': note
            })

        # 同时处理文字列表 (.stui-vodlist__text)
        for li in doc('.stui-vodlist__text li').items():
            a = li.find('a')
            href = a.attr('href') or ''
            vid = self._extract_vid(href)
            if not vid:
                continue
            title = a.attr('title') or a.text().strip()
            if not title:
                continue
            note = li.find('span.text-muted').eq(0).text().strip()
            vod_list.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': '',
                'vod_remarks': note
            })

        return vod_list

    def _parse_html_detail(self, vid):
        """HTML 解析详情页 (stui 模板)"""
        url = f'{self.site}{self.url_prefix["detail"]}/{vid}.html'
        r = self.session.get(url, timeout=15, verify=False)
        r.encoding = 'utf-8'
        html = r.text
        doc = pq(html)

        # 标题: 优先从 h1 或 .stui-content__detail 获取
        title = ''
        h1 = doc('.stui-content__detail h1, .stui-pannel__head h1, h1.title').eq(0)
        if h1.length:
            title = h1.text().strip()
        if not title:
            title_match = re.search(r'<title>(.+?)</title>', html)
            if title_match:
                title = title_match.group(1).split('-')[0].split('_')[0].strip()

        # 封面
        pic = ''
        pic_elem = doc('.stui-content__thumb, .stui-vodlist__thumb').eq(0)
        if pic_elem.length:
            pic = pic_elem.attr('data-original') or pic_elem.attr('src') or ''
            pic = self._fix_url(pic)

        # 详情字段 (stui 模板: .stui-content__detail 内的 p 标签)
        detail = doc('.stui-content__detail')
        type_name = ''
        vod_year = ''
        vod_area = ''
        vod_actor = ''
        vod_director = ''
        vod_remarks = ''
        desc = ''

        # 遍历详情行的 label: value 结构
        for p in detail.find('p, .data').items():
            text = p.text().strip()
            if '导演' in text:
                vod_director = re.sub(r'^.*?导演[:：]?\s*', '', text).strip()
            elif '主演' in text:
                vod_actor = re.sub(r'^.*?主演[:：]?\s*', '', text).strip()
            elif '类型' in text:
                type_name = re.sub(r'^.*?类型[:：]?\s*', '', text).strip()
            elif '地区' in text:
                vod_area = re.sub(r'^.*?地区[:：]?\s*', '', text).strip()
            elif '年份' in text:
                vod_year = re.sub(r'^.*?年份[:：]?\s*', '', text).strip()
            elif '备注' in text:
                vod_remarks = re.sub(r'^.*?备注[:：]?\s*', '', text).strip()

        # 简介
        desc_elem = doc('.stui-content__desc, .desc, [class*="content-desc"]').eq(0)
        if desc_elem.length:
            desc = desc_elem.text().strip()
        else:
            desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
            if desc_match:
                desc = desc_match.group(1).strip()
        # 清理 HTML 标签
        if desc:
            desc = re.sub(r'<[^>]+>', '', desc).strip()

        # 播放线路与剧集 (stui 模板)
        play_from = []
        play_url = []

        # 方式1: stui 播放源结构
        play_tabs = doc('.stui-pannel__head .title a, .module-player-tab, .stui-player__list .title')
        play_lists = doc('.stui-content__playlist, .stui-play__list, ul[class*="playlist"]')

        if play_lists.length:
            for i, playlist in enumerate(play_lists.items()):
                episodes = []
                for ep in playlist.find('li a').items():
                    ep_text = ep.text().strip()
                    ep_href = ep.attr('href') or ''
                    if ep_text and ep_href:
                        episodes.append(f'{ep_text}${ep_href}')

                if episodes:
                    line_name = f'线路{i + 1}'
                    if i < play_tabs.length:
                        tab_text = play_tabs.eq(i).text().strip()
                        if tab_text:
                            line_name = tab_text
                    play_from.append(line_name)
                    play_url.append('#'.join(episodes))

        # 方式2: 正则匹配播放链接 (降级)
        # 独播库播放链接格式: /vodplay/{vid}-{sid}-{nid}.html
        if not play_from:
            all_play = re.findall(
                r'<a[^>]+href="(/vodplay/(\d+)-(\d+)-(\d+)\.html)"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )
            episodes_by_sid = {}
            sids_in_order = []
            seen_sids = set()

            for href, pid, sid, nid, link_html in all_play:
                text = re.sub(r'<[^>]+>', '', link_html).strip()
                if not text:
                    continue
                if sid not in episodes_by_sid:
                    episodes_by_sid[sid] = []
                episodes_by_sid[sid].append(f'{text}${href}')
                if sid not in seen_sids:
                    seen_sids.add(sid)
                    sids_in_order.append(sid)

            for sid in sids_in_order:
                if episodes_by_sid.get(sid):
                    play_from.append(f'线路{sid}')
                    play_url.append('#'.join(episodes_by_sid[sid]))

        vod = {
            'vod_id': str(vid),
            'vod_name': title,
            'vod_pic': pic,
            'type_name': type_name,
            'vod_year': vod_year,
            'vod_area': vod_area,
            'vod_remarks': vod_remarks,
            'vod_actor': vod_actor,
            'vod_director': vod_director,
            'vod_content': desc,
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_url)
        }
        return vod

    def _html_search(self, key, page):
        """HTML 搜索解析 (stui 模板)"""
        # 独播库搜索: /vodsearch/-------------.html?wd=关键词
        url = f'{self.site}{self.url_prefix["search"]}/-------------.html?wd={quote(key)}'
        if page > 1:
            url = f'{self.site}{self.url_prefix["search"]}/{quote(key)}----------{page}---.html'

        r = self.session.get(url, timeout=15, verify=False)
        r.encoding = 'utf-8'
        doc = pq(r.text)

        vod_list = []
        for box in doc('.stui-vodlist__box, .stui-vodlist__item').items():
            a = box.find('.stui-vodlist__thumb')
            if not a.length:
                a = box.find('a').eq(0)
            href = a.attr('href') or ''
            vid = self._extract_vid(href)
            if not vid:
                continue

            title = a.attr('title') or box.find('h4 a').text() or ''
            title = title.strip()
            if not title:
                continue

            pic = a.attr('data-original') or ''
            pic = self._fix_url(pic)

            note = box.find('.pic-text').eq(0).text().strip()

            vod_list.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': note
            })

        return vod_list

    # ============================================================
    #  === 工具方法 ===
    # ============================================================

    def _extract_vid(self, url):
        """从 URL 中提取影片 ID"""
        if not url:
            return ''
        # 独播库格式: /voddetail/{vid}.html
        m = re.search(r'/voddetail/(\d+)\.html', url)
        if m:
            return m.group(1)
        # 播放页: /vodplay/{vid}-{sid}-{nid}.html
        m = re.search(r'/vodplay/(\d+)-', url)
        if m:
            return m.group(1)
        # 通用: /video/{vid}.html (兼容)
        m = re.search(r'/video/(\d+)\.html', url)
        if m:
            return m.group(1)
        return ''

    def _fix_url(self, url):
        """修复相对 URL"""
        if not url:
            return ''
        url = url.strip()
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.site + url
        return url

    def _extract_video_url(self, html):
        """从播放页 HTML 中提取真实视频地址"""
        patterns = [
            r'src["\']?\s*[:=]\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',
            r'"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"',
            r"url\s*:\s*'([^']+\.(?:m3u8|mp4)[^']*)'",
            r'data-url="([^"]+\.(?:m3u8|mp4)[^"]*)"',
        ]

        for pat in patterns:
            m = re.search(pat, html, re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(1)

        # 全文扫描所有 m3u8/mp4 链接
        all_urls = re.findall(
            r'https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*',
            html, re.IGNORECASE
        )
        if all_urls:
            for u in all_urls:
                if 'index.m3u8' in u or 'video.m3u8' in u or '.mp4' in u:
                    return u
            return all_urls[0]

        return ''

    def _try_parse_urls(self, play_url):
        """
        逐个尝试 VIP 解析接口,从返回内容中提取真实视频直链。
        策略: 按 self.parse_urls 顺序请求,成功提取到 m3u8/mp4 即返回。
        单个接口超时 self.parse_timeout 秒后跳过下一个。
        """
        if not play_url or not self.parse_urls:
            return ''

        for parse_base in self.parse_urls:
            try:
                parse_full = parse_base + play_url
                r = self.session.get(
                    parse_full,
                    timeout=self.parse_timeout,
                    verify=False,
                    allow_redirects=True
                )
                r.encoding = 'utf-8'
                html = r.text

                # 复用 _extract_video_url 提取直链
                video_url = self._extract_video_url(html)
                if video_url:
                    return video_url

                # 额外检查: 部分解析接口返回 JSON
                try:
                    data = r.json()
                    for key in ('url', 'data', 'src', 'video', 'm3u8'):
                        val = data.get(key, '')
                        if isinstance(val, str) and re.search(r'\.(m3u8|mp4)', val, re.IGNORECASE):
                            return val
                        if isinstance(val, dict):
                            inner = val.get('url', '') or val.get('src', '')
                            if isinstance(inner, str) and re.search(r'\.(m3u8|mp4)', inner, re.IGNORECASE):
                                return inner
                except Exception:
                    pass

            except Exception as e:
                print(f'parse_url failed [{parse_base}]: {e}')
                continue

        return ''
