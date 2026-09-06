# coding=utf-8
#!/usr/bin/python
import re
import sys
import json
import time
import base64
import hashlib
import random
import urllib.parse
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from base.spider import Spider

sys.path.append('..')

class Spider(Spider):
    def __init__(self):
        self.name = "瓜子"
        self.hosts = [
            'https://apinew.uozvr.com',
            'https://api.w32z7vtd.com',
            'https://api.6a7nnf7.com',
            'https://api.umygrx3.com',
            'https://api.rmedphk.com'
        ]
        self.host = self.hosts[0]
        self.aes_key = 'OITxa5OqAYjhswxx'
        self.aes_iv = 'rCMNwZASNBKZ8mXV'
        self.device_old_key = 'aLFBMWpxBrIDAD1Si/KVvm41'
        self.rsa_public_key = 'MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDUM5+/y8sPsWkd1/RQS64X259EUwxFXFE5HlA65MqrxnPs0JqoSRojSDy5QhwvROlaD6TwRQHKMY2OAZ6SnQeUJsChTEFIR9qUkwrs3/MVUMxjsv6JS6Oe/juclyJGTgVmDhB55EafXsD0SQYVj/QXXsxR6ewR5E2kL52yAAD4yQIDAQAB'
        self.rsa_private_key = """-----BEGIN RSA PRIVATE KEY-----
MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1
ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU
1wNr648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcK
ZT3wj/cCI1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7
HetybTh/j2p0Y1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcW
V9FmlVXr8VhfBzcZo1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdI
DblMAg+wiKKZ5KcdAkEA1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34
saTJnLWIHC8IXys6Qmzz30TtzCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVM
iMPhnwe/bXEehShK86yJK/g/UiKrO87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUM
WBsCQQChfhTIrdDinKi6lRxrdBnn0Ohjg2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8
jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X8nhx6AXsgCYRql1klbqtVmL8+95KZ
K7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzjE/oTXcByS+6XRQJAP/5ciy1b
L3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19mVq1feMbCXhz+L1rG8oa
t5lYKfpe8k83ZA==
-----END RSA PRIVATE KEY-----"""
        self.token = ''
        self.token_id = ''
        self.device_id = str(864150060000000 + random.randint(0, 9999))
        self.device_key = ''.join(random.choices('0123456789ABCDEF', k=40))
        self.registered = False
        self.token_ready = False
        # 分类映射 - sub参数对应值
        self.sub_map = {
            "1": "5",    # 电影
            "2": "12",   # 国产剧
            "3": "30",   # 综艺
            "4": "22",   # 动漫
            "64": ""     # 短剧
        }
        self.header = {
            'User-Agent': 'Lavf/57.83.100',
            'code': 'GZ0369',
            'deviceId': self.device_id,
            'lang': 'zh_cn',
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Version': '2604028',
            'PackageName': 'com.ae06aebdbb.y286327f5a.ofe849883320260517',
            'Ver': '3.0.3.2',
            'api-ver': '3.0.3.2'
        }
        self.cache = {}
        self.cache_timeout = 300

    def getName(self):
        return self.name

    def init(self, extend=''):
        for h in self.hosts:
            try:
                res = self.fetch(h, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res and res.status_code == 200:
                    self.host = h
                    break
            except:
                continue
        self.load_auth()
        try:
            self.ensure_token()
        except:
            pass

    def load_auth(self):
        if self.token and self.device_id and self.device_key:
            return
        self.device_id = str(864150060000000 + random.randint(0, 9999))
        self.device_key = ''.join(random.choices('0123456789ABCDEF', k=40))
        self.token = ''
        self.token_id = ''
        self.registered = False
        self.token_ready = False

    def ensure_token(self):
        if self.token_ready and self.token:
            return
        if not self.token:
            if self.registered:
                self.sign_in()
            else:
                self.sign_up()
        try:
            result = self.api_request('/App/Authentication/Authenticator/refresh', {}, 0)
            self.apply_auth(result)
        except Exception as e:
            if not self.registered:
                raise e
            self.sign_in()
        self.token_ready = True

    def sign_up(self):
        params = {
            'new_key': self.device_key,
            'old_key': self.device_old_key,
            'phone_type': 1,
            'code': ''
        }
        result = self.api_request('/App/Authentication/Device/signUp', params, 0)
        self.apply_auth(result)
        self.registered = True

    def sign_in(self):
        params = {
            'new_key': self.device_key,
            'old_key': self.device_old_key
        }
        result = self.api_request('/App/Authentication/Device/signIn', params, 0)
        self.apply_auth(result)

    def apply_auth(self, result):
        new_token = result.get('token', '')
        if not new_token:
            raise Exception('Token获取失败')
        self.token = new_token
        new_token_id = result.get('app_user_id', '')
        if new_token_id:
            self.token_id = new_token_id

    def homeContent(self, filter):
        result = {}
        classes = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "国产剧", "type_id": "2"},
            {"type_name": "综艺", "type_id": "4"},
            {"type_name": "短剧", "type_id": "64"},
            {"type_name": "动漫", "type_id": "3"},
            {"type_name": "海外剧", "type_id": "5"}
        ]
        result['class'] = classes
        
        # ========== 筛选配置 ==========
        filters = {}
        for cate in classes:
            tid = cate['type_id']
            filter_list = [
                # 地区筛选
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "大陆", "v": "大陆"},
                    {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"},
                    {"n": "美国", "v": "美国"},
                    {"n": "韩国", "v": "韩国"},
                    {"n": "日本", "v": "日本"},
                    {"n": "英国", "v": "英国"},
                    {"n": "法国", "v": "法国"},
                    {"n": "泰国", "v": "泰国"},
                    {"n": "印度", "v": "印度"},
                    {"n": "其他", "v": "其他"}
                ]},
                # 年份筛选
                {"key": "year", "name": "年份", "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "2026", "v": "2026"},
                    {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"},
                    {"n": "2023", "v": "2023"},
                    {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"},
                    {"n": "2020", "v": "2020"},
                    {"n": "2019", "v": "2019"},
                    {"n": "2018", "v": "2018"},
                    {"n": "2017", "v": "2017"},
                    {"n": "2016", "v": "2016"},
                    {"n": "2015", "v": "2015"},
                    {"n": "2014", "v": "2014"},
                    {"n": "2013", "v": "2013"},
                    {"n": "2012", "v": "2012"},
                    {"n": "2011", "v": "2011"},
                    {"n": "2010", "v": "2010"},
                    {"n": "2009", "v": "2009"},
                    {"n": "2008", "v": "2008"},
                    {"n": "2007", "v": "2007"},
                    {"n": "2006", "v": "2006"},
                    {"n": "2005", "v": "2005"},
                    {"n": "更早", "v": "2004"}
                ]},
                # 排序筛选
                {"key": "sort", "name": "排序", "value": [
                    {"n": "最新", "v": "d_id"},
                    {"n": "最热", "v": "d_hits"},
                    {"n": "推荐", "v": "d_score"}
                ]}
            ]
            
            # 子类型筛选 - 不同分类有不同的子类型
            if tid == "1":  # 电影
                filter_list.insert(0, {"key": "sub", "name": "类型", "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "动作", "v": "6"},
                    {"n": "喜剧", "v": "7"},
                    {"n": "爱情", "v": "8"},
                    {"n": "科幻", "v": "9"},
                    {"n": "恐怖", "v": "10"},
                    {"n": "剧情", "v": "11"},
                    {"n": "战争", "v": "24"}
                ]})
            elif tid == "2":  # 国产剧
                filter_list.insert(0, {"key": "sub", "name": "类型", "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "古装", "v": "13"},
                    {"n": "言情", "v": "14"},
                    {"n": "武侠", "v": "15"},
                    {"n": "都市", "v": "16"},
                    {"n": "历史", "v": "17"},
                    {"n": "悬疑", "v": "25"}
                ]})
            elif tid == "3":  # 综艺
                filter_list.insert(0, {"key": "sub", "name": "类型", "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "真人秀", "v": "31"},
                    {"n": "选秀", "v": "32"},
                    {"n": "情感", "v": "33"},
                    {"n": "访谈", "v": "34"},
                    {"n": "音乐", "v": "35"}
                ]})
            elif tid == "4":  # 动漫
                filter_list.insert(0, {"key": "sub", "name": "类型", "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "国产", "v": "23"},
                    {"n": "日本", "v": "21"},
                    {"n": "欧美", "v": "26"},
                    {"n": "其他", "v": "27"}
                ]})
            elif tid == "64":  # 短剧
                filter_list.insert(0, {"key": "sub", "name": "类型", "value": [
                    {"n": "全部", "v": "0"},
                    {"n": "男频", "v": "65"},
                    {"n": "女频", "v": "66"}
                ]})
            
            filters[tid] = filter_list
        
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        try:
            params = {'pid': '1'}
            data = self.api_request('/App/IndexList/index', params, 0)
            vods = []
            if data and 'list' in data and len(data['list']) > 1:
                for i in range(1, len(data['list'])):
                    item = data['list'][i]
                    vods.extend(self.parse_vod_list(item))
            return {'list': vods}
        except:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        videos = []
        try:
            # 获取sub参数：优先用extend传入的，否则用默认值
            sub = extend.get('sub', self.sub_map.get(tid, '0'))
            
            params = {
                'area': extend.get('area', '0'),
                'year': extend.get('year', '0'),
                'pageSize': '30',
                'sort': extend.get('sort', 'd_id'),
                'page': str(pg),
                'tid': tid,
                'sub': sub
            }
            
            cache_key = f"category_{tid}_{pg}_{hash(str(params))}"
            data = self.get_cached_data(cache_key, params, '/App/IndexList/indexList')
            videos = self.parse_vod_list(data)
        except Exception as e:
            print(f"分类获取失败: {e}")
        
        return {
            'list': videos,
            'page': int(pg),
            'pagecount': 9999,
            'limit': 30,
            'total': 999999
        }

    def detailContent(self, ids):
        try:
            self.ensure_token()
            vod_id = ids[0].split('/')[0] if '/' in ids[0] else ids[0]
            
            params1 = {
                'token_id': self.token_id,
                'vod_id': vod_id,
                'mobile_time': str(int(time.time())),
                'token': self.token
            }
            play_info = self.api_request('/App/IndexPlay/playInfo', params1, 0)
            
            params2 = {
                'vurl_cloud_id': '2',
                'vod_d_id': vod_id
            }
            vurl_info = self.api_request('/App/Resource/Vurl/show', params2, 0)
            
            vod_info = play_info.get('vodInfo', {})
            
            # 解析播放列表 - 每个画质作为一个播放源
            quality_episodes = {}
            quality_order = []
            
            vurl_list = vurl_info.get('list', [])
            if isinstance(vurl_list, list):
                for i, item in enumerate(vurl_list):
                    play_obj = item.get('play', {})
                    ep_name = vod_info.get('vod_name', '') if len(vurl_list) == 1 else str(i + 1)
                    
                    for quality, ep in play_obj.items():
                        if isinstance(ep, dict) and ep.get('param'):
                            param = ep.get('param', '')
                            if param:
                                if quality not in quality_episodes:
                                    quality_episodes[quality] = []
                                    quality_order.append(quality)
                                quality_episodes[quality].append(f"{ep_name}${param}||{quality}")
            
            # 按画质从高到低排序
            quality_order.sort(key=lambda q: self.get_quality_value(q), reverse=True)
            
            play_from_list = []
            play_url_list = []
            for quality in quality_order:
                play_from_list.append(quality)
                play_url_list.append('#'.join(quality_episodes[quality]))
            
            video_detail = {
                'vod_id': vod_id,
                'vod_name': vod_info.get('vod_name', ''),
                'vod_pic': vod_info.get('vod_pic', '') + '@User-Agent=Dalvik/2.1.0',
                'vod_year': vod_info.get('vod_year', ''),
                'vod_area': vod_info.get('vod_area', ''),
                'vod_actor': vod_info.get('vod_actor', ''),
                'vod_director': vod_info.get('vod_director', ''),
                'vod_content': vod_info.get('vod_use_content', '').replace('\u3000', '\n').strip(),
                'vod_play_from': '$$$'.join(play_from_list) if play_from_list else '瓜子视频',
                'vod_play_url': '$$$'.join(play_url_list)
            }
            
            return {'list': [video_detail]}
        except Exception as e:
            print(f"详情获取失败: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        videos = []
        try:
            params = {
                'keywords': key,
                'order_val': '1'
            }
            data = self.api_request('/App/Index/findMoreVod', params, 0)
            videos = self.parse_vod_list(data)
        except Exception as e:
            print(f"搜索失败: {e}")
        
        return {
            'list': videos,
            'page': int(pg),
            'pagecount': 9999,
            'limit': 30,
            'total': 999999
        }

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = id.split('||')
            params_str = parts[0]
            resolution = parts[1] if len(parts) > 1 else flag
            
            param_map = {}
            for param in params_str.split('&'):
                kv = param.split('=')
                if len(kv) == 2:
                    key = 'vod_id' if kv[0] == 'vod_d_id' else kv[0]
                    param_map[key] = kv[1]
            param_map['resolution'] = resolution
            
            result = self.api_request('/App/Resource/VurlDetail/showOne', param_map, 0)
            url = result.get('url', '')
            
            return {
                'parse': 0,
                'playUrl': '',
                'url': url,
                'header': json.dumps({
                    'User-Agent': 'Lavf/57.83.100',
                    'Referer': 'http://WJiZxLXA2.com/'
                })
            }
        except Exception as e:
            print(f"播放解析失败: {e}")
            return {'parse': 0, 'playUrl': '', 'url': ''}

    def parse_vod_list(self, data):
        vods = []
        if not data or 'list' not in data:
            return vods
        
        for item in data['list']:
            continu = item.get('vod_continu', 0)
            total = item.get('d_total', 0)
            
            if total and str(total) != '0' and continu and str(continu) != '0':
                if str(continu) == str(total):
                    remarks = f'全{total}集'
                else:
                    remarks = f'更新至{continu}集'
            else:
                remarks = item.get('vod_year', item.get('vod_scroe', ''))
            
            vods.append({
                'vod_id': f"{item.get('vod_id', '')}/{continu}",
                'vod_name': item.get('vod_name', ''),
                'vod_pic': item.get('vod_pic', '') + '@User-Agent=Dalvik/2.1.0',
                'vod_remarks': remarks
            })
        return vods

    def get_quality_value(self, quality):
        if not quality:
            return 0
        q = quality.upper()
        if '4K' in q or '2160' in q:
            return 2160
        if '1080' in q:
            return 1080
        if '720' in q:
            return 720
        if '480' in q:
            return 480
        if '360' in q:
            return 360
        nums = re.findall(r'\d+', q)
        if nums:
            return int(nums[0])
        return 0

    def get_cached_data(self, cache_key, data, path):
        current_time = time.time()
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if current_time - timestamp < self.cache_timeout:
                return cached_data
        result = self.api_request(path, data, 0)
        if result:
            self.cache[cache_key] = (result, current_time)
        return result

    def api_request(self, path, params, retry=0):
        auth_path = path.startswith('/App/Authentication/')
        if not auth_path:
            self.ensure_token()
        
        request_params = dict(params)
        if 'token' in request_params:
            request_params['token'] = self.token
        if 'token_id' in request_params:
            request_params['token_id'] = self.token_id
        
        json_params = json.dumps(request_params, ensure_ascii=False)
        encrypted = self.aes_encrypt(json_params.encode('utf-8'), self.aes_key.encode('utf-8'), self.aes_iv.encode('utf-8'))
        request_key = encrypted.hex().upper()
        timestamp = str(int(time.time()))
        keys = self.rsa_encrypt(json.dumps({'iv': self.aes_iv, 'key': self.aes_key}), self.rsa_public_key)
        
        sign_str = f"token_id=,token={self.token},phone_type=1,request_key={request_key},app_id=1,time={timestamp},keys={keys}*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br"
        signature = hashlib.md5(sign_str.encode('utf-8')).hexdigest().upper()
        
        body = {
            'token': self.token,
            'token_id': '',
            'phone_type': '1',
            'time': timestamp,
            'phone_model': 'xiaomi-25031',
            'keys': keys,
            'request_key': request_key,
            'signature': signature,
            'app_id': '1',
            'ad_version': '1'
        }
        
        url = f"{self.host}{path}"
        response = self.post(url, headers=self.header, data=body, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"请求失败: {response.status_code}")
        
        resp_json = response.json()
        
        if resp_json.get('code') != 200:
            if retry < 1 and not auth_path:
                self.token_ready = False
                self.ensure_token()
                return self.api_request(path, params, retry + 1)
            raise Exception(f"API错误: {resp_json}")
        
        data = resp_json.get('data', {})
        encrypted_data = data.get('response_key', '')
        key_data = data.get('keys', '')
        
        decrypted_info = self.rsa_decrypt(key_data, self.rsa_private_key)
        key_info = json.loads(decrypted_info)
        
        decrypted = self.aes_decrypt(
            bytes.fromhex(encrypted_data),
            key_info['key'].encode('utf-8'),
            key_info['iv'].encode('utf-8')
        )
        return json.loads(decrypted.decode('utf-8'))

    def aes_encrypt(self, data, key, iv):
        try:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            return cipher.encrypt(pad(data, AES.block_size))
        except Exception as e:
            print(f"AES加密失败: {e}")
            return b''

    def aes_decrypt(self, data, key, iv):
        try:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            return unpad(cipher.decrypt(data), AES.block_size)
        except Exception as e:
            print(f"AES解密失败: {e}")
            return b''

    def rsa_encrypt(self, data, public_key):
        try:
            key_bytes = base64.b64decode(public_key)
            public_key_obj = RSA.import_key(key_bytes)
            cipher = PKCS1_v1_5.new(public_key_obj)
            encrypted = cipher.encrypt(data.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            print(f"RSA加密失败: {e}")
            return ''

    def rsa_decrypt(self, encrypted_data, private_key):
        try:
            encrypted_bytes = base64.b64decode(encrypted_data)
            rsa_key = RSA.import_key(private_key)
            cipher = PKCS1_v1_5.new(rsa_key)
            decrypted = cipher.decrypt(encrypted_bytes, None)
            return decrypted.decode('utf-8') if decrypted else ''
        except Exception as e:
            print(f"RSA解密失败: {e}")
            return ''

    def isVideoFormat(self, url):
        video_formats = ['.m3u8', '.mp4', '.avi', '.mkv', '.flv', '.ts']
        return any(url.lower().endswith(fmt) for fmt in video_formats)

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None

    def destroy(self):
        pass

if __name__ == '__main__':
    pass
