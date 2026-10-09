#coding=utf-8
#!/usr/bin/python
"""YouTube source with 512KB Super-Chunk Engine & Anti-Stall Protection (Build 2026.10.04-v3.8)."""
import re
import os
import sys
import json
import html
import time
import base64
import hashlib
import threading
import random
from datetime import datetime, timezone
from urllib.parse import quote, unquote, parse_qs, urlencode, urlparse, urlunparse, urljoin

import copy
import requests
from base.spider import Spider

sys.path.append('..')

DEBUG_LOG = '/sdcard/Download/youtube-sabr-1_debug.log'
DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

DEFAULT_0YTB_JSON = {'recommend': 'LIST:Michael Jackson Vevo cinematic story official music video,Vevo official music video story short film,Michael Jackson Thriller Beat It Smooth Criminal official video', 'class': [{'type_id': 'music', 'type_name': '🎵音乐MV'}, {'type_id': 'channel', 'type_name': '🆘频道主'}, {'type_id': 'short_drama', 'type_name': '短剧'}, {'type_id': 'tv_drama', 'type_name': '电视剧'}, {'type_id': 'movie', 'type_name': '电影'}, {'type_id': 'variety', 'type_name': '综艺'}, {'type_id': 'documentary', 'type_name': '纪录片'}, {'type_id': 'live24h', 'type_name': '24小时直播'}, {'type_id': 'anime', 'type_name': '动画片'}, {'type_id': 'sports', 'type_name': '体育赛事'}, {'type_id': 'fashion', 'type_name': '时尚潮流'}, {'type_id': 'hdr', 'type_name': '4K HDR'}, {'type_id': 'science', 'type_name': '科普宇宙'}, {'type_id': 'explain', 'type_name': '影视解说'}], 'filters': {'channel': [{'key': 'tid', 'name': '频道精选', 'value': [{'n': '全部', 'v': 'LIST:LT視界,王志安,柴静 Chai Jing,汀见,硅谷101,BBC News 中文,李肅Hi5第一頻道,崔永元,老高與小茉,自说自话的总裁,老肉雜談,滇西小哥,老饭骨,小高姐,Mr Beast,Mark Rober,不良林,悟空的日常'}, {'n': '柴静', 'v': '柴静 Chai Jing'}, {'n': '王志安', 'v': '王志安'}, {'n': '老高与小茉', 'v': '老高與小茉 @laogao'}, {'n': '自说自话的总裁', 'v': '自说自话的总裁'}, {'n': '李永乐老师', 'v': '李永樂老師 @TchLiyongle'}, {'n': '滇西小哥', 'v': '滇西小哥 @dianxixiaoge'}, {'n': '老饭骨', 'v': '老饭骨'}, {'n': '小高姐', 'v': '小高姐的 Magic Ingredients'}, {'n': 'Mr Beast', 'v': 'Mr Beast @MrBeast'}, {'n': 'Mark Rober', 'v': 'Mark Rober @MarkRober'}, {'n': '不良林', 'v': '不良林'}, {'n': '涌哥侃侃', 'v': '涌哥侃侃 @ygkkk'}]}], 'short_drama': [{'key': 'year', 'name': '年份', 'value': [{'n': '全部', 'v': ''}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}]}, {'key': 'tid', 'name': '平台/地区', 'value': [{'n': '全部', 'v': '短剧'}, {'n': '抖音短剧', 'v': '抖音 短剧'}, {'n': '快手短剧', 'v': '快手 短剧'}, {'n': '大陆短剧', 'v': '大陆 短剧'}, {'n': '香港短剧', 'v': '香港 短剧'}, {'n': '台湾短剧', 'v': '台湾 短剧'}, {'n': '腾讯短剧', 'v': '腾讯 短剧'}, {'n': '爱奇艺短剧', 'v': '爱奇艺 短剧'}, {'n': '优酷短剧', 'v': '优酷 短剧'}, {'n': '芒果TV短剧', 'v': '芒果TV 短剧'}]}, {'key': 'topic', 'name': '题材/剧场', 'value': [{'n': '全部', 'v': ''}, {'n': '都市', 'v': '@Urbanshort-TV 都市 短剧'}, {'n': '爱情', 'v': '爱情 短剧'}, {'n': '复仇', 'v': '复仇 短剧'}, {'n': '穿越', 'v': '穿越 短剧'}, {'n': '喜剧', 'v': '喜剧 短剧'}, {'n': '奇幻', 'v': '奇幻 短剧'}, {'n': '九酱爱追剧', 'v': '@NineSauceDramaTV'}, {'n': '百万好剧场', 'v': '@1-pw5ox'}, {'n': '咖啡追剧', 'v': '@coffeedrama605'}, {'n': '斗罗短剧', 'v': '@DouluoDrama123 斗罗短剧'}, {'n': '嘟嘟剧场', 'v': '@DUDUJUCHANG'}, {'n': '牛牛短剧', 'v': '@niuniuduanju'}]}], 'tv_drama': [{'key': 'year', 'name': '年份', 'value': [{'n': '全部', 'v': ''}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '经典', 'v': '经典 电视剧'}]}, {'key': 'tid', 'name': '地区/平台', 'value': [{'n': '全部', 'v': '电视剧 剧集'}, {'n': '华语热播', 'v': '华语热播电视剧官方频道'}, {'n': 'TVB', 'v': '@TVB 粤剧 剧集'}, {'n': '国剧放映社', 'v': '国剧放映社'}, {'n': '腾讯剧集', 'v': '腾讯 剧集'}, {'n': '爱奇艺剧集', 'v': '爱奇艺 剧集'}, {'n': '优酷剧集', 'v': '优酷 剧集'}, {'n': '芒果TV', 'v': '芒果TV 剧集'}, {'n': '美剧(Full)', 'v': '美国 Full Episode 完整剧集'}, {'n': 'Netflix', 'v': 'Netflix Full Episode 完整剧集'}, {'n': 'Disney+', 'v': 'disney Full Episode 完整剧集'}, {'n': 'HBO', 'v': 'hbo Full Episode 完整剧集'}, {'n': '韩剧', 'v': '韩国 剧集'}, {'n': '日剧', 'v': '日本 剧集'}]}], 'movie': [{'key': 'year', 'name': '年份', 'value': [{'n': '全部', 'v': ''}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '经典', 'v': '经典 电影'}]}, {'key': 'tid', 'name': '地区/类型', 'value': [{'n': '全部', 'v': '电影 movie'}, {'n': '华语电影', 'v': '华语 电影 Full movie'}, {'n': '港台电影', 'v': '港台 经典电影'}, {'n': 'Netflix电影', 'v': 'netflix Full movie 电影'}, {'n': '好莱坞大片', 'v': '美国 Full movie 电影'}, {'n': 'Disney', 'v': 'disney Full movie 电影'}, {'n': '韩国电影', 'v': '韩国 Full movie 电影'}, {'n': '日本电影', 'v': '日本 Full movie 电影'}]}], 'variety': [{'key': 'tid', 'name': '节目类型', 'value': [{'n': '全部', 'v': '综艺节目'}, {'n': '大陆综艺', 'v': '大陆 综艺'}, {'n': '芒果综艺', 'v': '芒果 综艺'}, {'n': '腾讯综艺', 'v': '腾讯 综艺'}, {'n': '爱奇艺综艺', 'v': '爱奇艺 综艺'}, {'n': '港台综艺', 'v': '港台 综艺'}, {'n': '韩国综艺', 'v': '韩国 综艺'}, {'n': '小品相声', 'v': '春晚小品 相声 郭德纲 岳云鹏 开心麻花'}]}], 'documentary': [{'key': 'tid', 'name': '主题', 'value': [{'n': '全部', 'v': '纪录片 documentary'}, {'n': 'BBC纪录片', 'v': 'BBC documentary 纪录片'}, {'n': '国家地理', 'v': '国家地理 纪录片 National Geographic'}, {'n': 'CCTV纪录片', 'v': 'CCTV 纪录片'}, {'n': 'Netflix纪录片', 'v': 'netflix 纪录片'}, {'n': '自然地理', 'v': '地球 大自然 纪录片'}, {'n': '宇宙天文', 'v': '宇宙 天文 纪录片'}, {'n': '历史战争', 'v': '历史 战争 纪录片'}]}], 'music': [{'key': 'tid', 'name': '风格/类型', 'value': [{'n': '全部(VEVO剧情MV)', 'v': 'Michael Jackson Vevo cinematic story official music video short film'}, {'n': 'MJ电影级叙事MV', 'v': 'Michael Jackson Thriller Beat It Smooth Criminal Remember The Time Ghosts Official Video Short Film'}, {'n': 'VEVO剧情故事MV', 'v': 'Vevo cinematic story official music video mini movie'}, {'n': '欧美殿堂VEVO精选', 'v': 'Vevo most viewed official music video HD'}, {'n': '华语剧情MV', 'v': '周杰伦 剧情 电影感 官方完整版 MV'}, {'n': '热门MV', 'v': 'YouTube 点阅率最高 华语流行歌曲'}, {'n': '经典老歌', 'v': '80 90 经典怀旧音乐'}, {'n': '粤语经典', 'v': '粤语 经典音乐'}, {'n': '车载DJ', 'v': '车载慢摇 重低音 DJ 串烧'}]}, {'key': 'singer', 'name': '歌手精选', 'value': [{'n': '全部', 'v': ''}, {'n': '迈克尔·杰克逊', 'v': 'Michael Jackson Official Video Short Film Vevo'}, {'n': 'The Weeknd (VEVO)', 'v': 'The Weeknd Vevo Official Music Video'}, {'n': 'Lady Gaga (VEVO)', 'v': 'Lady Gaga Vevo Official Music Video story'}, {'n': 'Taylor Swift (VEVO)', 'v': 'Taylor Swift Vevo Official Music Video'}, {'n': 'Eminem (VEVO)', 'v': 'Eminem Vevo Official Music Video'}, {'n': '周杰伦', 'v': '周杰伦 官方完整版 MV'}, {'n': '刀郎', 'v': '刀郎 演唱会 音乐'}, {'n': '林俊杰', 'v': '林俊杰 剧情 MV'}, {'n': '邓紫棋', 'v': '邓紫棋 官方 MV'}, {'n': '张学友', 'v': '张学友 经典 MV'}]}], 'live24h': [{'key': 'tid', 'name': '直播分类', 'value': [{'n': '全部', 'v': 'live 新闻 直播'}, {'n': '中文新闻', 'v': '新闻 直播 live'}, {'n': '港台直播', 'v': '港台 直播 live'}, {'n': 'CNN', 'v': 'live CNN'}, {'n': 'BBC', 'v': 'live BBC'}, {'n': '体育直播', 'v': 'sports live 直播'}]}], 'anime': [{'key': 'tid', 'name': '类别/频道', 'value': [{'n': '全部', 'v': '国漫 动画 anime'}, {'n': '国漫3D', 'v': '国漫 3D 动画'}, {'n': '腾讯动漫', 'v': '@TencentVideoAnimation'}, {'n': '哔哩动漫', 'v': '@madebybilibili 哔哩动漫'}, {'n': '阅文动漫', 'v': '@yuewenanimation'}, {'n': '优酷动漫', 'v': '@youkuanimation 优酷动漫'}, {'n': '爱奇艺动漫', 'v': '@iQIYIAnime 爱奇艺动漫'}, {'n': '小猪佩奇', 'v': '@PeppaPigChineseOfficial 小猪佩奇 中文'}, {'n': '宝宝巴士', 'v': '宝宝巴士 儿童早教'}]}], 'sports': [{'key': 'tid', 'name': '赛事类型', 'value': [{'n': '全部', 'v': '体育 赛事 live sports'}, {'n': '足球', 'v': '足球 赛事 集锦 highlights'}, {'n': '篮球NBA', 'v': 'NBA 赛事 highlights 集锦'}, {'n': '极限运动', 'v': 'GoPro 极限运动 翼装飞行 Red Bull'}, {'n': '健身训练', 'v': '健身 运动 训练 workout'}]}], 'fashion': [{'key': 'tid', 'name': '分类', 'value': [{'n': '全部', 'v': 'T台走秀 fashion show'}, {'n': '时装秀', 'v': 'FASHION Runway 时装走秀'}, {'n': '街舞舞蹈', 'v': '街舞 机械舞 舞蹈 dance'}, {'n': '车模写生', 'v': '车模 模特 4K HDR'}]}], 'hdr': [{'key': 'tid', 'name': '画质精选', 'value': [{'n': '全部', 'v': '4K HDR 60fps 风景 演示片'}, {'n': '自然风光', 'v': '4K HDR 大自然 风景 nature'}, {'n': '城市漫步', 'v': '4K HDR city walk 城市街景'}, {'n': '动物世界', 'v': '4K HDR wildlife 动物世界'}, {'n': '放松冥想', 'v': '4K HDR 放松 冥想 睡眠 白噪音'}]}], 'science': [{'key': 'tid', 'name': '主题', 'value': [{'n': '全部', 'v': '科普 科技 宇宙'}, {'n': '黑洞与宇宙', 'v': '宇宙 黑洞 银河系 量子力学'}, {'n': '前沿科技/AI', 'v': '人工智能 AI 科技 technology'}, {'n': '航天探索', 'v': '航天 太空 火箭 Space'}]}], 'explain': [{'key': 'tid', 'name': '频道主', 'value': [{'n': '全部', 'v': '电影解说 故事解说'}, {'n': '宇哥侃故事', 'v': '@yuge 宇哥侃故事'}, {'n': '零度解说', 'v': '@lingdujieshuo 零度解说'}]}]}}

DEFAULT_LIVE_TXT = r'''
💎台灣YouTube新聞💎,#genre#
寰宇財經台,https://www.youtube.com/watch?v=yAUQQ0DhPxI
三立財經iNEWS,https://www.youtube.com/watch?v=pF507BLtbqU
東森財經新聞台,https://www.youtube.com/watch?v=1I2iq41Akmo
東森財經新聞,https://www.youtube.com/watch?v=AEBeWMM1atA
非凡新聞台,https://www.youtube.com/watch?v=wAUx3pywTt8
三立新聞台,https://www.youtube.com/watch?v=yeYC0mbSIOo
民視新聞台,https://www.youtube.com/watch?v=ylYJSBUgaMA
寰宇新聞台灣台,https://www.youtube.com/watch?v=w87VGpgd90U
東森新聞台,https://www.youtube.com/watch?v=V1p33hqPrUk
鏡電視新聞台,https://www.youtube.com/watch?v=5n0y6b0Q25o
寰宇新聞台,https://www.youtube.com/watch?v=6IquAgfvYmc
TVBS新聞台,https://www.youtube.com/watch?v=m_dhMSvUCIc
非凡財經台,https://www.youtube.com/watch?v=eA6Aczd3FZM
非凡財經,https://www.youtube.com/watch?v=xLqt2p6Dowo
TVBS財經台,https://www.youtube.com/watch?v=0an9taQ7OYM
台视新闻台,https://www.youtube.com/watch?v=9iRAqBMakXY
华视新闻台,https://www.youtube.com/watch?v=wM0g8EoUZ_E
中视新闻台,https://www.youtube.com/watch?v=TCnaIE_SAtM
公视新闻台,https://www.youtube.com/watch?v=quwqlazU-c8
中天新闻台,https://www.youtube.com/watch?v=vr3XyVCR4T0
TVBS新闻,https://m.youtube.com/@TVBSNEWS01/streams/1
东森新闻,https://m.youtube.com/@newsebc/streams/1
民视新闻,https://m.youtube.com/@FTV_News/streams/1
东森财经,https://m.youtube.com/@57ETFN/streams/2
华视新闻,https://m.youtube.com/@CtsTw/streams/1
中视新闻,https://m.youtube.com/@twctvnews/streams/1

'''

YOUTUBE_CLASSES = [
    {'type_id': '4K', 'type_name': '4K'},
    {'type_id': 'HDR', 'type_name': 'HDR'},
    {'type_id': '自然', 'type_name': '自然'},
    {'type_id': '动画片', 'type_name': '动画片'},
    {'type_id': '短剧', 'type_name': '短剧'},
    {'type_id': '剧集', 'type_name': '剧集'},
    {'type_id': '电影', 'type_name': '电影'},
    {'type_id': '纪录片', 'type_name': '纪录片'},
    {'type_id': '放松', 'type_name': '放松'},
    {'type_id': '16K HDR', 'type_name': '16K HDR'},
    {'type_id': '科技', 'type_name': '科技'},
    {'type_id': '解说', 'type_name': '解说'},
]

CATEGORY_QUERY = {
    '动画片': '动画 国漫 anime cartoon',
    '短剧': '短剧',
    '剧集': '电视剧 剧集 drama',
    '电影': '电影 movie',
    '纪录片': '纪录片 documentary',
    '放松': '放松 冥想 自然 音乐 relax meditation nature',
    '4K': '4K video',
    'HDR': 'HDR video',
    '自然': '大自然 风景 动物 世界 nature wildlife scenery',
    '16K HDR': '16K HDR video',
    '科技': '科技 technology',
    '解说': '电影解说 故事解说',
}

CATEGORY_ALIASES = {
    '動畫片': '动画片',
    '劇集': '剧集',
    '電影': '电影',
    '紀錄片': '纪录片',
    '解說': '解说',
    'movie': '电影',
    'game': '科技',
    'documentary': '纪录片',
}



def _live_b64e(text):
    return base64.urlsafe_b64encode(str(text).encode('utf-8')).decode('ascii').rstrip('=')

def _live_b64d(text):
    text = str(text or '') + '=' * (-len(str(text or '')) % 4)
    return base64.urlsafe_b64decode(text.encode('ascii')).decode('utf-8')

def _live_one(v):
    """localProxy 的参数值可能是 str 或 list，统一取第一个字符串。"""
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ''
    return v or ''

def _filter_group(key, name, pairs):
    return {
        'key': key,
        'name': name,
        'value': [{'n': '全部', 'v': ''}] + [{'n': n, 'v': v} for n, v in pairs]
    }


def _with_year(*groups):
    years = [{'n': '全部', 'v': ''}] + [{'n': str(year), 'v': str(year)} for year in range(2026, 1957, -1)]
    return [{'key': 'year', 'name': '年份', 'value': years}] + list(groups)


CATEGORY_FILTERS = {
    '动画片': _with_year(
        _filter_group('topic', '中文', [
            ('国漫', '国漫 3D 动画'), ('儿童早教', '儿童早教'), ('儿童歌曲', '儿童歌曲'),
            ('儿童音乐', '儿童音乐'), ('儿童绘画', '儿童绘画'), ('宝宝巴士', '宝宝巴士'),
            ('儿歌多多', '儿歌多多'), ('英语启蒙', '儿童英语启蒙'), ('安全教育', '儿童安全教育'),
        ]),
        _filter_group('channel', '频道', [
            ('小猪佩奇', '@PeppaPigChineseOfficial 小猪佩奇 中文'), ('CoComelon', '@CoComelon'),
            ('国漫合集', 'Anime ENG SUB 合集 国漫'), ('阅文动漫', '@yuewenanimation'),
            ('哔哩动漫', '@madebybilibili 哔哩动漫'), ('腾讯动漫', '@TencentVideoAnimation'),
            ('优酷动漫', '@youkuanimation 优酷动漫'), ('爱奇艺动漫', '@iQIYIAnime 爱奇艺动漫'),
        ])
    ),
    '短剧': _with_year(
        _filter_group('region', '地区/平台', [
            ('抖音', '抖音 短剧'), ('快手', '快手 短剧'), ('大陆', '大陆 短剧'),
            ('香港', '香港 短剧'), ('澳门', '澳门 短剧'), ('台湾', '台湾 短剧'),
            ('新加坡', '新加坡 短剧'), ('马来西亚', '马来西亚 短剧'), ('泰国', '泰国 短剧'),
            ('越南', '越南 短剧'), ('印度', '印度 短剧'), ('韩国', '韩国 短剧'),
            ('日本', '日本 短剧'), ('欧美', '欧美 短剧'), ('腾讯', '腾讯 短剧'),
            ('爱奇艺', '爱奇艺 短剧'), ('优酷', '优酷 短剧'), ('芒果', '芒果TV 短剧'), ('搜狐', '搜狐 短剧'),
        ]),
        _filter_group('topic', '题材/频道', [
            ('都市', '@Urbanshort-TV 都市 短剧'), ('爱情', '爱情 短剧'), ('复仇', '复仇 短剧'),
            ('穿越', '穿越 短剧'), ('喜剧', '喜剧 短剧'), ('奇幻', '奇幻 短剧'),
            ('九酱爱追剧', '@NineSauceDramaTV'), ('百万好剧场', '@1-pw5ox'),
            ('咖啡追剧', '@coffeedrama605'), ('斗罗短剧', '@DouluoDrama123 斗罗短剧'),
            ('嘟嘟剧场', '@DUDUJUCHANG'), ('牛牛短剧', '@niuniuduanju'),
        ])
    ),
    '剧集': _with_year(
        _filter_group('region', '中文', [
            ('华语热播', '华语热播电视剧官方频道'), ('粤剧', '粤剧 剧集'), ('TVB', '@TVB'),
            ('国剧放映社', '国剧放映社'), ('大陆', '大陆 剧集'), ('腾讯', '腾讯 剧集'),
            ('爱奇艺', '爱奇艺 剧集'), ('优酷', '优酷 剧集'), ('芒果', '芒果TV 剧集'),
            ('搜狐', '搜狐 剧集'), ('港台', '港台 剧集'), ('美国', '美国 剧集'),
            ('韩国', '韩国 剧集'), ('日本', '日本 剧集'), ('英国', '英国 剧集'),
        ]),
        _filter_group('platform', '平台', [
            ('Netflix', 'netflix drama'), ('Disney', 'disney drama'), ('Apple', 'apple drama'),
            ('Amazon', 'amazon drama'), ('HBO', 'hbo drama'),
        ])
    ),
    '电影': _with_year(
        _filter_group('region', '地区/平台', [
            ('大陆', '大陆 电影'), ('腾讯', '腾讯 电影'), ('爱奇艺', '爱奇艺 电影'),
            ('优酷', '优酷 电影'), ('芒果', '芒果TV 电影'), ('搜狐', '搜狐 电影'),
            ('港台', '港台 电影'), ('美国', '美国 movie'), ('韩国', '韩国 电影'),
            ('日本', '日本 电影'), ('英国', '英国 movie'),
        ]),
        _filter_group('platform', '平台', [
            ('YouTube Movies', 'youtube movies'), ('Netflix', 'netflix movie'), ('Disney', 'disney movie'),
            ('Apple', 'apple movie'), ('Amazon', 'amazon movie'), ('HBO', 'hbo movie'),
        ])
    ),
    '纪录片': _with_year(
        _filter_group('topic', '主题', [
            ('历史', '历史 纪录片'), ('野性', '野性 纪录片 wild documentary'),
            ('地球', '地球 纪录片 earth documentary'), ('宇宙', '宇宙 纪录片 universe documentary'),
            ('海洋', '海洋 纪录片 oceans documentary'), ('人文', '人文 纪录片'),
            ('战争', '战争 纪录片 war documentary'), ('BBC', 'BBC 纪录片 documentary'),
            ('国家地理', '国家地理 National Geographic documentary'), ('Netflix', 'netflix 纪录片 documentary'),
        ])
    ),
    '放松': [
        _filter_group('topic', '主题', [
            ('冥想', '冥想 放松 meditation relax'), ('睡眠', '睡眠 放松 sleep relax'),
            ('白噪音', '白噪音 放松 white noise'), ('自然声音', '自然 声音 放松 nature sounds'),
            ('雨声', '雨声 放松 rain sounds'), ('海浪', '海浪 放松 ocean waves'),
        ])
    ],
    '4K': [
        _filter_group('topic', '主题', [
            ('风景', '4K 风景 scenery'), ('城市', '4K 城市 city walk'), ('旅行', '4K travel'),
            ('动物', '4K wildlife animals'), ('航拍', '4K drone aerial'), ('演示片', '4K demo video'),
        ])
    ],
    'HDR': [
        _filter_group('topic', '主题', [
            ('风景', 'HDR 风景 scenery'), ('自然', 'HDR nature'), ('动物', 'HDR wildlife animals'),
            ('城市', 'HDR city'), ('演示片', 'HDR demo video'), ('放松', 'HDR relax'),
        ])
    ],
    '自然': [
        _filter_group('topic', '主题', [
            ('风景', '大自然 风景 nature scenery'), ('动物世界', '动物世界 wildlife documentary'),
            ('海洋', '海洋 自然 ocean nature'), ('森林', '森林 自然 forest nature'),
            ('鸟类', '鸟类 自然 birds nature'), ('地球', '地球 自然 earth nature'),
            ('国家地理', 'National Geographic nature wildlife'), ('BBC Earth', 'BBC Earth nature'),
        ])
    ],
    '16K HDR': [
        _filter_group('topic', '风景', [
            ('运动', 'GoPro 极限自行车 翼装飞行'), ('风景', 'hdr 大自然 风景'),
            ('Links TV', '@linksphotograph Links TV hdr'), ('放松', 'hdr 放松'),
            ('动物世界', 'hdr Carnivorous Animals 动物世界'), ('深海世界', 'hdr Invertebrate Fish 深海世界'),
            ('飞禽走兽', 'hdr Birds of Prey Birds'), ('生物世界', 'hdr Amphibians Reptiles 生物世界'),
        ])
    ],
    '科技': [
        _filter_group('topic', '主题', [
            ('AI', '人工智能 AI technology'), ('数码', '数码 科技 technology'),
            ('手机', '手机 评测 technology'), ('电脑', '电脑 科技 technology'),
            ('汽车科技', '汽车 科技 technology'), ('太空', '航天 太空 technology'),
        ])
    ],
    '解说': [
        _filter_group('channel', '频道主', [('宇哥侃故事', '@yuge'), ('零度解说', '@lingdujieshuo')])
    ],
}


def debug_log(message, data=None):
    try:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        if data is not None:
            if isinstance(data, (dict, list)):
                line += ' ' + json.dumps(data, ensure_ascii=False, default=str)
            else:
                line += ' ' + str(data)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


# -------------------------
# tiny protobuf / UMP helpers
# -------------------------
def _pb_varint(value):
    value = int(value or 0)
    out = bytearray()
    while True:
        b = value & 0x7f
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _pb_key(field_no, wire_type):
    return _pb_varint((int(field_no) << 3) | int(wire_type))


def _pb_int(field_no, value):
    if value is None:
        return b''
    return _pb_key(field_no, 0) + _pb_varint(value)


def _pb_bool(field_no, value):
    return _pb_key(field_no, 0) + (b'\x01' if value else b'\x00')


def _pb_bytes(field_no, value):
    if value is None:
        return b''
    if isinstance(value, str):
        value = value.encode('utf-8')
    return _pb_key(field_no, 2) + _pb_varint(len(value)) + value


def _pb_str(field_no, value):
    if value is None or value == '':
        return b''
    return _pb_bytes(field_no, str(value).encode('utf-8'))


def _pb_msg(field_no, payload):
    if not payload:
        return b''
    return _pb_key(field_no, 2) + _pb_varint(len(payload)) + payload


def _b64url_decode(value):
    if not value:
        return None
    if isinstance(value, bytes):
        s = value
    else:
        s = str(value).encode('ascii', 'ignore')
    s += b'=' * ((4 - len(s) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(s)
    except Exception:
        try:
            return base64.b64decode(s)
        except Exception:
            return None


def _read_pb_varint(data, pos):
    shift = 0
    result = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    return None, pos


def _skip_pb_value(data, pos, wire_type):
    if wire_type == 0:
        _, pos = _read_pb_varint(data, pos)
        return pos
    if wire_type == 1:
        return min(len(data), pos + 8)
    if wire_type == 2:
        size, pos = _read_pb_varint(data, pos)
        return min(len(data), pos + int(size or 0))
    if wire_type == 5:
        return min(len(data), pos + 4)
    return len(data)


def _pb_get_bytes(data, field_no):
    pos = 0
    while pos < len(data):
        key, pos = _read_pb_varint(data, pos)
        if key is None:
            break
        fn = key >> 3
        wt = key & 7
        if fn == field_no and wt == 2:
            size, pos = _read_pb_varint(data, pos)
            return data[pos:pos + int(size or 0)]
        pos = _skip_pb_value(data, pos, wt)
    return None


def _pb_get_int(data, field_no):
    pos = 0
    while pos < len(data):
        key, pos = _read_pb_varint(data, pos)
        if key is None:
            break
        fn = key >> 3
        wt = key & 7
        if fn == field_no and wt == 0:
            value, pos = _read_pb_varint(data, pos)
            return value
        pos = _skip_pb_value(data, pos, wt)
    return None


def _pb_get_str(data, field_no):
    value = _pb_get_bytes(data, field_no)
    if value is None:
        return None
    try:
        return value.decode('utf-8')
    except Exception:
        return None


def _sabr_extract_reload_token(part_data):
    # RELOAD_PLAYER_RESPONSE(46) 结构：field1 -> 嵌套消息 -> field1(string) = reloadPlaybackContext token。
    # 服务器在 SABR 会话到期（常见 ~70s 边界）时下发，要求客户端重取播放上下文才继续发媒体段。
    inner = _pb_get_bytes(part_data, 1)
    if inner is None:
        return None
    return _pb_get_str(inner, 1)


# ---- WebM/EBML 解析：为“越 70s 直链 Range 续播”把直链 WebM 按 Cluster 切段 ----
# SABR 会话 ~70s 到期后不再重建 SABR（reload 已证死路），改由盒子本地重签直链、
# 经 10172 代理 Range 拉取，把整文件 WebM 按 Cues 切成独立 Cluster 当 seg=N 送出。
EBML_ID_SEGMENT = 0x18538067
EBML_ID_INFO = 0x1549A966
EBML_ID_TIMECODESCALE = 0x2AD7B1
EBML_ID_CUES = 0x1C53BB6B
EBML_ID_CUEPOINT = 0xBB
EBML_ID_CUETIME = 0xB3
EBML_ID_CUETRACKPOS = 0xB7
EBML_ID_CUECLUSTERPOS = 0xF1


def _ebml_read_id(data, pos):
    if pos >= len(data):
        return None, pos
    b0 = data[pos]
    if b0 & 0x80:
        length = 1
    elif b0 & 0x40:
        length = 2
    elif b0 & 0x20:
        length = 3
    elif b0 & 0x10:
        length = 4
    else:
        return None, pos
    if pos + length > len(data):
        return None, pos
    val = int.from_bytes(data[pos:pos + length], 'big')  # ID 保留前导标记位
    return val, pos + length


def _ebml_read_size(data, pos):
    if pos >= len(data):
        return None, pos
    b0 = data[pos]
    mask = 0x80
    length = 1
    while length <= 8 and not (b0 & mask):
        mask >>= 1
        length += 1
    if length > 8 or pos + length > len(data):
        return None, pos
    val = b0 & (mask - 1)
    for i in range(1, length):
        val = (val << 8) | data[pos + i]
    return val, pos + length


def _webm_segment_data_offset(init_bytes):
    """定位 Segment 元素数据起始绝对偏移（CueClusterPosition 相对它）。"""
    pos = 0
    n = len(init_bytes)
    while pos < n:
        eid, p2 = _ebml_read_id(init_bytes, pos)
        if eid is None:
            break
        size, p3 = _ebml_read_size(init_bytes, p2)
        if size is None:
            break
        if eid == EBML_ID_SEGMENT:
            return p3
        pos = p3 + size
    return 0


def _webm_timecode_scale(init_bytes):
    """取 Info.TimecodeScale（ns/tick），缺省 1e6（每 tick 1ms）。"""
    n = len(init_bytes)
    pos = 0
    while pos < n:
        eid, p2 = _ebml_read_id(init_bytes, pos)
        if eid is None:
            break
        size, p3 = _ebml_read_size(init_bytes, p2)
        if size is None:
            break
        if eid == EBML_ID_SEGMENT:
            child = p3
            end = min(n, p3 + size) if size and size < (1 << 60) else n
            while child < end:
                cid, c2 = _ebml_read_id(init_bytes, child)
                if cid is None:
                    break
                csize, c3 = _ebml_read_size(init_bytes, c2)
                if csize is None:
                    break
                if cid == EBML_ID_INFO:
                    gc = c3
                    gend = min(n, c3 + csize)
                    while gc < gend:
                        gid, g2 = _ebml_read_id(init_bytes, gc)
                        if gid is None:
                            break
                        gsize, g3 = _ebml_read_size(init_bytes, g2)
                        if gsize is None:
                            break
                        if gid == EBML_ID_TIMECODESCALE:
                            return int.from_bytes(init_bytes[g3:g3 + gsize], 'big') or 1000000
                        gc = g3 + gsize
                    break
                child = c3 + csize
            break
        pos = p3 + size
    return 1000000


def _webm_parse_cues(cues_bytes, segment_data_offset, timecode_scale):
    """解析 Cues -> [(time_ms, cluster_abs_offset), ...]，按时间升序。"""
    entries = []
    n = len(cues_bytes)
    pos = 0
    eid, p2 = _ebml_read_id(cues_bytes, 0)
    if eid == EBML_ID_CUES:
        size, p3 = _ebml_read_size(cues_bytes, p2)
        pos = p3
        if size and size < (1 << 60):
            n = min(n, p3 + size)
    while pos < n:
        cid, c2 = _ebml_read_id(cues_bytes, pos)
        if cid is None:
            break
        csize, c3 = _ebml_read_size(cues_bytes, c2)
        if csize is None:
            break
        if cid == EBML_ID_CUEPOINT:
            cue_time = None
            cluster_pos = None
            gc = c3
            gend = min(len(cues_bytes), c3 + csize)
            while gc < gend:
                gid, g2 = _ebml_read_id(cues_bytes, gc)
                if gid is None:
                    break
                gsize, g3 = _ebml_read_size(cues_bytes, g2)
                if gsize is None:
                    break
                if gid == EBML_ID_CUETIME:
                    cue_time = int.from_bytes(cues_bytes[g3:g3 + gsize], 'big')
                elif gid == EBML_ID_CUETRACKPOS:
                    tc = g3
                    tend = min(len(cues_bytes), g3 + gsize)
                    while tc < tend:
                        tid, t2 = _ebml_read_id(cues_bytes, tc)
                        if tid is None:
                            break
                        tsize, t3 = _ebml_read_size(cues_bytes, t2)
                        if tsize is None:
                            break
                        if tid == EBML_ID_CUECLUSTERPOS:
                            cluster_pos = int.from_bytes(cues_bytes[t3:t3 + tsize], 'big')
                        tc = t3 + tsize
                gc = g3 + gsize
            if cue_time is not None and cluster_pos is not None:
                time_ms = int(cue_time * timecode_scale / 1000000)
                entries.append((time_ms, segment_data_offset + cluster_pos))
        pos = c3 + csize
    entries.sort(key=lambda x: x[0])
    return entries


UMP_MEDIA_HEADER = 20
UMP_MEDIA = 21
UMP_MEDIA_END = 22
UMP_NEXT_REQUEST_POLICY = 35
UMP_SABR_REDIRECT = 43
UMP_SABR_ERROR = 44
UMP_RELOAD_PLAYER_RESPONSE = 46
UMP_STREAM_PROTECTION_STATUS = 58


def _read_ump_varint_stream(fp):
    # 完全对齐 yt-dlp _streaming/ump.py::read_varint
    # 注意：UMP varint 不是 protobuf varint，也不是大端拼接。
    # 之前这里按“大端前导位”解析，会把 SABR 响应解析成大量 part_id=0，导致 media_len=0。
    first = fp.read(1)
    if not first:
        return -1
    prefix = first[0]
    size = 1 if prefix < 128 else 2 if prefix < 192 else 3 if prefix < 224 else 4 if prefix < 240 else 5
    result = 0
    shift = 0
    if size != 5:
        shift = 8 - size
        mask = (1 << shift) - 1
        result |= prefix & mask
    for _ in range(1, size):
        b = fp.read(1)
        if not b:
            return -1
        result |= b[0] << shift
        shift += 8
    return result


def _read_ump_varint_bytes(data, pos=0):
    """Read an UMP varint from bytes and return (value, next_pos)."""
    if pos >= len(data):
        return -1, pos
    prefix = data[pos]
    pos += 1
    size = 1 if prefix < 128 else 2 if prefix < 192 else 3 if prefix < 224 else 4 if prefix < 240 else 5
    result = 0
    shift = 0
    if size != 5:
        shift = 8 - size
        result = prefix & ((1 << shift) - 1)
    for _ in range(1, size):
        if pos >= len(data):
            return -1, pos
        result |= data[pos] << shift
        shift += 8
        pos += 1
    return result, pos


def iter_ump_parts(fp, max_parts=160):
    count = 0
    while count < max_parts:
        try:
            part_id = _read_ump_varint_stream(fp)
            if part_id < 0:
                break
            size = _read_ump_varint_stream(fp)
            if size < 0:
                break
            data = fp.read(size) or b''
        except Exception:
            if count > 0:
                break
            raise
        if len(data) < size:
            break
        count += 1
        yield part_id, data


def _sabr_media_key(part_data):
    """Return a short stable key for de-duplicating repeated SABR media parts."""
    if not part_data:
        return None
    return hashlib.sha1(part_data).hexdigest()


def _find_container_offset(media, content_type=None):
    ctype = (content_type or '').lower()
    candidates = []
    if 'webm' in ctype or 'matroska' in ctype or not ctype:
        candidates.append(media.find(b'\x1a\x45\xdf\xa3', 0, 128))
    if 'mp4' in ctype or not ctype:
        idx = media.find(b'ftyp', 0, 128)
        candidates.append(idx - 4 if idx >= 4 else -1)
    candidates = [x for x in candidates if x is not None and x >= 0]
    return min(candidates) if candidates else 0


def _sabr_header_format_id(header_data, fallback_itag=None):
    # yt-dlp MediaHeader.format_id is field 13. Older/minimal responses also expose itag in field 3.
    fmt = _pb_get_bytes(header_data, 13)
    if fmt:
        return fmt
    itag = _pb_get_int(header_data, 3) or fallback_itag
    return build_format_id(itag) if itag else b''


def _ticks_to_ms(ticks, timescale):
    try:
        return int(int(ticks or 0) * 1000 / int(timescale or 1000))
    except Exception:
        return 0


def _sabr_time_range_ms(header_data):
    # MediaHeader.time_range = field 15; TimeRange: start_ticks=1, duration_ticks=2, timescale=3
    tr = _pb_get_bytes(header_data, 15)
    if not tr:
        return 0, 0
    start_ticks = _pb_get_int(tr, 1) or 0
    duration_ticks = _pb_get_int(tr, 2) or 0
    timescale = _pb_get_int(tr, 3) or 1000
    return _ticks_to_ms(start_ticks, timescale), _ticks_to_ms(duration_ticks, timescale)


def build_buffered_range(format_id, start_ms=0, duration_ms=0, start_seq=None, end_seq=None):
    # BufferedRange: format_id=1, start_time_ms=2, duration_ms=3, start_segment_index=4, end_segment_index=5, time_range=6
    if not format_id:
        return b''
    p = _pb_msg(1, format_id)
    p += _pb_int(2, int(start_ms or 0))
    p += _pb_int(3, int(duration_ms or 0))
    if start_seq is not None:
        p += _pb_int(4, int(start_seq))
    if end_seq is not None:
        p += _pb_int(5, int(end_seq))
    time_range_msg = _pb_int(1, int(start_ms or 0)) + _pb_int(2, int(duration_ms or 0)) + _pb_int(3, 1000)
    p += _pb_msg(6, time_range_msg)
    return p


def build_format_id(itag, lmt=None, xtags=None):
    # yt-dlp _proto/videostreaming/format_id.py: itag=1, lmt=2, xtags=3
    p = b''
    if itag:
        p += _pb_int(1, int(itag))
    if lmt:
        try:
            p += _pb_int(2, int(lmt))
        except Exception:
            pass
    if xtags:
        p += _pb_str(3, xtags)
    return p


def build_client_info(client_info):
    # yt-dlp _proto/innertube/client_info.py
    c = client_info or {}
    p = b''
    p += _pb_str(1, c.get('hl') or 'en')
    p += _pb_str(2, c.get('gl') or 'US')
    p += _pb_str(12, c.get('deviceMake') or c.get('device_make'))
    p += _pb_str(13, c.get('deviceModel') or c.get('device_model'))
    p += _pb_str(14, c.get('visitorData') or c.get('visitor_data'))
    p += _pb_str(15, c.get('userAgent') or c.get('user_agent'))
    p += _pb_int(16, c.get('clientNameId') or c.get('client_name_id') or 1)
    p += _pb_str(17, c.get('clientVersion') or c.get('client_version'))
    p += _pb_str(18, c.get('osName') or c.get('os_name'))
    p += _pb_str(19, c.get('osVersion') or c.get('os_version'))
    sdk = c.get('androidSdkVersion') or c.get('android_sdk_version')
    if sdk:
        p += _pb_int(64, sdk)
    return p


def build_media_capabilities(client_name_id, prefer_hdr=False):
    # 对 ANDROID/IOS/ANDROID_VR 客户端，yt-dlp 会带 MediaCapabilities
    if client_name_id not in (3, 5, 28, 101):
        return b''
    p = b''
    # VideoFormatCapability: video_codec=1, efficient=2, is_10_bit_supported=15
    for codec in (2, 4, 8, 9):  # H264 VP9 AV1 H265
        p += _pb_msg(1, _pb_int(1, codec) + _pb_bool(2, True) + _pb_bool(15, True))
    # AudioFormatCapability: audio_codec=1
    for acodec in (1, 3, 9, 13):  # AAC OPUS MP3 XHEAAC
        p += _pb_msg(2, _pb_int(1, acodec))
    p += _pb_int(5, 3 if prefer_hdr else 0)
    return p


def build_client_abr_state(client_name_id=1, start_time_ms=0, prefer_hdr=False, audio_only=False, height=1080, elapsed_ms=1000):
    # ClientAbrState: 对齐 SabrStreamingAdapter 完整状态字段，确保分片拉取与 Seek 一次命中
    p = b''
    p += _pb_int(16, int(height or 1080))
    p += _pb_int(21, int(height or 1080))
    p += _pb_bool(22, False)
    p += _pb_int(23, 5000000)
    p += _pb_int(28, int(start_time_ms or 0))
    p += _pb_int(29, int(elapsed_ms or 1000))
    p += _pb_int(34, 1)
    p += _pb_int(36, int(elapsed_ms or 1000))
    mc = build_media_capabilities(client_name_id, prefer_hdr=prefer_hdr)
    if mc:
        p += _pb_msg(38, mc)
    p += _pb_int(39, int(elapsed_ms or 1000))
    p += _pb_int(40, 1 if audio_only else 0)
    p += _pb_bool(46, False)
    p += _pb_bool(76, True)
    return p


def build_streamer_context(client_info, po_token=None, playback_cookie=None):
    # StreamerContext: client_info=1, po_token=2, playback_cookie=3
    p = b''
    p += _pb_msg(1, build_client_info(client_info))
    pot = _b64url_decode(po_token) if po_token else None
    if pot:
        p += _pb_bytes(2, pot)
    if playback_cookie:
        p += _pb_bytes(3, playback_cookie)
    return p


def build_vpabr_request(sabr_config, video_itag=None, audio_itag=None, start_time_ms=0, playback_cookie=None, initialized_format_ids=None, buffered_ranges=None, audio_config=None, video_height=1080):
    # VideoPlaybackAbrRequest fields:
    # client_abr_state=1, initialized_format_ids=2, buffered_ranges=3, player_time_ms=4,
    # video_playback_ustreamer_config=5, preferred_audio_format_ids=16, preferred_video_format_ids=17, streamer_context=19
    client_info = sabr_config.get('client_info') or {}
    client_name_id = client_info.get('clientNameId') or client_info.get('client_name_id') or 1
    a_cfg = audio_config or sabr_config or {}
    p = b''
    p += _pb_msg(1, build_client_abr_state(
        client_name_id, start_time_ms, bool(sabr_config.get('prefer_hdr')),
        not video_itag, height=video_height))
    for fmt_id in initialized_format_ids or []:
        if fmt_id:
            p += _pb_msg(2, fmt_id)
    for br in buffered_ranges or []:
        if br:
            p += _pb_msg(3, br)
    p += _pb_int(4, int(start_time_ms or 0))
    ustreamer = _b64url_decode(sabr_config.get('video_playback_ustreamer_config'))
    if ustreamer:
        p += _pb_bytes(5, ustreamer)
    if audio_itag:
        p += _pb_msg(16, build_format_id(audio_itag, a_cfg.get('last_modified'), a_cfg.get('xtags')))
    if video_itag:
        p += _pb_msg(17, build_format_id(video_itag, sabr_config.get('last_modified'), sabr_config.get('xtags')))
    p += _pb_msg(19, build_streamer_context(client_info, sabr_config.get('po_token'), playback_cookie))
    return p

class YouTubeLite:
    def __init__(self, session, headers=None, config=None):
        self.session = session
        self.headers = headers or {}
        self.config = config or {}
        self.player_cache = {}
        self.extract_cache = {}
        self.sig_plan_cache = {}
        self._n_log_seen = set()
        self.sabr_state = {}
        self._extract_locks_guard = threading.Lock()
        self._extract_locks = {}
        self.extract_cache_ttl = int(self.config.get('extract_cache_ttl') or 300)
        # 纯本地免云端 SABR 专线：ANDROID_VR / ANDROID / IOS 客户端无需远端服务器签发 pot
        self._active_pot = None
        self._cached_visitor_data = None
        self._cached_visitor_exp = 0
        # SABR 续流：服务器每 ~70s 下发 RELOAD_PLAYER_RESPONSE 要求重取播放上下文。
        # Spider 在构造后注入此回调（入参 state_key，返回 fresh _sabr_config 或 None），
        # sabr_get_segment 命中 reload 时调用它换取新会话（新 URL/ustreamer/pot）后继续续拉。
        self.sabr_reload_hook = None

    def _auto_heal_singbox_node(self, video_id):
        """当 10172 代理的当前出口节点被 YouTube 要求 LOGIN_REQUIRED 时，自动通过本机 19090 端口切换到可用节点；若无单节点通过则恢复原选择。"""
        for api_host in ('http://127.0.0.1:19090', 'http://192.168.1.6:19090'):
            try:
                s = requests.Session()
                s.trust_env = False
                r = s.get(f'{api_host}/proxies', timeout=2)
                if r.status_code != 200:
                    continue
                proxies_map = r.json().get('proxies') or {}
                select_info = proxies_map.get('select') or {}
                cur_now = select_info.get('now') or 'urltest'
                all_nodes = [
                    n for n in (select_info.get('all') or [])
                    if n not in ('urltest', 'select', 'DIRECT', 'REJECT')
                ]
                if not all_nodes:
                    continue
                c = {
                    'clientName': 'ANDROID', 'clientVersion': '21.02.35',
                    'androidSdkVersion': 30,
                    'userAgent': 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip',
                    'osName': 'Android', 'osVersion': '11', 'hl': 'en', 'gl': 'US',
                }
                healed = False
                proxies = dict(self.session.proxies or {})
                try:
                    for node in all_nodes:
                        if node == cur_now:
                            continue
                        try:
                            s.put(f'{api_host}/proxies/select', json={'name': node}, timeout=2)
                            pr = requests.post(
                                'https://www.youtube.com/youtubei/v1/player?prettyPrint=false',
                                json={'context': {'client': c}, 'videoId': video_id, 'contentCheckOk': True, 'racyCheckOk': True},
                                headers={'User-Agent': c['userAgent'], 'Connection': 'close'},
                                proxies=proxies,
                                timeout=6,
                            )
                            if pr.status_code == 200 and (pr.json().get('playabilityStatus') or {}).get('status') == 'OK':
                                self.trace('singbox node auto healed', {'from': cur_now, 'to': node, 'api': api_host})
                                healed = True
                                return True
                        except Exception:
                            continue
                finally:
                    if not healed:
                        try:
                            s.put(f'{api_host}/proxies/select', json={'name': cur_now}, timeout=2)
                        except Exception:
                            pass
            except Exception:
                continue
        return False

    def _get_extract_lock(self, video_id):
        with self._extract_locks_guard:
            lk = self._extract_locks.get(video_id)
            if lk is None:
                lk = threading.RLock()
                self._extract_locks[video_id] = lk
            return lk

    def extract(self, url_or_id, force_refresh=False, reload_token=None, prefer_visitor_data=None):
        video_id = self.extract_video_id(url_or_id)
        now = time.time()
        cached = self.extract_cache.get(video_id)
        if not force_refresh and cached and cached.get('expires', 0) > now:
            self.trace('extract cache hit', {'video_id': video_id, 'ttl': int(cached.get('expires', 0) - now)})
            return cached['data']
        with self._get_extract_lock(video_id):
            now = time.time()
            cached = self.extract_cache.get(video_id)
            if not force_refresh and cached and cached.get('expires', 0) > now:
                self.trace('extract lock cache hit', {'video_id': video_id, 'ttl': int(cached.get('expires', 0) - now)})
                return cached['data']
            return self._extract_locked(video_id, force_refresh=force_refresh, reload_token=reload_token, prefer_visitor_data=prefer_visitor_data)

    def _extract_locked(self, video_id, force_refresh=False, reload_token=None, prefer_visitor_data=None):
        started = time.time()
        watch_url = f'https://www.youtube.com/watch?v={video_id}'
        self.trace('extract start', {'video_id': video_id, 'force_refresh': force_refresh})
        self._active_pot = None
        player_url = None
        initial_pr = {}
        ytcfg = {}
        visitor_data = prefer_visitor_data

        # 1. 纯净移动端 Innertube 直提（不预拉桌面 watch HTML，彻底杜绝 Cloudflare 节点下桌面端 LOGIN_REQUIRED 污染 visitorData 与 Cookie）
        responses = []
        api_responses = self._call_player_api(video_id, None, None, None, visitor_data, None, reload_token=reload_token)
        responses.extend([x for x in api_responses if x])

        # 2. 仅当移动端直提未拿到流数据时，才回退抓取 watch 页面
        if not responses or not any(x.get('streamingData') for x in responses):
            page = ''
            try:
                page_resp = self._get(watch_url)
                page = page_resp.text
                self.trace('watch page fallback', {'status': page_resp.status_code, 'length': len(page)})
            except Exception as e:
                self.trace('watch page error', {'error': repr(e)})
            if page:
                ytcfg = self._extract_ytcfg(page) or {}
                initial_pr = self._extract_initial_player_response(page) or {}
                player_url = self._extract_player_url(page)
                if not visitor_data:
                    visitor_data = self._extract_visitor_data(ytcfg, initial_pr)
                if initial_pr and initial_pr.get('streamingData'):
                    initial_pr['_client_name'] = 'WEB_INITIAL'
                    initial_pr['_client_ua'] = self.headers.get('User-Agent') or DEFAULT_UA
                    initial_pr['_client_info'] = {'clientNameId': 1, 'clientName': 'WEB', 'clientVersion': 'initial', 'userAgent': self.headers.get('User-Agent') or DEFAULT_UA, 'hl': 'en', 'gl': 'US', 'visitorData': visitor_data}
                    responses.append(initial_pr)
            direct_api_resps = self._call_direct_clients(video_id)
            responses.extend([x for x in direct_api_resps if x])

        best_pr = next((x for x in responses if (x.get('playabilityStatus') or {}).get('status') == 'OK' and x.get('streamingData')), None)
        if not best_pr:
            best_pr = next((x for x in responses if (x.get('playabilityStatus') or {}).get('status') == 'OK'), initial_pr or (responses[0] if responses else {}))
        if not visitor_data:
            visitor_data = ((best_pr.get('responseContext') or {}).get('visitorData'))
        if visitor_data:
            self._cached_visitor_data = visitor_data
            self._cached_visitor_exp = time.time() + 1800

        status = (best_pr.get('playabilityStatus') or {}).get('status')
        streaming = best_pr.get('streamingData') or {}
        if status and status not in ('OK', 'LIVE_STREAM_OFFLINE') and not streaming:
            if status == 'LOGIN_REQUIRED' and not getattr(self, '_in_node_heal', False):
                if self._auto_heal_singbox_node(video_id):
                    self._in_node_heal = True
                    try:
                        return self._extract_locked(video_id, force_refresh=True, reload_token=reload_token, prefer_visitor_data=prefer_visitor_data)
                    finally:
                        self._in_node_heal = False
            reason = (best_pr.get('playabilityStatus') or {}).get('reason') or status
            raise Exception(f'YouTube 不可播放: {reason}')

        details = best_pr.get('videoDetails') or {}
        captions = None
        for resp in responses:
            if resp.get('captions'):
                captions = resp.get('captions')
                break
        if not captions and initial_pr and initial_pr.get('captions'):
            captions = initial_pr.get('captions')
        if not captions and best_pr and best_pr.get('captions'):
            captions = best_pr.get('captions')

        # 自动提取直播 HLS 地址（优先提取 ANDROID / IOS / VISIONOS 无加密 HLS Manifest）
        hls_url = None
        hls_ua = None
        for resp in responses:
            sd = resp.get('streamingData') or {}
            if sd.get('hlsManifestUrl'):
                hls_url = sd.get('hlsManifestUrl')
                hls_ua = resp.get('_client_ua')
                break
        dur_sec = int(details.get('lengthSeconds') or 0)
        # NOTE: 过去的直播回放（VOD）也会带有 isLiveContent=True，但此时 isLive=False 且 dur_sec > 0 且无 hls_url；
        # 只有真正正在直播的流（有 hls_url，或 isLive=True，或 isLiveContent=True 且 dur_sec==0）才标记为 is_live=True。
        is_live = bool(
            hls_url
            or details.get('isLive')
            or (details.get('isLiveContent') and dur_sec == 0)
            or ((best_pr.get('playabilityStatus') or {}).get('liveStreamability') and dur_sec == 0)
        )
        if is_live:
            # 始终优先调用 ANDROID (20.10.38) 获取音画合一（itag 91~96，仅 7 个实时分片）的原生直播 HLS 清单，避免 VISIONOS 返回音画分离且带 3600s DVR keepalive 阻塞的清单
            live_fb = self._fetch_live_hls_fallback(video_id)
            if live_fb.get('hls_url'):
                hls_url = live_fb['hls_url']
                hls_ua = live_fb.get('hls_ua') or hls_ua

        formats, sabr_formats = self._extract_formats_from_responses(responses, player_url)
        result = {
            'id': video_id,
            'title': details.get('title') or video_id,
            'duration': dur_sec,
            'is_live': is_live,
            'hls_url': hls_url,
            'hls_ua': hls_ua,
            'formats': formats,
            'sabr_formats': sabr_formats,
            'captions': captions,
            'player_url': player_url,
        }
        self.extract_cache[video_id] = {'data': result, 'expires': time.time() + self.extract_cache_ttl}
        self.trace('extract complete', {
            'video_id': video_id,
            'cost_ms': int((time.time() - started) * 1000),
            'is_live': is_live,
            'has_hls': bool(hls_url),
            'direct_formats': len(formats),
            'sabr_formats': len(sabr_formats),
            'direct_heights': sorted(set(int(x.get('height') or 0) for x in formats if x.get('vcodec') != 'none'), reverse=True)[:12],
            'sabr_heights': sorted(set(int(x.get('height') or 0) for x in sabr_formats if x.get('vcodec') != 'none'), reverse=True)[:12],
        })
        return result

    def _fetch_live_hls_fallback(self, video_id):
        """针对正在直播的视频，优先请求 ANDROID (20.10.38) 提取音画合一（itag 91~96）的极速 HLS 清单。"""
        live_clients = [
            {'clientName': 'ANDROID', 'clientVersion': '20.10.38', 'androidSdkVersion': 34, 'ua': 'com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip'},
            {'clientName': 'IOS', 'clientVersion': '21.02.3', 'deviceMake': 'Apple', 'deviceModel': 'iPhone16,2', 'ua': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)'},
        ]
        proxies = dict(self.session.proxies or {})
        for c in live_clients:
            try:
                payload = {
                    'context': {'client': {
                        'clientName': c['clientName'],
                        'clientVersion': c['clientVersion'],
                        'hl': 'zh-CN',
                        'gl': 'US',
                    }},
                    'videoId': video_id,
                    'contentCheckOk': True,
                    'racyCheckOk': True,
                }
                if c.get('androidSdkVersion'):
                    payload['context']['client']['androidSdkVersion'] = c['androidSdkVersion']
                r = requests.post(
                    'https://www.youtube.com/youtubei/v1/player?prettyPrint=false',
                    json=payload,
                    headers={'Content-Type': 'application/json', 'User-Agent': c['ua'], 'Connection': 'close'},
                    proxies=proxies,
                    timeout=6,
                )
                if r.status_code == 200:
                    d = r.json()
                    hls_u = (d.get('streamingData') or {}).get('hlsManifestUrl')
                    if hls_u:
                        return {'hls_url': hls_u, 'hls_ua': c['ua']}
            except Exception as e:
                self.trace('live hls fallback error', {'client': c['clientName'], 'error': repr(e)})
        return {}

    def extract_live(self, url_or_id):
        data = self.extract(url_or_id)
        if data.get('hls_url'):
            return data
        video_id = self.extract_video_id(url_or_id)
        fb = self._fetch_live_hls_fallback(video_id)
        if fb.get('hls_url'):
            data['is_live'] = True
            data['hls_url'] = fb['hls_url']
            data['hls_ua'] = fb.get('hls_ua')
        return data


    @staticmethod
    def extract_video_id(text):
        text = str(text or '').strip()
        for pattern in [
            r'(?:v=|/v/|/embed/|/shorts/|youtu\.be/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        raise Exception('无法识别 YouTube 视频 ID')
    def _client_name_id(self, client_name):
        return {
            'WEB': 1,
            'MWEB': 2,
            'ANDROID': 3,
            'IOS': 5,
            'TVHTML5': 7,
            'ANDROID_VR': 28,
            'WEB_EMBEDDED_PLAYER': 56,
            'WEB_REMIX': 67,
            'VISIONOS': 101,
        }.get(client_name, 1)

    def _extract_visitor_data(self, ytcfg, player_response):
        return (
            self.config.get('visitor_data')
            or ytcfg.get('VISITOR_DATA')
            or (((ytcfg.get('INNERTUBE_CONTEXT') or {}).get('client') or {}).get('visitorData'))
            or ((player_response.get('responseContext') or {}).get('visitorData'))
        )

    def _extract_signature_timestamp(self, video_id, player_url, ytcfg=None):
        try:
            code = self._get_player_code(player_url)
            sts = self._search(r'(?:signatureTimestamp|sts)\s*:\s*(\d{5})', code)
            return int(sts) if sts else None
        except Exception as e:
            debug_log('sts extract error', repr(e))
            return None

    def _get_po_token(self, client_name, context='gvs'):
        # 纯本地模式：若用户在配置中自定义了静态 po_token 则读取，否则返回 None
        if context == 'gvs' and self._active_pot:
            return self._active_pot
        tokens = self.config.get('po_token') or self.config.get('po_tokens') or {}
        if isinstance(tokens, str):
            return tokens
        if isinstance(tokens, dict):
            return tokens.get(f'{client_name}.{context}') or tokens.get(client_name) or tokens.get(context)
        return None
    def choose_playable(self, formats, quality=None):
        all_videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        candidates = all_videos[:]
        if quality in ('8k', '8k_hdr'):
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 4320]
            if quality == '8k':
                candidates = [x for x in candidates if not self._is_hdr_video(x)]
            else:
                candidates = [x for x in candidates if self._is_hdr_video(x)]
        elif quality == '4k':
            candidates = [x for x in candidates if 2160 <= int(x.get('height') or 0) < 4320]
        elif quality == '2k':
            candidates = [x for x in candidates if 1440 <= int(x.get('height') or 0) < 2160]
        elif quality == '1080p':
            near = [x for x in candidates if 720 <= int(x.get('height') or 0) <= 1440]
            candidates = near or candidates
        elif quality == 'best':
            # 优先 ≤1080 且非 AV1，降低起播失败与高码率卡顿概率
            safe = [x for x in candidates if not self._is_risky_best_video(x)]
            capped = [x for x in (safe or candidates) if int(x.get('height') or 0) <= 1080]
            candidates = capped or safe or candidates
        else:
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 720] or candidates

        if not candidates and quality in ('best', '1080p', None, ''):
            candidates = all_videos
        if not candidates:
            return None
        # 画质优先，编码顺序 VP9/HDR > H264 > AV1。保留 VP9 Profile 2 HDR，
        # 只把 AV1 放到最后，避免默认选到 itag 701/702 的超大 AV1 分段。
        candidates.sort(key=lambda x: (
            1 if int(x.get('itag') or 0) == 140 else 0,
            1 if x.get('client') == 'IOS' else 0,
            1 if x.get('ext') == 'mp4' else 0,
            int(x.get('bitrate') or 0)
        ), reverse=True)
        selected = candidates[0]
        debug_log('video selected fast', {
            'quality': quality,
            'itag': selected.get('itag'),
            'height': selected.get('height'),
            'mime': selected.get('mimeType'),
            'codec_priority': self._video_codec_priority(selected),
            'candidates': len(candidates),
            'probe_skipped': True,
        })
        return selected

    def _video_codec_priority(self, item):
        codecs = (item.get('codecs') or '').lower()
        mime = (item.get('mimeType') or '').lower()
        # AVC/H.264 在所有电视盒子硬件芯片（晶晨/联发科/全志/海思）具有最高硬解兼容性，防解码器崩溃跳过
        if 'avc' in codecs or 'h264' in codecs or 'mp4v' in codecs:
            return 4
        if 'vp9.2' in mime or 'vp09.02' in codecs:
            return 3
        if 'vp9' in mime or 'vp09' in codecs:
            return 2
        if 'av01' in codecs:
            return 1
        return 0

    def _is_risky_best_video(self, item):
        codecs = (item.get('codecs') or '').lower()
        return 'av01' in codecs

    def choose_progressive(self, formats):
        """
        挑选无需 PO-Token 即可全片播放的渐进式 MP4 单文件流（首选 Android itag 18/22）。
        实测可全片畅播几十分钟、支持随意 Seek，绝不卡 60 秒。
        """
        prog = [x for x in (formats or []) if x.get('vcodec') != 'none' and x.get('acodec') != 'none' and x.get('url')]
        if not prog:
            return None
        # 绝对优先 ANDROID 客户端（免 60 秒限制）
        android_prog = [x for x in prog if x.get('client') == 'ANDROID']
        if android_prog:
            android_prog.sort(key=lambda x: (int(x.get('height') or 0), int(x.get('bitrate') or 0)), reverse=True)
            return android_prog[0]
        return prog[0]

    def choose_video_tracks(self, formats, quality=None, protocol=None):
        videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none' and (not protocol or x.get('protocol') == protocol)]
        quality = (quality or 'best').lower()
        prefer_hdr_only = quality in ('hdr', '8k_hdr')
        if quality == 'best':
            capped_1080 = [x for x in videos if int(x.get('height') or 0) <= 1080]
            capped_4k = [x for x in videos if int(x.get('height') or 0) <= 2160]
            videos = capped_1080 or capped_4k or videos
        elif quality in ('8k', '8k_hdr'):
            videos = [x for x in videos if int(x.get('height') or 0) >= 4320] or videos
        elif quality == '4k':
            videos = [x for x in videos if 2160 <= int(x.get('height') or 0) < 4320] or [
                x for x in videos if int(x.get('height') or 0) >= 1440
            ] or videos
        elif quality == '2k':
            videos = [x for x in videos if 1440 <= int(x.get('height') or 0) < 2160] or videos
        elif quality == '1080p':
            near = [x for x in videos if 900 <= int(x.get('height') or 0) <= 1440]
            if near:
                near.sort(key=lambda x: (
                    -abs(int(x.get('height') or 0) - 1080),
                    self._video_codec_priority(x),
                    int(x.get('bitrate') or 0),
                ), reverse=True)
                videos = near
        elif quality == '720p':
            near = [x for x in videos if 600 <= int(x.get('height') or 0) <= 800]
            if near:
                near.sort(key=lambda x: (
                    -abs(int(x.get('height') or 0) - 720),
                    self._video_codec_priority(x),
                    int(x.get('bitrate') or 0),
                ), reverse=True)
                videos = near
        if prefer_hdr_only:
            hdr_only = [x for x in videos if self._is_hdr_video(x)]
            videos = hdr_only or videos
        sdr = [x for x in videos if not self._is_hdr_video(x)]
        hdr = [x for x in videos if self._is_hdr_video(x)]
        client_prio = {'VISIONOS': 7, 'ANDROID_VR': 6, 'ANDROID': 5, 'IOS': 4, 'MWEB': 2, 'WEB': 1, 'WEB_INITIAL': 0}
        sort_key = lambda x: (
            1 if client_prio.get(str(x.get('client') or '').upper(), 0) >= 4 else 0,
            self._video_codec_priority(x),
            int(x.get('height') or 0),
            client_prio.get(str(x.get('client') or '').upper(), 0),
            int(x.get('bitrate') or 0)
        )
        sdr.sort(key=sort_key, reverse=True)
        hdr.sort(key=sort_key, reverse=True)
        tracks = []
        if prefer_hdr_only:
            if hdr:
                item = hdr[0].copy()
                item['track_name'] = f"{int(item.get('height') or 0)}P HDR"
                item['is_hdr'] = True
                tracks.append(item)
        else:
            seen_heights = set()
            for x in sdr:
                h = int(x.get('height') or 0)
                if h <= 0 or h in seen_heights:
                    continue
                seen_heights.add(h)
                item = x.copy()
                item['track_name'] = f'{h}P SDR'
                item['is_hdr'] = False
                tracks.append(item)
            if hdr:
                item = hdr[0].copy()
                item['track_name'] = f"{int(item.get('height') or 0)}P HDR"
                item['is_hdr'] = True
                tracks.append(item)
        if not tracks:
            item = self.choose_playable(videos, quality if quality != 'hdr' else 'best')
            if item:
                item = item.copy()
                item['track_name'] = 'HDR' if self._is_hdr_video(item) else 'SDR'
                item['is_hdr'] = self._is_hdr_video(item)
                tracks.append(item)
        debug_log('video tracks selected', [{'name': x.get('track_name'), 'itag': x.get('itag'), 'height': x.get('height'), 'codecs': x.get('codecs')} for x in tracks])
        return tracks

    def _is_hdr_video(self, item):
        mime = (item.get('mimeType') or '').lower()
        codecs = (item.get('codecs') or '').lower()
        color = item.get('colorInfo') or {}
        color_text = json.dumps(color, ensure_ascii=False).lower()
        hdr_markers = ('smpte2084', 'arib-std-b67', 'bt2020', 'hdr10', 'hlg', 'pq')
        return (
            'vp9.2' in mime
            or 'vp09.02' in codecs
            or bool(color.get('hdrMetadataInfo') or color.get('hdrMetadata'))
            or any(marker in color_text for marker in hdr_markers)
        )

    @staticmethod
    def _audio_lang_priority(item):
        """计算音轨语言与原声优先级：
        # NOTE: YouTube 多音轨视频（如王志安 zSAwwDEZNsI）会在同一 itag=251/140 下返回多条音轨，
        # 其中排在第 1 条且码率略高的往往是英语 AI 自动配音 (isAutoDubbed=True, en-US)，
        # 必须优先选择中文音轨 (zh-Hans/zh-Hant/zh) 或原声默认音轨 (audioIsDefault=True)。
        """
        at = (item or {}).get('audioTrack') or {}
        if not isinstance(at, dict):
            at = {}
        track_id = str(at.get('id') or '').lower()
        disp = str(at.get('displayName') or '').lower()
        is_default = bool(at.get('audioIsDefault'))
        is_auto_dub = bool(at.get('isAutoDubbed'))
        is_drc = bool((item or {}).get('isDrc'))
        xtags_raw = str((item or {}).get('xtags') or ((item or {}).get('_sabr_config') or {}).get('xtags') or '')
        xtags_decoded = ''
        if xtags_raw:
            try:
                pad = '=' * (-len(xtags_raw) % 4)
                xtags_decoded = base64.urlsafe_b64decode(xtags_raw + pad).decode('latin1', 'ignore').lower()
            except Exception:
                xtags_decoded = ''

        is_zh = (
            track_id.startswith('zh')
            or any(k in disp for k in ('zh', '中文', '汉语', '国语', '普通话', '粤语', 'chinese', 'mandarin', 'cantonese'))
            or 'zh-hans' in xtags_decoded
            or 'zh-hant' in xtags_decoded
            or 'lang\x12\x02zh' in xtags_decoded
        )
        is_orig = (
            is_default
            or any(k in disp for k in ('原始', '原声', 'original'))
            or 'original' in xtags_decoded
        )
        is_dub = is_auto_dub or 'dubbed' in xtags_decoded

        if is_zh:
            lang_score = 300 + (20 if is_orig else 0)
        elif is_orig and not is_dub:
            lang_score = 200
        elif not is_dub and not track_id:
            lang_score = 100
        elif not is_dub:
            lang_score = 50
        else:
            lang_score = -200

        drc_score = 0 if is_drc else 10
        return (lang_score, drc_score)

    def choose_audio(self, formats, protocol=None, same_client=None):
        candidates = [
            x for x in formats
            if x.get('acodec') != 'none' and x.get('vcodec') == 'none'
            and (not protocol or x.get('protocol') == protocol)
        ]
        if same_client:
            same = [x for x in candidates if x.get('client') == same_client]
            if same:
                candidates = same
        if not candidates:
            return None
        candidates.sort(key=lambda x: (
            self._audio_lang_priority(x),
            1 if x.get('client') == 'IOS' else 0,
            1 if x.get('ext') == 'mp4' else 0,
            int(x.get('bitrate') or 0)
        ), reverse=True)
        # A 方案：SABR 线音频锁 WebM/Opus(251)，与锁 WebM 的视频统一容器，
        # 让“越 70s 直链 Range 续播”音视频都按 WebM Cues 切 cluster（绕开 MP4 裸 mdat 坑）。
        # sabr_webm_only=0 可关闭恢复原偏好。
        if protocol == 'sabr':
            try:
                _webm_only = str(self.config.get('sabr_webm_only', '1')).lower() not in ('0', 'false', 'off', 'no')
            except Exception:
                _webm_only = True
            if _webm_only:
                _opus = [x for x in candidates if 'opus' in (x.get('codecs') or '').lower()
                         or 'webm' in (x.get('mimeType') or '').lower()]
                if _opus:
                    _opus.sort(key=lambda x: (
                        self._audio_lang_priority(x),
                        int(x.get('bitrate') or 0),
                    ), reverse=True)
                    candidates = _opus
        selected = candidates[0]
        debug_log('audio selected fast', {
            'itag': selected.get('itag'), 'mime': selected.get('mimeType'),
            'bitrate': selected.get('bitrate'), 'protocol': selected.get('protocol'),
            'client': selected.get('client'),
            'audioTrack': (selected.get('audioTrack') or {}).get('displayName') or (selected.get('audioTrack') or {}).get('id'),
            'lang_prio': self._audio_lang_priority(selected),
            'probe_skipped': True,
        })
        return selected

    def _probe_format(self, item):
        if item.get('protocol') == 'sabr':
            return False, 'skip-sabr-probe'
        try:
            headers = self.headers.copy()
            headers.update(item.get('headers') or {})
            headers['Range'] = 'bytes=0-1'
            r = self.session.get(item.get('url'), headers=headers, stream=True, timeout=10)
            if r.url and r.url != item.get('url'):
                item['url'] = r.url
                item['redirected'] = True
                debug_log('probe redirected url', self._url_summary(r.url))
            status_code = r.status_code
            r.close()
            return status_code in (200, 206), status_code
        except Exception as e:
            return False, repr(e)

    def choose_best_video_audio(self, formats):
        videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        audios = [x for x in formats if x.get('acodec') != 'none' and x.get('vcodec') == 'none']
        videos.sort(key=lambda x: (int(x.get('height') or 0), int(x.get('bitrate') or 0)), reverse=True)
        audios.sort(key=lambda x: (self._audio_lang_priority(x), int(x.get('bitrate') or 0)), reverse=True)
        return (videos[0] if videos else None), (audios[0] if audios else None)

    def _url_summary(self, media_url):
        parsed = urlparse(media_url or '')
        query = parse_qs(parsed.query)
        keys = ['itag', 'mime', 'c', 'expire', 'ip', 'mip', 'source', 'requiressl', 'gir', 'clen', 'dur', 'n', 'pot', 'sig', 'lsig', 'cms_redirect']
        return {
            'host': parsed.netloc,
            'path': parsed.path,
            'len': len(media_url or ''),
            'params': {k: bool(query.get(k)) if k in ('pot', 'sig', 'lsig', 'cms_redirect') else (query.get(k, [''])[0][:80]) for k in keys if k in query}
        }

    def _get(self, url, **kwargs):
        headers = self.headers.copy()
        headers.update(kwargs.pop('headers', {}) or {})
        headers.setdefault('Accept-Encoding', 'gzip, deflate')
        timeout = kwargs.pop('timeout', 10)
        last_exc = None
        for attempt in range(2):
            try:
                r = self.session.get(url, headers=headers, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except Exception as e:
                last_exc = e
                time.sleep(0.3 * (attempt + 1))
        if last_exc:
            raise last_exc

    def _post_json(self, url, payload, headers=None):
        h = self.headers.copy()
        h.update({'Content-Type': 'application/json', 'Origin': 'https://www.youtube.com', 'Accept-Encoding': 'gzip, deflate'})
        if headers:
            h.update({k: v for k, v in headers.items() if v})
        last_exc = None
        for attempt in range(2):
            try:
                r = self.session.post(url, json=payload, headers=h, timeout=10)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_exc = e
                time.sleep(0.3 * (attempt + 1))
        if last_exc:
            raise last_exc


    def _call_direct_clients(self, video_id):
        clients = [
            {'clientName': 'ANDROID', 'clientVersion': '20.10.38', 'ua': 'com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip', 'hl': 'zh-CN', 'gl': 'US'},
            {'clientName': 'IOS', 'clientVersion': '21.02.3', 'ua': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)', 'hl': 'zh-CN', 'gl': 'US'},
        ]
        results = []
        for c in clients:
            try:
                payload = {
                    'context': {'client': {'clientName': c['clientName'], 'clientVersion': c['clientVersion'], 'hl': c['hl'], 'gl': c['gl']}},
                    'videoId': video_id,
                    'contentCheckOk': True,
                    'racyCheckOk': True
                }
                r = self.session.post('https://www.youtube.com/youtubei/v1/player?prettyPrint=false', json=payload, headers={'User-Agent': c['ua']}, timeout=15)
                if r.status_code == 200:
                    d = r.json()
                    if d.get('streamingData'):
                        d['_client_name'] = c['clientName']
                        d['_client_ua'] = c['ua']
                        results.append(d)
            except Exception as e:
                self.trace('direct client error', {'client': c['clientName'], 'error': repr(e)})
        return results

    def _call_player_api(self, video_id, api_key, context, referer, visitor_data=None, sts=None, reload_token=None):
        # NOTE: VISIONOS 1.02 在携带 ANDROID 20.10.38 的 visitorData 时，返回全量 1080p/4K 直链与 SABR 流，
        # 且实测免 GVS po_token、无 60s/4.19MB 配额限制、无 3 次 Range 限制！
        clients = [
            {'client': {'clientName': 'VISIONOS', 'clientVersion': '1.02', 'deviceMake': 'Apple', 'deviceModel': 'RealityDevice17,1', 'userAgent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15', 'osName': 'visionOS', 'osVersion': '26.5.23O471', 'hl': 'zh-CN', 'gl': 'US'}},
            {'client': {'clientName': 'ANDROID_VR', 'clientVersion': '1.65.10', 'deviceMake': 'Oculus', 'deviceModel': 'Quest 3', 'androidSdkVersion': 32, 'userAgent': 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip', 'osName': 'Android', 'osVersion': '12L', 'hl': 'zh-CN', 'gl': 'US'}},
            {'client': {'clientName': 'ANDROID', 'clientVersion': '20.10.38', 'androidSdkVersion': 30, 'userAgent': 'com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip', 'osName': 'Android', 'osVersion': '11', 'hl': 'zh-CN', 'gl': 'US'}},
            {'client': {'clientName': 'IOS', 'clientVersion': '21.02.3', 'deviceMake': 'Apple', 'deviceModel': 'iPhone16,2', 'userAgent': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)', 'osName': 'iPhone', 'osVersion': '18.3.2.22D82', 'hl': 'zh-CN', 'gl': 'US'}},
        ]
        results_by_idx = [None] * len(clients)
        init_vd = visitor_data
        if not init_vd and getattr(self, '_cached_visitor_data', None) and getattr(self, '_cached_visitor_exp', 0) > time.time():
            init_vd = self._cached_visitor_data
        shared_vd = [init_vd]

        def _fetch_one_client(idx, ctx):
            client = (ctx.get('client') or {}).copy()
            client_name = client.get('clientName')
            try:
                url = f'https://www.youtube.com/youtubei/v1/player?key={api_key}&prettyPrint=false' if api_key else 'https://www.youtube.com/youtubei/v1/player?prettyPrint=false'
                payload = {
                    'context': {'client': client},
                    'videoId': video_id,
                    'contentCheckOk': True,
                    'racyCheckOk': True,
                }
                if sts:
                    payload['playbackContext'] = {'contentPlaybackContext': {'signatureTimestamp': sts}}
                if reload_token:
                    payload.setdefault('playbackContext', {})['reloadPlaybackContext'] = {'reloadPlaybackParams': {'token': reload_token}}
                client_ua = client.get('userAgent') or 'com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip'
                headers = {
                    'User-Agent': client_ua,
                    'Content-Type': 'application/json',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                    'X-YouTube-Client-Name': str(self._client_name_id(client_name)),
                    'X-YouTube-Client-Version': client.get('clientVersion') or '',
                    'Connection': 'close',
                }
                cur_vd = shared_vd[0]
                if cur_vd:
                    headers['X-Goog-Visitor-Id'] = cur_vd
                    client['visitorData'] = cur_vd
                resp = requests.post(url, json=payload, headers=headers, proxies=dict(self.session.proxies or {}), timeout=7)
                resp.raise_for_status()
                data = resp.json()
                resp_vd = (data.get('responseContext') or {}).get('visitorData')
                if resp_vd and not shared_vd[0]:
                    shared_vd[0] = resp_vd
                eff_vd = cur_vd or resp_vd or shared_vd[0]
                status = (data.get('playabilityStatus') or {}).get('status')
                sd = data.get('streamingData') or {}
                data['_client_name'] = client_name
                data['_client_ua'] = client_ua
                data['_client_info'] = {
                    'clientNameId': self._client_name_id(client_name),
                    'clientName': client_name,
                    'clientVersion': client.get('clientVersion'),
                    'userAgent': client_ua,
                    'deviceMake': client.get('deviceMake'),
                    'deviceModel': client.get('deviceModel'),
                    'androidSdkVersion': client.get('androidSdkVersion'),
                    'osName': client.get('osName'),
                    'osVersion': client.get('osVersion'),
                    'hl': client.get('hl') or 'zh-CN',
                    'gl': client.get('gl') or 'US',
                    'visitorData': eff_vd,
                }
                direct_video = [x for x in sd.get('adaptiveFormats') or [] if str(x.get('mimeType') or '').startswith('video/') and (x.get('url') or x.get('cipher') or x.get('signatureCipher'))]
                self.trace('player api client', {
                    'client': client_name,
                    'status': status,
                    'has_streaming': bool(sd),
                    'formats': len(sd.get('formats') or []),
                    'adaptive': len(sd.get('adaptiveFormats') or []),
                    'direct_video': len(direct_video),
                    'has_sabr_url': bool(sd.get('serverAbrStreamingUrl')),
                    'has_ustreamer': bool(self._traverse(data, ('playerConfig', 'mediaCommonConfig', 'mediaUstreamerRequestConfig', 'videoPlaybackUstreamerConfig'))),
                })
                if sd:
                    results_by_idx[idx] = data
            except Exception as e:
                self.trace('player api client error', {'client': client_name, 'error': repr(e)})

        # 若尚未持有 visitorData，先调用 ANDROID (idx=2) 提取 visitorData，使 Cloudflare 节点下 VISIONOS 与 ANDROID_VR 100% 解锁
        android_idx = 2
        if not shared_vd[0]:
            _fetch_one_client(android_idx, clients[android_idx])
        threads = []
        for idx, ctx in enumerate(clients):
            if idx == android_idx and results_by_idx[android_idx] is not None:
                continue
            t = threading.Thread(target=_fetch_one_client, args=(idx, ctx), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=8)
        return [r for r in results_by_idx if r]

    def _normalize_format(self, fmt, player_url):
        media_url = fmt.get('url')
        if not media_url:
            cipher = fmt.get('signatureCipher') or fmt.get('cipher')
            if cipher:
                media_url = self._decrypt_signature_cipher(cipher, player_url)
        if not media_url:
            return None
        media_url = self._decrypt_nsig(media_url, player_url)
        client_name = fmt.get('_client_name')
        po_token = self._get_po_token(client_name, 'gvs') if client_name else None
        if po_token:
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}pot={quote(po_token)}'
        mime = fmt.get('mimeType') or ''
        ext = 'mp4' if 'mp4' in mime else 'webm' if 'webm' in mime else 'unknown'
        codecs = self._search(r'codecs="([^"]+)"', mime) or ''
        has_audio = mime.startswith('audio/') or any(x in codecs for x in ('mp4a', 'opus', 'vorbis'))
        has_video = mime.startswith('video/') or any(x in codecs for x in ('avc', 'vp9', 'av01', 'h264'))
        headers = (fmt.get('http_headers') or {}).copy()
        if fmt.get('_client_ua'):
            headers['User-Agent'] = fmt.get('_client_ua')
        return {
            'itag': fmt.get('itag'),
            'url': media_url,
            'mimeType': mime,
            'client': fmt.get('_client_name'),
            'ext': ext,
            'width': fmt.get('width') or 0,
            'height': fmt.get('height') or 0,
            'fps': fmt.get('fps') or 0,
            'bitrate': fmt.get('bitrate') or fmt.get('averageBitrate') or 0,
            'contentLength': fmt.get('contentLength'),
            'initRange': fmt.get('initRange') or {},
            'indexRange': fmt.get('indexRange') or {},
            'codecs': codecs,
            'quality': fmt.get('qualityLabel') or fmt.get('quality'),
            'colorInfo': fmt.get('colorInfo') or {},
            'vcodec': codecs if has_video else 'none',
            'acodec': codecs if has_audio else 'none',
            'audioTrack': fmt.get('audioTrack') or {},
            'xtags': fmt.get('xtags') or '',
            'isDrc': bool(fmt.get('isDrc')),
            'headers': headers,
        }

    def _decrypt_signature_cipher(self, cipher, player_url):
        data = parse_qs(cipher)
        media_url = unquote(data.get('url', [''])[0])
        sig = unquote(data.get('s', [''])[0])
        sp = data.get('sp', ['sig'])[0]
        if not media_url:
            return ''
        if sig:
            decoded = self._decrypt_sig(sig, player_url)
            debug_log('signature cipher', {'sp': sp, 'sig_len': len(sig), 'decoded_changed': decoded != sig, 'has_player': bool(player_url)})
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}{sp}={quote(decoded)}'
        return media_url

    def _decrypt_sig(self, sig, player_url):
        cache_key = player_url or ''
        if cache_key in self.sig_plan_cache:
            plan = self.sig_plan_cache.get(cache_key)
            debug_log('sig plan cache', {'has_plan': bool(plan), 'plan': plan[:8] if plan else None})
        else:
            code = self._get_player_code(player_url)
            plan = self._extract_sig_plan(code)
            self.sig_plan_cache[cache_key] = plan
            debug_log('sig plan', {'code_len': len(code), 'has_plan': bool(plan), 'plan': plan[:8] if plan else None})
        if not plan:
            return sig
        arr = list(sig)
        for op, arg in plan:
            if op == 'reverse':
                arr.reverse()
            elif op in ('slice', 'splice'):
                arr = arr[int(arg):]
            elif op == 'swap' and arr:
                j = int(arg) % len(arr)
                arr[0], arr[j] = arr[j], arr[0]
        return ''.join(arr)

    def _decrypt_nsig(self, media_url, player_url):
        try:
            parsed = urlparse(media_url)
            query = parse_qs(parsed.query)
            n_value = query.get('n', [None])[0]
            if not n_value:
                return media_url
            path_match = re.search(r'/n/([^/]+)', parsed.path)
            if path_match and path_match.group(1) != n_value:
                new_path = parsed.path.replace(f"/n/{path_match.group(1)}", f"/n/{n_value}", 1)
                fixed = urlunparse(parsed._replace(path=new_path))
                debug_log('n path synced', {'old': path_match.group(1), 'new_len': len(n_value), 'changed': fixed != media_url})
                return fixed
            debug_log('n present', {'n_len': len(n_value), 'has_path_n': bool(path_match)})
            return media_url
        except Exception as e:
            debug_log('n sync error', repr(e))
            return media_url

    def _get_player_code(self, player_url):
        if not player_url:
            return ''
        if player_url in self.player_cache:
            return self.player_cache[player_url]
        if player_url.startswith('//'):
            player_url = 'https:' + player_url
        elif player_url.startswith('/'):
            player_url = 'https://www.youtube.com' + player_url
        try:
            code = self._get(player_url).text
        except Exception:
            code = ''
        self.player_cache[player_url] = code
        return code

    def _extract_sig_plan(self, code):
        if not code:
            return None
        name = None
        for pattern in [
            r'\.sig\|\|([a-zA-Z0-9_$]+)\(',
            r'"signature",\s*([a-zA-Z0-9_$]+)\(',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\);',
        ]:
            m = re.search(pattern, code)
            if m:
                name = m.group(1)
                break
        if not name:
            return None
        body = self._extract_js_function_body(code, name)
        if not body:
            return None
        helper = self._search(r'([a-zA-Z0-9_$]+)\.[a-zA-Z0-9_$]+\(a,\d+\)', body)
        helper_map = self._extract_helper_object(code, helper) if helper else {}
        plan = []
        for part in body.split(';'):
            if 'reverse()' in part:
                plan.append(('reverse', 0))
                continue
            m = re.search(r'\.slice\((\d+)\)', part)
            if m:
                plan.append(('slice', int(m.group(1))))
                continue
            m = re.search(r'\.splice\(0,(\d+)\)', part)
            if m:
                plan.append(('splice', int(m.group(1))))
                continue
            m = re.search(r'([a-zA-Z0-9_$]+)\.([a-zA-Z0-9_$]+)\(a,(\d+)\)', part)
            if m and m.group(1) == helper:
                op = helper_map.get(m.group(2))
                if op:
                    plan.append((op, int(m.group(3))))
        return plan or None

    def _extract_helper_object(self, code, name):
        if not name:
            return {}
        m = re.search(r'var\s+' + re.escape(name) + r'=\{(.+?)\};', code, re.S) or re.search(re.escape(name) + r'=\{(.+?)\};', code, re.S)
        if not m:
            return {}
        result = {}
        for method, body in re.findall(r'([a-zA-Z0-9_$]+):function\([a-z,]+\)\{(.*?)\}', m.group(1)):
            if '.reverse(' in body:
                result[method] = 'reverse'
            elif '.splice(' in body:
                result[method] = 'splice'
            elif '.slice(' in body:
                result[method] = 'slice'
            elif 'a[0]' in body and 'length' in body:
                result[method] = 'swap'
        return result

    def _extract_n_function(self, code):
        if not code:
            return None
        name = None
        for pattern in [
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)(?:\[(\d+)\])?\(b\)',
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)\(b\)',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{var b=a\.split\(""\)',
            r'function\s+([a-zA-Z0-9_$]+)\(a\)\{var b=a\.split\(""\)',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\)',
        ]:
            m = re.search(pattern, code)
            if m:
                name = m.group(1)
                break
        if not name:
            return None
        body = self._extract_js_function_body(code, name)
        debug_log('n function', {'name': name, 'body_len': len(body)})
        if not body:
            return None

        def transform(value):
            arr = list(value)
            for part in body.split(';'):
                if 'reverse()' in part:
                    arr.reverse()
                m = re.search(r'\.slice\((\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
                m = re.search(r'\.splice\(0,(\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
            return ''.join(arr) or value
        return transform

    def _extract_js_function_body(self, code, name):
        starts = []
        for pattern in [
            r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{',
            re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
            r'var\s+' + re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
        ]:
            m = re.search(pattern, code)
            if m:
                starts.append(m.end() - 1)
        if not starts:
            return ''
        start = starts[0]
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(code)):
            ch = code[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch in ('"', "'", '`'):
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return code[start + 1:i]
        return ''

    def _extract_ytcfg(self, text):
        m = re.search(r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;', text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    def _extract_initial_player_response(self, text):
        return self._extract_json_after(text, 'ytInitialPlayerResponse')

    def _extract_json_after(self, text, marker):
        pos = text.find(marker)
        if pos < 0:
            return None
        start = text.find('{', pos)
        if start < 0:
            return None
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch == '"':
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None

    def _extract_player_url(self, text):
        for pattern in [
            r'"jsUrl":"([^"]+)"',
            r'"PLAYER_JS_URL":"([^"]+)"',
            r'(/s/player/[^"\\]+/base\.js)',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1).replace('\\/', '/')
        return ''

    @staticmethod
    def _search(pattern, text, default=None):
        m = re.search(pattern, text or '', re.S)
        return m.group(1) if m else default

    def trace(self, event, data=None):
        if self.config.get('trace', True):
            debug_log(event, data)

    def _extract_formats_from_responses(self, responses, player_url):
        formats = []
        sabr_formats = []
        seen_direct = set()
        seen_sabr = set()
        source_summary = []
        for response in responses:
            if not response:
                continue
            sd = response.get('streamingData') or {}
            raw_list = (sd.get('formats') or []) + (sd.get('adaptiveFormats') or [])
            client_name = response.get('_client_name')
            client_ua = response.get('_client_ua')
            client_info = response.get('_client_info') or {}
            server_abr_url = sd.get('serverAbrStreamingUrl')
            ustreamer_config = self._traverse(response, ('playerConfig', 'mediaCommonConfig', 'mediaUstreamerRequestConfig', 'videoPlaybackUstreamerConfig'))
            source_summary.append({
                'client': client_name,
                'formats': len(sd.get('formats') or []),
                'adaptive': len(sd.get('adaptiveFormats') or []),
                'has_sabr_url': bool(server_abr_url),
                'has_ustreamer': bool(ustreamer_config),
            })
            for raw0 in raw_list:
                raw = raw0.copy()
                raw['_client_name'] = client_name
                raw['_client_ua'] = client_ua
                direct_key = (client_name, raw.get('itag'), raw.get('xtags'), raw.get('url') or raw.get('signatureCipher') or raw.get('cipher') or raw.get('mimeType'))
                if direct_key not in seen_direct:
                    seen_direct.add(direct_key)
                    item = self._normalize_format(raw, player_url)
                    if item and item.get('url'):
                        formats.append(item)

                if server_abr_url and ustreamer_config:
                    sabr_key = (client_name, raw.get('itag'), raw.get('mimeType'), raw.get('xtags'))
                    if sabr_key not in seen_sabr:
                        seen_sabr.add(sabr_key)
                        sabr_item = self._normalize_sabr_format(raw, server_abr_url, ustreamer_config, client_name, client_ua, client_info)
                        if sabr_item:
                            sabr_formats.append(sabr_item)
        self.trace('formats extracted', {'sources': source_summary, 'direct': len(formats), 'sabr': len(sabr_formats)})
        return formats, sabr_formats

    def _normalize_sabr_format(self, fmt, server_abr_url, ustreamer_config, client_name, client_ua, client_info):
        mime = fmt.get('mimeType') or ''
        codecs = self._search(r'codecs="([^"]+)"', mime) or ''
        has_audio = mime.startswith('audio/') or any(x in codecs for x in ('mp4a', 'opus', 'vorbis'))
        has_video = mime.startswith('video/') or any(x in codecs for x in ('avc', 'vp9', 'vp09', 'av01', 'h264'))
        if has_audio and has_video:
            return None
        itag = fmt.get('itag')
        if not itag:
            return None
        headers = {}
        if client_ua:
            headers['User-Agent'] = client_ua
        po_token = self._get_po_token(client_name, 'gvs') if client_name else None
        return {
            'itag': itag,
            'url': server_abr_url.replace('.c.youtube.com/videoplayback', '.googlevideo.com/videoplayback'),
            'protocol': 'sabr',
            'mimeType': mime,
            'client': client_name,
            'ext': 'mp4' if 'mp4' in mime else 'webm' if 'webm' in mime else 'unknown',
            'width': fmt.get('width') or 0,
            'height': fmt.get('height') or 0,
            'fps': fmt.get('fps') or 0,
            'bitrate': fmt.get('bitrate') or fmt.get('averageBitrate') or 0,
            'contentLength': fmt.get('contentLength'),
            'codecs': codecs,
            'quality': fmt.get('qualityLabel') or fmt.get('quality'),
            'vcodec': codecs if has_video else 'none',
            'acodec': codecs if has_audio else 'none',
            'audioTrack': fmt.get('audioTrack') or {},
            'xtags': fmt.get('xtags') or '',
            'isDrc': bool(fmt.get('isDrc')),
            'headers': headers,
            '_sabr_config': {
                'server_abr_streaming_url': server_abr_url,
                'video_playback_ustreamer_config': ustreamer_config,
                'client_name': client_name,
                'client_info': client_info,
                'po_token': po_token,
                'itag': itag,
                'xtags': fmt.get('xtags'),
                'last_modified': fmt.get('lastModified'),
                'target_duration_sec': fmt.get('targetDurationSec'),
            },
        }

    def _traverse(self, obj, path, default=None):
        cur = obj
        try:
            for key in path:
                if not isinstance(cur, dict):
                    return default
                cur = cur.get(key)
                if cur is None:
                    return default
            return cur
        except Exception:
            return default

    def sabr_first_chunk(self, video_item, audio_item=None, max_bytes=2 * 1024 * 1024, state_key=None):
        cfg = (video_item or {}).get('_sabr_config') or (audio_item or {}).get('_sabr_config') or {}
        if not cfg:
            raise Exception('missing sabr config')
        video_itag = video_item.get('itag') if video_item and video_item.get('vcodec') != 'none' else None
        audio_itag = audio_item.get('itag') if audio_item else None
        state_key = state_key or '%s:%s:%s' % (cfg.get('client_name'), video_itag or 0, audio_itag or 0)
        state = self.sabr_state.setdefault(state_key, {
            'playback_cookie': None, 'url': None, 'seen': [], 'request_count': 0,
            'initialized': {}, 'buffered': {}, 'player_time_ms': 0, 'init_media': {},
        })
        url = state.get('url') or cfg.get('server_abr_streaming_url') or video_item.get('url') or audio_item.get('url')
        headers = {
            'Content-Type': 'application/x-protobuf',
            'Accept': 'application/vnd.yt-ump',
            'Accept-Encoding': 'identity',
        }
        if video_item and video_item.get('headers'):
            headers.update(video_item.get('headers') or {})
        last_status = None
        media = bytearray()
        parts = []
        next_cookie = None
        redirect_url = None
        current_media_itag = None
        current_format_id = None
        current_header = None
        media_headers = []
        skipped_media_parts = 0
        duplicate_media_parts = 0
        max_parts = int(self.config.get('sabr_max_parts') or 512)
        seen = state.setdefault('seen', [])
        target_itag = video_itag or audio_itag
        for attempt in range(4):
            initialized_ids = list((state.get('initialized') or {}).values())
            buffered_ranges = []
            for br in (state.get('buffered') or {}).values():
                packed = build_buffered_range(
                    br.get('format_id'), br.get('start_ms') or 0, br.get('duration_ms') or 0,
                    br.get('start_seq'), br.get('end_seq'))
                if packed:
                    buffered_ranges.append(packed)
            payload = build_vpabr_request(
                cfg, video_itag=video_itag, audio_itag=audio_itag,
                start_time_ms=int(state.get('player_time_ms') or 0),
                playback_cookie=state.get('playback_cookie'),
                initialized_format_ids=initialized_ids, buffered_ranges=buffered_ranges)
            rn = int(state.get('request_count') or 0) + 1
            self.trace('sabr request', {
                'payload': len(payload), 'video_itag': video_itag, 'audio_itag': audio_itag, 'url_len': len(url or ''),
                'state_key': state_key, 'has_cookie': bool(state.get('playback_cookie')), 'rn': rn,
                'initialized': len(initialized_ids), 'buffered': len(buffered_ranges), 'player_time_ms': int(state.get('player_time_ms') or 0),
            })
            r = self.session.post(url, params={'rn': rn}, data=payload, headers=headers, stream=True, timeout=30)
            state['request_count'] = rn
            last_status = r.status_code
            self.trace('sabr http response', {'attempt': attempt + 1, 'rn': rn, 'status': r.status_code, 'content_type': r.headers.get('content-type'), 'content_length': r.headers.get('content-length'), 'encoding': r.headers.get('content-encoding'), 'host': urlparse(url or '').netloc})
            cur_redirect = None
            try:
                for part_id, part_data in iter_ump_parts(r.raw, max_parts=max_parts):
                    parts.append({'id': part_id, 'size': len(part_data)})
                    if part_id == UMP_MEDIA_HEADER:
                        current_media_itag = _pb_get_int(part_data, 3)
                        current_format_id = _sabr_header_format_id(part_data, current_media_itag)
                        is_init = _pb_get_int(part_data, 8)
                        seq = _pb_get_int(part_data, 9)
                        start_ms = _pb_get_int(part_data, 11) or 0
                        duration_ms = _pb_get_int(part_data, 12) or 0
                        if not start_ms and not duration_ms:
                            tr_start_ms, tr_duration_ms = _sabr_time_range_ms(part_data)
                            start_ms = tr_start_ms or start_ms
                            duration_ms = tr_duration_ms or duration_ms
                        if seq is not None and not duration_ms and not is_init:
                            # Some SABR MediaHeader omit timing. yt-dlp requires duration to progress;
                            # use targetDurationSec as conservative fallback so buffered_ranges/player_time advance.
                            duration_ms = int(float(cfg.get('target_duration_sec') or 5) * 1000)
                            start_ms = int(max(0, int(seq) - 1) * duration_ms)
                        current_header = {
                            'itag': current_media_itag, 'format_id': current_format_id, 'is_init': is_init,
                            'seq': seq, 'start_ms': start_ms, 'duration_ms': duration_ms,
                        }
                        media_headers.append({'itag': current_media_itag, 'size': len(part_data), 'is_init': is_init, 'seq': seq, 'start_ms': start_ms, 'duration_ms': duration_ms})
                        if current_format_id and is_init:
                            state.setdefault('initialized', {})[str(current_media_itag or current_format_id)] = current_format_id
                        continue
                    if part_id == UMP_MEDIA:
                        if target_itag and current_media_itag and int(current_media_itag) != int(target_itag):
                            skipped_media_parts += 1
                            continue
                        key = _sabr_media_key(part_data)
                        if key and key in seen:
                            duplicate_media_parts += 1
                            continue
                        if key:
                            seen.append(key)
                            if len(seen) > 512:
                                del seen[:-512]
                        media.extend(part_data)
                        if current_header and current_header.get('format_id'):
                            fmt_key = str(current_header.get('itag') or current_header.get('format_id'))
                            if current_header.get('is_init'):
                                state.setdefault('initialized', {})[fmt_key] = current_header.get('format_id')
                                # SABR 后续响应通常只给 media chunk，不再给 EBML/ftyp init。
                                # 本地代理每次都是独立 HTTP 响应，缓存 init 用于后续补头，避免播放器报不支持格式。
                                state.setdefault('init_media', {})[fmt_key] = bytes(part_data)
                            else:
                                seq = current_header.get('seq')
                                start_ms = int(current_header.get('start_ms') or 0)
                                duration_ms = int(current_header.get('duration_ms') or 0)
                                old = state.setdefault('buffered', {}).get(fmt_key)
                                if not old:
                                    state['buffered'][fmt_key] = {
                                        'format_id': current_header.get('format_id'), 'start_ms': start_ms, 'duration_ms': duration_ms,
                                        'start_seq': seq, 'end_seq': seq,
                                    }
                                else:
                                    end_ms = max(int(old.get('start_ms') or 0) + int(old.get('duration_ms') or 0), start_ms + duration_ms)
                                    old['start_ms'] = min(int(old.get('start_ms') or 0), start_ms)
                                    old['duration_ms'] = max(0, end_ms - int(old.get('start_ms') or 0))
                                    if seq is not None:
                                        old['start_seq'] = seq if old.get('start_seq') is None else min(old.get('start_seq'), seq)
                                        old['end_seq'] = seq if old.get('end_seq') is None else max(old.get('end_seq'), seq)
                                if start_ms or duration_ms:
                                    state['player_time_ms'] = max(int(state.get('player_time_ms') or 0), start_ms + duration_ms)
                        if len(media) >= max_bytes:
                            break
                    elif part_id == UMP_NEXT_REQUEST_POLICY:
                        next_cookie = _pb_get_bytes(part_data, 7)
                        if next_cookie:
                            state['playback_cookie'] = next_cookie
                    elif part_id == UMP_SABR_REDIRECT:
                        cur_redirect = _pb_get_str(part_data, 1)
                        redirect_url = cur_redirect
                        if cur_redirect:
                            state['url'] = cur_redirect
                        self.trace('sabr redirect part', {'url_len': len(cur_redirect or ''), 'host': urlparse(cur_redirect or '').netloc})
                    elif part_id == UMP_SABR_ERROR:
                        err_type = _pb_get_str(part_data, 1)
                        action = _pb_get_int(part_data, 2)
                        err_msg = _pb_get_bytes(part_data, 3) or b''
                        err_status = _pb_get_int(err_msg, 1)
                        err_inner_type = _pb_get_int(err_msg, 4)
                        self.trace('sabr error part', {'type': err_type, 'action': action, 'status_code': err_status, 'inner_type': err_inner_type, 'size': len(part_data)})
                    elif part_id in (UMP_RELOAD_PLAYER_RESPONSE, UMP_STREAM_PROTECTION_STATUS):
                        self.trace('sabr control part', {'id': part_id, 'size': len(part_data)})
            finally:
                try:
                    r.close()
                except Exception:
                    pass
            if len(media) >= max_bytes:
                break
            if cur_redirect:
                url = cur_redirect
                continue
            if media:
                break
            break
        self.trace('sabr response', {
            'status': last_status, 'parts': parts[:40], 'media_len': len(media),
            'has_cookie': bool(state.get('playback_cookie') or next_cookie), 'redirect': bool(redirect_url or state.get('url')),
            'media_headers': media_headers[:12], 'skipped_media_parts': skipped_media_parts,
            'duplicate_media_parts': duplicate_media_parts, 'state_seen': len(seen),
            'initialized': len(state.get('initialized') or {}), 'buffered': list((state.get('buffered') or {}).values())[:4],
            'player_time_ms': int(state.get('player_time_ms') or 0),
        })
        return bytes(media), {'status': last_status, 'parts': parts, 'next_cookie': state.get('playback_cookie') or next_cookie, 'redirect_url': redirect_url or state.get('url'), 'media_headers': media_headers, 'skipped_media_parts': skipped_media_parts, 'duplicate_media_parts': duplicate_media_parts}

    def sabr_get_segment(self, video_item, audio_item, track, segment, state_key):
        """Fetch a complete SABR init/media segment for the local DASH bridge.

        Mirrors yt-dlp's SabrStream/SabrFD contract: MEDIA_HEADER opens a segment,
        MEDIA parts are routed by their leading header_id varint, and MEDIA_END
        atomically publishes the completed segment.
        """
        cfg = (video_item or {}).get('_sabr_config') or (audio_item or {}).get('_sabr_config') or {}
        if not cfg:
            raise Exception('missing sabr config')
        video_itag = int((video_item or {}).get('itag') or 0) or None
        audio_itag = int((audio_item or {}).get('itag') or 0) or None
        state = self.sabr_state.setdefault(state_key, {
            'playback_cookie': None, 'url': None, 'request_count': 0,
            'initialized': {}, 'buffered': {}, 'player_time_ms': 0,
            'partial': {}, 'init_segments': {}, 'segments': {},
            'segment_meta': {}, 'segment_order': {},
            'lock': threading.RLock(), 'last_status': None,
        })
        # Upgrade a state created by an older implementation without losing cookies.
        state.setdefault('partial', {})
        state.setdefault('init_segments', {})
        state.setdefault('segments', {})
        state.setdefault('segment_meta', {})
        state.setdefault('segment_order', {})
        state.setdefault('initialized', {})
        state.setdefault('buffered', {})
        state.setdefault('lock', threading.RLock())
        target_itag = video_itag if track == 'video' else audio_itag
        if not target_itag:
            return None, {'error': 'track not selected', 'track': track}
        want_init = str(segment) == 'init'
        try:
            want_seq = None if want_init else int(segment)
        except Exception:
            return None, {'error': 'invalid segment', 'segment': segment}
        # DASH $Number$ 是本地桥的编号，不等于 YouTube SABR 原生 sequence_number。
        # 必须先换算成时间，再按 MediaHeader.start_ms/duration_ms 查找原生段。
        track_cfg = ((video_item if track == 'video' else audio_item) or {}).get('_sabr_config') or {}
        dash_seg_ms = int(float((track_cfg.get('target_duration_sec') or (6 if track == 'video' else 10)) * 1000))
        if track == 'audio' and dash_seg_ms < 8000:
            dash_seg_ms = 10000
        if dash_seg_ms <= 0:
            dash_seg_ms = 6000 if track == 'video' else 10000
        target_ms = None if want_init else max(0, (want_seq - 1) * dash_seg_ms)
        max_pumps = int(self.config.get('sabr_segment_fetch_requests') or 10)

        with state['lock']:
            if want_init:
                found = state['init_segments'].get(target_itag)
                if found is not None:
                    return found, {'status': state.get('last_status'), 'itag': target_itag,
                                    'segment': segment, 'request_count': state.get('request_count')}

            seeked = False
            reloaded = False
            transport_retries = 0
            for pump_idx in range(max_pumps):
                if want_init:
                    found, native_seq, native_meta = state['init_segments'].get(target_itag), None, None
                else:
                    found, native_seq, native_meta = self._sabr_find_segment_by_time(
                        state, target_itag, target_ms, dash_seg_ms, want_seq=want_seq)
                if found is not None:
                    return found, {
                        'status': state.get('last_status'), 'itag': target_itag,
                        'segment': segment, 'request_count': state.get('request_count'),
                        'seeked': seeked, 'reloaded': reloaded, 'target_ms': target_ms,
                        'native_seq': native_seq, 'native_meta': native_meta,
                    }
                if state.get('exhausted'):
                    break
                if not want_init and not seeked and self._sabr_should_seek_time(
                        state, target_itag, target_ms, dash_seg_ms, want_seq=want_seq):
                    cached = self._sabr_cached_time_range(state, target_itag)
                    deep_seek = (
                        target_ms is not None and self.sabr_reload_hook and not reloaded and
                        (cached is None or target_ms > int(cached[1]) + 5 * dash_seg_ms))
                    if deep_seek:
                        # 深跳或越 60s 断点：若目标已 >= 50s，直接切入本地 Super-Chunk WebM Cluster 极速续播，免去 15s 的无效 reload
                        if (target_ms or 0) >= 50000:
                            state['exhausted'] = True
                            self.trace('sabr deep-seek >=50s fast switch to direct-webm', {
                                'itag': target_itag, 'dash_number': want_seq, 'seek_ms': target_ms,
                            })
                            break
                        self.trace('sabr deep-seek reload', {
                            'itag': target_itag, 'dash_number': want_seq, 'seek_ms': target_ms,
                            'cached_time_range': cached,
                        })
                        new_cfg, new_video, new_audio = self._sabr_apply_reload(
                            state, state_key, video_item, audio_item, target_ms)
                        state['reload_needed'] = False
                        seeked = True
                        if new_cfg:
                            cfg, video_item, audio_item = new_cfg, new_video, new_audio
                            reloaded = True
                        else:
                            self._sabr_seek(state, target_ms)
                    else:
                        self._sabr_seek(state, target_ms)
                        seeked = True
                        self.trace('sabr seek', {
                            'itag': target_itag, 'dash_number': want_seq, 'seek_ms': target_ms,
                            'cached_time_range': cached,
                        })
                before = len((state.get('segments', {}).get(target_itag) or {}))
                pumped = False
                try:
                    self._sabr_pump_once(state, cfg, video_item, audio_item)
                    transport_retries = 0
                    pumped = True
                except Exception as e:
                    if not self._sabr_is_retryable_transport_error(e) or transport_retries >= 2:
                        raise
                    transport_retries += 1
                    state['partial'] = {}
                    self.trace('sabr transport retry', {
                        'attempt': transport_retries, 'error': repr(e),
                        'track': track, 'dash_number': want_seq,
                    })
                after = len((state.get('segments', {}).get(target_itag) or {}))
                # NOTE: 起播阶段（want_init=True）若因 10172 出口 IP 轮换导致首包即返回 RELOAD_PLAYER_RESPONSE(46)，
                # 或连续 2 次 pump 均未产出任何 init 段，立即标记 exhausted 并无缝切入 direct-webm，消除 19 次无效请求（省去 20s 黑屏等待）
                if want_init:
                    if state['init_segments'].get(target_itag) is not None:
                        continue
                    if state.get('reload_needed') or (pumped and pump_idx >= 1):
                        state['reload_needed'] = False
                        state['exhausted'] = True
                        self.trace('sabr init reload/empty -> instant switch to direct-webm', {
                            'itag': target_itag, 'track': track, 'pump_idx': pump_idx,
                            'request_count': state.get('request_count'),
                        })
                        break
                if state.get('reload_needed') and not want_init:
                    state['reload_needed'] = False
                    # 60 秒边界（>=45s）收到 RELOAD_PLAYER_RESPONSE(46) 时，直接标记会话耗尽并切入本地 Super-Chunk WebM Cluster，零延迟无缝过渡
                    if int(state.get('player_time_ms') or 0) >= 45000 or (target_ms or 0) >= 45000:
                        state['exhausted'] = True
                        self.trace('sabr 60s boundary reload -> instant switch to direct-webm', {
                            'itag': target_itag, 'segment': segment, 'target_ms': target_ms,
                            'player_time_ms': state.get('player_time_ms'),
                        })
                        break
                    if not reloaded and self.sabr_reload_hook:
                        new_cfg, new_video, new_audio = self._sabr_apply_reload(
                            state, state_key, video_item, audio_item,
                            target_ms if target_ms is not None else int(state.get('player_time_ms') or 0))
                        if new_cfg:
                            cfg, video_item, audio_item = new_cfg, new_video, new_audio
                            reloaded = True
                            continue
                if pumped and after == before and not want_init and (reloaded or pump_idx >= 1 or state.get('pump_timed_out')):
                    state['exhausted'] = True
                    self.trace('sabr pump slow/empty -> instant switch to direct-webm', {
                        'itag': target_itag, 'segment': segment, 'target_ms': target_ms,
                        'pump_idx': pump_idx, 'timed_out': bool(state.get('pump_timed_out')),
                    })
                    break
            return None, {
                'error': 'segment not produced by SABR server', 'itag': target_itag,
                'segment': segment, 'target_ms': target_ms,
                'request_count': state.get('request_count'),
                'native_available': sorted((state['segments'].get(target_itag) or {}).keys())[-12:],
                'cached_time_range': self._sabr_cached_time_range(state, target_itag),
                'seeked': seeked, 'reloaded': reloaded,
            }

    def _sabr_apply_reload(self, state, state_key, video_item, audio_item, resume_ms):
        """服务器要求 reload：向 Spider 回调换 fresh SABR 会话，重置状态后从 resume_ms 续拉。

        返回 (new_cfg, new_video_item, new_audio_item)；失败返回 (None, None, None)，
        由上层收场（最终切入本地 Super-Chunk 续播）。已缓存的分段保留在 state['segments']。
        """
        # 选项1（fresh，默认）：丢弃 reload_token，把这次当「全新起播 seek 到 resume_ms」而非
        # reload_token 续会话。SABR 前 66s 冷启动已证明稳定，全新会话 + player_time=resume_ms +
        # 空续播凭证 = 等价于一次干净的起播 seek，绕开 reload_token 续会话的 66s 死锁与音频饿死。
        fresh_mode = str(self.config.get('sabr_reload_mode', 'fresh')).strip().lower() == 'fresh'
        try:
            reload_token = None if fresh_mode else state.get('reload_token')
            result = self.sabr_reload_hook(state_key, video_item, audio_item, reload_token)
        except Exception as e:
            self.trace('sabr reload hook error', {'error': repr(e)})
            return None, None, None
        if not result:
            self.trace('sabr reload unavailable', {'state_key': state_key})
            return None, None, None
        new_video, new_audio = result
        new_cfg = (new_video or {}).get('_sabr_config') or (new_audio or {}).get('_sabr_config') or {}
        if not new_cfg.get('server_abr_streaming_url'):
            self.trace('sabr reload missing url', {'state_key': state_key})
            return None, None, None
        # reload_token（part46 内 reloadPlaybackContext）已在上面取出并回传给 reload hook，
        # 由 _sabr_reload_session 走 extract(reload_token=...) 续同一会话（而非纯 fresh 冷启动）。
        # 续流关键修复：reload 时保留 initialized + buffered_ranges 作为「跨会话续播凭证」。
        # 旧实现把两者清空，fresh 会话第一个请求 = 「我在 resume_ms、但啥都没初始化/缓冲」，
        # 服务器判为不自洽的冷客户端 → 只回控制 part(51/47/35) 不发媒体（真机 rn7+ 实测）。
        # 正确做法：带着已播 0→resume_ms 的 buffered_ranges + 已初始化 format_id 请求，
        # 让新会话以「续播」姿态起流。仅丢弃仅属旧会话的 cookie 与半包 partial。
        keep_continuity = str(self.config.get('sabr_reload_keep_buffer', '1')).lower() not in ('0', 'false', 'off', 'no')
        # 选项1（默认 fresh）：越 70s 断点不做 reload_token 续会话，改「开全新 SABR 会话」
        # 冷启动从 resume_ms 起流——SABR 前 66s 已证明稳定，等价于一次全新起播 seek 到 resume_ms。
        # 冷启动必须清空续播凭证（initialized/buffered/cookie/partial），让 fresh ustreamer 以
        # 「全新客户端 seek 到 resume_ms」姿态起流，绕开 reload_token 续会话的 66s 死锁与音频饿死。
        fresh_mode = str(self.config.get('sabr_reload_mode', 'fresh')).strip().lower() == 'fresh'
        if fresh_mode:
            keep_continuity = False
        # ---- 埋点：换会话前快照续播凭证 + 新旧会话对比，供真机日志进一步判断 ----
        def _fmt_hex(v):
            try:
                b = v if isinstance(v, (bytes, bytearray)) else (v or {}).get('format_id') or b''
                return bytes(b).hex()
            except Exception:
                return None
        carried_init = dict(state.get('initialized') or {})
        carried_buf = {k: dict(v) for k, v in (state.get('buffered') or {}).items()}
        new_v_cfg = (new_video or {}).get('_sabr_config') or {}
        new_a_cfg = (new_audio or {}).get('_sabr_config') or {}
        self.trace('sabr reload continuity', {
            'state_key': state_key, 'resume_ms': int(resume_ms or 0),
            'keep_continuity': keep_continuity, 'had_reload_token': bool(reload_token),
            'carried_initialized': len(carried_init),
            'initialized_fmt_hex': {k: _fmt_hex(v) for k, v in carried_init.items()},
            'carried_buffered': [
                {'k': k, 'fmt_hex': _fmt_hex(v), 'start_ms': v.get('start_ms'),
                 'duration_ms': v.get('duration_ms'), 'start_seq': v.get('start_seq'),
                 'end_seq': v.get('end_seq')}
                for k, v in carried_buf.items()],
            'old_itags': {'video': (video_item or {}).get('itag'), 'audio': (audio_item or {}).get('itag')},
            'new_itags': {'video': (new_video or {}).get('itag'), 'audio': (new_audio or {}).get('itag')},
            'old_lmt': {'video': ((video_item or {}).get('_sabr_config') or {}).get('last_modified'),
                        'audio': ((audio_item or {}).get('_sabr_config') or {}).get('last_modified')},
            'new_lmt': {'video': new_v_cfg.get('last_modified'), 'audio': new_a_cfg.get('last_modified')},
        })
        # 换新会话 URL，丢弃仅属旧会话的 cookie 与半包 partial。
        state['url'] = new_cfg.get('server_abr_streaming_url')
        state['playback_cookie'] = None
        state['partial'] = {}
        if not keep_continuity:
            # 对照开关（sabr_reload_keep_buffer=0）：退回旧的「中点冷启动」行为。
            state['initialized'] = {}
            state['buffered'] = {}
        state['player_time_ms'] = int(resume_ms or 0)
        state.pop('reload_token', None)
        self.trace('sabr session reloaded', {
            'state_key': state_key, 'resume_ms': int(resume_ms or 0),
            'kept_initialized': len(state.get('initialized') or {}),
            'kept_buffered': len(state.get('buffered') or {}),
            'host': urlparse(new_cfg.get('server_abr_streaming_url') or '').netloc,
        })
        return new_cfg, new_video, new_audio

    @staticmethod
    def _sabr_find_segment_by_time(state, target_itag, target_ms, dash_seg_ms, want_seq=None):
        """严格无跳变连续分段匹配：
        1. 连续播放（want_seq - 1 已投递）时，严格从上一分段结束的 native_seq + 1 开始取段，
           绝不因 MV 场景切换或 23.976/29.97fps GOP 时长偏短（如 5.33s vs 6.0s）而跳过中间的 WebM Cluster！
           若当前原生段结束时间比 DASH 时间轴落后超过 0.75 个段长且下一原生段已就绪，自动将两个相邻 Cluster 合并投递，
           保证画面帧 100% 连续无冻结且音画时间轴零漂移；
        2. 记录每个 DASH 序号 (want_seq) 结束时的精确时间戳 seq_end_ms，供 60s 切入本地 Super-Chunk 时零误差无缝衔接。
        """
        media = state.get('segments', {}).get(target_itag) or {}
        metas = state.get('segment_meta', {}).get(target_itag) or {}
        served_map = state.setdefault('served_seq_map', {}).setdefault(target_itag, {})
        seq_end_map = state.setdefault('seq_end_ms', {}).setdefault(target_itag, {})
        if want_seq is not None and want_seq in served_map:
            prev_entry = served_map[want_seq]
            nseqs = prev_entry if isinstance(prev_entry, (list, tuple)) else (prev_entry,)
            if all(s in media for s in nseqs):
                return b''.join(media[s] for s in nseqs), nseqs[-1], metas.get(nseqs[-1])
        if want_seq is not None and (want_seq - 1) in served_map:
            prev_entry = served_map[want_seq - 1]
            last_nseq = prev_entry[-1] if isinstance(prev_entry, (list, tuple)) else int(prev_entry)
            next_nseq = last_nseq + 1
            if next_nseq not in media:
                return None, None, None
            m1 = metas.get(next_nseq) or {}
            end1_ms = int(m1.get('start_ms') or 0) + int(m1.get('duration_ms') or 0)
            target_end_ms = target_ms + dash_seg_ms
            if end1_ms < target_end_ms - int(dash_seg_ms * 0.75) and (next_nseq + 1) in media:
                n2 = next_nseq + 1
                m2 = metas.get(n2) or {}
                end2_ms = int(m2.get('start_ms') or 0) + int(m2.get('duration_ms') or 0)
                served_map[want_seq] = (next_nseq, n2)
                seq_end_map[want_seq] = end2_ms
                return media[next_nseq] + media[n2], n2, m2
            served_map[want_seq] = (next_nseq,)
            seq_end_map[want_seq] = end1_ms
            return media[next_nseq], next_nseq, m1
        used_native = set()
        if want_seq is not None:
            for v in served_map.values():
                if isinstance(v, (list, tuple)):
                    used_native.update(v)
                else:
                    used_native.add(v)
        candidates = []
        for native_seq, meta in metas.items():
            if native_seq in used_native:
                continue
            start = int(meta.get('start_ms') or 0)
            duration = int(meta.get('duration_ms') or 0)
            match_end = start + max(1, int(duration * 0.70))
            if start <= target_ms < match_end:
                candidates.append((start, native_seq, meta))
        if not candidates:
            tol = min(1800, max(400, dash_seg_ms // 3))
            for native_seq, meta in metas.items():
                if native_seq in used_native:
                    continue
                start = int(meta.get('start_ms') or 0)
                if abs(start - target_ms) <= tol:
                    candidates.append((start, native_seq, meta))
        if not candidates:
            return None, None, None
        _, native_seq, meta = min(candidates, key=lambda x: abs(x[0] - target_ms))
        if want_seq is not None:
            served_map[want_seq] = (native_seq,)
            seq_end_map[want_seq] = int(meta.get('start_ms') or 0) + int(meta.get('duration_ms') or 0)
        return media.get(native_seq), native_seq, meta

    @staticmethod
    def _sabr_cached_time_range(state, target_itag):
        metas = (state.get('segment_meta') or {}).get(target_itag) or {}
        if not metas:
            return None
        starts = [int(x.get('start_ms') or 0) for x in metas.values()]
        ends = [int(x.get('start_ms') or 0) + int(x.get('duration_ms') or 0) for x in metas.values()]
        return [min(starts), max(ends)]

    @classmethod
    def _sabr_should_seek_time(cls, state, target_itag, target_ms, dash_seg_ms, want_seq=None):
        # NOTE: 当播放器正在顺序请求下一段（want_seq == 1 或 want_seq - 1 已投递）时，绝不能触发 _sabr_seek！
        # 否则当 MV 视频 GOP 略短于 6.0s 时，cached[1] 累积微偏会误触发 _sabr_seek 清空缓冲并跳过视频段，引起画面卡死数秒而声音正常。
        if want_seq is not None:
            served_map = (state.get('served_seq_map') or {}).get(target_itag) or {}
            if want_seq == 1 or want_seq in served_map or (want_seq - 1) in served_map:
                return False
        cached = cls._sabr_cached_time_range(state, target_itag)
        if not cached:
            current = int(state.get('player_time_ms') or 0)
            return current > target_ms + dash_seg_ms or target_ms > current + (2 * dash_seg_ms)
        return target_ms < cached[0] or target_ms > cached[1] + dash_seg_ms

    @staticmethod
    def _sabr_is_retryable_transport_error(error):
        text = repr(error)
        return any(x in text for x in (
            'IncompleteRead', 'ProtocolError', 'ChunkedEncodingError',
            'RemoteDisconnected', 'Connection reset', 'Read timed out'))


    @staticmethod
    def _sabr_seek(state, seek_ms):
        # 重置到目标时间点：清空 buffered_ranges，让服务器从 seek_ms 重新发段。
        # 保留 state['initialized'] 与已下载分段 state['segments']，对齐 SabrStreamingAdapter 协议。
        state['player_time_ms'] = int(seek_ms)
        state['buffered'] = {}
        state['partial'] = {}

    def _sabr_pump_once(self, state, cfg, video_item, audio_item):
        video_itag = int((video_item or {}).get('itag') or 0) or None
        audio_itag = int((audio_item or {}).get('itag') or 0) or None
        initialized_ids = list((state.get('initialized') or {}).values())
        buffered_ranges = []
        for br in (state.get('buffered') or {}).values():
            packed = build_buffered_range(
                br.get('format_id'), br.get('start_ms') or 0, br.get('duration_ms') or 0,
                br.get('start_seq'), br.get('end_seq'))
            if packed:
                buffered_ranges.append(packed)
        raw_vh = int((video_item or {}).get('height') or 1080)
        sabr_vh = 1080 if raw_vh <= 1080 else raw_vh
        payload = build_vpabr_request(
            cfg, video_itag=video_itag, audio_itag=audio_itag,
            start_time_ms=int(state.get('player_time_ms') or 0),
            playback_cookie=state.get('playback_cookie'),
            initialized_format_ids=initialized_ids, buffered_ranges=buffered_ranges,
            audio_config=(audio_item or {}).get('_sabr_config'),
            video_height=sabr_vh)
        url = state.get('url') or cfg.get('server_abr_streaming_url') or (video_item or {}).get('url')
        headers = {
            'Content-Type': 'application/x-protobuf', 'Accept': 'application/vnd.yt-ump',
            'Accept-Encoding': 'identity', 'Connection': 'close',
        }
        headers.update((video_item or {}).get('headers') or (audio_item or {}).get('headers') or {})
        target_itags = set(x for x in (video_itag, audio_itag) if x)

        for redirect_attempt in range(4):
            rn = int(state.get('request_count') or 0) + 1
            self.trace('sabr segment request', {
                'rn': rn, 'video_itag': video_itag, 'audio_itag': audio_itag,
                'player_time_ms': int(state.get('player_time_ms') or 0),
                'initialized': len(initialized_ids), 'buffered': len(buffered_ranges),
                'host': urlparse(url or '').netloc,
            })
            response = requests.post(
                url, params={'rn': rn}, data=payload, headers=headers,
                proxies=dict(self.session.proxies or {}), stream=True, timeout=(6, 10))
            state['request_count'] = rn
            state['last_status'] = response.status_code
            state['pump_timed_out'] = False
            pump_deadline = time.time() + 10.0
            redirect_url = None
            completed = []
            part_count = 0
            part_ids = []
            try:
                if response.status_code != 200:
                    try:
                        error_body = (response.raw.read(512) or b'').decode('utf-8', 'replace')
                    except Exception:
                        error_body = ''
                    self.trace('sabr http error', {
                        'status': response.status_code,
                        'client': cfg.get('client_name'),
                        'host': urlparse(url or '').netloc,
                        'content_type': response.headers.get('content-type'),
                        'body': error_body[:300],
                    })
                    raise Exception(f'SABR HTTP {response.status_code} client={cfg.get("client_name")}')
                for part_id, part_data in iter_ump_parts(
                        response.raw, max_parts=int(self.config.get('sabr_max_parts') or 4096)):
                    part_count += 1
                    part_ids.append(part_id)
                    if part_id == UMP_MEDIA_HEADER:
                        header_id = _pb_get_int(part_data, 1)
                        itag = _pb_get_int(part_data, 3)
                        if header_id is None:
                            continue
                        format_id = _sabr_header_format_id(part_data, itag)
                        is_init = bool(_pb_get_int(part_data, 8))
                        seq = _pb_get_int(part_data, 9)
                        start_ms = _pb_get_int(part_data, 11) or 0
                        duration_ms = _pb_get_int(part_data, 12) or 0
                        if not start_ms and not duration_ms:
                            start_ms, duration_ms = _sabr_time_range_ms(part_data)
                        if seq is not None and not duration_ms and not is_init:
                            duration_ms = int(float(cfg.get('target_duration_sec') or (10 if itag == audio_itag else 6)) * 1000)
                            start_ms = int(max(0, int(seq) - 1) * duration_ms)
                        state['partial'][header_id] = {
                            'header_id': header_id, 'itag': itag, 'format_id': format_id,
                            'is_init': is_init, 'seq': seq, 'start_ms': start_ms,
                            'duration_ms': duration_ms, 'expected': _pb_get_int(part_data, 14),
                            'data': bytearray(),
                        }
                    elif part_id == UMP_MEDIA:
                        header_id, data_pos = _read_ump_varint_bytes(part_data)
                        partial = state['partial'].get(header_id)
                        if partial and partial.get('itag') in target_itags:
                            # The leading UMP varint is routing metadata, never media bytes.
                            partial['data'].extend(part_data[data_pos:])
                    elif part_id == UMP_MEDIA_END:
                        header_id, _ = _read_ump_varint_bytes(part_data)
                        partial = state['partial'].pop(header_id, None)
                        if not partial or partial.get('itag') not in target_itags:
                            continue
                        media = bytes(partial.get('data') or b'')
                        expected = partial.get('expected')
                        if expected is not None and int(expected) != len(media):
                            self.trace('sabr segment size mismatch', {
                                'header_id': header_id, 'itag': partial.get('itag'),
                                'seq': partial.get('seq'), 'expected': expected, 'actual': len(media),
                            })
                            continue
                        itag = partial.get('itag')
                        if partial.get('is_init'):
                            state['init_segments'][itag] = media
                            if partial.get('format_id'):
                                state['initialized'][str(itag)] = partial.get('format_id')
                        elif partial.get('seq') is not None:
                            seq = int(partial.get('seq'))
                            state['segments'].setdefault(itag, {})[seq] = media
                            state['segment_meta'].setdefault(itag, {})[seq] = {
                                'start_ms': int(partial.get('start_ms') or 0),
                                'duration_ms': int(partial.get('duration_ms') or 0),
                                'size': len(media),
                            }
                            order = state['segment_order'].setdefault(itag, [])
                            if seq in order:
                                order.remove(seq)
                            order.append(seq)
                            self._sabr_commit_buffered(state, partial)
                            # 严格限制电视盒子内存占用：视频缓存上限 16MB（最多保留 3 段），音频 4MB，彻底根除 192MB 引发的频繁 GC 卡死遥控器
                            self._sabr_trim_cache(
                                state, itag,
                                int(self.config.get(
                                    'sabr_video_cache_bytes' if itag == video_itag else 'sabr_audio_cache_bytes')
                                    or (16 * 1024 * 1024 if itag == video_itag else 4 * 1024 * 1024)))
                        completed.append({
                            'itag': itag, 'seq': partial.get('seq'),
                            'init': partial.get('is_init'), 'size': len(media),
                        })
                        if time.time() > pump_deadline and completed:
                            state['pump_timed_out'] = True
                            break
                    elif part_id == UMP_NEXT_REQUEST_POLICY:
                        cookie = _pb_get_bytes(part_data, 7)
                        if cookie:
                            state['playback_cookie'] = cookie
                    elif part_id == UMP_SABR_REDIRECT:
                        redirect_url = _pb_get_str(part_data, 1)
                        if redirect_url:
                            state['url'] = redirect_url
                    elif part_id == UMP_SABR_ERROR:
                        err_type = _pb_get_str(part_data, 1)
                        err_action = _pb_get_int(part_data, 2)
                        err_inner = _pb_get_bytes(part_data, 3) or b''
                        self.trace('sabr error part', {
                            'type': err_type, 'action': err_action,
                            'status_code': _pb_get_int(err_inner, 1),
                            'inner_type': _pb_get_int(err_inner, 4),
                            'size': len(part_data), 'hex': part_data[:64].hex(),
                        })
                    elif part_id == UMP_RELOAD_PLAYER_RESPONSE:
                        # 服务器在 SABR 会话到期（真机实测 ~70s 边界）时下发 RELOAD_PLAYER_RESPONSE(46)，
                        # 之后只回控制 part 不再发媒体段。必须重取播放上下文（fresh 会话/URL/pot）才能续流。
                        # 这里只置标志与 token，真正的重取在 sabr_get_segment 的 pump 循环里执行（那层持有 vid/cfg）。
                        token = _sabr_extract_reload_token(part_data)
                        state['reload_needed'] = True
                        if token:
                            state['reload_token'] = token
                        self.trace('sabr reload requested', {
                            'has_token': bool(token), 'player_time_ms': state.get('player_time_ms'),
                        })
                    else:
                        # 未解码的控制 part（如 STREAM_PROTECTION_STATUS=58、FORMAT_INIT 等）。
                        # 卡死时服务器只回这些控制 part 不给媒体，抓原文才知它要什么。
                        self.trace('sabr control part', {
                            'id': part_id, 'size': len(part_data), 'hex': part_data[:64].hex(),
                            'text1': _pb_get_str(part_data, 1), 'int1': _pb_get_int(part_data, 1),
                            'int2': _pb_get_int(part_data, 2),
                        })
            finally:
                response.close()
            self.trace('sabr segment response', {
                'rn': rn, 'status': state.get('last_status'), 'parts': part_count,
                'part_ids': part_ids, 'completed': completed[:16], 'redirect': bool(redirect_url),
                'player_time_ms': state.get('player_time_ms'),
            })
            if redirect_url and not completed:
                url = redirect_url
                continue
            return

    @staticmethod
    def _sabr_trim_cache(state, itag, max_bytes):
        """清理已消费的旧分段，但绝不提前驱逐尚未被播放器消费的未来分段（防止高码率 1080p MV 未播先删导致跳段）。"""
        media = state.get('segments', {}).get(itag) or {}
        metas = state.get('segment_meta', {}).get(itag) or {}
        order = state.get('segment_order', {}).get(itag) or []
        served_map = (state.get('served_seq_map') or {}).get(itag) or {}
        max_served_nseq = 0
        for v in served_map.values():
            if isinstance(v, (list, tuple)):
                if v:
                    max_served_nseq = max(max_served_nseq, max(int(x) for x in v))
            elif v is not None:
                max_served_nseq = max(max_served_nseq, int(v))
        total = sum(len(value) for value in media.values())
        while total > max_bytes and len(order) > 2:
            # 若队首分段尚未被播放器消费（order[0] > max_served_nseq），且未消费分段数 <= 6，停止驱逐以防跳段
            if order[0] > max_served_nseq and len(order) <= 6:
                break
            old_seq = order.pop(0)
            old_media = media.pop(old_seq, None)
            metas.pop(old_seq, None)
            if old_media is not None:
                total -= len(old_media)
        state.setdefault('segment_order', {})[itag] = order


    @staticmethod
    def _sabr_commit_buffered(state, segment):
        format_id = segment.get('format_id')
        if not format_id:
            return
        seq = segment.get('seq')
        start_ms = int(segment.get('start_ms') or 0)
        duration_ms = int(segment.get('duration_ms') or 0)
        key = str(segment.get('itag') or format_id)
        old = state['buffered'].get(key)
        if not old:
            old = state['buffered'][key] = {
                'format_id': format_id, 'start_ms': start_ms, 'duration_ms': duration_ms,
                'start_seq': seq, 'end_seq': seq,
            }
        else:
            old_end = int(old.get('start_ms') or 0) + int(old.get('duration_ms') or 0)
            end_ms = max(old_end, start_ms + duration_ms)
            old['start_ms'] = min(int(old.get('start_ms') or 0), start_ms)
            old['duration_ms'] = max(0, end_ms - int(old.get('start_ms') or 0))
            if seq is not None:
                old['start_seq'] = seq if old.get('start_seq') is None else min(old['start_seq'], seq)
                old['end_seq'] = seq if old.get('end_seq') is None else max(old['end_seq'], seq)
        state['player_time_ms'] = max(int(state.get('player_time_ms') or 0), start_ms + duration_ms)

class Spider(Spider):
    @staticmethod
    def _parse_relative_time_to_seconds(text):
        """将 YouTube 相对时间文本（简/繁/英）解析为距今秒数，越小代表越新。

        NOTE: 必须先匹配「数字 + 时间单位（X前 / X ago）」，再判断「正在直播 / 刚刚」。
        否则像「直播时间：3个月前」「曾于 1 年前直播」「首播：2周前」「Streamed 4 months ago」
        会因为包含「直播/首播/live」被误判为 0 秒（刚刚发布），导致几年前的旧直播回放排到第 1 位！
        """
        if not text:
            return 9999999999
        text = str(text).strip().lower()
        # 1. 优先提取明确的数字+时间单位（兼容简体、繁体、英文）
        m = re.search(
            r"(\d+)\s*(秒|分钟|分鐘|分|小时|小時|钟头|鐘頭|天|日|周|週|星期|礼拜|禮拜|个月|個月|月|年|"
            r"second|sec|minute|min|hour|hr|day|week|month|year)s?",
            text,
        )
        if m:
            val = int(m.group(1))
            unit = m.group(2)
            unit_map = {
                "秒": 1, "second": 1, "sec": 1,
                "分": 60, "分钟": 60, "分鐘": 60, "minute": 60, "min": 60,
                "小时": 3600, "小時": 3600, "钟头": 3600, "鐘頭": 3600, "hour": 3600, "hr": 3600,
                "天": 86400, "日": 86400, "day": 86400,
                "周": 7 * 86400, "週": 7 * 86400, "星期": 7 * 86400, "礼拜": 7 * 86400, "禮拜": 7 * 86400, "week": 7 * 86400,
                "个月": 30 * 86400, "個月": 30 * 86400, "月": 30 * 86400, "month": 30 * 86400,
                "年": 365 * 86400, "year": 365 * 86400,
            }
            return val * unit_map.get(unit, 86400)
        # 2. 特殊相对日期词
        if any(k in text for k in ("昨天", "昨日", "yesterday")):
            return 86400
        if "前天" in text:
            return 2 * 86400
        # 3. 不含过去时间词的实时状态（真正正在直播或刚刚发布）
        if any(k in text for k in ("正在直播", "直播中", "live now", "刚刚", "剛剛", "just now", "moments ago")):
            return 0
        # 4. 绝对年份兜底
        year_m = re.search(r"(20\d\d)", text)
        if year_m:
            return max(1, 2026 - int(year_m.group(1))) * 365 * 86400
        return 8888888888

    CHANNEL_EXACT_MAP = {
        'LT視界': '@ltshijie',
        'LT视界': '@ltshijie',
        '王志安': '@wangzhian',
        '柴静 Chai Jing': '@chaijing2023',
        '柴静': '@chaijing2023',
        'Chai Jing': '@chaijing2023',
        '汀见': '@dlczxxs',
        '硅谷101': '@TheValley101',
        'BBC News 中文': '@bbcnewschinese',
        'BBC': '@bbcnewschinese',
        '李肅Hi5第一頻道': '@Hi5Hi5',
        '李肃Hi5第一频道': '@Hi5Hi5',
        '崔永元': '@cuiyongyuan_1963',
        '老高與小茉': '@laogao',
        '老高与小茉': '@laogao',
        '自说自话的总裁': '@STBoss',
        '老肉雜談': '@%E8%80%81%E8%82%89%E9%9B%9C%E8%AB%87',
        '老肉杂谈': '@%E8%80%81%E8%82%89%E9%9B%9C%E8%AB%87',
        '滇西小哥': '@dianxixiaoge',
        '老饭骨': '@LaoFanGu',
        '小高姐': '@MagicIngredients',
        'Mr Beast': '@MrBeast',
        'Mark Rober': '@MarkRober',
        '不良林': '@bulianglin',
        '悟空的日常': '@wukongdaily',
        '李永乐老师': 'channel/UCvNxfitQbWkmLuCd44UfrYQ',
        '李永樂老師': 'channel/UCvNxfitQbWkmLuCd44UfrYQ',
        '涌哥侃侃': '@ygkkk',
    }

    # 预设频道的官方 UC browseId 映射：直接请求 Innertube /youtubei/v1/browse JSON 接口（~0.6s 返回），
    # 彻底绕过网页端 1.8MB HTML 在代理节点下偶发空 Grid / 验证码导致回退到无序搜索的问题！
    CHANNEL_BROWSE_ID_MAP = {
        'LT視界': 'UCOsQMj_MZkQ5N7f1OOMB87Q',
        'LT视界': 'UCOsQMj_MZkQ5N7f1OOMB87Q',
        '王志安': 'UCBKDRq35-L8xev4O7ZqBeLg',
        '柴静 Chai Jing': 'UCjuNibFJ21MiSNpu8LZyV4w',
        '柴静': 'UCjuNibFJ21MiSNpu8LZyV4w',
        'Chai Jing': 'UCjuNibFJ21MiSNpu8LZyV4w',
        '汀见': 'UCv8djBlOdCZWZ-7Nal-3pJQ',
        '硅谷101': 'UCKV2yWPB3wn0RTZh3cTD8YA',
        'BBC News 中文': 'UCb3TZ4SD_Ys3j4z0-8o6auA',
        'BBC': 'UCb3TZ4SD_Ys3j4z0-8o6auA',
        '李肅Hi5第一頻道': 'UCvpX0E9dK-40zwYShv186oA',
        '李肃Hi5第一频道': 'UCvpX0E9dK-40zwYShv186oA',
        '崔永元': 'UCAq_xQV8pJ2Q_KOszzaYPBg',
        '老高與小茉': 'UCMUnInmOkrWN4gof9KlhNmQ',
        '老高与小茉': 'UCMUnInmOkrWN4gof9KlhNmQ',
        '自说自话的总裁': 'UCgo_-fjJxnLwwwq5dSY72rg',
        '老肉雜談': 'UC5DGiN7-nlPno2kjHUdcdCg',
        '老肉杂谈': 'UC5DGiN7-nlPno2kjHUdcdCg',
        '滇西小哥': 'UCQG_fzADCunBTV1KwjkfAQQ',
        '老饭骨': 'UCBJmYv3Vf_tKcQr5_qmayXg',
        '小高姐': 'UCCKlp1JI9Yg3-cUjKPdD3mw',
        'Mr Beast': 'UCX6OQ3DkcsbYNE6H8uQQuVA',
        'Mark Rober': 'UCY1kMZp36IQSyNx_9h4mpCg',
        '不良林': 'UCbCCUH8S3yhlm7__rhxR2QQ',
        '悟空的日常': 'UCii04BCvYIdQvshrdNDAcww',
        '李永乐老师': 'UCvNxfitQbWkmLuCd44UfrYQ',
        '李永樂老師': 'UCvNxfitQbWkmLuCd44UfrYQ',
        '涌哥侃侃': 'UCxukdnZiXnTFvjF5B5dvJ5w',
    }

    CHANNEL_CARD_AVATARS = {
        'LT視界': 'https://yt3.googleusercontent.com/omU8wiHJ3WFpKNML7sj5lFG9P3qzq_2CkWX_pMsYyxzT0nqjjBLmExvdCdU-DGzp96KKi3mAU5M=s900-c-k-c0x00ffffff-no-rj',
        '王志安': 'https://yt3.googleusercontent.com/Oy7RT7_C7QzpVxHee_8q3nHeK7qu01U9tosD-l4mFIQdnz-SuiRvv0TjV2g0IIbXBkwBMDvxrA=s900-c-k-c0x00ffffff-no-rj',
        '柴静 Chai Jing': 'https://yt3.googleusercontent.com/g0cH597imPPxPZ_Op4BOKyufZAtUSJQ-K_5fmLBb8aFS2eV9CP6bEIL4KxsFMPEgDp69pnCeFw=s900-c-k-c0x00ffffff-no-rj',
        '汀见': 'https://yt3.googleusercontent.com/LtFTpVovlDPRQVO9a-fD8AAtadYqib3Gg7buqZ9AA2Eb0Oebu-aS4er23ugnYPPftGE_b-U1LA=s900-c-k-c0x00ffffff-no-rj',
        '硅谷101': 'https://yt3.googleusercontent.com/Vqg_8nFFDNbk_IvXWE7ngTBTTx3h1StP7nPtRQv77UVvtXfHurANruNVH3MA-Ms-OC-6Ge0L=s900-c-k-c0x00ffffff-no-rj',
        'BBC News 中文': 'https://yt3.googleusercontent.com/zfLDpMaOaNOsNdaIESj8ekuIjlX6fkpXsytTufvpy_y3U9OzBA9MQ25p5XYXMvN9-Y-KhMvCMKs=s900-c-k-c0x00ffffff-no-rj',
        '李肅Hi5第一頻道': 'https://yt3.googleusercontent.com/wlqvi8Kd4e0_NgbnY-8srZFwW7ZSGLrnT50vKLMNpEwtOeE-3JcS3DLyfxqaRkGgjdSVsug9DQ=s900-c-k-c0x00ffffff-no-rj',
        '崔永元': 'https://yt3.googleusercontent.com/ytc/AIdro_law1kk7FdxysNj40PraV4q7t9qrrzLdcsw5nLv6aEphDE=s900-c-k-c0x00ffffff-no-rj',
        '老高與小茉': 'https://yt3.googleusercontent.com/WkqPeeZSOxzUz3eNJ-ztvIkHXqNvIqDy6_cGiIZIQm2PGDNnGW6DfIIUfQ8_CsqKoiAT2oz6FQ=s900-c-k-c0x00ffffff-no-rj',
        '老高与小茉': 'https://yt3.googleusercontent.com/WkqPeeZSOxzUz3eNJ-ztvIkHXqNvIqDy6_cGiIZIQm2PGDNnGW6DfIIUfQ8_CsqKoiAT2oz6FQ=s900-c-k-c0x00ffffff-no-rj',
        '自说自话的总裁': 'https://yt3.googleusercontent.com/ytc/AIdro_mZjrrtTv-US7XX4HNmQIw1TIkNtcUmP47PLqo90fKQOzU=s900-c-k-c0x00ffffff-no-rj',
        '老肉雜談': 'https://yt3.googleusercontent.com/ytc/AIdro_mWwce0FReAeILAiRmy_9epkhjKhYuHLYsLn4OeW_6MPA=s900-c-k-c0x00ffffff-no-rj',
        '老肉杂谈': 'https://yt3.googleusercontent.com/ytc/AIdro_mWwce0FReAeILAiRmy_9epkhjKhYuHLYsLn4OeW_6MPA=s900-c-k-c0x00ffffff-no-rj',
        '滇西小哥': 'https://yt3.googleusercontent.com/nMI05aTIRG7vvAPSmTpzN9Mt6WA5mHqJe8TfoVyrfK7BZGdpWXxITMwSiNc7BV3Ocfip3qsp7Q=s900-c-k-c0x00ffffff-no-rj',
        '老饭骨': 'https://yt3.googleusercontent.com/kjyptydd_rCoJfkr1ZZnwMUIZ5vItq-joWaL4ctElwK5aOY6_Awb3vwFiOgMqv6wzETDvIlQvw=s900-c-k-c0x00ffffff-no-rj',
        '小高姐': 'https://yt3.googleusercontent.com/ytc/AIdro_ntv3-ovHxkQ5k3BhUDPcWNL2w6Exzif_X-NKISrRN1ug=s900-c-k-c0x00ffffff-no-rj',
        'Mr Beast': 'https://yt3.googleusercontent.com/nxYrc_1_2f77DoBadyxMTmv7ZpRZapHR5jbuYe7PlPd5cIRJxtNNEYyOC0ZsxaDyJJzXrnJiuDE=s900-c-k-c0x00ffffff-no-rj',
        'Mark Rober': 'https://yt3.googleusercontent.com/ytc/AIdro_ksXY2REjZ6gYKSgnWT5jC_zT9mX900vyFtVinR8KbHww=s900-c-k-c0x00ffffff-no-rj',
        '不良林': 'https://yt3.googleusercontent.com/ytc/AIdro_ky5eU9_6HEcfjSLn5D7YMgqnDyLQVsbpxOzYrLL86J5g=s900-c-k-c0x00ffffff-no-rj',
        '悟空的日常': 'https://yt3.googleusercontent.com/ytc/AIdro_mdbX2lvPXPwrIwdW-1PIM59JnJ3zUvOoclqrKEpT3kCA=s900-c-k-c0x00ffffff-no-rj',
    }

    _MEMBERS_ONLY_MARKERS = (
        'BADGE_MEMBERS_ONLY',
        'BADGE_STYLE_TYPE_MEMBERS_ONLY',
        'THUMBNAIL_BADGE_STYLE_TYPE_MEMBERS_ONLY',
        'SPONSORSHIP_STAR',
        'sponsorOnlyBadge',
        'upcomingEventData',
        'THUMBNAIL_OVERLAY_TIME_STATUS_RENDERER_STYLE_UPCOMING',
        'BADGE_STYLE_TYPE_UPCOMING',
        '会员专享',
        '會員專享',
        '会员抢先',
        '會員搶先',
        '会员专属',
        '會員專屬',
        '仅限会员',
        '僅限會員',
        '频道会员',
        '頻道會員',
        'Members only',
        'Members-only',
        'Members first',
        '即将首播',
        '即將首播',
    )

    @classmethod
    def _is_members_only_node(cls, obj):
        if not obj:
            return False
        try:
            raw = json.dumps(obj, ensure_ascii=False)
            return any(m in raw for m in cls._MEMBERS_ONLY_MARKERS)
        except Exception:
            raw = str(obj)
            return any(m in raw for m in cls._MEMBERS_ONLY_MARKERS)

    def _parse_channel_browse_data(self, data):
        """从 Innertube /youtubei/v1/browse 或频道页 ytInitialData 中提取视频列表并严格按发布时间倒序排列。"""
        tabs = (data or {}).get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [])
        target_grid = None
        for t in tabs:
            tab_r = t.get('tabRenderer', {})
            if tab_r.get('selected') and tab_r.get('content', {}).get('richGridRenderer'):
                target_grid = tab_r.get('content', {}).get('richGridRenderer', {})
                break
        if not target_grid:
            for t in tabs:
                tab_r = t.get('tabRenderer', {})
                if tab_r.get('title') in ('视频', 'Videos', '影片') and tab_r.get('content', {}).get('richGridRenderer'):
                    target_grid = tab_r.get('content', {}).get('richGridRenderer', {})
                    break
        if not target_grid:
            return []

        contents = target_grid.get('contents', [])
        results = []
        for orig_idx, item in enumerate(contents):
            rir = item.get('richItemRenderer', {})
            r_content = rir.get('content', {})
            lvm = r_content.get('lockupViewModel')
            vr = r_content.get('videoRenderer')
            vid = None
            title = None
            remarks = ''
            pub_sec = 8888888888
            if lvm:
                if self._is_members_only_node(lvm):
                    continue
                vid = lvm.get('contentId')
                m_vm = lvm.get('metadata', {}).get('lockupMetadataViewModel', {})
                title = m_vm.get('title', {}).get('content')
                meta_rows = m_vm.get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
                row_texts = []
                for row in meta_rows:
                    for part in row.get('metadataParts', []):
                        txt = (part.get('text') or {}).get('content')
                        if txt:
                            row_texts.append(txt)
                remarks = ' · '.join(row_texts)
                for rt in reversed(row_texts):
                    cand_sec = self._parse_relative_time_to_seconds(rt)
                    if cand_sec < 8888888888:
                        pub_sec = cand_sec
                        break
            elif vr:
                if self._is_members_only_node(vr):
                    continue
                vid = vr.get('videoId')
                t_obj = vr.get('title', {})
                title = t_obj.get('simpleText') or ''.join([x.get('text', '') for x in (t_obj.get('runs') or [])])
                pub_obj = vr.get('publishedTimeText') or {}
                pub_text = pub_obj.get('simpleText') or ''.join([x.get('text', '') for x in (pub_obj.get('runs') or [])])
                view_obj = vr.get('shortViewCountText') or vr.get('viewCountText') or {}
                view_text = view_obj.get('simpleText') or ''.join([x.get('text', '') for x in (view_obj.get('runs') or [])])
                remarks = f'{pub_text} · {view_text}'.strip(' ·')
                pub_sec = self._parse_relative_time_to_seconds(pub_text or remarks)

            if vid and title:
                results.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={vid}&quality=hqdefault',
                    'vod_remarks': remarks,
                    'vod_pub_sec': pub_sec,
                    '_orig_idx': orig_idx,
                })
        if results:
            # 稳定排序：严格按距今秒数（vod_pub_sec）升序排列（越小代表越新）；
            # 若距今秒数相同（例如同为「2天前」），保持 YouTube 官方原始先后顺序 (_orig_idx)
            results.sort(key=lambda x: (x.get('vod_pub_sec', 9999999999), x.get('_orig_idx', 0)))
            for i, r_item in enumerate(results):
                r_item.pop('_orig_idx', None)
                r_rem = r_item.get('vod_remarks') or ''
                if i == 0:
                    tag = '【最新发布】'
                elif i == 1:
                    tag = '【次新】'
                else:
                    tag = f'【第{i+1}新】'
                if tag not in r_rem:
                    r_item['vod_remarks'] = f'{tag}{r_rem}'
        return results

    def _fetch_channel_videos_exact(self, ch_name):
        clean = re.sub(r'@[a-zA-Z0-9_-]+', '', str(ch_name or '')).replace('CH__', '').strip()
        cache_key = f'yt_ch_exact_v2_{clean}'
        cached_entry = self.getCache(cache_key)
        if isinstance(cached_entry, dict) and cached_entry.get('expires', 0) > time.time() and cached_entry.get('videos'):
            return copy.deepcopy(cached_entry['videos'])

        browse_id = None
        target = None
        for k, v in self.CHANNEL_BROWSE_ID_MAP.items():
            if k == clean or k in clean or clean in k:
                browse_id = v
                break
        for k, v in self.CHANNEL_EXACT_MAP.items():
            if k == clean or k in clean or clean in k:
                target = v
                break
        if target and target.startswith('channel/UC'):
            browse_id = target.split('/', 1)[1]

        # 若未在预设映射中，通过 Innertube search API 极速定位该频道主的 browseId (UC...)
        if not browse_id:
            try:
                search_url = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
                s_payload = {
                    "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240310.01.00", "hl": "zh-CN", "gl": "US"}},
                    "query": clean,
                    "params": "EgIQAg%3D%3D",
                }
                s_headers = self.header.copy()
                s_headers.update({"Content-Type": "application/json", "Accept-Encoding": "gzip, deflate", "Origin": "https://www.youtube.com"})
                r_s = self.session.post(search_url, json=s_payload, headers=s_headers, timeout=8)
                if r_s.status_code == 200:
                    s_txt = r_s.text
                    m_cid = re.search(r'"browseId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"', s_txt)
                    m_handle = re.search(r'"canonicalBaseUrl"\s*:\s*"(/@[^"]+)"', s_txt)
                    if m_cid:
                        browse_id = m_cid.group(1)
                        if not target:
                            target = f'channel/{browse_id}'
                    elif m_handle and not target:
                        target = m_handle.group(1).lstrip('/')
            except Exception as ex:
                debug_log('channel lookup error', repr(ex))

        # 1. 首选方案：使用官方 Innertube /youtubei/v1/browse JSON API（params="EgZ2aWRlb3PyBgQKAjoA" 对应「视频 -> 最新发布」Tab）
        #    纯 JSON 仅 ~50KB，耗时 ~0.6s，100% 免疫网页端 HTML 空 Grid 与验证码拦截！
        if browse_id:
            browse_url = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"
            b_payload = {
                "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240310.01.00", "hl": "zh-CN", "gl": "US"}},
                "browseId": browse_id,
                "params": "EgZ2aWRlb3PyBgQKAjoA",
            }
            b_headers = self.header.copy()
            b_headers.update({
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate",
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": "2.20240310.01.00",
            })
            for attempt in range(2):
                try:
                    r_b = self.session.post(browse_url, json=b_payload, headers=b_headers, timeout=10)
                    if r_b.status_code == 200:
                        b_data = r_b.json()
                        results = self._parse_channel_browse_data(b_data)
                        if results:
                            self.setCache(cache_key, {'videos': results, 'expires': time.time() + 300})
                            debug_log('fetched channel videos via innertube browse api', {
                                'channel': ch_name, 'browse_id': browse_id, 'count': len(results),
                                'top3': [(x.get('vod_id'), x.get('vod_remarks')) for x in results[:3]],
                            })
                            return copy.deepcopy(results)
                except Exception as be:
                    debug_log('innertube browse api retry', {'channel': ch_name, 'attempt': attempt + 1, 'error': repr(be)})
                    time.sleep(0.2)

        # 2. 兜底方案：若无 browse_id，回退流式读取网页端 /videos 的 ytInitialData
        if not target:
            if re.search(r'[\u4e00-\u9fff]', clean):
                return []
            target = f'@{clean}'

        videos_url = f'https://www.youtube.com/{target}/videos'
        fetch_headers = self.header.copy()
        fetch_headers['Accept-Encoding'] = 'gzip, deflate'
        fetch_headers['Accept-Language'] = 'zh-CN,zh;q=0.9'

        for attempt in range(2):
            try:
                r = self.session.get(videos_url, headers=fetch_headers, stream=True, timeout=10)
                buf = []
                total_len = 0
                try:
                    for chunk in r.iter_content(chunk_size=32768, decode_unicode=True):
                        if not chunk:
                            continue
                        if isinstance(chunk, bytes):
                            chunk = chunk.decode('utf-8', 'replace')
                        buf.append(chunk)
                        total_len += len(chunk)
                        if total_len > 65536 and ';</script>' in chunk and 'var ytInitialData = ' in ''.join(buf):
                            joined_check = ''.join(buf)
                            i0 = joined_check.find('var ytInitialData = ')
                            if i0 != -1 and ';</script>' in joined_check[i0:]:
                                break
                        if total_len > 2500000:
                            break
                except Exception as stream_err:
                    debug_log('channel stream partial read', {'channel': ch_name, 'len': total_len, 'err': repr(stream_err)})
                finally:
                    try:
                        r.close()
                    except Exception:
                        pass
                text = ''.join(buf)
                idx = text.find('var ytInitialData = ')
                if idx == -1:
                    continue
                sub = text[idx + len('var ytInitialData = '):]
                end_idx = sub.find(';</script>')
                if end_idx == -1:
                    continue
                data = json.loads(sub[:end_idx])
                results = self._parse_channel_browse_data(data)
                if results:
                    self.setCache(cache_key, {'videos': results, 'expires': time.time() + 300})
                    debug_log('fetched strict official channel videos sorted (html fallback)', {
                        'channel': ch_name, 'count': len(results),
                        'top3': [(x.get('vod_id'), x.get('vod_remarks')) for x in results[:3]],
                    })
                    return copy.deepcopy(results)
            except Exception as e:
                debug_log('fetch channel videos exact retry', {'channel': ch_name, 'attempt': attempt + 1, 'error': repr(e)})
                time.sleep(0.2)
        return []

    @staticmethod
    def _clean_channel_name(raw_name):
        s = str(raw_name or '').replace('CH__', '').strip()
        s = re.sub(r'@[a-zA-Z0-9_-]+', '', s).strip()
        s = re.sub(r'[\(（].*?[\)）]', '', s).strip()
        s = s.replace('频道：', '').replace('频道:', '').strip()
        return s if s else str(raw_name or '').replace('CH__', '').strip()

    @staticmethod
    def _extract_channel_query(channel_str):
        return Spider._clean_channel_name(channel_str)

    _local_cache = {}

    def getCache(self, key):
        try:
            val = self._local_cache.get(key)
            if val is not None:
                return val
            if hasattr(super(), 'getCache'):
                return super().getCache(key)
        except Exception:
            pass
        return None

    def setCache(self, key, value):
        try:
            self._local_cache[key] = value
            if hasattr(super(), 'setCache'):
                super().setCache(key, value)
        except Exception:
            pass
    def _clean_json_text(self, text):
        if not text:
            return ''
        text = re.sub(r'/\*[\s\S]*?\*/', '', text)
        lines = []
        for line in text.split('\n'):
            line_str = line.strip()
            if line_str.startswith('//'):
                continue
            idx = line.find('//')
            if idx != -1:
                prefix = line[:idx]
                if prefix.count('"') % 2 == 0 and prefix.count("'") % 2 == 0:
                    line = prefix
            lines.append(line)
        cleaned = '\n'.join(lines)
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        return cleaned.strip()

    def _load_custom_json(self, json_url):
        raw_path = str(json_url or '').strip()
        candidates = []
        if raw_path:
            if raw_path.startswith('clan://localhost/'):
                rel_p = raw_path.replace('clan://localhost/', '')
                candidates.extend([
                    rel_p,
                    os.path.join('/sdcard/TVBox', rel_p),
                    os.path.join('/sdcard/Download', rel_p),
                    os.path.join('/storage/emulated/0/TVBox', rel_p),
                ])
            else:
                candidates.append(raw_path)
        candidates.extend([
            'C:/Users/LYQ/Desktop/0ytb.json',
            'C:/Users/LYQ/Desktop/cua-main/a/lib/0ytb.json',
            '0ytb.json',
        ])
        for p in candidates:
            if not p:
                continue
            if p.startswith(('http://', 'https://')):
                try:
                    r = self.session.get(p, timeout=5)
                    if r.status_code == 200:
                        data = json.loads(self._clean_json_text(r.text))
                        if data and isinstance(data, dict):
                            debug_log('load remote json success', {'url': p})
                            return data
                except Exception as e:
                    debug_log('load remote json error', {'url': p, 'error': repr(e)})
            elif os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.loads(self._clean_json_text(f.read()))
                        if data and isinstance(data, dict):
                            debug_log('load local json success', {'path': p})
                            return data
                except Exception as e:
                    debug_log('load local json error', {'path': p, 'error': repr(e)})
        return None

    def _parse_channel_names(self, val_str):
        if not val_str:
            return []
        s = val_str.strip()
        if s.startswith('LIST:'):
            s = s[5:]
        items = [x.strip() for x in s.split(',') if x.strip()]
        return items

    def _get_channel_list(self):
        if hasattr(self, 'custom_filters') and self.custom_filters and 'channel' in self.custom_filters:
            ch_filter = self.custom_filters['channel']
            if isinstance(ch_filter, list):
                for item in ch_filter:
                    vals = item.get('value') or []
                    for v in vals:
                        if v.get('n') == '全部' and v.get('v', '').startswith('LIST:'):
                            names = self._parse_channel_names(v.get('v'))
                            if names:
                                return names
                        if v.get('n') and v.get('n') != '全部':
                            names = [x.get('n') for x in vals if x.get('n') and x.get('n') != '全部']
                            if names:
                                return names
        return [
            'LT視界', '王志安', '柴静 Chai Jing', '汀见', '硅谷101', 'BBC News 中文',
            '李肅Hi5第一頻道', '崔永元', '老高與小茉', '自说自话的总裁', '老肉雜談',
            '滇西小哥', '老饭骨', '小高姐', 'Mr Beast', 'Mark Rober', '不良林', '悟空的日常'
        ]

    _ch_state_lock = threading.RLock()
    _ch_bg_checking = set()
    _cmt_fetch_locks = {}

    @staticmethod
    def _channel_state_file_path():
        for d in ('/sdcard/Download', '/storage/emulated/0/Download', '/data/data/com.fongmi.android.tv/cache', os.path.dirname(os.path.abspath(__file__))):
            try:
                if d and os.path.isdir(d) and os.access(d, os.W_OK):
                    return os.path.join(d, 'yt_channel_update_state.json')
            except Exception:
                continue
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yt_channel_update_state.json')

    def _load_channel_update_state(self):
        with self._ch_state_lock:
            cached = getattr(self, '_ch_state_mem', None)
            if isinstance(cached, dict):
                return cached
            path = self._channel_state_file_path()
            data = {}
            try:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
            except Exception as e:
                debug_log('load channel update state error', repr(e))
            self._ch_state_mem = data
            return data

    def _save_channel_update_state(self, state):
        with self._ch_state_lock:
            self._ch_state_mem = state
            path = self._channel_state_file_path()
            try:
                tmp_path = path + '.tmp'
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, path)
            except Exception as e:
                debug_log('save channel update state error', repr(e))

    @staticmethod
    def _format_age_short(age_sec):
        if age_sec is None or age_sec < 0:
            return '刚刚'
        if age_sec < 3600:
            return f'{max(1, int(age_sec // 60))}分钟前'
        if age_sec < 86400:
            return f'{max(1, int(age_sec // 3600))}小时前'
        if age_sec < 86400 * 30:
            return f'{max(1, int(age_sec // 86400))}天前'
        return '近期'

    def _check_single_channel_rss(self, ch_name, force=False):
        clean = self._clean_channel_name(ch_name)
        state = self._load_channel_update_state()
        now = time.time()
        entry = state.get(clean) or {}
        if not force and entry.get('checked_at') and (now - float(entry.get('checked_at') or 0) < 900) and entry.get('latest_vid'):
            return entry

        browse_id = None
        for k, v in self.CHANNEL_BROWSE_ID_MAP.items():
            if k == clean or k in clean or clean in k:
                browse_id = v
                break
        if not browse_id:
            for k, v in self.CHANNEL_EXACT_MAP.items():
                if (k == clean or k in clean or clean in k) and str(v).startswith('channel/UC'):
                    browse_id = str(v).split('/', 1)[1]
                    break

        latest_vid = ''
        latest_title = ''
        age_sec = 999999999
        pub_text = ''

        if browse_id:
            rss_url = f'https://www.youtube.com/feeds/videos.xml?channel_id={browse_id}'
            try:
                r = self.session.get(rss_url, headers=self.header, timeout=5)
                if r.status_code == 200 and r.text:
                    entries = re.findall(r'<entry>([\s\S]*?)</entry>', r.text)
                    for e_xml in entries[:5]:
                        m_vid = re.search(r'<yt:videoId>([^<]+)</yt:videoId>', e_xml)
                        m_title = re.search(r'<title>([^<]+)</title>', e_xml)
                        m_pub = re.search(r'<published>([^<]+)</published>', e_xml)
                        m_views = re.search(r'views="([0-9]+)"', e_xml)
                        views = int(m_views.group(1)) if m_views else 1
                        if views <= 0 or any(m in e_xml for m in self._MEMBERS_ONLY_MARKERS):
                            continue
                        if m_vid and m_pub:
                            latest_vid = m_vid.group(1).strip()
                            latest_title = html.unescape(m_title.group(1).strip()) if m_title else ''
                            pub_iso = m_pub.group(1).strip()
                            try:
                                dt = datetime.fromisoformat(pub_iso)
                                age_sec = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
                                pub_text = self._format_age_short(age_sec)
                            except Exception:
                                age_sec = 86400
                                pub_text = '近期更新'
                            break
            except Exception as e:
                debug_log('check channel rss error', {'channel': clean, 'error': repr(e)})

        if not latest_vid:
            cached_exact = self.getCache(f'yt_ch_exact_v2_{clean}')
            if isinstance(cached_exact, dict) and cached_exact.get('videos'):
                v0 = cached_exact['videos'][0]
                latest_vid = v0.get('vod_id') or ''
                latest_title = v0.get('vod_name') or ''
                age_sec = int(v0.get('vod_pub_sec') or 999999999)
                pub_text = self._format_age_short(age_sec) if age_sec < 86400 * 365 else ''

        if latest_vid:
            with self._ch_state_lock:
                state = self._load_channel_update_state()
                cur = state.get(clean) or {}
                cur.update({
                    'latest_vid': latest_vid,
                    'latest_title': latest_title[:60],
                    'age_sec': age_sec,
                    'pub_text': pub_text,
                    'checked_at': now,
                })
                state[clean] = cur
                self._save_channel_update_state(state)
                return cur
        return entry

    def _is_channel_has_update(self, ch_name, entry=None):
        clean = self._clean_channel_name(ch_name)
        if entry is None:
            state = self._load_channel_update_state()
            entry = state.get(clean) or {}
        latest_vid = entry.get('latest_vid') or ''
        if not latest_vid:
            return False, ''
        seen_vid = entry.get('seen_vid') or ''
        age_sec = int(entry.get('age_sec') if entry.get('age_sec') is not None else 999999999)
        pub_text = entry.get('pub_text') or self._format_age_short(age_sec)
        try:
            fresh_hours = int(self.extendDict.get('ch_update_hours') or 72)
        except Exception:
            fresh_hours = 72
        fresh_window_sec = max(6, fresh_hours) * 3600
        if seen_vid and seen_vid == latest_vid:
            return False, pub_text
        if seen_vid and seen_vid != latest_vid:
            return True, pub_text
        if age_sec <= fresh_window_sec:
            return True, pub_text
        return False, pub_text

    def _mark_channel_seen(self, ch_name, videos=None):
        clean = self._clean_channel_name(ch_name)
        with self._ch_state_lock:
            state = self._load_channel_update_state()
            cur = state.get(clean) or {}
            latest_vid = cur.get('latest_vid') or ''
            if videos and isinstance(videos, list) and len(videos) > 0:
                v0 = videos[0]
                if v0.get('vod_id'):
                    latest_vid = v0['vod_id']
                    cur['latest_vid'] = latest_vid
                    cur['latest_title'] = (v0.get('vod_name') or '')[:60]
                    pub_s = int(v0.get('vod_pub_sec') or 999999999)
                    if pub_s < 86400 * 365:
                        cur['age_sec'] = pub_s
                        cur['pub_text'] = self._format_age_short(pub_s)
                    cur['checked_at'] = time.time()
            if latest_vid:
                cur['seen_vid'] = latest_vid
                cur['seen_at'] = time.time()
                state[clean] = cur
                self._save_channel_update_state(state)

    def _trigger_bg_channels_check(self, channel_names):
        names_to_check = []
        now = time.time()
        state = self._load_channel_update_state()
        for name in (channel_names or []):
            clean = self._clean_channel_name(name)
            if clean in self._ch_bg_checking:
                continue
            entry = state.get(clean) or {}
            if not entry.get('latest_vid') or (now - float(entry.get('checked_at') or 0) >= 900):
                names_to_check.append(clean)
        if not names_to_check:
            return

        def _worker():
            for clean_n in names_to_check:
                if clean_n in self._ch_bg_checking:
                    continue
                self._ch_bg_checking.add(clean_n)
                try:
                    self._check_single_channel_rss(clean_n, force=False)
                except Exception:
                    pass
                finally:
                    self._ch_bg_checking.discard(clean_n)

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            pass

    def _draw_update_badge_on_image(self, img_bytes, pub_text='', latest_title=''):
        """使用 Android 原生 Skia Canvas (Chaquopy java.jclass) 在频道头像图片上直接绘制醒目的『🔥有更新』角标与更新时间横幅。"""
        if not img_bytes:
            return None, None
        badge_label = f'🔥有更新 · {pub_text}' if pub_text else '🔥有新更新'
        try:
            from java import jclass
            BitmapFactory = jclass('android.graphics.BitmapFactory')
            Bitmap = jclass('android.graphics.Bitmap')
            BitmapConfig = jclass('android.graphics.Bitmap$Config')
            Canvas = jclass('android.graphics.Canvas')
            Paint = jclass('android.graphics.Paint')
            PaintStyle = jclass('android.graphics.Paint$Style')
            PaintAlign = jclass('android.graphics.Paint$Align')
            RectF = jclass('android.graphics.RectF')
            Typeface = jclass('android.graphics.Typeface')
            ByteArrayOutputStream = jclass('java.io.ByteArrayOutputStream')
            CompressFormat = jclass('android.graphics.Bitmap$CompressFormat')

            src_bmp = BitmapFactory.decodeByteArray(img_bytes, 0, len(img_bytes))
            if src_bmp is None:
                return None, None
            w = int(src_bmp.getWidth())
            h = int(src_bmp.getHeight())
            if w <= 0 or h <= 0:
                return None, None

            mutable_bmp = src_bmp.copy(BitmapConfig.ARGB_8888, True)
            if mutable_bmp is None:
                return None, None
            canvas = Canvas(mutable_bmp)

            border_w = max(6.0, w * 0.022)
            border_paint = Paint(Paint.ANTI_ALIAS_FLAG)
            border_paint.setStyle(PaintStyle.STROKE)
            border_paint.setStrokeWidth(float(border_w))
            border_paint.setColor(-47802)  # 0xFFFF4546
            half_b = float(border_w / 2.0)
            canvas.drawRect(half_b, half_b, float(w) - half_b, float(h) - half_b, border_paint)

            text_size = max(22.0, w * 0.072)
            text_paint = Paint(Paint.ANTI_ALIAS_FLAG)
            text_paint.setColor(-1)
            text_paint.setTextSize(float(text_size))
            text_paint.setTypeface(Typeface.DEFAULT_BOLD)
            text_paint.setTextAlign(PaintAlign.CENTER)

            text_w = float(text_paint.measureText(badge_label))
            pad_x = max(16.0, w * 0.045)
            pad_y = max(10.0, h * 0.028)
            pill_w = min(float(w) * 0.92, text_w + pad_x * 2.0)
            pill_h = text_size + pad_y * 2.0
            margin = max(12.0, w * 0.035)
            left = float(w) - pill_w - margin
            top = margin
            right = float(w) - margin
            bottom = top + pill_h
            radius = pill_h / 2.0

            shadow_paint = Paint(Paint.ANTI_ALIAS_FLAG)
            shadow_paint.setStyle(PaintStyle.FILL)
            shadow_paint.setColor(-1728053248)  # 0x99000000
            shadow_rect = RectF(float(left + 3.0), float(top + 4.0), float(right + 3.0), float(bottom + 4.0))
            canvas.drawRoundRect(shadow_rect, float(radius), float(radius), shadow_paint)

            bg_paint = Paint(Paint.ANTI_ALIAS_FLAG)
            bg_paint.setStyle(PaintStyle.FILL)
            bg_paint.setColor(-1767148)  # 0xFFE50914
            pill_rect = RectF(float(left), float(top), float(right), float(bottom))
            canvas.drawRoundRect(pill_rect, float(radius), float(radius), bg_paint)

            stroke_paint = Paint(Paint.ANTI_ALIAS_FLAG)
            stroke_paint.setStyle(PaintStyle.STROKE)
            stroke_paint.setStrokeWidth(max(2.5, w * 0.008))
            stroke_paint.setColor(-10496)  # 0xFFFFD700
            canvas.drawRoundRect(pill_rect, float(radius), float(radius), stroke_paint)

            center_x = (left + right) / 2.0
            fm = text_paint.getFontMetrics()
            center_y = (top + bottom) / 2.0 - (fm.ascent + fm.descent) / 2.0
            canvas.drawText(badge_label, float(center_x), float(center_y), text_paint)

            if latest_title:
                clean_t = re.sub(r'\s+', ' ', str(latest_title)).strip()
                if len(clean_t) > 13:
                    clean_t = clean_t[:12] + '…'
                sub_label = f'新片: {clean_t}'
                bar_h = max(28.0, h * 0.12)
                bar_top = float(h) - bar_h - half_b
                bar_paint = Paint(Paint.ANTI_ALIAS_FLAG)
                bar_paint.setStyle(PaintStyle.FILL)
                bar_paint.setColor(-1291845632)  # 0xB3000000
                canvas.drawRect(half_b, float(bar_top), float(w) - half_b, float(h) - half_b, bar_paint)

                sub_paint = Paint(Paint.ANTI_ALIAS_FLAG)
                sub_paint.setColor(-10496)
                sub_paint.setTextSize(max(18.0, w * 0.054))
                sub_paint.setTypeface(Typeface.DEFAULT_BOLD)
                sub_paint.setTextAlign(PaintAlign.CENTER)
                sfm = sub_paint.getFontMetrics()
                sub_y = (bar_top + float(h) - half_b) / 2.0 - (sfm.ascent + sfm.descent) / 2.0
                canvas.drawText(sub_label, float(w) / 2.0, float(sub_y), sub_paint)

            baos = ByteArrayOutputStream()
            mutable_bmp.compress(CompressFormat.JPEG, 90, baos)
            out_bytes = bytes(baos.toByteArray())
            try:
                src_bmp.recycle()
                mutable_bmp.recycle()
            except Exception:
                pass
            if out_bytes:
                return out_bytes, 'image/jpeg'
        except Exception as e:
            debug_log('android canvas badge fallback', repr(e))
        return None, None

    def _fetch_hot_comments(self, video_id, max_count=25):
        """通过 YouTube Innertube /youtubei/v1/next/ 接口极速抓取视频热门评论（单次 5KB 请求，~0.6s 完成）。
        # NOTE: 为什么之前 TV 端抓不到评论（ReadTimeout / 403）：
        #   1. 在代理节点下，不带末尾斜杠的 `/youtubei/v1/next` 会触发 Google 边缘 WAF 403 验证码拦截或慢速排队，
        #      而 `/youtubei/v1/next/`（带末尾斜杠）100% 绕过边缘 WAF 直达 Innertube 后端；
        #   2. 不带 `X-Goog-FieldMask` 时，Step 1 返回 ~900KB、Step 2 返回 ~450KB，与起播视频流并发时必超 4 秒超时；
        #   3. 直接在本地用 Protobuf 合成「最热门评论」的 continuation token，结合 `X-Goog-FieldMask` 仅需 1 次 5KB 请求即可秒拿 20 条热评！
        """
        if not video_id:
            return []
        cache_key = f'yt_hot_comments_{video_id}'
        cached = self.getCache(cache_key)
        if isinstance(cached, dict) and cached.get('expires', 0) > time.time():
            return cached.get('comments') or []

        lock = self._cmt_fetch_locks.setdefault(video_id, threading.RLock())
        with lock:
            cached = self.getCache(cache_key)
            if isinstance(cached, dict) and cached.get('expires', 0) > time.time():
                return cached.get('comments') or []

            url = 'https://www.youtube.com/youtubei/v1/next/?prettyPrint=false'
            ctx = {'client': {'clientName': 'WEB', 'clientVersion': '2.20250201.00.00', 'hl': 'zh-CN', 'gl': 'US'}}
            proxies = dict(self.session.proxies or {})
            field_mask_step1 = (
                'contents.twoColumnWatchNextResults.results.results.contents.itemSectionRenderer('
                'sectionIdentifier,contents.continuationItemRenderer.continuationEndpoint.continuationCommand.token),'
                'engagementPanels.engagementPanelSectionListRenderer(panelIdentifier,targetId,'
                'header.engagementPanelTitleHeaderRenderer.menu.sortFilterSubMenuRenderer.subMenuItems('
                'title,serviceEndpoint.continuationCommand.token))'
            )
            field_mask_step2 = (
                'frameworkUpdates.entityBatchUpdate.mutations.payload.commentEntityPayload('
                'properties.content.content,author.displayName,toolbar(likeCountNotliked,likeCountLiked)),'
                'onResponseReceivedEndpoints(reloadContinuationItemsCommand.continuationItems,'
                'appendContinuationItemsAction.continuationItems)'
            )
            base_headers = {
                'User-Agent': self.header.get('User-Agent') or DEFAULT_UA,
                'Content-Type': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
                'Origin': 'https://www.youtube.com',
                'Referer': f'https://www.youtube.com/watch?v={video_id}',
                'X-YouTube-Client-Name': '1',
                'X-YouTube-Client-Version': '2.20250201.00.00',
                'Connection': 'close',
            }

            comments = []
            seen_texts = set()

            def _parse_comments_response(d2):
                mutations = (((d2.get('frameworkUpdates') or {}).get('entityBatchUpdate') or {}).get('mutations') or [])
                for m in mutations:
                    payload = (m.get('payload') or {}).get('commentEntityPayload')
                    if payload:
                        props = payload.get('properties') or {}
                        author = ((payload.get('author') or {}).get('displayName') or '').strip()
                        content = ((props.get('content') or {}).get('content') or '').strip()
                        likes = ((payload.get('toolbar') or {}).get('likeCountNotliked') or (payload.get('toolbar') or {}).get('likeCountLiked') or '').strip()
                        content_clean = re.sub(r'\s+', ' ', html.unescape(content)).strip()
                        if content_clean and content_clean not in seen_texts:
                            seen_texts.add(content_clean)
                            comments.append({
                                'author': author or '网友',
                                'likes': likes,
                                'text': content_clean,
                            })
                if not comments:
                    def scan_legacy(o):
                        if isinstance(o, dict):
                            cr = o.get('commentRenderer')
                            if cr:
                                author = ((cr.get('authorText') or {}).get('simpleText') or '').strip()
                                runs = (cr.get('contentText') or {}).get('runs') or []
                                content = ''.join(x.get('text', '') for x in runs).strip()
                                likes = ((cr.get('voteCount') or {}).get('simpleText') or '').strip()
                                content_clean = re.sub(r'\s+', ' ', html.unescape(content)).strip()
                                if content_clean and content_clean not in seen_texts:
                                    seen_texts.add(content_clean)
                                    comments.append({
                                        'author': author or '网友',
                                        'likes': likes,
                                        'text': content_clean,
                                    })
                            for v in o.values():
                                scan_legacy(v)
                        elif isinstance(o, list):
                            for v in o:
                                scan_legacy(v)
                    scan_legacy(d2)

            try:
                # 1. 优先尝试零延迟单次直达 Token（直接合成 11 字节 video_id 的最热门评论 continuation token，免去 Step 1）
                if len(video_id) == 11:
                    vid_bytes = video_id.encode('ascii')
                    raw_tok = (
                        bytes.fromhex('120d120b') + vid_bytes +
                        bytes.fromhex('180632382211220b') + vid_bytes +
                        bytes.fromhex('3000780230014221656e676167656d656e742d70616e656c2d636f6d6d656e74732d73656374696f6e')
                    )
                    direct_tok = base64.urlsafe_b64encode(raw_tok).decode('ascii').rstrip('=')
                    h2 = base_headers.copy()
                    h2['X-Goog-FieldMask'] = field_mask_step2
                    r_direct = requests.post(
                        url, json={'context': ctx, 'continuation': direct_tok},
                        headers=h2, proxies=proxies, timeout=(4, 7))
                    if r_direct.status_code == 200:
                        _parse_comments_response(r_direct.json())

                # 2. 若单次直达未取到评论（如特殊视频面板结构），回退带 FieldMask 的 1.7KB 轻量级 Step 1 + Step 2
                if not comments:
                    h1 = base_headers.copy()
                    h1['X-Goog-FieldMask'] = field_mask_step1
                    r1 = requests.post(
                        url, json={'context': ctx, 'videoId': video_id},
                        headers=h1, proxies=proxies, timeout=(4, 7))
                    if r1.status_code == 200:
                        d1 = r1.json()
                        top_token = None
                        fallback_tokens = []

                        def scan_tokens(obj):
                            nonlocal top_token
                            if isinstance(obj, dict):
                                if 'subMenuItems' in obj and isinstance(obj['subMenuItems'], list):
                                    for idx, item in enumerate(obj['subMenuItems']):
                                        tok = (((item.get('serviceEndpoint') or {}).get('continuationCommand') or {}).get('token'))
                                        title = str(item.get('title') or '')
                                        if tok:
                                            if '热' in title or '热门' in title or 'Top' in title or idx == 0:
                                                if not top_token:
                                                    top_token = tok
                                            fallback_tokens.append(tok)
                                if obj.get('sectionIdentifier') == 'comment-item-section' or obj.get('targetId') == 'engagement-panel-comments-section':
                                    def scan_inner(o):
                                        if isinstance(o, dict):
                                            t = (o.get('continuationCommand') or {}).get('token')
                                            if t:
                                                fallback_tokens.append(t)
                                            for v in o.values():
                                                scan_inner(v)
                                        elif isinstance(o, list):
                                            for v in o:
                                                scan_inner(v)
                                    scan_inner(obj)
                                for v in obj.values():
                                    scan_tokens(v)
                            elif isinstance(obj, list):
                                for v in obj:
                                    scan_tokens(v)

                        scan_tokens(d1)
                        token = top_token or (fallback_tokens[0] if fallback_tokens else None)
                        if token:
                            h2 = base_headers.copy()
                            h2['X-Goog-FieldMask'] = field_mask_step2
                            r2 = requests.post(
                                url, json={'context': ctx, 'continuation': token},
                                headers=h2, proxies=proxies, timeout=(4, 7))
                            if r2.status_code == 200:
                                _parse_comments_response(r2.json())
            except Exception as e:
                debug_log('fetch hot comments error', {'vid': video_id, 'error': repr(e)})

            comments = comments[:max_count]
            # 有评论时缓存 30 分钟；若为空仅短缓存 15 秒，防止偶发网络抖动锁死 30 分钟无评论
            ttl = 1800 if comments else 15
            self.setCache(cache_key, {'comments': comments, 'expires': time.time() + ttl})
            debug_log('fetched hot comments', {'vid': video_id, 'count': len(comments)})
            return comments

    def _prewarm_comments_async(self, video_id):
        if not video_id:
            return
        marquee_on = str(self.extendDict.get('comment_marquee') or 'on').strip().lower() not in ('0', 'off', 'false', 'no')
        if not marquee_on:
            return
        def _bg():
            try:
                self._fetch_hot_comments(video_id, max_count=20)
            except Exception:
                pass
        try:
            threading.Thread(target=_bg, daemon=True).start()
        except Exception:
            pass

    def _build_marquee_cues(self, comments, total_duration=1800, max_line_chars=38, gap_sec=1.5):
        """生成“像流水一样慢慢输出”的无顿挫热门评论跑马灯字幕序列 [(start_sec, end_sec, text, vtt_settings), ...]。
        # NOTE: 为什么之前的跑马灯会看着“一顿一顿”：
        #   1. WebVTT 默认是居中对齐（align:center），当字符串长度变化或用视口滑动时，整行文字的中心点不断左右摇摆抖动；
        #   2. 之前每次步进 2~3 个字符、间隔 0.95s（约 1Hz 跳变），人眼对 1Hz 的整行跳动极度敏感。
        # 解决方案（左锚定流水式逐字平滑流出 + 自适应停留阅读）：
        #   1. 使用 VTT 左对齐固定锚点 (`line:6% position:6% align:start`)，每个已出现的字在屏幕上的像素坐标绝对固定，绝不左右晃动；
        #   2. 采用逐字匀速流式输出（每次仅自然生长 1 个字符 / 1 个英文单词，帧间隔 0.14s ≈ 7fps 连续流体感），末尾辅以轻量流光游标 `▸`；
        #   3. 超长评论在完成第一行后保留上一行并平滑流入第二行；整条评论流完后静止停留 5.5~11.0 秒（按字数自适应），让观众从容看完。
        """
        if not comments:
            return []
        try:
            max_line_chars = max(28, int(self.extendDict.get('comment_line_chars') or max_line_chars))
            gap_sec = max(0.8, float(self.extendDict.get('comment_gap_sec') or gap_sec))
        except Exception:
            pass

        def _wrap_comment_lines(full_str, line_width, max_lines=2):
            """按自然标点将评论切分为最多 2 行，避免单行过长超出电视屏幕右侧。"""
            if len(full_str) <= line_width:
                return [full_str]
            lines = []
            rem = full_str.strip()
            punct = set('，。！？；、,.!?;:： ）)】」》')
            while rem and len(lines) < max_lines:
                if len(rem) <= line_width or len(lines) == max_lines - 1:
                    if len(rem) > line_width + 4:
                        rem = rem[:line_width + 3] + '…'
                    lines.append(rem)
                    break
                cut = line_width
                for back in range(min(len(rem) - 1, line_width + 3), max(12, line_width - 10), -1):
                    if rem[back] in punct:
                        cut = back + 1
                        break
                lines.append(rem[:cut].strip())
                rem = rem[cut:].strip()
            return lines

        def _tokenize_smooth_stream(s):
            """将字符串切分为均匀的流式生长单元：中文字符 1 字 1 步（紧跟的标点合并），英文按短词合并。"""
            tokens = []
            i = 0
            n = len(s)
            punct = set('，。！？；、,.!?;:：）)】」》”’')
            while i < n:
                ch = s[i]
                if ch.isascii() and (ch.isalnum() or ch in ('_', '-', "'")):
                    j = i + 1
                    while j < n and (j - i) < 5 and s[j].isascii() and (s[j].isalnum() or s[j] in ('_', '-', "'")):
                        j += 1
                    while j < n and s[j] in (' ',) and (j - i) < 6:
                        j += 1
                    tokens.append(s[i:j])
                    i = j
                else:
                    j = i + 1
                    while j < n and s[j] in punct:
                        j += 1
                    tokens.append(s[i:j])
                    i = j
            return tokens

        prepared = []
        for idx, c in enumerate(comments[:20]):
            author = str(c.get('author') or '网友').lstrip('@').strip()[:14]
            likes = str(c.get('likes') or '').strip()
            text = re.sub(r'\s+', ' ', html.unescape(html.unescape(str(c.get('text') or '')))).strip()
            if not text:
                continue
            if len(text) > 78:
                text = text[:76] + '…'
            like_str = f' 👍{likes}' if likes and likes != '0' else ''
            prefix = f'🔥热评#{idx + 1} [@{author}{like_str}]：'
            body_lines = _wrap_comment_lines(text, max_line_chars, max_lines=2)
            if not body_lines:
                continue
            prepared.append((prefix, body_lines, len(text)))

        if not prepared:
            return []

        cues = []
        t = 2.0
        dur_limit = max(180.0, min(float(total_duration or 1800), 7200.0))
        # 左对齐固定锚点：确保新字流出时已有文字纹丝不动，彻底消除居中重排带来的左右抖动
        vtt_pos = 'line:6% position:6% align:start'
        char_step_sec = 0.14

        while t < dur_limit and len(cues) < 2400:
            for prefix, body_lines, text_len in prepared:
                if t >= dur_limit or len(cues) >= 2400:
                    break
                completed_lines = []
                for line_idx, line_str in enumerate(body_lines):
                    tokens = _tokenize_smooth_stream(line_str)
                    cur_line = ''
                    for tok_idx, tok in enumerate(tokens):
                        if t >= dur_limit or len(cues) >= 2400:
                            break
                        cur_line += tok
                        is_very_last = (line_idx == len(body_lines) - 1 and tok_idx == len(tokens) - 1)
                        if is_very_last:
                            # 最后一个字流完后，直接进入整条评论的静止阅读阶段，无缝衔接
                            hold_sec = max(5.5, min(11.0, 4.5 + text_len * 0.12))
                            s_t = t
                            e_t = min(dur_limit, t + hold_sec)
                            full_display = '\n'.join([prefix + (completed_lines[0] if completed_lines else cur_line)] + (
                                [cur_line] if completed_lines else []
                            ))
                            cues.append((s_t, e_t, full_display, vtt_pos))
                            t = e_t
                        else:
                            s_t = t
                            e_t = min(dur_limit, t + char_step_sec)
                            first_row = prefix + (completed_lines[0] if completed_lines else (cur_line + ' ▸'))
                            rows = [first_row]
                            if completed_lines:
                                rows.append(cur_line + ' ▸')
                            cues.append((s_t, e_t, '\n'.join(rows), vtt_pos))
                            t = e_t
                    completed_lines.append(line_str)
                t += gap_sec
            t += 4.0
        return cues

    def _attach_default_zh_subs(self, res, data, video_id):
        sub_proxy_vtt = f'http://127.0.0.1:9978/proxy?do=py&type=sub&vid={video_id}&format=vtt&ext=.vtt'
        sub_proxy_comments = f'http://127.0.0.1:9978/proxy?do=py&type=sub&vid={video_id}&mode=comments&format=vtt&ext=.vtt'
        sub_proxy_clean = f'http://127.0.0.1:9978/proxy?do=py&type=sub&vid={video_id}&mode=sub_only&format=vtt&ext=.vtt'
        sub_proxy_srt = f'http://127.0.0.1:9978/proxy?do=py&type=sub&vid={video_id}&format=srt&ext=.srt'
        res['subt'] = sub_proxy_vtt
        res['sub'] = sub_proxy_vtt
        res['subs'] = [
            {'name': '简体中文+🔥热评跑马灯', 'lang': 'zh-Hans', 'format': 'text/vtt', 'url': sub_proxy_vtt},
            {'name': '💬 仅热门评论跑马灯', 'lang': 'zh-CN', 'format': 'text/vtt', 'url': sub_proxy_comments},
            {'name': '纯净中文字幕', 'lang': 'zh-TW', 'format': 'text/vtt', 'url': sub_proxy_clean},
            {'name': '中文 (SRT)', 'lang': 'zh', 'format': 'application/x-subrip', 'url': sub_proxy_srt},
        ]
        res['extra'] = {
            'subt': sub_proxy_vtt,
            'subtitles': [
                {'url': sub_proxy_vtt, 'name': '简体中文+🔥热评跑马灯', 'lang': 'zh-Hans', 'format': 'text/vtt'},
                {'url': sub_proxy_comments, 'name': '💬 仅热门评论跑马灯', 'lang': 'zh-CN', 'format': 'text/vtt'},
                {'url': sub_proxy_clean, 'name': '纯净中文字幕', 'lang': 'zh-TW', 'format': 'text/vtt'},
                {'url': sub_proxy_srt, 'name': '中文 (SRT)', 'lang': 'zh', 'format': 'application/x-subrip'},
            ]
        }
        return res

    def _extract_chinese_subtitle_urls(self, captions):
        if not captions:
            return []
        tracklist = (captions.get('playerCaptionsTracklistRenderer') or {})
        tracks = tracklist.get('captionTracks') or []
        if not tracks:
            return []
        candidates = []
        # 1. 优先 zh / zh-CN / zh-Hans 原生字幕
        for t in tracks:
            lc = (t.get('languageCode') or '').lower()
            if lc in ('zh', 'zh-cn', 'zh-hans', 'zh-sg'):
                u = t.get('baseUrl')
                if u and u not in candidates:
                    candidates.append(u)
        # 2. 繁体中文原生字幕
        for t in tracks:
            lc = (t.get('languageCode') or '').lower()
            if lc in ('zh-hant', 'zh-tw', 'zh-hk'):
                u = t.get('baseUrl')
                if u and u not in candidates:
                    candidates.append(u)
        # 3. 包含中文字样的原生字幕
        for t in tracks:
            name_text = (t.get('name') or {}).get('simpleText') or ''
            if not name_text and t.get('name', {}).get('runs'):
                name_text = ''.join(x.get('text', '') for x in t['name']['runs'])
            if '中' in name_text or 'Chinese' in name_text:
                u = t.get('baseUrl')
                if u and u not in candidates:
                    candidates.append(u)
        # 4. 自动翻译为简体中文（对首个非中文原生轨追加 &tlang=zh-Hans）
        # 5. 同时追加不带 &tlang= 的原生轨 baseUrl 作为抗 429 兜底（Cloudflare 节点下 &tlang= 易触发 429，原生轨返回 200 后由本地 GTX 批量翻译为中文）
        for t in tracks:
            lc = (t.get('languageCode') or '').lower()
            if not lc.startswith('zh'):
                base_u = t.get('baseUrl')
                if base_u:
                    clean_u = re.sub(r'&tlang=[^&]+', '', base_u)
                    clean_u = re.sub(r'&fmt=[^&]+', '', clean_u)
                    tlang_u = clean_u + '&tlang=zh-Hans'
                    if tlang_u not in candidates:
                        candidates.append(tlang_u)
                    if clean_u not in candidates:
                        candidates.append(clean_u)
                    break
        return candidates


    def _extract_chinese_subtitle_url(self, captions):
        urls = self._extract_chinese_subtitle_urls(captions)
        return urls[0] if urls else None

    def _translate_cues_to_zh(self, cues):
        """当回退到非中文原生字幕轨（如英文 ASR）时，批量并发调用 Google GTX 翻译为简体中文。
        # NOTE: 采用带行号标记 [j] 的批量翻译解析，避免 Google GTX 偶发合并换行符导致整批行数不等而漏翻。
        """
        if not cues:
            return cues
        sample = ''.join(c[2] for c in cues[:25])
        if not sample:
            return cues
        cjk_count = sum(1 for ch in sample if '\u4e00' <= ch <= '\u9fff')
        if cjk_count >= max(2, int(len(sample) * 0.15)):
            return cues
        proxies = dict(getattr(self, 'session', None) and self.session.proxies or {})
        batch_size = 35
        batches = [cues[i:i + batch_size] for i in range(0, len(cues), batch_size)]
        translated_map = {}

        def _trans_batch(b_idx, batch):
            tagged_lines = [f'[{j}] ' + x[2].replace('\n', ' ') for j, x in enumerate(batch)]
            joined = '\n'.join(tagged_lines)
            try:
                r = requests.get(
                    'https://translate.googleapis.com/translate_a/single',
                    params={'client': 'gtx', 'sl': 'auto', 'tl': 'zh-CN', 'dt': 't', 'q': joined},
                    headers={'User-Agent': 'Mozilla/5.0', 'Connection': 'close'},
                    proxies=proxies,
                    timeout=6,
                )
                if r.status_code == 200:
                    data = r.json()
                    full_zh = ''.join(seg[0] for seg in (data[0] or []) if seg and seg[0])
                    matches = re.findall(r'[\[\【](\d+)[\]\】]\s*([^\n\[\【]+)', full_zh)
                    if matches:
                        for idx_str, zh_txt in matches:
                            j = int(idx_str)
                            if 0 <= j < len(batch):
                                s, e, orig, pos = batch[j]
                                clean_zh = zh_txt.strip()
                                if clean_zh:
                                    translated_map[b_idx * batch_size + j] = (s, e, clean_zh, pos)
                    else:
                        lines = [ln.strip() for ln in full_zh.split('\n') if ln.strip()]
                        for j in range(min(len(lines), len(batch))):
                            s, e, orig, pos = batch[j]
                            clean_zh = re.sub(r'^[\[\【]\d+[\]\】]\s*', '', lines[j]).strip()
                            translated_map[b_idx * batch_size + j] = (s, e, clean_zh or orig, pos)
            except Exception:
                pass

        threads = []
        for b_idx, batch in enumerate(batches[:16]):
            t = threading.Thread(target=_trans_batch, args=(b_idx, batch), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=6)

        if not translated_map:
            return cues
        return [translated_map.get(i, c) for i, c in enumerate(cues)]

    def _proxy_sub(self, params):
        vid = params.get('vid')
        ext_param = str(params.get('ext') or '').lower()
        fmt_param = str(params.get('format') or '').lower()
        if fmt_param in ('vtt', 'srt'):
            wanted_fmt = fmt_param
        elif ext_param.endswith('.srt'):
            wanted_fmt = 'srt'
        else:
            wanted_fmt = 'vtt'
        if not vid:
            if wanted_fmt == 'srt':
                return [200, 'application/x-subrip; charset=utf-8', b'1\r\n00:00:00,000 --> 00:00:00,100\r\n \r\n\r\n']
            return [200, 'text/vtt; charset=utf-8', b'WEBVTT\n\n']

        mode = str(params.get('mode') or 'both').lower()
        marquee_cfg = str(self.extendDict.get('comment_marquee') or 'on').strip().lower() not in ('0', 'off', 'false', 'no')
        include_comments = (mode in ('both', 'comments')) and (marquee_cfg or mode == 'comments')
        include_subs = (mode in ('both', 'sub_only'))

        ua_candidates = [
            'com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]

        def fmt_time_vtt(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            sec = t % 60
            return f'{h:02d}:{m:02d}:{sec:06.3f}'

        def fmt_time_srt(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            sec = int(t % 60)
            ms = int(round((t - int(t)) * 1000))
            return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'

        sub_cues = []
        max_sub_end = 0.0
        cached_ext = ((getattr(self, 'yt', None) and getattr(self.yt, 'extract_cache', {}).get(vid)) or {}).get('data') or {}

        if include_subs:
            cached_sub_cues = self.getCache(f'yt_sub_cues_{vid}')
            if isinstance(cached_sub_cues, list) and cached_sub_cues:
                sub_cues = cached_sub_cues
                max_sub_end = max((c[1] for c in sub_cues), default=0.0)
            else:
                captions = cached_ext.get('captions')
                if not captions:
                    data = self.getCache(f'yt_{vid}_1080p') or self.getCache(f'yt_{vid}_best')
                    if isinstance(data, dict):
                        captions = data.get('captions')
                if not captions:
                    for c in (
                        {
                            'clientName': 'ANDROID', 'clientVersion': '20.10.38', 'androidSdkVersion': 30,
                            'userAgent': 'com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip',
                            'osName': 'Android', 'osVersion': '11', 'hl': 'zh-CN', 'gl': 'US'
                        },
                        {
                            'clientName': 'IOS', 'clientVersion': '21.02.3',
                            'userAgent': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)',
                            'osName': 'iPhone', 'osVersion': '18.3.2.22D82', 'hl': 'zh-CN', 'gl': 'US'
                        }
                    ):
                        try:
                            res = requests.post(
                                'https://www.youtube.com/youtubei/v1/player?prettyPrint=false',
                                json={'context': {'client': c}, 'videoId': vid},
                                headers={'User-Agent': c['userAgent'], 'Connection': 'close'},
                                proxies=dict(self.session.proxies or {}),
                                timeout=6
                            ).json()
                            captions = res.get('captions')
                            if captions:
                                break
                        except Exception:
                            continue

                sub_urls = self._extract_chinese_subtitle_urls(captions)
                for sub_url in sub_urls:
                    if '&exp=xpe' in sub_url:
                        continue
                    fetched_ok = False
                    for ua in ua_candidates:
                        try:
                            r = requests.get(
                                sub_url,
                                headers={'User-Agent': ua, 'Accept': '*/*', 'Connection': 'close'},
                                proxies=dict(self.session.proxies or {}),
                                timeout=6
                            )
                            if r.status_code == 200 and len(r.text) > 30:
                                text = r.text
                                items = re.findall(r'<text start="([0-9.]+)" dur="([0-9.]+)"[^>]*>([\s\S]*?)</text>', text)
                                if not items:
                                    p_items = re.findall(r'<p t="([0-9]+)" d="([0-9]+)"[^>]*>([\s\S]*?)</p>', text)
                                    items = [(str(float(t_ms) / 1000.0), str(float(d_ms) / 1000.0), b) for t_ms, d_ms, b in p_items]
                                if items:
                                    raw_cues = []
                                    for s_str, d_str, body in items:
                                        s, d = float(s_str), float(d_str)
                                        clean = html.unescape(html.unescape(re.sub(r'<[^>]+>', '', body))).strip()
                                        clean = re.sub(r'^>+\s*', '', clean)
                                        clean = re.sub(r'\s+', ' ', clean).strip()
                                        if clean and (not raw_cues or raw_cues[-1][2] != clean):
                                            raw_cues.append((s, s + d, clean, ''))
                                            if s + d > max_sub_end:
                                                max_sub_end = s + d
                                    # NOTE: 消除 YouTube ASR 滚动字幕相邻两句时间戳重叠（会导致双行同时显示并在说到一半时跳动）
                                    for idx_c, (s, e, clean, pos) in enumerate(raw_cues):
                                        if idx_c + 1 < len(raw_cues):
                                            next_s = raw_cues[idx_c + 1][0]
                                            if next_s > s + 0.15 and e > next_s - 0.02:
                                                e = next_s - 0.02
                                        sub_cues.append((s, e, clean, pos))
                                    if sub_cues:
                                        if 'tlang=zh' not in sub_url:
                                            sub_cues = self._translate_cues_to_zh(sub_cues)
                                        self.setCache(f'yt_sub_cues_{vid}', sub_cues)
                                        fetched_ok = True
                                        break
                        except Exception:
                            continue
                    if fetched_ok:
                        break
                debug_log('proxy sub result', {'vid': vid, 'urls': len(sub_urls), 'cues': len(sub_cues)})

        marquee_cues = []
        if include_comments:
            comments = self._fetch_hot_comments(vid, max_count=20)
            if comments:
                vid_dur = float(cached_ext.get('duration') or 0)
                est_dur = vid_dur if vid_dur > 0 else (max(600.0, max_sub_end) if max_sub_end > 0 else 1800.0)
                marquee_cues = self._build_marquee_cues(comments, total_duration=est_dur)
            debug_log('proxy sub marquee', {'vid': vid, 'comments': len(comments or []), 'marquee_cues': len(marquee_cues)})

        all_cues = sub_cues + marquee_cues
        if not all_cues:
            # 绝不返回 404，防止 ExoPlayer SingleSampleMediaSource / MergingMediaSource 因字幕 404 中断整部视频播放
            if wanted_fmt == 'srt':
                return [200, 'application/x-subrip; charset=utf-8', b'1\r\n00:00:00,000 --> 00:00:00,100\r\n \r\n\r\n']
            return [200, 'text/vtt; charset=utf-8', b'WEBVTT\n\n']

        all_cues.sort(key=lambda x: (x[0], 0 if x[3] else 1))

        if wanted_fmt == 'vtt':
            lines = ['WEBVTT\n\n']
            for i, (s, e, text, vtt_pos) in enumerate(all_cues):
                pos_suffix = f' {vtt_pos}' if vtt_pos else ''
                lines.append(f'{i + 1}\n{fmt_time_vtt(s)} --> {fmt_time_vtt(e)}{pos_suffix}\n{text}\n\n')
            return [200, 'text/vtt; charset=utf-8', ''.join(lines).encode('utf-8')]
        else:
            lines = []
            for i, (s, e, text, vtt_pos) in enumerate(all_cues):
                prefix = '{\\an8}' if vtt_pos else ''
                lines.append(f'{i + 1}\r\n{fmt_time_srt(s)} --> {fmt_time_srt(e)}\r\n{prefix}{text}\r\n\r\n')
            return [200, 'application/x-subrip; charset=utf-8', ''.join(lines).encode('utf-8')]

    CH_CARD_PNG_BYTES = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAUAAAAC0CAIAAABqhmJGAAACJklEQVR4nO3TMQkAMBDAwFfy"
        "U/1rrIcuJXBwArJkdg8QNd8LgGcGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQ"
        "ZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkY"
        "wgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjAD"
        "Q5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBm"
        "YAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjC"
        "DAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMAND"
        "mIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIMDGEGhjADQ5iBIczAEGZg"
        "CDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OYgSHMwBBmYAgzMIQZGMIM"
        "DGEGhjADQ5iBIczAEGZgCDMwhBkYwgwMYQaGMANDmIEhzMAQZmAIMzCEGRjCDAxhBoYwA0OY"
        "gSHMwBBmYAgzMIQZGMIMDGEGhjAD2AXIx2TtQISjigAAAABJRU5ErkJggg=="
    )

    def _proxy_ch_pic(self, params):
        return [200, 'image/png', self.CH_CARD_PNG_BYTES, {
            'Content-Type': 'image/png',
            'Content-Length': str(len(self.CH_CARD_PNG_BYTES)),
            'Cache-Control': 'public, max-age=86400',
        }]

    def _proxy_ch_avatar(self, params):
        ch_name = unquote(params.get('name') or '')
        clean = self._clean_channel_name(ch_name)
        entry = self._check_single_channel_rss(clean, force=False)
        has_upd, pub_text = self._is_channel_has_update(clean, entry)
        latest_title = (entry or {}).get('latest_title') or ''

        raw_key = f'yt_raw_avatar_{clean}'
        raw_cached = self.getCache(raw_key)
        img_bytes = None
        c_type = 'image/jpeg'
        if isinstance(raw_cached, dict) and raw_cached.get('bytes'):
            img_bytes = raw_cached['bytes']
            c_type = raw_cached.get('type') or 'image/jpeg'
        else:
            avatar_url = self.CHANNEL_CARD_AVATARS.get(clean) or self.CHANNEL_CARD_AVATARS.get(ch_name)
            if avatar_url:
                for attempt in range(2):
                    try:
                        r = self.session.get(avatar_url, timeout=5)
                        if r.status_code == 200 and r.content:
                            img_bytes = bytes(r.content)
                            c_type = r.headers.get('content-type', 'image/jpeg')
                            self.setCache(raw_key, {'bytes': img_bytes, 'type': c_type})
                            break
                    except Exception:
                        pass

        if not img_bytes:
            img_bytes = self.CH_CARD_PNG_BYTES
            c_type = 'image/png'

        if has_upd:
            badged_bytes, badged_type = self._draw_update_badge_on_image(img_bytes, pub_text=pub_text, latest_title=latest_title)
            if badged_bytes:
                return [200, badged_type, badged_bytes, {
                    'Content-Type': badged_type,
                    'Content-Length': str(len(badged_bytes)),
                    'Cache-Control': 'no-cache, max-age=0',
                }]

        return [200, c_type, img_bytes, {
            'Content-Type': c_type,
            'Content-Length': str(len(img_bytes)),
            'Cache-Control': 'public, max-age=300',
        }]

    # ==========================================================
    # 🔴 直播支持（ofiii 风格）：
    #   liveContent()  -> 返回 M3U（影视TV/猫影视「直播」入口）
    #   localProxy(type=live) -> 解析 YouTube 直播并返回改写后的 m3u8
    #   同时提供点播站形式：首页「🔴 直播」分类 -> 选频道 -> 播放
    # 列表来源：ext 的 live_txt（http(s)/本地路径/裸文本）> 内置 DEFAULT_LIVE_TXT
    # ==========================================================
    LIVE_MIME = 'application/vnd.apple.mpegurl'

    def isVideoFormat(self, url):
        # 只对「直播代理地址」生效；点播地址一律返回 False，保持原脚本行为不变
        try:
            return 'type=live' in str(url or '')
        except Exception:
            return False

    def manualVideoCheck(self):
        return False

    def _live_cfg(self, key, default=None):
        try:
            val = (self.extendDict or {}).get(key)
        except Exception:
            val = None
        return default if val is None else val

    def _live_on(self, key, default=True):
        raw = self._live_cfg(key, None)
        if raw is None:
            return default
        return str(raw).strip().lower() not in ('0', 'off', 'false', 'no')

    def _live_proxy_base(self):
        base = ''
        try:
            base = str(self.getProxyUrl() or '').strip()
        except Exception:
            base = ''
        return base if base.startswith('http') else 'http://127.0.0.1:9978/proxy?do=py'

    def _live_play_url(self, src):
        """频道播放地址 = 本地代理，真正取流推迟到点击时（lazy），列表秒开。"""
        base = self._live_proxy_base()
        sep = '&' if '?' in base else '?'
        return '%s%stype=live&id=%s&ext=.m3u8' % (base, sep, _live_b64e(str(src)))

    def _live_thumb(self, src):
        vid = ''
        try:
            vid = YouTubeLite.extract_video_id(src)
        except Exception:
            vid = ''
        if not vid:
            return ''
        return '%s&type=image&vid=%s&quality=mqdefault' % (self._live_proxy_base(), vid)

    def _live_load_txt(self):
        now = time.time()
        if getattr(self, '_live_txt_cache', '') and getattr(self, '_live_txt_exp', 0) > now:
            return self._live_txt_cache
        text = ''
        src_cfg = str(self._live_cfg('live_txt', '') or '').strip()
        if src_cfg:
            try:
                if src_cfg.startswith(('http://', 'https://')):
                    r = self.session.get(src_cfg, timeout=(6, 15))
                    if r is not None and r.status_code == 200:
                        # 【核心修复】：不直接用 r.text，改为手动处理 r.content
                        content = r.content
                        if content:
                            # 依次尝试常见编码：UTF-8, GBK, GB18030
                            for enc in ('utf-8', 'gbk', 'gb18030', 'latin-1'):
                                try:
                                    text = content.decode(enc)
                                    break
                                except UnicodeDecodeError:
                                    continue
                            else:
                                # 如果都不行，用替换模式强行解码，避免崩溃
                                text = content.decode('utf-8', errors='replace')
                elif src_cfg.startswith('file://'):
                    # 本地文件读取增加备份编码
                    file_path = src_cfg[7:]
                    text = self._live_read_file_safe(file_path)
                elif os.path.exists(src_cfg):
                    text = self._live_read_file_safe(src_cfg)
                else:
                    text = src_cfg  # ext 里直接内嵌 "名称,url" 多行文本
            except Exception as e:
                debug_log('live txt load error', repr(e))
        if not text.strip():
            text = DEFAULT_LIVE_TXT
        try:
            ttl = int(self._live_cfg('live_ttl', 1800) or 1800)
        except Exception:
            ttl = 1800
        self._live_txt_cache = text
        self._live_txt_exp = now + max(60, ttl)
        return text
    
    def _live_read_file_safe(self, file_path):
        """安全的本地文件读取，避免编码问题导致乱码"""
        for enc in ('utf-8', 'gbk', 'gb18030'):
            try:
                with io.open(file_path, 'r', encoding=enc, errors='ignore') as f:
                    return f.read()
            except Exception:
                continue
        # 都不行就用 utf-8 忽略错误读取
        with io.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _live_channels(self):
        """解析列表文本 -> [(分组, 名称, 源地址)]，支持 名称,#genre# 分组。"""
        now = time.time()
        if getattr(self, '_live_chan_cache', None) and getattr(self, '_live_chan_exp', 0) > now:
            return self._live_chan_cache
        rows = []
        seen = set()
        group = '未分组'
        for raw in (self._live_load_txt() or '').splitlines():
            line = (raw or '').strip()
            if not line or line.startswith('#'):
                continue
            if '#genre#' in line:
                group = line.split(',')[0].strip() or '未分组'
                continue
            if ',' not in line:
                continue
            name, url = line.split(',', 1)
            name, url = name.strip(), url.strip()
            if not name or not url:
                continue
            if 'youtube.com' not in url and 'youtu.be' not in url:
                continue
            key = (name, url)
            if key in seen:
                continue
            seen.add(key)
            rows.append((group, name, url))
        only = str(self._live_cfg('live_group', '') or '').strip()
        if only:
            keys = [x.strip() for x in only.split(',') if x.strip()]
            rows = [r for r in rows if r[0] in keys]
        self._live_chan_cache = rows
        self._live_chan_exp = now + 600
        debug_log('live channels loaded', {'count': len(rows)})
        return rows

    # ---------- 入口一：直播源（M3U） ----------
    def liveContent(self, url):
        try:
            rows = self._live_channels()
            epg = str(self._live_cfg('live_epg', '') or '').strip()
            out = ['#EXTM3U x-tvg-url="%s"' % epg] if epg else ['#EXTM3U']
            for group, name, src in rows:
                logo = self._live_thumb(src)
                tag = '#EXTINF:-1 tvg-name="%s"%s group-title="%s",%s' % (
                    name, (' tvg-logo="%s"' % logo) if logo else '', group, name)
                out.append(tag)
                out.append(self._live_play_url(src))
            return '\n'.join(out) + '\n'
        except Exception as e:
            debug_log('liveContent error', repr(e))
            return '#EXTM3U\n'

    # ---------- 入口二：点播站形式的「🔴 直播」分类 ----------
    def _live_vod_list(self, group=None):
        out = []
        for g, name, src in self._live_channels():
            if group and group not in ('', 'all', '全部') and g != group:
                continue
            out.append({
                'vod_id': 'LIVE__' + src,
                'vod_name': name,
                'vod_pic': self._live_thumb(src),
                'vod_remarks': '🔴 ' + g,
                'vod_tag': 'live',
            })
        return out

    def _live_detail(self, raw_id):
        src = str(raw_id)[6:]
        name, group = src, '直播'
        for g, n_, u in self._live_channels():
            if u == src:
                name, group = n_, g
                break
        return {'list': [{
            'vod_id': raw_id,
            'vod_name': name,
            'vod_pic': self._live_thumb(src),
            'type_name': group,
            'vod_remarks': '🔴 直播中',
            'vod_content': '%s（YouTube 直播 · 本地代理取流，自动选最高码率）' % name,
            'vod_play_from': 'YouTube直播',
            'vod_play_url': '直播$' + raw_id,
        }]}

    # ---------- 频道页（@handle/streams）-> 当前正在直播的 videoId ----------
    def _live_resolve(self, src):
        """返回 (video_id, hls_url)。watch/ID 直接返回；@handle 抓 /live 页面解析。"""
        src = (src or '').strip()
        try:
            vid = YouTubeLite.extract_video_id(src)
            if vid:
                return vid, ''
        except Exception:
            pass
        m = (re.search(r'youtube\.com/(@[0-9A-Za-z_.-]+)', src)
             or re.search(r'youtube\.com/((?:c|user)/[0-9A-Za-z_.-]+|channel/[0-9A-Za-z_-]+)', src))
        if not m:
            return '', ''
        key = m.group(1)
        now = time.time()
        cached = self._live_handle_cache.get(key) if hasattr(self, '_live_handle_cache') else None
        if cached and cached[2] > now:
            return cached[0], cached[1]
        try:
            ttl = int(self._live_cfg('live_handle_ttl', 120) or 120)
        except Exception:
            ttl = 120
        vid, hls = '', ''
        for page_url in ('https://www.youtube.com/%s/live' % key, 'https://www.youtube.com/%s/streams' % key):
            try:
                r = self.session.get(page_url, headers=self.header, timeout=(6, 15))
                final_url = getattr(r, 'url', '') or ''
                m2 = re.search(r'(?:v=|/live/)([0-9A-Za-z_-]{11})', final_url)
                if m2:
                    vid = m2.group(1)
                body = r.text or ''
                if not vid:
                    m3 = (re.search(r'videoId\\?":\\?"([0-9A-Za-z_-]{11})', body)
                          or re.search(r'/watch\?v=([0-9A-Za-z_-]{11})', body))
                    if m3:
                        vid = m3.group(1)
                if not hls:
                    m4 = re.search(r'hlsManifestUrl\\?":\\?"([^"\\]+)', body)
                    if m4:
                        hls = m4.group(1).replace('\\/', '/')
                if vid or hls:
                    break
            except Exception as e:
                debug_log('live handle resolve error', {'key': key, 'err': repr(e)})
        self._live_handle_cache[key] = (vid, hls, now + max(30, ttl))
        debug_log('live handle resolved', {'key': key, 'vid': vid, 'has_hls': bool(hls)})
        return vid, hls

    # ---------- localProxy(type=live) ----------
    def _proxy_live(self, params):
        raw = _live_one(params.get('id'))
        try:
            src = _live_b64d(raw)
        except Exception:
            src = raw
        if not src:
            return [400, 'text/plain', 'missing live id']
        try:
            vid, hls = self._live_resolve(src)
            if not hls and vid:
                yt = getattr(self, 'yt', None)
                if yt is None:
                    return [503, 'text/plain', '直播解析组件未初始化']
                data = yt.extract_live(vid)
                hls = (data or {}).get('hls_url') or ''
            if not hls:
                return [503, 'text/plain', '直播未开始或无法获取流']
            r = self.session.get(hls, headers=self._hls_headers(hls, 'master'), timeout=(6, 15))
            if r is None or r.status_code != 200:
                return [502, 'text/plain', 'live manifest failed: %s' % getattr(r, 'status_code', None)]
            text = self._rewrite_m3u8(r.text or '', hls, vid)
            debug_log('proxy live ok', {'src': src, 'vid': vid, 'lines': len(text.splitlines())})
            return [200, self.LIVE_MIME, text,
                    {'Content-Type': self.LIVE_MIME, 'Cache-Control': 'no-cache'}]
        except Exception as e:
            debug_log('proxy live error', {'src': src, 'err': repr(e)})
            return [500, 'text/plain', 'live error: %r' % e]

    def getName(self):
        return 'YouTube(SABR纯本地)'

    def init(self, extend):
        try:
            self.extendDict = json.loads(extend) if extend else {}
        except Exception:
            self.extendDict = {}
        self.session = requests.Session()
        self.session.trust_env = True
        # 独立媒体会话：用于本地直链兜底流拉取
        self.media_session = requests.Session()
        self.media_session.trust_env = False
        self.media_session.proxies = {'http': None, 'https': None}
        self.media_session.headers.clear()

        # 代理三级回退：ext 显式代理 > 内置本机节点 > 系统/全局代理。
        self.proxy_str = None
        proxy_val = self.extendDict.get('youtube_proxy') or self.extendDict.get('proxy')
        if proxy_val:
            if isinstance(proxy_val, str):
                proxy_url = proxy_val.strip()
                if proxy_url and not proxy_url.startswith(('http://', 'https://')):
                    proxy_url = 'http://' + proxy_url
                if proxy_url:
                    self.session.proxies = {'http': proxy_url, 'https': proxy_url}
                    if hasattr(self, 'media_session'):
                        self.media_session.proxies = {'http': proxy_url, 'https': proxy_url}
                    self.proxy_str = proxy_url.replace('http://', '').replace('https://', '')
                    debug_log('使用 ext 传入代理', {'proxy': proxy_url})
                else:
                    self._auto_detect_proxy()
            elif isinstance(proxy_val, dict):
                proxies = {}
                for scheme, value in proxy_val.items():
                    if scheme not in ('http', 'https') or not value:
                        continue
                    proxy_url = str(value).strip()
                    if not proxy_url.startswith(('http://', 'https://')):
                        proxy_url = 'http://' + proxy_url
                    proxies[scheme] = proxy_url
                if proxies:
                    self.session.proxies = proxies
                    if hasattr(self, 'media_session'):
                        self.media_session.proxies = proxies
                    selected_proxy = proxies.get('https') or proxies.get('http') or ''
                    self.proxy_str = selected_proxy.replace('http://', '').replace('https://', '')
                    debug_log('使用 ext 传入的字典代理', proxies)
                else:
                    self._auto_detect_proxy()
            else:
                self._auto_detect_proxy()
        else:
            self._auto_detect_proxy()
        self.header = {

            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.youtube.com/'
        }
        self.session.headers.update(self.header)
        self.yt = YouTubeLite(self.session, self.header, self.extendDict)
        self.config = {}
        self.search_page_cache = {}
        self.hls_url_cache = {}
        self.hls_proxy_enabled = self.extendDict.get('hls_proxy', True) is not False
        self.sabr_switch_lock = threading.RLock()
        # SABR 续流：把重取播放上下文的实现注入到 YouTubeLite。服务器每 ~70s 下发
        # RELOAD_PLAYER_RESPONSE 时，pump 循环回调此钩子换 fresh 会话（新 URL/ustreamer/pot）。
        self.yt.sabr_reload_hook = self._sabr_reload_session

        # 分类防刷去抖：盒子快速切分类时每次都会调 categoryContent，
        # 只有在某分类停留足够久（默认 2 秒）的那次请求才真正去搜，其余被后续切换取代者直接返回空。
        self._cat_seq = 0
        self._cat_lock = threading.Lock()
        try:
            self._cat_debounce_sec = float(self.extendDict.get('cat_debounce_sec') or 0.3)
        except Exception:
            self._cat_debounce_sec = 0.3
        self._cat_debounce_on = str(self.extendDict.get('cat_debounce') or 'on').strip().lower() not in ('0', 'off', 'false', 'no')
        # 起播预热：详情页打开即后台解析，起播从冷启动 ~10s 降到秒开
        self._prewarm_on = str(self.extendDict.get('prewarm') or 'on').strip().lower() not in ('0', 'off', 'false', 'no')
        self._prewarmed = set()
        # 超长音乐MV随机连播 & 相关推荐线路开关
        self._mv_mix_on = str(self.extendDict.get('mv_mix') or 'on').strip().lower() not in ('0', 'off', 'false', 'no')
        self._related_reco_on = str(self.extendDict.get('related_reco') or 'on').strip().lower() not in ('0', 'off', 'false', 'no')

        # 0ytb.json 绝对优先：无论本地还是网络环境，默认基准即为完整 0ytb.json 数据
        self.custom_data = copy.deepcopy(DEFAULT_0YTB_JSON)
        json_url = self.extendDict.get('json') or ''
        loaded_data = self._load_custom_json(json_url)
        if loaded_data and isinstance(loaded_data, dict):
            self.custom_data.update(loaded_data)

        self.custom_classes = self.custom_data.get('class') or self.custom_data.get('classes') or []
        # NOTE: 确保“音乐MV”栏目永远排在推荐页第 1 个默认选中位（即使本地存在旧版 0ytb.json 也将 music 置顶）
        if isinstance(self.custom_classes, list) and self.custom_classes:
            music_cls = [c for c in self.custom_classes if c.get('type_id') == 'music']
            other_cls = [c for c in self.custom_classes if c.get('type_id') != 'music']
            if music_cls:
                music_cls[0]['type_name'] = '🎵音乐MV'
                self.custom_classes = music_cls + other_cls
            else:
                self.custom_classes = [{'type_id': 'music', 'type_name': '🎵音乐MV'}] + other_cls
        self.custom_filters = self.custom_data.get('filter') or self.custom_data.get('filters') or {}
        if isinstance(self.custom_filters, dict):
            # 始终使用最新的 VEVO / 迈克尔·杰克逊剧情 MV 筛选配置
            self.custom_filters['music'] = copy.deepcopy(DEFAULT_0YTB_JSON['filters']['music'])
        self.custom_recommend = DEFAULT_0YTB_JSON.get('recommend') or self.custom_data.get('recommend') or []
        debug_log('0ytb.json loaded successfully', {
            'classes_count': len(self.custom_classes),
            'first_class': self.custom_classes[0].get('type_id') if self.custom_classes else None,
            'filters_keys': list(self.custom_filters.keys()) if isinstance(self.custom_filters, dict) else [],
            'has_recommend': bool(self.custom_recommend),
        })
        ua = (self.extendDict.get('ua') or '').strip()
        if ua:
            self.header['User-Agent'] = ua
            self.session.headers['User-Agent'] = ua

        # ---- 直播（Live）扩展配置 ----
        self._live_txt_cache = ''
        self._live_txt_exp = 0
        self._live_chan_cache = []
        self._live_chan_exp = 0
        self._live_handle_cache = {}
        debug_log('live module ready', {
            'live_txt': self.extendDict.get('live_txt') or '内置默认列表',
        })


    def _auto_detect_proxy(self):
        """依次探测内置本机代理；均不可用时回退到系统/环境代理。"""
        proxy_list = [
            'http://127.0.0.1:7897',
            'http://127.0.0.1:2080',
            'http://127.0.0.1:7890',
            'http://127.0.0.1:10809',
            'http://127.0.0.1:10172',
            'http://127.0.0.1:20172',
            'http://127.0.0.1:7891',
            'http://127.0.0.1:10808',
            'http://127.0.0.1:1087',
            'http://127.0.0.1:3128',
            'http://127.0.0.1:1080',
            'http://127.0.0.1:8080',
            'http://127.0.0.1:9090',
        ]
        for proxy_url in proxy_list:
            response = None
            try:
                test_proxies = {'http': proxy_url, 'https': proxy_url}
                response = requests.get(
                    'https://www.youtube.com', proxies=test_proxies, timeout=2)
                if response.status_code < 400:
                    self.session.proxies = test_proxies
                    if hasattr(self, 'media_session'):
                        self.media_session.proxies = test_proxies
                    self.proxy_str = proxy_url.replace('http://', '').replace('https://', '')
                    debug_log('内置代理探测成功，使用内置', {'proxy': proxy_url})
                    return
            except Exception:
                continue
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        # trust_env 保持开启；清空会话代理后由 requests 自动读取系统环境代理。
        self.session.proxies = {}
        if hasattr(self, 'media_session'):
            self.media_session.proxies = {}
        self.proxy_str = ''
        debug_log('所有内置代理均不可用，清空设置，回退使用系统/全局代理')

    def homeContent(self, filter):
        result = {}
        # 0ytb.json 100% 绝对优先：确保永远呈现 0ytb.json 的 14 个分类与筛选，且默认排第 1 为音乐MV
        result['class'] = self.custom_classes or (DEFAULT_0YTB_JSON.get('class') or YOUTUBE_CLASSES)
        result['filters'] = self.custom_filters or (DEFAULT_0YTB_JSON.get('filters') or CATEGORY_FILTERS)
        try:
            if self._live_on('live_cat', True):
                classes = list(result['class'] or [])
                if not any(str(c.get('type_id')) == 'live' for c in classes):
                    live_cls = {'type_id': 'live', 'type_name': '🔴 直播'}
                    # 默认插到「🎵音乐MV」正前方；ext 可配 live_cat_pos=first（第1位）/ last（末尾）
                    pos = str(self._live_cfg('live_cat_pos', 'music') or 'music').strip().lower()
                    music_idx = next((i for i, c in enumerate(classes)
                                      if str(c.get('type_id')) == 'music'), None)
                    if pos == 'first':
                        classes.insert(0, live_cls)
                    elif pos == 'last' or music_idx is None:
                        classes.append(live_cls)
                    else:
                        classes.insert(music_idx, live_cls)
                    result['class'] = classes
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        # 推荐页面默认直接呈现「音乐MV」栏目（YouTube 官方音乐频道 UC-9-kyTW8ZkZNDHQJ6FgpwQ 下的 VEVO / 迈克尔·杰克逊风格带剧情 MV）
        return self.categoryContent('music', 1, False, {})

    def categoryContent(self, cid, page, filter, ext):
        page = int(page) if page else 1
        filters = ext if isinstance(ext, dict) else {}

        # 🔴 直播分类：纯本地列表，不做搜索/去抖，秒出
        if str(cid) == 'live':
            items = self._live_vod_list((filters or {}).get('group') if isinstance(filters, dict) else '')
            return {'list': items, 'page': 1, 'pagecount': 1, 'limit': len(items), 'total': len(items)}

        # 分类防刷：TV 上下切分类会连发多次 categoryContent，逐个真去搜会造成频繁刷新/卡顿。
        # 仅在某分类停留 >= cat_debounce_sec（默认 2s）的请求才真正加载；停留期间被新的切换取代者返回空列表，
        # 让页面保持不动，彻底消除“切一下刷一屏”。仅对第 1 页去抖，翻页/搜索不受影响。
        if self._cat_debounce_on and page == 1 and not str(cid).startswith('CH__'):
            with self._cat_lock:
                self._cat_seq += 1
                my_seq = self._cat_seq
            time.sleep(self._cat_debounce_sec)
            with self._cat_lock:
                superseded = (my_seq != self._cat_seq)
            if superseded:
                debug_log('category debounce skip', {'cid': cid, 'seq': my_seq, 'latest': self._cat_seq})
                return {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}

                        # 频道主分类特殊处理：分频道主展示独立聚合卡片，最新发布排在第一个
        if cid == 'channel' or str(cid).startswith('CH__'):
            selected_filter = filters.get('tid') or ''
            ch_target = str(cid).replace('CH__', '').strip() if str(cid).startswith('CH__') else selected_filter

            # 如果用户选中了某一个特定频道主，直接展示该频道的最新视频列表（按发布时间严格倒序，最新发布排第1）
            if ch_target and ch_target not in ('全部', '') and not ch_target.startswith('LIST:'):
                clean_name = self._clean_channel_name(ch_target)
                # 100% 官方频道直达：直接从频道 /videos 获取该博主真实上传视频，顺序严格保真，第1个必为最新发布！
                exact_videos = self._fetch_channel_videos_exact(clean_name)
                if exact_videos:
                    videos = exact_videos
                    has_more = False
                else:
                    videos, has_more = self._search_youtube_page(clean_name, page, sort_by_date=True)

                if not exact_videos and videos:
                    videos.sort(key=lambda x: x.get('vod_pub_sec', 9999999999))
                if videos:
                    self._mark_channel_seen(clean_name, videos)
                    first_rem = videos[0].get('vod_remarks') or ''
                    if '【最新发布】' not in first_rem:
                        videos[0]['vod_remarks'] = f'【最新发布】{first_rem}'
                    if len(videos) > 1:
                        second_rem = videos[1].get('vod_remarks') or ''
                        if '【次新】' not in second_rem:
                            videos[1]['vod_remarks'] = f'【次新】{second_rem}'
                    for i in range(2, len(videos)):
                        r_rem = videos[i].get('vod_remarks') or ''
                        tag = f'【第{i+1}新】'
                        if tag not in r_rem:
                            videos[i]['vod_remarks'] = f'{tag}{r_rem}'
                return {'list': videos, 'page': page, 'pagecount': page + 1 if has_more else page, 'limit': len(videos), 'total': len(videos)}

            # 默认频道主主页（选全部）：展示各频道主的独立卡片，自动检测新更新并在图片与角标上显著提示
            channel_names = self._get_channel_list()
            self._trigger_bg_channels_check(channel_names)
            ch_state = self._load_channel_update_state()
            vod_list = []
            for name in channel_names:
                clean_n = self._clean_channel_name(name)
                entry = ch_state.get(clean_n) or {}
                has_upd, pub_text = self._is_channel_has_update(clean_n, entry)
                latest_vid = entry.get('latest_vid') or ''
                upd_flag = f'1_{latest_vid}' if has_upd else f'0_{latest_vid}'
                avatar = f'http://127.0.0.1:9978/proxy?do=py&type=ch_avatar&name={quote(name)}&upd={quote(upd_flag)}'
                if has_upd:
                    latest_t = (entry.get('latest_title') or '').strip()
                    short_t = (latest_t[:12] + '…') if len(latest_t) > 13 else latest_t
                    card_name = f'🔴 {name}（有新更新：{short_t}）' if short_t else f'🔴 {name}（有新作品更新）'
                    card_rem = f'🔥有更新 · {pub_text}' if pub_text else '🔥有新更新'
                else:
                    card_name = f'{name}（点击查看最新视频）'
                    card_rem = f'最新：{pub_text} · 倒序排第1' if pub_text else '频道主 · 最新发布排第1'
                vod_list.append({
                    'vod_id': f'CH__{name}',
                    'vod_name': card_name,
                    'vod_tag': 'folder',
                    'vod_pic': avatar,
                    'vod_remarks': card_rem,
                })
            return {'list': vod_list, 'page': page, 'pagecount': 1, 'limit': len(vod_list), 'total': len(vod_list)}

        query = self._build_category_keyword(cid, filters)
        is_live_cat = (self._normalize_category_id(cid) == 'live24h')
        videos, has_more = self._search_youtube_page(query, page, live_only=is_live_cat)
        if videos:
            videos.sort(key=lambda x: x.get('vod_pub_sec', 9999999999))
        # 音乐MV分类：在第 1 页顶部插入「超长音乐MV随机连播」入口卡片，点进去后台自动一部接一部随机超长 MV。
        if self._mv_mix_on and self._normalize_category_id(cid) == 'music' and page == 1:
            mix_card = {
                'vod_id': 'MVMIX__',
                'vod_name': '🎵 超长音乐MV随机连播（自动续播）',
                'vod_tag': 'folder',
                'vod_pic': 'http://127.0.0.1:9978/proxy?do=py&type=image&vid=' + (videos[0]['vod_id'] if videos else 'dQw4w9WgXcQ') + '&quality=hqdefault',
                'vod_remarks': '一部放完自动随机下一部 · 每天焕新',
            }
            videos = [mix_card] + (videos or [])
        return {'list': videos, 'page': page, 'pagecount': page + 1 if has_more else page, 'limit': len(videos), 'total': len(videos)}

    def searchContent(self, key, quick, pg=1):
        page = int(pg)
        videos, has_more = self._search_youtube_page(key, page)
        return {'list': videos, 'page': page, 'pagecount': page + 1 if has_more else page, 'limit': len(videos), 'total': len(videos)}

    def detailContent(self, did):
        raw_id = did[0] if isinstance(did, list) else str(did or '')

        # 🔴 直播频道
        if str(raw_id).startswith('LIVE__'):
            return self._live_detail(raw_id)

        # 超长音乐MV随机连播：聚合一批时长超长的音乐MV/演唱会，随机打乱后做成一个播放列表。
        # FongMi/TVBox 播完一集会自动跳下一集，配合随机顺序即“放完自动随机下一部超长MV”。
        if str(raw_id) == 'MVMIX__' or str(raw_id).startswith('MVMIX__'):
            return self._mvmix_detail()

        # 频道主聚合卡片点击进入：展示该频道全部最新视频，100% 严格官方时间轴：第1个必为最新发布，第2个必为次新，依次类推！
        if str(raw_id).startswith('CH__'):
            ch_name = str(raw_id).replace('CH__', '').strip()
            clean_name = self._clean_channel_name(ch_name)
            videos = self._fetch_channel_videos_exact(clean_name)
            if not videos:
                videos, _ = self._search_youtube_page(clean_name, page=1, sort_by_date=True)
                if videos:
                    videos.sort(key=lambda x: x.get('vod_pub_sec', 9999999999))
            if videos:
                self._mark_channel_seen(clean_name, videos)

            episodes_sabr = []
            for idx, v in enumerate(videos):
                vid = v['vod_id']
                v_title = self._safe_title(v['vod_name'])
                if idx == 0:
                    ep_prefix = '【最新发布】'
                elif idx == 1:
                    ep_prefix = '【次新】'
                else:
                    ep_prefix = f'【第{idx + 1}新】'
                ep_name = f'{ep_prefix} {v_title}'
                episodes_sabr.append(f'{ep_name}${vid}@sabr')

            latest_desc = f'最新发布：{videos[0]["vod_name"]}' if videos else '频道视频列表'
            first_vid = videos[0]['vod_id'] if videos else ''
            if first_vid:
                self._prewarm_async(first_vid, 'best')
                self._prewarm_comments_async(first_vid)
            sub_url = f'http://127.0.0.1:9978/proxy?do=py&type=sub&vid={first_vid}&format=vtt&ext=.vtt' if first_vid else ''
            vod = {
                'vod_id': raw_id,
                'vod_name': f'频道：{clean_name}',
                'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=ch_avatar&name={quote(clean_name)}&upd=0_{first_vid}',
                'vod_remarks': f'共 {len(videos)} 视频 · 官方上传倒序',
                'vod_content': f'【{clean_name}】{latest_desc}（官方上传倒序排列，已开启热门评论跑马灯与中文字幕）',
                'vod_sub': f'简体中文+🔥热评跑马灯#text/vtt#{sub_url}' if sub_url else '',
                'vod_play_from': 'SABR',
                'vod_play_url': '#'.join(episodes_sabr) if episodes_sabr else '暂无视频$none',
            }
            return {'list': [vod]}

        video_id = self.yt.extract_video_id(raw_id)
        title = self._get_video_title(video_id)
        safe_title = self._safe_title(title)
        sub_url = f'http://127.0.0.1:9978/proxy?do=py&type=sub&vid={video_id}&format=vtt&ext=.vtt'

        # 起播预热：详情页一打开就后台本地解析这个视频并预取热门评论，等用户按播放时缓存已就绪，起播秒开。
        self._prewarm_async(video_id, 'best')
        self._prewarm_comments_async(video_id)

        # 自动连播：把“本片 + 一批相关视频”做成选集列表放进 vod_play_url（复用同一份推荐列表，避免重复网络搜索）
        autonext_on = str(self.extendDict.get('autonext') or 'on').strip().lower() not in ('0', 'off', 'false', 'no')
        need_related = autonext_on or self._related_reco_on
        related = self._related_videos(title, video_id, limit=20) if need_related else []

        eps_sabr = [f'{safe_title}${video_id}@sabr']
        if autonext_on:
            for name, rvid in related:
                eps_sabr.append(f'{name}${rvid}@sabr')

        play_from = ['SABR']
        play_url = ['#'.join(eps_sabr)]

        # 备用线路：默认不启用（保持原行为）；ext 配 lines="sabr,dash,stable" 即额外暴露可切换线路
        _want_lines = str((self.extendDict or {}).get('lines') or '').strip()
        if _want_lines:
            _line_tags = {'dash': 'DASH 云直链', 'stable': '免卡直连(progressive)',
                          'progressive': '免卡直连(progressive)'}
            for _ln in [x.strip().lower() for x in _want_lines.split(',') if x.strip()]:
                _tag = _line_tags.get(_ln)
                if not _ln or _ln == 'sabr' or not _tag:
                    continue
                _eps = [f'{safe_title}${video_id}@{_ln}']
                if autonext_on:
                    _eps += [f'{name}${rvid}@{_ln}' for name, rvid in related]
                play_from.append(_tag)
                play_url.append('#'.join(_eps))
        # 小窗口选线旁的「关键词推荐」按钮：切过去即是按本片标题关键词推荐的一批同类视频
        if self._related_reco_on and related:
            reco_line = '#'.join([f'{name}${rvid}@sabr' for name, rvid in related])
            if reco_line:
                play_from.append('🔎 关键词推荐 (换线即换片)')
                play_url.append(reco_line)

        vod = {
            'vod_id': video_id,
            'vod_name': title,
            'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={video_id}&quality=hqdefault',
            'vod_remarks': '💬热评跑马灯 · 中文字幕 · 超清畅播',
            'vod_content': f'{title}（已开启顶部热门评论跑马灯、底部中文字幕与全片防卡引擎）',
            'vod_sub': f'简体中文+🔥热评跑马灯#text/vtt#{sub_url}',
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_url),
        }
        return {'list': [vod]}

    def _related_keyword(self, title):
        """从标题提炼一个用于相关推荐的搜索关键词：优先歌手/片名前段，去掉常见噪声词。"""
        t = html.unescape(str(title or '')).strip()
        if not t:
            return ''
        # 取第一个自然分隔段（-、|、《》、（）、空格前的主体），限制长度，避免整句超长搜索
        for sep in ('《', '》', '|', '-', '–', '—', '(', '（', '[', '【'):
            if sep in t:
                head = t.split(sep)[0].strip()
                if len(head) >= 2:
                    t = head
                    break
        t = re.sub(r'\b(official|mv|hd|4k|1080p|full|video|lyrics|audio|live)\b', '', t, flags=re.I)
        t = re.sub(r'\s+', ' ', t).strip()
        return t[:40]

    def _related_videos(self, title, cur_vid, limit=20):
        """按标题关键词搜一批相关视频，返回 [(安全标题, vid), ...]，用于自动连播/关键词推荐。

        修复“放同一首歌时推荐全是同一首”：
          1. 多页抓取扩大候选池，避免单页结果高度雷同；
          2. 严格排除当前视频 vid，并按标题去重（同名不同 vid 也视为重复）；
          3. 打散顺序，保证推荐的是同风格/同类型的不同曲目，而非重复同一首。
        """
        try:
            key = self._related_keyword(title)
            if not key:
                return []
            cur_name = self._safe_title(str(title or '')).strip().lower()
            out = []
            seen_vid = {cur_vid}
            seen_name = set()
            if cur_name:
                seen_name.add(cur_name)
            # 仅抓第 1 页（30 条结果已足够去重挑选 20 条推荐），避免连抓 3 页阻塞详情页与播放器线程
            for page in (1,):
                try:
                    videos, has_more = self._search_youtube_page(key, page)
                except Exception:
                    videos, has_more = [], False
                for v in (videos or []):
                    vid = v.get('vod_id')
                    if not vid or vid in seen_vid:
                        continue
                    name = self._safe_title(v.get('vod_name') or '')
                    nkey = name.strip().lower()
                    # 标题去重：同名（哪怕不同 vid）只保留一条，避免“同一首歌”的多个搬运版占满推荐
                    if not nkey or nkey in seen_name:
                        continue
                    seen_vid.add(vid)
                    seen_name.add(nkey)
                    out.append((name, vid))
                if len(out) >= limit * 2 or not has_more:
                    break
            # 打散后截断，保证每次推荐的是同类里的不同曲目
            random.shuffle(out)
            return out[:limit]
        except Exception as e:
            debug_log('related videos error', repr(e))
            return []

    def _build_related_line(self, title, cur_vid):
        """构造“关键词推荐”线路的 vod_play_url：按标题关键词搜一批同风格不同曲目做成可点播列表。"""
        eps = [f'{name}${vid}@sabr' for name, vid in self._related_videos(title, cur_vid, limit=20)]
        return '#'.join(eps) if eps else ''

    def _prewarm_async(self, video_id, quality='best'):
        if not getattr(self, '_prewarm_on', True) or not video_id:
            return
        if video_id in self._prewarmed:
            return
        self._prewarmed.add(video_id)
        def _work():
            try:
                # 纯本地后台预热：详情页打开时仅预取 YouTubeLite.extract 元数据与热门评论，
                # 不再预拉 single progresive 块（避免占用 2MB 代理带宽抢占 SABR 视频流）
                self.yt.extract(video_id, force_refresh=False)
                self._prewarm_comments_async(video_id)
                debug_log('prewarm local extract done', {'vid': video_id})
            except Exception as e:
                debug_log('prewarm error', {'vid': video_id, 'error': repr(e)})
        try:
            threading.Thread(target=_work, daemon=True).start()
        except Exception:
            pass

    def _mvmix_detail(self):
        """聚合一批 VEVO 剧情 MV / 迈克尔·杰克逊风格音乐短片与演唱会，随机打乱做成播放列表，播完自动跳下一部。"""
        try:
            min_sec = int(self.extendDict.get('mv_min_sec') or 240)  # 默认 >=4 分钟（涵盖电影级叙事短片 MV 与合集）
        except Exception:
            min_sec = 240
        seeds = self.extendDict.get('mv_mix_keywords')
        if isinstance(seeds, str):
            seeds = [x.strip() for x in seeds.split(',') if x.strip()]
        if not isinstance(seeds, list) or not seeds:
            seeds = [
                'Michael Jackson Official Video Short Film Vevo',
                'Vevo cinematic story official music video mini movie',
                'Michael Jackson Thriller Beat It Smooth Criminal Remember The Time Ghosts',
                'Vevo most viewed official music video HD',
                '周杰伦 剧情 电影感 官方完整版 MV',
            ]
        # 每天用日期做随机种子，保证“每天焕新”，同一天内顺序稳定
        day_seed = int(time.strftime('%Y%m%d'))
        rnd = random.Random(day_seed)
        rnd.shuffle(seeds)

        collected = []
        seen = set()
        for kw in seeds:
            try:
                videos, _ = self._search_youtube_page(kw, 1)
            except Exception:
                videos = []
            for v in (videos or []):
                vid = v.get('vod_id')
                if not vid or vid in seen:
                    continue
                if int(v.get('vod_dur_sec') or 0) < min_sec:
                    continue
                seen.add(vid)
                collected.append(v)
            if len(collected) >= 60:
                break
        # 没有拿到足够超长视频时放宽时长门槛兜底，避免空列表
        if len(collected) < 5:
            for kw in seeds:
                try:
                    videos, _ = self._search_youtube_page(kw, 1)
                except Exception:
                    videos = []
                for v in (videos or []):
                    vid = v.get('vod_id')
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    collected.append(v)
                if len(collected) >= 30:
                    break

        rnd.shuffle(collected)
        eps_sabr = []
        for v in collected:
            vid = v['vod_id']
            name = self._safe_title(v.get('vod_name') or '')
            dur_min = int((v.get('vod_dur_sec') or 0) // 60)
            tag = f'[{dur_min}分] ' if dur_min else ''
            eps_sabr.append(f'{tag}{name}${vid}@sabr')

        if not eps_sabr:
            return {'list': [{
                'vod_id': 'MVMIX__',
                'vod_name': '超长音乐MV随机连播',
                'vod_remarks': '暂未取到超长MV，请稍后再试',
                'vod_play_from': 'SABR',
                'vod_play_url': '暂无$none',
            }]}

        first_vid = collected[0]['vod_id']
        vod = {
            'vod_id': 'MVMIX__',
            'vod_name': '🎵 超长音乐MV随机连播',
            'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={first_vid}&quality=hqdefault',
            'vod_remarks': f'{len(eps_sabr)} 部超长MV · 播完自动随机下一部 · 每天焕新',
            'vod_content': '自动连播：一部超长音乐MV放完，TVBox 会自动播放下一部（已随机打乱，每天焕新）。',
            'vod_play_from': 'SABR',
            'vod_play_url': '#'.join(eps_sabr),
        }
        return {'list': [vod]}

    def playerContent(self, flag, pid, vipFlags):
        debug_log('playerContent ENTRY', {'flag': flag, 'pid': str(pid)})
        if isinstance(pid, list):
            pid = pid[0] if pid else ''
        pid_str = str(pid or '')

        # 🔴 直播：直接返回本地代理 m3u8 地址（含 @handle 频道也能解析，故须在 '@' 拆分前拦截）
        if 'LIVE__' in pid_str:
            live_src = pid_str.split('LIVE__', 1)[1].split('$')[0]
            return {
                'parse': 0, 'jx': 0,
                'url': self._live_play_url(live_src),
                'format': self.LIVE_MIME,
                'mediaType': self.LIVE_MIME,
                'header': self.header,
            }

        raw_pid = pid_str.split('$')[-1]
        quality = '1080p'
        if '@' in raw_pid:
            video_id, quality = raw_pid.rsplit('@', 1)
        else:
            video_id = raw_pid
        # 线路选择：SABR = 主力专线，DASH = 158 云直链兜底专线；各自内部自动取最佳画质。
        line = 'sabr'
        if quality == 'dash':
            line = 'dash'
        # [修复] 免卡专线死代码：原逻辑把 stable/progressive 也归一成 'best'，
        # 使第 4925 行「免卡专线」分支永远进不去，@stable/@progressive 实际等同 @sabr。
        # 现放行二者，并显式跳过 SABR 主力线，让「免卡直连(progressive)」真正可切换。
        if quality in ('stable', 'progressive'):
            line = 'none'
        if quality in ('', 'sabr', 'dash', '1080p', '720p'):
            quality = 'best'
        video_id = self.yt.extract_video_id(video_id) if hasattr(self, 'yt') and hasattr(self.yt, 'extract_video_id') else Spider._clean_video_id(video_id)

        # 保持本地解析流自洽匹配，杜绝中途异步热替换导致的解码崩溃与频繁换线

        # 1. 直播专线
        if quality == 'live':
            try:
                data = self.yt.extract_live(video_id)
                hls_url = data.get('hls_url') or ''
                if hls_url:
                    play_url = self._cache_hls_url(hls_url, video_id, 'master') if self.hls_proxy_enabled else hls_url
                    debug_log('player live stream active', {'vid': video_id, 'line': line, 'quality': quality, 'play_url': play_url})
                    return {
                        'parse': 0, 'jx': 0,
                        'url': play_url,
                        'format': 'application/vnd.apple.mpegurl',
                        'mediaType': 'application/vnd.apple.mpegurl',
                        'header': self._hls_headers(hls_url, 'master'),
                    }
            except Exception as e:
                debug_log('player live error', repr(e))

        # 2. 纯本地 1080p SABR 主力专线（结合 VISIONOS / ANDROID_VR 1080p WebM Super-Chunk 零服务器全片畅播）
        if line == 'sabr':
            try:
                ext = self.yt.extract(video_id)
                # 直播流禁止进入静态点播 SABR MPD（否则 duration=0 且分片序号为直播实时递增导致 404），直接走本地 HLS 直播流代理
                if ext.get('is_live') or ext.get('hls_url'):
                    hls_url = ext.get('hls_url') or ''
                    if not hls_url:
                        live_data = self.yt.extract_live(video_id)
                        hls_url = live_data.get('hls_url') or ''
                    if hls_url:
                        play_url = self._cache_hls_url(hls_url, video_id, 'master') if self.hls_proxy_enabled else hls_url
                        debug_log('sabr line detected live stream, routing to hls', {'vid': video_id, 'play_url': play_url})
                        return {
                            'parse': 0, 'jx': 0,
                            'url': play_url,
                            'format': 'application/vnd.apple.mpegurl',
                            'mediaType': 'application/vnd.apple.mpegurl',
                            'header': self._hls_headers(hls_url, 'master'),
                        }
                sabr_quality = 'best' if quality == 'best' else quality
                sabr_data = self._new_sabr_play_data(video_id, ext, sabr_quality)
                if not sabr_data and quality != 'best':
                    sabr_data = self._new_sabr_play_data(video_id, ext, 'best')
                if sabr_data and sabr_data.get('video_item') and sabr_data.get('audio_item'):
                    debug_log('sabr primary line active', {
                        'vid': video_id, 'quality': quality,
                        'client': sabr_data['video_item'].get('client'),
                        'v_itag': sabr_data['video_item'].get('itag'),
                        'a_itag': sabr_data['audio_item'].get('itag'),
                    })
                    res = {
                        'parse': 0, 'jx': 0,
                        'url': f'http://127.0.0.1:9978/proxy?do=py&type=sabr_mpd&vid={video_id}&ext=.mpd',
                        'format': 'application/dash+xml',
                        'mediaType': 'application/dash+xml',
                        'header': self.header,
                    }
                    return self._attach_default_zh_subs(res, ext, video_id)
                debug_log('sabr webm unavailable, fallback to local dash/progressive', {'vid': video_id, 'quality': quality})
            except Exception as se:
                debug_log('sabr primary failed, fallback to local dash/progressive', repr(se))

        # 3. 兜底点播：提取本地视频流数据（涵盖 1080P、720P、480P、360P 等所有视轨）
        data = None
        try:
            data = self.yt.extract(video_id)
            if data.get('is_live') or data.get('hls_url'):
                hls_url = data.get('hls_url') or ''
                if not hls_url:
                    live_data = self.yt.extract_live(video_id)
                    hls_url = live_data.get('hls_url') or ''
                if hls_url:
                    play_url = self._cache_hls_url(hls_url, video_id, 'master') if self.hls_proxy_enabled else hls_url
                    debug_log('fallback detected live stream, routing to hls', {'vid': video_id, 'play_url': play_url})
                    return {
                        'parse': 0, 'jx': 0,
                        'url': play_url,
                        'format': 'application/vnd.apple.mpegurl',
                        'mediaType': 'application/vnd.apple.mpegurl',
                        'header': self._hls_headers(hls_url, 'master'),
                    }

            formats = data.get('formats') or []

            # 3. 免卡专线（stable / progressive）：直走 Progressive 单流（_proxy_single），零 403、全片畅播
            if quality in ('stable', 'progressive'):
                prog = self.yt.choose_progressive(formats)
                if prog and prog.get('url'):
                    headers = self.header.copy()
                    headers.update(prog.get('headers') or {})
                    headers['User-Agent'] = 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip'
                    self.setCache(f'yt_single_{video_id}', {
                        'url': prog['url'],
                        'headers': headers,
                        'item': prog,
                        'expires': time.time() + 21600,
                    })
                    debug_log('return stable progressive stream', {'video_id': video_id, 'itag': prog.get('itag'), 'quality': quality})
                    res = {
                        'parse': 0, 'jx': 0,
                        'url': f'http://127.0.0.1:9978/proxy?do=py&type=single&vid={video_id}&ext=.mp4',
                        'format': 'video/mp4',
                        'mediaType': 'video/mp4',
                        'header': headers,
                    }
                    return self._attach_default_zh_subs(res, data, video_id)

            # 4. 高清自适应专线（best / 1080p / 720p）：走 DASH MPD 代理，包含真实 1080P、720P 等多视轨！
            cache_data = self._rebuild_play_cache(video_id, quality)
            if not cache_data and quality != 'best':
                cache_data = self._rebuild_play_cache(video_id, 'best')
            if cache_data:
                res = {
                    'parse': 0, 'jx': 0,
                    'url': f'http://127.0.0.1:9978/proxy?do=py&type=mpd&vid={video_id}&quality={quality}&ext=.mpd',
                    'format': 'application/dash+xml',
                    'mediaType': 'application/dash+xml',
                    'header': self.header,
                }
                return self._attach_default_zh_subs(res, data, video_id)

            # 兜底降级到 single 流
            prog = self.yt.choose_progressive(formats)
            if prog and prog.get('url'):
                headers = self.header.copy()
                headers.update(prog.get('headers') or {})
                self.setCache(f'yt_single_{video_id}', {
                    'url': prog['url'],
                    'headers': headers,
                    'item': prog,
                    'expires': time.time() + 21600,
                })
                res = {
                    'parse': 0, 'jx': 0,
                    'url': f'http://127.0.0.1:9978/proxy?do=py&type=single&vid={video_id}&ext=.mp4',
                    'format': 'video/mp4',
                    'mediaType': 'video/mp4',
                    'header': headers,
                }
                return self._attach_default_zh_subs(res, data, video_id)

            raise Exception('无法提取可播放视频格式')
        except Exception as e:
            debug_log('playerContent error', repr(e))
            print(f'[YouTubeLite] 解析失败: {e}')
            return {'parse': 0, 'jx': 0, 'url': ''}

    def _cache_hls_url(self, target_url, video_id='', kind='media'):
        # 使用基于 target_url 的确定性 key 并延长有效期至 6 小时，防止直播定时刷新子 m3u8 时 key 过期或无限膨胀
        key = hashlib.md5(f"{kind}:{target_url}".encode('utf-8')).hexdigest()[:20]
        if len(self.hls_url_cache) > 1500:
            now_ts = time.time()
            expired_keys = [k for k, v in list(self.hls_url_cache.items()) if v.get('expires', 0) < now_ts]
            for k in expired_keys:
                self.hls_url_cache.pop(k, None)
            if len(self.hls_url_cache) > 1500:
                media_keys = [k for k, v in list(self.hls_url_cache.items()) if v.get('kind') == 'media']
                for k in media_keys[:600]:
                    self.hls_url_cache.pop(k, None)
        self.hls_url_cache[key] = {
            'url': target_url,
            'video_id': video_id,
            'kind': kind,
            'expires': time.time() + 21600,
        }
        ext_sfx = '.m3u8' if kind in ('master', 'playlist') else '.ts'
        return f'http://127.0.0.1:9978/proxy?do=py&type=hls&key={quote(key)}&ext={ext_sfx}'

    def _hls_headers(self, target_url, kind=None):
        if kind == 'media_retry':
            return {
                'User-Agent': 'com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip',
                'Accept': '*/*',
                'Connection': 'close',
            }
        headers = self.header.copy()
        headers['Accept'] = '*/*'
        headers['Connection'] = 'close'
        if kind in ('master', 'playlist'):
            headers['Origin'] = 'https://www.youtube.com'
            headers['Referer'] = 'https://www.youtube.com/'
        elif kind == 'media':
            headers['User-Agent'] = 'com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip'
            headers.pop('Origin', None)
            headers.pop('Referer', None)
        return headers

    def _rewrite_m3u8(self, text, base_url, video_id=''):
        lines = (text or '').splitlines()
        # 若是 Master M3U8（含多清晰度 #EXT-X-STREAM-INF），优先将 720P 排在首位（兼顾高清与秒开，避免 1080P 单分片 2.5MB 超时或默认首项 144P 模糊），随后按 1080P -> 480P 排列供 ExoPlayer 自适应
        if any(l.strip().startswith('#EXT-X-STREAM-INF') for l in lines):
            header_lines = []
            variants = []
            i = 0
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith('#EXT-X-STREAM-INF'):
                    res_m = re.search(r'RESOLUTION=(\d+)x(\d+)', stripped)
                    height = int(res_m.group(2)) if res_m else 0
                    bw_m = re.search(r'BANDWIDTH=(\d+)', stripped)
                    bw = int(bw_m.group(1)) if bw_m else 0
                    tag_line = self._rewrite_m3u8_tag(lines[i], base_url, video_id)
                    uri_line = ''
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j].strip()
                        if not nxt:
                            j += 1
                            continue
                        if nxt.startswith('#'):
                            tag_line += '\n' + self._rewrite_m3u8_tag(lines[j], base_url, video_id)
                            j += 1
                            continue
                        absolute = urljoin(base_url, nxt)
                        kind = 'playlist' if nxt.endswith('.m3u8') or '/hls_playlist/' in nxt else 'media'
                        uri_line = self._cache_hls_url(absolute, video_id, kind)
                        break
                    if uri_line:
                        variants.append((height, bw, tag_line, uri_line))
                    i = j + 1
                    continue
                else:
                    if stripped.startswith('#'):
                        header_lines.append(self._rewrite_m3u8_tag(lines[i], base_url, video_id))
                    elif stripped:
                        header_lines.append(lines[i])
                    i += 1
            if variants:
                def _var_sort_key(v):
                    h, b = v[0], v[1]
                    tier = 2 if h == 720 else (1 if h == 1080 else 0)
                    return (tier, h, b)
                variants.sort(key=_var_sort_key, reverse=True)
                out = list(header_lines)
                for _, _, t_line, u_line in variants:
                    out.append(t_line)
                    out.append(u_line)
                return '\n'.join(out) + '\n'

        # 若是实时直播子 M3U8（不含 #EXT-X-ENDLIST），过滤直播广告插入标记，并在分片过多时仅保留最后 12 个最新实时分片并同步递增 #EXT-X-MEDIA-SEQUENCE
        lines = [l for l in lines if not l.strip().startswith('#EXT-X-DATERANGE:') and not l.strip().startswith('#EXT-X-CUEPOINT:')]
        is_live_media_pl = not any(l.strip().startswith('#EXT-X-ENDLIST') for l in lines)
        if is_live_media_pl:
            top_headers = []
            segments = []
            cur_seg_tags = []
            in_segments = False
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith('#EXTINF') or stripped.startswith('#EXT-X-PROGRAM-DATE-TIME') or stripped.startswith('#EXT-X-DISCONTINUITY'):
                    in_segments = True
                    cur_seg_tags.append(line)
                elif stripped.startswith('#'):
                    if in_segments:
                        cur_seg_tags.append(line)
                    else:
                        top_headers.append(line)
                else:
                    segments.append((cur_seg_tags, stripped))
                    cur_seg_tags = []
            if len(segments) > 12:
                dropped = segments[:-12]
                kept = segments[-12:]
                drop_count = len(dropped)
                drop_disc = sum(1 for tags, _ in dropped if any(t.strip().startswith('#EXT-X-DISCONTINUITY') for t in tags))
                new_headers = []
                for h_line in top_headers:
                    hs = h_line.strip()
                    if hs.startswith('#EXT-X-MEDIA-SEQUENCE:'):
                        try:
                            seq_num = int(hs.split(':', 1)[1].strip())
                            new_headers.append(f'#EXT-X-MEDIA-SEQUENCE:{seq_num + drop_count}')
                            continue
                        except Exception:
                            pass
                    elif hs.startswith('#EXT-X-DISCONTINUITY-SEQUENCE:') and drop_disc > 0:
                        try:
                            d_num = int(hs.split(':', 1)[1].strip())
                            new_headers.append(f'#EXT-X-DISCONTINUITY-SEQUENCE:{d_num + drop_disc}')
                            continue
                        except Exception:
                            pass
                    new_headers.append(self._rewrite_m3u8_tag(h_line, base_url, video_id))
                out = list(new_headers)
                for tags, uri_raw in kept:
                    for t_line in tags:
                        out.append(self._rewrite_m3u8_tag(t_line, base_url, video_id))
                    absolute = urljoin(base_url, uri_raw)
                    kind = 'playlist' if uri_raw.endswith('.m3u8') or '/hls_playlist/' in uri_raw else 'media'
                    out.append(self._cache_hls_url(absolute, video_id, kind))
                return '\n'.join(out) + '\n'

        output = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                output.append(line)
                continue
            if stripped.startswith('#'):
                output.append(self._rewrite_m3u8_tag(line, base_url, video_id))
                continue
            absolute = urljoin(base_url, stripped)
            kind = 'playlist' if stripped.endswith('.m3u8') or '/hls_playlist/' in stripped else 'media'
            output.append(self._cache_hls_url(absolute, video_id, kind))
        return '\n'.join(output) + '\n'

    def _rewrite_m3u8_tag(self, line, base_url, video_id=''):
        def replace_uri(match):
            raw_url = match.group(1)
            absolute = urljoin(base_url, raw_url)
            kind = 'playlist' if raw_url.endswith('.m3u8') or '/hls_playlist/' in raw_url else 'media'
            proxied = self._cache_hls_url(absolute, video_id, kind)
            return f'URI="{proxied}"'
        return re.sub(r'URI="([^"]+)"', replace_uri, line)

    def _parse_hls_master(self, hls_url):
        try:
            r = self.session.get(hls_url, headers=self.header, timeout=10)
            lines = [x.strip() for x in (r.text or '').splitlines()]
            variants = []
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF'):
                    res_m = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                    height = int(res_m.group(2)) if res_m else 0
                    bw_m = re.search(r'BANDWIDTH=(\d+)', line)
                    bw = int(bw_m.group(1)) if bw_m else 0
                    for next_line in lines[i+1:]:
                        if not next_line or next_line.startswith('#'):
                            continue
                        sub_url = urljoin(hls_url, next_line)
                        variants.append({'height': height, 'bitrate': bw, 'url': sub_url})
                        break
            return sorted(variants, key=lambda x: (x['height'], x['bitrate']), reverse=True)
        except Exception:
            return []

    def _proxy_hls(self, params):
        key = params.get('key') or ''
        item = self.hls_url_cache.get(key)
        if not item or item.get('expires', 0) < time.time():
            debug_log('proxy hls cache miss', {'key': key})
            return [404, 'text/plain', 'HLS 缓存已过期']
        target_url = item.get('url') or ''
        kind = item.get('kind') or 'media'
        # 剥离 YouTube HLS TS 分片 URL 中的 /keepalive/yes，防止长连接挂起导致读取分片超时阻塞
        if kind == 'media' and '/keepalive/yes' in target_url:
            target_url = target_url.replace('/keepalive/yes', '')
        try:
            headers = self._hls_headers(target_url, kind)
            proxies = dict(self.session.proxies or {})
            response = requests.get(target_url, headers=headers, proxies=proxies, timeout=(6, 25))
            if kind == 'media' and response.status_code == 403:
                retry_headers = self._hls_headers(target_url, 'media_retry')
                response.close()
                response = requests.get(target_url, headers=retry_headers, proxies=proxies, timeout=(6, 25))
            content_type = response.headers.get('content-type') or ''
            is_m3u8 = (
                kind in ('master', 'playlist')
                or 'mpegurl' in content_type.lower()
                or target_url.split('?')[0].endswith('.m3u8')
                or '/hls_playlist/' in target_url
                or response.content[:7] == b'#EXTM3U'
            )
            if is_m3u8:
                text = response.content.decode('utf-8', errors='replace')
                rewritten = self._rewrite_m3u8(text, target_url, item.get('video_id') or '')
                debug_log('proxy hls m3u8 ok', {'kind': kind, 'vid': item.get('video_id'), 'status': response.status_code, 'lines': len(rewritten.splitlines())})
                return [response.status_code, 'application/vnd.apple.mpegurl', rewritten, {'Content-Type': 'application/vnd.apple.mpegurl', 'Cache-Control': 'no-cache'}]
            body = response.content
            resp_headers = {
                'Content-Type': content_type or 'video/MP2T',
                'Cache-Control': 'no-cache',
                'Content-Length': str(len(body)),
            }
            return [response.status_code, content_type or 'video/MP2T', body, resp_headers]
        except Exception as e:
            debug_log('proxy hls error', {'kind': kind, 'err': repr(e)})
            return [500, 'text/plain', f'HLS 代理失败: {str(e)}']

    def localProxy(self, params):
        if params.get('do') != 'py':
            return None
        if params.get('type') == 'mpd':
            return self._proxy_mpd(params)
        if params.get('type') == 'media':
            return self._proxy_media(params)
        if params.get('type') == 'single':
            return self._proxy_single(params)
        if params.get('type') == 'hls':
            return self._proxy_hls(params)
        if params.get('type') == 'live':
            return self._proxy_live(params)
        if params.get('type') == 'image':
            return self._proxy_image(params)
        if params.get('type') == 'sub':
            return self._proxy_sub(params)
        if params.get('type') == 'ch_pic':
            return self._proxy_ch_pic(params)
        if params.get('type') == 'ch_avatar':
            return self._proxy_ch_avatar(params)
        if params.get('type') == 'sabr_mpd':
            return self._proxy_sabr_mpd(params)
        if params.get('type') == 'sabr':
            return self._proxy_sabr(params)
        return None

    def _proxy_image(self, params):
        """通过主 Session 获取缩略图，继承与 API/播放流相同的代理设置。"""
        vid = str(params.get('vid') or '').strip()
        if not re.fullmatch(r'[0-9A-Za-z_-]{11}', vid):
            return [400, 'text/plain', '无效的 video id']

        requested = str(params.get('quality') or 'hqdefault').strip().lower()
        allowed = ('maxresdefault', 'sddefault', 'hqdefault', 'mqdefault', 'default')
        if requested not in allowed:
            requested = 'hqdefault'
        qualities = []
        for quality in (requested, 'hqdefault', 'mqdefault', 'default'):
            if quality not in qualities:
                qualities.append(quality)

        headers = self.header.copy()
        headers.update({
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Referer': f'https://www.youtube.com/watch?v={vid}',
        })
        last_status = None
        for quality in qualities:
            image_url = f'https://i.ytimg.com/vi/{vid}/{quality}.jpg'
            response = None
            try:
                response = self.session.get(
                    image_url, headers=headers, timeout=10, allow_redirects=True)
                last_status = response.status_code
                content_type = response.headers.get('content-type', '').split(';', 1)[0]
                if response.status_code == 200 and response.content and content_type.startswith('image/'):
                    body = bytes(response.content)
                    debug_log('proxy image response', {
                        'vid': vid, 'quality': quality, 'status': response.status_code,
                        'content_type': content_type, 'content_length': len(body),
                    })
                    return [200, content_type or 'image/jpeg', body, {
                        'Cache-Control': 'public, max-age=86400',
                        'Content-Length': str(len(body)),
                    }]
                debug_log('proxy image candidate failed', {
                    'vid': vid, 'quality': quality, 'status': response.status_code,
                    'content_type': content_type,
                })
            except Exception as e:
                debug_log('proxy image request error', {
                    'vid': vid, 'quality': quality, 'error': repr(e),
                })
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass
        return [404, 'text/plain', f'图片不存在或代理请求失败 ({last_status})']

    @staticmethod
    def _direct_audio_key(item):
        return (
            str((item or {}).get('client') or ''),
            int((item or {}).get('itag') or 0),
            str((item or {}).get('codecs') or '').lower(),
        )

    @staticmethod
    def _direct_audio_signature(item):
        return (
            int((item or {}).get('itag') or 0),
            ((item or {}).get('mimeType') or '').split(';')[0].lower(),
            str((item or {}).get('codecs') or '').lower(),
        )

    def _direct_audio_candidates(self, formats, failed_keys=None, required_signature=None):
        failed = set(tuple(x) for x in (failed_keys or []))
        audios = [
            x for x in (formats or [])
            if x.get('protocol') != 'sabr' and x.get('url')
            and x.get('acodec') != 'none' and x.get('vcodec') == 'none'
            and self._direct_audio_key(x) not in failed
        ]
        risky_markers = ('ec-3', 'ec3', 'eac3', 'ac-3', 'ac3', 'dts', 'truehd')
        safe = [x for x in audios if not any(m in ((x.get('codecs') or '') + ' ' + (x.get('mimeType') or '')).lower() for m in risky_markers)]
        # EC-3/AC-3 等只在没有任何常规音轨时兜底，避免高码率覆盖 AAC。
        audios = safe or audios
        if required_signature is not None:
            audios = [x for x in audios if self._direct_audio_signature(x) == tuple(required_signature)]
        client_order = {'VISIONOS': 7, 'ANDROID_VR': 6, 'IOS': 5, 'MWEB': 4, 'ANDROID': 3, 'WEB_INITIAL': 2, 'WEB': 1}

        def codec_rank(item):
            text = ((item.get('codecs') or '') + ' ' + (item.get('mimeType') or '')).lower()
            if 'mp4a' in text or 'aac' in text:
                return 5
            if 'opus' in text:
                return 4
            if 'vorbis' in text:
                return 3
            if 'mp3' in text:
                return 2
            return 1

        audios.sort(key=lambda x: (
            self.yt._audio_lang_priority(x),
            1 if int(x.get('itag') or 0) == 140 else 0,
            1 if str(x.get('client') or '').upper() in ('VISIONOS', 'IOS') else 0,
            codec_rank(x),
            client_order.get(str(x.get('client') or '').upper(), 0),
            int(x.get('bitrate') or 0),
        ), reverse=True)
        # 同一客户端/itag/编码只保留一条；URL 变化由强制刷新负责。
        result = []
        seen = set()
        for item in audios:
            key = self._direct_audio_key(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        debug_log('direct audio candidates', {
            'failed': [list(x) for x in failed],
            'items': [{
                'client': x.get('client'), 'itag': x.get('itag'),
                'codecs': x.get('codecs'), 'bitrate': x.get('bitrate'),
            } for x in result[:10]],
        })
        return result

    def _choose_direct_audio(self, formats, failed_keys=None, required_signature=None):
        candidates = self._direct_audio_candidates(formats, failed_keys, required_signature)
        if not candidates and formats:
            # 保护机制：如果所有候选客户端被拉黑导致空列表，强制清空黑名单重新全选
            candidates = self._direct_audio_candidates(formats, None, required_signature)
        selected = candidates[0] if candidates else None
        debug_log('direct audio selected', {
            'client': selected.get('client') if selected else None,
            'itag': selected.get('itag') if selected else None,
            'codecs': selected.get('codecs') if selected else None,
            'candidate_count': len(candidates),
        })
        return selected, candidates

    def _next_cached_direct_audio(self, data, failed_item):
        failed_keys = [tuple(x) for x in (data.get('failed_audio_keys') or [])]
        failed_key = self._direct_audio_key(failed_item)
        if failed_key not in failed_keys:
            failed_keys.append(failed_key)
        primary_signature = self._direct_audio_signature(data.get('audio_item') or failed_item)
        candidates = data.get('audio_candidates') or []
        # MPD 已下发，运行时只切换相同 itag/容器/编码，保证 SegmentBase 兼容。
        remaining = [
            x for x in candidates
            if self._direct_audio_key(x) not in failed_keys
            and self._direct_audio_signature(x) == primary_signature
        ]
        data['failed_audio_keys'] = [list(x) for x in failed_keys]
        if not remaining:
            return None
        selected = remaining[0]
        data['audio_item'] = selected
        data['audio_url'] = selected.get('url')
        debug_log('direct audio cache failover', {
            'from': list(failed_key), 'to': list(self._direct_audio_key(selected)),
            'remaining_same_format': len(remaining),
        })
        return selected

    def _rebuild_play_cache(self, vid, quality, force_refresh=False, failed_audio_keys=None, required_audio_signature=None):
        # 纯本地 DASH 缓存构建：当部分老视频/推荐视频无 WebM 轨时，使用本地 ANDROID_VR / ANDROID / IOS 的 MP4 轨构建
        # 2. 兜底回源到本地爬虫提取
        try:
            data = self.yt.extract(vid, force_refresh=force_refresh)
            select_quality = quality if quality in ('8k', '8k_hdr', '4k', '2k', '1080p', '720p', '480p') else 'best'
            all_tracks = self.yt.choose_video_tracks(data['formats'], select_quality)
            wanted_name = 'HDR' if quality in ('hdr', '8k_hdr') else 'SDR'
            video_tracks = [x for x in all_tracks if x.get('track_name') == wanted_name]
            if not video_tracks and all_tracks and quality not in ('8k', '8k_hdr'):
                video_tracks = [all_tracks[0]]
            audio, audio_candidates = self._choose_direct_audio(
                data['formats'], failed_audio_keys, required_audio_signature)
            if not video_tracks or not audio:
                debug_log('proxy cache rebuild empty', {
                    'vid': vid, 'quality': quality,
                    'failed_audio_keys': failed_audio_keys or [],
                })
                return None

            # DASH MPD 严格保持由本地解析出的 initRange 与 indexRange 匹配的视频流，杜绝跨源错位

            cache_key = f'yt_{vid}_{quality}'
            cache_val = {
                'video_tracks': video_tracks,
                'video_url': video_tracks[0]['url'],
                'audio_url': audio['url'],
                'video_item': video_tracks[0],
                'audio_item': audio,
                'audio_candidates': audio_candidates,
                'failed_audio_keys': list(failed_audio_keys or []),
                'duration': data.get('duration') or 0,
                'expires': time.time() + 21600,
            }
            self.setCache(cache_key, cache_val)
            debug_log('proxy cache rebuilt', {
                'vid': vid, 'quality': quality,
                'video_itag': video_tracks[0].get('itag'),
                'audio_itag': audio.get('itag'), 'audio_client': audio.get('client'),
                'audio_codecs': audio.get('codecs'),
            })
            return cache_val
        except Exception as e:
            debug_log('proxy cache rebuild error', {'vid': vid, 'quality': quality, 'error': repr(e)})
            return None

    def _rebuild_single_cache(self, vid, force_refresh=False, ext_data=None, failed_url=None):
        if not hasattr(self, '_single_refresh_lock') or self._single_refresh_lock is None:
            self._single_refresh_lock = threading.RLock()
        with self._single_refresh_lock:
            if force_refresh and failed_url:
                cached = self.getCache(f'yt_single_{vid}')
                if cached and cached.get('url') and cached.get('url') != failed_url:
                    return cached
            try:
                data = ext_data if (ext_data and not force_refresh) else self.yt.extract(vid, force_refresh=force_refresh)
                formats = data.get('formats') or []
                prog = self.yt.choose_progressive(formats)
                if not (prog and prog.get('url')) and not force_refresh:
                    data = self.yt.extract(vid, force_refresh=True)
                    formats = data.get('formats') or []
                    prog = self.yt.choose_progressive(formats)
                if prog and prog.get('url'):
                    headers = self.header.copy()
                    headers.update(prog.get('headers') or {})
                    headers['User-Agent'] = 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip'
                    prev = self.getCache(f'yt_single_{vid}') or {}
                    total_len = int(prog.get('contentLength') or prev.get('content_length') or 0)
                    cache_data = {
                        'url': prog['url'],
                        'headers': headers,
                        'item': prog,
                        'content_length': total_len,
                        'expires': time.time() + 21600,
                    }
                    self.setCache(f'yt_single_{vid}', cache_data)
                    return cache_data
            except Exception as e:
                debug_log('rebuild single cache error', {'vid': vid, 'error': repr(e)})
            return None

    def _fetch_single_block(self, vid, block_idx):
        BLOCK_SIZE = 524288  # 512KB 对齐超级分片（约 17 秒视频，首包极快且 100% 稳定）
        if not hasattr(self, '_single_block_lock') or self._single_block_lock is None:
            self._single_block_lock = threading.Lock()
            self._single_block_cache = {}
            self._single_block_events = {}
        key = (vid, int(block_idx))
        with self._single_block_lock:
            if key in self._single_block_cache:
                val = self._single_block_cache.pop(key)
                self._single_block_cache[key] = val
                return val
            ev = self._single_block_events.get(key)
            if ev is not None:
                is_leader = False
            else:
                ev = threading.Event()
                self._single_block_events[key] = ev
                is_leader = True

        if not is_leader:
            ev.wait(timeout=22)
            with self._single_block_lock:
                return self._single_block_cache.get(key)

        try:
            data = self.getCache(f'yt_single_{vid}')
            if not data or not data.get('url'):
                data = self._rebuild_single_cache(vid)
            if not data or not data.get('url'):
                return None

            total_length = int(data.get('content_length') or ((data.get('item') or {}).get('contentLength')) or 0)
            b_start = block_idx * BLOCK_SIZE
            if total_length > 0 and b_start >= total_length:
                return (b'', total_length, 'video/mp4')
            b_end = min(b_start + BLOCK_SIZE - 1, total_length - 1) if total_length > 0 else (b_start + BLOCK_SIZE - 1)

            for attempt in range(3):
                target_url = data.get('url')
                headers = {
                    'User-Agent': 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip',
                    'Accept': '*/*',
                    'Accept-Encoding': 'identity',
                    'Range': f'bytes={b_start}-{b_end}',
                    'Connection': 'close',
                }
                r = None
                try:
                    r = requests.get(target_url, headers=headers, proxies=dict(self.session.proxies or {}), timeout=15, allow_redirects=True)
                    if r.status_code in (403, 404):
                        r.close()
                        r = None
                        debug_log('single super-chunk status refresh', {'vid': vid, 'block': block_idx, 'status': 403})
                        rebuilt = self._rebuild_single_cache(vid, force_refresh=True, failed_url=target_url)
                        if rebuilt and rebuilt.get('url'):
                            data = rebuilt
                        continue
                    if r.status_code in (200, 206):
                        body = r.content
                        ctype = r.headers.get('content-type') or 'video/mp4'
                        cr = r.headers.get('content-range') or ''
                        if '/' in cr:
                            try:
                                parsed_total = int(cr.split('/')[-1].strip())
                                if parsed_total > 0:
                                    total_length = parsed_total
                                    data['content_length'] = total_length
                                    self.setCache(f'yt_single_{vid}', data)
                            except Exception:
                                pass
                        r.close()
                        r = None
                        res_tuple = (body, total_length, ctype)
                        with self._single_block_lock:
                            self._single_block_cache[key] = res_tuple
                            while len(self._single_block_cache) > 16:
                                oldest_k = next(iter(self._single_block_cache))
                                if oldest_k == key:
                                    break
                                self._single_block_cache.pop(oldest_k, None)
                        return res_tuple
                except Exception as e:
                    debug_log('single super-chunk fetch error', {'vid': vid, 'block': block_idx, 'attempt': attempt, 'error': repr(e)})
                    time.sleep(0.2 * (attempt + 1))
                finally:
                    if r is not None:
                        try:
                            r.close()
                        except Exception:
                            pass
            return None
        finally:
            with self._single_block_lock:
                ev_done = self._single_block_events.pop(key, None)
                if ev_done:
                    ev_done.set()

    def _prefetch_single_blocks(self, vid, block_indices):
        if not block_indices:
            return
        def _bg():
            for b_idx in block_indices:
                if b_idx < 0:
                    continue
                if hasattr(self, '_single_block_cache') and (vid, int(b_idx)) in self._single_block_cache:
                    continue
                res = self._fetch_single_block(vid, int(b_idx))
                if not res or not res[0]:
                    break
        try:
            threading.Thread(target=_bg, daemon=True).start()
        except Exception:
            pass

    def _proxy_single(self, params):
        vid = params.get('vid')
        data = self.getCache(f'yt_single_{vid}') if vid else None
        if not data:
            data = self._rebuild_single_cache(vid) if vid else None
        if not data or not data.get('url'):
            return [404, 'text/plain', '播放缓存已过期或不存在']

        BLOCK_SIZE = 524288  # 512KB 对齐超级分片
        total_length = int(data.get('content_length') or ((data.get('item') or {}).get('contentLength')) or 0)

        range_header = str(params.get('range') or params.get('Range') or '').strip()
        start = 0
        end = None
        has_explicit_end = False
        if range_header.startswith('bytes='):
            raw_r = range_header.replace('bytes=', '').strip()
            parts = raw_r.split('-')
            if parts[0].isdigit():
                start = int(parts[0])
            if len(parts) > 1 and parts[1].isdigit():
                end = int(parts[1])
                has_explicit_end = True

        if end is None:
            if total_length > 0:
                end = min(start + BLOCK_SIZE - 1, total_length - 1)
            else:
                end = start + BLOCK_SIZE - 1
        else:
            if total_length > 0:
                end = min(end, total_length - 1)
            if (end - start + 1) > BLOCK_SIZE:
                end = start + BLOCK_SIZE - 1

        if total_length > 0 and start >= total_length:
            return [416, 'text/plain', b'', {'Content-Range': f'bytes */{total_length}'}]

        b_start_idx = start // BLOCK_SIZE
        b_end_idx = end // BLOCK_SIZE
        out_parts = []
        content_type = 'video/mp4'

        b_idx = b_start_idx
        while b_idx <= b_end_idx:
            blk = self._fetch_single_block(vid, b_idx)
            if not blk or blk[0] is None:
                # 容灾：如果该块获取失败，但之前已收集到部分数据，则按部分数据返回，避免直接 502 崩溃
                if out_parts:
                    break
                # 单独重试一次强制刷新
                rebuilt = self._rebuild_single_cache(vid, force_refresh=True)
                if rebuilt and rebuilt.get('url'):
                    blk = self._fetch_single_block(vid, b_idx)
                if not blk or blk[0] is None:
                    return [502, 'text/plain', b'Single block fetch failed', {'Content-Type': 'text/plain'}]
            b_bytes, blk_total, ctype = blk
            if blk_total > 0:
                total_length = blk_total
            if ctype:
                content_type = ctype

            # 关键防崩溃机制：超长视频（如 30~60 分钟以上）的 MP4 moov 索引头可达 600KB~2MB（大于单块 512KB）。
            # ExoPlayer Mp4Extractor 读取 moov 时使用单次 readFully，若首个响应在 moov 中途截断会直接抛 EOFException 导致崩溃。
            # 因此当读取首块 (b_idx == 0) 时自动检测 MP4 顶层 moov 原子大小，若 moov 跨越当前 end，则自动扩展 b_end_idx 完整覆盖整个 moov + 首个 mdat 块！
            if b_idx == 0 and start < BLOCK_SIZE and len(b_bytes) >= 16:
                moov_end = 0
                atom_off = 0
                while atom_off + 8 <= min(len(b_bytes), 4096):
                    atom_sz = int.from_bytes(b_bytes[atom_off:atom_off + 4], 'big')
                    atom_tp = b_bytes[atom_off + 4:atom_off + 8]
                    if atom_sz == 1 and atom_off + 16 <= len(b_bytes):
                        atom_sz = int.from_bytes(b_bytes[atom_off + 8:atom_off + 16], 'big')
                    elif atom_sz < 8:
                        break
                    if atom_tp == b'moov':
                        moov_end = atom_off + atom_sz
                        break
                    if atom_tp == b'mdat':
                        break
                    atom_off += atom_sz
                if moov_end > 0 and start < moov_end and not has_explicit_end:
                    needed_blocks = min(8, ((moov_end + 65535) // BLOCK_SIZE) + 1)
                    needed_end = needed_blocks * BLOCK_SIZE - 1
                    if total_length > 0:
                        needed_end = min(needed_end, total_length - 1)
                    if needed_end > end:
                        end = needed_end
                        b_end_idx = end // BLOCK_SIZE
                        debug_log('single moov auto-extended', {'vid': vid, 'moov_end': moov_end, 'new_end': end, 'blocks': b_end_idx + 1})

            blk_byte_start = b_idx * BLOCK_SIZE
            slice_from = max(0, start - blk_byte_start)
            slice_to = min(len(b_bytes), end - blk_byte_start + 1)
            if slice_to > slice_from:
                out_parts.append(b_bytes[slice_from:slice_to])
            b_idx += 1

        body = b''.join(out_parts)
        actual_end = start + len(body) - 1 if body else start

        # 触发后台滑窗预取后续 2 个 512KB 块，保证顺序播放与 Seek 后续缓冲 0 等待
        if total_length == 0 or (b_end_idx + 1) * BLOCK_SIZE < total_length:
            self._prefetch_single_blocks(vid, [b_end_idx + 1, b_end_idx + 2])

        resp_headers = {
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-cache',
            'Content-Length': str(len(body)),
        }
        if total_length > 0:
            resp_headers['Content-Range'] = f'bytes {start}-{actual_end}/{total_length}'
        elif range_header:
            resp_headers['Content-Range'] = f'bytes {start}-{actual_end}/*'

        status_code = 206 if range_header else 200
        return [status_code, content_type, body, resp_headers]

    def _proxy_mpd(self, params):
        vid = params.get('vid')
        quality = params.get('quality') or 'best'
        data = self.getCache(f'yt_{vid}_{quality}') if vid else None
        if not data and quality != 'best':
            data = self.getCache(f'yt_{vid}_best') if vid else None
        if not data:
            debug_log('proxy mpd cache miss, rebuilding', {'vid': vid, 'quality': quality})
            data = self._rebuild_play_cache(vid, quality) if vid else None
        if not data and quality != 'best':
            data = self._rebuild_play_cache(vid, 'best') if vid else None
        if not data:
            return [404, 'text/plain', '视频缓存已过期或不存在']
        audio_url = data.get('audio_url')
        duration = data.get('duration') or 0
        video_tracks = data.get('video_tracks') or [data.get('video_item') or {}]
        audio_item = data.get('audio_item') or {}
        # DASH 高峰/弱网流畅度：默认锁 720P 单轨（用户要求“使用 DASH 直接锁定 720 画质”）。
        # 原因：多轨自适应在高峰期会抢上 1080P，后端带宽 ~78KB/s 撑不住 → 缓冲区见底卡顿。
        # 锁 720 单轨后码率需求砍半，缓冲水位稳。可用 ext 的 dash_lock_720=0 关闭恢复自适应。
        try:
            lock_720 = str(self.extendDict.get('dash_lock_720', '0')).lower() not in ('0', 'false', 'off', 'no')
        except Exception:
            lock_720 = False
        if lock_720 and video_tracks:
            _valid = [t for t in video_tracks if int(t.get('height') or 0) > 0]
            if _valid:
                _le720 = [t for t in _valid if int(t.get('height') or 0) <= 720]
                if _le720:
                    # 取 ≤720 中最高的（通常就是 720），锁成单轨
                    _pick = max(_le720, key=lambda t: int(t.get('height') or 0))
                else:
                    # 没有 ≤720 的轨，退而取最低画质那条，避免强推高码率
                    _pick = min(_valid, key=lambda t: int(t.get('height') or 0))
                video_tracks = [_pick]
                debug_log('dash lock 720', {'vid': vid, 'picked_itag': _pick.get('itag'), 'picked_height': _pick.get('height')})
        media_base = f'http://127.0.0.1:9978/proxy?do=py&type=media&vid={vid}&quality={quality}'
        direct_segments = (str(self.extendDict.get('seg') or 'proxy').lower() == 'direct')
        duration_pt = f"PT{int(duration or 0)}S"
        # 流畅度微调：配合 _proxy_media 的 1MB 对齐块内存缓存与后台 3MB 滑窗预取，
        # 首块 1MB 已包含 init + sidx + 前 2~3 个 5s 分片，minBufferTime 设为 12s 即可快速起播且全程零缓冲。
        try:
            min_buf = float(self.extendDict.get('min_buffer_sec') or 12.0)
        except Exception:
            min_buf = 12.0
        try:
            pres_delay = float(self.extendDict.get('pres_delay_sec') or 6.0)
        except Exception:
            pres_delay = 6.0
        mpd = f'''<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="{duration_pt}" minBufferTime="PT{min_buf:.1f}S" suggestedPresentationDelay="PT{pres_delay:.1f}S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">
  <Period id="1" start="PT0S">
'''
        # NOTE: 每条视轨独立为一个 AdaptationSet contentType="video"，
        # 首条（默认 1080P）带 Role value="main"，使 ExoPlayer 视轨菜单仅单选当前画质，
        # 且点击切换其他画质时立即释放旧缓冲并重拉新 itag 分片。
        for idx_v, item in enumerate(video_tracks):
            init_range = item.get('initRange') or {}
            index_range = item.get('indexRange') or {}
            v_mime = html.escape((item.get('mimeType') or 'video/mp4').split(';')[0])
            base_url = item.get('url') if direct_segments else media_base + f"&track=video&itag={item.get('itag')}"
            role_tag = '\n      <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>' if idx_v == 0 else ''
            mpd += f'''    <AdaptationSet id="{idx_v + 1}" contentType="video" mimeType="{v_mime}" startWithSAP="1" segmentAlignment="true" scanType="progressive">{role_tag}
      <Representation id="v{item.get('itag', 1)}" bandwidth="{item.get('bitrate', 1000000)}" codecs="{html.escape(item.get('codecs') or '')}" height="{item.get('height', 0)}" width="{item.get('width', 0)}">
        <BaseURL>{html.escape(base_url)}</BaseURL>
        <SegmentBase indexRange="{index_range.get('start', '0')}-{index_range.get('end', '0')}"><Initialization range="{init_range.get('start', '0')}-{init_range.get('end', '0')}"/></SegmentBase>
      </Representation>
    </AdaptationSet>
'''
        if audio_url:
            audio_init = audio_item.get('initRange') or {}
            audio_index = audio_item.get('indexRange') or {}
            audio_base = audio_url if direct_segments else media_base + '&track=audio'
            mpd += f'''    <AdaptationSet mimeType="{html.escape((audio_item.get('mimeType') or 'audio/mp4').split(';')[0])}" startWithSAP="1" segmentAlignment="true" lang="und">
      <Representation id="audio" bandwidth="{audio_item.get('bitrate', 128000)}" codecs="{html.escape(audio_item.get('codecs') or '')}" audioSamplingRate="44100">
        <BaseURL>{html.escape(audio_base)}</BaseURL>
        <SegmentBase indexRange="{audio_index.get('start', '0')}-{audio_index.get('end', '0')}"><Initialization range="{audio_init.get('start', '0')}-{audio_init.get('end', '0')}"/></SegmentBase>
      </Representation>
    </AdaptationSet>
'''
        # 注入中文字幕轨，确保 ExoPlayer 播放 DASH MPD 时能原生识别并加载字幕
        sub_proxy_mpd = f'http://127.0.0.1:9978/proxy?do=py&amp;type=sub&amp;vid={vid}&amp;format=vtt'
        mpd += f'''    <AdaptationSet contentType="text" mimeType="text/vtt" lang="zh">
      <Representation id="sub-zh" bandwidth="256">
        <BaseURL>{html.escape(sub_proxy_mpd)}</BaseURL>
      </Representation>
    </AdaptationSet>
'''
        mpd += '  </Period>\n</MPD>'
        debug_log('proxy mpd tracks', {'vid': vid, 'quality': quality, 'tracks': [{'name': x.get('track_name'), 'itag': x.get('itag')} for x in video_tracks], 'audio': audio_item.get('itag'), 'direct': direct_segments, 'duration': duration_pt})
        return [200, 'application/dash+xml', mpd]

    def _proxy_media(self, params):
        vid = params.get('vid')
        quality = params.get('quality') or 'best'
        track = params.get('track')
        cache_key = f'yt_{vid}_{quality}'
        data = self.getCache(cache_key) if vid else None
        if not data and quality != 'best':
            data = self.getCache(f'yt_{vid}_best') if vid else None
            if data:
                cache_key = f'yt_{vid}_best'
        if not data and vid and track in ('video', 'audio'):
            debug_log('proxy media cache miss, rebuilding', {'vid': vid, 'quality': quality, 'track': track})
            data = self._rebuild_play_cache(vid, quality)
            if not data and quality != 'best':
                data = self._rebuild_play_cache(vid, 'best')
                if data:
                    cache_key = f'yt_{vid}_best'
        if not data or track not in ('video', 'audio'):
            return [404, 'text/plain', b'Media not found', {'Content-Type': 'text/plain'}]

        def select_item(cache):
            if track == 'video':
                wanted_itag = str(params.get('itag') or '')
                tracks = cache.get('video_tracks') or [cache.get('video_item') or {}]
                item = next((x for x in tracks if str(x.get('itag')) == wanted_itag), tracks[0] if tracks else {})
                return item, item.get('url')
            item = cache.get('audio_item') or {}
            return item, cache.get('audio_url') or item.get('url')

        media_item, target_url = select_item(data)
        if not target_url:
            return [404, 'text/plain', b'Target stream not found', {'Content-Type': 'text/plain'}]

        try:
            BIG_WIN = int(float(self.extendDict.get('big_win_kb') or 8192) * 1024) - 1
        except Exception:
            BIG_WIN = 8388607
        range_header = str(params.get('range') or params.get('Range') or '').strip()
        start = 0
        has_end = False
        if range_header.startswith('bytes='):
            parts = range_header.replace('bytes=', '').split('-')
            start = int(parts[0]) if parts[0].isdigit() else 0
            has_end = len(parts) > 1 and parts[1].isdigit()
            if has_end:
                end = int(parts[1])
                computed_range = f'bytes={start}-{end}'
            else:
                end = start + BIG_WIN
                computed_range = f'bytes={start}-{end}'
        else:
            end = BIG_WIN
            computed_range = f'bytes=0-{BIG_WIN}'

        def do_fetch(url, item, req_range):
            fetch_session = getattr(self, 'media_session', None) or self.session
            if not getattr(self, '_media_adapter_mounted', False):
                try:
                    adapter = requests.adapters.HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=2)
                    fetch_session.mount('https://', adapter)
                    fetch_session.mount('http://', adapter)
                    self._media_adapter_mounted = True
                except Exception:
                    pass
            client_ua_map = {
                'ANDROID_VR': 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip',
                'ANDROID': 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip',
                'IOS': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)',
                'MWEB': 'Mozilla/5.0 (iPad; CPU OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1,gzip(gfe)',
                'WEB': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            item_client = (item or {}).get('client') or 'IOS'
            item_headers = (item or {}).get('headers') or {}
            ua = item_headers.get('User-Agent') or client_ua_map.get(item_client) or client_ua_map['ANDROID']
            headers = {
                'User-Agent': ua,
                'Range': req_range,
                'Accept': '*/*',
            }

            last_err = None
            for attempt in range(3):
                try:
                    resp = fetch_session.get(url, headers=headers, stream=True, timeout=20, allow_redirects=True)
                    if resp.status_code < 500:
                        return resp
                except Exception as ex:
                    last_err = ex
                    try:
                        # 重建本地媒体会话并保留代理配置
                        self.media_session = requests.Session()
                        self.media_session.trust_env = True
                        self.media_session.proxies = dict(self.session.proxies or {})
                        fetch_session = self.media_session
                    except Exception:
                        pass
                    time.sleep(0.3 * (attempt + 1))

        # 纯本地媒体分片拉取（配额耗尽 403 时自动强制刷新本地直链续传）

        try:
            r = do_fetch(target_url, media_item, computed_range)
            if r.status_code in (403, 404):
                debug_log('proxy media retry on status', {
                    'vid': vid, 'quality': quality, 'track': track,
                    'status': r.status_code, 'range': computed_range,
                })
                try:
                    r.close()
                except Exception:
                    pass
                r = None
                recovered = False
                if track == 'audio':
                    next_audio = self._next_cached_direct_audio(data, media_item)
                    if next_audio:
                        media_item = next_audio
                        target_url = next_audio.get('url')
                        r = do_fetch(target_url, media_item, computed_range)
                        if r.status_code not in (403, 404):
                            recovered = True
                elif track == 'video':
                    tracks = data.get('video_tracks') or []
                    cur_itag = str(media_item.get('itag'))
                    other_tracks = [x for x in tracks if str(x.get('itag')) != cur_itag and x.get('url')]
                    if other_tracks:
                        media_item = other_tracks[0]
                        target_url = media_item.get('url')
                        r = do_fetch(target_url, media_item, computed_range)
                        if r.status_code not in (403, 404):
                            recovered = True
                if not recovered:
                    # 避免跨源热替换导致 range 字节错位
                    pass

                if not recovered:
                    try:
                        # 快速刷新本地直链 URL
                        rebuilt = self._rebuild_play_cache(vid, quality, force_refresh=True)
                        if rebuilt:
                            data = rebuilt
                            media_item, target_url = select_item(data)
                            if target_url:
                                r = do_fetch(target_url, media_item, computed_range)
                    except Exception as re_err:
                        debug_log('proxy media fast recovery failed', repr(re_err))
                if r is None or r.status_code in (403, 404):
                    if r is not None:
                        try:
                            r.close()
                        except Exception:
                            pass
                    return [403, 'text/plain', b'Stream expired', {'Content-Type': 'text/plain'}]

            content_type = r.headers.get('content-type', 'application/octet-stream')
            resp_headers = {'Content-Type': content_type, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-cache'}
            if r.headers.get('content-range'):
                resp_headers['Content-Range'] = r.headers.get('content-range')
            if r.headers.get('content-length'):
                resp_headers['Content-Length'] = r.headers.get('content-length')
            status_code = r.status_code
            body = r.content
            r.close()
            return [status_code, content_type, body, resp_headers]
        except Exception as e:
            debug_log('proxy media error', {
                'vid': vid, 'track': track, 'range': computed_range, 'error': repr(e),
            })
            return [500, 'text/plain', str(e).encode('utf-8'), {'Content-Type': 'text/plain'}]

    def _normalize_category_id(self, cid):
        raw = str(cid or '').strip()
        return CATEGORY_ALIASES.get(raw, raw)

    def _normalize_filter_term(self, value):
        if isinstance(value, (list, tuple)):
            return ' '.join([self._normalize_filter_term(item) for item in value if item])
        if isinstance(value, dict):
            return ' '.join([self._normalize_filter_term(item) for item in value.values() if item])
        return re.sub(r'\s+', ' ', str(value or '')).strip()[:180]

    def _default_filter_query_from_json(self, cid):
        """从 0ytb.json 的 filters 中取「全部」默认搜索词，保证自定义分类优先。"""
        custom = getattr(self, 'custom_filters', None) or {}
        groups = custom.get(str(cid or '').strip()) or []
        if not isinstance(groups, list):
            return ''
        for group in groups:
            for item in (group.get('value') or []):
                if (item.get('n') or '') == '全部' and item.get('v'):
                    return self._normalize_filter_term(item.get('v'))
        # 无「全部」时取该分类第一个非空 value
        for group in groups:
            for item in (group.get('value') or []):
                if item.get('v'):
                    return self._normalize_filter_term(item.get('v'))
        return ''

    def _build_category_keyword(self, cid, filters=None):
        category_id = self._normalize_category_id(cid)
        terms = []
        # 用户筛选优先；否则 0ytb.json 默认词；最后才回退内置 CATEGORY_QUERY
        user_terms = []
        if isinstance(filters, dict):
            for value in filters.values():
                term = self._normalize_filter_term(value)
                if term and term not in ('全部',):
                    user_terms.append(term)
        if user_terms:
            terms.extend(user_terms)
        else:
            json_default = self._default_filter_query_from_json(cid)
            if json_default:
                terms.append(json_default)
            else:
                base = CATEGORY_QUERY.get(category_id) or CATEGORY_QUERY.get(str(cid or '').strip()) or ''
                if base:
                    terms.append(base)
                elif category_id and category_id not in ('channel',):
                    terms.append(str(category_id))
        seen = set()
        output = []
        for term in terms:
            term = term.strip()
            if term and term not in seen:
                seen.add(term)
                output.append(term)
        return ' '.join(output)

    def _search_cache_key(self, key):
        return re.sub(r'\s+', ' ', str(key or '')).strip().lower()

    def _search_youtube(self, key):
        videos, _ = self._search_youtube_page(key, 1)
        return videos

    def _search_youtube_page(self, key, page=1, sort_by_date=False, live_only=False):
        page = max(1, int(page or 1))
        cache_key = f'{self._search_cache_key(key)}_{sort_by_date}_{live_only}'
        session = self.search_page_cache.get(cache_key)
        if page == 1 or not session:
            session = self._fetch_search_first_page(key, sort_by_date=sort_by_date, live_only=live_only)
            self.search_page_cache[cache_key] = session
        while len(session.get('pages', [])) < page and session.get('next'):
            data = self._fetch_search_continuation(session)
            videos = self._extract_videos_from_api(data, 30)
            session.setdefault('pages', []).append(videos)
            session['next'] = self._extract_continuation_token(data)
        pages = session.get('pages', [])
        videos = pages[page - 1] if len(pages) >= page else []
        has_more = bool(session.get('next')) or len(pages) > page
        return videos, has_more

    def _fetch_search_first_page(self, key, sort_by_date=False, live_only=False):
        # 优先使用 Innertube 官方搜索 API：纯 JSON、响应极快；live_only 使用 EgJAAQ== 过滤正在进行的实时直播
        url = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
        search_params = "EgJAAQ%3D%3D" if live_only else ("CAISAhAB" if sort_by_date else "")
        if live_only:
            search_params = "EgJAAQ=="
        payload = {
            "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240310.01.00", "hl": "zh-CN", "gl": "US"}},
            "query": str(key or ""),
            "params": search_params
        }
        headers = self.header.copy()
        headers.update({
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": "2.20240310.01.00",
            "Connection": "close",
        })
        for attempt in range(5):
            try:
                r = requests.post(url, json=payload, headers=headers, proxies=dict(self.session.proxies or {}), timeout=12)
                if r.status_code == 200:
                    data = r.json()
                    videos = self._extract_videos_from_api(data, 30)
                    if (sort_by_date or live_only) and not videos:
                        # 降级：部分中文关键词带过滤参数会返回空列表，此时平滑回退到标准相关度搜索
                        payload_fallback = payload.copy()
                        payload_fallback["params"] = ""
                        try:
                            r2 = requests.post(url, json=payload_fallback, headers=headers, proxies=dict(self.session.proxies or {}), timeout=12)
                            if r2.status_code == 200:
                                data2 = r2.json()
                                videos2 = self._extract_videos_from_api(data2, 30)
                                if videos2:
                                    videos = videos2
                                    data = data2
                        except Exception:
                            pass
                    return {
                        "key": key,
                        "api_key": "",
                        "context": payload["context"],
                        "client_name": "WEB",
                        "client_version": "2.20240310.01.00",
                        "referer": "https://www.youtube.com/",
                        "pages": [videos],
                        "next": self._extract_continuation_token(data),
                    }
            except Exception as e:
                debug_log("fetch search first page retry", repr(e))
                time.sleep(0.8 * (attempt + 1))
        return {"key": key, "pages": [[]], "next": None}

    def _fetch_search_continuation(self, session):
        token = session.get('next')
        api_key = session.get('api_key')
        if not token or not api_key:
            return {}
        url = f'https://www.youtube.com/youtubei/v1/search?key={quote(api_key)}'
        headers = self.header.copy()
        headers.update({
            'Content-Type': 'application/json',
            'Origin': 'https://www.youtube.com',
            'Referer': session.get('referer') or 'https://www.youtube.com/',
            'X-YouTube-Client-Name': str(self.yt._client_name_id(session.get('client_name'))),
            'X-YouTube-Client-Version': session.get('client_version') or '2.20240310.01.00',
        })
        payload = {'context': session.get('context') or {}, 'continuation': token}
        r = self.session.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def _extract_continuation_token(self, data):
        tokens = []
        def scan(obj):
            if isinstance(obj, dict):
                endpoint = obj.get('continuationEndpoint') or {}
                token = endpoint.get('continuationCommand', {}).get('token')
                if token:
                    tokens.append(token)
                renderer = obj.get('continuationItemRenderer') or {}
                token = renderer.get('continuationEndpoint', {}).get('continuationCommand', {}).get('token')
                if token:
                    tokens.append(token)
                for value in obj.values():
                    scan(value)
            elif isinstance(obj, list):
                for value in obj:
                    scan(value)
        scan(data)
        return tokens[0] if tokens else ''

    def _extract_videos_fixed(self, html_str, limit=30):
        data = None
        match = re.search(r'var ytInitialData = (\{.*?\});', html_str)
        if match:
            try:
                data = json.loads(match.group(1))
            except Exception:
                data = None
        if not data:
            return []
        return self._extract_videos_from_api(data, limit)

    def _extract_videos_from_api(self, data, limit=30):
        videos = []
        seen = set()
        def scan(obj):
            if len(videos) >= limit:
                return
            if isinstance(obj, dict):
                for key in ('videoRenderer', 'compactVideoRenderer', 'gridVideoRenderer', 'reelItemRenderer'):
                    if key in obj:
                        item = self._parse_renderer(obj[key])
                        if item and item['vod_id'] not in seen:
                            seen.add(item['vod_id'])
                            videos.append(item)
                if 'lockupViewModel' in obj and isinstance(obj['lockupViewModel'], dict):
                    lvm = obj['lockupViewModel']
                    if not self._is_members_only_node(lvm):
                        vid = lvm.get('contentId')
                        m_vm = lvm.get('metadata', {}).get('lockupMetadataViewModel', {})
                        title = m_vm.get('title', {}).get('content')
                        if vid and title and re.fullmatch(r'[0-9A-Za-z_-]{11}', str(vid)) and vid not in seen and not self._is_members_only_node(title):
                            meta_rows = m_vm.get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
                            row_texts = []
                            for row in meta_rows:
                                for part in row.get('metadataParts', []):
                                    txt = (part.get('text') or {}).get('content')
                                    if txt:
                                        row_texts.append(txt)
                            remarks = ' · '.join(row_texts)
                            pub_sec = 8888888888
                            for rt in reversed(row_texts):
                                cand_sec = self._parse_relative_time_to_seconds(rt)
                                if cand_sec < 8888888888:
                                    pub_sec = cand_sec
                                    break
                            seen.add(vid)
                            videos.append({
                                'vod_id': vid,
                                'vod_name': html.unescape(title),
                                'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={vid}&quality=hqdefault',
                                'vod_remarks': remarks or 'YouTube',
                                'vod_author': row_texts[0] if row_texts else '',
                                'vod_pub_sec': pub_sec,
                                'vod_dur_sec': 0,
                            })
                for value in obj.values():
                    scan(value)
            elif isinstance(obj, list):
                for value in obj:
                    scan(value)
        scan(data)
        return videos[:limit]

    def _parse_renderer(self, renderer):
        try:
            if renderer.get('upcomingEventData') or self._is_members_only_node(renderer):
                return None
            vid = renderer.get('videoId')
            if not vid:
                nav = renderer.get('navigationEndpoint') or {}
                vid = (nav.get('watchEndpoint') or {}).get('videoId')
            if not vid:
                return None
            title_obj = renderer.get('title') or renderer.get('headline') or {}
            title = title_obj.get('simpleText') or ''.join([x.get('text', '') for x in title_obj.get('runs', [])]) or 'YouTube Video'
            dur = (renderer.get('lengthText') or {}).get('simpleText') or ''
            dur_sec = self._dur_text_to_seconds(dur)
            pub_obj = renderer.get('publishedTimeText') or {}
            pub = pub_obj.get('simpleText') or ''.join([x.get('text', '') for x in pub_obj.get('runs', [])]) or ''
            byline = renderer.get('ownerText') or renderer.get('shortBylineText') or renderer.get('longBylineText') or {}
            author = byline.get('simpleText') or ''.join([x.get('text', '') for x in byline.get('runs', [])]) or ''
            is_live_item = False
            for b in (renderer.get('badges') or []) + (renderer.get('thumbnailOverlays') or []):
                b_str = json.dumps(b, ensure_ascii=False)
                if 'BADGE_STYLE_TYPE_LIVE_NOW' in b_str or '"LIVE"' in b_str or '"直播"' in b_str or '正在直播' in b_str:
                    is_live_item = True
                    break
            vc_obj = renderer.get('viewCountText') or renderer.get('shortViewCountText') or {}
            vc_text = vc_obj.get('simpleText') or ''.join([x.get('text', '') for x in vc_obj.get('runs', [])]) or ''
            if '正在观看' in vc_text or 'watching' in vc_text.lower():
                is_live_item = True
            if is_live_item and not dur:
                pub = f'🔴正在直播 {vc_text}'.strip()
                pub_sec = 0
            else:
                pub_sec = self._parse_relative_time_to_seconds(pub)
            remarks = f'{pub} · {dur}' if pub and dur else (pub or dur or 'YouTube')
            return {
                'vod_id': vid,
                'vod_name': html.unescape(title),
                'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={vid}&quality=hqdefault',
                'vod_remarks': remarks,
                'vod_author': author,
                'vod_pub_sec': pub_sec,
                'vod_dur_sec': dur_sec,
            }
        except Exception:
            return None

    @staticmethod
    def _dur_text_to_seconds(text):
        """把 YouTube lengthText（如 '1:23:45'、'12:30'）解析为秒；解析失败返回 0。"""
        s = str(text or '').strip()
        if not s or ':' not in s:
            return 0
        try:
            parts = [int(x) for x in s.split(':')]
        except Exception:
            return 0
        total = 0
        for p in parts:
            total = total * 60 + p
        return total

    def _get_video_title(self, vid):
        try:
            r = self.session.get(f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json', timeout=5)
            return r.json().get('title') or vid
        except Exception:
            return vid

    def _safe_title(self, title):
        if not title:
            return 'video'
        return re.sub(r'[#$@%&!?*|\\/:<>]', ' ', title)[:60]

    def _seconds_to_iso_duration(self, seconds):
        seconds = float(seconds or 0)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds - hours * 3600 - minutes * 60
        parts = []
        if hours:
            parts.append(f'{hours}H')
        if minutes:
            parts.append(f'{minutes}M')
        parts.append(f'{secs:.3f}S')
        return 'PT' + ''.join(parts)

    def destroy(self):
        if hasattr(self, 'session') and self.session:
            try:
                self.session.close()
            except Exception:
                pass
        if hasattr(self, 'media_session') and self.media_session:
            try:
                self.media_session.close()
            except Exception:
                pass
    def _sabr_client_priority(self):
        configured = self.extendDict.get('sabr_clients') if hasattr(self, 'extendDict') else None
        if isinstance(configured, str):
            configured = [x.strip().upper() for x in configured.split(',') if x.strip()]
        if not isinstance(configured, (list, tuple)):
            # 优先使用免 GVS Po-Token 且无 60s/Range 限制的 VISIONOS 与 ANDROID_VR 原生客户端
            configured = ['VISIONOS', 'ANDROID_VR', 'ANDROID', 'IOS']
        seen = set()
        return [str(x).upper() for x in configured if x and not (str(x).upper() in seen or seen.add(str(x).upper()))]

    def _sabr_quality_videos(self, formats, quality='best'):
        bad_itags = {337, 401}
        configured = self.extendDict.get('sabr_skip_itags') if hasattr(self, 'extendDict') else None
        for value in configured or []:
            if str(value).isdigit():
                bad_itags.add(int(value))
        allowed_clients = set(self._sabr_client_priority())
        videos = [
            x for x in (formats or [])
            if x.get('protocol') == 'sabr'
            and x.get('vcodec') != 'none' and x.get('acodec') == 'none'
            and int(x.get('itag') or 0) not in bad_itags
            and str(x.get('client') or '').upper() in allowed_clients
        ]
        if quality in ('8k', '8k_hdr'):
            videos = [x for x in videos if int(x.get('height') or 0) >= 4320]
        elif quality == '4k':
            videos = [x for x in videos if 2160 <= int(x.get('height') or 0) < 4320]
        elif quality == '2k':
            videos = [x for x in videos if 1440 <= int(x.get('height') or 0) < 2160]
        elif quality == '1080p':
            videos = [x for x in videos if 1000 <= int(x.get('height') or 0) < 1440]
        # 默认限速 1080P（用户要求 SABR 默认播 1080P）：sabr_max_height 默认 1080，
        # ext 里设 sabr_max_height=2160 可放开 4K。472MB 的 4K WebM 直链读配额
        # 撑不住（09-30 idx313 第 3 次 Range 必读 403），1080 轨实测连读全 206。
        try:
            _maxh = int(self.extendDict.get('sabr_max_height') or 1080)
        except Exception:
            _maxh = 1080
        _clamped = [x for x in videos if int(x.get('height') or 0) <= _maxh]
        if _clamped:
            videos = _clamped
        # A 方案：SABR 线锁 WebM/VP9 视频，为“越 70s 直链 Range 续播”统一 WebM 容器
        # （直链按 Cues 切 cluster，绕开 MP4 裸 mdat 无 moof 不能当独立段的坑）。
        # sabr_webm_only=0 可关闭恢复原自适应。
        try:
            _webm_only = str(self.extendDict.get('sabr_webm_only', '1')).lower() not in ('0', 'false', 'off', 'no')
        except Exception:
            _webm_only = True
        debug_log('sabr videos pre-webm', {
            'quality': quality,
            'all': [{
                'itag': x.get('itag'), 'client': x.get('client'),
                'codecs': x.get('codecs'), 'mime': (x.get('mimeType') or '').split(';')[0],
                'height': x.get('height'),
            } for x in videos],
        })
        if _webm_only:
            _webm = [x for x in videos if 'webm' in (x.get('mimeType') or '').lower()
                     or 'vp9' in (x.get('codecs') or '').lower() or 'vp09' in (x.get('codecs') or '').lower()]
            debug_log('sabr webm filter', {
                'webm_only': _webm_only, 'matched': len(_webm),
                'webm_itags': [x.get('itag') for x in _webm],
                'fallback_to_local_mp4': (len(_webm) == 0),
            })
            videos = _webm
        # 在同分辨率下优先选 <=30fps（如同时有 248 与 303 时选 248）；若 1080p/720p 仅有 60fps (itag 303/302)，
        # 则优先选用 720p60 (itag 302，码率约 1080p60 的 45%)，兼顾高清画质与盒子解码流畅度
        videos.sort(key=lambda x: (
            0 if self.yt._is_hdr_video(x) else 1,
            1 if int(x.get('height') or 0) >= 720 else 0,
            1 if (int(x.get('fps') or 30) <= 30 and int(x.get('height') or 0) >= 720) else 0,
            1 if int(x.get('itag') or 0) == 302 else 0,
            int(x.get('height') or 0),
            self.yt._video_codec_priority(x),
            int(x.get('bitrate') or 0),
        ), reverse=True)
        return videos, bad_itags

    def _build_sabr_candidates(self, sabr_formats, quality='best'):
        videos, bad_itags = self._sabr_quality_videos(sabr_formats, quality)
        priorities = self._sabr_client_priority()
        candidates = []
        primary_video_sig = None
        primary_audio_sig = None

        def media_signature(item, kind):
            return (
                int(item.get('itag') or 0),
                (item.get('mimeType') or '').split(';')[0].lower(),
                (item.get('codecs') or '').lower(),
                int(item.get('height') or 0) if kind == 'video' else 0,
                int(item.get('width') or 0) if kind == 'video' else 0,
            )

        for client in priorities:
            client_videos = [x for x in videos if str(x.get('client') or '').upper() == client]
            client_audios = [
                x for x in (sabr_formats or [])
                if x.get('protocol') == 'sabr'
                and x.get('vcodec') == 'none' and x.get('acodec') != 'none'
                and str(x.get('client') or '').upper() == client
            ]
            if not client_videos or not client_audios:
                continue
            if primary_video_sig:
                client_videos = [x for x in client_videos if media_signature(x, 'video') == primary_video_sig]
                client_audios = [x for x in client_audios if media_signature(x, 'audio') == primary_audio_sig]
                if not client_videos or not client_audios:
                    debug_log('sabr incompatible fallback skipped', {
                        'client': client, 'required_video': primary_video_sig,
                        'required_audio': primary_audio_sig,
                    })
                    continue
            video = client_videos[0]
            audio = self.yt.choose_audio(client_audios, protocol='sabr', same_client=client)
            if not audio:
                continue
            video_cfg = video.get('_sabr_config') or {}
            audio_cfg = audio.get('_sabr_config') or {}
            # Never mix formats and SABR session data from different player responses.
            if not video_cfg.get('server_abr_streaming_url') or not video_cfg.get('video_playback_ustreamer_config'):
                continue
            if audio_cfg.get('server_abr_streaming_url') != video_cfg.get('server_abr_streaming_url'):
                same_session_audio = next((x for x in client_audios if (
                    (x.get('_sabr_config') or {}).get('server_abr_streaming_url')
                    == video_cfg.get('server_abr_streaming_url'))), None)
                if same_session_audio:
                    audio = same_session_audio
                else:
                    continue
            video_sig = media_signature(video, 'video')
            audio_sig = media_signature(audio, 'audio')
            if primary_video_sig is None:
                primary_video_sig, primary_audio_sig = video_sig, audio_sig
            elif video_sig != primary_video_sig or audio_sig != primary_audio_sig:
                continue
            candidates.append({
                'client': client, 'video_item': video, 'audio_item': audio,
                'video_signature': video_sig, 'audio_signature': audio_sig,
            })
        debug_log('sabr client candidates', {
            'priority': priorities, 'filtered_itags': sorted(bad_itags),
            'candidates': [{
                'client': x['client'], 'video': x['video_item'].get('itag'),
                'audio': x['audio_item'].get('itag'),
                'height': x['video_item'].get('height'),
                'host': urlparse((x['video_item'].get('_sabr_config') or {}).get('server_abr_streaming_url') or '').netloc,
            } for x in candidates],
        })
        return candidates

    def _activate_sabr_candidate(self, vid, data, index, reason='initial'):
        candidates = data.get('sabr_candidates') or []
        if index < 0 or index >= len(candidates):
            return None
        selected = candidates[index]
        video = selected['video_item']
        audio = selected['audio_item']
        state_key = f'{vid}:sabr:{selected.get("client")}:{video.get("itag")}:{audio.get("itag")}'
        self.yt.sabr_state.pop(state_key, None)
        data.update({
            'active_index': index,
            'video_item': video,
            'audio_item': audio,
            'state_key': state_key,
        })
        self.setCache(f'yt_sabr_{vid}', data)
        debug_log('sabr client activated', {
            'vid': vid, 'reason': reason, 'index': index,
            'client': selected.get('client'), 'video': video.get('itag'),
            'audio': audio.get('itag'), 'height': video.get('height'),
            'host': urlparse((video.get('_sabr_config') or {}).get('server_abr_streaming_url') or '').netloc,
        })
        return data

    def _new_sabr_play_data(self, vid, extracted, quality='best'):
        self.setCache(f'yt_sabr_dmode_{vid}', None)
        candidates = self._build_sabr_candidates(extracted.get('sabr_formats') or [], quality)
        if not candidates:
            return None
        data = {
            'sabr_candidates': candidates,
            'duration': extracted.get('duration') or 0,
            'expires': time.time() + 1800,
        }
        data = self._activate_sabr_candidate(vid, data, 0, reason='initial')
        # 全屏轨选：把可选 SABR 视轨（同 player response、WebM 优先、≤sabr_max_height）
        # 存进播放数据，_proxy_sabr_mpd 据此发多 Representation，用户全屏后可切。
        try:
            _webm_options = self.extendDict
        except Exception:
            _webm_options = {}
        try:
            options_src = extracted.get('sabr_formats') or []
            vids, _bad = self._sabr_quality_videos(options_src, quality)
            active_sig = data.get('video_item', {}).get('_sabr_config', {}).get('server_abr_streaming_url')
            options = []
            seen_itags = set()
            for x in vids:
                it = int(x.get('itag') or 0)
                h = int(x.get('height') or 0)
                cfgx = x.get('_sabr_config') or {}
                if not it or not cfgx.get('server_abr_streaming_url'):
                    continue
                if cfgx.get('server_abr_streaming_url') != active_sig:
                    continue  # 只保留与激活会话同一 player response 的轨，避免混 session 数据
                if it in seen_itags:
                    continue
                seen_itags.add(it)
                options.append(x)
            data['sabr_video_options'] = options
            self.setCache(f'yt_sabr_{vid}', data)
            debug_log('sabr track options', {'vid': vid,
                      'options': [{'itag': o.get('itag'), 'h': o.get('height')} for o in options]})
        except Exception as e:
            debug_log('sabr track options error', repr(e))
        return data

    def _activate_sabr_itag(self, vid, itag):
        """全屏轨选：切换到 sabr_video_options 里指定 itag 的视频轨，并同步更新 state_key 及直链模式。"""
        with self.sabr_switch_lock:
            data = self.getCache(f'yt_sabr_{vid}') if vid else None
            if not data:
                return None
            try:
                want = int(itag)
            except Exception:
                return None
            cur = int((data.get('video_item') or {}).get('itag') or 0)
            if cur == want:
                return data
            opt = next((o for o in (data.get('sabr_video_options') or [])
                        if int(o.get('itag') or 0) == want), None)
            if not opt:
                debug_log('sabr track switch unknown itag', {'vid': vid, 'want': want})
                return None
            data['video_item'] = opt
            # NOTE: 同步更新 state_key 中的 v_itag，并直接开启本地 Super-Chunk 直链模式 (yt_sabr_dmode=1)，
            # 确保切轨后请求的 seg=init 与当前播放进度的 seg=N 立即返回对应新分辨率的数据，且绝不会被旧 state_key 覆盖回原画质。
            audio_it = int((data.get('audio_item') or {}).get('itag') or 0)
            client_name = str(opt.get('client') or (data.get('video_item') or {}).get('client') or 'VISIONOS').upper()
            data['state_key'] = f'{vid}:sabr:{client_name}:{want}:{audio_it}'
            self.setCache(f'yt_sabr_{vid}', data)
            self.setCache(f'yt_sabr_dmode_{vid}', 1)
            debug_log('sabr track switched', {'vid': vid, 'from': cur, 'to': want,
                      'height': opt.get('height'), 'state_key': data.get('state_key')})
            return data

    def _sabr_reload_session(self, state_key, video_item, audio_item, reload_token=None):
        """SABR 续流回调：服务器要求 reload 时，重取 fresh 播放上下文并匹配回同一 itag 组合。

        state_key 形如 '{vid}:sabr:{client}:{v_itag}:{a_itag}'，从中取 vid 与目标 itag。
        reload_token（part46 内 reloadPlaybackParams.token）回传到 player 请求的
        reloadPlaybackContext，让服务器把这次当「续同一会话」而非冷启动——不带 token 的纯
        force_refresh 真机实测被服务器当无缓冲冷客户端，只回控制 part 不发媒体（70s 死循环）。
        force_refresh 重新 extract（沿用旧 visitorData 保 pot 绑定→新 server_abr_url、新 ustreamer），
        重建候选后取回相同 client/itag 的 video/audio 组合。返回 (video_item, audio_item) 或 None。
        """
        try:
            parts = str(state_key or '').split(':')
            # 期望 [vid, 'sabr', client, v_itag, a_itag]
            if len(parts) < 5 or parts[1] != 'sabr':
                debug_log('sabr reload bad state_key', {'state_key': state_key})
                return None
            vid = parts[0]
            want_client = parts[2]
            try:
                want_v = int(parts[3])
                want_a = int(parts[4])
            except Exception:
                want_v = int((video_item or {}).get('itag') or 0)
                want_a = int((audio_item or {}).get('itag') or 0)
        except Exception as e:
            debug_log('sabr reload parse error', {'state_key': state_key, 'error': repr(e)})
            return None

        with self.sabr_switch_lock:
            # 复用旧会话 visitorData：pot 绑定 visitorData，换了必 403；同时把 reload_token
            # 回传 player 请求的 reloadPlaybackContext，让服务器识别为「续同一会话」而非冷启动。
            prev_vd = None
            try:
                prev_vd = (((video_item or {}).get('_sabr_config') or {}).get('client_info') or {}).get('visitorData') \
                    or (((audio_item or {}).get('_sabr_config') or {}).get('client_info') or {}).get('visitorData')
            except Exception:
                prev_vd = None
            debug_log('sabr reload extract begin', {'vid': vid, 'has_token': bool(reload_token), 'reuse_visitor': bool(prev_vd)})
            try:
                ext = self.yt.extract(vid, force_refresh=True, reload_token=reload_token, prefer_visitor_data=prev_vd)
            except Exception as e:
                debug_log('sabr reload extract error', {'vid': vid, 'error': repr(e)})
                return None
            candidates = self._build_sabr_candidates(ext.get('sabr_formats') or [], 'best')
            if not candidates:
                debug_log('sabr reload no candidates', {'vid': vid})
                return None
            # 优先精确匹配原 client + itag 组合，退而求其次匹配同 itag，再退而取首个候选。
            chosen = None
            for c in candidates:
                if (str(c.get('client') or '').upper() == want_client
                        and int(c['video_item'].get('itag') or 0) == want_v
                        and int(c['audio_item'].get('itag') or 0) == want_a):
                    chosen = c
                    break
            if not chosen:
                for c in candidates:
                    if (int(c['video_item'].get('itag') or 0) == want_v
                            and int(c['audio_item'].get('itag') or 0) == want_a):
                        chosen = c
                        break
            if not chosen:
                chosen = candidates[0]
            # 把 fresh 会话写回缓存，但保持 state_key 不变——后续每个分段请求都从缓存读
            # video_item/audio_item，若不更新会拿旧 cfg（旧 ustreamer/pot）再次触发 reload。
            # 保持 state_key 一致是关键：sabr_state 里已累积的分段与元数据不能丢。
            try:
                cache = self.getCache(f'yt_sabr_{vid}')
                if cache:
                    cache['video_item'] = chosen['video_item']
                    cache['audio_item'] = chosen['audio_item']
                    self.setCache(f'yt_sabr_{vid}', cache)
            except Exception as e:
                debug_log('sabr reload cache update error', {'vid': vid, 'error': repr(e)})
            debug_log('sabr reload session ready', {
                'vid': vid, 'want_client': want_client, 'want_v': want_v, 'want_a': want_a,
                'got_client': chosen.get('client'),
                'got_v': chosen['video_item'].get('itag'),
                'got_a': chosen['audio_item'].get('itag'),
                'host': urlparse((chosen['video_item'].get('_sabr_config') or {}).get('server_abr_streaming_url') or '').netloc,
            })
            return chosen['video_item'], chosen['audio_item']

    def _switch_sabr_client(self, vid, failed_index, error):
        with self.sabr_switch_lock:
            current = self.getCache(f'yt_sabr_{vid}') if vid else None
            if not current:
                return None
            failed_index = int(failed_index or 0)
            current_index = int(current.get('active_index') or 0)
            # Parallel audio/video init may already have switched this exact failure.
            if current_index != failed_index:
                debug_log('sabr failover already applied', {
                    'vid': vid, 'failed_index': failed_index,
                    'active_index': current_index,
                })
                return current
            next_index = current_index + 1
            if next_index >= len(current.get('sabr_candidates') or []):
                debug_log('sabr client failover exhausted', {
                    'vid': vid, 'active_index': current_index, 'error': repr(error),
                })
                return None
            old_client = current['sabr_candidates'][current_index].get('client')
            debug_log('sabr client failover', {
                'vid': vid, 'from': old_client,
                'to': current['sabr_candidates'][next_index].get('client'),
                'error': repr(error),
            })
            return self._activate_sabr_candidate(
                vid, current, next_index, reason=f'init failure: {error}')

    def _choose_sabr_video(self, sabr_formats, quality='best'):
        candidates = self._build_sabr_candidates(sabr_formats, quality)
        item = candidates[0]['video_item'] if candidates else None
        debug_log('choose sabr isolated', {
            'client': item.get('client') if item else None,
            'itag': item.get('itag') if item else None,
            'height': item.get('height') if item else None,
            'candidate_count': len(candidates),
        })
        return item

    def _proxy_sabr_mpd(self, params):
        vid = params.get('vid')
        data = self.getCache(f'yt_sabr_{vid}') if vid else None
        if not data:
            debug_log('sabr mpd cache miss rebuild', {'vid': vid})
            try:
                ext = self.yt.extract(vid, force_refresh=True)
                data = self._new_sabr_play_data(vid, ext, 'best')
            except Exception as e:
                debug_log('sabr mpd rebuild error', repr(e))
        if not data or not data.get('video_item') or not data.get('audio_item'):
            return [404, 'text/plain', 'SABR 音视频缓存不存在']

        video = data['video_item']
        audio = data['audio_item']
        duration = int(data.get('duration') or 0)
        duration_pt = f'PT{duration}S' if duration else 'PT0S'
        base = f'http://127.0.0.1:9978/proxy?do=py&amp;type=sabr&amp;vid={html.escape(str(vid))}'
        video_mime = html.escape((video.get('mimeType') or 'video/webm').split(';')[0])
        audio_mime = html.escape((audio.get('mimeType') or 'audio/webm').split(';')[0])
        video_duration_ms = int(float((video.get('_sabr_config') or {}).get('target_duration_sec') or 6) * 1000)
        # YouTube VOD SABR audio segments are normally ~10 seconds (observed in MediaHeader).
        audio_duration_ms = int(float((audio.get('_sabr_config') or {}).get('target_duration_sec') or 10) * 1000)
        if audio_duration_ms < 8000:
            audio_duration_ms = 10000
        # 起播微调：纯本地 SABR 走内置代理直连，使用小缓冲实现秒开起播。
        # 默认 minBuffer 1.5s、无呈现延迟；可用 ext 的 sabr_min_buffer_sec / sabr_pres_delay_sec 调整。
        try:
            sabr_min_buf = float(self.extendDict.get('sabr_min_buffer_sec') or 1.5)
        except Exception:
            sabr_min_buf = 1.5
        try:
            sabr_pres_delay = float(self.extendDict.get('sabr_pres_delay_sec') or 0.0)
        except Exception:
            sabr_pres_delay = 0.0
        pres_attr = f' suggestedPresentationDelay="PT{sabr_pres_delay:.1f}S"' if sabr_pres_delay > 0 else ''
        # 全屏轨选：每条可选视轨独立生成一个 <AdaptationSet contentType="video">，
        # 默认激活轨（1080p）排第 1 位并标记 <Role value="main"/>，使 ExoPlayer：
        #   1. 起播时以 FixedTrackSelection 锁定 1080p，绝不自动降画质；
        #   2. 全屏“视轨”弹窗中仅当前画质为选中态（不会出现多轨同时高亮）；
        #   3. 用户点击切换任意分辨率时，ExoPlayer 立即释放旧缓冲并请求新 itag 的 seg=init 与当前进度 seg=N！
        vid_opts = [o for o in (data.get('sabr_video_options') or []) if o.get('_sabr_config')]
        if not vid_opts or all(int(o.get('itag') or 0) != int(video.get('itag') or 0) for o in vid_opts):
            vid_opts = [video] + [o for o in vid_opts if int(o.get('itag') or 0) != int(video.get('itag') or 0)]
        active_itag = int(video.get('itag') or 0)
        vid_opts.sort(key=lambda o: (1 if int(o.get('itag') or 0) == active_itag else 0, int(o.get('height') or 0)), reverse=True)
        video_adapt_sets = ''
        for idx_v, o in enumerate(vid_opts):
            o_itag = int(o.get('itag') or 0)
            o_mime = html.escape((o.get('mimeType') or 'video/webm').split(';')[0])
            o_dur = int(float((o.get('_sabr_config') or {}).get('target_duration_sec') or 6) * 1000)
            o_base = f'{base}&amp;itag={o_itag}'
            bw = int(o.get('bitrate') or 1000000)
            role_xml = '\n      <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>' if idx_v == 0 else ''
            video_adapt_sets += f'''    <AdaptationSet id="{idx_v + 1}" contentType="video" mimeType="{o_mime}" segmentAlignment="true" startWithSAP="1">{role_xml}
      <Representation id="sabr-v{o_itag}" bandwidth="{bw}" codecs="{html.escape(o.get('codecs') or '')}" width="{int(o.get('width') or 0)}" height="{int(o.get('height') or 0)}" mimeType="{o_mime}">
        <SegmentTemplate timescale="1000" duration="{o_dur}" startNumber="1" initialization="{o_base}&amp;track=video&amp;seg=init" media="{o_base}&amp;track=video&amp;seg=$Number$"/>
      </Representation>
    </AdaptationSet>
'''
        audio_adapt_id = len(vid_opts) + 1
        sub_adapt_id = len(vid_opts) + 2
        sub_url_mpd = f'http://127.0.0.1:9978/proxy?do=py&amp;type=sub&amp;vid={html.escape(str(vid))}&amp;format=vtt&amp;ext=.vtt'
        mpd = f'''<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="{duration_pt}" minBufferTime="PT{sabr_min_buf:.1f}S"{pres_attr} profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">
  <Period id="1" start="PT0S">
{video_adapt_sets}    <AdaptationSet id="{audio_adapt_id}" contentType="audio" mimeType="{audio_mime}" segmentAlignment="true" startWithSAP="1">
      <Representation id="sabr-a{int(audio.get('itag') or 0)}" bandwidth="{int(audio.get('bitrate') or 128000)}" codecs="{html.escape(audio.get('codecs') or '')}">
        <SegmentTemplate timescale="1000" duration="{audio_duration_ms}" startNumber="1" initialization="{base}&amp;track=audio&amp;seg=init" media="{base}&amp;track=audio&amp;seg=$Number$"/>
      </Representation>
    </AdaptationSet>
    <AdaptationSet id="{sub_adapt_id}" contentType="text" mimeType="text/vtt" lang="zh">
      <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>
      <Representation id="sub-zh" bandwidth="256">
        <BaseURL>{sub_url_mpd}</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>'''
        debug_log('proxy true sabr mpd', {
            'vid': vid, 'video': video.get('itag'), 'audio': audio.get('itag'),
            'client': video.get('client'), 'duration': duration,
            'video_segment_ms': video_duration_ms, 'audio_segment_ms': audio_duration_ms,
            'track_options': [{'itag': o.get('itag'), 'h': o.get('height')} for o in vid_opts],
        })
        return [200, 'application/dash+xml', mpd]

    def _build_direct_webm_cont(self, vid, video_item, audio_item, force_refresh=False):
        """越 60s 断点：构建纯本地 WebM Cues 索引与 Super-Chunk 超级分片续播上下文。

        纯本地零服务器设计：
          1. 严格优先选用 VISIONOS / ANDROID_VR / ANDROID 等免 n 加密直链客户端（其中 VISIONOS 免 GVS po_token 且无 60s/Range 限制）；
          2. 将连续的 initRange(0..init_end) 与 indexRange(cues_start..cues_end) 合并为单次 bytes=0-{cues_end+1} 请求，
             音视频双轨并发拉取，建表耗时仅 ~0.6s；
          3. 切视轨时自动复用已建好的音频轨 Cues 缓存，仅需单次请求新视轨的 head+cues（~0.3s）；
          4. 若非 VISIONOS 轨且超长视频 Cues 分了 2 次 Range 拉取，建表完成后自动原地刷新一次本地 URL。
        """
        cache_key = f'yt_sabr_dcont_{vid}_{int((video_item or {}).get("itag") or 0)}'
        if not force_refresh:
            cached = self.getCache(cache_key)
            if cached:
                return cached
        if not hasattr(self, '_dcont_lock') or self._dcont_lock is None:
            self._dcont_lock = threading.RLock()
        with self._dcont_lock:
            if not force_refresh:
                cached = self.getCache(cache_key)
                if cached:
                    return cached
            want_v = int((video_item or {}).get('itag') or 0)
            want_a = int((audio_item or {}).get('itag') or 0)
            audio_cache_key = f'yt_sabr_dcont_a_{vid}_{want_a}'
            cached_audio = self.getCache(audio_cache_key) if not force_refresh else None
            try:
                ext = self.yt.extract(vid, force_refresh=force_refresh)
                if not (ext.get('formats') or []) and not force_refresh:
                    ext = self.yt.extract(vid, force_refresh=True)
            except Exception as e:
                debug_log('direct-cont extract error', {'vid': vid, 'error': repr(e)})
                return None
            formats = ext.get('formats') or []
            client_rank = {'VISIONOS': 7, 'ANDROID_VR': 6, 'ANDROID': 5, 'IOS': 4, 'MWEB': 2, 'WEB': 1, 'WEB_INITIAL': 0}

            def pick(itag, kind):
                exact_cands = [f for f in formats if int(f.get('itag') or 0) == itag and f.get('url')]
                if exact_cands:
                    if kind == 'audio':
                        exact_cands.sort(key=lambda f: (self.yt._audio_lang_priority(f), client_rank.get(str(f.get('client') or '').upper(), 0), int(f.get('bitrate') or 0)), reverse=True)
                    else:
                        exact_cands.sort(key=lambda f: client_rank.get(str(f.get('client') or '').upper(), 0), reverse=True)
                    return exact_cands[0]
                if kind == 'video':
                    cands = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none'
                             and f.get('url') and ('webm' in (f.get('mimeType') or '').lower()
                             or 'vp9' in (f.get('codecs') or '').lower())]
                    cands.sort(key=lambda f: (client_rank.get(str(f.get('client') or '').upper(), 0), int(f.get('height') or 0)), reverse=True)
                else:
                    cands = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none'
                             and f.get('url') and ('opus' in (f.get('codecs') or '').lower()
                             or 'webm' in (f.get('mimeType') or '').lower())]
                    cands.sort(key=lambda f: (self.yt._audio_lang_priority(f), client_rank.get(str(f.get('client') or '').upper(), 0), int(f.get('bitrate') or 0)), reverse=True)
                return cands[0] if cands else None

            result = {}
            if cached_audio and isinstance(cached_audio, dict) and cached_audio.get('cues'):
                result['audio'] = cached_audio
            used_two_ranges = [False]
            req_proxies = dict(self.session.proxies or {})

            def _build_one_track(kind, want):
                fmt = pick(want, kind)
                if not fmt or not fmt.get('url'):
                    debug_log('direct-cont no format', {'vid': vid, 'kind': kind, 'want': want})
                    return
                cur_itag = int(fmt.get('itag') or 0)
                url = fmt.get('url')
                headers = self.header.copy()
                headers.update(fmt.get('headers') or {})
                headers['Accept-Encoding'] = 'identity'
                headers['Connection'] = 'close'
                init_range = fmt.get('initRange') or {}
                index_range = fmt.get('indexRange') or {}
                init_end = int(init_range.get('end') or 0)
                cues_start = int(index_range.get('start') or 0)
                cues_end = int(index_range.get('end') or 0)
                if not init_end or not cues_end:
                    debug_log('direct-cont missing ranges', {'vid': vid, 'kind': kind})
                    return
                total = int(fmt.get('contentLength') or 0)
                head_bytes = None
                cues_bytes = None
                # 合并 init (0..init_end) 与 cues (cues_start..cues_end) 为单次 HTTP Range 请求（上限放宽至 512KB）
                combined_end = max(init_end, cues_end + 1)
                if combined_end <= 524288 and cues_start >= init_end:
                    try:
                        h_comb = dict(headers)
                        h_comb['Range'] = f'bytes=0-{combined_end}'
                        r_comb = requests.get(url, headers=h_comb, proxies=req_proxies, timeout=12, allow_redirects=True)
                        if r_comb.status_code in (200, 206) and len(r_comb.content) > cues_start:
                            raw_comb = r_comb.content
                            head_bytes = raw_comb[:init_end + 1]
                            cues_bytes = raw_comb[cues_start:cues_end + 2]
                            if not total:
                                cr = r_comb.headers.get('content-range') or ''
                                if '/' in cr:
                                    try:
                                        total = int(cr.split('/')[-1])
                                    except Exception:
                                        total = 0
                        r_comb.close()
                    except Exception as e:
                        debug_log('direct-cont combined head+cues local error', {'vid': vid, 'kind': kind, 'error': repr(e)})

                if not head_bytes:
                    used_two_ranges[0] = True
                    try:
                        h = dict(headers)
                        h['Range'] = f'bytes=0-{init_end}'
                        r = requests.get(url, headers=h, proxies=req_proxies, timeout=12, allow_redirects=True)
                        if r.status_code in (200, 206):
                            head_bytes = r.content
                        r.close()
                    except Exception:
                        pass
                if not head_bytes:
                    debug_log('direct-cont head fetch failed', {'vid': vid, 'kind': kind})
                    return

                seg_off = _webm_segment_data_offset(head_bytes)
                tc_scale = _webm_timecode_scale(head_bytes)
                if not cues_bytes:
                    used_two_ranges[0] = True
                    try:
                        hc = dict(headers)
                        hc['Range'] = f'bytes={cues_start}-{cues_end + 1}'
                        rc = requests.get(url, headers=hc, proxies=req_proxies, timeout=12, allow_redirects=True)
                        if rc.status_code in (200, 206):
                            cues_bytes = rc.content
                        rc.close()
                    except Exception:
                        pass
                if not cues_bytes:
                    debug_log('direct-cont cues fetch failed', {'vid': vid, 'kind': kind})
                    return

                cues = _webm_parse_cues(cues_bytes, seg_off, tc_scale)
                if not cues:
                    debug_log('direct-cont cues empty', {'vid': vid, 'kind': kind,
                              'seg_off': seg_off, 'cues_start': cues_start, 'head_len': len(head_bytes)})
                    return
                init_end_byte = int(init_range.get('end') or 0)
                init_bytes = head_bytes[:init_end_byte + 1] if init_end_byte else head_bytes[:seg_off]
                result[kind] = {
                    'vid': vid, 'kind': kind,
                    'url': url,
                    'headers': headers, 'cues': cues,
                    'content_length': total or (cues[-1][1] if cues else 0),
                    'seg_data_offset': seg_off, 'timecode_scale': tc_scale,
                    'init_bytes': init_bytes, 'init_bytes_len': len(init_bytes),
                    'itag': cur_itag, 'client': fmt.get('client'),
                    'mimeType': fmt.get('mimeType'),
                }
                if kind == 'audio':
                    self.setCache(audio_cache_key, result[kind])
                debug_log('direct-cont track ready', {
                    'vid': vid, 'kind': kind, 'itag': cur_itag, 'client': fmt.get('client'),
                    'audioTrack': (fmt.get('audioTrack') or {}).get('displayName') if kind == 'audio' else None,
                    'cues': len(cues),
                    'first_cue_ms': cues[0][0], 'last_cue_ms': cues[-1][0],
                    'content_length': result[kind]['content_length'], 'seg_off': seg_off,
                })

            t_v = threading.Thread(target=_build_one_track, args=('video', want_v), daemon=True)
            t_v.start()
            if 'audio' not in result:
                t_a = threading.Thread(target=_build_one_track, args=('audio', want_a), daemon=True)
                t_a.start()
                t_a.join(timeout=20)
            t_v.join(timeout=20)
            if 'video' not in result or 'audio' not in result:
                return None
            if used_two_ranges[0] and str(result['video'].get('client') or '').upper() != 'VISIONOS':
                self._refresh_local_webm_urls(vid, result)
            self.setCache(cache_key, result)
            return result

    @staticmethod
    def _webm_cue_boundary_index(cues, target_ms):
        """将目标时间戳映射为单调递增的 Cue 索引，容忍 YouTube WebM Cue 时间戳如 10001ms/70007ms 的微小正偏。"""
        if not cues or target_ms <= 0:
            return 0
        n = len(cues)
        limit_ms = target_ms + 500
        idx = 0
        for i, (t_ms, _) in enumerate(cues):
            if t_ms <= limit_ms:
                idx = i
            else:
                break
        return min(idx, n)

    def _get_sabr_seq_end_map(self, vid, itag):
        """读取本场 SABR 已投递分段的精确结束时间戳表 {seq: end_ms}，用于 60s 切入本地 Super-Chunk 时零误差衔接。"""
        if not vid or not itag:
            return {}
        try:
            for sk, st in list((self.yt.sabr_state or {}).items()):
                if str(sk).startswith(f'{vid}:'):
                    m = (st.get('seq_end_ms') or {}).get(int(itag))
                    if m:
                        return m
        except Exception:
            pass
        return {}

    def _compute_direct_webm_range(self, info, want_seq, dash_seg_ms):
        """计算第 want_seq 段的严格连续、零重叠、零重复、零跳帧精确字节范围 (range_str, start_ms, end_ms)。
        # NOTE: 为什么之前有时画面会卡顿 5~6 秒但声音正常：
        #   1. 音频 Opus WebM 的 Cue 严格固定为 10000ms，从不漂移；
        #   2. 视频 VP9 WebM 的 Cue 受帧率（29.97fps 每段 6006ms 累积正偏）或 MV 镜头切换（如某段 GOP 在 12600ms 结束，超出 12000+500ms）影响，
        #      旧的无状态 _webm_cue_boundary_index 会在 seg=k 将 end_idx 强行 +1，随后 seg=k+1 的 start_idx 仍停留在同一 Cue，
        #      导致连续两个分段向 ExoPlayer 发送完全相同的视频 Cluster 字节，视频解码器因收到重复旧时间戳画面冻结 6 秒，而音频继续正常播放！
        # 解决方案：按轨道维护严格单调递增的连续分区表 seg_table，保证 start_idx(seq) == end_idx(seq - 1) 恒成立，
        # 并在 SABR 切入 direct-webm 的交界点自动对齐 SABR 最后一段的精确结束时间，实现 100% 零重发、零漏帧！
        """
        cues = info['cues']
        content_length = int(info.get('content_length') or 0)
        n = len(cues)
        if n == 0:
            start_ms = max(0, (want_seq - 1) * dash_seg_ms)
            return 'bytes=0-', start_ms, start_ms + dash_seg_ms
        want_seq = max(1, int(want_seq))
        tables = info.setdefault('_seg_tables', {})
        table = tables.setdefault(int(dash_seg_ms), {})
        if want_seq not in table:
            sabr_end_map = self._get_sabr_seq_end_map(info.get('vid'), info.get('itag'))
            for s in range(1, want_seq + 1):
                if s in table:
                    continue
                if s == 1:
                    s_idx = 0
                else:
                    s_idx = table[s - 1][1]
                    if sabr_end_map and (s - 1) in sabr_end_map and s not in sabr_end_map:
                        anchor_ms = sabr_end_map[s - 1]
                        best_k = min(range(n), key=lambda k: abs(cues[k][0] - anchor_ms))
                        if abs(cues[best_k][0] - anchor_ms) <= 600:
                            s_idx = best_k
                if s_idx >= n:
                    s_idx = max(0, n - 1)
                    e_idx = n
                else:
                    e_idx = s_idx + 1
                    s_off = cues[s_idx][1]
                    target_end_ms = s * dash_seg_ms
                    low_thresh = target_end_ms - int(dash_seg_ms * 0.55)
                    high_thresh = target_end_ms + int(dash_seg_ms * 0.55)
                    while e_idx < n:
                        cur_end_ms = cues[e_idx][0]
                        next_end_ms = cues[e_idx + 1][0] if (e_idx + 1) < n else (cur_end_ms + dash_seg_ms)
                        next_off = cues[e_idx + 1][1] if (e_idx + 1) < n else (content_length or (cues[e_idx][1] + 512 * 1024))
                        if cur_end_ms < low_thresh and next_end_ms <= high_thresh and (next_off - s_off) <= 1800 * 1024:
                            e_idx += 1
                        else:
                            break
                table[s] = (s_idx, e_idx)
        start_idx, end_idx = table[want_seq]
        start_off = cues[start_idx][1]
        if end_idx < n:
            end_off = cues[end_idx][1]
            actual_end_ms = cues[end_idx][0]
        else:
            end_off = content_length if content_length and content_length > start_off else None
            actual_end_ms = max(cues[start_idx][0] + dash_seg_ms, want_seq * dash_seg_ms)
        actual_start_ms = cues[start_idx][0]
        range_str = f'bytes={start_off}-' + (str(end_off - 1) if end_off else '')
        return range_str, actual_start_ms, actual_end_ms

    def _get_dwebm_track_lock(self, vid, track, cur_itag=0):
        if not hasattr(self, '_dwebm_locks_guard') or self._dwebm_locks_guard is None:
            self._dwebm_locks_guard = threading.Lock()
            self._dwebm_track_locks = {}
        key = f'{vid}:{track}:{int(cur_itag or 0)}'
        with self._dwebm_locks_guard:
            lk = self._dwebm_track_locks.get(key)
            if lk is None:
                lk = threading.RLock()
                self._dwebm_track_locks[key] = lk
            return lk

    def _refresh_local_webm_urls(self, vid, cont):
        """纯本地极速刷新 WebM 直链 URL（无需重新拉取 head+cues），用于绕过单 URL 2~3 次 Range 配额限制。"""
        if not hasattr(self, '_refresh_url_lock') or self._refresh_url_lock is None:
            self._refresh_url_lock = threading.RLock()
        with self._refresh_url_lock:
            now = time.time()
            last_ts = getattr(self, f'_last_url_refresh_{vid}', 0)
            # 若 1.5 秒内刚由另一轨道刷新过同一视频的直链 URL，直接复用，避免音视频同时撞 403 时双倍 extract
            if now - last_ts < 1.5:
                return True
            try:
                ext = self.yt.extract(vid, force_refresh=True)
                formats = ext.get('formats') or []
                client_rank = {'VISIONOS': 7, 'ANDROID_VR': 6, 'ANDROID': 5, 'IOS': 4, 'MWEB': 2, 'WEB': 1}
                updated = False
                for kind in ('video', 'audio'):
                    info = (cont or {}).get(kind)
                    if not info:
                        continue
                    want_itag = int(info.get('itag') or 0)
                    cands = [f for f in formats if int(f.get('itag') or 0) == want_itag and f.get('url')]
                    if cands:
                        if kind == 'audio':
                            cands.sort(key=lambda f: (self.yt._audio_lang_priority(f), client_rank.get(str(f.get('client') or '').upper(), 0), int(f.get('bitrate') or 0)), reverse=True)
                        else:
                            cands.sort(key=lambda f: client_rank.get(str(f.get('client') or '').upper(), 0), reverse=True)
                        info['url'] = cands[0]['url']
                        if cands[0].get('headers'):
                            info['headers'].update(cands[0]['headers'])
                        updated = True
                if updated:
                    setattr(self, f'_last_url_refresh_{vid}', time.time())
                return updated
            except Exception as e:
                debug_log('refresh local webm urls error', {'vid': vid, 'error': repr(e)})
                return False

    def _prefetch_direct_webm_next(self, vid, track, next_seq, video_item, audio_item, dash_seg_ms):
        """纯本地 Super-Chunk 滑窗预取：当缓存中还没有 next_seq 时，后台自动触发下一批 Super-Chunk 拉取。
        # NOTE: _serve_direct_webm_segment 内部已将首段与后续批次全部写入 _dwebm_seg_cache（或由主请求消费），
        # 预取线程同样将首段写回缓存，且通过 track_lock 防止与主请求重复拉取同一分段。
        """
        if not hasattr(self, '_dwebm_seg_cache'):
            self._dwebm_seg_cache = {}
        if not hasattr(self, '_dwebm_inflight'):
            self._dwebm_inflight = set()
        cur_itag = int(((video_item if track == 'video' else audio_item) or {}).get('itag') or 0)
        ck = f'{vid}:{track}:{cur_itag}:{next_seq}'
        if ck in self._dwebm_seg_cache or ck in self._dwebm_inflight:
            return

        def _bg():
            if ck in self._dwebm_seg_cache or ck in self._dwebm_inflight:
                return
            self._dwebm_inflight.add(ck)
            try:
                body, meta = self._serve_direct_webm_segment(
                    vid, track, next_seq, video_item, audio_item, dash_seg_ms, _from_prefetch=True
                )
                if body is not None and ck not in self._dwebm_seg_cache:
                    while len(self._dwebm_seg_cache) >= 24:
                        oldest = next(iter(self._dwebm_seg_cache))
                        self._dwebm_seg_cache.pop(oldest, None)
                    self._dwebm_seg_cache[ck] = (body, meta)
            except Exception:
                pass
            finally:
                self._dwebm_inflight.discard(ck)

        try:
            threading.Thread(target=_bg, daemon=True).start()
        except Exception:
            pass

    def _trigger_dwebm_lookahead(self, vid, track, cur_itag, want_seq, video_item, audio_item, dash_seg_ms):
        """前瞻滑窗预取调度：始终保持当前播放点前方 2~3 个分段（12~18 秒）处于已缓存或后台预拉状态。
        即便遇到高码率舞蹈 MV 场景或 403 直链刷新（~1.5s），也在后台提前 12 秒完成，前端解码器零感知！
        """
        cache = getattr(self, '_dwebm_seg_cache', None) or {}
        for step in (1, 2, 3):
            look_seq = want_seq + step
            if f'{vid}:{track}:{cur_itag}:{look_seq}' not in cache:
                self._prefetch_direct_webm_next(vid, track, look_seq, video_item, audio_item, dash_seg_ms)
                break

    def _serve_direct_webm_segment(self, vid, track, segment, video_item, audio_item, dash_seg_ms, _rebuilt_count=0, _from_prefetch=False):
        """按 DASH seg=N 从 WebM 切出覆盖 [start_ms, start_ms+dash_seg_ms) 的 Cluster 字节。

        100% 纯本地免服务器 Super-Chunk（超级分片）+ 原地断点续读 + 原地刷新 URL 引擎：
          - 优先使用 VISIONOS 免 po_token 无限制直链；
          - 视频单次 Super-Chunk 上限控制在 1.15MB（音频 768KB），避免超过 1.8MB 触发代理节点 ChunkedEncodingError / IncompleteRead；
          - 当代理节点偶发中途断开连接（IncompleteRead）时，立即在当前偏移处发起剩余字节续读，无需重下整块更无需重新 extract；
          - 单轨 Single-Flight 锁保护 + 3 段前瞻滑窗预取，彻底杜绝预取与主请求重复下载同一分段；
          - 配额耗尽返回 403/404 时，原地极速刷新直链 URL（~1.5s）无缝续传，实现无限时长零卡顿播放！
        """
        if not hasattr(self, '_dwebm_seg_cache'):
            self._dwebm_seg_cache = {}
        cont = self._build_direct_webm_cont(vid, video_item, audio_item)
        if not cont or track not in cont:
            return None, {'error': 'direct-cont unavailable', 'track': track}
        info = cont[track]
        cur_itag = int(info.get('itag') or ((video_item if track == 'video' else audio_item) or {}).get('itag') or 0)
        if str(segment) == 'init':
            init_b = info.get('init_bytes') or b''
            if not init_b:
                return None, {'error': 'direct-cont no init bytes', 'track': track}
            return init_b, {'source': 'direct-webm', 'track': track, 'seg': 'init',
                            'bytes': len(init_b), 'itag': cur_itag}
        try:
            want_seq = int(segment)
        except Exception:
            return None, {'error': 'direct-cont bad segment', 'segment': segment}

        ck = f'{vid}:{track}:{cur_itag}:{want_seq}'
        if not _from_prefetch:
            prefetched = self._dwebm_seg_cache.pop(ck, None)
            if prefetched:
                p_body, p_meta = prefetched
                debug_log('direct-cont superchunk cache hit', p_meta)
                self._trigger_dwebm_lookahead(vid, track, cur_itag, want_seq, video_item, audio_item, dash_seg_ms)
                return p_body, p_meta

        track_lock = self._get_dwebm_track_lock(vid, track, cur_itag)
        with track_lock:
            # 拿到锁后再次检查缓存（若预取线程刚刚完成并写入了缓存，直接零耗时命中返回！）
            if _from_prefetch and ck in self._dwebm_seg_cache:
                return self._dwebm_seg_cache[ck]
            prefetched = self._dwebm_seg_cache.pop(ck, None)
            if prefetched:
                p_body, p_meta = prefetched
                debug_log('direct-cont superchunk lock hit', p_meta)
                if not _from_prefetch:
                    self._trigger_dwebm_lookahead(vid, track, cur_itag, want_seq, video_item, audio_item, dash_seg_ms)
                return p_body, p_meta

            range_str, start_ms, end_ms = self._compute_direct_webm_range(info, want_seq, dash_seg_ms)
            batch_plan = []
            super_start = None
            super_end = None
            # 视频控制在 1.15MB 以内（高码率段单拉、常规模率段 2~3 段合并），彻底规避 1.8MB+ 大包在代理链路上的 IncompleteRead
            MAX_SUPER_BYTES = 1200 * 1024 if track == 'video' else 768 * 1024
            max_batch_segs = 3 if track == 'video' else 4
            for seq_i in range(want_seq, want_seq + max_batch_segs):
                r_i, s_i, e_i = self._compute_direct_webm_range(info, seq_i, dash_seg_ms)
                m_r = re.match(r'^bytes=(\d+)-(\d*)$', r_i)
                if not m_r:
                    break
                b_s = int(m_r.group(1))
                b_e = int(m_r.group(2)) if m_r.group(2) else None
                if super_start is None:
                    super_start = b_s
                if b_e is not None and (b_e - super_start + 1) > MAX_SUPER_BYTES and batch_plan:
                    break
                batch_plan.append((seq_i, b_s, b_e, s_i, e_i, r_i))
                super_end = b_e
                if b_e is None:
                    break

            super_range = f'bytes={super_start}-' + (str(super_end) if super_end is not None else '') if super_start is not None else range_str
            expected_len = (super_end - super_start + 1) if (super_start is not None and super_end is not None) else 0
            req_proxies = dict(self.session.proxies or {})

            def _fetch_range_with_resume(url, base_headers, start_b, end_b):
                """支持断点续读的 Range 拉取：若遇 IncompleteRead 已读出部分数据，则从断点处立即续读剩余字节。"""
                buf = bytearray()
                cur_s = start_b
                for _part_try in range(3):
                    h_req = dict(base_headers)
                    h_req['Accept-Encoding'] = 'identity'
                    h_req['Connection'] = 'close'
                    h_req['Range'] = f'bytes={cur_s}-' + (str(end_b) if end_b is not None else '')
                    r = None
                    try:
                        r = requests.get(url, headers=h_req, proxies=req_proxies, timeout=(6, 14), allow_redirects=True, stream=True)
                        if r.status_code not in (200, 206):
                            sc = r.status_code
                            r.close()
                            return sc, bytes(buf)
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                buf.extend(chunk)
                                if cur_s is not None:
                                    cur_s += len(chunk)
                        r.close()
                        if not expected_len or len(buf) >= expected_len:
                            return 206, bytes(buf)
                    except Exception as ex:
                        if r is not None:
                            try:
                                r.close()
                            except Exception:
                                pass
                        # 若已读出部分字节且有明确终点，直接循环续读剩余字节，无需报错重头拉取
                        if cur_s is not None and end_b is not None and len(buf) > 0 and cur_s <= end_b:
                            debug_log('direct-cont partial resume', {
                                'track': track, 'seg': want_seq, 'read_so_far': len(buf),
                                'resume_from': cur_s, 'end': end_b, 'try': _part_try + 1,
                            })
                            continue
                        if _part_try == 2:
                            raise ex
                return (206 if len(buf) > 0 else 500), bytes(buf)

            try:
                status_code, super_body = _fetch_range_with_resume(
                    info['url'], info.get('headers') or {}, super_start, super_end)
                if status_code not in (200, 206) or (expected_len and len(super_body) < expected_len):
                    if _rebuilt_count < 2 and status_code in (403, 404, 500):
                        debug_log('direct-cont local quota/broken, fast refresh local url', {
                            'track': track, 'range': super_range, 'seg': want_seq,
                            'status': status_code, 'attempt': _rebuilt_count + 1})
                        if self._refresh_local_webm_urls(vid, cont):
                            return self._serve_direct_webm_segment(
                                vid, track, segment, video_item, audio_item, dash_seg_ms,
                                _rebuilt_count=_rebuilt_count + 1, _from_prefetch=_from_prefetch)
                    return None, {'error': f'direct-cont http {status_code}', 'track': track,
                                  'range': super_range, 'itag': cur_itag}
                if batch_plan and super_start is not None and len(super_body) > 0:
                    first_body = None
                    first_meta = None
                    for seq_i, b_s, b_e, s_i, e_i, r_i in batch_plan:
                        rel_s = max(0, b_s - super_start)
                        rel_e = (b_e - super_start + 1) if b_e is not None else len(super_body)
                        if rel_s >= len(super_body):
                            break
                        piece = super_body[rel_s:min(rel_e, len(super_body))]
                        if not piece:
                            break
                        if seq_i == want_seq:
                            first_body = piece
                            first_meta = {
                                'source': 'local-superchunk', 'track': track, 'seg': want_seq,
                                'start_ms': start_ms, 'end_ms': end_ms, 'range': range_str,
                                'bytes': len(first_body), 'itag': cur_itag,
                            }
                            if _from_prefetch:
                                while len(self._dwebm_seg_cache) >= 24:
                                    oldest = next(iter(self._dwebm_seg_cache))
                                    self._dwebm_seg_cache.pop(oldest, None)
                                self._dwebm_seg_cache[ck] = (first_body, first_meta)
                        else:
                            while len(self._dwebm_seg_cache) >= 24:
                                oldest = next(iter(self._dwebm_seg_cache))
                                self._dwebm_seg_cache.pop(oldest, None)
                            self._dwebm_seg_cache[f'{vid}:{track}:{cur_itag}:{seq_i}'] = (piece, {
                                'source': 'local-superchunk-cache', 'track': track, 'seg': seq_i,
                                'start_ms': s_i, 'end_ms': e_i, 'range': r_i,
                                'bytes': len(piece), 'itag': cur_itag,
                            })
                    if first_body is not None:
                        debug_log('direct-cont local superchunk ok', {
                            'vid': vid, 'track': track, 'seg': want_seq, 'itag': cur_itag,
                            'batched_segs': [x[0] for x in batch_plan],
                            'super_bytes': len(super_body), 'seg_bytes': len(first_body),
                        })
                        if not _from_prefetch:
                            self._trigger_dwebm_lookahead(vid, track, cur_itag, want_seq, video_item, audio_item, dash_seg_ms)
                        return first_body, first_meta
                body = super_body
            except Exception as e:
                if _rebuilt_count < 1:
                    if self._refresh_local_webm_urls(vid, cont):
                        return self._serve_direct_webm_segment(
                            vid, track, segment, video_item, audio_item, dash_seg_ms,
                            _rebuilt_count=_rebuilt_count + 1, _from_prefetch=_from_prefetch)
                return None, {'error': f'direct-cont fetch {e!r}', 'track': track, 'range': super_range}
            res_meta = {
                'source': 'direct-webm', 'track': track, 'seg': want_seq,
                'start_ms': start_ms, 'end_ms': end_ms, 'range': super_range,
                'bytes': len(body), 'itag': cur_itag,
            }
            if _from_prefetch:
                self._dwebm_seg_cache[ck] = (body, res_meta)
            elif body is not None:
                self._trigger_dwebm_lookahead(vid, track, cur_itag, want_seq, video_item, audio_item, dash_seg_ms)
            return body, res_meta

    def _proxy_sabr(self, params):
        vid = params.get('vid')
        track = params.get('track') or 'video'
        segment = params.get('seg') or 'init'
        req_itag = params.get('itag')
        req_video_item = None
        if req_itag and track == 'video':
            try:
                want_itag = int(req_itag)
                cur_data = self.getCache(f'yt_sabr_{vid}') or {}
                cur_v = int((cur_data.get('video_item') or {}).get('itag') or 0)
                if want_itag:
                    req_video_item = next(
                        (o for o in (cur_data.get('sabr_video_options') or []) if int(o.get('itag') or 0) == want_itag),
                        None,
                    )
                if want_itag and want_itag != cur_v:
                    self._activate_sabr_itag(vid, want_itag)
            except Exception:
                pass
        data = self.getCache(f'yt_sabr_{vid}') if vid else None
        if not data:
            return [404, 'text/plain', 'SABR 缓存不存在']
        if track not in ('video', 'audio'):
            return [400, 'text/plain', '无效 SABR 轨道']
        max_attempts = 1 + (len(data.get('sabr_candidates') or []) if str(segment) == 'init' else 0)
        last_error = None
        # 直链模式粘滞：本场已切入本地 Super-Chunk 直链模式（或用户主动切换了视轨），则直接走本地 Super-Chunk
        if self.getCache(f'yt_sabr_dmode_{vid}'):
            video_item = req_video_item or (data or {}).get('video_item')
            audio_item = (data or {}).get('audio_item')
            debug_log('direct-mode sticky serve', {
                'vid': vid, 'track': track, 'seg': segment,
                'itag': (video_item if track == 'video' else audio_item or {}).get('itag'),
            })
            item0 = video_item if track == 'video' else audio_item
            seg_ms = int(float((item0.get('_sabr_config') or {}).get('target_duration_sec')
                        or (6 if track == 'video' else 10)) * 1000)
            if track == 'audio' and seg_ms < 8000:
                seg_ms = 10000
            if seg_ms <= 0:
                seg_ms = 6000 if track == 'video' else 10000
            dbody, dmeta = self._serve_direct_webm_segment(
                vid, track, segment, video_item, audio_item, seg_ms)
            if dbody is not None:
                content_type = (item0.get('mimeType') or ('video/webm' if track == 'video' else 'audio/webm')).split(';')[0]
                return [200, content_type, dbody, {
                    'Content-Type': content_type, 'Content-Length': str(len(dbody)),
                    'Cache-Control': 'private, max-age=30', 'Accept-Ranges': 'none',
                }]
            # NOTE: 即使单次分片网络异常也不要清空 yt_sabr_dmode_{vid}，防止回退进已耗尽的 SABR 会话白白触发 6s extra extract！
            debug_log('direct-mode serve transient error', dmeta)
            return [503, 'text/plain', 'Direct WebM transient retry']
        # 后台预建 Cues 索引：当 SABR 稳定播放到第 4 段（约 18s）时，后台静默预建 WebM Cues 索引表，
        # 使 60s 边界从 SABR 切入 direct-webm 时零耗时（0ms）无缝过渡！
        if track == 'video' and str(segment) == '4':
            v_bg = req_video_item or data.get('video_item')
            a_bg = data.get('audio_item')
            threading.Thread(target=lambda: self._build_direct_webm_cont(vid, v_bg, a_bg), daemon=True).start()
        for attempt in range(max_attempts):
            data = self.getCache(f'yt_sabr_{vid}') or data
            request_index = int(data.get('active_index') or 0)
            video_item = req_video_item or data.get('video_item')
            audio_item = data.get('audio_item')
            state_key = data.get('state_key') or f'{vid}:sabr'
            try:
                media, meta = self.yt.sabr_get_segment(
                    video_item, audio_item, track, segment, state_key)
                if media is None:
                    debug_log('sabr segment unavailable', meta)
                    if str(meta.get('error') or '') == 'segment not produced by SABR server':
                        item0 = video_item if track == 'video' else audio_item
                        seg_ms = int(float((item0.get('_sabr_config') or {}).get('target_duration_sec')
                                    or (6 if track == 'video' else 10)) * 1000)
                        if track == 'audio' and seg_ms < 8000:
                            seg_ms = 10000
                        if seg_ms <= 0:
                            seg_ms = 6000 if track == 'video' else 10000
                        dbody, dmeta = self._serve_direct_webm_segment(
                            vid, track, segment, video_item, audio_item, seg_ms)
                        if dbody is not None:
                            content_type = (item0.get('mimeType') or ('video/webm' if track == 'video' else 'audio/webm')).split(';')[0]
                            self.setCache(f'yt_sabr_dmode_{vid}', 1)
                            debug_log('sabr->direct webm segment', dmeta)
                            return [200, content_type, dbody, {
                                'Content-Type': content_type, 'Content-Length': str(len(dbody)),
                                'Cache-Control': 'private, max-age=30', 'Accept-Ranges': 'none',
                            }]
                        debug_log('sabr->direct webm failed', dmeta)
                    return [500, 'text/plain', 'SABR 分段不可用: ' + json.dumps(meta, ensure_ascii=False, default=str)[:1000]]
                current = self.getCache(f'yt_sabr_{vid}') or data
                current_index = int(current.get('active_index') or 0)
                if str(segment) == 'init' and current_index != request_index:
                    debug_log('sabr stale init discarded', {
                        'vid': vid, 'track': track, 'request_index': request_index,
                        'active_index': current_index,
                    })
                    continue
                item = video_item if track == 'video' else audio_item
                content_type = (item.get('mimeType') or ('video/webm' if track == 'video' else 'audio/webm')).split(';')[0]
                debug_log('proxy true sabr segment', {
                    'vid': vid, 'track': track, 'seg': segment, 'itag': item.get('itag'),
                    'client': item.get('client'), 'len': len(media),
                    'first16': media[:16].hex(), 'request_count': meta.get('request_count'),
                    'status': meta.get('status'), 'attempt': attempt + 1,
                })
                return [200, content_type, media, {
                    'Content-Type': content_type, 'Content-Length': str(len(media)),
                    'Cache-Control': 'private, max-age=30', 'Accept-Ranges': 'none',
                }]
            except Exception as e:
                last_error = e
                client = (video_item or {}).get('client')
                debug_log('proxy true sabr error', {
                    'vid': vid, 'track': track, 'seg': segment,
                    'client': client, 'client_index': request_index,
                    'attempt': attempt + 1, 'error': repr(e),
                })
                can_failover = str(segment) == 'init' and ('SABR HTTP 403' in repr(e) or 'SABR HTTP 4' in repr(e))
                if not can_failover or not self._switch_sabr_client(vid, request_index, e):
                    break
        # 终极防 500 兜底：当所有 SABR 候选客户端在 init 或中途均触发异常（如 HTTP 403/网络断流）时，
        # 立即无缝切入本地 Super-Chunk 直链模式返回媒体段，绝不向 ExoPlayer 抛 500！
        try:
            data = self.getCache(f'yt_sabr_{vid}') or data
            video_item = req_video_item or (data or {}).get('video_item')
            audio_item = (data or {}).get('audio_item')
            item0 = video_item if track == 'video' else audio_item
            seg_ms = int(float(((item0 or {}).get('_sabr_config') or {}).get('target_duration_sec')
                        or (6 if track == 'video' else 10)) * 1000)
            if track == 'audio' and seg_ms < 8000:
                seg_ms = 10000
            if seg_ms <= 0:
                seg_ms = 6000 if track == 'video' else 10000
            dbody, dmeta = self._serve_direct_webm_segment(
                vid, track, segment, video_item, audio_item, seg_ms)
            if dbody is not None:
                content_type = ((item0 or {}).get('mimeType') or ('video/webm' if track == 'video' else 'audio/webm')).split(';')[0]
                self.setCache(f'yt_sabr_dmode_{vid}', 1)
                debug_log('sabr exception -> direct webm rescued', dmeta)
                return [200, content_type, dbody, {
                    'Content-Type': content_type, 'Content-Length': str(len(dbody)),
                    'Cache-Control': 'private, max-age=30', 'Accept-Ranges': 'none',
                }]
        except Exception as de:
            debug_log('sabr exception direct webm rescue failed', repr(de))
        return [500, 'text/plain', f'SABR 代理失败: {last_error}']
