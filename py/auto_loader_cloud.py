# -*- coding: utf-8 -*-
# @tvbox-role manager
# @version v3.0
# @author 江 晚枫
# @signature 秋色正好，江 晚枫来过。

import copy
import hashlib
import json
import os
import re
import shutil
import socket
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import zipfile

from base.spider import Spider as BaseSpider

def _detect_storage_root():
    candidates = []
    external = str(os.environ.get("EXTERNAL_STORAGE", "")).strip()
    if external:
        candidates.append(external)
    candidates.extend(("/sdcard", "/storage/emulated/0", os.path.expanduser("~/storage/shared")))
    seen = set()
    for candidate in candidates:
        path = os.path.abspath(os.path.expanduser(candidate))
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        if os.path.isdir(path):
            return real
    return os.path.abspath(external or "/sdcard")

def _detect_local_base(storage_root):
    candidates = []
    configured = str(os.environ.get("TVBOX_HOME", "")).strip()
    if configured:
        candidates.append(configured)
    candidates.extend(
        (
            os.path.join(storage_root, "tvbox"),
            os.path.join(storage_root, "TVBox"),
        )
    )
    for candidate in candidates:
        path = os.path.realpath(os.path.abspath(os.path.expanduser(candidate)))
        if os.path.isdir(path):
            return path
    return os.path.realpath(os.path.join(storage_root, "tvbox"))

def _detect_child_dir(base, *names):
    if os.path.isdir(base):
        try:
            entries = {
                name.lower(): name
                for name in os.listdir(base)
                if os.path.isdir(os.path.join(base, name))
            }
            for name in names:
                actual = entries.get(name.lower())
                if actual:
                    return os.path.join(base, actual)
        except Exception:
            pass
    return os.path.join(base, names[0])

DETECTED_STORAGE_ROOT = _detect_storage_root()
DETECTED_LOCAL_BASE = _detect_local_base(DETECTED_STORAGE_ROOT)
_AUTO_SCAN_STATE = {"last": 0.0}

class RegistryChangedError(RuntimeError):
    pass
class SiteTestCancelled(RuntimeError):
    pass
