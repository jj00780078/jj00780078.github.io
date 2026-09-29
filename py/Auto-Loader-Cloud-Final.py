# -*- coding: utf-8 -*-
# Cloud Auto Loader v3.3 - Fixed exec
# Shows [Click Me] option, exec writes registry.json with robust paths

try:
    from base.spider import Spider as BaseSpider
except:
    class BaseSpider:
        pass

import json, os, hashlib, urllib.request, urllib.parse, traceback

def find_writable_registry():
    candidates = [
        "/sdcard/TV/CustomCsp/registry.json",
        "/sdcard/tvbox/CustomCsp/registry.json",
        "/storage/emulated/0/TV/CustomCsp/registry.json",
        "/storage/emulated/0/tvbox/CustomCsp/registry.json",
        "/sdcard/TVBox/CustomCsp/registry.json",
        "/sdcard/TV/Custom/registry.json",
    ]
    for p in candidates:
        try:
            d = os.path.dirname(p)
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
            # test write
            test_file = os.path.join(d, ".write_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            return p
        except:
            continue
    # fallback: try to find any existing registry.json
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]

def fetch_py_list():
    user = "jj00780078"
    repo = "jj00780078.github.io"
    branch = "main"
    dir_name = "py"
    # Use multiple mirrors for API
    api_urls = [
        f"https://api.github.com/repos/{user}/{repo}/contents/{dir_name}?ref={branch}",
        f"https://ghproxy.com/https://api.github.com/repos/{user}/{repo}/contents/{dir_name}?ref={branch}",
        f"https://api.github.moeyy.xyz/repos/{user}/{repo}/contents/{dir_name}?ref={branch}",
    ]
    raw_base = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{dir_name}"
    raw_base_proxy = f"https://ghproxy.com/https://raw.githubusercontent.com/{user}/{repo}/{branch}/{dir_name}"

    last_error = ""
    for api_url in api_urls:
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode('utf-8'))
                files = []
                for it in data:
                    if it.get("type") == "file" and it.get("name","").endswith(".py"):
                        name = it["name"]
                        if "auto_loader" in name or "test_loader" in name:
                            continue
                        try:
                            name.encode('ascii')
                        except:
                            continue
                        # Use download_url if present, else build
                        url = it.get("download_url")
                        if not url:
                            url = f"{raw_base}/{urllib.parse.quote(name)}"
                        # Replace with proxy version to help TVBox load later
                        # Keep both: raw url for storage, but we will use ghproxy for player
                        files.append({"name": name, "url": url, "url_proxy": f"{raw_base_proxy}/{urllib.parse.quote(name)}"})
                if files:
                    return files, f"OK via {api_url}"
        except Exception as e:
            last_error = f"{api_url} -> {e}"
            continue

    return [], f"All API failed, last: {last_error}"

