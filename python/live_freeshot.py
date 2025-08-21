# -*- coding: utf-8 -*-
# @Author  : Doubebly
# @Time    : 2025/8/5 09:21


import sys
import requests
import re
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return self.tv.name

    def init(self, extend):
        self.tv = TvLive()
        self.cache = {}
        pass

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def liveContent(self, url):
        return self.tv.get_tv_list(self.getProxyUrl())

    def homeContent(self, filter):
        return {}

    def homeVideoContent(self):
        return {}

    def categoryContent(self, cid, page, filter, ext):
        return {}

    def detailContent(self, did):
        return {}

    def searchContent(self, key, quick, page='1'):
        return {}

    def searchContentPage(self, keywords, quick, page):
        return {}

    def playerContent(self, flag, pid, vipFlags):
        return {}

    def localProxy(self, params):
        pid = params['pid']
        play_data = self.cache.get(pid, None)
        if play_data is None:
            play_data = self.tv.get_info(params)
            self.cache['pid'] = play_data
        # return self.tv.get_info(params)
        return play_data

    def destroy(self):
        return '正在Destroy'


class TvLive:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        self.d = [{"pid":"PenthouseBLACK","name":"Penthouse Black"},{"pid":"Extasy4K","name":"EXTASY 4K"},{"pid":"VIXEN","name":"VIXEN"},{"pid":"Penthouse","name":"Penthouse"},{"pid":"HOT-HD","name":"HOT HD"},{"pid":"PinkoClubTV","name":"Pinko Club TV"},{"pid":"NuartTV","name":"Nuart TV"},{"pid":"DesireTV","name":"Desire TV"},{"pid":"Tiny4k3","name":"Adult Tiny 4K III"},{"pid":"Tiny4k2","name":"Adult Tiny 4K II"},{"pid":"Tiny4k1","name":"Adult Tiny 4K"},{"pid":"BalkanErotic","name":"Balkan Erotic"},{"pid":"EroLuxeShemales","name":"EroLuxe Shemales"},{"pid":"Mofos","name":"Mofos"},{"pid":"cum4k","name":"CUM 4K"},{"pid":"XXL","name":"XXL"},{"pid":"4kporn4","name":"4K PORN LOVE IV"},{"pid":"4kporn3","name":"4K PORN LOVE III"},{"pid":"4kporn2","name":"4K PORN LOVE II"},{"pid":"4kporn","name":"4K PORN LOVE"},{"pid":"SecretCircleTV","name":"Secret Circle TV"},{"pid":"HOTXXL","name":"HOT XXL"},{"pid":"EvilAngel","name":"Evil Angel"},{"pid":"TransErotica","name":"Trans Erotica"},{"pid":"HOTMan","name":"HOT Man"},{"pid":"ExxxoticaTV","name":"EXXXotica"},{"pid":"SexPriveEurope","name":"SexPrivé Europe"},{"pid":"Television-X","name":"Television X"},{"pid":"Barely-Legal-TV","name":"Barely Legal TV"},{"pid":"SeXation","name":"SeXation"},{"pid":"LeoGoldTV","name":"Leo Gold TV"},{"pid":"HotPleasure","name":"Hot Pleasure"},{"pid":"LeoTV","name":"Leo TV"},{"pid":"PenthouseNN","name":"Penthouse Naughty Nights"},{"pid":"PureBabes","name":"Pure Babes"},{"pid":"ExtasyHD","name":"EXTASY TV"},{"pid":"True-Amateurs","name":"True Amateurs"},{"pid":"PenthouseAFM","name":"Penthouse After Midnight"},{"pid":"VividTV","name":"Vivid TV"},{"pid":"PenthouseTV","name":"Penthouse TV"},{"pid":"PassionXXX","name":"Passion XXX"},{"pid":"Venus","name":"Venus"},{"pid":"DorcelXXX","name":"Dorcel XXX"},{"pid":"CentoXCento","name":"Cento X Cento"},{"pid":"SuperONE","name":"Super ONE"},{"pid":"TransAngels","name":"Trans Angels"},{"pid":"SexyHOT","name":"Sexy Hot"},{"pid":"HustlerTV","name":"Hustler TV"},{"pid":"DorcelTVAfrica","name":"Dorcel TV Africa"},{"pid":"SextremeTV","name":"Sextreme"},{"pid":"MeidenvanHolland","name":"Meiden van Holland"},{"pid":"PlayboyTV","name":"Playboy TV"},{"pid":"HOTTaboo","name":"HOT Taboo"},{"pid":"PenthousePassion","name":"Penthouse Passion"},{"pid":"Babes","name":"Babes TV HD"},{"pid":"BangU","name":"Bang U"},{"pid":"Tiny4K","name":"Tiny 4K"},{"pid":"FAKETAXI","name":"FAKE TAXI"},{"pid":"BlueHustler","name":"Blue Hustler"},{"pid":"PenthouseRealityTV","name":"Penthouse Reality TV"},{"pid":"PenthouseGold","name":"Penthouse Gold"},{"pid":"XyPlus","name":"XY PLUS"},{"pid":"HOT","name":"HOT"},{"pid":"EroX-XxX","name":"EroXXX HD"},{"pid":"RedlightHD","name":"REDLIGHT HD"},{"pid":"BrazzersTVEU","name":"Brazzers TV Europe"},{"pid":"Private","name":"Private TV"},{"pid":"VividHD","name":"Vivid RED HD"},{"pid":"Dusk","name":"Dusk TV"},{"pid":"RealityKingsTV","name":"Reality Kings TV"},{"pid":"DorcelTV","name":"Dorcel TV"},{"pid":"SexPrive","name":"SexPrivé"},{"pid":"HustlerHD","name":"Hustler HD"}]
        self.name = 'FreesHot'

    def get_tv_list(self, host):
        tv_list = self.d
        d = ['#EXTM3U']
        for i in tv_list:
            pid = i['pid']
            img = 'https://logo.doube.eu.org/FreesHot/' + pid + '.png'
            name = i['name']
            d.append(f"#EXTINF:-1 tvg-id=\"{pid}\" tvg-name=\"{name}\" tvg-logo=\"{img}\" group-title=\"{self.name}\",{name}")
            d.append(f'{host}&pid={pid}')
        return '\n'.join(d)

    def get_info(self, params):
        pid = params['pid']
        res = requests.get(f'https://popcdn.day/play.php?stream={pid}', headers=self.headers)
        token = re.findall('token=(.*?)&remote', res.text)
        if len(token) == 0:
            return [302, "text/plain", None, {
                'Location': 'https://sf1-cdn-tos.huoshanstatic.com/obj/media-fe/xgplayer_doc_video/mp4/xgplayer-demo-720p.mp4'}]
        token = token[0]

        return [302, "text/plain", None,
                {'Location': f'https://moonlight.wideiptv.top/{pid}/index.fmp4.m3u8?token={token}'}]

if __name__ == '__main__':
    pass
