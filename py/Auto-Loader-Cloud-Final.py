# -*- coding: utf-8 -*-
from base.spider import Spider as BaseSpider
import json, os, hashlib, urllib.request, urllib.parse

STORAGE_ROOT = "/sdcard"

class Spider(BaseSpider):
    def getName(self):
        return "CloudAutoLoader"

    def init(self, extend=""):
        self.extend = extend

    def homeContent(self, filter):
        # 首页不做任何网络请求，保证一定能显示
        # 如果这里都显示不了，就是文件本身没上传对
        videos = [
            {
                "vod_id": "scan",
                "vod_name": "[点我] 一键扫描GitHub py文件夹",
                "vod_pic": "",
                "vod_remarks": "jj00780078.github.io/py"
            },
            {
                "vod_id": "https://raw.githubusercontent.com/jj00780078/jj00780078.github.io/main/py/nangua.py",
                "vod_name": "测试: nangua.py",
                "vod_pic": "",
                "vod_remarks": "示例文件"
            }
        ]
        return {
            "class": [{"type_name": "云端", "type_id": "1"}],
            "list": videos,
            "filters": {}
        }

    def categoryContent(self, tid, pg, filter, extend):
        return self.homeContent(filter)

    def detailContent(self, array):
        vid = array[0]
        vod = {
            "vod_id": vid,
            "vod_name": "云端自动加载",
            "vod_pic": "",
            "vod_remarks": "点击播放执行操作",
            "vod_content": f"ID: {vid}"
        }
        # 两个播放源
        play_url = f"执行一键扫描并写入registry$scan"
        if vid.startswith("http"):
            play_url = f"单独测试播放${vid}"
        return {
            "list": [vod],
            "vod": {
                "vod_play_from": "操作",
                "vod_play_url": play_url
            }
        }

    def _get_py_list(self):
        user = "jj00780078"
        repo = "jj00780078.github.io"
        branch = "main"
        dir_name = "py"
        api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{dir_name}?ref={branch}"
        raw_base = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{dir_name}"
        files = []
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "TVBox"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode('utf-8'))
                for it in data:
                    if it.get("type") == "file" and it.get("name","").endswith(".py"):
                        name = it["name"]
                        if "auto_loader" in name:
                            continue
                        # 跳过中文文件名，避免ascii错误
                        try:
                            name.encode('ascii')
                        except:
                            continue
                        url = it.get("download_url") or f"{raw_base}/{urllib.parse.quote(name)}"
                        files.append({"name": name, "url": url})
        except Exception as e:
            # API失败，返回空，但不崩溃
            print(f"GitHub API error: {e}")
        return files

    def _write_registry(self, py_files):
        reg_path = os.path.join(STORAGE_ROOT, "TV", "CustomCsp", "registry.json")
        try:
            os.makedirs(os.path.dirname(reg_path), exist_ok=True)
        except:
            pass
        existing = {"sites": []}
        if os.path.exists(reg_path):
            try:
                with open(reg_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                existing = {"sites": []}
        manual = [s for s in existing.get("sites", []) if not str(s.get("key","")).startswith("local_auto_")]
        auto = []
        for pf in py_files:
            raw_name = pf["name"].replace(".py","")
            key = "local_auto_" + hashlib.md5(pf["url"].encode()).hexdigest()[:10]
            auto.append({
                "key": key,
                "name": raw_name,
                "type": 3,
                "api": pf["url"],
                "searchable": 1,
                "quickSearch": 1
            })
        existing["sites"] = manual + auto
        # 备份
        try:
            if os.path.exists(reg_path):
                with open(reg_path, 'r', encoding='utf-8') as f:
                    old = f.read()
                with open(reg_path + ".bak", 'w', encoding='utf-8') as f:
                    f.write(old)
        except:
            pass
        with open(reg_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return len(auto), len(manual), reg_path

    def playerContent(self, flag, id, vipFlags):
        # id 就是 vod_id
        if id == "scan":
            py_list = self._get_py_list()
            if not py_list:
                return {"parse":0,"url":"","header":{},"msg":"扫描失败: GitHub API未返回数据，请检查 1.仓库是否为public 2.py文件夹下是否有英文名.py 3.盒子网络能否访问api.github.com"}
            try:
                added, kept, path = self._write_registry(py_list)
                return {"parse":0,"url":"","header":{},"msg":f"成功! 新增{added}个, 保留{kept}个, 已写入 {path}，请返回首页重载"}
            except Exception as e:
                return {"parse":0,"url":"","header":{},"msg":f"写入失败: {e}"}
        else:
            # 直接返回url让TVBox尝试播放测试
            return {"parse":0,"url":id,"header":{},"msg":""}

    def searchContent(self, key, quick):
        return {"list": []}

    def isVideoFormat(self, url):
        return False
    def manualVideoCheck(self):
        return False
    def destroy(self):
        pass
