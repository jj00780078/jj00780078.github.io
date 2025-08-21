# coding = utf-8
# !/usr/bin/python

"""

作者 丢丢喵 🚓 内容均从互联网收集而来 仅供交流学习使用 版权归原创者所有 如侵犯了您的权益 请通知作者 将及时删除侵权内容
                    ====================Diudiumiao====================

"""

from Crypto.Util.Padding import unpad
from urllib.parse import unquote
from Crypto.Cipher import ARC4
from urllib.parse import quote
from base.spider import Spider
from Crypto.Cipher import AES
from bs4 import BeautifulSoup
from base64 import b64decode
import urllib.request
import urllib.parse
import binascii
import requests
import base64
import json
import time
import sys
import re
import os

sys.path.append('..')

xurl = "https://light-ios.yiys04.com"

headerx = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'
          }

class Spider(Spider):
    global xurl
    global headerx

    def getName(self):
        return "首页"

    def init(self, extend):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def extract_middle_text(self, text, start_str, end_str, pl, start_index1: str = '', end_index2: str = ''):
        if pl == 3:
            plx = []
            while True:
                start_index = text.find(start_str)
                if start_index == -1:
                    break
                end_index = text.find(end_str, start_index + len(start_str))
                if end_index == -1:
                    break
                middle_text = text[start_index + len(start_str):end_index]
                plx.append(middle_text)
                text = text.replace(start_str + middle_text + end_str, '')
            if len(plx) > 0:
                purl = ''
                for i in range(len(plx)):
                    matches = re.findall(start_index1, plx[i])
                    output = ""
                    for match in matches:
                        match3 = re.search(r'(?:^|[^0-9])(\d+)(?:[^0-9]|$)', match[1])
                        if match3:
                            number = match3.group(1)
                        else:
                            number = 0
                        if 'http' not in match[0]:
                            output += f"#{match[1]}${number}{xurl}{match[0]}"
                        else:
                            output += f"#{match[1]}${number}{match[0]}"
                    output = output[1:]
                    purl = purl + output + "$$$"
                purl = purl[:-3]
                return purl
            else:
                return ""
        else:
            start_index = text.find(start_str)
            if start_index == -1:
                return ""
            end_index = text.find(end_str, start_index + len(start_str))
            if end_index == -1:
                return ""

        if pl == 0:
            middle_text = text[start_index + len(start_str):end_index]
            return middle_text.replace("\\", "")

        if pl == 1:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                jg = ' '.join(matches)
                return jg

        if pl == 2:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                new_list = [f'{item}' for item in matches]
                jg = '$$$'.join(new_list)
                return jg

    def homeContent(self, filter):
        result = {}
        result = {"class": [{"type_id": "1", "type_name": "电影"},
                            {"type_id": "2", "type_name": "剧集"},
                            {"type_id": "4", "type_name": "动漫"},
                            {"type_id": "22", "type_name": "短剧"},
                            {"type_id": "3", "type_name": "综艺"}],

                 }

        return result

    def homeVideoContent(self):
        videos = []

        detail = requests.get(url=xurl + "/api/typepage/0?", headers=headerx)
        data = detail.json()
        datas = data.get('data')

        js = datas['hots'][0]['vod_list']

        for vod in js:
            name = vod['vod_name']

            type = vod['refer']['type']

            if '电影' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/1/nid/1"
            if '电视剧' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/2/nid/1"
            if '综艺' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/3/nid/1"
            if '动漫' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/4/nid/1"
            if '短剧' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/22/nid/1"

            pic = vod['vod_pic']

            remark = vod['vod_remarks']

            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark
                     }
            videos.append(video)

        result = {'list': videos}
        return result

    def categoryContent(self, cid, pg, filter, ext):
        result = {}
        videos = []

        if pg:
            page = int(pg)
        else:
            page = 1

        if page == 1:
            url = f'{xurl}/api/vod/v1/vod/list?pageNum=1&pageSize=12&tid={cid}&by=time&area=&lang=&year=&class='

        else:
            url = f'{xurl}/api/vod/v1/vod/list?pageNum={str(page)}&pageSize=12&tid={cid}&by=time&area=&lang=&year=&class='

        detail = requests.get(url=url, headers=headerx)
        data = detail.json()
        datas = data.get('data')

        js = datas['List']

        for vod in js:
            name = vod['vod_name']

            id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/{cid}/nid/1"

            pic = vod['vod_pic']

            remark = vod['vod_remarks']

            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark
                    }
            videos.append(video)

        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        did = ids[0]
        result = {}
        videos = []

        if 'http' not in did:
            did = xurl + did

        res = requests.get(url=did, headers=headerx)
        res.encoding = "utf-8"
        res = res.text
        res = self.extract_middle_text(res, 'self.__next_f.push([1,"8:', '\\n"])', 0)
        data = json.loads(res)

        content = '为您介绍剧情📢' + data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_content']
        content = content.replace('003', '').replace('ucpue', '').replace('pueucpue', '').replace('1uc', '').replace('pue', '')

        director = data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_class']

        actor = data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_actor']

        remarks = data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_lang']

        year = data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_year']

        area = data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_area']

        xianlu = ''
        bofang = ''

        soup = data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_sources']

        for sou in soup:

            name = sou['source_name']

            xianlu = xianlu + name + '$$$'

        xianlu = xianlu[:-3]

        soup1 = data[3]['children'][0][3]['children'][2][3]['children'][0][3]['children'][0][3]['infoData']['vod_sources']
        for sou1 in soup1:
            soup2 = sou1['vod_play_list']['urls']
            for sou3 in soup2:

                name = sou3['name']

                id = sou3['url']

                bofang = bofang + name + '$' + id + '#'

            bofang = bofang[:-1] + '$$$'

        bofang = bofang[:-3]

        videos.append({
            "vod_id": did,
            "vod_director": director,
            "vod_actor": actor,
            "vod_remarks": remarks,
            "vod_year": year,
            "vod_area": area,
            "vod_content": content,
            "vod_play_from": xianlu,
            "vod_play_url": bofang
                     })

        result['list'] = videos
        return result

    def playerContent(self, flag, id, vipFlags):

        result = {}
        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = id
        result["header"] = headerx
        return result

    def searchContentPage(self, key, quick, page):
        result = {}
        videos = []

        if not page:
            page = '1'
        if page == '1':
            url = f'{xurl}/api/search?pageNum=1&pageSize=12&key={key}'

        else:
            url = f'{xurl}/api/search?pageNum={str(page)}&pageSize=12&key={key}'

        detail = requests.get(url=url, headers=headerx)
        data = detail.json()
        datas = data.get('data')

        js = datas['List']

        for vod in js:
            name = vod['vod_name']

            type = vod['type_id']

            if '电影' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/1/nid/1"
            if '电视剧' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/2/nid/1"
            if '综艺' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/3/nid/1"
            if '动漫' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/4/nid/1"
            if '短剧' in type:
                id = xurl + f"/vod/play/id/{vod['vod_id']}/sid/22/nid/1"

            pic = vod['vod_pic']

            remark = vod['vod_remarks']

            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark
                    }
            videos.append(video)

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, '1')

    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None







