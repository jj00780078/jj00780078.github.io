# -*- coding: utf-8 -*-
# @tvbox-role manager
# 纯云端自动加载 - 修复版 v3.1
# 指向: https://github.com/jj00780078/jj00780078.github.io/blob/main/py
# 修复: 1. 中文文件名URL编码 2. 精简可运行 3. 英文文件名

import json
import os
import hashlib
import urllib.request
import urllib.parse

from base.spider import Spider as BaseSpider

def _detect_storage_root():
    for p in [os.environ.get("EXTERNAL_STORAGE",""), "/sdcard", "/storage/emulated/0"]:
        if p and os.path.isdir(p):
            return os.path.realpath(p)
    return "/sdcard"

STORAGE_ROOT = _detect_storage_root()

class Spider(BaseSpider):
    # ========== 配置区 - 指向你的仓库 ==========
    GITHUB_USER = "jj00780078"
    GITHUB_REPO = "jj00780078.github.io"
    GITHUB_BRANCH = "main"
    REMOTE_DIR = "py"
    # 必须用英文文件名！
    MANAGER_FILE = "auto_loader_cloud_final.py"

    def getName(self):
        return "☁️云端自动加载 v3.1"

    def init(self, extend=""):
        # extend 可以是 json，预留
        self.extend = extend
        self.sources_cache = []

    def _fetch_github_py_list(self):
        """获取 py 文件夹下所有 py 文件的 raw 链接"""
        user = self.GITHUB_USER
        repo = self.GITHUB_REPO
        branch = self.GITHUB_BRANCH
        dir_name = self.REMOTE_DIR

        # 方式1: 尝试 GitHub API (盒子可能无网络，用try)
        api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{dir_name}?ref={branch}"
        raw_base = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{dir_name}"

        py_files = []
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "TVBox/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode('utf-8'))
                for item in data:
                    if item.get("type") == "file" and item.get("name","").endswith(".py"):
                        name = item["name"]
                        # 跳过自己，避免循环
                        if name == self.MANAGER_FILE:
                            continue
                        # download_url 已经是编码好的
                        download_url = item.get("download_url") or f"{raw_base}/{urllib.parse.quote(name)}"
                        py_files.append({"name": name, "url": download_url})
            if py_files:
                return py_files
        except Exception as e:
            print(f"API failed {e}, fallback to raw_base")

        # 方式2: 如果API失败，尝试直接用你已知的列表或返回空，至少不崩溃
        # 这里为了演示，返回空，实际使用时你可以在 GitHub 放一个 index.json
        return py_files

    def _build_registry(self, py_files):
        """写入 registry.json"""
        registry_path = os.path.join(STORAGE_ROOT, "TV", "CustomCsp", "registry.json")
        # 确保目录存在
        os.makedirs(os.path.dirname(registry_path), exist_ok=True)

        # 读取现有 registry，保留手工项
        existing = {"sites": []}
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                existing = {"sites": []}

        # 分离：保留非自动生成的
        manual_sites = [s for s in existing.get("sites", []) if not str(s.get("key","")).startswith("local_auto_")]
        new_auto_sites = []
        for pf in py_files:
            raw_name = os.path.splitext(pf["name"])[0]
            key = "local_auto_" + hashlib.md5(pf["url"].encode()).hexdigest()[:10]
            site = {
                "key": key,
                "name": raw_name,
                "type": 3,
                "api": pf["url"],
                "searchable": 1,
                "quickSearch": 1
            }
            new_auto_sites.append(site)

        # 合并
        all_sites = manual_sites + new_auto_sites
        existing["sites"] = all_sites

        # 备份
        try:
            backup_path = registry_path + ".bak"
            if os.path.exists(registry_path):
                import shutil
                shutil.copyfile(registry_path, backup_path)
        except:
            pass

        with open(registry_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        return len(new_auto_sites), len(manual_sites)

    def homeContent(self, filter):
        py_list = self._fetch_github_py_list()
        self.sources_cache = py_list

        # 显示首页：分类 + 列表
        classes = [{"type_name": "全部云端PY", "type_id": "all"}]
        # 按名称简单分类
        videos = []
        for pf in py_list:
            videos.append({
                "vod_id": pf["url"],
                "vod_name": pf["name"],
                "vod_pic": "",
                "vod_remarks": "☁️云端直连"
            })

        if not videos:
            videos.append({
                "vod_id": "no_data",
                "vod_name": "⚠️未扫描到PY文件 | 请检查GitHub仓库 py/ 文件夹是否为英文文件名",
                "vod_pic": "",
                "vod_remarks": f"{self.GITHUB_USER}/{self.GITHUB_REPO}/{self.REMOTE_DIR}"
            })

        result = {
            "class": classes,
            "list": videos,
            "filters": {}
        }
        return result

    def categoryContent(self, tid, pg, filter, extend):
        return self.homeContent(filter)

    def detailContent(self, array):
        # array[0] 是 vod_id 即 url
        url = array[0]
        if url == "no_data":
            return {"list": []}

        # 找对应文件名
        name = url
        for pf in self.sources_cache:
            if pf["url"] == url:
                name = pf["name"]
                break

        # 提供两个操作：1. 单独加载 2. 一键全部加载
        vod = {
            "vod_id": url,
            "vod_name": name,
            "vod_pic": "",
            "type_name": "PY源",
            "vod_year": "",
            "vod_area": "GitHub",
            "vod_remarks": "云端直连",
            "vod_actor": self.GITHUB_USER,
            "vod_director": f"{self.GITHUB_REPO}/{self.REMOTE_DIR}",
            "vod_content": f"API链接:\n{url}\n\n点击播放会执行「一键扫描并加载」"
        }

        play_url = f"一键扫描并加载${url}#单独预览${url}"

        return {
            "list": [vod],
            "vod": {
                "vod_play_from": "操作",
                "vod_play_url": play_url
            }
        }

    def searchContent(self, key, quick):
        # 简单搜索
        all_videos = self.homeContent({})["list"]
        result = []
        for v in all_videos:
            if key.lower() in v["vod_name"].lower():
                result.append(v)
        return {"list": result}

    def playerContent(self, flag, id, vipFlags):
        # id 是 url
        if "一键扫描" in flag or "一键扫描并加载" in id or id.startswith("https://"):
            # 执行全量扫描写入
            py_list = self._fetch_github_py_list()
            if not py_list:
                # 如果API被墙，尝试从缓存或给出提示
                py_list = self.sources_cache

            try:
                added, kept = self._build_registry(py_list)
                msg = f"扫描完成：新增{added}个云端源，保留{kept}个手工源。已写入 {os.path.join(STORAGE_ROOT,'TV/CustomCsp/registry.json')}，请返回重载配置。"
                # 返回一个假的播放地址，实际是提示
                return {"parse": 0, "url": "", "header": {}, "msg": msg}
            except Exception as e:
                return {"parse": 0, "url": "", "header": {}, "msg": f"写入失败: {e}"}
        else:
            # 单独预览，直接播放该py
            return {"parse": 0, "url": id, "header": {}, "msg": ""}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass
