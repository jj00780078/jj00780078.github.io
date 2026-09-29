# -*- coding: utf-8 -*-
# Cloud Auto Loader v3.4 - Detail exec, not player
# Fix: move scan from playerContent to detailContent

try:
    from base.spider import Spider as BaseSpider
except:
    class BaseSpider:
        pass

import json, os, hashlib, urllib.request, urllib.parse, traceback, time

def find_registry():
    cands = [
        "/sdcard/TV/CustomCsp/registry.json",
        "/sdcard/tvbox/CustomCsp/registry.json",
        "/storage/emulated/0/TV/CustomCsp/registry.json",
        "/storage/emulated/0/tvbox/CustomCsp/registry.json",
        "/sdcard/TVBox/CustomCsp/registry.json",
    ]
    for p in cands:
        try:
            d = os.path.dirname(p)
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
            return p
        except:
            continue
    return cands[0]

def fetch_py_list():
    user = "jj00780078"
    repo = "jj00780078.github.io"
    branch = "main"
    dir_name = "py"
    api_urls = [
        f"https://api.github.com/repos/{user}/{repo}/contents/{dir_name}?ref={branch}",
        f"https://ghproxy.com/https://api.github.com/repos/{user}/{repo}/contents/{dir_name}?ref={branch}",
        f"https://api.github.moeyy.xyz/repos/{user}/{repo}/contents/{dir_name}?ref={branch}",
    ]
    raw_base = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{dir_name}"
    raw_proxy = f"https://ghproxy.com/https://raw.githubusercontent.com/{user}/{repo}/{branch}/{dir_name}"

    for api_url in api_urls:
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode('utf-8'))
                files = []
                for it in data:
                    if it.get("type") == "file" and str(it.get("name","")).endswith(".py"):
                        name = it["name"]
                        if "auto_loader" in name or "test_loader" in name:
                            continue
                        try:
                            name.encode('ascii')
                        except:
                            continue
                        url = it.get("download_url") or f"{raw_base}/{urllib.parse.quote(name)}"
                        files.append({"name": name, "url": url, "url_proxy": f"{raw_proxy}/{urllib.parse.quote(name)}"})
                if files:
                    return files, f"OK via {api_url}"
        except Exception as e:
            last = str(e)
            continue
    return [], f"API all failed: {last}"

def write_registry(py_files, reg_path):
    os.makedirs(os.path.dirname(reg_path), exist_ok=True)
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
        api_url = pf.get("url_proxy") or pf["url"]
        auto.append({"key": key, "name": raw_name, "type": 3, "api": api_url, "searchable": 1, "quickSearch": 1})
    existing["sites"] = manual + auto
    try:
        if os.path.exists(reg_path):
            os.rename(reg_path, reg_path + ".bak." + str(int(time.time())))
    except:
        pass
    with open(reg_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return len(auto), len(manual)

class Spider(BaseSpider):
    def getName(self):
        return "CloudLoader v3.4"

    def init(self, extend=""):
        self.reg_path = find_registry()

    def homeContent(self, filter):
        # 首页显示3个入口
        return {
            "class": [{"type_name": "Cloud", "type_id": "1"}],
            "list": [
                {"vod_id": "scan", "vod_name": "1. [CLICK ME] Scan GitHub and Write Registry", "vod_pic": "", "vod_remarks": "Click to execute"},
                {"vod_id": "view_reg", "vod_name": "2. [View] Current Registry", "vod_pic": "", "vod_remarks": self.reg_path},
                {"vod_id": "view_list", "vod_name": "3. [View] GitHub py list", "vod_pic": "", "vod_remarks": "List files"},
            ],
            "filters": {}
        }

    def categoryContent(self, tid, pg, filter, extend):
        return self.homeContent(filter)

    def detailContent(self, array):
        vid = array[0]
        content = ""
        play_from = "Result"
        play_url = ""

        if vid == "scan":
            try:
                py_list, msg = fetch_py_list()
                if not py_list:
                    content = f"SCAN FAILED\n{msg}\n\nPlease check:\n- Repo is public: jj00780078/jj00780078.github.io\n- py/ folder has English .py files\n- Box can access api.github.com or ghproxy.com\n\nCurrent reg path: {self.reg_path}"
                    play_url = ""
                else:
                    added, kept = write_registry(py_list, self.reg_path)
                    file_names = "\n".join([f"- {p['name']} -> {p['url_proxy']}" for p in py_list])
                    content = f"SCAN SUCCESS!\n\nAdded: {added}\nKept manual: {kept}\nWrote to: {self.reg_path}\n\nFiles:\n{file_names}\n\nNEXT: Go back and Reload Config in TVBox settings.\nIf new sources not show, restart TVBox app."
                    play_url = ""
            except Exception as e:
                content = f"EXCEPTION in scan:\n{e}\n{traceback.format_exc()}\n\nReg path: {self.reg_path}"

        elif vid == "view_reg":
            try:
                if os.path.exists(self.reg_path):
                    with open(self.reg_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    sites = data.get("sites", [])
                    auto = [s for s in sites if str(s.get("key","")).startswith("local_auto_")]
                    manual = [s for s in sites if not str(s.get("key","")).startswith("local_auto_")]
                    content = f"Registry: {self.reg_path}\nTotal: {len(sites)}\nAuto: {len(auto)}\nManual: {len(manual)}\n\nAuto list:\n" + "\n".join([f"- {s.get('name')} | {s.get('key')}" for s in auto[:20]])
                else:
                    content = f"Registry file NOT exist: {self.reg_path}\nPlease run scan first."
            except Exception as e:
                content = f"Read registry failed: {e}\n{traceback.format_exc()}"

        elif vid == "view_list":
            try:
                py_list, msg = fetch_py_list()
                if not py_list:
                    content = f"Fetch failed: {msg}"
                else:
                    content = f"GitHub py/ list ({len(py_list)} files) via {msg}:\n\n" + "\n".join([f"- {p['name']}" for p in py_list])
            except Exception as e:
                content = f"Fetch list failed: {e}\n{traceback.format_exc()}"
        else:
            content = f"Unknown id: {vid}"

        vod = {
            "vod_id": vid,
            "vod_name": f"Result for {vid}",
            "vod_pic": "",
            "vod_remarks": "See content below",
            "vod_content": content,
            "type_name": "CloudLoader",
        }

        # 不提供播放地址，避免跳到播放器
        # 如果必须提供，给一个空的播放列表，让盒子停留在详情页
        return {
            "list": [vod],
            "vod": {"vod_play_from": play_from, "vod_play_url": play_url}
        }

    def playerContent(self, flag, id, vipFlags):
        # 详情页已经执行完了，播放器这里直接返回空，避免二次执行
        # 返回一个合法的空m3u8，避免播放器报错
        return {"parse": 0, "url": "", "header": {}, "msg": "Already executed in detail page"}

    def searchContent(self, key, quick):
        return {"list": []}

    def isVideoFormat(self, url):
        return False
    def manualVideoCheck(self):
        return False
    def destroy(self):
        pass
