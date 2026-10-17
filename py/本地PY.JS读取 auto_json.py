# -*- coding: utf-8 -*-
"""
PY.JS源自动加载
==============
- 扫描规定目录下的 py/js 站点
- 生成 /sdcard/auto_config.json
- 自动切换 OK影视 点播源到该文件
- 界面：频道按文件夹归类，点频道进入子 py 的节目列表
"""
import os
import sys
import json
import time
import threading
import importlib.util
import types
import urllib.parse
import urllib.request

# ============================================================
# base 模块导入（兼容 TVBox 各版本加载方式）
# ============================================================
try:
    from base.spider import Spider as BaseSpider
except Exception:
    try:
        from base import Spider as BaseSpider
    except Exception:
        class BaseSpider:
            def __init__(self): pass
            def getName(self): return "AutoLoader"
            def init(self, extend=""): pass
            def isVideoFormat(self, url): pass
            def manualVideoCheck(self): pass
            def homeContent(self, filter): return {'class': [], 'list': []}
            def homeVideoContent(self): return {'list': []}
            def categoryContent(self, tid, pg, filter, extend): return {'list': []}
            def detailContent(self, array): return {'list': []}
            def searchContent(self, key, quick): return {'list': []}
            def playerContent(self, flag, id, vipFlags): return {}
            def localProxy(self, param): return None
            def action(self, action): return {'code': 0, 'msg': ''}


# ============================================================
# 假 base 模块注入：让子 py 的 "from base.spider import Spider" 能 import 成功
# ============================================================
def _install_fake_base():
    try:
        import base  # noqa
        import base.spider  # noqa
        return
    except ImportError:
        pass

    class _DummySpider:
        def __init__(self): pass
        def getName(self): return "DummySpider"
        def init(self, extend=""): pass
        def isVideoFormat(self, url): pass
        def manualVideoCheck(self): pass
        def homeContent(self, filter): return {'class': [], 'list': []}
        def homeVideoContent(self): return {'list': []}
        def categoryContent(self, tid, pg, filter, extend): return {'list': []}
        def detailContent(self, array): return {'list': []}
        def searchContent(self, key, quick): return {'list': []}
        def playerContent(self, flag, id, vipFlags): return {}
        def localProxy(self, param): return None
        def action(self, action): return {'code': 0, 'msg': ''}

    base_mod = types.ModuleType("base")
    spider_mod = types.ModuleType("base.spider")
    spider_mod.Spider = _DummySpider
    base_mod.spider = spider_mod
    sys.modules["base"] = base_mod
    sys.modules["base.spider"] = spider_mod


_install_fake_base()


# ============================================================
# 搜索图标（baidu）
# ============================================================
_ICON_SCAN = "https://t9.baidu.com/it/u=59951231,564237437&fm=193"
_ICON_SEARCH = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f50d.png"


