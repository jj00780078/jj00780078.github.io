# coding=utf-8
# 极简 TVBox Py 直播源模板
# 使用方法：把直播源文本粘贴到下面的 RAW 中，保存为 .py 文件即可。
# RAW 格式示例：
# 央视,#genre#
# CCTV1,http://xxx.m3u8
# CCTV2,http://xxx.m3u8
# 卫视,#genre#
# 湖南卫视,http://xxx.m3u8

RAW = """
直播,#genre#
1所有台挂梯潘多拉完美台,http://15.204.105.50:25461/live/G2s9zK2n9m/xDtwVfWM8T/86.ts
2香蕉台,http://15.204.105.50:25461/live/G2s9zK2n9m/xDtwVfWM8T/117.ts
3惊艳台，http://15.204.105.50:25461/live/G2s9zK2n9m/xDtwVfWM8T/85.ts
4松视1台,http://15.204.105.50:25461/live/G2s9zK2n9m/xDtwVfWM8T/88.ts
5松视2台,http://15.204.105.50:25461/live/G2s9zK2n9m/xDtwVfWM8T/89.ts
6松视3台,http://15.204.105.50:25461/live/G2s9zK2n9m/xDtwVfWM8T/90.ts
7奥视台,http://125.227.210.55:1022/VideoInput/play.ts
8彩虹E台,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/8c855daa/index.m3u8
9极限电影台,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/8c855fdf/index.m3u8
10奥视2台,http://125.227.210.55:3031/VideoInput/play.ts
11惊艳台2线,http://15.204.105.50:25461/live/G2s9zK2n9m/xDtwVfWM8T/87.ts
12俄极限台,http://127.0.0.1:9978/m3u8.m3u8?url=http%3A%2F%2Fef90a6cd.rossteleccom.net%2Fiptv%2F2TBC4G2WWDG6RSUSN5SXSQEC%2F14158%2Findex.m3u8
13HAPPY,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/mdfdc125/index.m3u8
14MVLO,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/asdm3134/index.m3u8
15午夜1，http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/8jainsbq/index.m3u8
16午夜2,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/v19a2133/index.m3u8
17午夜3,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/56ffe9b8/index.m3u8
18午夜4,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/2a8cba45/index.m3u8
19午夜5,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/48a8dcb9/index.m3u8
20午夜6,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/e8f7e463/index.m3u8
21午夜7,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/846a1ghm/index.m3u8
22午夜8,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/1bf4a301/index.m3u8
23午夜9,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/84a15gbc/index.m3u8
24午夜10,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/952a3vvv/index.m3u8
25午夜11,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/984fa1vb/index.m3u8
26午夜12,http://x315601.serv00.net/cr.php?url=http://lc.aacalive.com:26789/i/ghjnvq5o/456oinav/index.m3u8
27央视3台,http://112.92.129.96:9898/hls/20/index.m3u8
28央视5台,http://112.92.129.96:9898/hls/22/index.m3u8
29央视5+,http://112.92.129.96:9898/hls/23/index.m3u8
30央视13台,http://112.92.129.96:9898/hls/31/index.m3u8
31央视16台,http://112.92.129.96:9898/hls/127/index.m3u8
32北京卫视,http://121.57.88.206:898/hls/28/index.m3u8
33深圳卫视,http://112.92.129.96:9898/hls/16/index.m3u8
34东方卫视,http://112.92.129.96:9898/hls/36/index.m3u8
35江苏卫视,http://112.92.129.96:9898/hls/38/index.m3u8
36湖南卫视,http://121.57.88.206:898/hls/32/index.m3u8
37浙江卫视,http://121.57.88.206:898/hls/20/index.m3u8
38辽宁卫视,http://121.57.88.206:898/hls/24/index.m3u8
39河南卫视,http://112.92.129.96:9898/hls/66/index.m3u8
40山东卫视,http://112.92.129.96:9898/hls/41/index.m3u8



"""

import sys
sys.path.append('..')
from base.spider import Spider

def parse_raw(text):
    groups = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '#genre#' in line:
            gname = line.split(',')[0].strip()
            if gname:
                current = {'name': gname, 'channels': []}
                groups.append(current)
            continue
        if ',' in line:
            name, url = line.split(',', 1)
            name, url = name.strip(), url.strip()
            if name and url:
                if current is None:
                    current = {'name': '直播', 'channels': []}
                    groups.append(current)
                current['channels'].append({'name': name, 'url': url})
    return groups

CHANNELS = parse_raw(RAW)
CLASSES = [{'type_name': g['name'], 'type_id': str(i)} for i, g in enumerate(CHANNELS)]

class Spider(Spider):
    def getName(self):
        return "我的直播源"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def homeContent(self, filter):
        return {'class': CLASSES}

    def categoryContent(self, tid, pg, filter, extend):
        tid = int(tid)
        group = CHANNELS[tid]['channels']
        videos = []
        for idx, ch in enumerate(group):
            videos.append({
                'vod_id': f"{tid}_{idx}",
                'vod_name': ch['name'],
                'vod_pic': '',
                'vod_remarks': CHANNELS[tid]['name'],
                'vod_play_url': ch['url']
            })
        return {'list': videos, 'page': pg, 'pagecount': 1, 'limit': len(videos), 'total': len(videos)}

    def detailContent(self, ids):
        vid = ids[0]
        tid, idx = vid.split('_')
        tid = int(tid)
        idx = int(idx)
        ch = CHANNELS[tid]['channels'][idx]
        vod = {
            'vod_id': vid,
            'vod_name': ch['name'],
            'vod_pic': '',
            'vod_remarks': CHANNELS[tid]['name'],
            'vod_content': ch['name'],
            'vod_play_from': '直播',
            'vod_play_url': ch['url']
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'playUrl': '', 'url': id, 'header': ''}