class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Spider(BaseSpider):
    # ===== 纯云端配置 - 已指向你的仓库 =====
    GITHUB_USER = "jj00780078"
    GITHUB_REPO = "jj00780078.github.io"
    GITHUB_BRANCH = "main"
    REMOTE_DIRS = ["py"]
    REMOTE_PY_BASE_URL = "https://raw.githubusercontent.com/jj00780078/jj00780078.github.io/main/py"
    REMOTE_MANIFEST_URLS = []
    PURE_CLOUD_MODE = True
    SCAN_ROOTS = []

    REGISTRY_PATH = os.path.join(DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "registry.json")
    OUTPUT_PATH = REGISTRY_PATH
    STORAGE_ROOT = DETECTED_STORAGE_ROOT
    LOCAL_BASE_DIR = DETECTED_LOCAL_BASE
    VERSION = "v3.0-cloud"
    XBPQ_API = "csp_XBPQ"
    XBPQ_JAR = ""
    HTML_API = "csp_Builtin"
    PAGE_SIZE = 60
    BACKUP_BEFORE_WRITE = True
    ALLOW_EMPTY_WRITE = False
    DEFAULT_SEARCHABLE = 1
    DEFAULT_QUICK_SEARCH = 1
    STRICT_RECOGNITION = True
    CACHE_VERSION = 5
    AUTO_RELOAD_APP = True
    AUTO_SCAN_ON_EMPTY = True
    AUTO_SCAN_COOLDOWN = 300.0
    APP_PORT_START = 9978
    APP_PORT_END = 9998
    APP_REQUEST_TIMEOUT = 0.35
    APP_RELOAD_DELAY = 1.0
    MAX_SCAN_FILES = 3000
    MAX_SCAN_DEPTH = 8
    MAX_SOURCE_SIZE = 5 * 1024 * 1024
    MAX_JAR_DEX_SCAN_SIZE = 64 * 1024 * 1024
    MAX_LOG_SIZE = 256 * 1024
    SITE_TEST_TIMEOUT = 3.0
    MAX_SITE_TESTS = 50
    SITE_TEST_CACHE_VERSION = 3
    GENERATED_KEY_PREFIX = "local_auto_"
    GENERATED_INSERT_INDEX = None

    JS_EXCLUDE = {"drpy2-fast.min.js","drpy2.min.js","drpy2-obj.min.js","drpy2-template.js","drpy2.js","config.js"}
    SKIP_DIRS = {"__pycache__","node_modules",".git",".svn",".idea",".vscode"}

    #... 為了讓你直接改，下面的核心方法已重寫為純雲端...

    def _file_url(self, path):
        p = str(path).strip()
        if p.lower().startswith(("http://", "https://")):
            return p
        absolute = os.path.realpath(os.path.abspath(os.path.expanduser(p)))
        storage_root = os.path.realpath(os.path.abspath(self.STORAGE_ROOT))
        try:
            relative = os.path.relpath(absolute, storage_root).replace(os.sep, "/")
        except Exception:
            relative = ""
        if relative and relative!= ".." and not relative.startswith("../"):
            return "file://" + relative.lstrip("/")
        return "file://" + absolute

    def _scan_all_roots(self):
        self.cache = self._empty_cache()
        self._jar_inspection_cache = {}
        self.incomplete_scan_roots = []
        self.incomplete_scan_types = set()
        sources = []

        if getattr(self, 'REMOTE_MANIFEST_URLS', None):
            for manifest_url in self.REMOTE_MANIFEST_URLS:
                if not manifest_url or 'example.com' in manifest_url or '你的用户名' in manifest_url:
                    continue
                try:
                    req = urllib.request.Request(manifest_url, headers={"User-Agent": "TVBox"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = json.loads(r.read().decode('utf-8'))
                    if isinstance(data, dict):
                        for type_key, lst in data.items():
                            t = type_key.upper()
                            for item in lst:
                                url = item.get('url') if isinstance(item, dict) else str(item)
                                name = item.get('name', os.path.basename(url)) if isinstance(item, dict) else os.path.basename(url)
                                if not url.lower().startswith('http'):
                                    continue
                                sources.append({"path": url,"type": t if t in self.TYPE_ORDER else "PY","name": name,"key": "{}{}_{}".format(self.GENERATED_KEY_PREFIX, t.lower(), hashlib.md5(url.encode()).hexdigest()[:10])})
                    self._log("INFO", "清单加载成功: {} ({}个)".format(manifest_url, len(sources)))
                except Exception as e:
                    self._log("ERROR", "清单加载失败 {}: {}".format(manifest_url, e))

        if not sources:
            user = getattr(self, 'GITHUB_USER', '').strip()
            repo = getattr(self, 'GITHUB_REPO', '').strip()
            branch = getattr(self, 'GITHUB_BRANCH', 'main').strip()
            if not user or '你的用户名' in user:
                self.status["error"] = "请先配置 GITHUB_USER / GITHUB_REPO"
            else:
                for remote_dir in getattr(self, 'REMOTE_DIRS', ['py']):
                    api_url = "https://api.github.com/repos/{}/{}/contents/{}?ref={}".format(user, repo, remote_dir, branch)
                    try:
                        req = urllib.request.Request(api_url, headers={"User-Agent": "TVBox", "Accept": "application/vnd.github.v3+json"})
                        with urllib.request.urlopen(req, timeout=10) as r:
                            files = json.loads(r.read().decode('utf-8'))
                        raw_base = "https://raw.githubusercontent.com/{}/{}/{}/{}".format(user, repo, branch, remote_dir)
                        custom_base = getattr(self, 'REMOTE_PY_BASE_URL', '').strip()
                        if custom_base:
                            raw_base = custom_base.rstrip('/')
                        for f in files:
                            if not isinstance(f, dict): continue
                            if f.get('type')!= 'file': continue
                            fname = f.get('name','')
                            if not fname.endswith(('.py','.js','.json')): continue
                            if '自动加载' in fname or 'auto-loader' in fname.lower(): continue
                            download_url = f.get('download_url') or "{}/{}".format(raw_base, fname)
                            t = 'PY' if fname.endswith('.py') else 'JS' if fname.endswith('.js') else 'CSP'
                            sources.append({"path": download_url,"type": t,"name": os.path.splitext(fname)[0],"key": "{}{}_{}".format(self.GENERATED_KEY_PREFIX, t.lower(), hashlib.md5(download_url.encode()).hexdigest()[:10])})
                    except Exception as e:
                        self._log("ERROR", "GitHub API 扫描失败 {}: {}".format(api_url, e))

        uniq = []
        seen = set()
        for s in sources:
            if s['path'] in seen: continue
            seen.add(s['path'])
            uniq.append(s)
        sources = uniq

        self.cache["sources"] = []
        self.cache["ignored"] = []
        for src in sources:
            try:
                site = self._build_site(src)
                src["site"] = site
                self.cache["sources"].append(src)
            except Exception as e:
                self._log("WARN", "站点构建失败 {}: {}".format(src.get('path'), e))
        self.status["found"] = len(sources)
        self.status["included"] = len(self.cache["sources"])
        return

    # 以下請直接用你原版 v3.0 的完整方法覆蓋，這裡為了貼文長度省略
    # 你原版的 _empty_cache, _build_site, _merge_registry, _generate_config,
    # _load_registry, _save_settings 等全部保留
    # 最簡可用版已在上傳的.py 文件中