class Spider(BaseSpider):
    # 频道 TID
    TOOLS_TID = "__tools__"
    ALL_TID = "__all__"
    INT_PY_TID = "__int_py_sources__"
    EXT_PY_TID = "__ext_py_sources__"
    INT_JS_TID = "__int_js_sources__"
    EXT_JS_TID = "__ext_js_sources__"

    # 点播源显示名
    SOURCE_NAME = "PY.JS源自动加载"

    # 唯一输出文件
    AUTO_CONFIG = "/sdcard/auto_config.json"

    def __init__(self):
        super().__init__()

        # ★ 待扫描的一级目录
        self.SCAN_DIR_LIST = ["bh", "tvbox", "lz", "py", "js"]

        # ★ 排除文件
        self.EXCLUDE_FILES = {
            'AutoJsonGenerator.py', 'AutoJsonGenerator.js',
            'auto_loader.py',
            'auto_json.py', 'auto_json.js',
            'loader.py', 'loader.js',
            'main.py', 'main.js',
        }
        
        # ★ 屏蔽/过滤文件夹门阀
        self.EXCLUDE_DIRS = {
            'test', '小百合ok', '百合影仓', '重点保存',
            'backup', '操作综合读取', '优化', '老文件',
            'temp', 'py-'
            # 可以在这里继续添加需要过滤的文件夹名称
        }
         
        # 清理历史临时文件
        self.CLEANUP_FILES = [
            '/sdcard/bdjmcc_dedug.log',
            '/storage/emulated/0/bdjmcc_dedug.log',
            '/sdcard/bdjmcc_debug.log',
            '/storage/emulated/0/bdjmcc_debug.log',
            '/sdcard/_write_test_.txt',
            '/storage/emulated/0/_write_test_.txt',
            '/sdcard/auto_config.tmp',
            '/storage/emulated/0/auto_config.tmp',
        ]

        self.lock = threading.RLock()
        self.internal_count = 0
        self.external_count = 0
        self.total_count = 0
        self.int_py_count = 0
        self.ext_py_count = 0
        self.int_js_count = 0
        self.ext_js_count = 0
        self.out_file_path = ""
        self.err_msg = ""
        self.sources = []
        self.category_map = {}       # {分类名: [sources]}
        self._category_ext = {}      # {分类名: 是否全来自外置}
        self.inited = False

        # 子 py 实例缓存
        self._loaded_spiders = {}

        # OK影视 重载状态
        self.last_app_port = 0
        self.last_reload_target = ""

        # 首次进入：加载已有配置 + 若无则自动扫描，并立刻自动触发加载点播源
        try:
            self._cleanup_temp_files()
            self._load_existing_json()
            if not self.sources:
                self._scan_and_cache()
                self._try_reload_app()
        except Exception as e:
            self.err_msg = "加载已有配置异常: {}".format(e)

    def getName(self):
        return "PY.JS源自动加载"

    def init(self, extend=""):
        if self.inited:
            return
        with self.lock:
            try:
                self._cleanup_temp_files()
                if not self.sources:
                    self._load_existing_json()
                if not self.sources:
                    self._scan_and_cache()
                    self._try_reload_app()
            except Exception as e:
                self.err_msg = "init 异常: {}".format(e)
            self.inited = True

    # ============================================================
    # 工具方法
    # ============================================================
    def _script_dir(self):
        """安全获取脚本所在目录"""
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return os.getcwd()

    def _cleanup_temp_files(self):
        """★ 清理历史临时文件（不留垃圾）"""
        for p in self.CLEANUP_FILES:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        try:
            sd = self._script_dir()
            for name in ('bdjmcc_dedug.log', 'bdjmcc_debug.log',
                         '_write_test_.txt', 'auto_config.tmp'):
                fp = os.path.join(sd, name)
                if os.path.exists(fp):
                    os.remove(fp)
        except Exception:
            pass

    def _clean_relative_path(self, local_path):
        """★ 去掉绝对路径前缀，直接获得干净的相对路径（如 bh/py/央视.py）"""
        p = local_path.replace('\\', '/')
        # 去掉常见内置路径前缀
        p = p.replace('/sdcard/', '').replace('/storage/emulated/0/', '')
        
        # 去掉外部存储路径前缀 (如 /storage/XXXX-XXXX/)
        if p.startswith('/storage/'):
            parts = p.split('/')
            if len(parts) > 3:
                p = '/'.join(parts[3:])
            else:
                p = p.lstrip('/')
        else:
            p = p.lstrip('/')
            
        return p

    # ============================================================
    # 读取已有 auto_config.json
    # ============================================================
    def _load_existing_json(self):
        candidates = [
            self.AUTO_CONFIG,
            '/storage/emulated/0/auto_config.json',
            os.path.join(self._script_dir(), 'auto_config.json'),
        ]
        config = None
        used_path = None
        for path in candidates:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    used_path = path
                    break
                except Exception:
                    continue

        if not config or not isinstance(config.get('sites'), list):
            return

        sources = []
        category_map = {}
        category_ext = {}
        int_cnt = 0
        ext_cnt = 0
        int_py_cnt = 0
        ext_py_cnt = 0
        int_js_cnt = 0
        ext_js_cnt = 0

        for site in config['sites']:
            if not isinstance(site, dict):
                continue
            api = str(site.get('api', ''))
            name = str(site.get('name', ''))
            key = str(site.get('key', ''))

            is_ext = name.endswith('☆') or ('/storage/' in api and 'emulated' not in api)

            local_path = api
            if api.startswith('file://storage/emulated/0/'):
                local_path = '/storage/emulated/0/' + api[len('file://storage/emulated/0/'):]
            elif api.startswith('file://storage/'):
                local_path = '/storage/' + api[len('file://storage/'):]
            elif api.startswith('file://'):
                local_path = '/' + api[len('file://'):]

            rel = self._clean_relative_path(local_path)
            cat_name = self._path_to_category(local_path)
            is_js = api.lower().endswith('.js')

            src = {
                "id": key or ("js_" if is_js else "py_") + name.replace('[JS]', '').replace('☆', ''),
                "name": name,
                "path": local_path,
                "relative_path": rel,
                "api": api,
                "type": "JS" if is_js else "PY",
                "is_external": is_ext,
                "category": cat_name,
            }
            sources.append(src)
            category_map.setdefault(cat_name, []).append(src)
            if cat_name not in category_ext:
                category_ext[cat_name] = is_ext
            else:
                category_ext[cat_name] = category_ext[cat_name] and is_ext

            if is_ext:
                ext_cnt += 1
                if is_js:
                    ext_js_cnt += 1
                else:
                    ext_py_cnt += 1
            else:
                int_cnt += 1
                if is_js:
                    int_js_cnt += 1
                else:
                    int_py_cnt += 1

        self.sources = sources
        self.category_map = category_map
        self._category_ext = category_ext
        self.internal_count = int_cnt
        self.external_count = ext_cnt
        self.total_count = len(sources)
        self.int_py_count = int_py_cnt
        self.ext_py_count = ext_py_cnt
        self.int_js_count = int_js_cnt
        self.ext_js_count = ext_js_cnt
        self.out_file_path = used_path or ''

    def _path_to_category(self, local_path):
        """★ 从本地路径精准反推分类名（兼容 bh/tvbox 等多级及根目录）"""
        p = local_path.replace('\\', '/').rstrip('/')
        matched_base = ''
        pos_idx = -1
        for name in self.SCAN_DIR_LIST:
            patt = '/' + name + '/'
            pos = p.find(patt)
            if pos >= 0 and pos > pos_idx:
                pos_idx = pos
                matched_base = name
            else:
                patt2 = '/' + name
                if p.endswith(patt2):
                    pos = len(p) - len(patt2)
                    if pos > pos_idx:
                        pos_idx = pos
                        matched_base = name

        if not matched_base or pos_idx < 0:
            return '其它'

        suffix = p[pos_idx + len(matched_base) + 1:].lstrip('/')
        suffix_dir = os.path.dirname(suffix)
        if not suffix_dir:
            return matched_base
        return suffix_dir.replace('/', '')

    def _build_api(self, file_abs_path):
        """★ API 路径统一为 file:// 形式"""
        p = file_abs_path.replace('\\', '/')
        if p.startswith('/sdcard/'):
            return "file://storage/emulated/0/" + p[len('/sdcard/'):]
        if p.startswith('/storage/emulated/0/'):
            return "file://storage/emulated/0/" + p[len('/storage/emulated/0/'):]
        if p.startswith('/storage/'):
            rel = p[len('/storage/'):]
            if rel.startswith('emulated/'):
                rel = rel[len('emulated/'):]
                return "file://storage/emulated/0/" + rel
            return "file://storage/" + rel
        p = p.lstrip('/')
        return "file://" + p

    # ============================================================
    # 扫描目录收集（支持无限子目录递归）
    # ============================================================
    def _is_excluded_dir(self, dir_path):
        """★ 检查目录是否命中过滤门阀"""
        try:
            norm_path = os.path.normpath(dir_path)
            parts = norm_path.split(os.sep)
            for part in parts:
                if part in self.EXCLUDE_DIRS:
                    return True
        except Exception:
            pass
        return False

    def _collect_scan_dirs(self):
        result = []
        seen = set()

        def _add(path, is_ext):
            if not (os.path.exists(path) and os.path.isdir(path)):
                return
            if self._is_excluded_dir(path):
                return
            try:
                ap = os.path.abspath(path)
            except Exception:
                return
            if ap in seen:
                return
            if '/data/user/' in ap or '/data/data/' in ap or '/cache/' in ap:
                return
            seen.add(ap)
            result.append((ap, is_ext))

        def _walk_recursive(current_dir, is_ext):
            if not (os.path.exists(current_dir) and os.path.isdir(current_dir)):
                return
            if self._is_excluded_dir(current_dir):
                return
            _add(current_dir, is_ext)
            try:
                items = os.listdir(current_dir)
            except Exception:
                return
            for item in items:
                sub_path = os.path.join(current_dir, item)
                if os.path.isdir(sub_path):
                    if not self._is_excluded_dir(sub_path):
                        _walk_recursive(sub_path, is_ext)

        def _walk_root(root, is_ext):
            if not (os.path.exists(root) and os.path.isdir(root)):
                return
            for name in self.SCAN_DIR_LIST:
                lv1 = os.path.join(root, name)
                if os.path.exists(lv1) and os.path.isdir(lv1):
                    _walk_recursive(lv1, is_ext)

        # 内部存储
        for root in ('/sdcard', '/storage/emulated/0'):
            _walk_root(root, False)

        # 外部存储
        storage_root = '/storage'
        if os.path.exists(storage_root):
            try:
                for item in os.listdir(storage_root):
                    if item in ('emulated', 'self', 'knox', 'container'):
                        continue
                    ext_root = os.path.join(storage_root, item)
                    if not os.path.isdir(ext_root):
                        continue
                    _walk_root(ext_root, True)
            except Exception:
                pass

        return result

    def _folder_to_category(self, py_dir):
        """★ 从 py 目录路径精准获取分类名"""
        return self._path_to_category(os.path.join(py_dir, 'dummy.py'))

    # ============================================================
    # 扫描 + 生成 auto_config.json
    # ============================================================
    def _scan_and_cache(self):
        scan_dirs = self._collect_scan_dirs()
        scan_dirs_sorted = sorted(scan_dirs, key=lambda x: 1 if x[1] else 0)

        sources = []
        seen_mods = set()
        category_map = {}
        category_ext = {}
        int_cnt = 0
        ext_cnt = 0
        int_py_cnt = 0
        ext_py_cnt = 0
        int_js_cnt = 0
        ext_js_cnt = 0

        for py_dir, is_external in scan_dirs_sorted:
            try:
                files = os.listdir(py_dir)
            except Exception:
                continue
            cat_name = self._folder_to_category(py_dir)

            for file in files:
                lower = file.lower()
                if not (lower.endswith('.py') or lower.endswith('.js')):
                    continue
                if file.startswith('__'):
                    continue
                if file in self.EXCLUDE_FILES:
                    continue
                if file.startswith('自动加载'):
                    continue

                ext = os.path.splitext(file)[1].lower()
                mod_name = os.path.splitext(file)[0]

                dedup_key = (ext, mod_name)
                if dedup_key in seen_mods:
                    continue
                seen_mods.add(dedup_key)

                file_abs_path = os.path.join(py_dir, file)
                api = self._build_api(file_abs_path)

                if ext == '.js':
                    base_name = mod_name + "[JS]"
                else:
                    base_name = mod_name

                # 区分内外置主标题标识与数量统计
                if is_external:
                    disp_name = base_name + "☆"
                    ext_cnt += 1
                    if ext == '.js':
                        ext_js_cnt += 1
                    else:
                        ext_py_cnt += 1
                else:
                    disp_name = base_name
                    int_cnt += 1
                    if ext == '.js':
                        int_js_cnt += 1
                    else:
                        int_py_cnt += 1

                rel = self._clean_relative_path(file_abs_path)
                key_prefix = "js_" if ext == '.js' else "py_"

                src = {
                    "id": key_prefix + mod_name,
                    "name": disp_name,
                    "path": file_abs_path,
                    "relative_path": rel,
                    "api": api,
                    "type": "JS" if ext == '.js' else "PY",
                    "is_external": is_external,
                    "category": cat_name,
                }
                sources.append(src)
                category_map.setdefault(cat_name, []).append(src)
                if cat_name not in category_ext:
                    category_ext[cat_name] = is_external
                else:
                    category_ext[cat_name] = category_ext[cat_name] and is_external

        self.sources = sources
        self.category_map = category_map
        self._category_ext = category_ext
        self.internal_count = int_cnt
        self.external_count = ext_cnt
        self.total_count = len(sources)
        self.int_py_count = int_py_cnt
        self.ext_py_count = ext_py_cnt
        self.int_js_count = int_js_cnt
        self.ext_js_count = ext_js_cnt

        self._loaded_spiders.clear()

        config_data = {"sites": [{
            "key": s["id"],
            "name": s["name"],
            "type": 3,
            "api": s["api"],
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 1,
            "changeable": 1,
            "playerType": 2,
        } for s in sources]}

        target_paths = [
            self.AUTO_CONFIG,
            '/storage/emulated/0/auto_config.json',
            os.path.join(self._script_dir(), 'auto_config.json'),
        ]

        for out_path in target_paths:
            try:
                out_dir = os.path.dirname(out_path)
                if out_dir and not os.path.exists(out_dir):
                    os.makedirs(out_dir, exist_ok=True)
                if os.path.exists(out_dir) and os.access(out_dir, os.W_OK):
                    tmp = out_path + '.tmp'
                    with open(tmp, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=4)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, out_path)
                    self.out_file_path = out_path
                    break
            except Exception as e:
                try:
                    if os.path.exists(out_path + '.tmp'):
                        os.remove(out_path + '.tmp')
                except Exception:
                    pass
                self.err_msg = "写入 {} 失败: {}".format(out_path, e)
                continue

        if not self.out_file_path:
            self.err_msg = self.err_msg or "所有路径写入失败"
            return

        self._cleanup_temp_files()

    # ============================================================
    # OK影视 自动重载
    # ============================================================
    def _get_current_app_port(self):
        try:
            from java import jclass
            port = int(jclass("com.github.catvod.Proxy").getPort())
            if port > 0:
                return port
        except Exception:
            pass
        return self.last_app_port or 0

    def _file_url(self, path):
        absolute = os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))
        if absolute.startswith('/storage/emulated/0/'):
            return "file://storage/emulated/0/" + absolute[len('/storage/emulated/0/'):]
        if absolute.startswith('/sdcard/'):
            return "file://storage/emulated/0/" + absolute[len('/sdcard/'):]
        if absolute.startswith('/storage/'):
            return "file://storage/" + absolute[len('/storage/'):]
        return "file://" + absolute.lstrip('/')

    def _perform_ok_vod_reload(self):
        try:
            port = self._get_current_app_port()
            if port < 1:
                return False, "OK影视 本机服务端口未获取"

            target = self._file_url(self.AUTO_CONFIG)

            config_body = json.dumps({
                "type": 0,
                "url": target,
                "name": self.SOURCE_NAME,
            }, ensure_ascii=False, separators=(',', ':'))

            body = urllib.parse.urlencode({
                "config": config_body,
                "targets": "[]",
                "force": "true",
            }).encode('utf-8')

            url = "http://127.0.0.1:{}/action?do=sync&mode=1&type=history".format(port)
            req = urllib.request.Request(
                url, data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                    "Connection": "close",
                },
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=2.5) as resp:
                status = int(getattr(resp, 'status', resp.getcode()))
                if status != 200:
                    return False, "HTTP {}".format(status)

            self.last_reload_target = target
            return True, "OK影视 站点已主动重载"
        except Exception as e:
            return False, "OK影视 主动重载失败: {}".format(e)

    def _try_reload_app(self):
        return self._perform_ok_vod_reload()

    def _load_child_spider(self, src):
        src_id = src["id"]
        if src_id in self._loaded_spiders:
            return self._loaded_spiders[src_id]

        py_path = src["path"]
        if not os.path.isfile(py_path):
            return None

        mod_name = "child_mod_" + src_id.replace("-", "_").replace(".", "_").replace("/", "_")
        try:
            spec = importlib.util.spec_from_file_location(mod_name, py_path)
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
        except Exception as e:
            sys.stderr.write("[AutoLoader] 加载失败 {}: {}\n".format(py_path, e))
            return None

        spider_cls = getattr(mod, "Spider", None)
        if spider_cls is None:
            return None

        try:
            instance = spider_cls()
        except Exception as e:
            sys.stderr.write("[AutoLoader] 实例化失败 {}: {}\n".format(py_path, e))
            return None

        try:
            if hasattr(instance, "init"):
                try:
                    instance.init("")
                except TypeError:
                    instance.init()
        except Exception:
            pass

        self._loaded_spiders[src_id] = instance
        return instance

    # ============================================================
    # 界面
    # ============================================================
    def homeContent(self, filter):
        classes = [
            {"type_id": self.TOOLS_TID, "type_name": "⚙ 扫描"},
            {"type_id": self.ALL_TID, "type_name": "全部 ({})".format(self.total_count)},
            {"type_id": self.INT_PY_TID, "type_name": "内PY源 ({})".format(self.int_py_count)},
            {"type_id": self.EXT_PY_TID, "type_name": "外PY源☆ ({})".format(self.ext_py_count)},
            {"type_id": self.INT_JS_TID, "type_name": "内JS源 ({})".format(self.int_js_count)},
            {"type_id": self.EXT_JS_TID, "type_name": "外JS源☆ ({})".format(self.ext_js_count)},
        ]

        def cat_sort_key(cat_name):
            return (
                1 if self._category_ext.get(cat_name, False) else 0,
                cat_name.casefold(),
            )

        for cat_name in sorted(self.category_map.keys(), key=cat_sort_key):
            count = len(self.category_map[cat_name])
            suffix = "☆" if self._category_ext.get(cat_name, False) else ""
            classes.append({
                "type_id": "cat:" + cat_name,
                "type_name": "{}{} ({})".format(cat_name, suffix, count),
            })

        return {"class": classes, "list": self._sources_to_vods(self.sources)}

    def homeVideoContent(self):
        return {"list": self._sources_to_vods(self.sources)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        page_size = 60

        if tid == self.TOOLS_TID:
            items = self._tools_items()
            return {"page": 1, "pagecount": 1, "limit": page_size,
                    "total": len(items), "list": items}

        # ★ 细分的内外置 PY/JS 分类过滤
        if tid == self.INT_PY_TID:
            items = [s for s in self.sources if s["type"] == "PY" and not s["is_external"]]
        elif tid == self.EXT_PY_TID:
            items = [s for s in self.sources if s["type"] == "PY" and s["is_external"]]
        elif tid == self.INT_JS_TID:
            items = [s for s in self.sources if s["type"] == "JS" and not s["is_external"]]
        elif tid == self.EXT_JS_TID:
            items = [s for s in self.sources if s["type"] == "JS" and s["is_external"]]
        elif str(tid).startswith("cat:"):
            cat_name = str(tid)[4:]
            items = list(self.category_map.get(cat_name, []))
        elif tid == self.ALL_TID or tid == "all":
            items = list(self.sources)
        else:
            items = list(self.sources)

        total = len(items)
        page_count = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        page_items = items[start:start + page_size]

        return {
            "page": page, "pagecount": page_count, "limit": page_size,
            "total": total,
            "list": self._sources_to_vods(page_items),
        }

    def _tools_items(self):
        return [
            {
                "vod_id": "__rescan__",
                "vod_name": "自动加载到点播",
                "vod_pic": _ICON_SCAN,
                "vod_remarks": "手动扫描并生成 auto_config.json",
                "action": "rescan",
            },
        ]

    def detailContent(self, array):
        vid = str(array[0]) if isinstance(array, (list, tuple)) and array else str(array)

        if vid == "__rescan__":
            content = "重要提示：请切换到点播点击[PY.JS源自动加载]"
            return {"list": [{
                "vod_id": vid, "vod_name": "手动扫描",
                "vod_pic": _ICON_SCAN,
                "vod_play_from": "提示",
                "vod_play_url": "查看:$" + content,
                "vod_content": content,
            }]}

        for src in self.sources:
            if src["id"] == vid:
                content = (
                    "名称: {}\n"
                    "分类: {}\n"
                    "文件: {}\n"
                    "API: {}\n\n"
                    "重要提示：请切换到点播点击[PY.JS源自动加载]"
                ).format(src["name"], src["category"], src["path"], src["api"])
                return {"list": [{
                    "vod_id": vid, "vod_name": src["name"],
                    "vod_pic": "",
                    "vod_play_from": "提示",
                    "vod_play_url": "查看:$" + content,
                    "vod_content": content,
                }]}

        return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        keyword = str(key or "").strip().lower()
        if not keyword:
            return {"list": []}
        result = [s for s in self.sources if keyword in s["name"].lower()]
        return {"list": self._sources_to_vods(result, icon=_ICON_SEARCH)}

    def playerContent(self, flag, id, vipFlags):
        return {}

    def localProxy(self, param):
        return None

    def action(self, action):
        action = str(action)
        if action == "rescan":
            with self.lock:
                try:
                    self._cleanup_temp_files()
                    self._scan_and_cache()
                    ok, detail = self._try_reload_app()

                    if ok:
                        msg = ("扫描完成：共 {} 个 (内置PY:{} 外置PY:{} 内置JS:{} 外置JS:{})；已自动切换点播").format(
                            self.total_count, self.int_py_count, self.ext_py_count, self.int_js_count, self.ext_js_count)
                    else:
                        msg = ("扫描完成：共 {} 个 (内置PY:{} 外置PY:{} 内置JS:{} 外置JS:{})；自动切换失败：{}").format(
                            self.total_count, self.int_py_count, self.ext_py_count, self.int_js_count, self.ext_js_count, detail)
                except Exception as e:
                    msg = "扫描失败：{}".format(e)
            return {"code": 0, "msg": msg}
        return {"code": 0, "msg": ""}

    def _sources_to_vods(self, items, icon=""):
        out = []
        for src in items:
            out.append({
                "vod_id": src["id"],
                "vod_name": src["name"],
                "vod_pic": icon,
                "vod_remarks": src["relative_path"],
            })
        return out