class Spider(BaseSpider):
    def getName(self):
        return "CloudAutoLoader v3.3"

    def init(self, extend=""):
        self.log_path = "/sdcard/tvbox/py/loader_log.txt"
        self.registry_path = find_writable_registry()

    def _log(self, msg):
        try:
            d = os.path.dirname(self.log_path)
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(msg + "\n")
        except:
            pass

    def homeContent(self, filter):
        reg = self.registry_path
        videos = [
            {
                "vod_id": "scan",
                "vod_name": "[点我] 一键扫描GitHub并写入 registry.json",
                "vod_pic": "",
                "vod_remarks": f"目标: {reg}"
            },
            {
                "vod_id": "show_registry",
                "vod_name": f"[查看] 当前registry路径: {reg}",
                "vod_pic": "",
                "vod_remarks": "点击查看已加载源数量"
            },
            {
                "vod_id": "show_log",
                "vod_name": "[查看] 执行日志 loader_log.txt",
                "vod_pic": "",
                "vod_remarks": "/sdcard/tvbox/py/loader_log.txt"
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
            "vod_name": "CloudAutoLoader v3.3",
            "vod_pic": "",
            "vod_remarks": "操作项",
            "vod_content": f"ID: {vid}\nRegistry: {self.registry_path}\nLog: {self.log_path}"
        }
        play_url = f"执行扫描${vid}"
        return {
            "list": [vod],
            "vod": {"vod_play_from": "操作", "vod_play_url": play_url}
        }

    def _write_registry(self, py_files):
        reg_path = self.registry_path
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
                self._log(f"Existing registry parse failed, creating new")

        manual = [s for s in existing.get("sites", []) if not str(s.get("key","")).startswith("local_auto_")]
        auto = []
        for pf in py_files:
            raw_name = pf["name"].replace(".py","")
            key = "local_auto_" + hashlib.md5(pf["url"].encode()).hexdigest()[:10]
            # 使用代理URL，提高盒子加载成功率
            api_url = pf.get("url_proxy") or pf["url"]
            auto.append({
                "key": key,
                "name": raw_name,
                "type": 3,
                "api": api_url,
                "searchable": 1,
                "quickSearch": 1
            })
        existing["sites"] = manual + auto

        # backup
        try:
            if os.path.exists(reg_path):
                with open(reg_path, 'r', encoding='utf-8') as f:
                    old = f.read()
                with open(reg_path + ".bak", 'w', encoding='utf-8') as f:
                    f.write(old)
        except Exception as e:
            self._log(f"Backup failed: {e}")

        with open(reg_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        return len(auto), len(manual), reg_path

    def playerContent(self, flag, id, vipFlags):
        self._log(f"=== playerContent called id={id} ===")
        try:
            if id == "scan":
                self._log("Start fetch_py_list")
                py_list, msg = fetch_py_list()
                self._log(f"fetch result: {len(py_list)} files, msg={msg}")
                if not py_list:
                    err = f"扫描失败: {msg}\n请检查:\n1. GitHub仓库 { 'jj00780078/jj00780078.github.io' } 是否public\n2. py文件夹下是否有英文名.py文件\n3. 盒子能否访问 api.github.com (尝试用ghproxy)\n已记录到 {self.log_path}"
                    self._log(err)
                    return {"parse": 0, "url": "", "header": {}, "msg": err}

                self._log(f"Start _write_registry to {self.registry_path}")
                added, kept, path = self._write_registry(py_list)
                success_msg = f"成功! 新增{added}个云端源, 保留{kept}个手工源\n已写入: {path}\n文件列表: {', '.join([p['name'] for p in py_list[:10]])}\n请返回重载配置"
                self._log(success_msg)
                # 返回一个可播放的空地址，但带msg提示
                return {"parse": 0, "url": "", "header": {}, "msg": success_msg}

            elif id == "show_registry":
                if os.path.exists(self.registry_path):
                    with open(self.registry_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    count = len(data.get("sites", []))
                    auto_count = len([s for s in data.get("sites", []) if str(s.get("key","")).startswith("local_auto_")])
                    msg = f"Registry: {self.registry_path}\n总数: {count}\n自动加载: {auto_count}\n手工: {count-auto_count}"
                    return {"parse": 0, "url": "", "header": {}, "msg": msg}
                else:
                    return {"parse": 0, "url": "", "header": {}, "msg": f"文件不存在: {self.registry_path}"}

            elif id == "show_log":
                if os.path.exists(self.log_path):
                    with open(self.log_path, 'r', encoding='utf-8') as f:
                        content = f.read()[-1000:]
                    return {"parse": 0, "url": "", "header": {}, "msg": content}
                else:
                    return {"parse": 0, "url": "", "header": {}, "msg": f"日志不存在: {self.log_path}"}
            else:
                return {"parse": 0, "url": id, "header": {}, "msg": ""}
        except Exception as e:
            err = f"执行异常: {e}\n{traceback.format_exc()}"
            self._log(err)
            return {"parse": 0, "url": "", "header": {}, "msg": err}

    def searchContent(self, key, quick):
        return {"list": []}

    def isVideoFormat(self, url):
        return False
    def manualVideoCheck(self):
        return False
    def destroy(self):
        pass
