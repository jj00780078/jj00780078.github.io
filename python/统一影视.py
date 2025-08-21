# -*- coding: utf-8 -*-
# 统一影视爬虫 - https://tyys2.com/ (精简版)
# 作者: AI Assistant
# 说明: 基于PyramidStore框架的影视爬虫，精简优化版本

import sys
import re
import json
import urllib.parse
import os

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.host = 'https://tyys2.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def getName(self):
        return "统一影视"

    def _extract_video_info(self, element):
        """提取视频信息"""
        try:
            # 获取视频链接和ID
            link_elem = element.xpath('.//a[@class="public-list-exp"]/@href')
            if not link_elem:
                return None

            link = link_elem[0]
            vod_id = self.regStr(r'/detail/id/(\d+)\.html', link)
            if not vod_id:
                return None

            # 获取标题
            title_selectors = [
                './/a[@class="time-title"]/text()',
                './/a[contains(@class,"time-title")]/text()',
                './/a[@class="public-list-exp"]/@title'
            ]

            title = ''
            for title_selector in title_selectors:
                title_elem = element.xpath(title_selector)
                if title_elem:
                    title = title_elem[0].strip()
                    break

            # 获取封面图片
            pic_elem = element.xpath('.//img/@data-src | .//img/@src')
            pic = ''
            for pic_url in pic_elem:
                if pic_url and not pic_url.startswith('data:'):
                    pic = pic_url
                    if not pic.startswith('http'):
                        pic = self.host + pic
                    break

            # 获取更新状态
            remarks_selectors = [
                './/span[@class="public-list-prb"]/text()',
                './/span[contains(@class,"public-list-prb")]/text()',
                './/div[@class="public-list-subtitle"]/text()'
            ]

            remarks = ''
            for remarks_selector in remarks_selectors:
                remarks_elem = element.xpath(remarks_selector)
                if remarks_elem:
                    remarks = remarks_elem[0].strip()
                    break

            if title and vod_id:
                return {
                    'vod_id': vod_id,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remarks,
                    'vod_year': ''
                }
        except Exception as e:
            self.log(f"解析视频信息出错: {str(e)}")
        return None

    def homeContent(self, filter):
        """获取首页内容和分类"""
        result = {}
        
        # 定义分类
        classes = [
            {'type_name': '电视剧', 'type_id': '1'},
            {'type_name': '电影', 'type_id': '2'},
            {'type_name': '动漫', 'type_id': '3'},
            {'type_name': '综艺', 'type_id': '4'},
            {'type_name': '体育赛事', 'type_id': '5'},
            {'type_name': '短剧', 'type_id': '41'},
        ]
        result['class'] = classes
        
        # 获取首页推荐内容
        try:
            rsp = self.fetch(self.host, headers=self.headers)
            content = rsp.text
            doc = self.html(content)

            # 提取推荐视频
            video_elements = doc.xpath('//div[contains(@class,"public-list-box")]')
            videos = []
            for element in video_elements:
                video_info = self._extract_video_info(element)
                if video_info:
                    videos.append(video_info)
            
            result['list'] = videos
            
        except Exception as e:
            self.log(f"获取首页内容出错: {str(e)}")
            result['list'] = []
        
        return result

    def categoryContent(self, tid, pg, filter, extend):
        """获取分类内容"""
        result = {}
        videos = []
        
        try:
            # 构建分类页面URL
            if pg == '1':
                url = f"{self.host}/index.php/vod/type/id/{tid}.html"
            else:
                url = f"{self.host}/index.php/vod/type/id/{tid}/page/{pg}.html"
            
            rsp = self.fetch(url, headers=self.headers)
            content = rsp.text
            doc = self.html(content)
            
            # 解析视频列表
            video_elements = doc.xpath('//div[contains(@class,"public-list-box")]')
            for element in video_elements:
                video_info = self._extract_video_info(element)
                if video_info:
                    videos.append(video_info)
            
            result['list'] = videos
            result['page'] = pg
            result['pagecount'] = 999
            result['limit'] = 20
            result['total'] = 999 * 20
            
        except Exception as e:
            self.log(f"获取分类内容出错: {str(e)}")
            result['list'] = []
            result['page'] = pg
            result['pagecount'] = 1
            result['limit'] = 20
            result['total'] = 0
        
        return result

    def _parse_play_sources(self, doc):
        """解析播放源 - 精简版"""
        play_from = []
        play_url = []
        
        # 查找所有播放链接，按sid分组
        all_episodes = doc.xpath('//a[contains(@href,"/vod/play/")]')
        sid_groups = {}
        
        for ep in all_episodes:
            ep_url = ep.xpath('./@href')[0] if ep.xpath('./@href') else ''
            ep_title = ep.xpath('./text()')[0] if ep.xpath('./text()') else ''
            
            if ep_url:
                sid_match = re.search(r'/sid/(\d+)/', ep_url)
                if sid_match:
                    sid = sid_match.group(1)
                    if sid not in sid_groups:
                        sid_groups[sid] = []
                    sid_groups[sid].append((ep_title, ep_url))
        
        # 播放源名称映射
        sid_names = {
            '9': '超清', '6': '蓝光5', '7': '备用1', '4': '备用2',
            '8': '备用3', '1': '备用4', '2': '备用5', '3': '1080', 
            '5': '播放源5', '10': '播放源10', '11': '播放源11', '12': '播放源12'
        }
        
        # 快速质量排序
        def get_priority(sid, source_name):
            if sid == '3' or '1080' in source_name.lower():
                return 1  # 1080P最高优先级
            elif sid == '9':
                return 2  # 超清
            elif sid == '6':
                return 3  # 蓝光5
            elif sid == '7':
                return 4  # 备用1
            elif sid == '4':
                return 5  # 备用2
            elif sid == '5':
                return 6  # 播放源5
            elif sid == '1':
                return 7  # 备用4
            elif sid == '2':
                return 8  # 备用5
            else:
                return 9  # 其他
        
        # 排序并生成播放源
        sorted_sids = sorted(sid_groups.keys(), 
                           key=lambda x: get_priority(x, sid_names.get(x, f'播放源{x}')))
        
        used_names = set()
        for sid in sorted_sids:
            episodes = sid_groups[sid]
            if episodes:
                source_name = sid_names.get(sid, f'播放源{sid}')
                
                # 智能重命名
                if sid == '3':
                    base_name = "1080"
                elif sid == '9':
                    base_name = "超清"
                elif sid == '6':
                    base_name = "蓝光5"
                else:
                    base_name = source_name
                
                # 确保唯一性
                final_name = base_name
                counter = 1
                while final_name in used_names:
                    final_name = f"{base_name}_{counter}"
                    counter += 1
                used_names.add(final_name)
                
                # 添加SID标识确保播放时正确识别
                display_name = f"{final_name}[SID:{sid}]"
                play_from.append(display_name)
                
                episode_list = []
                for ep_title, ep_url in episodes:
                    if ep_title and ep_url:
                        episode_list.append(f"{ep_title}${ep_url}")
                
                play_url.append('#'.join(episode_list))
        
        return play_from, play_url

    def searchContent(self, key, quick, pg="1"):
        """搜索内容"""
        result = {}
        videos = []

        try:
            # 构建搜索URL
            search_url = f"{self.host}/index.php/vod/search.html"
            search_data = {'wd': key, 'submit': ''}

            rsp = self.post(search_url, data=search_data, headers=self.headers)
            content = rsp.text
            doc = self.html(content)

            # 解析搜索结果
            search_links = doc.xpath('//a[contains(@href,"/detail/id/")]')
            self.log(f"找到 {len(search_links)} 个搜索链接")

            for link in search_links:
                try:
                    href = link.xpath('./@href')[0] if link.xpath('./@href') else ''
                    if not href:
                        continue

                    vod_id = self.regStr(r'/detail/id/(\d+)\.html', href)
                    if not vod_id:
                        continue

                    # 获取标题
                    title = link.xpath('./@title | ./text()')[0] if link.xpath('./@title | ./text()') else ''
                    title = title.strip()

                    if title and vod_id and len(title) > 2:
                        videos.append({
                            'vod_id': vod_id,
                            'vod_name': title,
                            'vod_pic': '',
                            'vod_remarks': '',
                            'vod_year': ''
                        })

                except Exception as e:
                    continue

            result['list'] = videos

        except Exception as e:
            self.log(f"搜索出错: {str(e)}")
            result['list'] = []

        return result

    def detailContent(self, ids):
        """获取详情内容"""
        result = {}
        videos = []

        try:
            for vod_id in ids:
                detail_url = f"{self.host}/index.php/vod/detail/id/{vod_id}.html"
                rsp = self.fetch(detail_url, headers=self.headers)
                content = rsp.text
                doc = self.html(content)

                # 获取基本信息
                title_elem = doc.xpath('//h1[@class="slide-info-title"]/text() | //h1/text()')
                title = title_elem[0].strip() if title_elem else ''

                pic_elem = doc.xpath('//div[@class="slide-info-pic"]//img/@src | //img[@class="lazy"]/@data-src')
                pic = pic_elem[0] if pic_elem else ''
                if pic and not pic.startswith('http'):
                    pic = self.host + pic

                # 获取描述信息
                desc_elem = doc.xpath('//div[@class="slide-info-desc"]/text() | //div[@class="desc"]/text()')
                desc = desc_elem[0].strip() if desc_elem else ''

                # 获取演员、导演等信息
                info_texts = doc.xpath('//div[@class="slide-info"]//text()')
                director = ''
                actor = ''
                for text in info_texts:
                    if '导演：' in text:
                        director = text.replace('导演：', '').strip()
                    elif '主演：' in text:
                        actor = text.replace('主演：', '').strip()

                # 获取播放列表
                play_from, play_url = self._parse_play_sources(doc)

                video_info = {
                    'vod_id': vod_id,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': '',
                    'vod_year': '',
                    'vod_area': '',
                    'vod_director': director,
                    'vod_actor': actor,
                    'vod_content': desc,
                    'vod_play_from': '$$$'.join(play_from),
                    'vod_play_url': '$$$'.join(play_url)
                }
                videos.append(video_info)

            result['list'] = videos

        except Exception as e:
            self.log(f"获取详情出错: {str(e)}")
            result['list'] = []

        return result

    def _extract_video_url(self, content):
        """提取视频URL"""
        # 常见的视频URL模式
        patterns = [
            r'"url":\s*"([^"]*\.m3u8[^"]*)"',
            r'"url":\s*"([^"]*\.mp4[^"]*)"',
            r'src\s*=\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'src\s*=\s*["\']([^"\']*\.mp4[^"\']*)["\']',
            r'video_url\s*=\s*["\']([^"\']*)["\']',
            r'playurl\s*=\s*["\']([^"\']*)["\']'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match and ('m3u8' in match or 'mp4' in match):
                    # 解码URL
                    try:
                        decoded_url = urllib.parse.unquote(match)
                        if decoded_url.startswith('http'):
                            return decoded_url
                    except:
                        if match.startswith('http'):
                            return match
        return ''

    def playerContent(self, flag, id, vipFlags):
        """获取播放链接"""
        result = {}

        try:
            # 解析播放源SID
            expected_sid = None
            if flag and '[SID:' in flag and ']' in flag:
                sid_match = re.search(r'\[SID:(\d+)\]', flag)
                if sid_match:
                    expected_sid = sid_match.group(1)

            play_url = self.host + id if id.startswith('/index.php/vod/play/') else self.host + id
            rsp = self.fetch(play_url, headers=self.headers)
            content = rsp.text

            # 查找iframe中的视频链接
            iframe_pattern = r'<iframe[^>]*src=["\']([^"\']*)["\'][^>]*>'
            iframe_matches = re.findall(iframe_pattern, content, re.IGNORECASE)

            for iframe_url in iframe_matches:
                if iframe_url and 'player' in iframe_url.lower():
                    if not iframe_url.startswith('http'):
                        iframe_url = urllib.parse.urljoin(self.host, iframe_url)

                    iframe_rsp = self.fetch(iframe_url, headers=self.headers)
                    iframe_content = iframe_rsp.text

                    video_url = self._extract_video_url(iframe_content)
                    if video_url:
                        result['parse'] = 0
                        result['playUrl'] = ''
                        result['url'] = video_url
                        result['header'] = {}
                        return result

            # 直接在页面中查找视频URL
            video_url = self._extract_video_url(content)
            if video_url:
                result['parse'] = 0
                result['playUrl'] = ''
                result['url'] = video_url
                result['header'] = {}
                return result

        except Exception as e:
            self.log(f"获取播放链接出错: {str(e)}")

        return result

    def isVideoFormat(self, url):
        """判断是否为视频格式"""
        pass

    def manualVideoCheck(self):
        """手动视频检查"""
        pass

    def destroy(self):
        """销毁"""
        pass

    def localProxy(self, param):
        """本地代理"""
        return None
