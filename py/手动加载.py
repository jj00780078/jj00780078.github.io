import base64
import copy
import hashlib
import json
import os
import re
import shutil
import socket
import struct
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

# 进程级自动补扫冷却，防止"补扫 -> 重载 -> 重建实例 -> 再补扫"循环。
_AUTO_SCAN_STATE = {"last": 0.0}


class RegistryChangedError(RuntimeError):
    pass


class SiteTestCancelled(RuntimeError):
    pass


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# ============================================================
# 恶意代码检测模块（从文档1移植）
# ============================================================

_HAS_AES = False
try:
    from Crypto.Cipher import AES as _AES_IMPL
    _HAS_AES = True
    _AES_MODE = 'pycryptodome'
except ImportError:
    try:
        import pyaes as _AES_IMPL
        _HAS_AES = True
        _AES_MODE = 'pyaes'
    except ImportError:
        _HAS_AES = False


def pad_end(key: str) -> str:
    """补齐到16字节"""
    return key + "0000000000000000"[:16 - len(key)]


def decrypt_cbc(hex_data: str) -> str:
    """AES-CBC解密"""
    if not hex_data or len(hex_data) < 50 or not _HAS_AES:
        return None
    
    try:
        cleaned = re.sub(r'\s+', '', hex_data)
        if len(cleaned) % 2 != 0:
            cleaned = cleaned[:-1]
        
        raw_bytes = bytes.fromhex(cleaned)
        raw_str = raw_bytes.decode('latin-1').lower()
        
        key_start = raw_str.find('$#')
        if key_start < 0:
            return None
        key_end = raw_str.find('#$', key_start + 2)
        if key_end < 0:
            return None
        key = raw_str[key_start+2:key_end]
        
        iv = raw_str[-13:]
        
        hdr_end = cleaned.find('2324')
        if hdr_end < 0:
            return None
        hdr_end += 4
        
        cipher_hex = cleaned[hdr_end:-26]
        if len(cipher_hex) < 32:
            return None
        
        cipher = bytes.fromhex(cipher_hex)
        
        key_full = pad_end(key).encode('latin-1')
        iv_full = pad_end(iv).encode('latin-1')
        
        if _AES_MODE == 'pycryptodome':
            _aes = _AES_IMPL.new(key_full, _AES_IMPL.MODE_CBC, iv_full)
            decrypted = _aes.decrypt(cipher)
        elif _AES_MODE == 'pyaes':
            _aes = _AES_IMPL.AESModeOfOperationCBC(key_full, iv=iv_full)
            decrypted = b''
            for _i in range(0, len(cipher), 16):
                decrypted += _aes.decrypt(cipher[_i:_i+16])
        else:
            return None
        
        pad_len = decrypted[-1]
        if 0 < pad_len <= 16:
            decrypted = decrypted[:-pad_len]
        
        result = decrypted.decode('utf-8', errors='replace').strip()
        if result.startswith('{') or result.startswith('['):
            return result
        return None
    except Exception:
        return None


def decode_bmp(content: bytes) -> str:
    """BMP隐写解码"""
    if len(content) < 100 or content[:2] != b'BM':
        return None
    
    try:
        pixel_offset = struct.unpack('<I', content[10:14])[0]
        pixel_data = content[pixel_offset:]
        if not pixel_data:
            return None
        
        for key in [0x9B, 0xAF, 0x5A, 0x66, 0x88, 0x77]:
            decoded = bytes([b ^ key for b in pixel_data])
            text = decoded.decode('utf-8', errors='replace').strip()
            start = text.find('{')
            if start < 0:
                start = text.find('[')
            if start >= 0:
                candidate = text[start:]
                try:
                    json.loads(candidate)
                    return candidate
                except:
                    continue
    except:
        pass
    return None


def decode_image(content: bytes):
    """图片隐写解码"""
    if not content or len(content) < 50:
        return None
    
    # WebP
    if len(content) > 200 and content[:4] == b'RIFF' and b'WEBP' in content[:12]:
        try:
            text = content.decode('latin-1')
            b64s = re.findall(r'[A-Za-z0-9+/=]{200,}', text)
            for b64 in b64s:
                try:
                    pad = 4 - len(b64) % 4
                    if pad != 4:
                        b64 += '=' * pad
                    dec = base64.b64decode(b64)
                    return json.loads(dec)
                except:
                    continue
        except:
            pass
    
    # PNG
    if content[:4] == b'\x89PNG':
        try:
            iend_pos = content.rfind(b'IEND')
            if iend_pos > 0:
                after_iend = content[iend_pos + 8:]
                if len(after_iend) > 50:
                    b64s = re.findall(rb'[A-Za-z0-9+/]{100,}=*', after_iend)
                    for b64 in b64s:
                        try:
                            padding = 4 - len(b64) % 4
                            if padding != 4:
                                b64 += b'=' * padding
                            dec = base64.b64decode(b64)
                            try:
                                return json.loads(dec)
                            except:
                                pass
                            try:
                                txt = dec.decode('utf-8', errors='ignore')
                                start = txt.find('{')
                                if start >= 0:
                                    depth, end = 0, 0
                                    for i, ch in enumerate(txt[start:], start):
                                        if ch == '{':
                                            depth += 1
                                        elif ch == '}':
                                            depth -= 1
                                            if depth == 0:
                                                end = i + 1
                                                break
                                    if end > 0:
                                        try:
                                            return json.loads(txt[start:end])
                                        except:
                                            pass
                            except:
                                pass
                        except:
                            pass
        except:
            pass
    
    return None


def detect_and_decode_content(content: str) -> dict:
    """
    检测并解密内容
    返回: {'decoded': bool, 'content': str, 'method': str}
    """
    if not content or len(content) < 10:
        return {'decoded': False, 'content': content, 'method': 'none'}
    
    result = {'decoded': False, 'content': content, 'method': 'none'}
    
    # 方法1: 检查是否为JSON
    try:
        trimmed = content.lstrip('\ufeff \t\n\r')
        json.loads(trimmed)
        result['decoded'] = True
        result['method'] = 'plain_json'
        return result
    except:
        pass
    
    # 方法2: AES-CBC解密
    cleaned = re.sub(r'\s+', '', content)
    if re.match(r'^[A-Fa-f0-9]+$', cleaned) and len(cleaned) > 100:
        decrypted = decrypt_cbc(cleaned)
        if decrypted:
            try:
                json.loads(decrypted.lstrip('\ufeff').strip())
                result['decoded'] = True
                result['content'] = decrypted
                result['method'] = 'aes_cbc'
                return result
            except:
                pass
    
    # 方法3: Base64解密
    if '**' in content:
        try:
            m = re.search(r'[A-Za-z0-9]{8}\*\*(.+)', content, re.DOTALL)
            if m:
                decoded_bytes = base64.b64decode(m.group(1).strip())
                decoded_text = decoded_bytes.decode('utf-8', errors='replace')
                json.loads(decoded_text.lstrip('\ufeff').strip())
                result['decoded'] = True
                result['content'] = decoded_text
                result['method'] = 'base64'
                return result
        except:
            pass
    
    # 方法4: BMP隐写
    if len(content) > 100 and content[:2] == 'BM':
        try:
            decoded = decode_bmp(content.encode('latin1'))
            if decoded:
                json.loads(decoded.lstrip('\ufeff').strip())
                result['decoded'] = True
                result['content'] = decoded
                result['method'] = 'bmp_stego'
                return result
        except:
            pass
    
    # 方法5: 图片隐写
    if len(content) > 100:
        try:
            raw = content.encode('latin1')
            if (len(raw) >= 4 and raw[:4] == b'\x89PNG') or \
               (len(raw) >= 4 and raw[:4] == b'RIFF' and b'WEBP' in raw[:12]) or \
               (len(raw) >= 2 and raw[:2] == b'\xff\xd8') or \
               (len(raw) >= 4 and raw[:4] == b'GIF8'):
                decoded = decode_image(raw)
                if decoded:
                    if isinstance(decoded, dict):
                        result['content'] = json.dumps(decoded, ensure_ascii=False)
                    else:
                        result['content'] = decoded
                    result['decoded'] = True
                    result['method'] = 'image_stego'
                    return result
        except:
            pass
    
    return result


class TVBoxMalwareDetector:
    """TVBox恶意代码检测器 - 支持解密后分析"""
    
    def __init__(self):
        # 恶意代码特征（针对解密后的代码）
        self.malware_patterns = {
            # 文件上传到远程服务器
            'upload_to_server': {
                'patterns': [
                    r'upload_file_to_server',
                    r'_upload_file_to_server',
                    r'upload_py_file',
                    r'upload\.php',
                    r'server_url.*upload',
                    r'action[\'"]?\s*:\s*[\'"]?upload',
                    r'files[\'"]?\s*:\s*\{.*?\'file\'',
                    r'multipart/form-data.*upload',
                    r'requests\.post.*files=',
                    r'enctype="multipart/form-data"',
                    r'upload_cache',
                    r'_load_upload_cache',
                    r'_save_upload_cache',
                ],
                'level': '严重',
                'desc': '上传文件到远程服务器'
            },
            
            # 文件扫描遍历
            'file_scan': {
                'patterns': [
                    r'_scan_py_files',
                    r'_scan_dirs',
                    r'scan_dirs',
                    r'os\.walk.*\.py',
                    r'Path\(.*\)\.glob',
                    r'listdir.*\.py',
                    r'扫描.*\.py',
                    r'collect.*files',
                    r'get_files_to_scan',
                ],
                'level': '严重',
                'desc': '扫描本地文件'
            },
            
            # 定时触发
            'trigger_mechanism': {
                'patterns': [
                    r'_trigger_scan_if_needed',
                    r'_last_scan_time',
                    r'_scan_interval',
                    r'_is_scanning',
                    r'threading\.Thread.*scan',
                    r'daemon=True',
                    r'background.*scan',
                    r'定时.*扫描',
                ],
                'level': '高危',
                'desc': '定时触发恶意行为'
            },
            
            # 删除文件
            'file_delete': {
                'patterns': [
                    r'os\.remove\s*\(',
                    r'os\.unlink\s*\(',
                    r'shutil\.rmtree\s*\(',
                    r'Path\(.*\)\.unlink\s*\(',
                    r'删除.*文件',
                    r'rm\s+-rf',
                    r'_delete_file\s*\(',
                    r'_cleanup\s*\(',
                ],
                'level': '高危',
                'desc': '删除文件操作'
            },
            
            # 修改/覆盖文件
            'file_modify': {
                'patterns': [
                    r'open\([^)]*["\']w["\']\)',
                    r'open\([^)]*["\']a["\']\)',
                    r'Path\(.*\)\.write_text\s*\(',
                    r'Path\(.*\)\.write_bytes\s*\(',
                    r'shutil\.copy\s*\(',
                    r'shutil\.move\s*\(',
                    r'os\.rename\s*\(',
                    r'_mark_file_uploaded\s*\(',
                    r'_is_file_uploaded\s*\(',
                ],
                'level': '高危',
                'desc': '修改/覆盖文件'
            },
            
            # 执行系统命令 - 改进版，区分安全的exec
            'command_exec': {
                'patterns': [
                    r'os\.system\s*\(',
                    r'subprocess\.(call|run|Popen)\s*\(',
                    r'eval\s*\([^)]*\)',
                    r'exec\s*\([^)]*\)',
                    r'__import__\s*\(',
                    r'compile\s*\(',
                ],
                'level': '严重',
                'desc': '执行系统命令/代码'
            },
            
            # 敏感路径访问
            'sensitive_path': {
                'patterns': [
                    r'/sdcard/.*\.py',
                    r'/storage/emulated/.*\.py',
                    r'/data/data/.*\.py',
                    r'getExternalStorageDirectory',
                    r'tvbox/py',
                    r'tvbox/js',
                ],
                'level': '高危',
                'desc': '访问敏感路径'
            },
        }
        
        # 白名单模式 - 用于排除误报
        self.whitelist_patterns = {
            # exec 白名单 - 正则表达式的exec是安全的
            'exec_regex': [
                r'\.exec\s*\(',  # 正则表达式的exec方法
                r'regex\.exec\s*\(',
                r'/.*?\.exec\s*\(',
                r'RegExp.*\.exec\s*\(',
                r'while\s*\(\s*[^)]*\.exec\s*\(',
                r'cardRegex\.exec\s*\(',
                r'pattern\.exec\s*\(',
                r'match\s*=\s*[^)]*\.exec\s*\(',
            ],
            # eval 白名单 - 某些正常场景
            'eval_whitelist': [
                r'eval\s*\(\s*[\'"]use strict[\'"]\s*\)',
                r'eval\s*\(\s*[\'"]\s*[\'"]\s*\)',
                r'eval\s*\(\s*[^)]*\.toString\s*\(\s*\)\s*\)',
            ],
            # 正常的文件操作
            'file_whitelist': [
                r'open\s*\(\s*__file__\s*,\s*[\'"]r[\'"]\s*\)',
                r'open\s*\(\s*[\'"]/dev/null[\'"]\s*,\s*[\'"]w[\'"]\s*\)',
            ]
        }
        
        # TVBox插件特征
        self.tvbox_patterns = [
            'class Spider',
            'from base.spider import Spider',
            'def homeContent',
            'def categoryContent',
            'def detailContent',
            'def playerContent',
            'def searchContent',
        ]
        
        self.scan_results = {
            'normal': [],
            'dangerous': [],
            'summary': {
                'total': 0,
                'normal_count': 0,
                'dangerous_count': 0,
                'encrypted_count': 0,
                'scan_time': time.strftime('%Y-%m-%d %H:%M:%S')
            }
        }
    
    def is_whitelisted(self, content: str, pattern: str, match: str) -> bool:
        """检查是否在白名单中"""
        # 检查exec白名单
        if 'exec' in pattern or pattern == r'exec\s*\([^)]*\)':
            for wp in self.whitelist_patterns['exec_regex']:
                if re.search(wp, content, re.IGNORECASE):
                    lines = content.split('\n')
                    for line in lines:
                        if '.exec(' in line and 'regex' in line.lower():
                            return True
                        if 'match =' in line and '.exec(' in line:
                            return True
                    return False
        
        # 检查eval白名单
        if 'eval' in pattern:
            for wp in self.whitelist_patterns['eval_whitelist']:
                if re.search(wp, content, re.IGNORECASE):
                    return True
        
        # 检查文件操作白名单
        if 'open' in pattern or 'write' in pattern:
            for wp in self.whitelist_patterns['file_whitelist']:
                if re.search(wp, content, re.IGNORECASE):
                    return True
        
        return False
    
    def is_tvbox_plugin(self, content: str) -> bool:
        """判断是否为TVBox插件"""
        for pattern in self.tvbox_patterns:
            if pattern in content:
                return True
        return False
    
    def calculate_malware_score(self, content: str) -> tuple:
        """计算恶意代码评分"""
        score = 0
        findings = []
        
        for category, info in self.malware_patterns.items():
            for pattern in info['patterns']:
                # 特殊处理exec模式
                if pattern == r'exec\s*\([^)]*\)':
                    lines = content.split('\n')
                    valid_matches = []
                    for line in lines:
                        if '.exec(' in line and ('regex' in line.lower() or 'match' in line.lower()):
                            continue
                        if re.search(pattern, line, re.IGNORECASE):
                            valid_matches.append(line)
                    
                    if valid_matches:
                        matches = valid_matches
                    else:
                        continue
                else:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                
                if matches:
                    filtered_matches = []
                    for match in matches:
                        if not self.is_whitelisted(content, pattern, match):
                            filtered_matches.append(match)
                    
                    if filtered_matches:
                        level_weight = {'严重': 10, '高危': 7, '中危': 4, '低危': 2}
                        weight = level_weight.get(info['level'], 3)
                        score += weight * len(filtered_matches)
                        
                        findings.append({
                            'category': category,
                            'level': info['level'],
                            'desc': info['desc'],
                            'pattern': pattern,
                            'matches': filtered_matches[:3],
                            'count': len(filtered_matches)
                        })
        
        return score, findings
    
    def extract_critical_code(self, content: str, findings: list) -> list:
        """提取关键恶意代码片段"""
        critical_code = []
        
        for f in findings[:2]:
            for match in f['matches'][:2]:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if match.lower() in line.lower():
                        start = max(0, i-2)
                        end = min(len(lines), i+3)
                        context = '\n'.join(lines[start:end])
                        critical_code.append({
                            'line': i+1,
                            'code': context
                        })
                        break
        
        return critical_code
    
    def analyze_file(self, file_path: str) -> dict:
        """分析单个文件"""
        result = {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'file_ext': os.path.splitext(file_path)[1].lower(),
            'is_malware': False,
            'is_tvbox_plugin': False,
            'is_encrypted': False,
            'decrypt_method': 'none',
            'malware_score': 0,
            'risk_level': '安全',
            'findings': [],
            'content_snippet': '',
            'decrypted_snippet': '',
            'key_features': []
        }
        
        try:
            # 读取原始内容
            with open(file_path, 'rb') as f:
                raw_bytes = f.read()
            
            # 尝试解码
            try:
                original_content = raw_bytes.decode('utf-8', errors='replace')
            except:
                original_content = raw_bytes.decode('latin-1', errors='replace')
            
            # 检测并解密
            decode_result = detect_and_decode_content(original_content)
            
            if decode_result['decoded'] and decode_result['method'] != 'plain_json':
                result['is_encrypted'] = True
                result['decrypt_method'] = decode_result['method']
                content = decode_result['content']
                result['decrypted_snippet'] = content[:500] + '...' if len(content) > 500 else content
            else:
                content = original_content
            
            # 保存内容片段
            result['content_snippet'] = content[:500] + '...' if len(content) > 500 else content
            
            # 判断是否为TVBox插件
            result['is_tvbox_plugin'] = self.is_tvbox_plugin(content)
            
            # 计算恶意评分
            score, findings = self.calculate_malware_score(content)
            result['malware_score'] = score
            result['findings'] = findings
            
            # 提取关键特征
            has_upload = any(f['category'] == 'upload_to_server' for f in findings)
            has_scan = any(f['category'] == 'file_scan' for f in findings)
            has_trigger = any(f['category'] == 'trigger_mechanism' for f in findings)
            has_delete = any(f['category'] == 'file_delete' for f in findings)
            has_modify = any(f['category'] == 'file_modify' for f in findings)
            has_exec = any(f['category'] == 'command_exec' for f in findings)
            has_sensitive = any(f['category'] == 'sensitive_path' for f in findings)
            
            if has_upload:
                result['key_features'].append('上传文件到远程服务器')
            if has_scan:
                result['key_features'].append('扫描本地文件')
            if has_trigger:
                result['key_features'].append('定时触发机制')
            if has_delete:
                result['key_features'].append('删除文件')
            if has_modify:
                result['key_features'].append('修改文件')
            if has_exec:
                result['key_features'].append('执行系统命令')
            if has_sensitive:
                result['key_features'].append('访问敏感路径')
            
            # 判断是否为恶意代码
            is_malicious = False
            
            # 严重：上传+扫描+触发
            if has_upload and has_scan and has_trigger:
                is_malicious = True
                result['risk_level'] = '严重恶意'
            # 高度：上传+扫描 或 上传+触发 或 上传+exec
            elif has_upload and (has_scan or has_trigger or has_exec):
                is_malicious = True
                result['risk_level'] = '高度恶意'
            # 中度：单独上传 或 扫描+删除+触发
            elif has_upload:
                is_malicious = True
                result['risk_level'] = '中度恶意'
            elif has_scan and (has_delete or has_modify) and has_trigger:
                is_malicious = True
                result['risk_level'] = '中度恶意'
            # exec + 敏感路径 + 触发
            elif has_exec and has_trigger and has_sensitive:
                is_malicious = True
                result['risk_level'] = '中度恶意'
            # 评分超过阈值
            elif score >= 15:
                is_malicious = True
                result['risk_level'] = '疑似恶意'
            
            result['is_malware'] = is_malicious
            
            # 提取关键代码片段
            if is_malicious and findings:
                result['critical_code'] = self.extract_critical_code(content, findings)
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def analyze_directory(self, scan_path: str, supported_extensions=None) -> dict:
        """扫描目录中的所有文件"""
        if supported_extensions is None:
            # 只扫描 py, js, html 三种文件
            supported_extensions = {'.py', '.js', '.html'}
        
        results = {
            'scan_path': scan_path,
            'files': [],
            'summary': {
                'total': 0,
                'safe': 0,
                'dangerous': 0,
                'encrypted': 0
            }
        }
        
        if not os.path.exists(scan_path):
            return results
        
        # 收集所有支持的文件
        files_to_scan = []
        if os.path.isfile(scan_path):
            ext = os.path.splitext(scan_path)[1].lower()
            if ext in supported_extensions:
                files_to_scan.append(scan_path)
        else:
            for root, _, filenames in os.walk(scan_path):
                for f in filenames:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in supported_extensions:
                        files_to_scan.append(os.path.join(root, f))
        
        # 分析每个文件
        for file_path in files_to_scan:
            result = self.analyze_file(file_path)
            results['files'].append(result)
            
            results['summary']['total'] += 1
            if result['is_malware']:
                results['summary']['dangerous'] += 1
            else:
                results['summary']['safe'] += 1
            if result['is_encrypted']:
                results['summary']['encrypted'] += 1
        
        return results


# ============================================================
# 主类 Spider
# ============================================================

class Spider(BaseSpider):
    # ==========================================================================
    # 配置区
    # ==========================================================================
    SCAN_ROOTS = [
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "py", "python"), "type": "PY", "extensions": [".py"]},
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "js", "javascript"), "type": "JS", "extensions": [".js", ".json"]},
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "csp"), "type": "CSP", "extensions": [".json"]},
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "XBPQ"), "type": "XBPQ", "extensions": [".json"]},
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "html"), "type": "HTML", "extensions": [".html"]},
    ]

    # WebHTV 原生站点注入注册表。
    REGISTRY_PATH = os.path.join(DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "registry.json")
    OUTPUT_PATH = REGISTRY_PATH
    STORAGE_ROOT = DETECTED_STORAGE_ROOT
    LOCAL_BASE_DIR = DETECTED_LOCAL_BASE
    VERSION = "v3.0"

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
    GENERATED_INSERT_INDEX = None  # None 表示追加；也可填写 0、1、2……

    JS_EXCLUDE = {
        "drpy2-fast.min.js",
        "drpy2.min.js",
        "drpy2-obj.min.js",
        "drpy2-template.js",
        "drpy2.js",
        "config.js",
    }
    SKIP_DIRS = {
        "__pycache__",
        "node_modules",
        ".git",
        ".svn",
        "lib",
        "libs",
        "extension",
        "extensions",
        "webhomeextensions",
    }
    PY_EXCLUDE_RELATIVE = {"base/spider.py"}
    JS_EXTENSION_SUFFIXES = (".ext.js", ".extension.js", ".user.js")

    # ========== 18+ 成人内容过滤（识别完全本地，不上传服务器） ==========
    # 强信号文本：命中即判（用户指定）。
    # 注意：其中 "色/瑟" 为裸字，会误判含这些字的正常站点（角色/特色/颜色/瑟瑟发抖等）。
    ADULT_STRONG_TEXT = ("🔞", "🈲", "㊙", "🍆", "🍑", "🍌", "🥒", "色", "瑟")
    # av / 18 作为整词强信号，命中即判（避免命中 java/javascript/navigation、
    # 年份数字等正常内容；站名如 "AV天堂"、"18影视"、"xxx18" 仍会命中）。
    ADULT_STRONG_WORD_PATTERN = re.compile(
        r"(?:^|[^0-9a-z])(?:av|18)(?:$|[^0-9a-z])", re.IGNORECASE
    )
    # 强标记符号：唯一明确指向 18 禁的符号，直接判定。
    ADULT_SYMBOLS = ("🔞",)
    # 弱标记符号：禁令/性别标记，日常也常见，只计分不单独判定。
    ADULT_WEAK_SYMBOLS = ("🈲", "㊙", "⛔", "🚷", "㊛", "㊚")
    # 弱标记 Emoji：影视、美食、天气等正常站点也常见，只计分不单独判定。
    ADULT_EMOJI = ("🥵", "🌶️", "🎞️", "🎬", "💦")
    # 更弱 Emoji：只用于内容计分叠加，绝不单独判定。
    ADULT_EMOJI_WEAK = ("🍆", "🍑", "🍌", "🥒", "🍒", "👅", "🌮", "🐱")
    # 简写 / ASCII 字符画标记（非 Emoji 字符串）。
    ADULT_SHORT_TEXT = re.compile(
        r"r-?18\s*(?:g|禁)?|x[- ]rated|xxx[- ]hd|18➕|8====D|c==3|(?:\u2b50.*?)18禁",
        re.IGNORECASE,
    )
    ADULT_KEYWORDS = (
        "18禁", "r18", "成人", "色情", "情色", "无码", "有码", "女优",
        "麻豆", "偷拍", "乱伦", "淫", "福利姬", "裸聊", "约炮", "里番",
        "少妇", "爱色", "好色", "色播", "色库", "色岛", "色站", "黄色仓库",
        "小黄书", "榨汁姐", "国产麻豆", "高端外泄", "自拍偷拍", "国产自拍",
    )
    # 只匹配完整名称，避免把普通的教授课程等来源误判为 18+ 站点。
    ADULT_EXACT_NAMES = frozenset(
        (
            "教授",
            "教授(梯)",
            "小红薯",
            "小红薯app",
            "51吸瓜",
            "51吸瓜动态版",
        )
    )
    ADULT_FILTER_REVISION = 3
    ADULT_LATIN_PATTERN = re.compile(
        r"(?:rule34|porn|hentai|jable|javday|jav6k|javffm|javtsunami|xvideos|"
        r"xhamster|xnxx|missav|mrjav|netflav|pornlulu|pornhub|sexnguon|"
        r"onlyfans|redtube|youporn|spankbang|brazzers|hanime|91porn|"
        r"91md|avgle|kissav|pandaav|airav|kanav|nowav|soav|owoav|qinav)",
        re.IGNORECASE,
    )
    # ==========================================================================

    TYPE_ORDER = {"PY": 0, "JS": 1, "CSP": 2, "XBPQ": 3, "HTML": 4}
    TYPE_PREFIX = {
        "PY": "",
        "JS": "",
        "CSP": "",
        "XBPQ": "",
        "HTML": "",
    }
    TYPE_LABEL = {
        "PY": "PY",
        "JS": "JS",
        "CSP": "JAR/CSP",
        "XBPQ": "XBPQ",
        "HTML": "HTML",
    }
    TYPE_GROUP = {
        "PY": "[py]",
        "JS": "[js]",
        "CSP": "[jar]",
        "XBPQ": "[xbpq]",
        "HTML": "[html]",
    }
    TYPE_EXTENSIONS = {
        "PY": [".py"],
        "JS": [".js", ".json"],
        "CSP": [".json"],
        "XBPQ": [".json"],
        "HTML": [".html"],
    }
    SCAN_SETTINGS_TID = "scan_settings"
    BACKUPS_TID = "scan_backups"
    STATUS_ID = "__local_source_status__"
    RESCAN_ID = "__local_source_rescan__"
    CLEAR_SITES_ID = "__local_source_clear_sites__"
    DELETE_BACKUPS_ID = "__local_source_delete_backups__"
    TEST_SITES_ID = "__local_source_test_sites__"
    RETEST_SITES_ID = "__local_source_retest_sites__"
    SCAN_BASE_PATH_ID = "__local_source_scan_base_path__"
    RESET_SCAN_BASE_ID = "__local_source_reset_scan_base__"
    ACTION_RESCAN = "local_source_rescan"
    ACTION_CLEAR_SITES = "local_source_clear_sites"
    ACTION_DELETE_BACKUPS = "local_source_delete_backups"
    ACTION_TEST_SITES = "local_source_test_sites"
    ACTION_RETEST_SITES = "local_source_retest_sites"
    ACTION_EDIT_SCAN_BASE = "local_source_edit_scan_base"
    ACTION_RESET_SCAN_BASE = "local_source_reset_scan_base"
    ACTION_EDIT_SCAN_TYPES = "local_source_edit_scan_types"
    ACTION_APPLY_SCAN_CONFIG = "local_source_apply_scan_config"
    ACTION_TOGGLE_TYPE_PREFIX = "local_source_toggle_type:"
    ACTION_TOGGLE_AUTO_SCAN = "local_source_toggle_auto_scan"
    ACTION_TOGGLE_IGNORE_PREFIX = "local_source_toggle_ignore:"
    ACTION_ADULT_ALLOW_PREFIX = "local_source_adult_allow:"
    ACTION_ADULT_UNALLOW_PREFIX = "local_source_adult_unallow:"
    ACTION_EDIT_KEYWORDS = "local_source_edit_keywords"
    ACTION_KEYWORD_ALLOW_PREFIX = "local_source_keyword_allow:"
    ACTION_KEYWORD_UNALLOW_PREFIX = "local_source_keyword_unallow:"
    ACTION_RESET_ALL = "local_source_reset_all"
    RESET_ALL_SETTING_ID = "setting_reset_all"
    KEYWORDS_SETTING_ID = "setting_keywords"
    ACTION_RESTORE_SNAPSHOT_PREFIX = "local_source_restore_snapshot:"
    ACTION_SOURCE_PREFIX = "local_source_info:"
    EXPORT_LOCAL_JSON_ID = "__local_source_export_json__"
    ACTION_EXPORT_LOCAL_JSON = "local_source_export_json"
    
    # ========== 恶意代码扫描 ==========
    MALWARE_SCAN_ID = "__local_source_malware_scan__"
    ACTION_MALWARE_SCAN = "local_source_malware_scan"
    
    # ========== 导出连通性结果 ==========
    ACTION_EXPORT_TEST_RESULTS = "local_source_export_test_results"
    EXPORT_TEST_RESULTS_ID = "__local_source_export_test_results__"

    def __init__(self):
        super().__init__()
        self.lock = threading.RLock()
        self.inited = False
        self.scan_roots = [dict(item) for item in self.SCAN_ROOTS]
        self.configured_scan_roots = [dict(item) for item in self.scan_roots]
        self.scan_base_path = ""
        self.registry_path = self.REGISTRY_PATH
        self.output_path = self.OUTPUT_PATH
        self.settings_path = os.path.join(os.path.dirname(self.REGISTRY_PATH), "auto-loader.settings.json")
        self.cache_path = os.path.join(os.path.dirname(self.REGISTRY_PATH), "auto-loader.cache.json")
        self.backup_dir = os.path.join(os.path.dirname(self.REGISTRY_PATH), "backups")
        self.roots_config_path = os.path.join(
            os.path.dirname(self.REGISTRY_PATH), "auto-loader.roots.json"
        )
        self.log_path = os.path.join(
            os.path.dirname(self.REGISTRY_PATH), "auto-loader.log"
        )
        self.xbpq_api = self.XBPQ_API
        self.xbpq_jar = self.XBPQ_JAR
        self.html_api = self.HTML_API
        self.local_base_dir = self.LOCAL_BASE_DIR
        self.page_size = self.PAGE_SIZE
        self.max_scan_files = self.MAX_SCAN_FILES
        self.max_scan_depth = self.MAX_SCAN_DEPTH
        self.max_source_size = self.MAX_SOURCE_SIZE
        self.max_log_size = self.MAX_LOG_SIZE
        self.backup_before_write = self.BACKUP_BEFORE_WRITE
        self.allow_empty_write = self.ALLOW_EMPTY_WRITE
        self.generated_insert_index = self.GENERATED_INSERT_INDEX
        self.type_enabled = {source_type: True for source_type in self.TYPE_ORDER}
        self.pending_type_enabled = dict(self.type_enabled)
        self.config_dirty = False
        self.manual_ignored_sources = set()
        self.auto_blocked_sources = set()
        self.ignored_sources = set()
        # 18+ 成人内容过滤
        self.block_adult_sites = False
        self.pending_block_adult_sites = False
        self.adult_filter_revision = 0
        self.adult_blocked_sources = set()
        self.adult_allowed_sources = set()
        # 自定义关键词屏蔽（用户可自行配置白名单/黑名单）
        self.custom_block_keywords = []
        self.custom_allow_keywords = []
        self.keyword_blocked_sources = set()
        self.keyword_allowed_sources = set()
        self.site_test_results = {}
        self.incomplete_scan_roots = []
        self.incomplete_scan_types = set()
        self.strict_recognition = self.STRICT_RECOGNITION
        self.auto_reload_app = self.AUTO_RELOAD_APP
        self.auto_scan_on_empty = self.AUTO_SCAN_ON_EMPTY
        self.auto_scan_suspended = False
        self.app_server_ports = list(range(self.APP_PORT_START, self.APP_PORT_END + 1))
        self.last_app_port = 0
        self.cache = self._empty_cache()
        self.status = self._empty_status()
        self._dialog_refs = []
        self._notification_refs = []
        self._site_test_toast = None
        self._site_test_thread = None
        self._site_test_control_lock = threading.Lock()
        self._site_test_cancel = threading.Event()
        self._destroyed = False
        self._jar_inspection_cache = {}
        self._retest_pending = []
        self._retest_auto_blocked = set()
        self._reload_generation = 0
        self._author_scan_surprise_shown = False
        
        # 恶意代码检测器
        self.malware_detector = TVBoxMalwareDetector()
        self.malware_scan_result = None
        
        # 导出连通性结果路径
        self.test_results_export_path = os.path.join(self.STORAGE_ROOT, "tvbox", "可用站点结果.txt")

    def getName(self):
        return "本地源手动加载 {}（安全版）".format(self.VERSION)

    def init(self, extend=""):
        with self.lock:
            if self.inited:
                return
            self._apply_extend(extend)
            self._load_roots_config()
            self.configured_scan_roots = [dict(item) for item in self.scan_roots]
            self._load_settings()
            try:
                self._normalize_backup_storage()
            except Exception as exc:
                self._warn("历史备份整理失败: {}".format(exc))
            startup_warnings = list(self.status["warnings"])
            self._set_manual_idle_status()
            try:
                restored = self._restore_scan_snapshot()
            except Exception as exc:
                restored = False
                warning = "扫描快照恢复失败: {}".format(exc)
                startup_warnings.append(warning)
                self._log("WARN", warning)
            if not restored:
                try:
                    self._auto_scan_on_enter_locked()
                except Exception as exc:
                    self._warn("进入自动补扫失败: {}".format(exc))
            if startup_warnings:
                self.status["warnings"] = list(dict.fromkeys(
                    startup_warnings + self.status["warnings"]
                ))
            self.inited = True

    def _empty_cache(self):
        return {
            "sources": [],
            "ignored": [],
            "source_index": {},
            "type_counts": {},
            "ignored_counts": {},
        }

    def _empty_status(self):
        return {
            "scan_time": "-",
            "found": 0,
            "included": 0,
            "skipped": 0,
            "duplicates": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "ignored": 0,
            "stale_ignored_removed": 0,
            "adult_filtered": 0,
            "keyword_filtered": 0,
            "limit_reached": False,
            "manual_sites": 0,
            "generated_sites": 0,
            "added_sites": 0,
            "updated_sites": 0,
            "removed_sites": 0,
            "unchanged_sites": 0,
            "registry_changed": False,
            "write_state": "尚未扫描",
            "written": False,
            "warnings": [],
            "error": "",
        }

    # --------------------------------------------------------------------------
    # 可选 extend 配置
    # --------------------------------------------------------------------------
    def _apply_extend(self, extend):
        data = self._parse_extend(extend)
        if not isinstance(data, dict):
            return

        roots = data.get("scan_roots", data.get("scanRoots"))
        if isinstance(roots, list):
            normalized = self._normalize_scan_roots(roots)
            if normalized:
                self.scan_roots = normalized

        self.registry_path = self._string_option(
            data, ("registry_path", "registryPath", "base_config_path", "baseConfigPath"), self.registry_path
        )
        self.output_path = self._string_option(
            data, ("output_path", "outputPath"), self.registry_path
        )
        self.settings_path = self._string_option(
            data,
            ("settings_path", "settingsPath"),
            os.path.join(os.path.dirname(self.output_path), "auto-loader.settings.json"),
        )
        self.cache_path = self._string_option(
            data,
            ("cache_path", "cachePath"),
            os.path.join(os.path.dirname(self.output_path), "auto-loader.cache.json"),
        )
        self.backup_dir = self._string_option(
            data,
            ("backup_dir", "backupDir"),
            os.path.join(os.path.dirname(self.output_path), "backups"),
        )
        self.roots_config_path = self._string_option(
            data,
            ("roots_config_path", "rootsConfigPath"),
            os.path.join(os.path.dirname(self.output_path), "auto-loader.roots.json"),
        )
        self.log_path = self._string_option(
            data,
            ("log_path", "logPath"),
            os.path.join(os.path.dirname(self.output_path), "auto-loader.log"),
        )
        self.xbpq_api = self._string_option(data, ("xbpq_api", "xbpqApi"), self.xbpq_api)
        self.xbpq_jar = self._string_option(data, ("xbpq_jar", "xbpqJar"), self.xbpq_jar)
        self.html_api = self._string_option(data, ("html_api", "htmlApi"), self.html_api)
        self.page_size = self._int_option(data, ("page_size", "pageSize"), self.page_size, 1, 200)
        self.max_scan_files = self._int_option(
            data, ("max_scan_files", "maxScanFiles"), self.max_scan_files, 1, 20000
        )
        self.max_scan_depth = self._int_option(
            data, ("max_scan_depth", "maxScanDepth"), self.max_scan_depth, 0, 32
        )
        self.max_source_size = self._int_option(
            data,
            ("max_source_size", "maxSourceSize"),
            self.max_source_size,
            1024,
            100 * 1024 * 1024,
        )
        self.max_log_size = self._int_option(
            data,
            ("max_log_size", "maxLogSize"),
            self.max_log_size,
            16 * 1024,
            2 * 1024 * 1024,
        )
        self.backup_before_write = self._bool_option(
            data, ("backup_before_write", "backupBeforeWrite"), self.backup_before_write
        )
        self.allow_empty_write = self._bool_option(
            data, ("allow_empty_write", "allowEmptyWrite"), self.allow_empty_write
        )
        self.strict_recognition = self._bool_option(
            data, ("strict_recognition", "strictRecognition"), self.strict_recognition
        )
        self.auto_reload_app = self._bool_option(
            data, ("auto_reload_app", "autoReloadApp"), self.auto_reload_app
        )
        self.auto_scan_on_empty = self._bool_option(
            data, ("auto_scan_on_empty", "autoScanOnEmpty"), self.auto_scan_on_empty
        )
        self.block_adult_sites = self._bool_option(
            data, ("block_adult_sites", "blockAdultSites"), self.block_adult_sites
        )
        self.custom_block_keywords = self._keyword_list_option(
            data, ("custom_block_keywords", "customBlockKeywords", "block_keywords"),
            self.custom_block_keywords,
        )
        self.custom_allow_keywords = self._keyword_list_option(
            data, ("custom_allow_keywords", "customAllowKeywords", "allow_keywords"),
            self.custom_allow_keywords,
        )
        if "generated_insert_index" in data or "generatedInsertIndex" in data:
            value = data.get("generated_insert_index", data.get("generatedInsertIndex"))
            try:
                self.generated_insert_index = max(0, int(value))
            except Exception:
                self.generated_insert_index = None

    def _parse_extend(self, extend):
        if isinstance(extend, dict):
            return extend
        if not isinstance(extend, str) or not extend.strip():
            return {}
        text = extend.strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        path = text.replace("file://", "")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                return {}
        return {}

    def _load_roots_config(self):
        path = os.path.abspath(os.path.expanduser(self.roots_config_path))
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, list):
                roots = data
                limits = {}
            elif isinstance(data, dict):
                roots = data.get("roots", data.get("scan_roots", []))
                limits = data.get("limits", {})
            else:
                raise ValueError("顶层必须是数组或 JSON 对象")
            normalized = self._normalize_scan_roots(roots) if isinstance(roots, list) else []
            if normalized:
                self.scan_roots = normalized
            runtime = dict(data) if isinstance(data, dict) else {}
            if isinstance(runtime.get("runtime"), dict):
                runtime.update(runtime["runtime"])
            self.xbpq_api = self._string_option(
                runtime, ("xbpq_api", "xbpqApi"), self.xbpq_api
            )
            self.xbpq_jar = self._string_option(
                runtime, ("xbpq_jar", "xbpqJar"), self.xbpq_jar
            )
            self.log_path = self._string_option(
                runtime, ("log_path", "logPath"), self.log_path
            )
            if isinstance(limits, dict):
                self.max_scan_files = self._int_option(
                    limits,
                    ("max_files", "maxFiles"),
                    self.max_scan_files,
                    1,
                    20000,
                )
                self.max_scan_depth = self._int_option(
                    limits,
                    ("max_depth", "maxDepth"),
                    self.max_scan_depth,
                    0,
                    32,
                )
                self.max_source_size = self._int_option(
                    limits,
                    ("max_file_size", "maxFileSize"),
                    self.max_source_size,
                    1024,
                    100 * 1024 * 1024,
                )
                self.max_log_size = self._int_option(
                    limits,
                    ("max_log_size", "maxLogSize"),
                    self.max_log_size,
                    16 * 1024,
                    2 * 1024 * 1024,
                )
        except Exception as exc:
            self._warn("扫描目录配置读取失败，将使用自动探测目录: {}".format(exc))

    def _normalize_scan_roots(self, roots):
        result = []
        seen = set()
        for item in roots:
            if isinstance(item, str):
                path = item
                source_type = os.path.basename(path).upper()
                if source_type == "HTML":
                    pass
                elif source_type == "CSP":
                    pass
                elif source_type == "XBPQ":
                    pass
                elif source_type not in ("PY", "JS"):
                    continue
                extensions = self.TYPE_EXTENSIONS[source_type]
            elif isinstance(item, dict):
                path = str(item.get("path", "")).strip()
                source_type = str(item.get("type", "")).strip().upper()
                if source_type not in self.TYPE_ORDER:
                    continue
                extensions = item.get("extensions", self.TYPE_EXTENSIONS[source_type])
            else:
                continue
            if not path:
                continue
            if not isinstance(extensions, (list, tuple)):
                extensions = [extensions]
            extensions = [self._normalize_extension(ext) for ext in extensions]
            extensions = [ext for ext in extensions if ext]
            if not extensions:
                extensions = list(self.TYPE_EXTENSIONS[source_type])
            identity = (os.path.abspath(os.path.expanduser(path)), source_type)
            if identity in seen:
                continue
            seen.add(identity)
            result.append({"path": path, "type": source_type, "extensions": extensions})
        return result

    def _string_option(self, data, keys, fallback):
        for key in keys:
            if key in data and str(data.get(key, "")).strip():
                return str(data[key]).strip()
        return fallback

    def _int_option(self, data, keys, fallback, minimum, maximum):
        for key in keys:
            if key not in data:
                continue
            try:
                return max(minimum, min(maximum, int(data[key])))
            except Exception:
                return fallback
        return fallback

    def _bool_option(self, data, keys, fallback):
        for key in keys:
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        return fallback

    def _keyword_list_option(self, data, keys, fallback):
        """从配置读取关键词列表（支持 list 或逗号/换行分隔字符串）。"""
        for key in keys:
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, (list, tuple, set)):
                return self._normalize_keywords(value)
            if isinstance(value, str) and value.strip():
                return self._normalize_keywords([value])
        return list(fallback or [])

    def _normalize_keywords(self, values):
        """把关键词输入规范化为去重后的字符串列表。"""
        result = []
        seen = set()
        for item in values or []:
            for part in re.split(r"[,，;\n\r\t ]+", str(item or "").strip()):
                part = part.strip()
                if not part:
                    continue
                key = part.casefold()
                if key in seen:
                    continue
                seen.add(key)
                result.append(part)
        return result

    def _load_settings(self):
        path = os.path.abspath(os.path.expanduser(self.settings_path))
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                return
            type_enabled = data.get("type_enabled", data.get("typeEnabled", {}))
            if isinstance(type_enabled, dict):
                for source_type in self.TYPE_ORDER:
                    if source_type in type_enabled:
                        self.type_enabled[source_type] = self._as_bool(
                            type_enabled[source_type], True
                        )
            pending = data.get("pending_type_enabled", data.get("pendingTypeEnabled", {}))
            self.pending_type_enabled = dict(self.type_enabled)
            if isinstance(pending, dict):
                for source_type in self.TYPE_ORDER:
                    if source_type in pending:
                        self.pending_type_enabled[source_type] = self._as_bool(
                            pending[source_type], self.type_enabled[source_type]
                        )
            self.config_dirty = any(
                self.pending_type_enabled[source_type] != self.type_enabled[source_type]
                for source_type in self.TYPE_ORDER
            )
            scan_base = data.get("scan_base_path", data.get("scanBasePath", ""))
            if str(scan_base or "").strip():
                self._apply_scan_base_path(str(scan_base))
            test_results = data.get("site_test_results", data.get("siteTestResults", {}))
            if isinstance(test_results, dict):
                self.site_test_results = {
                    str(identity): result
                    for identity, result in test_results.items()
                    if str(identity).strip() and isinstance(result, dict)
                }
            self._retest_pending = list(dict.fromkeys(
                str(identity).strip()
                for identity in data.get(
                    "retest_pending", data.get("retestPending", [])
                )
                if str(identity).strip()
            )) if isinstance(
                data.get("retest_pending", data.get("retestPending", [])), list
            ) else []
            self._retest_auto_blocked = self._identity_set(
                data.get(
                    "retest_auto_blocked", data.get("retestAutoBlocked", [])
                )
            )
            manual_ignored = data.get(
                "manual_ignored_sources", data.get("manualIgnoredSources")
            )
            auto_blocked = data.get(
                "auto_blocked_sources", data.get("autoBlockedSources")
            )
            if isinstance(manual_ignored, list) or isinstance(auto_blocked, list):
                self.manual_ignored_sources = self._identity_set(manual_ignored)
                self.auto_blocked_sources = self._identity_set(auto_blocked)
            else:
                legacy_ignored = self._identity_set(
                    data.get("ignored_sources", data.get("ignoredSources", []))
                )
                self.manual_ignored_sources = legacy_ignored
                self.auto_blocked_sources = set()
            self.auto_blocked_sources = {
                identity
                for identity in self.auto_blocked_sources
                if self.site_test_results.get(identity, {}).get("state")
                != "limited"
            }
            self.block_adult_sites = self._as_bool(
                data.get("block_adult_sites", data.get("blockAdultSites", False)),
                self.block_adult_sites,
            )
            self.pending_block_adult_sites = self._as_bool(
                data.get(
                    "pending_block_adult_sites",
                    data.get("pendingBlockAdultSites", self.block_adult_sites),
                ),
                self.block_adult_sites,
            )
            self.adult_filter_revision = max(
                0, int(data.get("adult_filter_revision", 0) or 0)
            )
            self.adult_blocked_sources = self._identity_set(
                data.get("adult_blocked_sources", data.get("adultBlockedSources", []))
            )
            self.adult_allowed_sources = self._identity_set(
                data.get("adult_allowed_sources", data.get("adultAllowedSources", []))
            )
            self.custom_block_keywords = self._keyword_list_option(
                data,
                ("custom_block_keywords", "customBlockKeywords", "block_keywords"),
                self.custom_block_keywords,
            )
            self.custom_allow_keywords = self._keyword_list_option(
                data,
                ("custom_allow_keywords", "customAllowKeywords", "allow_keywords"),
                self.custom_allow_keywords,
            )
            self.keyword_blocked_sources = self._identity_set(
                data.get(
                    "keyword_blocked_sources",
                    data.get("keywordBlockedSources", []),
                )
            )
            self.keyword_allowed_sources = self._identity_set(
                data.get(
                    "keyword_allowed_sources",
                    data.get("keywordAllowedSources", []),
                )
            )
            self._sync_ignored_sources()
            self.strict_recognition = self._as_bool(
                data.get("strict_recognition", data.get("strictRecognition", self.strict_recognition)),
                self.strict_recognition,
            )
            self.auto_scan_on_empty = self._as_bool(
                data.get("auto_scan_on_empty", data.get("autoScanOnEmpty", self.auto_scan_on_empty)),
                self.auto_scan_on_empty,
            )
            self.auto_scan_suspended = self._as_bool(
                data.get("auto_scan_suspended", data.get("autoScanSuspended", False)),
                False,
            )
            self._author_scan_surprise_shown = self._as_bool(
                data.get(
                    "author_scan_surprise_shown",
                    data.get("authorScanSurpriseShown", False),
                ),
                False,
            )
            try:
                port = int(data.get("last_app_port", data.get("lastAppPort", 0)) or 0)
                self.last_app_port = port if self.APP_PORT_START <= port <= 65535 else 0
            except Exception:
                self.last_app_port = 0
        except Exception as exc:
            self._warn("扫描设置读取失败，将使用默认配置: {}".format(exc))

    def _identity_set(self, values):
        if not isinstance(values, (list, tuple, set)):
            return set()
        return {
            str(item).strip() for item in values if str(item).strip()
        }

    def _sync_ignored_sources(self):
        self.ignored_sources = set(self.manual_ignored_sources)
        self.ignored_sources.update(self.auto_blocked_sources)
        if self.block_adult_sites:
            self.ignored_sources.update(self.adult_blocked_sources)
        self.ignored_sources.update(self.keyword_blocked_sources)

    def _as_bool(self, value, fallback=False):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if value is None:
            return fallback
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _save_settings(self):
        path = os.path.abspath(os.path.expanduser(self.settings_path))
        data = {
            "type_enabled": {
                source_type: bool(self.type_enabled.get(source_type, True))
                for source_type in self.TYPE_ORDER
            },
            "pending_type_enabled": {
                source_type: bool(
                    self.pending_type_enabled.get(
                        source_type, self.type_enabled.get(source_type, True)
                    )
                )
                for source_type in self.TYPE_ORDER
            },
            "strict_recognition": bool(self.strict_recognition),
            "auto_scan_on_empty": bool(self.auto_scan_on_empty),
            "auto_scan_suspended": bool(self.auto_scan_suspended),
            "scan_base_path": self.scan_base_path,
            "ignored_sources": sorted(self.ignored_sources),
            "manual_ignored_sources": sorted(self.manual_ignored_sources),
            "auto_blocked_sources": sorted(self.auto_blocked_sources),
            "block_adult_sites": bool(self.block_adult_sites),
            "pending_block_adult_sites": bool(self.pending_block_adult_sites),
            "adult_filter_revision": int(self.adult_filter_revision or 0),
            "adult_blocked_sources": sorted(self.adult_blocked_sources),
            "adult_allowed_sources": sorted(self.adult_allowed_sources),
            "custom_block_keywords": list(self.custom_block_keywords),
            "custom_allow_keywords": list(self.custom_allow_keywords),
            "keyword_blocked_sources": sorted(self.keyword_blocked_sources),
            "keyword_allowed_sources": sorted(self.keyword_allowed_sources),
            "site_test_results": self.site_test_results,
            "retest_pending": list(self._retest_pending),
            "retest_auto_blocked": sorted(self._retest_auto_blocked),
            "last_app_port": int(self.last_app_port or 0),
            "author_scan_surprise_shown": bool(
                self._author_scan_surprise_shown
            ),
        }
        self._atomic_write_plain_json(path, data)

    def _normalize_scan_base_path(self, value):
        path = str(value or "").strip().strip('"').strip("'")
        if path.lower().startswith("file://"):
            path = path[7:]
        if not path:
            return ""
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.STORAGE_ROOT, path.lstrip("/"))
        return os.path.realpath(os.path.abspath(path))

    def _scan_roots_for_base(self, base_path):
        return [
            {
                "path": _detect_child_dir(base_path, "py", "python"),
                "type": "PY",
                "extensions": [".py"],
            },
            {
                "path": _detect_child_dir(base_path, "js", "javascript"),
                "type": "JS",
                "extensions": [".js", ".json"],
            },
            {
                "path": _detect_child_dir(base_path, "csp"),
                "type": "CSP",
                "extensions": [".json"],
            },
            {
                "path": _detect_child_dir(base_path, "XBPQ"),
                "type": "XBPQ",
                "extensions": [".json"],
            },
            {
                "path": _detect_child_dir(base_path, "html"),
                "type": "HTML",
                "extensions": [".html"],
            },
        ]

    def _apply_scan_base_path(self, value):
        path = self._normalize_scan_base_path(value)
        if path:
            self.scan_base_path = path
            self.local_base_dir = path
            self.scan_roots = self._scan_roots_for_base(path)
        else:
            self.scan_base_path = ""
            self.local_base_dir = self.LOCAL_BASE_DIR
            self.scan_roots = [dict(item) for item in self.configured_scan_roots]

    def _create_scan_base_tree(self, path):
        created = []
        try:
            if os.path.exists(path) and not os.path.isdir(path):
                raise ValueError("输入路径不是目录: {}".format(path))
            if not os.path.isdir(path):
                missing = []
                current = path
                while current and not os.path.exists(current):
                    missing.append(current)
                    parent = os.path.dirname(current)
                    if parent == current:
                        break
                    current = parent
                for directory in reversed(missing):
                    if os.path.isdir(directory):
                        continue
                    try:
                        os.mkdir(directory)
                    except FileExistsError:
                        if not os.path.isdir(directory):
                            raise
                    else:
                        created.append(directory)
            for root in self._scan_roots_for_base(path):
                directory = root["path"]
                if os.path.isdir(directory):
                    continue
                try:
                    os.mkdir(directory)
                except FileExistsError:
                    if not os.path.isdir(directory):
                        raise
                else:
                    created.append(directory)
            return created
        except Exception:
            self._remove_created_scan_dirs(created)
            raise

    def _remove_created_scan_dirs(self, directories):
        for directory in reversed(directories):
            try:
                os.rmdir(directory)
            except Exception:
                pass

    def _set_scan_base_path(self, value):
        path = self._normalize_scan_base_path(value)
        previous_path = self.scan_base_path
        previous_base = self.local_base_dir
        previous_roots = [dict(item) for item in self.scan_roots]
        created_dirs = []
        try:
            if path:
                created_dirs = self._create_scan_base_tree(path)
                if not os.access(path, os.R_OK):
                    raise ValueError("目录不可读: {}".format(path))
            self._apply_scan_base_path(path)
            self._save_settings()
            self._set_manual_idle_status(
                "扫描根目录已更新，等待点击一键扫描并加载"
            )
            self._clear_scan_cache_file()
            if created_dirs:
                self._log(
                    "INFO",
                    "扫描分类目录已自动创建: {}".format(
                        ", ".join(created_dirs)
                    ),
                )
        except Exception:
            self.scan_base_path = previous_path
            self.local_base_dir = previous_base
            self.scan_roots = previous_roots
            self._remove_created_scan_dirs(created_dirs)
            raise
        return self.scan_base_path

    def _set_pending_type_settings(self, values, block_adult_sites=None):
        previous = dict(self.pending_type_enabled)
        previous_dirty = self.config_dirty
        previous_block_adult = self.pending_block_adult_sites
        for source_type in self.TYPE_ORDER:
            if source_type in values:
                self.pending_type_enabled[source_type] = bool(values[source_type])
        if block_adult_sites is not None:
            self.pending_block_adult_sites = bool(block_adult_sites)
        self.config_dirty = any(
            self.pending_type_enabled[item] != self.type_enabled[item]
            for item in self.TYPE_ORDER
        ) or self.pending_block_adult_sites != self.block_adult_sites
        try:
            self._save_settings()
        except Exception:
            self.pending_type_enabled = previous
            self.config_dirty = previous_dirty
            self.pending_block_adult_sites = previous_block_adult
            raise
        return self.config_dirty

    def _current_android_activity(self, jclass):
        app_class = jclass("com.fongmi.android.tv.App")
        activity_class = jclass("android.app.Activity")
        modifier_class = jclass("java.lang.reflect.Modifier")
        app_info = app_class.getClass()
        activity_info = activity_class.getClass()

        for method in app_info.getDeclaredMethods():
            try:
                if not modifier_class.isStatic(method.getModifiers()):
                    continue
                if len(method.getParameterTypes()) != 0:
                    continue
                if not activity_info.isAssignableFrom(method.getReturnType()):
                    continue
                method.setAccessible(True)
                try:
                    activity = method.invoke(None, [])
                except Exception:
                    activity = method.invoke(None)
                if activity is not None:
                    return activity
            except Exception:
                continue

        app = None
        for field in app_info.getDeclaredFields():
            try:
                if not modifier_class.isStatic(field.getModifiers()):
                    continue
                if not app_info.isAssignableFrom(field.getType()):
                    continue
                field.setAccessible(True)
                app = field.get(None)
                if app is not None:
                    break
            except Exception:
                continue
        if app is not None:
            for field in app.getClass().getDeclaredFields():
                try:
                    if modifier_class.isStatic(field.getModifiers()):
                        continue
                    if not activity_info.isAssignableFrom(field.getType()):
                        continue
                    field.setAccessible(True)
                    activity = field.get(app)
                    if activity is not None:
                        return activity
                except Exception:
                    continue
        raise ValueError("未找到当前 Android 页面")

    def _android_ui_context(self, jclass):
        try:
            activity = self._current_android_activity(jclass)
            if activity is not None:
                return activity, activity
        except Exception:
            pass

        context_candidates = []
        try:
            app_class = jclass("com.fongmi.android.tv.App")
            for method_name in ("get", "getInstance", "instance"):
                try:
                    method = getattr(app_class, method_name)
                    context = method() if callable(method) else method
                    if context is not None:
                        context_candidates.append(context)
                except Exception:
                    continue
        except Exception:
            pass
        try:
            activity_thread = jclass("android.app.ActivityThread")
            context = activity_thread.currentApplication()
            if context is not None:
                context_candidates.append(context)
        except Exception:
            pass
        try:
            platform = jclass("com.chaquo.python.Python").getPlatform()
            for method_name in (
                "getApplication", "getApplicationContext", "getContext",
            ):
                try:
                    method = getattr(platform, method_name)
                    context = method() if callable(method) else method
                    if context is not None:
                        context_candidates.append(context)
                except Exception:
                    continue
        except Exception:
            pass
        return None, next(
            (context for context in context_candidates if context is not None),
            None,
        )

    def _open_scan_base_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            edit_text_class = jclass("android.widget.EditText")
            input_type = jclass("android.text.InputType")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            class SaveListener(dynamic_proxy(click_listener)):
                def __init__(self, edit):
                    super().__init__()
                    self.edit = edit

                def onClick(self, dialog, which):
                    try:
                        value = str(self.edit.getText().toString())
                        with owner.lock:
                            saved = owner._set_scan_base_path(value)
                        message = (
                            "扫描根目录已恢复自动探测"
                            if not saved
                            else "扫描根目录已保存: {}".format(saved)
                        )
                        toast_class.makeText(
                            activity, message, toast_class.LENGTH_LONG
                        ).show()
                    except Exception as exc:
                        toast_class.makeText(
                            activity,
                            "扫描根目录保存失败: {}".format(exc),
                            toast_class.LENGTH_LONG,
                        ).show()

            class CancelListener(dynamic_proxy(click_listener)):
                def onClick(self, dialog, which):
                    return None

            class ShowDialog(dynamic_proxy(runnable_class)):
                def run(self):
                    try:
                        self._run_dialog()
                    except Exception as exc:
                        message = "根目录输入框打开失败: {}".format(exc)
                        owner._log("ERROR", message)
                        try:
                            toast_class.makeText(
                                activity, message, toast_class.LENGTH_LONG
                            ).show()
                        except Exception:
                            owner._notify_app(message)

                def _run_dialog(self):
                    edit = edit_text_class(activity)
                    current = owner.scan_base_path or owner.local_base_dir
                    edit.setSingleLine(True)
                    edit.setInputType(
                        input_type.TYPE_CLASS_TEXT
                        | input_type.TYPE_TEXT_VARIATION_URI
                    )
                    edit.setHint("/storage/emulated/0/xxxx/xxx")
                    edit.setText(current)
                    edit.setSelection(len(current))
                    save_listener = SaveListener(edit)
                    cancel_listener = CancelListener()
                    builder = builder_class(activity)
                    builder.setTitle("设置扫描根目录")
                    builder.setView(edit)
                    builder.setPositiveButton("保存", save_listener)
                    builder.setNegativeButton("取消", cancel_listener)
                    dialog = builder.show()
                    edit.requestFocus()
                    owner._dialog_refs.extend(
                        [edit, save_listener, cancel_listener, dialog]
                    )
                    owner._dialog_refs = owner._dialog_refs[-12:]

            runner = ShowDialog()
            self._dialog_refs.append(runner)
            self._dialog_refs = self._dialog_refs[-12:]
            activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "根目录输入框打开失败: {}".format(exc)

    def _open_scan_types_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            linear_layout_class = jclass("android.widget.LinearLayout")
            text_view_class = jclass("android.widget.TextView")
            switch_class = jclass("android.widget.Switch")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            view_click_listener = jclass("android.view.View$OnClickListener")
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            class NoopListener(dynamic_proxy(click_listener)):
                def onClick(self, dialog, which):
                    return None

            class SaveButtonListener(dynamic_proxy(view_click_listener)):
                def __init__(self, switches, adult_switch, dialog):
                    super().__init__()
                    self.switches = switches
                    self.adult_switch = adult_switch
                    self.dialog = dialog

                def onClick(self, view):
                    values = {
                        source_type: bool(control.isChecked())
                        for source_type, control in self.switches.items()
                    }
                    try:
                        with owner.lock:
                            dirty = owner._set_pending_type_settings(
                                values,
                                block_adult_sites=bool(
                                    self.adult_switch.isChecked()
                                ),
                            )
                        message = (
                            "扫描类型已保存，请点击应用并加载"
                            if dirty
                            else "扫描类型设置未变更"
                        )
                        toast_class.makeText(
                            activity, message, toast_class.LENGTH_LONG
                        ).show()
                        self.dialog.dismiss()
                    except Exception as exc:
                        toast_class.makeText(
                            activity,
                            "扫描类型保存失败: {}".format(exc),
                            toast_class.LENGTH_LONG,
                        ).show()

            class ShowDialog(dynamic_proxy(runnable_class)):
                def run(self):
                    try:
                        self._run_dialog()
                    except Exception as exc:
                        message = "扫描类型开关打开失败: {}".format(exc)
                        owner._log("ERROR", message)
                        try:
                            toast_class.makeText(
                                activity, message, toast_class.LENGTH_LONG
                            ).show()
                        except Exception:
                            owner._notify_app(message)

                def _run_dialog(self):
                    density = float(
                        activity.getResources().getDisplayMetrics().density
                    )
                    padding = int(16 * density + 0.5)
                    row_padding = int(8 * density + 0.5)
                    container = linear_layout_class(activity)
                    container.setOrientation(linear_layout_class.VERTICAL)
                    container.setPadding(padding, row_padding, padding, 0)
                    description = text_view_class(activity)
                    description.setText(
                        "选择一键扫描时要读取的站点类型"
                    )
                    description.setTextSize(13.0)
                    description.setPadding(0, 0, 0, row_padding)
                    container.addView(description)
                    switches = {}
                    for source_type in owner.TYPE_ORDER:
                        control = switch_class(activity)
                        control.setText(
                            "{} 扫描".format(
                                owner.TYPE_LABEL.get(source_type, source_type)
                            )
                        )
                        control.setTextSize(16.0)
                        control.setChecked(
                            bool(
                                owner.pending_type_enabled.get(
                                    source_type,
                                    owner.type_enabled.get(source_type, True),
                                )
                            )
                        )
                        control.setPadding(0, row_padding, 0, row_padding)
                        control.setFocusable(True)
                        container.addView(control)
                        switches[source_type] = control
                    adult_switch = switch_class(activity)
                    adult_switch.setText("屏蔽 18+ 站点")
                    adult_switch.setTextSize(16.0)
                    adult_switch.setChecked(
                        bool(owner.pending_block_adult_sites)
                    )
                    adult_switch.setPadding(0, row_padding, 0, row_padding)
                    adult_switch.setFocusable(True)
                    container.addView(adult_switch)
                    noop_listener = NoopListener()
                    builder = builder_class(activity)
                    builder.setTitle("扫描类型开关")
                    builder.setView(container)
                    builder.setPositiveButton("保存", noop_listener)
                    builder.setNegativeButton("取消", noop_listener)
                    dialog = builder.show()
                    save_listener = SaveButtonListener(
                        switches, adult_switch, dialog
                    )
                    dialog.getButton(-1).setOnClickListener(save_listener)
                    owner._dialog_refs.append(
                        [
                            container,
                            description,
                            switches,
                            adult_switch,
                            noop_listener,
                            save_listener,
                            dialog,
                        ]
                    )
                    owner._dialog_refs = owner._dialog_refs[-12:]

            runner = ShowDialog()
            self._dialog_refs.append(runner)
            self._dialog_refs = self._dialog_refs[-12:]
            activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "扫描类型开关打开失败: {}".format(exc)

    def _set_keywords(self, block_text, allow_text):
        """保存自定义黑/白名单关键词；黑名单变化后清除旧命中，重扫时重新评估。"""
        previous_block = list(self.custom_block_keywords)
        previous_allow = list(self.custom_allow_keywords)
        previous_blocked = set(self.keyword_blocked_sources)
        self.custom_block_keywords = self._normalize_keywords([block_text])
        self.custom_allow_keywords = self._normalize_keywords([allow_text])
        self.keyword_blocked_sources = set()
        self._sync_ignored_sources()
        try:
            self._save_settings()
        except Exception:
            self.custom_block_keywords = previous_block
            self.custom_allow_keywords = previous_allow
            self.keyword_blocked_sources = previous_blocked
            raise
        return "关键词已保存：黑名单 {} 条 · 白名单 {} 条，请点击扫描并加载生效".format(
            len(self.custom_block_keywords), len(self.custom_allow_keywords)
        )

    def _open_keywords_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            edit_text_class = jclass("android.widget.EditText")
            linear_layout_class = jclass("android.widget.LinearLayout")
            text_view_class = jclass("android.widget.TextView")
            input_type = jclass("android.text.InputType")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            class SaveListener(dynamic_proxy(click_listener)):
                def __init__(self, block_edit, allow_edit):
                    super().__init__()
                    self.block_edit = block_edit
                    self.allow_edit = allow_edit

                def onClick(self, dialog, which):
                    try:
                        block_text = str(self.block_edit.getText().toString())
                        allow_text = str(self.allow_edit.getText().toString())
                        with owner.lock:
                            message = owner._set_keywords(block_text, allow_text)
                        toast_class.makeText(
                            activity, message, toast_class.LENGTH_LONG
                        ).show()
                    except Exception as exc:
                        toast_class.makeText(
                            activity,
                            "关键词保存失败: {}".format(exc),
                            toast_class.LENGTH_LONG,
                        ).show()

            class CancelListener(dynamic_proxy(click_listener)):
                def onClick(self, dialog, which):
                    return None

            class ShowDialog(dynamic_proxy(runnable_class)):
                def run(self):
                    try:
                        self._run_dialog()
                    except Exception as exc:
                        message = "关键词输入框打开失败: {}".format(exc)
                        owner._log("ERROR", message)
                        try:
                            toast_class.makeText(
                                activity, message, toast_class.LENGTH_LONG
                            ).show()
                        except Exception:
                            owner._notify_app(message)

                def _run_dialog(self):
                    density = float(
                        activity.getResources().getDisplayMetrics().density
                    )
                    padding = int(16 * density + 0.5)
                    row_padding = int(8 * density + 0.5)
                    container = linear_layout_class(activity)
                    container.setOrientation(linear_layout_class.VERTICAL)
                    container.setPadding(padding, row_padding, padding, 0)

                    block_label = text_view_class(activity)
                    block_label.setText(
                        "黑名单关键词（命中即屏蔽，逗号或换行分隔）"
                    )
                    block_label.setTextSize(14.0)
                    block_label.setPadding(0, 0, 0, row_padding)
                    container.addView(block_label)
                    block_edit = edit_text_class(activity)
                    block_edit.setSingleLine(False)
                    block_edit.setInputType(
                        input_type.TYPE_CLASS_TEXT
                        | input_type.TYPE_TEXT_FLAG_MULTI_LINE
                    )
                    block_edit.setText(", ".join(owner.custom_block_keywords))
                    container.addView(block_edit)

                    allow_label = text_view_class(activity)
                    allow_label.setText(
                        "白名单关键词（命中即放行，优先于黑名单/成人规则）"
                    )
                    allow_label.setTextSize(14.0)
                    allow_label.setPadding(0, row_padding, 0, row_padding)
                    container.addView(allow_label)
                    allow_edit = edit_text_class(activity)
                    allow_edit.setSingleLine(False)
                    allow_edit.setInputType(
                        input_type.TYPE_CLASS_TEXT
                        | input_type.TYPE_TEXT_FLAG_MULTI_LINE
                    )
                    allow_edit.setText(", ".join(owner.custom_allow_keywords))
                    container.addView(allow_edit)

                    save_listener = SaveListener(block_edit, allow_edit)
                    cancel_listener = CancelListener()
                    builder = builder_class(activity)
                    builder.setTitle("关键词屏蔽")
                    builder.setView(container)
                    builder.setPositiveButton("保存", save_listener)
                    builder.setNegativeButton("取消", cancel_listener)
                    dialog = builder.show()
                    owner._dialog_refs.extend(
                        [
                            container,
                            block_label,
                            allow_label,
                            block_edit,
                            allow_edit,
                            save_listener,
                            cancel_listener,
                            dialog,
                        ]
                    )
                    owner._dialog_refs = owner._dialog_refs[-12:]

            runner = ShowDialog()
            self._dialog_refs.append(runner)
            self._dialog_refs = self._dialog_refs[-12:]
            activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "关键词输入框打开失败: {}".format(exc)

    def _open_reset_all_dialog(self):
        """一键清除全部数据的二次确认对话框（此操作不可恢复）。"""
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            class ConfirmListener(dynamic_proxy(click_listener)):
                def onClick(self, dialog, which):
                    try:
                        with owner.lock:
                            message = owner._reset_all_data()
                        toast_class.makeText(
                            activity, message, toast_class.LENGTH_LONG
                        ).show()
                    except Exception as exc:
                        owner._log(
                            "ERROR", "清除全部数据失败: {}".format(exc)
                        )
                        toast_class.makeText(
                            activity,
                            "清除全部数据失败: {}".format(exc),
                            toast_class.LENGTH_LONG,
                        ).show()

            class CancelListener(dynamic_proxy(click_listener)):
                def onClick(self, dialog, which):
                    return None

            class ShowDialog(dynamic_proxy(runnable_class)):
                def run(self):
                    try:
                        self._run_dialog()
                    except Exception as exc:
                        message = "确认框打开失败: {}".format(exc)
                        owner._log("ERROR", message)
                        try:
                            toast_class.makeText(
                                activity, message, toast_class.LENGTH_LONG
                            ).show()
                        except Exception:
                            owner._notify_app(message)

                def _run_dialog(self):
                    confirm_listener = ConfirmListener()
                    cancel_listener = CancelListener()
                    builder = builder_class(activity)
                    builder.setTitle("一键清除全部数据")
                    builder.setMessage(
                        "将清除：屏蔽/放行名单、自定义关键词、站点测试结果、"
                        "扫描快照/缓存、历史备份，以及已生成的站点列表。\n\n"
                        "此操作不可恢复！确定继续吗？"
                    )
                    builder.setPositiveButton("清除", confirm_listener)
                    builder.setNegativeButton("取消", cancel_listener)
                    dialog = builder.show()
                    owner._dialog_refs.extend(
                        [confirm_listener, cancel_listener, dialog]
                    )
                    owner._dialog_refs = owner._dialog_refs[-12:]

            runner = ShowDialog()
            self._dialog_refs.append(runner)
            self._dialog_refs = self._dialog_refs[-12:]
            activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "清除数据确认框打开失败: {}".format(exc)

    def _apply_pending_type_settings(self):
        previous_types = dict(self.type_enabled)
        previous_pending = dict(self.pending_type_enabled)
        previous_block_adult = self.block_adult_sites
        previous_pending_block_adult = self.pending_block_adult_sites
        previous_dirty = self.config_dirty
        try:
            self.type_enabled = {
                source_type: bool(
                    self.pending_type_enabled.get(
                        source_type, self.type_enabled.get(source_type, True)
                    )
                )
                for source_type in self.TYPE_ORDER
            }
            self.pending_type_enabled = dict(self.type_enabled)
            self.block_adult_sites = bool(self.pending_block_adult_sites)
            self.pending_block_adult_sites = self.block_adult_sites
            self._sync_ignored_sources()
            self.config_dirty = False
            self._save_settings()
        except Exception:
            self.type_enabled = previous_types
            self.pending_type_enabled = previous_pending
            self.block_adult_sites = previous_block_adult
            self.pending_block_adult_sites = previous_pending_block_adult
            self.config_dirty = previous_dirty
            raise

    def _load_scan_cache_payload(self, warn=True):
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict) or data.get("version") != self.CACHE_VERSION:
                return {}
            return data
        except Exception as exc:
            if warn:
                self._warn(
                    "增量扫描缓存读取失败，将全量扫描: {}".format(
                        exc
                    )
                )
            return {}

    def _load_scan_cache(self):
        data = self._load_scan_cache_payload()
        files = data.get("files", {}) if isinstance(data, dict) else {}
        return files if isinstance(files, dict) else {}

    def _save_scan_cache(self, files):
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        previous = self._load_scan_cache_payload(warn=False)
        data = {"version": self.CACHE_VERSION, "files": files}
        if isinstance(previous.get("snapshot"), dict):
            data["snapshot"] = previous["snapshot"]
        self._atomic_write_plain_json(path, data)

    def _scan_snapshot_sources(self):
        fields = (
            "id",
            "identity",
            "key",
            "type",
            "path",
            "scan_root",
            "root_order",
            "relative_in_root",
            "base_name",
            "package_label",
            "name",
            "validation",
            "ignored",
            "size",
            "mtime_ns",
            "csp_site",
            "dependencies",
            "test_result",
            "site",
        )
        result = []
        for source in self.cache["sources"] + self.cache["ignored"]:
            result.append(
                {
                    field: copy.deepcopy(source[field])
                    for field in fields
                    if field in source
                }
            )
        return result

    def _save_scan_snapshot(self):
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        data = self._load_scan_cache_payload(warn=False)
        files = data.get("files", {}) if isinstance(data, dict) else {}
        if not isinstance(files, dict):
            files = {}
        status_fields = (
            "scan_time",
            "found",
            "included",
            "skipped",
            "duplicates",
            "cache_hits",
            "cache_misses",
            "ignored",
            "stale_ignored_removed",
            "manual_sites",
            "generated_sites",
            "added_sites",
            "updated_sites",
            "removed_sites",
            "unchanged_sites",
        )
        data = {
            "version": self.CACHE_VERSION,
            "files": files,
            "snapshot": {
                "registry_token": self._registry_token(self.output_path),
                "sources": self._scan_snapshot_sources(),
                "status": {
                    field: copy.deepcopy(self.status.get(field))
                    for field in status_fields
                },
            },
        }
        self._atomic_write_plain_json(path, data)

    def _restore_scan_snapshot(self):
        data = self._load_scan_cache_payload(warn=False)
        snapshot = data.get("snapshot", {}) if isinstance(data, dict) else {}
        if not isinstance(snapshot, dict):
            return False
        expected_token = str(snapshot.get("registry_token", ""))
        if not expected_token or expected_token != self._registry_token(
            self.output_path
        ):
            return False
        raw_sources = snapshot.get("sources", [])
        if not isinstance(raw_sources, list):
            return False

        restored = self._empty_cache()
        seen_ids = set()
        for raw in raw_sources:
            if not isinstance(raw, dict):
                continue
            source = copy.deepcopy(raw)
            source_id = str(source.get("id", "")).strip()
            identity = str(source.get("identity", "")).strip()
            source_type = str(source.get("type", "")).upper()
            if (
                not source_id
                or source_id in seen_ids
                or not identity
                or source_type not in self.TYPE_ORDER
                or not isinstance(source.get("site"), dict)
            ):
                continue
            source["type"] = source_type
            source["ignored"] = identity in self.ignored_sources
            test_result = self.site_test_results.get(identity, {})
            if not isinstance(test_result, dict) or test_result.get(
                "source_signature"
            ) != self._source_signature(source):
                test_result = {}
            source["test_result"] = test_result
            seen_ids.add(source_id)
            restored["source_index"][source_id] = source
            if source["ignored"]:
                restored["ignored"].append(source)
                counts = restored["ignored_counts"]
            else:
                restored["sources"].append(source)
                counts = restored["type_counts"]
            counts[source_type] = counts.get(source_type, 0) + 1
        if not restored["sources"] and not restored["ignored"]:
            return False

        current_manual = self.status["manual_sites"]
        current_generated = self.status["generated_sites"]
        saved_status = snapshot.get("status", {})
        self.cache = restored
        if isinstance(saved_status, dict):
            for field in self._empty_status():
                if field in saved_status:
                    self.status[field] = copy.deepcopy(saved_status[field])
        self.status["included"] = len(restored["sources"])
        self.status["ignored"] = len(restored["ignored"])
        self.status["manual_sites"] = current_manual
        self.status["generated_sites"] = current_generated
        self.status["written"] = True
        self.status["registry_changed"] = False
        self.status["write_state"] = "已恢复上次成功扫描结果"
        self.status["error"] = ""
        return True

    def _atomic_write_plain_json(self, path, data):
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        temp_path = path + ".tmp"
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            with open(temp_path, "w", encoding="utf-8") as fp:
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temp_path, path)
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            raise

    def _reload_app_vod_config(self, expected_keys=None):
        if not self.auto_reload_app:
            return False, "注册表已写入；App 自动重载已关闭"
        expected = set(expected_keys) if expected_keys is not None else None
        with self.lock:
            self._reload_generation += 1
            generation = self._reload_generation
            worker = threading.Thread(
                target=self._delayed_app_vod_reload,
                args=(generation, expected),
                name="webhtv-csp-reload",
            )
            worker.daemon = True
            worker.start()
        self._log(
            "INFO",
            "已安排 App 主动重载: delay={}s sites={}".format(
                self.APP_RELOAD_DELAY,
                len(expected) if expected is not None else "-",
            ),
        )
        return True, "已安排主动重载 WebHTV 站点列表"

    def _delayed_app_vod_reload(self, generation, expected_keys):
        time.sleep(max(0.1, float(self.APP_RELOAD_DELAY)))
        try:
            with self.lock:
                if generation != self._reload_generation:
                    return
            ok, detail = self._perform_app_vod_reload(expected_keys)
            self._log("INFO" if ok else "WARN", detail)
            self._notify_app(detail)
        except Exception as exc:
            detail = "App 主动重载失败: {}".format(exc)
            self._log("ERROR", detail)
            self._notify_app(detail)

    def _perform_app_vod_reload(self, expected_keys=None):
        last_error = "未发现 WebHTV 本机服务"
        ports = []
        if self.last_app_port:
            ports.append(self.last_app_port)
        ports.extend(port for port in self.app_server_ports if port not in ports)
        for port in ports:
            base = "http://127.0.0.1:{}".format(port)
            try:
                payload = self._request_json(
                    base + "/manage/configs", self.APP_REQUEST_TIMEOUT
                )
                items = payload.get("items", []) if isinstance(payload, dict) else []
                current = next(
                    (
                        item
                        for item in items
                        if isinstance(item, dict)
                        and int(item.get("type", -1)) == 0
                        and bool(item.get("active", False))
                    ),
                    None,
                )
                if not current or not str(current.get("url", "")).strip():
                    last_error = "WebHTV 未返回当前点播接口"
                    continue
                query = urllib.parse.urlencode(
                    {"type": 0, "url": str(current["url"]).strip()}
                )
                self._request_json(
                    base + "/manage/config/use?" + query,
                    max(1.5, self.APP_REQUEST_TIMEOUT * 4),
                )
                self._remember_app_port(port)
                return True, "WebHTV 站点列表已主动重载，已触发页面刷新"
            except Exception as exc:
                last_error = str(exc)
        if last_error:
            self._warn("WebHTV 本机管理接口未确认: {}".format(last_error))
        return False, "App 主动重载失败，注册表已写入；重启 App 后生效"

    def _remember_app_port(self, port):
        with self.lock:
            if self.last_app_port == int(port):
                return
            self.last_app_port = int(port)
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("App 端口缓存保存失败: {}".format(exc))

    def _generated_registry_keys(self, registry=None):
        registry = registry if isinstance(registry, dict) else self._load_registry()
        return {
            self._registry_item_key(item)
            for item in registry.get("items", [])
            if self._is_generated_registry_item(item)
        }

    def _request_json(self, url, timeout):
        headers = {"Accept": "application/json", "Connection": "close"}
        request = urllib.request.Request(
            url,
            headers=headers,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            raw = response.read()
        if int(status) < 200 or int(status) >= 300:
            raise ValueError("HTTP {}".format(status))
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("WebHTV 本机接口返回格式无效")
        return data

    def _notify_app(self, message, wait=False, replace=False):
        text = " ".join(str(message or "").split()).strip()
        if not text or self._destroyed:
            return False
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            runnable_class = jclass("java.lang.Runnable")
            handler_class = jclass("android.os.Handler")
            looper_class = jclass("android.os.Looper")
            activity, context = self._android_ui_context(jclass)
            if context is None:
                return False
            handler = handler_class(looper_class.getMainLooper())
            owner = self
            displayed = threading.Event()

            class ShowNotification(dynamic_proxy(runnable_class)):
                def run(self):
                    try:
                        try:
                            toast = (
                                owner._site_test_toast
                                if replace
                                else None
                            )
                            if toast is None:
                                toast = toast_class.makeText(
                                    context,
                                    text[:120],
                                    toast_class.LENGTH_LONG,
                                )
                                if replace:
                                    owner._site_test_toast = toast
                            else:
                                toast.setText(text[:120])
                            toast.show()
                        except Exception as exc:
                            owner._log(
                                "WARN", "站点通知显示失败: {}".format(exc)
                            )
                    finally:
                        try:
                            owner._notification_refs.remove(self)
                        except (ValueError, AttributeError):
                            pass
                        displayed.set()

            runner = ShowNotification()
            self._notification_refs.append(runner)
            try:
                if activity is not None:
                    activity.runOnUiThread(runner)
                    queued = True
                else:
                    queued = handler.post(runner)
            except Exception:
                self._notification_refs.remove(runner)
                raise
            if queued is not None and not bool(queued):
                self._notification_refs.remove(runner)
                return False
            if wait and not displayed.wait(1.5):
                self._log("WARN", "站点通知等待 UI 显示超时: {}".format(text))
                return False
            return True
        except Exception as exc:
            try:
                self._log("WARN", "站点通知调度失败: {}".format(exc))
            except Exception:
                pass
            return False

    def _show_author_scan_surprise(self):
        if not self.cache["sources"]:
            return False
        first_scan = not self._author_scan_surprise_shown
        added_sites = max(0, int(self.status.get("added_sites", 0) or 0))
        if first_scan:
            message = "恭喜你已点亮 {} 个站点。".format(
                len(self.cache["sources"])
            )
        elif added_sites:
            message = "恭喜你又点亮 {} 个新站点。".format(
                added_sites
            )
        else:
            return False
        if not self._notify_app(message):
            return False
        if first_scan:
            self._author_scan_surprise_shown = True
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("作者彩蛋状态保存失败: {}".format(exc))
        self._log(
            "INFO",
            "{}扫描彩蛋已显示: {}".format(
                "首次手动" if first_scan else "新增站点", message
            ),
        )
        return True

    def _test_sites_locked(self, force=False):
        active_sources = list(self.cache["sources"])
        ignored_sources = list(self.cache["ignored"])
        all_sources = ignored_sources + active_sources
        source_by_identity = {
            source["identity"]: source for source in all_sources
        }
        if not all_sources:
            return {
                "tested": 0,
                "cached": 0,
                "available": 0,
                "unavailable": 0,
                "limited": 0,
                "blocked": 0,
                "restored": 0,
                "remaining": 0,
                "retest": False,
            }
        previous_ignored = set(self.ignored_sources)
        previous_manual_ignored = set(self.manual_ignored_sources)
        previous_auto_blocked = set(self.auto_blocked_sources)
        previous_results = dict(self.site_test_results)
        previous_cache = copy.deepcopy(self.cache)
        previous_status = self.status
        previous_retest_pending = list(self._retest_pending)
        previous_retest_auto_blocked = set(self._retest_auto_blocked)
        retest = bool(self._retest_pending)
        if force and not retest:
            self._retest_pending = [
                source["identity"] for source in all_sources
            ]
            self._retest_auto_blocked = set(self.auto_blocked_sources)
            for source in all_sources:
                self.site_test_results.pop(source["identity"], None)
                source["test_result"] = {}
            retest = True
        if retest:
            self._retest_pending = [
                identity
                for identity in self._retest_pending
                if identity in source_by_identity
            ]
            pending_identities = self._retest_pending[: self.MAX_SITE_TESTS]
            pending = [
                source_by_identity[identity] for identity in pending_identities
            ]
            pending_count = len(self._retest_pending)
            cached_count = max(0, len(all_sources) - pending_count)
        else:
            pending_all = [
                source
                for source in active_sources
                if not self._has_fresh_test_result(source)
            ]
            pending = pending_all[: self.MAX_SITE_TESTS]
            pending_count = len(pending_all)
            cached_count = len(active_sources) - len(pending_all)
        counts = {"available": 0, "unavailable": 0, "limited": 0}
        blocked = 0
        restored = 0
        total = len(pending)
        self._log(
            "INFO",
            "开始站点检测: 模式={} 待请求={} 缓存命中={} 总站点={}".format(
                "全部复检" if retest else "增量检测",
                total,
                cached_count,
                len(all_sources),
            ),
        )
        self._site_test_toast = None
        
        # 收集检测结果用于导出
        test_results_for_export = []
        
        try:
            for idx, source in enumerate(pending, 1):
                if self._site_test_cancel.is_set():
                    raise SiteTestCancelled("站点检测已取消")
                result = self._test_source_availability(source)
                if self._site_test_cancel.is_set():
                    raise SiteTestCancelled("站点检测已取消")
                result["source_signature"] = self._source_signature(source)
                state = result["state"]
                counts[state] += 1
                self.site_test_results[source["identity"]] = result
                source["test_result"] = result
                
                # 记录结果用于导出
                test_results_for_export.append({
                    "source": source,
                    "result": result,
                    "state": state
                })
                
                state_label = self._test_result_label(result)
                source_name = " ".join(
                    str(source.get("name", "未命名站点")).split()
                )[:60]
                self._log(
                    "INFO",
                    "站点检测 [{}/{}] {}: {} | {} | {}".format(
                        idx,
                        total,
                        source_name or "未命名站点",
                        state_label,
                        result.get("detail", ""),
                        source.get("path", source.get("identity", "")),
                    ),
                )
                notified = self._notify_app(
                    "[{}/{}] {}：{}".format(
                        idx, total, source_name or "未命名站点", state_label
                    ),
                    wait=True,
                    replace=True,
                )
                if notified:
                    time.sleep(0.25)
                if (
                    state == "unavailable"
                    and source["identity"] not in self.auto_blocked_sources
                ):
                    was_ignored = source["identity"] in self.ignored_sources
                    self.auto_blocked_sources.add(source["identity"])
                    self._sync_ignored_sources()
                    if not was_ignored:
                        blocked += 1
                elif (
                    state != "unavailable"
                    and source["identity"] in self._retest_auto_blocked
                    and source["identity"] in self.auto_blocked_sources
                ):
                    self.auto_blocked_sources.discard(source["identity"])
                    self._sync_ignored_sources()
                    self._retest_auto_blocked.discard(source["identity"])
                    restored += 1
            if retest:
                processed = {source["identity"] for source in pending}
                self._retest_pending = [
                    identity
                    for identity in self._retest_pending
                    if identity not in processed
                ]
                remaining = len(self._retest_pending)
                if not remaining:
                    self._retest_auto_blocked.clear()
            else:
                remaining = max(0, pending_count - len(pending))
            self._save_settings()
            if blocked or restored:
                if not self._refresh_locked(allow_empty=True):
                    raise ValueError(self.status["error"] or self.status["write_state"])
            
            # 导出连通性检测结果
            try:
                self._export_test_results(test_results_for_export)
            except Exception as exc:
                self._warn("导出连通性检测结果失败: {}".format(exc))
            
            summary = {
                "tested": len(pending),
                "cached": cached_count,
                "available": counts["available"],
                "unavailable": counts["unavailable"],
                "limited": counts["limited"],
                "blocked": blocked,
                "restored": restored,
                "remaining": remaining,
                "retest": retest,
            }
            self._log(
                "INFO",
                "站点检测完成: 请求={tested} 可达={available} 结构无效={unavailable} "
                "受限={limited} 新增失效屏蔽={blocked} 恢复={restored} 剩余={remaining}".format(
                    **summary
                ),
            )
            return summary
        except Exception as exc:
            self._log(
                "INFO" if isinstance(exc, SiteTestCancelled) else "ERROR",
                "站点检测批次{}: {}".format(
                    "已取消" if isinstance(exc, SiteTestCancelled) else "失败",
                    exc,
                ),
            )
            self.ignored_sources = previous_ignored
            self.manual_ignored_sources = previous_manual_ignored
            self.auto_blocked_sources = previous_auto_blocked
            self.site_test_results = previous_results
            self.cache = previous_cache
            self.status = previous_status
            self._retest_pending = previous_retest_pending
            self._retest_auto_blocked = previous_retest_auto_blocked
            try:
                self._save_settings()
            except Exception:
                pass
            raise

    def _export_test_results(self, test_results_for_export):
        """导出连通性检测结果到文件"""
        if not test_results_for_export:
            return
        
        # 按状态分组，每种状态内按类型排序（PY > JS > HTML）
        type_order = {"PY": 0, "JS": 1, "HTML": 2}
        
        grouped = {
            "available": [],
            "unavailable": [],
            "limited": [],
            "blocked": []
        }
        
        # 收集新增屏蔽的站点
        blocked_identities = set(self.auto_blocked_sources)
        previous_blocked = set(self._retest_auto_blocked)
        newly_blocked = blocked_identities - previous_blocked
        
        for item in test_results_for_export:
            source = item["source"]
            state = item["state"]
            source_type = source.get("type", "")
            file_name = os.path.basename(source.get("path", ""))
            
            # 获取显示名称
            display_name = source.get("name", file_name)
            
            entry = {
                "name": display_name,
                "file_name": file_name,
                "type": source_type,
                "path": source.get("path", ""),
                "result": item["result"]
            }
            
            if state == "available":
                grouped["available"].append(entry)
            elif state == "unavailable":
                grouped["unavailable"].append(entry)
            elif state == "limited":
                grouped["limited"].append(entry)
            
            # 检查是否被屏蔽
            identity = source.get("identity", "")
            if identity in newly_blocked:
                grouped["blocked"].append(entry)
        
        # 对每个分组按类型排序
        for key in grouped:
            grouped[key].sort(key=lambda x: type_order.get(x.get("type", ""), 99))
        
        # 生成输出内容
        lines = []
        lines.append("=" * 60)
        lines.append("TVBox 本地站点连通性检测结果")
        lines.append("检测时间: {}".format(time.strftime("%Y-%m-%d %H:%M:%S")))
        lines.append("结果仅供参考")
        lines.append("=" * 60)
        lines.append("")
        
        # 可用站点
        if grouped["available"]:
            lines.append("【可用站点】")
            for entry in grouped["available"]:
                type_label = entry.get("type", "")
                file_name = entry.get("file_name", "")
                display_name = entry.get("name", file_name)
                lines.append("  {} {}".format(
                    file_name,
                    "({})".format(display_name) if display_name != file_name else ""
                ))
            lines.append("")
        
        # 不可用站点
        if grouped["unavailable"]:
            lines.append("【不可用站点】")
            for entry in grouped["unavailable"]:
                file_name = entry.get("file_name", "")
                display_name = entry.get("name", file_name)
                lines.append("  {} {}".format(
                    file_name,
                    "({})".format(display_name) if display_name != file_name else ""
                ))
            lines.append("")
        
        # 受限站点
        if grouped["limited"]:
            lines.append("【受限站点】")
            for entry in grouped["limited"]:
                file_name = entry.get("file_name", "")
                display_name = entry.get("name", file_name)
                lines.append("  {} {}".format(
                    file_name,
                    "({})".format(display_name) if display_name != file_name else ""
                ))
            lines.append("")
        
        # 结构无效站点（unavailable 已在上面显示）
        
        # 新增屏蔽站点
        if grouped["blocked"]:
            lines.append("【新增屏蔽站点】")
            for entry in grouped["blocked"]:
                file_name = entry.get("file_name", "")
                display_name = entry.get("name", file_name)
                lines.append("  {} {}".format(
                    file_name,
                    "({})".format(display_name) if display_name != file_name else ""
                ))
            lines.append("")
        
        lines.append("=" * 60)
        lines.append("总计: 可用 {} | 不可用 {} | 受限 {} | 新增屏蔽 {}".format(
            len(grouped["available"]),
            len(grouped["unavailable"]),
            len(grouped["limited"]),
            len(grouped["blocked"])
        ))
        lines.append("导出路径: {}".format(self.test_results_export_path))
        
        # 写入文件
        output_dir = os.path.dirname(self.test_results_export_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        with open(self.test_results_export_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        self._log("INFO", "连通性检测结果已导出: {}".format(self.test_results_export_path))

    def _site_test_summary_text(self, summary):
        return (
            "站点检测完成：请求 {tested}，可达 {available}，"
            "结构无效 {unavailable}，受限 {limited}，"
            "新增屏蔽 {blocked}，恢复 {restored}，剩余 {remaining}"
        ).format(**summary)

    def _run_site_test_worker(self, force):
        current = threading.current_thread()
        try:
            summary = self._test_sites_locked(force=force)
            if summary["blocked"] or summary["restored"]:
                _, reload_detail = self._reload_app_vod_config(
                    expected_keys=self._generated_registry_keys()
                )
            else:
                reload_detail = "屏蔽状态未变化，无需重载"
            self.inited = True
            summary_text = self._site_test_summary_text(summary)
            export_msg = "，结果已导出至 {}".format(self.test_results_export_path) if summary["tested"] > 0 else ""
            self._log("INFO", "{}{}；{}".format(summary_text, export_msg, reload_detail))
            if not self._destroyed:
                self._notify_app(summary_text + export_msg)
        except SiteTestCancelled:
            self._log("INFO", "站点检测后台任务已取消")
        except Exception as exc:
            message = "站点检测失败：{}".format(exc)
            self._log("ERROR", "站点检测后台任务失败: {}".format(exc))
            if not self._destroyed:
                self._notify_app(message)
        finally:
            with self._site_test_control_lock:
                if self._site_test_thread is current:
                    self._site_test_thread = None

    def _start_site_test_worker(self, force=False):
        with self.lock:
            with self._site_test_control_lock:
                worker = self._site_test_thread
                if worker is not None and worker.is_alive():
                    return False
                worker = threading.Thread(
                    target=self._run_site_test_worker,
                    args=(bool(force),),
                    name="webhtv-site-test",
                )
                worker.daemon = True
                self._destroyed = False
                self._site_test_cancel.clear()
                self._site_test_thread = worker
                worker.start()
                return True

    def _site_test_is_running(self):
        with self._site_test_control_lock:
            worker = self._site_test_thread
            return worker is not None and worker.is_alive()

    def _source_signature(self, source):
        size = source.get("size")
        modified_ns = source.get("mtime_ns")
        if size is None or modified_ns is None:
            try:
                stat = os.stat(source["path"])
                size = stat.st_size
                modified_ns = getattr(
                    stat, "st_mtime_ns", int(stat.st_mtime * 1000000000)
                )
            except Exception:
                return "missing"
        signature_data = {
            "version": self.SITE_TEST_CACHE_VERSION,
            "type": str(source.get("type", "")).upper(),
            "size": int(size),
            "mtime_ns": int(modified_ns),
        }
        if source.get("dependencies"):
            dependency_stats = []
            for path in source.get("dependencies", []):
                try:
                    stat = os.stat(path)
                    dependency_stats.append(
                        {
                            "path": self._file_url(path),
                            "size": int(stat.st_size),
                            "mtime_ns": int(
                                getattr(
                                    stat,
                                    "st_mtime_ns",
                                    int(stat.st_mtime * 1000000000),
                                )
                            ),
                        }
                    )
                except Exception:
                    dependency_stats.append(
                        {"path": self._file_url(path), "missing": True}
                    )
            signature_data["dependencies"] = dependency_stats
        proxy_values = {
            name: str(os.environ.get(name, ""))
            for name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "no_proxy",
            )
            if os.environ.get(name)
        }
        signature_data["proxy"] = self._digest(
            json.dumps(proxy_values, sort_keys=True, separators=(",", ":")), 16
        )
        if signature_data["type"] == "XBPQ":
            signature_data["xbpq_api"] = self._runtime_reference(self.xbpq_api)
            signature_data["xbpq_jar"] = self._xbpq_jar_reference()
        raw = json.dumps(
            signature_data, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _has_fresh_test_result(self, source):
        result = self.site_test_results.get(source["identity"])
        return (
            isinstance(result, dict)
            and result.get("state") in ("available", "unavailable", "limited")
            and result.get("source_signature") == self._source_signature(source)
        )

    def _test_source_availability(self, source):
        checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        source_type = source["type"]
        path = source["path"]
        try:
            if not os.path.isfile(path) or not os.access(path, os.R_OK):
                return self._test_result("unavailable", "源文件不存在或不可读", checked_at)
            package_detail = ""
            if source.get("csp_site"):
                if "#bundle-site-" in str(source.get("identity", "")):
                    missing = [
                        item
                        for item in source.get("dependencies", [])
                        if not os.path.isfile(item) or not os.access(item, os.R_OK)
                    ]
                    if missing:
                        return self._test_result(
                            "unavailable",
                            "整包站点本地依赖已缺失: {}".format(missing[0]),
                            checked_at,
                        )
                    package_detail = source.get("validation", "") or "整包站点依赖完整"
                else:
                    valid, detail = self._validate_source(source_type, path)
                    if not valid:
                        return self._test_result("unavailable", detail, checked_at)
                    package_detail = (
                        detail
                        or source.get("validation", "")
                        or "目录包结构有效"
                    )
            if source_type == "HTML":
                valid, detail = self._validate_source("HTML", path)
                return self._test_result(
                    "available" if valid else "unavailable",
                    "本地 WebHome 页面结构有效" if valid else detail,
                    checked_at,
                )
            if source_type == "JS":
                text = self._read_text(
                    self._source_probe_path(source), 512 * 1024
                )
                if not self._has_quickjs_export(text):
                    return self._test_result(
                        "unavailable",
                        "未发现 QuickJS 导出入口",
                        checked_at,
                    )
            if source_type == "PY":
                valid, detail = self._validate_source("PY", path)
                if not valid:
                    return self._test_result("unavailable", detail, checked_at)
            if source_type == "XBPQ" and not source.get("csp_site"):
                ready, detail = self._xbpq_runtime_status()
                if not ready:
                    return self._test_result("unavailable", detail, checked_at)

            probe_url = self._source_probe_url(source)
            if not probe_url:
                probe_path = self._source_probe_path(source)
                probe_url = self._extract_probe_url(probe_path)
            if not probe_url:
                return self._test_result(
                    "limited",
                    "{}；未提取到可安全探测的主页地址".format(
                        package_detail                    ).lstrip("；"),
                    checked_at,
                )
            origin = self._url_origin(probe_url)
            if not origin:
                return self._test_result("limited", "主页地址格式无法确认", checked_at)
            state, detail = self._probe_site_url(probe_url)
            if package_detail:
                detail = package_detail + "；" + detail
            return self._test_result(state, detail, checked_at, origin)
        except Exception as exc:
            return self._test_result(
                "limited", "检测过程受限: {}".format(exc), checked_at
            )

    def _source_probe_path(self, source):
        site = source.get("csp_site", {})
        if isinstance(site, dict):
            fields = ("homePage", "ext", "api") if "#bundle-site-" in str(
                source.get("identity", "")
            ) else (("api",) if source.get("type") == "JS" else ("ext",))
            for field in fields:
                reference = site.get(field, "")
                if isinstance(reference, str) and reference.strip():
                    path = self._site_reference_path(reference)
                    if path and os.path.isfile(path) and os.access(path, os.R_OK):
                        return path
        return source["path"]

    def _source_probe_url(self, source):
        site = source.get("csp_site", {})
        if not isinstance(site, dict):
            return ""
        for field in ("homePage", "ext", "api"):
            value = site.get(field, "")
            if not isinstance(value, str):
                continue
            parsed = urllib.parse.urlsplit(value.strip())
            if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
                return value.strip()
        return ""

    def _test_result(self, state, detail, checked_at, origin=""):
        result = {
            "state": state,
            "detail": str(detail or "")[:240],
            "checked_at": checked_at,
        }
        if origin:
            result["origin"] = origin
        return result

    def _extract_probe_url(self, path):
        text = self._read_text(path, 512 * 1024)
        text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
        matches = re.findall(r"https?://[^\s\"'<>\\]+", text, flags=re.IGNORECASE)
        scored = []
        for index, value in enumerate(matches):
            value = value.rstrip("),;]}，。")
            parsed = urllib.parse.urlsplit(value)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                continue
            host = (parsed.hostname or "").lower()
            if host in ("127.0.0.1", "localhost") or host.endswith(".local"):
                continue
            lower = value.lower()
            score = -index
            if parsed.path in ("", "/"):
                score += 20
            if re.search(r"\.(?:jpg|jpeg|png|gif|webp|svg|m3u8|mp4|css|woff2?)(?:\?|$)", lower):
                score -= 50
            if host in ("example.com", "www.example.com"):
                score -= 100
            scored.append((score, value))
        return max(scored, default=(0, ""), key=lambda item: item[0])[1]

    def _url_origin(self, url):
        try:
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                return ""
            return "{}://{}/".format(parsed.scheme.lower(), parsed.netloc)
        except Exception:
            return ""

    def _probe_site_url(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Android; TVBox Site Check)",
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                "Range": "bytes=0-1023",
                "Connection": "close",
            },
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(), NoRedirectHandler()
        )
        try:
            with opener.open(request, timeout=self.SITE_TEST_TIMEOUT) as response:
                status = int(getattr(response, "status", response.getcode()))
                response.read(1024)
            if 200 <= status < 400:
                return "available", "站点地址可达 (HTTP {})".format(status)
            return "limited", "站点响应受限 (HTTP {})".format(status)
        except urllib.error.HTTPError as exc:
            if 300 <= int(exc.code) < 400:
                return "available", "站点地址可达并返回跳转 (HTTP {})".format(
                    exc.code
                )
            return "limited", "站点响应受限 (HTTP {})".format(exc.code)
        except urllib.error.URLError as exc:
            reason = exc.reason
            text = str(reason).lower()
            if isinstance(reason, socket.timeout) or "timed out" in text or "timeout" in text:
                return "limited", "主页连接超时"
            if isinstance(reason, (socket.gaierror, ConnectionRefusedError)) or any(
                marker in text
                for marker in (
                    "connection refused",
                    "name or service not known",
                    "nodename nor servname",
                    "no address associated",
                )
            ):
                return "limited", "站点网络不可达: {}".format(reason)
            return "limited", "站点连接受限: {}".format(reason)
        except (socket.timeout, TimeoutError):
            return "limited", "主页连接超时"
        except ConnectionRefusedError as exc:
            return "limited", "站点连接被拒绝: {}".format(exc)
        except Exception as exc:
            return "limited", "主页检测受限: {}".format(exc)

    def _test_result_label(self, result):
        if not isinstance(result, dict):
            return "未检测"
        return {
            "available": "可达",
            "unavailable": "疑似失效",
            "limited": "检测受限",
        }.get(str(result.get("state", "")), "未检测")

    def _normalize_extension(self, value):
        value = str(value or "").strip().lower()
        if not value:
            return ""
        return value if value.startswith(".") else "." + value

    # --------------------------------------------------------------------------
    # 扫描与配置生成
    # --------------------------------------------------------------------------
    def _ensure_initialized(self):
        if self.inited:
            return
        self.init("")

    def _refresh_locked(self, allow_empty=False):
        self.status = self._empty_status()
        self.status["scan_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        enabled_roots = [
            "{}={}".format(item.get("type", "?"), item.get("path", ""))
            for item in self.scan_roots
            if self.type_enabled.get(str(item.get("type", "")).upper(), True)
        ]
        self._log(
            "INFO",
            "开始扫描: allow_empty={} roots={}".format(
                bool(self.allow_empty_write or allow_empty),
                "; ".join(enabled_roots) or "无已开启目录",
            ),
        )
        try:
            self._scan_all_roots()
            if self.status["limit_reached"]:
                self.status["write_state"] = "扫描达到保护上限，已保护旧注册表"
                self.status["error"] = "请缩小扫描目录或调整 max_files"
                self._log("WARN", self.status["error"])
                return False
            if (
                not self.cache["sources"]
                and not self.cache["ignored"]
                and not (self.allow_empty_write or allow_empty)
            ):
                self.status["write_state"] = "未找到有效源，已保护旧配置"
                self.status["error"] = "扫描结果为空，未改写站点注入注册表"
                self._log("WARN", self.status["error"])
                return False
            self._generate_config()
            completed = self.status["written"] or self.status["write_state"] == "配置内容未变化"
            if completed:
                try:
                    self._save_scan_snapshot()
                except Exception as exc:
                    self._warn("扫描列表快照保存失败: {}".format(exc))
                if self.auto_scan_suspended:
                    self.auto_scan_suspended = False
                    try:
                        self._save_settings()
                    except Exception as exc:
                        self._warn("自动补扫状态保存失败: {}".format(exc))
            self._log(
                "INFO",
                "扫描完成: 发现={} 有效={} 忽略={} 跳过={} 重复={} 状态={}".format(
                    self.status["found"],
                    self.status["included"],
                    self.status["ignored"],
                    self.status["skipped"],
                    self.status["duplicates"],
                    self.status["write_state"],
                ),
            )
            return completed
        except Exception as exc:
            self.status["error"] = str(exc)
            self.status["write_state"] = "合并失败"
            self._log("ERROR", "扫描合并失败: {}".format(exc))
            return False

    def _auto_scan_on_enter_locked(self):
        """无有效快照时进入管理页自动补扫一次。

        仅扫描和写入注册表，不做站点网络检测；一键清除或恢复备份后暂停，
        直到下次手动扫描。进程内冷却防止"补扫 -> 重载 -> 再补扫"循环。
        """
        if not self.auto_scan_on_empty or self.auto_scan_suspended:
            return False
        if self.config_dirty or not any(self.type_enabled.values()):
            return False
        now = time.monotonic()
        if now - _AUTO_SCAN_STATE["last"] < self.AUTO_SCAN_COOLDOWN:
            return False
        _AUTO_SCAN_STATE["last"] = now
        ok = self._refresh_locked()
        if not ok:
            if (
                not self.cache["sources"]
                and not self.status["limit_reached"]
                and self.status["write_state"] == "未找到有效源，已保护旧配置"
            ):
                if self.cache["ignored"]:
                    self.status["write_state"] = "所有本地源均已被忽略，可在忽略分类中恢复"
                    self.status["error"] = ""
                else:
                    self._set_manual_idle_status("未发现本地源，等待点击一键扫描并加载")
            return False
        self.status["write_state"] += " · 进入自动补扫"
        if self.status["registry_changed"] and self._snapshot_matches_registry():
            self._reload_app_vod_config(
                expected_keys=self._generated_registry_keys()
            )
        return True

    def _suspend_auto_scan(self):
        if self.auto_scan_suspended:
            return
        self.auto_scan_suspended = True
        try:
            self._save_settings()
        except Exception as exc:
            self._warn("自动补扫暂停状态保存失败: {}".format(exc))

    def _snapshot_matches_registry(self):
        data = self._load_scan_cache_payload(warn=False)
        snapshot = data.get("snapshot", {}) if isinstance(data, dict) else {}
        if not isinstance(snapshot, dict):
            return False
        token = str(snapshot.get("registry_token", ""))
        return bool(token) and token == self._registry_token(self.output_path)

    def _set_manual_idle_status(self, state="等待点击一键扫描并加载"):
        self.cache = self._empty_cache()
        self.status = self._empty_status()
        self.status["write_state"] = state
        try:
            registry = self._load_registry()
            items = registry.get("items", [])
            if isinstance(items, list):
                self.status["generated_sites"] = sum(
                    1 for item in items if self._is_generated_registry_item(item)
                )
                self.status["manual_sites"] = len(items) - self.status["generated_sites"]
        except Exception as exc:
            self._warn("注册表状态读取失败: {}".format(exc))

    def _clear_scan_cache_file(self):
        removed = 0
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        protected = {
            os.path.abspath(os.path.expanduser(item))
            for item in (
                self.registry_path,
                self.output_path,
                self.settings_path,
                self.roots_config_path,
            )
        }
        if path in protected:
            self._warn("扫描缓存路径与配置文件冲突，已跳过删除: {}".format(path))
            return 0
        for candidate in (path, path + ".tmp"):
            try:
                os.remove(candidate)
                removed += 1
            except FileNotFoundError:
                pass
            except Exception as exc:
                self._warn("扫描缓存删除失败: {} ({})".format(candidate, exc))
        return removed

    def _scan_all_roots(self):
        self.cache = self._empty_cache()
        self._jar_inspection_cache = {}
        self.incomplete_scan_roots = []
        self.incomplete_scan_types = set()
        sources = []
        ignored_sources = []
        seen_paths = set()
        self_path = os.path.realpath(__file__)
        old_file_cache = self._load_scan_cache()
        new_file_cache = {}
        available_types = set()
        limit_reached = False

        for root_order, spec in enumerate(self.scan_roots):
            if limit_reached:
                break
            source_type = str(spec.get("type", "")).upper()
            if source_type not in self.TYPE_ORDER:
                self._warn("忽略未知类型目录: {}".format(spec))
                continue
            if not self.type_enabled.get(source_type, True):
                continue
            root = os.path.abspath(os.path.expanduser(str(spec.get("path", ""))))
            extensions = {
                self._normalize_extension(ext)
                for ext in spec.get("extensions", self.TYPE_EXTENSIONS[source_type])
            }
            extensions.discard("")
            if not os.path.isdir(root):
                self._warn("目录不存在: {}".format(root))
                self._mark_scan_incomplete(source_type, root)
                continue
            available_types.add(source_type)
            manifest_owned_paths = self._manifest_owned_source_paths(
                root, source_type
            )
            manifest_owned_paths.update(
                self._bundle_owned_source_paths(root, source_type)
            )
            if source_type in ("XBPQ", "CSP"):
                local_jar_pairs, local_jar_ambiguous = self._discover_json_jar_pairs(
                    root, manifest_owned_paths
                )
            else:
                local_jar_pairs, local_jar_ambiguous = {}, set()

            def walk_error(exc, current_type=source_type, current_root=root):
                failed_path = getattr(exc, "filename", "") or current_root
                self._mark_scan_incomplete(current_type, failed_path)
                self._warn("扫描目录读取失败: {} ({})".format(failed_path, exc))

            for current, dirs, files in os.walk(
                root, topdown=True, onerror=walk_error, followlinks=False
            ):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = sorted(
                    [
                        name
                        for name in dirs
                        if not name.startswith(".")
                        and name.lower() not in self.SKIP_DIRS
                        and not os.path.islink(os.path.join(current, name))
                    ],
                    key=lambda value: value.lower(),
                )
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                for file_name in sorted(files, key=lambda value: value.lower()):
                    full_path = os.path.join(current, file_name)
                    lower_name = file_name.lower()
                    extension = os.path.splitext(lower_name)[1]
                    if extension not in extensions:
                        continue
                    is_manifest = self._is_site_manifest_name(lower_name)
                    if source_type == "JS" and extension == ".json" and not is_manifest:
                        continue
                    candidate_path = os.path.realpath(full_path)
                    if not is_manifest and candidate_path in manifest_owned_paths:
                        continue
                    if (
                        source_type == "CSP"
                        and not is_manifest
                        and candidate_path not in local_jar_pairs
                        and candidate_path not in local_jar_ambiguous
                    ):
                        continue
                    if self.status["found"] >= self.max_scan_files:
                        limit_reached = True
                        self.status["limit_reached"] = True
                        self._warn(
                            "已达扫描文件上限 {}，后续文件未扫描".format(
                                self.max_scan_files
                            )
                        )
                        break
                    self.status["found"] += 1
                    if os.path.islink(full_path) or not os.path.isfile(full_path):
                        self.status["skipped"] += 1
                        continue
                    real_path = os.path.realpath(full_path)
                    if real_path == self_path:
                        continue
                    if real_path in seen_paths:
                        self.status["duplicates"] += 1
                        continue
                    try:
                        readable = os.access(real_path, os.R_OK)
                        stat = os.stat(real_path)
                        file_size = stat.st_size
                        modified_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1000000000))
                    except Exception as exc:
                        self.status["skipped"] += 1
                        self._mark_scan_incomplete(source_type, full_path)
                        self._warn("读取文件状态失败: {} ({})".format(real_path, exc))
                        continue
                    if not readable or file_size <= 0:
                        self.status["skipped"] += 1
                        self._warn("跳过不可读或空文件: {}".format(real_path))
                        continue
                    if file_size > self.max_source_size:
                        self.status["skipped"] += 1
                        self._warn(
                            "跳过超过大小上限的文件: {} ({} bytes)".format(
                                real_path, file_size
                            )
                        )
                        continue

                    relative_in_root = os.path.relpath(real_path, root).replace(os.sep, "/")
                    if self._is_excluded(source_type, lower_name, relative_in_root):
                        self.status["skipped"] += 1
                        continue
                    identity = self._source_identity(source_type, real_path)

                    bundle = None
                    if (
                        source_type in ("XBPQ", "CSP")
                        and extension == ".json"
                        and not is_manifest
                    ):
                        bundle = self._parse_site_bundle(real_path)
                    if bundle is not None:
                        role = self._detect_file_role(source_type, lower_name, real_path)
                        if role not in ("source", "forced_source"):
                            self.status["skipped"] += 1
                            self._warn("已按 {} 标识排除: {}".format(role, real_path))
                            continue
                        self.status["cache_misses"] += 1
                        seen_paths.add(real_path)
                        new_file_cache[identity] = {
                            "size": file_size,
                            "mtime_ns": modified_ns,
                            "strict": bool(self.strict_recognition),
                            "role": "bundle",
                            "valid": bool(bundle["sites"]),
                            "validation": "TVBox 整包配置",
                        }
                        for entry in bundle["sites"]:
                            site = entry["site"]
                            site_identity = self._bundle_source_identity(
                                source_type, real_path, site
                            )
                            if site_identity in seen_paths:
                                self.status["duplicates"] += 1
                                continue
                            seen_paths.add(site_identity)
                            new_file_cache[site_identity] = {
                                "size": file_size,
                                "mtime_ns": modified_ns,
                                "strict": bool(self.strict_recognition),
                                "role": "bundle_site",
                                "valid": True,
                                "validation": entry["validation"],
                            }
                            source_id = "src_" + self._digest(site_identity, 20)
                            key = (
                                self.GENERATED_KEY_PREFIX
                                + source_type.lower()
                                + "_"
                                + self._digest(site_identity, 14)
                            )
                            source = {
                                "id": source_id,
                                "identity": site_identity,
                                "key": key,
                                "type": source_type,
                                "path": real_path,
                                "scan_root": root,
                                "root_order": root_order,
                                "relative_in_root": "{}::site:{:04d}".format(
                                    relative_in_root, entry["index"]
                                ),
                                "base_name": str(site.get("name", "")).strip(),
                                "package_label": self._bundle_package_label(
                                    root, real_path
                                ),
                                "validation": entry["validation"],
                                "ignored": site_identity in self.ignored_sources,
                                "size": file_size,
                                "mtime_ns": modified_ns,
                                "csp_site": site,
                                "dependencies": entry["dependencies"],
                            }
                            test_result = self.site_test_results.get(site_identity, {})
                            if not isinstance(test_result, dict) or test_result.get(
                                "source_signature"
                            ) != self._source_signature(source):
                                test_result = {}
                            source["test_result"] = test_result
                            if source["ignored"]:
                                ignored_sources.append(source)
                            else:
                                sources.append(source)
                        rejected = bundle["rejected"]
                        self.status["skipped"] += len(rejected)
                        self._log(
                            "INFO",
                            "整包配置识别: {} 总站点={} 完整={} 跳过={}".format(
                                real_path,
                                bundle["total"],
                                len(bundle["sites"]),
                                len(rejected),
                            ),
                        )
                        if rejected:
                            self._warn(
                                "整包配置已跳过 {} 个依赖不完整站点: {}".format(
                                    len(rejected), os.path.basename(real_path)
                                )
                            )
                            for item in rejected:
                                self._log(
                                    "WARN",
                                    "整包站点已跳过: {} ({})".format(
                                        item["name"], item["reason"]
                                    ),
                                )
                        continue

                    cached = old_file_cache.get(identity)
                    cache_hit = (
                        isinstance(cached, dict)
                        and cached.get("size") == file_size
                        and cached.get("mtime_ns") == modified_ns
                        and cached.get("strict") == bool(self.strict_recognition)
                        and not is_manifest
                    )
                    if cache_hit:
                        role = str(cached.get("role", "source"))
                        valid = bool(cached.get("valid", True))
                        validation = str(cached.get("validation", ""))
                        self.status["cache_hits"] += 1
                    else:
                        role = self._detect_file_role(source_type, lower_name, real_path)
                        forced = role == "forced_source"
                        valid, validation = (
                            (True, "已通过 @tvbox-source 强制收录")
                            if forced
                            else self._validate_source(source_type, real_path)
                        )
                        self.status["cache_misses"] += 1
                    new_file_cache[identity] = {
                        "size": file_size,
                        "mtime_ns": modified_ns,
                        "strict": bool(self.strict_recognition),
                        "role": role,
                        "valid": bool(valid),
                        "validation": validation,
                    }
                    if role not in ("source", "forced_source"):
                        self.status["skipped"] += 1
                        self._warn("已按 {} 标识排除: {}".format(role, real_path))
                        continue
                    if not valid and self.strict_recognition:
                        self.status["skipped"] += 1
                        self._warn(validation)
                        continue
                    if validation and not valid:
                        self._warn(validation)
                    csp_site = None
                    dependencies = []
                    if source_type in ("XBPQ", "CSP") and not is_manifest:
                        if real_path in local_jar_ambiguous:
                            self.status["skipped"] += 1
                            self._warn(
                                "{} JAR 绑定不明确，已跳过: {}".format(
                                    source_type, real_path
                                )
                            )
                            continue
                        paired_jar = local_jar_pairs.get(real_path)
                        if paired_jar:
                            try:
                                if source_type == "XBPQ":
                                    csp_site, dependencies, validation = (
                                        self._auto_xbpq_site(real_path, paired_jar)
                                    )
                                else:
                                    csp_site, dependencies, validation = (
                                        self._auto_csp_site(real_path, paired_jar)
                                    )
                            except Exception as exc:
                                self.status["skipped"] += 1
                                self._warn(
                                    "{} 自动配对失败: {} ({})".format(
                                        source_type, real_path, exc
                                    )
                                )
                                continue
                        elif source_type == "XBPQ":
                            ready, runtime_message = self._xbpq_runtime_status()
                            if not ready:
                                self.status["skipped"] += 1
                                self.incomplete_scan_types.add(source_type)
                                self._warn(runtime_message)
                                continue
                    if is_manifest and source_type in ("JS", "XBPQ", "CSP"):
                        try:
                            csp_site, dependencies, validation = (
                                self._parse_site_manifest(real_path, source_type)
                            )
                        except Exception as exc:
                            self.status["skipped"] += 1
                            self._warn(
                                "站点清单解析失败: {} ({})".format(
                                    real_path, exc
                                )
                            )
                            continue

                    seen_paths.add(real_path)
                    if csp_site is not None:
                        base_name = str(csp_site.get("name", "")).strip()
                    else:
                        base_name = file_name[: -len(extension)] if extension else file_name
                    source_id = "src_" + self._digest(identity, 20)
                    key = self.GENERATED_KEY_PREFIX + source_type.lower() + "_" + self._digest(
                        identity, 14
                    )
                    source = {
                        "id": source_id,
                        "identity": identity,
                        "key": key,
                        "type": source_type,
                        "path": real_path,
                        "scan_root": root,
                        "root_order": root_order,
                        "relative_in_root": relative_in_root,
                        "base_name": base_name,
                        "validation": validation,
                        "ignored": identity in self.ignored_sources,
                        "size": file_size,
                        "mtime_ns": modified_ns,
                    }
                    if csp_site is not None:
                        source["csp_site"] = csp_site
                        source["dependencies"] = dependencies
                    test_result = self.site_test_results.get(identity, {})
                    if not isinstance(test_result, dict) or test_result.get(
                        "source_signature"
                    ) != self._source_signature(source):
                        test_result = {}
                    source["test_result"] = test_result
                    if source["ignored"]:
                        ignored_sources.append(source)
                    else:
                        sources.append(source)
                if limit_reached:
                    break

        all_sources = sources + ignored_sources
        self._apply_display_names(all_sources)
        all_sources.sort(
            key=lambda item: (
                item["root_order"],
                self.TYPE_ORDER[item["type"]],
                item["relative_in_root"].lower(),
            )
        )

        # 18+ 成人内容过滤：仅本地识别（站点名/内容关键词与正则），不上传服务器。
        # 命中且不在放行列表中的来源加入 adult_blocked_sources 并标记为忽略。
        # 用户白名单关键词命中的站点优先放行（覆盖成人规则）。
        if self.block_adult_sites:
            newly_adult = 0
            for source in all_sources:
                if source["ignored"]:
                    continue
                identity = source.get("identity", "")
                if not identity or identity in self.adult_allowed_sources:
                    continue
                if self._keyword_allow_match(source):
                    continue
                if self._is_adult_source(source):
                    self.adult_blocked_sources.add(identity)
                    source["ignored"] = True
                    newly_adult += 1
            if newly_adult:
                self._sync_ignored_sources()
                self.status["adult_filtered"] += newly_adult
                self._log(
                    "INFO",
                    "18+ 过滤已屏蔽 {} 个站点".format(newly_adult),
                )

        # 自定义关键词屏蔽：用户黑名单命中即屏蔽；白名单命中优先放行。
        if self.custom_block_keywords:
            newly_blocked = 0
            for source in all_sources:
                if source["ignored"]:
                    continue
                identity = source.get("identity", "")
                if not identity or identity in self.keyword_allowed_sources:
                    continue
                if self._keyword_allow_match(source):
                    continue
                if self._keyword_block_match(source):
                    self.keyword_blocked_sources.add(identity)
                    source["ignored"] = True
                    newly_blocked += 1
            if newly_blocked:
                self._sync_ignored_sources()
                self.status["keyword_filtered"] += newly_blocked
                self._log(
                    "INFO",
                    "关键词屏蔽 {} 个站点".format(newly_blocked),
                )

        deduplicated_sources = []
        active_fingerprints = set()
        for source in all_sources:
            source["site"] = self._build_site(source)
            fingerprint = self._site_fingerprint(source["site"])
            if (
                not source["ignored"]
                and fingerprint
                and fingerprint in active_fingerprints
            ):
                self.status["duplicates"] += 1
                self._log(
                    "INFO",
                    "语义重复站点已去重: {} ({})".format(
                        source["base_name"], source["relative_in_root"]
                    ),
                )
                continue
            if not source["ignored"] and fingerprint:
                active_fingerprints.add(fingerprint)
            deduplicated_sources.append(source)

        all_sources = deduplicated_sources
        for source in all_sources:
            self.cache["source_index"][source["id"]] = source
            source_type = source["type"]
            counts_key = "ignored_counts" if source["ignored"] else "type_counts"
            counts = self.cache[counts_key]
            counts[source_type] = counts.get(source_type, 0) + 1

        self.cache["sources"] = [item for item in all_sources if not item["ignored"]]
        self.cache["ignored"] = [item for item in all_sources if item["ignored"]]
        self.status["included"] = len(self.cache["sources"])
        self.status["ignored"] = len(self.cache["ignored"])
        stale_ignored = {
            identity
            for identity in self.ignored_sources
            if not limit_reached
            and identity.split("|", 1)[0] in available_types
            and not self._scan_failure_covers_identity(identity)
            and identity not in new_file_cache
        }
        if stale_ignored:
            self.manual_ignored_sources.difference_update(stale_ignored)
            self.auto_blocked_sources.difference_update(stale_ignored)
            self.adult_blocked_sources.difference_update(stale_ignored)
            self.keyword_blocked_sources.difference_update(stale_ignored)
            self._sync_ignored_sources()
            self.status["stale_ignored_removed"] = len(stale_ignored)
        stale_test_results = {
            identity
            for identity in self.site_test_results
            if not limit_reached
            and identity.split("|", 1)[0] in available_types
            and not self._scan_failure_covers_identity(identity)
            and identity not in new_file_cache
        }
        for identity in stale_test_results:
            self.site_test_results.pop(identity, None)
        if stale_ignored or stale_test_results:
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("过期扫描状态清理保存失败: {}".format(exc))
        for identity, cached in old_file_cache.items():
            if identity not in new_file_cache and self._scan_failure_covers_identity(identity):
                new_file_cache[identity] = cached
        try:
            self._save_scan_cache(new_file_cache)
        except Exception as exc:
            self._warn("增量扫描缓存保存失败: {}".format(exc))

    def _mark_scan_incomplete(self, source_type, path):
        source_type = str(source_type or "").upper()
        normalized = os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))
        marker = (source_type, normalized)
        if marker not in self.incomplete_scan_roots:
            self.incomplete_scan_roots.append(marker)

    def _reference_path(self, reference):
        value = str(reference or "").strip()
        if not value.lower().startswith("file://"):
            return ""
        path = value[7:]
        if not os.path.isabs(path):
            path = os.path.join(self.STORAGE_ROOT, path)
        return os.path.realpath(os.path.abspath(os.path.expanduser(path)))

    def _identity_source_path(self, identity):
        parts = str(identity or "").split("|", 1)
        reference = parts[1].split("#bundle-site-", 1)[0] if len(parts) == 2 else ""
        return self._reference_path(reference) if reference else ""

    def _path_is_within(self, path, parent):
        if not path or not parent:
            return False
        try:
            return os.path.commonpath((path, parent)) == parent
        except Exception:
            return False

    def _scan_failure_covers_identity(self, identity):
        source_type = str(identity or "").split("|", 1)[0].upper()
        if source_type in self.incomplete_scan_types:
            return True
        path = self._identity_source_path(identity)
        return any(
            item_type == source_type and self._path_is_within(path, failed_path)
            for item_type, failed_path in self.incomplete_scan_roots
        )

    def _source_identity(self, source_type, path):
        return source_type + "|" + self._file_url(path)

    def _bundle_source_identity(self, source_type, bundle_path, site):
        identity = {
            "key": str(site.get("key", "")),
            "name": str(site.get("name", "")),
            "api": site.get("api", ""),
            "ext": site.get("ext", ""),
            "jar": site.get("jar", ""),
            "homePage": site.get("homePage", site.get("home_page", "")),
        }
        raw = json.dumps(
            identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return "{}|{}#bundle-site-{}".format(
            source_type,
            self._file_url(bundle_path),
            self._digest(raw, 20),
        )

    def _bundle_package_label(self, scan_root, bundle_path):
        root = os.path.realpath(os.path.abspath(os.path.expanduser(str(scan_root))))
        path = os.path.realpath(os.path.abspath(os.path.expanduser(str(bundle_path))))
        try:
            relative = os.path.relpath(path, root)
        except Exception:
            relative = os.path.basename(path)
        parts = [part for part in relative.split(os.sep) if part not in ("", ".", "..")]
        if len(parts) > 1:
            label = parts[0]
        else:
            root_name = os.path.basename(root.rstrip(os.sep))
            generic_roots = {
                "xbpq", "csp", "js", "javascript", "py", "python", "html",
            }
            label = (
                os.path.splitext(os.path.basename(path))[0]
                if root_name.lower() in generic_roots
                else root_name
            )
        label = re.sub(r"[\r\n\t【】]+", " ", str(label)).strip()
        return label[:32] or os.path.splitext(os.path.basename(path))[0][:32] or "本地包"

    def _strip_json_comments(self, text):
        result = []
        index = 0
        in_string = False
        escaped = False
        length = len(text)
        while index < length:
            char = text[index]
            if in_string:
                result.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
                result.append(char)
                index += 1
                continue
            if char == "/" and index + 1 < length:
                marker = text[index + 1]
                if marker == "/":
                    index += 2
                    while index < length and text[index] not in "\r\n":
                        index += 1
                    continue
                if marker == "*":
                    index += 2
                    while index + 1 < length and text[index : index + 2] != "*/":
                        if text[index] in "\r\n":
                            result.append(text[index])
                        index += 1
                    index = min(length, index + 2)
                    continue
            result.append(char)
            index += 1
        return "".join(result)

    def _strip_json_trailing_commas(self, text):
        result = []
        index = 0
        in_string = False
        escaped = False
        length = len(text)
        while index < length:
            char = text[index]
            if in_string:
                result.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
                result.append(char)
                index += 1
                continue
            if char == ",":
                lookahead = index + 1
                while lookahead < length and text[lookahead].isspace():
                    lookahead += 1
                if lookahead < length and text[lookahead] in "}]":
                    index += 1
                    continue
            result.append(char)
            index += 1
        return "".join(result)

    def _load_json_compatible(self, path):
        with open(path, "r", encoding="utf-8-sig") as fp:
            text = fp.read()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = self._strip_json_trailing_commas(
                self._strip_json_comments(text)
            )
            return json.loads(cleaned)

    def _parse_site_bundle(self, path):
        try:
            data = self._load_json_compatible(path)
        except Exception:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("sites"), list):
            return None

        default_jar = data.get("spider", "")
        accepted = []
        rejected = []
        for index, raw_site in enumerate(data["sites"]):
            raw_name = "站点 #{}".format(index + 1)
            if isinstance(raw_site, dict):
                raw_name = str(
                    raw_site.get("name")
                    or raw_site.get("key")
                    or raw_name
                ).strip()
            try:
                site, dependencies, validation = self._normalize_bundle_site(
                    path, raw_site, default_jar, index
                )
                accepted.append(
                    {
                        "index": index,
                        "site": site,
                        "dependencies": dependencies,
                        "validation": validation,
                    }
                )
            except Exception as exc:
                rejected.append({"index": index, "name": raw_name, "reason": str(exc)})
        return {
            "total": len(data["sites"]),
            "sites": accepted,
            "rejected": rejected,
        }

    def _looks_like_bundle_local_reference(self, bundle_path, value, field):
        source = str(value or "").strip().split(";md5;", 1)[0].strip()
        if not source or source.startswith(("{", "[")):
            return False
        field_key = str(field or "").strip().lower()
        local_reference_fields = {
            "api", "ext", "jar", "homepage", "home_page", "filters", "filter",
            "class", "classes", "type", "config", "configs", "file", "path",
            "script", "source",
        }
        if field == "api" and source.startswith("csp_"):
            return False
        scheme = urllib.parse.urlsplit(source).scheme.lower()
        if scheme in ("http", "https", "assets", "proxy"):
            return False
        if scheme in ("file", "clan"):
            return True
        if scheme:
            return False
        if source.startswith(("./", "../")):
            return True
        if os.path.isabs(source):
            storage_root = os.path.realpath(os.path.abspath(self.STORAGE_ROOT))
            real_source = os.path.realpath(os.path.abspath(source))
            local_prefixes = ("/storage/", "/sdcard/", "/data/")
            if (
                os.path.exists(source)
                or real_source == storage_root
                or real_source.startswith(storage_root + os.sep)
                or source.startswith(local_prefixes)
            ):
                return True
        sibling = os.path.join(os.path.dirname(bundle_path), source)
        if os.path.exists(sibling):
            return True
        extension = os.path.splitext(source.lower())[1]
        local_extensions = {
            ".json", ".jsonc", ".jar", ".py", ".js", ".html", ".htm",
            ".txt", ".m3u", ".m3u8",
        }
        if field == "jar":
            return True
        return extension in local_extensions and field_key in local_reference_fields

    def _resolve_bundle_reference(self, bundle_path, value, field, with_md5=False):
        source = str(value or "").strip()
        suffix = ""
        if with_md5 and ";md5;" in source:
            source, digest = source.split(";md5;", 1)
            source = source.strip()
            suffix = ";md5;" + digest.strip().lower()
        parsed = urllib.parse.urlsplit(source)
        if parsed.scheme.lower() == "clan" and parsed.hostname in (
            "localhost", "127.0.0.1"
        ):
            local_path = os.path.join(self.STORAGE_ROOT, parsed.path.lstrip("/"))
            return self._file_url(local_path) + suffix
        if not self._looks_like_bundle_local_reference(
            bundle_path, source, field
        ):
            return source + suffix
        return self._resolve_site_reference(
            bundle_path, source + suffix, with_md5=with_md5
        )

    def _require_local_dependency(self, reference, label, with_md5=False):
        path = self._site_reference_path(reference, with_md5=with_md5)
        if not path:
            return ""
        if not os.path.isfile(path) or not os.access(path, os.R_OK):
            raise ValueError("{} 不存在或不可读: {}".format(label, reference))
        if os.path.getsize(path) <= 0:
            raise ValueError("{} 是空文件: {}".format(label, reference))
        return path

    def _normalize_bundle_nested_refs(
        self, bundle_path, value, field, dependencies
    ):
        if isinstance(value, dict):
            return {
                key: self._normalize_bundle_nested_refs(
                    bundle_path, item, str(key), dependencies
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._normalize_bundle_nested_refs(
                    bundle_path, item, field, dependencies
                )
                for item in value
            ]
        if not isinstance(value, str) or not self._looks_like_bundle_local_reference(
            bundle_path, value, field
        ):
            return value
        with_md5 = field == "jar"
        reference = self._resolve_bundle_reference(
            bundle_path, value, field, with_md5=with_md5
        )
        path = self._require_local_dependency(
            reference, field or "嵌套依赖", with_md5=with_md5
        )
        if path:
            if path.lower().endswith((".json", ".jsonc")):
                self._load_json_compatible(path)
            dependencies.append(path)
        return reference

    def _normalize_bundle_site(self, bundle_path, raw_site, default_jar, index):
        if not isinstance(raw_site, dict):
            raise ValueError("站点必须是 JSON 对象")
        site = copy.deepcopy(raw_site)
        raw_home_page = site.get("homePage", site.get("home_page", ""))
        is_webhome = isinstance(raw_home_page, str) and bool(raw_home_page.strip())
        api = self._runtime_reference(self.html_api) if is_webhome else str(
            site.get("api", "")
        ).strip()
        if not api:
            raise ValueError("缺少 api")

        dependencies = []
        validation = []
        api_is_local = self._looks_like_bundle_local_reference(
            bundle_path, api, "api"
        )
        if api_is_local:
            api = self._resolve_bundle_reference(bundle_path, api, "api")
            api_path = self._require_local_dependency(api, "api")
            lower_api = api_path.lower()
            if lower_api.endswith(".py"):
                valid, detail = self._validate_source("PY", api_path)
            elif lower_api.endswith(".js"):
                valid, detail = self._validate_source("JS", api_path)
            else:
                valid, detail = True, ""
            if not valid:
                raise ValueError(detail)
            dependencies.append(api_path)
            if detail:
                validation.append(detail)
            site["api"] = api
        else:
            scheme = urllib.parse.urlsplit(api).scheme.lower()
            if not api.startswith("csp_") and scheme not in (
                "http", "https", "assets", "proxy"
            ):
                raise ValueError("api 类型无法确认: {}".format(api))
            site["api"] = api

        home_page = raw_home_page
        if isinstance(home_page, str) and home_page.strip():
            resolved_home = self._resolve_bundle_reference(
                bundle_path, home_page, "homePage"
            )
            home_path = self._require_local_dependency(resolved_home, "homePage")
            if home_path:
                dependencies.append(home_path)
            site["homePage"] = resolved_home
            site["api"] = api
            site.pop("home_page", None)
        elif home_page not in (None, ""):
            raise ValueError("homePage 必须是路径或 URL")

        ext = "" if is_webhome else site.get("ext", "")
        if isinstance(ext, str) and ext.strip():
            resolved_ext = self._resolve_bundle_reference(bundle_path, ext, "ext")
            ext_path = self._require_local_dependency(resolved_ext, "ext")
            if ext_path:
                if ext_path.lower().endswith((".json", ".jsonc")):
                    self._load_json_compatible(ext_path)
                if api == "csp_XBPQ":
                    valid, detail = self._validate_source("XBPQ", ext_path)
                    if not valid:
                        raise ValueError(detail)
                    if detail:
                        validation.append(detail)
                dependencies.append(ext_path)
            site["ext"] = resolved_ext
        elif isinstance(ext, (dict, list)):
            site["ext"] = self._normalize_bundle_nested_refs(
                bundle_path, ext, "ext", dependencies
            )
        elif ext not in (None, "") and not isinstance(ext, (dict, list)):
            raise ValueError("ext 必须是路径、URL 或 JSON 对象")

        if is_webhome:
            site.pop("ext", None)
        jar_value = "" if is_webhome else site.get("jar", "")
        if (
            not is_webhome
            and not str(jar_value or "").strip()
            and api.startswith("csp_")
        ):
            jar_value = default_jar
        if jar_value:
            if not isinstance(jar_value, str):
                raise ValueError("jar 必须是路径或 URL")
            resolved_jar = self._resolve_bundle_reference(
                bundle_path, jar_value, "jar", with_md5=True
            )
            jar_detail = self._validate_site_jar(resolved_jar, api)
            jar_path = self._require_local_dependency(
                resolved_jar, "jar", with_md5=True
            )
            if jar_path and ";md5;" not in resolved_jar:
                resolved_jar += ";md5;" + self._inspect_local_jar(jar_path)["md5"]
            if jar_path:
                dependencies.append(jar_path)
            site["jar"] = resolved_jar
            if jar_detail:
                validation.append(jar_detail)
        elif api.startswith("csp_") and not str(site.get("homePage", "")).strip():
            raise ValueError("{} 缺少可验证的 jar".format(api))
        else:
            site.pop("jar", None)

        name = str(site.get("name") or site.get("key") or api).strip()
        if not name:
            name = "站点 #{}".format(index + 1)
        site["name"] = name
        site["type"] = int(site.get("type", 3))
        site.setdefault("searchable", 0 if is_webhome else self.DEFAULT_SEARCHABLE)
        site.setdefault("quickSearch", 0 if is_webhome else self.DEFAULT_QUICK_SEARCH)
        dependencies = list(dict.fromkeys(dependencies))
        return site, dependencies, "；".join(validation) or "整包站点本地依赖完整"

    def _manifest_owned_source_paths(self, root, source_type):
        source_type = str(source_type or "").upper()
        if source_type not in ("JS", "XBPQ", "CSP") or not os.path.isdir(root):
            return set()
        fields = ("api", "ext") if source_type == "JS" else ("ext",)
        result = set()
        try:
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = [
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and name.lower() not in self.SKIP_DIRS
                    and not os.path.islink(os.path.join(current, name))
                ]
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                for name in files:
                    if not self._is_site_manifest_name(name):
                        continue
                    path = os.path.join(current, name)
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    try:
                        data = self._load_json_compatible(path)
                        if isinstance(data, dict) and isinstance(data.get("site"), dict) and not data.get("api"):
                            data = data["site"]
                        if not isinstance(data, dict):
                            continue
                        for field in fields:
                            reference = data.get(field, "")
                            if not isinstance(reference, str) or not reference.strip():
                                continue
                            resolved = self._resolve_site_reference(path, reference)
                            dependency = self._site_reference_path(resolved)
                            if dependency:
                                result.add(dependency)
                    except Exception:
                        continue
        except Exception:
            return result
        return result

    def _bundle_owned_source_paths(self, root, source_type):
        source_type = str(source_type or "").upper()
        if source_type not in ("XBPQ", "CSP") or not os.path.isdir(root):
            return set()
        result = set()

        def collect(bundle_path, value, field=""):
            if isinstance(value, dict):
                for key, item in value.items():
                    collect(bundle_path, item, str(key))
            elif isinstance(value, list):
                for item in value:
                    collect(bundle_path, item, field)
            elif isinstance(value, str) and self._looks_like_bundle_local_reference(
                bundle_path, value, field
            ):
                reference = self._resolve_bundle_reference(
                    bundle_path, value, field, with_md5=field == "jar"
                )
                dependency = self._site_reference_path(
                    reference, with_md5=field == "jar"
                )
                if dependency:
                    result.add(dependency)

        try:
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = [
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and name.lower() not in self.SKIP_DIRS
                    and not os.path.islink(os.path.join(current, name))
                ]
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                for name in files:
                    if not name.lower().endswith((".json", ".jsonc")):
                        continue
                    path = os.path.join(current, name)
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    try:
                        if os.path.getsize(path) > self.max_source_size:
                            continue
                        data = self._load_json_compatible(path)
                        if not isinstance(data, dict) or not isinstance(
                            data.get("sites"), list
                        ):
                            continue
                        collect(path, data.get("spider", ""), "jar")
                        collect(path, data["sites"])
                    except Exception:
                        continue
        except Exception:
            return result
        return result

    def _discover_json_jar_pairs(self, root, manifest_owned_paths):
        pairs = {}
        ambiguous = set()
        owned = set(manifest_owned_paths or ())
        try:
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = [
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and name.lower() not in self.SKIP_DIRS
                    and not os.path.islink(os.path.join(current, name))
                ]
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                jars = []
                rules = []
                for name in files:
                    path = os.path.join(current, name)
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    lower_name = name.lower()
                    real_path = os.path.realpath(path)
                    if lower_name.endswith(".jar"):
                        jars.append(real_path)
                    elif (
                        lower_name.endswith(".json")
                        and not self._is_site_manifest_name(lower_name)
                        and real_path not in owned
                    ):
                        rules.append(real_path)
                if not jars or not rules:
                    continue
                if len(jars) == 1:
                    for rule in rules:
                        pairs[rule] = jars[0]
                    continue
                jars_by_stem = {}
                for jar in jars:
                    stem = os.path.splitext(os.path.basename(jar))[0].lower()
                    jars_by_stem.setdefault(stem, []).append(jar)
                for rule in rules:
                    stem = os.path.splitext(os.path.basename(rule))[0].lower()
                    matches = jars_by_stem.get(stem, [])
                    if len(matches) == 1:
                        pairs[rule] = matches[0]
                    else:
                        ambiguous.add(rule)
        except Exception as exc:
            self._warn("JSON/JAR 配对扫描失败: {} ({})".format(root, exc))
        return pairs, ambiguous

    def _is_site_manifest_name(self, lower_name):
        value = str(lower_name or "").lower()
        return value == "site.json" or value.endswith(".site.json")

    def _is_excluded(self, source_type, lower_name, relative_in_root):
        relative_lower = relative_in_root.lower()
        if lower_name.startswith("."):
            return True
        if (
            source_type == "JS"
            and lower_name.endswith(".json")
            and not self._is_site_manifest_name(lower_name)
        ):
            return True
        if source_type == "JS" and lower_name in self.JS_EXCLUDE:
            return True
        if source_type == "PY":
            if lower_name == "__init__.py":
                return True
            if relative_lower in self.PY_EXCLUDE_RELATIVE:
                return True
        return False

    def _detect_file_role(self, source_type, lower_name, path):
        try:
            text = self._read_text(path, 64 * 1024)
        except Exception:
            text = ""
        lower_text = text.lower()

        if "@tvbox-ignore" in lower_text:
            return "ignore"
        role_match = re.search(r"@tvbox-role\s*(?:[:=]\s*)?([a-z_-]+)", lower_text)
        if role_match:
            role = role_match.group(1)
            if role in ("manager", "extension", "library", "ignore"):
                return role
            if role == "source":
                return "forced_source"
        if "@tvbox-source" in lower_text:
            return "forced_source"

        if (
            source_type == "PY"
            and lower_name.startswith("自动加载")
            and lower_name.endswith(".py")
        ):
            return "manager"
        if source_type == "JS":
            if lower_name.endswith(self.JS_EXTENSION_SUFFIXES):
                return "extension"
            extension_signatures = (
                "window.fm",
                "fm.vodinline",
                "window.fongmibridge",
                "webhomeextensions",
                "gm_addstyle",
                "document-start",
                "fmsdk",
                "@match",
            )
            looks_like_extension = any(signature in lower_text for signature in extension_signatures)
            looks_like_rule = self._has_quickjs_export(text)
            if looks_like_extension and not looks_like_rule:
                return "extension"
        return "source"

    def _resolve_site_reference(self, manifest_path, reference, with_md5=False):
        value = str(reference or "").strip()
        if not value:
            return ""
        suffix = ""
        source = value
        if with_md5 and ";md5;" in value:
            source, digest = value.split(";md5;", 1)
            source = source.strip()
            suffix = ";md5;" + digest.strip().lower()
        lower = source.lower()
        if lower.startswith(("http://", "https://", "assets://")):
            return source + suffix
        if lower.startswith("file://"):
            file_value = source[7:]
            if file_value.startswith(("./", "../")):
                path = os.path.join(os.path.dirname(manifest_path), file_value)
                return self._file_url(path) + suffix
            return source + suffix
        if os.path.isabs(source):
            return self._file_url(source) + suffix
        path = os.path.join(os.path.dirname(manifest_path), source)
        return self._file_url(path) + suffix

    def _site_reference_path(self, reference, with_md5=False):
        value = str(reference or "").strip()
        if with_md5:
            value = value.split(";md5;", 1)[0].strip()
        return self._reference_path(value)

    def _file_md5(self, path):
        digest = hashlib.md5()
        with open(path, "rb") as fp:
            while True:
                chunk = fp.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _dex_u32(self, data, offset):
        if offset < 0 or offset + 4 > len(data):
            raise ValueError("DEX 索引越界")
        return int.from_bytes(data[offset : offset + 4], "little")

    def _dex_uleb128(self, data, offset):
        value = 0
        for shift in range(0, 35, 7):
            if offset >= len(data):
                raise ValueError("DEX ULEB128 越界")
            byte = data[offset]
            offset += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value, offset
        raise ValueError("DEX ULEB128 格式无效")

    def _dex_defined_spider_classes(self, data):
        if len(data) < 0x70 or not data.startswith(b"dex\n"):
            raise ValueError("DEX 文件头无效")
        if self._dex_u32(data, 0x28) != 0x12345678:
            raise ValueError("DEX 字节序不受支持")
        string_ids_size = self._dex_u32(data, 0x38)
        string_ids_off = self._dex_u32(data, 0x3C)
        type_ids_size = self._dex_u32(data, 0x40)
        type_ids_off = self._dex_u32(data, 0x44)
        class_defs_size = self._dex_u32(data, 0x60)
        class_defs_off = self._dex_u32(data, 0x64)
        if string_ids_off + string_ids_size * 4 > len(data):
            raise ValueError("DEX string_ids 越界")
        if type_ids_off + type_ids_size * 4 > len(data):
            raise ValueError("DEX type_ids 越界")
        if class_defs_off + class_defs_size * 32 > len(data):
            raise ValueError("DEX class_defs 越界")

        result = set()
        prefix = b"Lcom/github/catvod/spider/"
        for index in range(class_defs_size):
            class_idx = self._dex_u32(data, class_defs_off + index * 32)
            if class_idx >= type_ids_size:
                raise ValueError("DEX class_idx 越界")
            descriptor_idx = self._dex_u32(
                data, type_ids_off + class_idx * 4
            )
            if descriptor_idx >= string_ids_size:
                raise ValueError("DEX descriptor_idx 越界")
            string_offset = self._dex_u32(
                data, string_ids_off + descriptor_idx * 4
            )
            _, value_offset = self._dex_uleb128(data, string_offset)
            end = data.find(b"\0", value_offset)
            if end < 0:
                raise ValueError("DEX 类描述符未终止")
            descriptor = data[value_offset:end]
            if descriptor.startswith(prefix) and descriptor.endswith(b";"):
                class_name = descriptor[len(prefix) : -1].decode(
                    "utf-8", errors="ignore"
                )
                if not class_name:
                    continue
                result.add(class_name.replace("/", "."))
        return result

    def _inspect_local_jar(self, path):
        real_path = os.path.realpath(os.path.abspath(path))
        stat = os.stat(real_path)
        cache_key = (
            real_path,
            int(stat.st_size),
            int(
                getattr(
                    stat,
                    "st_mtime_ns",
                    int(stat.st_mtime * 1000000000),
                )
            ),
        )
        cached = self._jar_inspection_cache.get(cache_key)
        if isinstance(cached, dict):
            return cached
        if not zipfile.is_zipfile(real_path):
            raise ValueError("JAR 不是有效 ZIP: {}".format(real_path))
        with zipfile.ZipFile(real_path, "r") as archive:
            dex_entries = sorted(
                name
                for name in archive.namelist()
                if re.fullmatch(r"classes(?:[2-9][0-9]*)?\.dex", name)
            )
            if "classes.dex" not in dex_entries:
                raise ValueError("JAR 缺少 classes.dex: {}".format(real_path))
            remaining = self.MAX_JAR_DEX_SCAN_SIZE
            class_names = set()
            direct_classes = set()
            class_scan_complete = True
            for entry in dex_entries:
                info = archive.getinfo(entry)
                if remaining <= 0:
                    class_scan_complete = False
                    break
                read_limit = min(int(info.file_size), remaining)
                with archive.open(entry, "r") as dex_stream:
                    dex_data = dex_stream.read(read_limit + 1)
                if not dex_data.startswith(b"dex\n"):
                    raise ValueError(
                        "JAR 的 {} 格式无效: {}".format(entry, real_path)
                    )
                scanned = dex_data[:read_limit]
                remaining -= len(scanned)
                entry_complete = (
                    int(info.file_size) <= read_limit
                    and len(dex_data) <= read_limit
                )
                if not entry_complete:
                    class_scan_complete = False
                    continue
                for class_name in self._dex_defined_spider_classes(scanned):
                    class_names.add(class_name)
                    if "." not in class_name and "$" not in class_name:
                        direct_classes.add(class_name)
        result = {
            "md5": self._file_md5(real_path),
            "classes": class_names,
            "direct_classes": direct_classes,
            "dex_entries": dex_entries,
            "class_scan_complete": class_scan_complete,
        }
        self._jar_inspection_cache[cache_key] = result
        return result

    def _validate_site_jar(self, jar_reference, api=""):
        source, separator, expected_md5 = str(jar_reference).partition(";md5;")
        source = source.strip()
        expected_md5 = expected_md5.strip().lower() if separator else ""
        if expected_md5 and not re.fullmatch(r"[0-9a-f]{32}", expected_md5):
            raise ValueError("JAR md5 格式无效")
        lower = source.lower()
        if lower.startswith(("http://", "https://", "assets://")):
            return "远程或内置 JAR，等待 App 运行时确认"
        path = self._site_reference_path(source)
        if not path or not os.path.isfile(path) or not os.access(path, os.R_OK):
            raise ValueError("JAR 不存在或不可读: {}".format(source))
        inspection = self._inspect_local_jar(path)
        if expected_md5 and inspection["md5"] != expected_md5:
            raise ValueError("JAR md5 校验失败: {}".format(path))
        class_name = api[len("csp_") :] if api.startswith("csp_") else ""
        confirmed = bool(class_name) and class_name in inspection["classes"]
        if confirmed:
            return "已确认 JAR 类 com.github.catvod.spider.{}".format(class_name)
        if not class_name:
            return "JAR 结构有效"
        if inspection["class_scan_complete"]:
            raise ValueError(
                "JAR 未包含类 com.github.catvod.spider.{}: {}".format(
                    class_name, path
                )
            )
        return "JAR 结构有效，类名未静态确认，等待 App 运行时验证"

    def _auto_xbpq_site(self, rule_path, jar_path):
        valid, detail = self._validate_source("XBPQ", rule_path)
        if not valid:
            raise ValueError(detail)
        rule = self._load_json_compatible(rule_path)
        name = ""
        for field in ("站名", "name", "名称", "title"):
            value = rule.get(field) if isinstance(rule, dict) else ""
            if str(value or "").strip():
                name = str(value).strip()
                break
        if not name:
            name = os.path.splitext(os.path.basename(rule_path))[0]
        jar_reference = self._file_url(jar_path)
        jar_detail = self._validate_site_jar(jar_reference, "csp_XBPQ")
        jar_reference += ";md5;" + self._inspect_local_jar(jar_path)["md5"]
        site = {
            "name": name,
            "type": 3,
            "api": "csp_XBPQ",
            "ext": self._file_url(rule_path),
            "jar": jar_reference,
            "searchable": self.DEFAULT_SEARCHABLE,
            "quickSearch": self.DEFAULT_QUICK_SEARCH,
        }
        return site, [jar_path], jar_detail

    def _auto_csp_site(self, config_path, jar_path):
        config = self._load_json_compatible(config_path)
        if not isinstance(config, dict) or not config:
            raise ValueError("CSP 配置必须是非空 JSON 对象")

        config_stem = os.path.splitext(os.path.basename(config_path))[0]
        inspection = self._inspect_local_jar(jar_path)
        matching_classes = sorted(
            class_name
            for class_name in inspection["direct_classes"]
            if class_name.casefold() == config_stem.casefold()
        )
        if len(matching_classes) != 1:
            if not matching_classes:
                reason = "JAR 中未找到与 {} 匹配的顶层类".format(
                    config_stem
                )
            else:
                reason = "JAR 中匹配到多个顶层类: {}".format(
                    ", ".join(matching_classes)
                )
            raise ValueError(reason + "，请使用 site.json 显式配置 api")

        class_name = matching_classes[0]
        api = "csp_" + class_name
        jar_reference = (
            self._file_url(jar_path) + ";md5;" + inspection["md5"]
        )
        folder_name = os.path.basename(os.path.dirname(config_path)).strip()
        if not folder_name or folder_name.casefold() == "csp":
            folder_name = config_stem
        site = {
            "name": folder_name,
            "type": 3,
            "api": api,
            "ext": self._file_url(config_path),
            "jar": jar_reference,
            "searchable": self.DEFAULT_SEARCHABLE,
            "quickSearch": self.DEFAULT_QUICK_SEARCH,
        }
        if config.get("filters"):
            site["filterable"] = 1
        detail = "已根据 JSON 文件名确认 JAR 类 com.github.catvod.spider.{}".format(
            class_name
        )
        return site, [jar_path], detail

    def _parse_site_manifest(self, path, source_type):
        data = self._load_json_compatible(path)
        if not isinstance(data, dict):
            raise ValueError("站点清单顶层必须是 JSON 对象")
        if isinstance(data.get("site"), dict) and not data.get("api"):
            data = data["site"]
        site = copy.deepcopy(data)
        source_type = str(source_type or "").upper()
        api = str(site.get("api", "")).strip()
        dependencies = []
        validation_details = []
        if source_type == "JS":
            if not api:
                raise ValueError("JS 清单缺少 api")
            api_reference = self._resolve_site_reference(path, api)
            if ".js" not in api_reference.lower():
                raise ValueError("JS 清单 api 必须指向 .js 文件或URL")
            api_path = self._site_reference_path(api_reference)
            if api_path:
                if not os.path.isfile(api_path) or not os.access(api_path, os.R_OK):
                    raise ValueError("JS api 不存在或不可读: {}".format(api_reference))
                valid, detail = self._validate_source("JS", api_path)
                if not valid:
                    raise ValueError(detail)
                dependencies.append(api_path)
            site["api"] = api_reference
            validation_details.append("JS 清单有效")
        else:
            if not re.fullmatch(r"csp_[A-Za-z_$][A-Za-z0-9_.$]*", api):
                raise ValueError("{} api 必须是 csp_ 开头的有效类名".format(source_type))
            if source_type == "XBPQ" and api != "csp_XBPQ":
                raise ValueError("XBPQ 清单 api 必须是 csp_XBPQ")
            site["api"] = api
        jar_value = str(site.get("jar", "")).strip()
        if source_type in ("CSP", "XBPQ") and not jar_value:
            raise ValueError("{} 清单缺少 jar".format(source_type))
        if jar_value:
            jar_reference = self._resolve_site_reference(
                path, jar_value, with_md5=True
            )
            jar_detail = self._validate_site_jar(jar_reference, api)
            jar_path = self._site_reference_path(jar_reference, with_md5=True)
            if jar_path and ";md5;" not in jar_reference:
                jar_reference += ";md5;" + self._inspect_local_jar(jar_path)["md5"]
            if jar_path:
                dependencies.append(jar_path)
            site["jar"] = jar_reference
            validation_details.append(jar_detail)
        else:
            site.pop("jar", None)
        ext = site.get("ext", "")
        if isinstance(ext, str) and ext.strip():
            ext_reference = self._resolve_site_reference(path, ext)
            ext_path = self._site_reference_path(ext_reference)
            if ext_path:
                if not os.path.isfile(ext_path) or not os.access(ext_path, os.R_OK):
                    raise ValueError("{} ext 不存在或不可读: {}".format(source_type, ext_reference))
                if os.path.getsize(ext_path) <= 0:
                    raise ValueError("{} ext 是空文件: {}".format(source_type, ext_path))
                if ext_path.lower().endswith(".json"):
                    self._load_json_compatible(ext_path)
                if source_type == "XBPQ":
                    valid, detail = self._validate_source("XBPQ", ext_path)
                    if not valid:
                        raise ValueError(detail)
                dependencies.append(ext_path)
            site["ext"] = ext_reference
        elif ext not in (None, "") and not isinstance(ext, (dict, list)):
            raise ValueError("{} ext 必须是路径、URL或JSON对象".format(source_type))
        site["type"] = 3
        site.setdefault("searchable", self.DEFAULT_SEARCHABLE)
        site.setdefault("quickSearch", self.DEFAULT_QUICK_SEARCH)
        name = str(site.get("name", "")).strip()
        if not name:
            stem = os.path.basename(path)
            if stem.lower() == "site.json":
                stem = os.path.basename(os.path.dirname(path))
            elif stem.lower().endswith(".site.json"):
                stem = stem[: -len(".site.json")]
            fallback = api[len("csp_") :] if api.startswith("csp_") else "JS站点"
            site["name"] = stem or fallback
        return (
            site,
            list(dict.fromkeys(dependencies)),
            "；".join(item for item in validation_details if item),
        )

    def _validate_source(self, source_type, path):
        try:
            lower_name = os.path.basename(path).lower()
            if (
                source_type in ("JS", "XBPQ", "CSP")
                and self._is_site_manifest_name(lower_name)
            ):
                _, _, detail = self._parse_site_manifest(path, source_type)
                return True, detail
            if source_type == "XBPQ":
                data = self._load_json_compatible(path)
                if not isinstance(data, dict) or not data:
                    return False, "XBPQ 缺少有效的 JSON 对象: {}".format(path)
                keys = "|".join(str(key).lower() for key in data.keys())
                signatures = (
                    "url",
                    "主页",
                    "分类",
                    "搜索",
                    "二级",
                    "播放",
                    "列表",
                    "数组",
                    "标题",
                )
                if not any(signature in keys for signature in signatures):
                    return False, "XBPQ 未发现常用规则字段: {}".format(path)
            elif source_type == "PY":
                text = self._read_text(path, 256 * 1024)
                if not re.search(r"\bclass\s+Spider\s*(?:\(|:)", text):
                    return False, "PY 文件未发现 Spider 类，已按依赖库跳过: {}".format(path)
            elif source_type == "JS":
                text = self._read_text(path, 256 * 1024)
                if not self._has_quickjs_export(text):
                    return False, "JS 文件未发现 QuickJS 导出入口，已按不兼容规则或扩展跳过: {}".format(path)
            elif source_type == "HTML":
                text = self._read_text(path, 128 * 1024).lower()
                if not any(tag in text for tag in ("<!doctype html", "<html", "<body")):
                    return False, "HTML 文件未发现页面结构: {}".format(path)
        except Exception as exc:
            return False, "{} 文件检查失败: {} ({})".format(source_type, path, exc)
        return True, ""

    def _has_quickjs_export(self, text):
        return bool(
            re.search(
                r"\bexport\s+(?:default|(?:async\s+)?function|class|const|let|var|\{)",
                str(text or ""),
            )
            or "__jsEvalReturn" in str(text or "")
            or "__JS_SPIDER__" in str(text or "")
        )

    def _read_text(self, path, limit):
        with open(path, "rb") as fp:
            data = fp.read(limit)
        return data.decode("utf-8", errors="ignore")

    # --------------------------------------------------------------------------
    # 18+ 成人内容识别（完全本地处理，不上传服务器）
    # --------------------------------------------------------------------------
    def _adult_text_matches(self, value):
        # 放宽版（计分制）：只允许明确信号单独判定，Emoji/符号/简写均需叠加，
        # 避免影视、美食、天气等正常站点因表情或禁令符号被误判。
        text = str(value or "")
        lower = text.casefold()
        # —— 强信号：任一命中即判定 ——
        # 用户指定的强信号（🔞🈲㊙🍆🍑🍌🥒 与 "色/瑟"，裸命中即判）
        if any(token in lower for token in self.ADULT_STRONG_TEXT):
            return True
        # av / 18 整词强信号（避免误伤 java/javascript/navigation 与年份数字）
        if self.ADULT_STRONG_WORD_PATTERN.search(text):
            return True
        if "🔞" in text:
            return True
        if self.ADULT_LATIN_PATTERN.search(text):
            return True
        if self.ADULT_SHORT_TEXT.search(text):
            return True
        if any(keyword.casefold() in lower for keyword in self.ADULT_KEYWORDS):
            return True
        # —— 弱信号：累计 ≥2 才判定 ——
        weak = 0
        if any(symbol in text for symbol in self.ADULT_WEAK_SYMBOLS):
            weak += 1
        if any(symbol in text for symbol in self.ADULT_EMOJI):
            weak += 1
        if any(symbol in text for symbol in self.ADULT_EMOJI_WEAK):
            weak += 1
        if re.search(r"(?:^|[^0-9a-z])(?:adult|nsfw|xxx)(?:$|[^0-9a-z])", lower):
            weak += 1
        if re.search(r"(?:^|[^0-9a-z])18(?:\+|xxx|av|j|禁)(?:$|[^0-9a-z])", lower):
            weak += 1
        if re.search(r"(?:^|[^0-9a-z])av(?:$|[^0-9a-z])", lower):
            weak += 1
        for token in re.findall(r"[a-z0-9]+", lower):
            if token.startswith("jav") and not token.startswith(
                ("java", "javascript")
            ):
                weak += 1
                break
        return weak >= 2

    def _adult_content_matches(self, value):
        # 内容场景多义性更高：明确信号需叠加更多，弱信号需累计 ≥3 才判定。
        text = str(value or "")
        lower = text.casefold()
        if "🔞" in text:
            return True
        if self.ADULT_LATIN_PATTERN.search(text):
            return True
        if re.search(r"(?:^|[^0-9a-z])18(?:\+|xxx|av|j|禁)(?:$|[^0-9a-z])", lower):
            return True
        keyword_hits = {
            keyword.casefold()
            for keyword in self.ADULT_KEYWORDS
            if keyword.casefold() in lower
        }
        if len(keyword_hits) >= 2:
            return True
        # 弱信号累计
        weak = 0
        if any(symbol in text for symbol in self.ADULT_WEAK_SYMBOLS):
            weak += 1
        if any(symbol in text for symbol in self.ADULT_EMOJI):
            weak += 1
        if any(symbol in text for symbol in self.ADULT_EMOJI_WEAK):
            weak += 1
        if self.ADULT_SHORT_TEXT.search(text):
            weak += 1
        if re.search(
            r"(?:^|[^0-9a-z])(?:adult|nsfw|xxx|av)(?:$|[^0-9a-z])", lower
        ):
            weak += 1
        if keyword_hits:
            weak += 1
        return weak >= 3

    def _adult_exact_name_matches(self, value):
        name = os.path.basename(str(value or "").strip())
        stem = os.path.splitext(name)[0].strip().casefold()
        return stem in self.ADULT_EXACT_NAMES

    # --------------------------------------------------------------------------
    # 自定义关键词屏蔽（用户黑名单/白名单，完全本地）
    # --------------------------------------------------------------------------
    def _keyword_text_values(self, source):
        values = [
            source.get("base_name", ""),
            source.get("name", ""),
            os.path.basename(str(source.get("path", ""))),
            source.get("relative_in_root", ""),
        ]
        return [str(value) for value in values if str(value or "").strip()]

    def _keyword_allow_match(self, source):
        """站点名命中任一白名单关键词 → 放行（覆盖黑名单与成人规则）。"""
        if not self.custom_allow_keywords:
            return False
        haystacks = [value.casefold() for value in self._keyword_text_values(source)]
        for keyword in self.custom_allow_keywords:
            needle = str(keyword or "").casefold()
            if needle and any(needle in h for h in haystacks):
                return True
        return False

    def _keyword_block_match(self, source):
        """站点名命中任一黑名单关键词 → 屏蔽。"""
        if not self.custom_block_keywords:
            return False
        haystacks = [value.casefold() for value in self._keyword_text_values(source)]
        for keyword in self.custom_block_keywords:
            needle = str(keyword or "").casefold()
            if needle and any(needle in h for h in haystacks):
                return True
        return False

    def _is_adult_source(self, source):
        site = source.get("csp_site", {})
        if isinstance(site, dict):
            for key in ("adult", "isAdult", "is_adult", "nsfw", "restricted18"):
                if key in site:
                    return self._as_bool(site.get(key), False)
            site_text = json.dumps(
                site, ensure_ascii=False, sort_keys=True, default=str
            )
            if self._adult_text_matches(site_text):
                return True

        values = [
            source.get("base_name", ""),
            os.path.basename(str(source.get("path", ""))),
        ]
        if not source.get("csp_site"):
            values.append(source.get("relative_in_root", ""))
        if any(self._adult_exact_name_matches(value) for value in values):
            return True
        if any(self._adult_text_matches(value) for value in values):
            return True

        paths = list(source.get("dependencies", []))
        if not source.get("csp_site"):
            paths.append(source.get("path", ""))
        seen = set()
        for path in paths:
            real_path = os.path.realpath(str(path or ""))
            if not real_path or real_path in seen or not os.path.isfile(real_path):
                continue
            seen.add(real_path)
            if not real_path.lower().endswith(
                (".json", ".jsonc", ".py", ".js", ".html", ".htm", ".txt")
            ):
                continue
            try:
                text = self._read_text(real_path, 256 * 1024)
            except Exception:
                continue
            if "@tvbox-safe" in text.casefold():
                continue
            if "@tvbox-adult" in text.casefold() or self._adult_content_matches(text):
                return True
        return False

    def _apply_display_names(self, sources):
        counts = {}
        folder_counts = {}
        for source in sources:
            identity = (source["type"], source["base_name"].lower())
            counts[identity] = counts.get(identity, 0) + 1
            folder = os.path.dirname(source["relative_in_root"]).replace(
                os.sep, "/"
            )
            folder_identity = identity + (folder.lower(),)
            folder_counts[folder_identity] = (
                folder_counts.get(folder_identity, 0) + 1
            )

        for source in sources:
            source_type = source["type"]
            base_name = source["base_name"]
            package_label = str(source.get("package_label", "")).strip()
            identity = (source_type, base_name.lower())
            suffix = ""
            if counts.get(identity, 0) > 1:
                folder = os.path.dirname(source["relative_in_root"]).replace(os.sep, "/")
                folder_identity = identity + (folder.lower(),)
                if folder_counts.get(folder_identity, 0) > 1:
                    original_key = str(
                        source.get("csp_site", {}).get("key", "")
                        if isinstance(source.get("csp_site"), dict)
                        else ""
                    ).strip()
                    if "#bundle-site-" in source["identity"] and original_key:
                        disambiguator = original_key
                    else:
                        relative_name = os.path.basename(source["relative_in_root"])
                        disambiguator = os.path.splitext(relative_name)[0]
                else:
                    disambiguator = folder or os.path.basename(
                        source["scan_root"]
                    )
                suffix = " · " + disambiguator
            source["name"] = (
                self.TYPE_PREFIX[source_type]
                + ("【{}】".format(package_label) if package_label else "")
                + base_name
                + suffix
                + "┃"
                + self.TYPE_GROUP[source_type]
            )

    def _build_site(self, source):
        source_type = source["type"]
        file_ref = self._file_url(source["path"])
        site = {
            "key": source["key"],
            "name": source["name"],
            "type": 3,
            "searchable": self.DEFAULT_SEARCHABLE,
            "quickSearch": self.DEFAULT_QUICK_SEARCH,
        }
        if source.get("csp_site"):
            manifest_site = copy.deepcopy(source.get("csp_site", {}))
            if not isinstance(manifest_site, dict):
                manifest_site = {}
            site.update(manifest_site)
            site["key"] = source["key"]
            site["name"] = source["name"]
            site["type"] = 3
            site.setdefault("searchable", self.DEFAULT_SEARCHABLE)
            site.setdefault("quickSearch", self.DEFAULT_QUICK_SEARCH)
        elif source_type == "PY":
            site.update({"api": file_ref})
        elif source_type == "JS":
            site.update(
                {
                    "api": file_ref,
                    "ext": "",
                }
            )
        elif source_type == "XBPQ":
            site.update(
                {
                    "api": self._runtime_reference(self.xbpq_api),
                    "ext": file_ref,
                    "jar": self._xbpq_jar_reference(),
                }
            )
        elif source_type == "HTML":
            site.update(
                {
                    "api": self._runtime_reference(self.html_api),
                    "homePage": file_ref,
                }
            )
        return site

    def _xbpq_runtime_status(self):
        jar = self._xbpq_jar_reference()
        if not jar:
            return False, (
                "XBPQ 已跳过：缺少 xbpqJar，请在 auto-loader.roots.json "
                "的 runtime 中配置包含 csp_XBPQ 的 JAR"
            )
        source = jar.split(";md5;", 1)[0].strip()
        lower = source.lower()
        if lower.startswith(("http://", "https://", "assets://")):
            return True, ""
        if lower.startswith("file://"):
            path = source[7:]
            if not os.path.isabs(path):
                path = os.path.join(self.STORAGE_ROOT, path)
        else:
            path = source
        if os.path.isfile(os.path.abspath(os.path.expanduser(path))):
            return True, ""
        return False, "XBPQ 已跳过：配置的 xbpqJar 不存在 ({})".format(source)

    def _xbpq_jar_reference(self):
        value = str(self.xbpq_jar or "").strip()
        if not value:
            return ""
        parts = value.split(";md5;", 1)
        reference = self._runtime_reference(parts[0].strip())
        if len(parts) == 1:
            return reference
        return reference + ";md5;" + parts[1].strip()

    def _file_url(self, path):
        absolute = os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))
        storage_root = os.path.realpath(os.path.abspath(self.STORAGE_ROOT))
        try:
            relative = os.path.relpath(absolute, storage_root).replace(os.sep, "/")
        except Exception:
            relative = ""
        if relative and relative != ".." and not relative.startswith("../"):
            return "file:///sdcard/" + relative.lstrip("/")
        return "file://" + absolute

    def _runtime_reference(self, reference):
        value = str(reference or "").strip()
        if not value:
            return ""
        lower = value.lower()
        if lower.startswith(("http://", "https://", "file://", "assets://")):
            return value
        if value.startswith("csp_"):
            return value
        if os.path.isabs(value):
            return self._file_url(value)
        return self._file_url(os.path.join(self.local_base_dir, value.lstrip("./")))

    def _generate_config(self):
        base_duplicates = self.status["duplicates"]
        last_error = None
        for _ in range(3):
            registry, token = self._load_registry_snapshot()
            registry, manual_count, generated_count, duplicate_count, diff = self._merge_registry(
                registry
            )
            try:
                self._atomic_write_json(registry, expected_token=token)
                self.status["manual_sites"] = manual_count
                self.status["generated_sites"] = generated_count
                self.status["duplicates"] = base_duplicates + duplicate_count
                self.status["added_sites"] = diff["added"]
                self.status["updated_sites"] = diff["updated"]
                self.status["removed_sites"] = diff["removed"]
                self.status["unchanged_sites"] = diff["unchanged"]
                return
            except RegistryChangedError as exc:
                last_error = exc
        raise RegistryChangedError(
            "注册表在扫描期间持续被修改，已停止写入: {}".format(last_error)
        )

    def _merge_registry(self, registry):
        items = registry.get("items", [])
        if not isinstance(items, list):
            raise ValueError("站点注入注册表的 items 必须是数组")

        old_generated_items = [
            item for item in items if self._is_generated_registry_item(item)
        ]
        manual_items = []
        for item in items:
            if not isinstance(item, dict):
                manual_items.append(item)
                continue
            if self._is_generated_registry_item(item):
                continue
            manual_items.append(item)

        manual_fingerprints = {
            self._site_fingerprint(self._registry_item_site(item))
            for item in manual_items
            if isinstance(item, dict)
        }
        generated_items = []
        duplicate_count = 0
        for source in self.cache["sources"]:
            site = source["site"]
            if self._site_fingerprint(site) in manual_fingerprints:
                duplicate_count += 1
                continue
            generated_items.append(
                {
                    "id": source["key"],
                    "enabled": True,
                    "kind": self._registry_kind(source),
                    "site": site,
                }
            )

        generated_keys = {
            self._registry_item_key(item) for item in generated_items
        }
        preserved_count = 0
        for item in old_generated_items:
            key = self._registry_item_key(item)
            if key in generated_keys or not self._should_preserve_generated_item(item):
                continue
            generated_items.append(item)
            generated_keys.add(key)
            preserved_count += 1
        if preserved_count:
            self._warn(
                "{} 个旧站点因对应扫描目录暂时不可用而保留".format(
                    preserved_count
                )
            )

        if self.generated_insert_index is None:
            merged_items = manual_items + generated_items
        else:
            index = max(0, min(int(self.generated_insert_index), len(manual_items)))
            merged_items = manual_items[:index] + generated_items + manual_items[index:]

        registry["enabled"] = True
        registry.setdefault("insertIndex", 0)
        registry.setdefault("homeKey", "")
        registry["items"] = merged_items
        home_key = str(registry.get("homeKey", "")).strip()
        if home_key.startswith(self.GENERATED_KEY_PREFIX) and home_key not in generated_keys:
            registry["homeKey"] = ""
        old_map = {
            self._registry_item_key(item): self._registry_content_fingerprint(item)
            for item in old_generated_items
        }
        new_map = {
            self._registry_item_key(item): self._registry_content_fingerprint(item)
            for item in generated_items
        }
        shared = set(old_map) & set(new_map)
        diff = {
            "added": len(set(new_map) - set(old_map)),
            "removed": len(set(old_map) - set(new_map)),
            "updated": sum(1 for key in shared if old_map[key] != new_map[key]),
            "unchanged": sum(1 for key in shared if old_map[key] == new_map[key]),
        }
        return registry, len(manual_items), len(generated_items), duplicate_count, diff

    def _registry_kind(self, source):
        if source.get("type") == "HTML":
            return "webHome"
        site = source.get("site", {})
        if not isinstance(site, dict):
            return "csp"
        has_home = bool(str(site.get("homePage", "")).strip())
        return "webHome" if has_home else "csp"

    def _generated_item_type(self, item):
        key = self._registry_item_key(item).lower()
        for source_type in self.TYPE_ORDER:
            if key.startswith(
                self.GENERATED_KEY_PREFIX.lower() + source_type.lower() + "_"
            ):
                return source_type
        return ""

    def _generated_item_reference(self, item, source_type):
        site = self._registry_item_site(item)
        if not isinstance(site, dict):
            return ""
        field = {
            "PY": "api",
            "JS": "api",
            "CSP": "jar",
            "XBPQ": "ext",
            "HTML": "homePage",
        }.get(source_type, "")
        return str(site.get(field, "")).strip() if field else ""

    def _should_preserve_generated_item(self, item):
        source_type = self._generated_item_type(item)
        if not source_type:
            return False
        if source_type in self.incomplete_scan_types:
            return True
        failed_same_type = any(
            item_type == source_type
            for item_type, _ in self.incomplete_scan_roots
        )
        reference = self._generated_item_reference(item, source_type)
        if not reference:
            return failed_same_type
        reference_value = reference.split(";md5;", 1)[0].strip()
        if not self._reference_path(reference_value):
            return failed_same_type
        return self._scan_failure_covers_identity(
            source_type + "|" + reference_value
        )

    def _load_registry(self):
        return self._load_registry_snapshot()[0]

    def _load_registry_snapshot(self):
        registry_path = os.path.abspath(os.path.expanduser(self.registry_path))
        output_path = os.path.abspath(os.path.expanduser(self.output_path))
        path = registry_path if os.path.isfile(registry_path) else output_path
        if os.path.isfile(path):
            try:
                with open(path, "rb") as fp:
                    raw = fp.read()
                registry = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                raise ValueError("站点注入注册表无法读取，已停止写入: {} ({})".format(path, exc))
            if not isinstance(registry, dict):
                raise ValueError("站点注入注册表顶层必须是 JSON 对象: {}".format(path))
            if "items" not in registry:
                registry = self._legacy_registry(registry)
            token = (
                hashlib.sha256(raw).hexdigest()
                if os.path.abspath(path) == output_path
                else self._registry_token(output_path)
            )
            return registry, token
        return {
            "enabled": True,
            "insertIndex": 0,
            "homeKey": "",
            "items": [],
        }, "__missing__"

    def _registry_token(self, path=None):
        path = os.path.abspath(os.path.expanduser(path or self.output_path))
        if not os.path.isfile(path):
            return "__missing__"
        with open(path, "rb") as fp:
            return hashlib.sha256(fp.read()).hexdigest()

    def _legacy_registry(self, data):
        items = []
        sites = data.get("sites", [])
        if isinstance(sites, list):
            for index, site in enumerate(sites):
                if not isinstance(site, dict):
                    continue
                key = str(site.get("key", "")).strip()
                items.append(
                    {
                        "id": key or "legacy_site_{}".format(index),
                        "enabled": True,
                        "kind": "webHome" if site.get("homePage") else "csp",
                        "site": site,
                    }
                )
        return {
            "enabled": bool(data.get("enabled", True)),
            "insertIndex": int(data.get("insertIndex", 0) or 0),
            "homeKey": str(data.get("homeKey", data.get("home", "")) or ""),
            "items": items,
        }

    def _registry_item_site(self, item):
        site = item.get("site")
        return site if isinstance(site, dict) else item

    def _registry_item_key(self, item):
        key = str(item.get("key", "")).strip()
        if key:
            return key
        site = item.get("site")
        return str(site.get("key", "")).strip() if isinstance(site, dict) else ""

    def _is_generated_registry_item(self, item):
        if not isinstance(item, dict):
            return False
        key = self._registry_item_key(item)
        item_id = str(item.get("id", "")).strip()
        return key.startswith(self.GENERATED_KEY_PREFIX) or item_id.startswith(
            self.GENERATED_KEY_PREFIX
        )

    def _clear_generated_registry(self):
        last_error = None
        for _ in range(3):
            registry, token = self._load_registry_snapshot()
            registry, removed = self._remove_generated_items(registry)
            try:
                self._atomic_write_json(registry, expected_token=token)
                return removed
            except RegistryChangedError as exc:
                last_error = exc
        raise RegistryChangedError(
            "注册表在清除期间持续被修改: {}".format(last_error)
        )

    def _remove_generated_items(self, registry):
        items = registry.get("items", [])
        if not isinstance(items, list):
            raise ValueError("站点注入注册表的 items 必须是数组")
        generated_keys = {
            self._registry_item_key(item)
            for item in items
            if self._is_generated_registry_item(item)
        }
        kept = [item for item in items if not self._is_generated_registry_item(item)]
        removed = len(items) - len(kept)
        registry["items"] = kept
        if str(registry.get("homeKey", "")).strip() in generated_keys:
            registry["homeKey"] = ""
        return registry, removed

    def _restore_registry_file(self, backup_path):
        if not os.path.isfile(backup_path):
            raise ValueError("暂无可恢复的注册表备份")
        registry = self._validate_registry_backup(backup_path)
        current_path = os.path.abspath(os.path.expanduser(self.output_path))
        expected_token = self._registry_token(current_path)
        if os.path.isfile(current_path):
            self._create_registry_backup(current_path)
        self._atomic_write_json(
            registry,
            create_backup=False,
            expected_token=expected_token,
        )
        return len(registry.get("items", []))

    def _create_registry_backup(self, source_path):
        os.makedirs(self.backup_dir, exist_ok=True)
        backup_path = self._latest_backup_path()
        temp_path = backup_path + ".tmp"
        try:
            shutil.copy2(source_path, temp_path)
            self._validate_registry_backup(temp_path)
            os.replace(temp_path, backup_path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        self._remove_legacy_backup_files(keep=backup_path)

    def _latest_backup_path(self):
        return os.path.join(
            os.path.abspath(os.path.expanduser(self.backup_dir)),
            "registry-latest.json",
        )

    def _backup_candidates(self):
        candidates = []
        backup_dir = os.path.abspath(os.path.expanduser(self.backup_dir))
        if os.path.isdir(backup_dir):
            candidates.extend(
                os.path.join(backup_dir, name)
                for name in os.listdir(backup_dir)
                if name.startswith("registry-")
                and name.endswith(".json")
                and os.path.isfile(os.path.join(backup_dir, name))
            )
        output_path = os.path.abspath(os.path.expanduser(self.output_path))
        for suffix in (".bak", ".before-restore.bak"):
            path = output_path + suffix
            if os.path.isfile(path):
                candidates.append(path)
        return candidates

    def _normalize_backup_storage(self):
        candidates = self._backup_candidates()
        if not candidates:
            return
        latest_path = self._latest_backup_path()
        valid_candidates = []
        for path in candidates:
            try:
                self._validate_registry_backup(path)
                valid_candidates.append(path)
            except Exception as exc:
                self._warn("忽略损坏的历史备份: {} ({})".format(path, exc))
        if not valid_candidates:
            return
        newest = max(
            valid_candidates,
            key=lambda path: (os.path.getmtime(path), os.path.basename(path)),
        )
        if os.path.abspath(newest) != os.path.abspath(latest_path):
            os.makedirs(os.path.dirname(latest_path), exist_ok=True)
            temp_path = latest_path + ".tmp"
            try:
                shutil.copy2(newest, temp_path)
                self._validate_registry_backup(temp_path)
                os.replace(temp_path, latest_path)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
        self._remove_legacy_backup_files(keep=latest_path)

    def _validate_registry_backup(self, path):
        registry = self._read_config_file(path, "注册表备份")
        if "items" not in registry and isinstance(registry.get("sites"), list):
            registry = self._legacy_registry(registry)
        if not isinstance(registry.get("items"), list):
            raise ValueError("注册表备份的 items 必须是数组: {}".format(path))
        return registry

    def _remove_legacy_backup_files(self, keep=None):
        keep = os.path.abspath(keep) if keep else ""
        for path in self._backup_candidates():
            if os.path.abspath(path) == keep:
                continue
            try:
                os.remove(path)
            except Exception:
                pass

    def _delete_backup_files(self):
        removed = 0
        for path in self._backup_candidates():
            try:
                os.remove(path)
                removed += 1
            except FileNotFoundError:
                pass
        return removed

    def _reset_all_data(self):
        """一键清除全部数据：屏蔽名单、放行名单、关键词、测试结果、
        扫描快照/缓存、历史备份与生成的站点注入注册表。
        保留扫描根目录、扫描类型等基础配置，避免丢失源路径。"""
        self.manual_ignored_sources = set()
        self.auto_blocked_sources = set()
        self.ignored_sources = set()
        self.adult_blocked_sources = set()
        self.adult_allowed_sources = set()
        self.keyword_blocked_sources = set()
        self.keyword_allowed_sources = set()
        self.custom_block_keywords = []
        self.custom_allow_keywords = []
        self.block_adult_sites = False
        self.pending_block_adult_sites = False
        self.site_test_results = {}
        self._retest_pending = set()
        self._retest_auto_blocked = set()
        self._author_scan_surprise_shown = False
        self.auto_scan_suspended = False
        self.cache = self._empty_cache()
        self.status = self._empty_status()
        # 删除扫描快照/缓存文件
        try:
            if os.path.isfile(self.cache_path):
                os.remove(self.cache_path)
        except Exception:
            pass
        # 删除历史备份
        self._delete_backup_files()
        # 清空生成的站点注入注册表
        try:
            empty_registry = {
                "enabled": True,
                "insertIndex": 0,
                "homeKey": "",
                "items": [],
            }
            output_path = os.path.abspath(
                os.path.expanduser(self.output_path)
            )
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.isdir(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            temp_path = output_path + ".tmp"
            content = (
                json.dumps(empty_registry, ensure_ascii=False, indent=2) + "\n"
            )
            with open(temp_path, "w", encoding="utf-8") as fp:
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temp_path, output_path)
        except Exception as exc:
            self._log("WARN", "清空站点注入注册表失败: {}".format(exc))
        self._sync_ignored_sources()
        self._save_settings()
        return "已清除全部数据：屏蔽/放行/关键词/测试结果/快照/备份与站点列表已清空，请重新扫描"

    def _list_backup_files(self):
        path = self._latest_backup_path()
        if not os.path.isfile(path):
            return []
        try:
            self._validate_registry_backup(path)
            return [path]
        except Exception:
            return []

    def _read_config_file(self, path, label):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as exc:
            raise ValueError("{}无法读取，已停止写入: {} ({})".format(label, path, exc))
        if not isinstance(data, dict):
            raise ValueError("{}顶层必须是 JSON 对象: {}".format(label, path))
        return data

    def _site_fingerprint(self, site):
        if not isinstance(site, dict):
            return ""
        data = {
            "type": site.get("type", 3),
            "api": site.get("api", ""),
            "ext": site.get("ext", ""),
            "jar": site.get("jar", ""),
            "homePage": site.get("homePage", site.get("home_page", "")),
        }
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _registry_content_fingerprint(self, item):
        if not isinstance(item, dict):
            return ""
        return json.dumps(
            item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    def _atomic_write_json(self, config, create_backup=True, expected_token=None):
        output_path = os.path.abspath(os.path.expanduser(self.output_path))
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        content = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
        if os.path.isfile(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as fp:
                    if fp.read() == content:
                        self.status["write_state"] = "配置内容未变化"
                        self.status["written"] = True
                        self.status["registry_changed"] = False
                        return
            except Exception:
                pass

        temp_path = output_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as fp:
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
            with open(temp_path, "r", encoding="utf-8") as fp:
                check = json.load(fp)
            if not isinstance(check, dict) or not isinstance(check.get("items", []), list):
                raise ValueError("临时注册表校验失败")
            if expected_token is not None and self._registry_token(output_path) != expected_token:
                raise RegistryChangedError("注册表已被其他操作修改")
            if os.path.isfile(output_path) and self.backup_before_write and create_backup:
                self._create_registry_backup(output_path)
            os.replace(temp_path, output_path)
            self.status["write_state"] = "已写入 WebHTV 站点注入注册表"
            self.status["written"] = True
            self.status["registry_changed"] = True
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            raise

    def _digest(self, value, length):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]

    def _diagnostic_log_path(self):
        return os.path.abspath(os.path.expanduser(self.log_path))

    def _log(self, level, message):
        text = " ".join(str(message or "").split()).strip()
        if not text:
            return
        try:
            path = self._diagnostic_log_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            limit = max(16 * 1024, int(self.max_log_size))
            line = "{} [{}] {}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"),
                str(level or "INFO").upper()[:10],
                text[:4000],
            ).encode("utf-8", errors="replace")
            if len(line) > limit // 2:
                line = line[: limit // 2].decode("utf-8", errors="ignore").encode("utf-8")
                line = line.rstrip(b"\n") + b"\n"

            current_size = os.path.getsize(path) if os.path.isfile(path) else 0
            if current_size + len(line) > limit:
                header = b"... earlier log entries truncated ...\n"
                keep = max(0, limit - len(header) - len(line))
                tail = b""
                if keep and os.path.isfile(path):
                    with open(path, "rb") as fp:
                        fp.seek(max(0, current_size - keep))
                        tail = fp.read(keep)
                    newline = tail.find(b"\n")
                    if newline >= 0:
                        tail = tail[newline + 1 :]
                    else:
                        tail = b""
                temp_path = path + ".tmp"
                try:
                    with open(temp_path, "wb") as fp:
                        fp.write(header)
                        fp.write(tail)
                    os.replace(temp_path, path)
                finally:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except Exception:
                        pass
            with open(path, "ab") as fp:
                fp.write(line)
        except Exception:
            pass

    def _warn(self, text):
        if text and text not in self.status["warnings"]:
            self.status["warnings"].append(text)
            self._log("WARN", text)

    # --------------------------------------------------------------------------
    # TVBox 标准接口
    # --------------------------------------------------------------------------
    def homeContent(self, filter):
        self._ensure_initialized()
        classes = [{"type_id": "all", "type_name": "全部 ({})".format(len(self.cache["sources"]))}]
        for source_type in self.TYPE_ORDER:
            count = self.cache["type_counts"].get(source_type, 0)
            if count:
                classes.append(
                    {
                        "type_id": "type:" + source_type,
                        "type_name": "{} ({})".format(
                            self.TYPE_LABEL.get(source_type, source_type), count
                        ),
                    }
                )
        if self.cache["ignored"]:
            classes.append(
                {
                    "type_id": "ignored",
                    "type_name": "屏蔽 ({})".format(len(self.cache["ignored"])),
                }
            )
        classes.append(
            {
                "type_id": self.SCAN_SETTINGS_TID,
                "type_name": "设置" + (" *" if self.config_dirty else ""),
            }
        )
        backup_count = len(self._list_backup_files())
        if backup_count:
            classes.append(
                {
                    "type_id": self.BACKUPS_TID,
                    "type_name": "历史备份 ({})".format(backup_count),
                }
            )
        classes.append(
            {
                "type_id": self.EXPORT_LOCAL_JSON_ID,
                "type_name": "📤 导出本地点播JSON",
            }
        )
        # 恶意代码扫描入口
        classes.append(
            {
                "type_id": self.MALWARE_SCAN_ID,
                "type_name": "🔍 扫描恶意代码",
            }
        )
        return {"class": classes, "list": self._home_items()}

    def homeVideoContent(self):
        self._ensure_initialized()
        return {"list": self._home_items()}

    def _home_items(self):
        ready = self.status["written"]
        status_name = "✅ 站点已合并" if ready else "ℹ 手动扫描模式"
        items = [
            {
                "vod_id": self.STATUS_ID,
                "vod_name": status_name,
                "vod_pic": "",
                "vod_remarks": "{} 个源 · {}".format(len(self.cache["sources"]), self.status["write_state"]),
            },
        ]
        items.extend(
            [
            {
                "vod_id": self.RESCAN_ID,
                "vod_name": "⚡ 一键扫描并加载",
                "vod_pic": "",
                "vod_remarks": "扫描、写入注册表并重载当前点播配置",
                "action": self.ACTION_RESCAN,
            },
            {
                "vod_id": self.EXPORT_LOCAL_JSON_ID,
                "vod_name": "📤 导出本地点播JSON",
                "vod_pic": "",
                "vod_remarks": "导出 PY/JS 文件为 JSON 点播配置",
                "action": self.ACTION_EXPORT_LOCAL_JSON,
            },
            {
                "vod_id": self.MALWARE_SCAN_ID,
                "vod_name": "🔍 扫描恶意代码",
                "vod_pic": "",
                "vod_remarks": "扫描 tvbox 目录下的 PY/JS/HTML 文件",
                "action": self.ACTION_MALWARE_SCAN,
            },
            {
                "vod_id": self.TEST_SITES_ID,
                "vod_name": "✓ 测试站点连通性",
                "vod_pic": "",
                "vod_remarks": "仅点击时检测；受限只标记，疑似失效才写入忽略",
                "action": self.ACTION_TEST_SITES,
            },
            {
                "vod_id": self.RETEST_SITES_ID,
                "vod_name": "↻ 重新检测全部站点",
                "vod_pic": "",
                "vod_remarks": "清除检测缓存并分批复检",
                "action": self.ACTION_RETEST_SITES,
            },
            {
                "vod_id": self.CLEAR_SITES_ID,
                "vod_name": "🗑 清除自动站点",
                "vod_pic": "",
                "vod_remarks": "保留手工站点和扫描设置",
                "action": self.ACTION_CLEAR_SITES,
            },
            ]
        )
        return items

    def categoryContent(self, tid, pg, filter, ext):
        self._ensure_initialized()
        page = self._page_number(pg)
        if tid == "all":
            items = list(self.cache["sources"])
        elif str(tid).startswith("type:"):
            source_type = str(tid).split(":", 1)[1].upper()
            items = [item for item in self.cache["sources"] if item["type"] == source_type]
        elif tid == "ignored":
            items = list(self.cache["ignored"])
        elif tid == self.SCAN_SETTINGS_TID:
            return self._paged_result(self._scan_setting_items(), page)
        elif tid == self.BACKUPS_TID:
            return self._paged_result(self._backup_items(), page)
        elif tid == self.EXPORT_LOCAL_JSON_ID:
            return self._paged_result(self._export_json_items(), page)
        elif tid == self.MALWARE_SCAN_ID:
            return self._paged_result(self._malware_scan_items(), page)
        else:
            items = []
        return self._paged_result(items, page)

    def _export_json_items(self):
        """生成导出JSON功能列表"""
        sources = self._collect_py_js_sources()
        if not sources:
            return [{
                "id": "export_empty",
                "name": "⚠ 未发现 PY/JS 站点文件",
                "type": "INFO",
                "relative_in_root": "请先扫描或确认文件存在",
                "export": False,
            }]
        
        items = []
        # 按类型分组统计
        py_count = len([s for s in sources if s["type"] == "PY"])
        js_count = len([s for s in sources if s["type"] == "JS"])
        
        items.append({
            "id": "export_header",
            "name": "📊 将导出 {} 个 PY + {} 个 JS 站点".format(py_count, js_count),
            "type": "INFO",
            "relative_in_root": "点击下方按钮导出",
            "export": False,
        })
        
        # 导出操作按钮
        items.append({
            "id": "export_do_export",
            "name": "📤 导出本地点播 JSON",
            "type": "EXPORT",
            "relative_in_root": "生成 {}.json".format(
                os.path.join(self.STORAGE_ROOT, "tvbox", "本地点播")
            ),
            "export": True,
            "action": self.ACTION_EXPORT_LOCAL_JSON,
        })
        
        # 列出所有将导出的站点
        for source in sources[:20]:  # 最多显示20个
            items.append({
                "id": "export_preview_{}".format(source["id"]),
                "name": "📄 {}".format(source["name"]),
                "type": "PREVIEW",
                "relative_in_root": "{} · {}".format(
                    source["type"],
                    source["relative_in_root"]
                ),
                "export": False,
            })
        
        if len(sources) > 20:
            items.append({
                "id": "export_more",
                "name": "... 还有 {} 个站点".format(len(sources) - 20),
                "type": "INFO",
                "relative_in_root": "",
                "export": False,
            })
        
        return items

    def _collect_py_js_sources(self):
        """收集所有 PY 和 JS 类型的站点源"""
        sources = []
        for source in self.cache["sources"]:
            if source["type"] in ("PY", "JS"):
                sources.append(source)
        return sources

    def _export_local_json_file(self):
        """导出本地点播JSON文件"""
        try:
            sources = self._collect_py_js_sources()

            if not sources:
                return False, "未发现 PY/JS 站点文件，请先扫描"

            # 按 设置/4K/视/播/漫/短/听/书/画/游/瑟 分类排序导出
            CATEGORY_ORDER = ["设置", "4K", "视", "播", "漫", "短", "听", "书", "画", "游", "瑟"]

            def _classify_site(name):
                # 分类依据：本地源名字最前面 [] 里的字
                n = str(name or "")
                m = re.match(r"^\s*\[([^\[\]]+)\]", n)
                if m:
                    token = m.group(1).strip()
                    token_lower = token.lower()
                    for cat in CATEGORY_ORDER:
                        if cat.lower() == token_lower:
                            return cat
                    for cat in CATEGORY_ORDER:
                        if cat in token:
                            return cat
                return "视"

            sources.sort(
                key=lambda s: (
                    CATEGORY_ORDER.index(_classify_site(s.get("name", ""))),
                    _classify_site(s.get("name", "")),
                    str(s.get("name", "")),
                )
            )

            sites = []

            # 固定置顶线路
            pinned_site = {
                "key": "手动加载本地",
                "name": "👑手动加载",
                "type": 3,
                "api": "http://39.98.94.174:8889/tvbox/手动加载.py",
                "searchable": 1,
                "changeable": 1,
                "quickSearch": 1,
                "filterable": 1,
                "playerType": 2,
            }
            sites.append(pinned_site)

            for source in sources:
                site = source.get("site", {})
                if not site.get("key"):
                    site["key"] = source["key"]
                if not site.get("name"):
                    site["name"] = source["name"]
                site.setdefault("type", 3)
                site.setdefault("searchable", 1)
                site.setdefault("changeable", 1)
                site.setdefault("quickSearch", 1)
                site.setdefault("filterable", 1)
                site.setdefault("playerType", 2)
                sites.append(site)
            
            config = {
                "spider": "",
                "wallpaper": "",
                "logo": "",
                "sites": sites,
                "parses": [
                    {
                        "name": "虾🦐米",
                        "type": 0,
                        "url": "https://jx.xmflv.com/?url=",
                        "ext": {
                            "flag": [
                                "bilibili1", "qiyi", "imgo", "爱奇艺", "奇艺",
                                "qq", "qq 预告及花絮", "腾讯",
                                "youku", "优酷",
                                "pptv", "PPTV",
                                "letv", "乐视", "leshi",
                                "mgtv", "芒果",
                                "sohu",
                                "xigua",
                                "fun", "风行"
                            ],
                            "header": {
                                "User-Agent": "okhttp/4.1.0"
                            }
                        }
                    },
                    {
                        "name": "华勇",
                        "type": 0,
                        "url": "https://huayong.net/vip4/?url="
                    },
                    {
                        "name": "剖云",
                        "type": 0,
                        "url": "https://www.pouyun.com/?url="
                    },
                    {
                        "name": "m3u8",
                        "type": 0,
                        "url": "https://jx.m3u8.tv/jiexi/?url="
                    }
                ],
                "lives": [
                    {
                        "name": "直播",
                        "type": 0,
                        "url": "https://gh-proxy.org/https://raw.githubusercontent.com/vinkerq/iptv-api/refs/heads/master/iptv.txt",
                        "ua": "okhttp/3.15"
                    }
                ]
            }
            
            output_dir = os.path.join(self.STORAGE_ROOT, "tvbox")
            output_path = os.path.join(output_dir, "本地点播.json")
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            
            self._log("INFO", "本地点播JSON导出成功: {} ({} 个站点)".format(output_path, len(sites)))
            return True, "导出本地json成功: {} ({} 个站点)".format(output_path, len(sites))
            
        except Exception as exc:
            self._log("ERROR", "导出本地点播JSON失败: {}".format(exc))
            return False, "导出失败: {}".format(exc)

    def _malware_scan_items(self):
        """生成恶意代码扫描功能列表"""
        items = []
        
        # 扫描按钮
        items.append({
            "id": "malware_scan_do",
            "name": "🔍 开始扫描恶意代码",
            "type": "SCAN",
            "relative_in_root": "扫描 tvbox 目录下的 PY/JS/HTML 文件",
            "scan": True,
            "action": self.ACTION_MALWARE_SCAN,
        })
        
        # 如果已有扫描结果，显示摘要
        if self.malware_scan_result:
            summary = self.malware_scan_result.get('summary', {})
            items.append({
                "id": "malware_summary",
                "name": "📊 扫描结果: 总文件 {}，危险 {}，安全 {}".format(
                    summary.get('total', 0),
                    summary.get('dangerous', 0),
                    summary.get('safe', 0)
                ),
                "type": "SUMMARY",
                "relative_in_root": "加密文件: {}".format(summary.get('encrypted', 0)),
                "scan": False,
            })
            
            # 显示危险文件列表
            dangerous_files = [f for f in self.malware_scan_result.get('files', []) if f.get('is_malware')]
            if dangerous_files:
                items.append({
                    "id": "malware_danger_header",
                    "name": "⚠ 发现 {} 个危险文件".format(len(dangerous_files)),
                    "type": "DANGER",
                    "relative_in_root": "点击查看详情",
                    "scan": False,
                })
                for f in dangerous_files[:10]:  # 最多显示10个
                    items.append({
                        "id": "malware_file_{}".format(f.get('file_name', 'unknown')),
                        "name": "🔴 {}".format(f.get('file_name', '')),
                        "type": "FILE",
                        "relative_in_root": "评分: {} · 等级: {} · {}".format(
                            f.get('malware_score', 0),
                            f.get('risk_level', '安全'),
                            ', '.join(f.get('key_features', []))[:50]
                        ),
                        "scan": False,
                    })
            else:
                items.append({
                    "id": "malware_safe",
                    "name": "✅ 未发现危险文件",
                    "type": "SAFE",
                    "relative_in_root": "所有扫描文件均安全",
                    "scan": False,
                })
        else:
            items.append({
                "id": "malware_ready",
                "name": "💡 点击上方按钮开始扫描",
                "type": "INFO",
                "relative_in_root": "扫描 tvbox 目录",
                "scan": False,
            })
        
        return items

    def _run_malware_scan(self):
        """执行恶意代码扫描 - 只扫描 py, js, html 三种文件"""
        try:
            # 确定扫描路径
            scan_path = self.local_base_dir
            
            # 如果local_base_dir不存在，尝试使用STORAGE_ROOT下的tvbox
            if not os.path.exists(scan_path):
                scan_path = os.path.join(self.STORAGE_ROOT, "tvbox")
            
            if not os.path.exists(scan_path):
                return False, "扫描路径不存在: {}".format(scan_path)
            
            self._log("INFO", "开始恶意代码扫描: {}".format(scan_path))
            
            # 执行扫描 - 只扫描 py, js, html
            supported_extensions = {'.py', '.js', '.html'}
            result = self.malware_detector.analyze_directory(scan_path, supported_extensions)
            self.malware_scan_result = result
            
            # 记录结果
            summary = result.get('summary', {})
            self._log("INFO", "恶意代码扫描完成: 总文件={}, 危险={}, 安全={}, 加密={}".format(
                summary.get('total', 0),
                summary.get('dangerous', 0),
                summary.get('safe', 0),
                summary.get('encrypted', 0)
            ))
            
            # 生成报告
            report_path = os.path.join(self.STORAGE_ROOT, "tvbox", "恶意代码扫描报告.txt")
            self._save_malware_report(result, report_path)
            
            return True, "扫描完成: 总文件 {}, 危险 {}, 安全 {}, 报告已保存至 {}".format(
                summary.get('total', 0),
                summary.get('dangerous', 0),
                summary.get('safe', 0),
                report_path
            )
            
        except Exception as exc:
            self._log("ERROR", "恶意代码扫描失败: {}".format(exc))
            return False, "扫描失败: {}".format(exc)

    def _save_malware_report(self, result, report_path):
        """保存恶意代码扫描报告"""
        try:
            output_dir = os.path.dirname(report_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("TVBox恶意代码扫描报告\n")
                f.write("=" * 80 + "\n")
                f.write("扫描时间: {}\n".format(time.strftime('%Y-%m-%d %H:%M:%S')))
                f.write("扫描路径: {}\n".format(result.get('scan_path', '未知')))
                summary = result.get('summary', {})
                f.write("总文件数: {}\n".format(summary.get('total', 0)))
                f.write("安全文件: {}\n".format(summary.get('safe', 0)))
                f.write("危险文件: {}\n".format(summary.get('dangerous', 0)))
                f.write("加密文件: {}\n".format(summary.get('encrypted', 0)))
                f.write("=" * 80 + "\n\n")
                
                # 危险文件详情
                dangerous = [f for f in result.get('files', []) if f.get('is_malware')]
                if dangerous:
                    f.write("【危险文件详情】\n")
                    f.write("-" * 80 + "\n")
                    for idx, file_result in enumerate(dangerous, 1):
                        f.write("\n{}. {}\n".format(idx, file_result.get('file_path', '未知')))
                        f.write("   文件名: {}\n".format(file_result.get('file_name', '未知')))
                        f.write("   风险等级: {}\n".format(file_result.get('risk_level', '未知')))
                        f.write("   恶意评分: {}\n".format(file_result.get('malware_score', 0)))
                        f.write("   加密方式: {}\n".format(file_result.get('decrypt_method', '无')))
                        if file_result.get('key_features'):
                            f.write("   关键特征: {}\n".format(', '.join(file_result['key_features'])))
                        f.write("\n   检测到的问题:\n")
                        for finding in file_result.get('findings', []):
                            f.write("     [{}] {} (匹配: {})\n".format(
                                finding.get('level', '未知'),
                                finding.get('desc', ''),
                                finding.get('count', 0)
                            ))
                        f.write("-" * 60 + "\n")
                else:
                    f.write("\n未发现危险文件\n")
                
                # 安全建议
                if dangerous:
                    f.write("\n" + "=" * 80 + "\n")
                    f.write("⚠ 安全警告\n")
                    f.write("=" * 80 + "\n")
                    f.write("发现文件存在恶意行为，建议立即删除或隔离危险文件。\n")
                    f.write("=" * 80 + "\n")
            
            self._log("INFO", "恶意代码扫描报告已保存: {}".format(report_path))
        except Exception as exc:
            self._warn("保存恶意代码扫描报告失败: {}".format(exc))

    def _scan_setting_items(self):
        items = [
            {
                "id": self.SCAN_BASE_PATH_ID,
                "name": "扫描目录",
                "type": "PATH",
                "relative_in_root": self.scan_base_path
                or "自动探测: {}".format(self.local_base_dir),
                "settings": True,
                "scan_base_path": True,
            },
            {
                "id": self.RESET_SCAN_BASE_ID,
                "name": "恢复默认目录",
                "type": "RESET_PATH",
                "relative_in_root": self.LOCAL_BASE_DIR,
                "settings": True,
                "reset_scan_base": True,
            },
            {
                "id": "setting_scan_types",
                "name": "扫描类型",
                "type": "TYPES",
                "relative_in_root": "已开启: {}".format(
                    ", ".join(
                        self.TYPE_LABEL.get(source_type, source_type)
                        for source_type in self.TYPE_ORDER
                        if self.pending_type_enabled.get(
                            source_type,
                            self.type_enabled.get(source_type, True),
                        )
                    )
                    or "无"
                ),
                "settings": True,
                "scan_types": True,
            },
            {
                "id": self.KEYWORDS_SETTING_ID,
                "name": "关键词屏蔽",
                "type": "KEYWORDS",
                "relative_in_root": "黑名单 {} · 白名单 {}".format(
                    len(self.custom_block_keywords),
                    len(self.custom_allow_keywords),
                ),
                "settings": True,
                "keywords": True,
            },
            {
                "id": self.RESET_ALL_SETTING_ID,
                "name": "一键清除全部数据",
                "type": "RESET_ALL",
                "relative_in_root": "清空屏蔽/关键词/测试结果/快照/备份与站点列表（需确认）",
                "settings": True,
                "reset_all": True,
            },
            {
                "id": "setting_apply",
                "name": "应用并扫描"
                if self.config_dirty
                else "扫描并加载",
                "type": "APPLY",
                "relative_in_root": "扫描类型有待应用变更"
                if self.config_dirty
                else "使用当前设置扫描",
                "settings": True,
                "apply": True,
                "enabled": bool(self.config_dirty),
            },
            {
                "id": "setting_auto_scan",
                "name": "自动补扫",
                "type": "AUTO_SCAN",
                "relative_in_root": (
                    "已暂停（清除/恢复后），手动扫描一次即恢复"
                    if self.auto_scan_on_empty and self.auto_scan_suspended
                    else "无有效扫描快照时进入管理页自动扫描一次"
                ),
                "settings": True,
                "auto_scan": True,
                "enabled": bool(self.auto_scan_on_empty),
            },
        ]
        return items

    def _backup_items(self):
        items = []
        for path in self._list_backup_files():
            try:
                registry = self._validate_registry_backup(path)
                count = len(registry.get("items", []))
                modified = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))
                )
                items.append(
                    {
                        "id": "backup_" + self._digest(os.path.basename(path), 12),
                        "name": "撤销 " + modified,
                        "type": "BACKUP",
                        "relative_in_root": "{} 个条目".format(count),
                        "backup": True,
                        "path": path,
                    }
                )
            except Exception as exc:
                self._warn("历史备份读取失败: {} ({})".format(path, exc))
        if items:
            items.append(
                {
                    "id": self.DELETE_BACKUPS_ID,
                    "name": "删除历史备份",
                    "type": "DELETE_BACKUP",
                    "relative_in_root": "当前仅保留 1 份，点击删除",
                    "delete_backup": True,
                }
            )
        return items

    def detailContent(self, array):
        self._ensure_initialized()
        source_id = str(array[0]) if isinstance(array, (list, tuple)) and array else str(array or "")
        if source_id == self.STATUS_ID:
            return {"list": [self._status_detail()]}
        if source_id == self.RESCAN_ID:
            with self.lock:
                if self._site_test_is_running():
                    detail = self._status_detail()
                    detail["vod_remarks"] = "站点正在后台检测"
                    detail["vod_content"] = (
                        "站点正在后检测，请等本批完成后再重新扫描。\n\n"
                        + detail.get("vod_content", "")
                    )
                    return {"list": [detail]}
                if self._refresh_locked(
                    allow_empty=not any(self.type_enabled.values())
                ):
                    self._show_author_scan_surprise()
                    self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                self.inited = True
            return {"list": [self._status_detail()]}
        if source_id == self.EXPORT_LOCAL_JSON_ID:
            with self.lock:
                ok, msg = self._export_local_json_file()
                if not self._notify_app(msg):
                    self._log("INFO", "导出结果: {}".format(msg))
                return {"list": [{
                    "vod_id": self.EXPORT_LOCAL_JSON_ID,
                    "vod_name": "📤 导出结果",
                    "vod_pic": "",
                    "vod_remarks": "成功" if ok else "失败",
                    "vod_content": msg,
                }]}
        if source_id == self.MALWARE_SCAN_ID:
            with self.lock:
                # 如果已经有扫描结果，直接显示
                if self.malware_scan_result:
                    summary = self.malware_scan_result.get('summary', {})
                    content = "恶意代码扫描结果\n"
                    content += "=" * 50 + "\n"
                    content += "扫描路径: {}\n".format(self.malware_scan_result.get('scan_path', '未知'))
                    content += "总文件数: {}\n".format(summary.get('total', 0))
                    content += "安全文件: {}\n".format(summary.get('safe', 0))
                    content += "危险文件: {}\n".format(summary.get('dangerous', 0))
                    content += "加密文件: {}\n".format(summary.get('encrypted', 0))
                    content += "=" * 50 + "\n\n"
                    
                    dangerous = [f for f in self.malware_scan_result.get('files', []) if f.get('is_malware')]
                    if dangerous:
                        content += "⚠ 危险文件:\n"
                        for f in dangerous:
                            content += "\n📁 {}\n".format(f.get('file_name', '未知'))
                            content += "  风险等级: {}\n".format(f.get('risk_level', '未知'))
                            content += "  恶意评分: {}\n".format(f.get('malware_score', 0))
                            if f.get('key_features'):
                                content += "  特征: {}\n".format(', '.join(f['key_features']))
                            content += "  加密方式: {}\n".format(f.get('decrypt_method', '无'))
                    else:
                        content += "✅ 未发现危险文件\n"
                    
                    report_path = os.path.join(self.STORAGE_ROOT, "tvbox", "恶意代码扫描报告.txt")
                    content += "\n详细报告已保存至: {}".format(report_path)
                    
                    return {"list": [{
                        "vod_id": self.MALWARE_SCAN_ID,
                        "vod_name": "🔍 扫描结果",
                        "vod_pic": "",
                        "vod_remarks": "危险: {}".format(summary.get('dangerous', 0)),
                        "vod_content": content,
                    }]}
                else:
                    # 执行扫描
                    ok, msg = self._run_malware_scan()
                    if ok:
                        # 再次获取结果并显示
                        summary = self.malware_scan_result.get('summary', {})
                        content = "恶意代码扫描完成\n"
                        content += "=" * 50 + "\n"
                        content += "总文件: {}\n".format(summary.get('total', 0))
                        content += "危险文件: {}\n".format(summary.get('dangerous', 0))
                        content += "安全文件: {}\n".format(summary.get('safe', 0))
                        content += "加密文件: {}\n".format(summary.get('encrypted', 0))
                        content += "=" * 50 + "\n\n"
                        
                        dangerous = [f for f in self.malware_scan_result.get('files', []) if f.get('is_malware')]
                        if dangerous:
                            content += "⚠ 发现 {} 个危险文件:\n".format(len(dangerous))
                            for f in dangerous[:10]:
                                content += "\n📁 {}\n".format(f.get('file_name', '未知'))
                                content += "  等级: {}\n".format(f.get('risk_level', '未知'))
                                content += "  评分: {}\n".format(f.get('malware_score', 0))
                        else:
                            content += "✅ 所有文件安全\n"
                        
                        report_path = os.path.join(self.STORAGE_ROOT, "tvbox", "恶意代码扫描报告.txt")
                        content += "\n详细报告已保存至: {}".format(report_path)
                        
                        if not self._notify_app(msg):
                            self._log("INFO", "扫描结果: {}".format(msg))
                        
                        return {"list": [{
                            "vod_id": self.MALWARE_SCAN_ID,
                            "vod_name": "🔍 扫描完成",
                            "vod_pic": "",
                            "vod_remarks": "危险: {}".format(summary.get('dangerous', 0)),
                            "vod_content": content,
                        }]}
                    else:
                        return {"list": [{
                            "vod_id": self.MALWARE_SCAN_ID,
                            "vod_name": "🔍 扫描失败",
                            "vod_pic": "",
                            "vod_remarks": "失败",
                            "vod_content": msg,
                        }]}

        source = self.cache["source_index"].get(source_id)
        if not source:
            return {"list": [{"vod_name": "源不存在", "vod_content": "请重新扫描后再试。"}]}

        site_text = json.dumps(source["site"], ensure_ascii=False, indent=2)
        validation = source.get("validation") or "静态检查未发现明显问题"
        test_result = source.get("test_result", {})
        test_text = (
            "{} · {} · {}".format(
                self._test_result_label(test_result),
                test_result.get("checked_at", "-"),
                test_result.get("detail", ""),
            )
            if isinstance(test_result, dict) and test_result
            else "未检测"
        )
        content = (
            "类型: {type}\n"
            "文件: {path}\n"
            "相对路径: {relative}\n"
            "稳定标识: {identity}\n"
            "检查: {validation}\n\n"
            "连通性: {test_result}\n\n"
            "生成的站点配置:\n{site}\n\n"
            "注入注册表: {output}\n"
            "注册表变更后，App 会主动重载站点列表。"
        ).format(
            type=self.TYPE_LABEL.get(source["type"], source["type"]),
            path=source["path"],
            relative=source["relative_in_root"],
            identity=source["identity"],
            validation=validation,
            test_result=test_text,
            site=site_text,
            output=self.output_path,
        )
        return {
            "list": [
                {
                    "vod_id": source_id,
                    "vod_name": source["name"],
                    "vod_pic": "",
                    "vod_remarks": self.TYPE_LABEL.get(
                        source["type"], source["type"]
                    ),
                    "vod_content": content,
                }
            ]
        }

    def _status_detail(self):
        warning_text = "\n".join("- " + item for item in self.status["warnings"][:20]) or "无"
        error_text = self.status["error"] or "无"
        test_counts = {"available": 0, "unavailable": 0, "limited": 0}
        for result in list(self.site_test_results.values()):
            state = str(result.get("state", "")) if isinstance(result, dict) else ""
            if state in test_counts:
                test_counts[state] += 1
        content = (
            "版本: {version}\n"
            "扫描方式: 手动点击 + 进入自动补扫({auto_scan})\n"
            "严格识别: {strict}\n"
            "待应用配置: {dirty}\n"
            "分类开关: {types}\n"
            "扫描时间: {scan_time}\n"
            "发现文件: {found}\n"
            "有效源: {included}\n"
            "忽略源: {ignored}\n"
            "18+过滤: {adult_block} · 自动屏蔽 {adult_filtered} · 已放行 {adult_allowed}\n"
            "关键词屏蔽: 黑名单 {kw_block} · 白名单 {kw_allow} · 已屏蔽 {kw_filtered}\n"
            "清理过期忽略项: {stale_ignored}\n"
            "跳过文件: {skipped}\n"
            "重复项: {duplicates}\n"
            "缓存命中/重检: {cache_hits}/{cache_misses}\n"
            "连通性检测: 可达 {test_available} · 结构无效 {test_unavailable} · 受限 {test_limited}\n"
            "保留注入项: {manual}\n"
            "自动注入项: {generated}\n"
            "变更预览: +{added} ~{updated} -{removed} ={unchanged}\n"
            "写入状态: {state}\n"
            "错误: {error}\n\n"
            "警告:\n{warnings}\n\n"
            "站点注入注册表: {output}\n\n"
            "扫描开关设置: {settings}\n\n"
            "扫描目录配置: {roots_config}\n"
            "诊断日志: {log_path} (上限 {max_log_kb} KB)\n"
            "扫描根目录: {scan_base}\n"
            "XBPQ JAR: {xbpq_jar}\n"
            "扫描上限: 文件 {max_files} · 深度 {max_depth} · 单文件 {max_size} bytes\n\n"
            "扫描结果已写入 WebHTV 站点注入注册表，手工注入项保留。\n"
            "注册表变更会在当前操作返回后主动重载 App。\n\n"
            "----------------\n"
            "秋色正好，江 晚枫来过。"
        ).format(
            version=self.VERSION,
            auto_scan="暂停"
            if self.auto_scan_on_empty and self.auto_scan_suspended
            else ("开" if self.auto_scan_on_empty else "关"),
            strict="开启" if self.strict_recognition else "关闭",
            dirty="是" if self.config_dirty else "否",
            types=" ".join(
                "{}:{}{}".format(
                    self.TYPE_LABEL.get(source_type, source_type),
                    "开" if self.type_enabled.get(source_type, True) else "关",
                    "->{}".format(
                        "开"
                        if self.pending_type_enabled.get(
                            source_type, self.type_enabled.get(source_type, True)
                        )
                        else "关"
                    )
                    if self.pending_type_enabled.get(
                        source_type, self.type_enabled.get(source_type, True)
                    )
                    != self.type_enabled.get(source_type, True)
                    else "",
                )
                for source_type in self.TYPE_ORDER
            ),
            scan_time=self.status["scan_time"],
            found=self.status["found"],
            included=self.status["included"],
            ignored=self.status["ignored"],
            adult_block="开" if self.block_adult_sites else "关",
            adult_filtered=len(self.adult_blocked_sources),
            adult_allowed=len(self.adult_allowed_sources),
            kw_block=len(self.custom_block_keywords),
            kw_allow=len(self.custom_allow_keywords),
            kw_filtered=len(self.keyword_blocked_sources),
            stale_ignored=self.status["stale_ignored_removed"],
            skipped=self.status["skipped"],
            duplicates=self.status["duplicates"],
            cache_hits=self.status["cache_hits"],
            cache_misses=self.status["cache_misses"],
            test_available=test_counts["available"],
            test_unavailable=test_counts["unavailable"],
            test_limited=test_counts["limited"],
            manual=self.status["manual_sites"],
            generated=self.status["generated_sites"],
            added=self.status["added_sites"],
            updated=self.status["updated_sites"],
            removed=self.status["removed_sites"],
            unchanged=self.status["unchanged_sites"],
            state=self.status["write_state"],
            error=error_text,
            warnings=warning_text,
            output=self.output_path,
            settings=self.settings_path,
            roots_config=self.roots_config_path,
            log_path=self._diagnostic_log_path(),
            max_log_kb=max(1, int(self.max_log_size) // 1024),
            scan_base=self.scan_base_path or "自动探测 ({})".format(self.local_base_dir),
            xbpq_jar="已配置" if self.xbpq_jar else "未配置",
            max_files=self.max_scan_files,
            max_depth=self.max_scan_depth,
            max_size=self.max_source_size,
        )
        return {
            "vod_id": self.STATUS_ID,
            "vod_name": "本地源扫描状态",
            "vod_pic": "",
            "vod_remarks": self.status["write_state"],
            "vod_content": content,
        }

    def searchContent(self, key, quick, pg="1"):
        self._ensure_initialized()
        keyword = str(key or "").strip().lower()
        page = self._page_number(pg)
        if not keyword:
            items = []
        else:
            items = [
                source
                for source in self.cache["sources"]
                if keyword in source["name"].lower()
                or keyword in source["relative_in_root"].lower()
                or keyword in source["type"].lower()
            ]
        return self._paged_result(items, page)

    def _paged_result(self, items, page):
        total = len(items)
        page_size = max(1, int(self.page_size))
        page_count = max(1, (total + page_size - 1) // page_size)
        if page > page_count:
            page_items = []
        else:
            start = (page - 1) * page_size
            page_items = items[start : start + page_size]
        return {
            "page": page,
            "pagecount": page_count,
            "limit": page_size,
            "total": total,
            "list": [self._source_vod(item) for item in page_items],
        }

    def _source_state_icon(self, source):
        result = source.get("test_result", {})
        state = str(result.get("state", "")) if isinstance(result, dict) else ""
        if state == "unavailable":
            return "⛔ "
        if state == "limited":
            return "⚠ "
        return "🚫 " if source.get("ignored") else ""

    def _source_vod(self, source):
        if source.get("delete_backup"):
            return {
                "vod_id": source["id"],
                "vod_name": "🗑 " + source["name"],
                "vod_pic": "",
                "vod_remarks": source["relative_in_root"],
                "action": self.ACTION_DELETE_BACKUPS,
            }
        if source.get("backup"):
            return {
                "vod_id": source["id"],
                "vod_name": "↩ " + source["name"],
                "vod_pic": "",
                "vod_remarks": source["relative_in_root"],
                "action": self.ACTION_RESTORE_SNAPSHOT_PREFIX
                + os.path.basename(source["path"]),
            }
        if source.get("settings"):
            if source.get("reset_scan_base"):
                return {
                    "vod_id": source["id"],
                    "vod_name": "↺ " + source["name"],
                    "vod_pic": "",
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_RESET_SCAN_BASE,
                }
            if source.get("scan_base_path"):
                return {
                    "vod_id": source["id"],
                    "vod_name": "✎ " + source["name"],
                    "vod_pic": "",
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_EDIT_SCAN_BASE,
                }
            if source.get("scan_types"):
                return {
                    "vod_id": source["id"],
                    "vod_name": "☷ " + source["name"],
                    "vod_pic": "",
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_EDIT_SCAN_TYPES,
                }
            if source.get("keywords"):
                return {
                    "vod_id": source["id"],
                    "vod_name": "🔧 " + source["name"],
                    "vod_pic": "",
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_EDIT_KEYWORDS,
                }
            if source.get("reset_all"):
                return {
                    "vod_id": source["id"],
                    "vod_name": "🗑 " + source["name"],
                    "vod_pic": "",
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_RESET_ALL,
                }
            if source.get("apply"):
                return {
                    "vod_id": source["id"],
                    "vod_name": "⚡ " + source["name"],
                    "vod_pic": "",
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_APPLY_SCAN_CONFIG,
                }
            if source.get("auto_scan"):
                enabled = bool(source.get("enabled"))
                return {
                    "vod_id": source["id"],
                    "vod_name": "{} {}".format(
                        "🟢" if enabled else "⚪", source["name"]
                    ),
                    "vod_pic": "",
                    "vod_remarks": "Toggle · {} · {}".format(
                        "已开启" if enabled else "已关闭",
                        source["relative_in_root"],
                    ),
                    "action": self.ACTION_TOGGLE_AUTO_SCAN,
                }
            enabled = bool(source.get("enabled"))
            return {
                "vod_id": source["id"],
                "vod_name": "🟢 {}".format(source["name"])
                if enabled
                else "⚪ {}".format(source["name"]),
                "vod_pic": "",
                "vod_remarks": "Toggle · {}".format(
                    "已开启" if enabled else "已关闭"
                ),
                "action": self.ACTION_TOGGLE_TYPE_PREFIX + source["type"],
            }
        if source.get("export"):
            return {
                "vod_id": source["id"],
                "vod_name": "📤 " + source["name"],
                "vod_pic": "",
                "vod_remarks": source["relative_in_root"],
                "action": source.get("action", ""),
            }
        if source.get("scan"):
            return {
                "vod_id": source["id"],
                "vod_name": "🔍 " + source["name"],
                "vod_pic": "",
                "vod_remarks": source["relative_in_root"],
                "action": source.get("action", ""),
            }
        # 自定义关键词屏蔽的站点：专属标记，点击放行（下次扫描正常加载）
        identity = source.get("identity", "")
        if source.get("ignored") and identity in self.keyword_blocked_sources:
            return {
                "vod_id": source["id"],
                "vod_name": "🔧 " + source["name"],
                "vod_pic": "",
                "vod_remarks": "关键词屏蔽 · {} · 点击放行".format(
                    source["type"]
                ),
                "action": self.ACTION_KEYWORD_ALLOW_PREFIX + source["id"],
            }
        # 已放行的关键词站点：显示标记，点击可重新屏蔽
        if identity in self.keyword_allowed_sources:
            return {
                "vod_id": source["id"],
                "vod_name": "🔧已放行 " + source["name"],
                "vod_pic": "",
                "vod_remarks": "已放行关键词屏蔽 · {} · 点击重新屏蔽".format(
                    source["type"]
                ),
                "action": self.ACTION_KEYWORD_UNALLOW_PREFIX + source["id"],
            }
        # 18+ 成人自动屏蔽的站点：专属标记，点击放行（进白名单，下次扫描正常加载）
        if source.get("ignored") and identity in self.adult_blocked_sources:
            return {
                "vod_id": source["id"],
                "vod_name": "⛔ " + source["name"],
                "vod_pic": "",
                "vod_remarks": "成人自动屏蔽 · {} · 点击放行".format(
                    source["type"]
                ),
                "action": self.ACTION_ADULT_ALLOW_PREFIX + source["id"],
            }
        # 已放行的成人站点：显示标记，点击可取消放行（重新进入成人检测/屏蔽）
        if self.block_adult_sites and identity in self.adult_allowed_sources:
            return {
                "vod_id": source["id"],
                "vod_name": "⛔已放行 " + source["name"],
                "vod_pic": "",
                "vod_remarks": "已放行成人屏蔽 · {} · 点击重新屏蔽".format(
                    source["type"]
                ),
                "action": self.ACTION_ADULT_UNALLOW_PREFIX + source["id"],
            }
        return {
            "vod_id": source["id"],
            "vod_name": self._source_state_icon(source) + source["name"],
            "vod_pic": "",
            "vod_remarks": "{} · {} · {} · {}".format(
                source["type"],
                source["relative_in_root"],
                "点击恢复" if source.get("ignored") else "点击忽略",
                self._test_result_label(source.get("test_result")),
            ),
            "action": self.ACTION_TOGGLE_IGNORE_PREFIX + source["id"],
        }

    def _page_number(self, value):
        try:
            return max(1, int(value))
        except Exception:
            return 1

    def action(self, action):
        action = str(action)
        self._log("INFO", "用户操作: {}".format(action))
        
        # 导出操作独立处理
        if action == self.ACTION_EXPORT_LOCAL_JSON:
            with self.lock:
                ok, msg = self._export_local_json_file()
                if not self._notify_app(msg):
                    self._log("INFO", "导出结果: {}".format(msg))
                return {"code": 0, "msg": msg}
        
        # 恶意代码扫描操作独立处理
        if action == self.ACTION_MALWARE_SCAN:
            with self.lock:
                ok, msg = self._run_malware_scan()
                if not self._notify_app(msg):
                    self._log("INFO", "扫描结果: {}".format(msg))
                return {"code": 0, "msg": msg}
        
        protected = (
            action not in (self.ACTION_TEST_SITES, self.ACTION_RETEST_SITES)
            and not action.startswith(self.ACTION_SOURCE_PREFIX)
        )
        if protected:
            with self.lock:
                if self._site_test_is_running():
                    return {
                        "code": 0,
                        "msg": "站点正在后台检测，请等本批完成后再修改扫描或屏蔽设置",
                    }
                return self._action_impl(action)
        return self._action_impl(action)

    def _action_impl(self, action):
        if action == self.ACTION_EDIT_SCAN_BASE:
            opened, message = self._open_scan_base_dialog()
            if not opened:
                self._log("WARN", "扫描路径设置未打开: {}".format(message))
            return {
                "code": 0,
                "msg": "" if opened else message,
            }
        if action == self.ACTION_RESET_SCAN_BASE:
            with self.lock:
                try:
                    self._set_scan_base_path("")
                    return {
                        "code": 0,
                        "msg": "扫描目录已初始化为: {}".format(
                            self.local_base_dir
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "扫描目录初始化失败: {}".format(exc))
                    return {
                        "code": 0,
                        "msg": "扫描目录初始化失败：{}".format(exc),
                    }
        if action == self.ACTION_EDIT_SCAN_TYPES:
            opened, message = self._open_scan_types_dialog()
            if not opened:
                self._log("WARN", "扫描类型设置未打开: {}".format(message))
            return {
                "code": 0,
                "msg": "" if opened else message,
            }
        if action == self.ACTION_EDIT_KEYWORDS:
            opened, message = self._open_keywords_dialog()
            if not opened:
                self._log("WARN", "关键词屏蔽设置未打开: {}".format(message))
            return {
                "code": 0,
                "msg": "" if opened else message,
            }
        if action == self.ACTION_RESET_ALL:
            opened, message = self._open_reset_all_dialog()
            if not opened:
                self._log("WARN", "清除数据确认框未打开: {}".format(message))
            return {
                "code": 0,
                "msg": "" if opened else message,
            }
        # 自定义关键词误判站点：手动放行（下次扫描正常加载）
        if action.startswith(self.ACTION_KEYWORD_ALLOW_PREFIX):
            source_id = action[len(self.ACTION_KEYWORD_ALLOW_PREFIX):]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "源不存在，请重新扫描"}
            with self.lock:
                identity = source["identity"]
                previous_allowed = set(self.keyword_allowed_sources)
                previous_blocked = set(self.keyword_blocked_sources)
                previous_cache = self.cache
                previous_status = self.status
                self.keyword_allowed_sources.add(identity)
                self.keyword_blocked_sources.discard(identity)
                self._sync_ignored_sources()
                try:
                    self._save_settings()
                    ok = self._refresh_locked(allow_empty=True)
                    if not ok:
                        raise ValueError(
                            self.status["error"] or self.status["write_state"]
                        )
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    return {
                        "code": 0,
                        "msg": "已放行：{}；下次扫描将正常加载；{}".format(
                            source["name"], detail
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "关键词放行未生效: {}".format(exc))
                    self.keyword_allowed_sources = previous_allowed
                    self.keyword_blocked_sources = previous_blocked
                    self.cache = previous_cache
                    self.status = previous_status
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    return {"code": 0, "msg": "放行未生效：{}".format(exc)}
        # 已放行的关键词站点：取消放行（重新进入关键词检测/屏蔽）
        if action.startswith(self.ACTION_KEYWORD_UNALLOW_PREFIX):
            source_id = action[len(self.ACTION_KEYWORD_UNALLOW_PREFIX):]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "源不存在，请重新扫描"}
            with self.lock:
                identity = source["identity"]
                previous_allowed = set(self.keyword_allowed_sources)
                previous_blocked = set(self.keyword_blocked_sources)
                previous_cache = self.cache
                previous_status = self.status
                self.keyword_allowed_sources.discard(identity)
                self._sync_ignored_sources()
                try:
                    self._save_settings()
                    ok = self._refresh_locked(allow_empty=True)
                    if not ok:
                        raise ValueError(
                            self.status["error"] or self.status["write_state"]
                        )
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    return {
                        "code": 0,
                        "msg": "已取消放行：{}；若仍命中黑名单将重新屏蔽；{}".format(
                            source["name"], detail
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "取消关键词放行未生效: {}".format(exc))
                    self.keyword_allowed_sources = previous_allowed
                    self.keyword_blocked_sources = previous_blocked
                    self.cache = previous_cache
                    self.status = previous_status
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    return {"code": 0, "msg": "取消放行未生效：{}".format(exc)}
        # 18+ 误判站点：手动放行（加入白名单，下次扫描正常加载）
        if action.startswith(self.ACTION_ADULT_ALLOW_PREFIX):
            source_id = action[len(self.ACTION_ADULT_ALLOW_PREFIX):]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "源不存在，请重新扫描"}
            with self.lock:
                identity = source["identity"]
                previous_allowed = set(self.adult_allowed_sources)
                previous_blocked = set(self.adult_blocked_sources)
                previous_cache = self.cache
                previous_status = self.status
                self.adult_allowed_sources.add(identity)
                self.adult_blocked_sources.discard(identity)
                self._sync_ignored_sources()
                try:
                    self._save_settings()
                    ok = self._refresh_locked(allow_empty=True)
                    if not ok:
                        raise ValueError(
                            self.status["error"] or self.status["write_state"]
                        )
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    return {
                        "code": 0,
                        "msg": "已放行：{}；下次扫描将正常加载；{}".format(
                            source["name"], detail
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "放行未生效: {}".format(exc))
                    self.adult_allowed_sources = previous_allowed
                    self.adult_blocked_sources = previous_blocked
                    self.cache = previous_cache
                    self.status = previous_status
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    return {"code": 0, "msg": "放行未生效：{}".format(exc)}
        # 18+ 已放行站点：取消放行（重新进入成人检测/屏蔽）
        if action.startswith(self.ACTION_ADULT_UNALLOW_PREFIX):
            source_id = action[len(self.ACTION_ADULT_UNALLOW_PREFIX):]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "源不存在，请重新扫描"}
            with self.lock:
                identity = source["identity"]
                previous_allowed = set(self.adult_allowed_sources)
                previous_blocked = set(self.adult_blocked_sources)
                previous_cache = self.cache
                previous_status = self.status
                self.adult_allowed_sources.discard(identity)
                self._sync_ignored_sources()
                try:
                    self._save_settings()
                    ok = self._refresh_locked(allow_empty=True)
                    if not ok:
                        raise ValueError(
                            self.status["error"] or self.status["write_state"]
                        )
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    return {
                        "code": 0,
                        "msg": "已取消放行：{}；若仍命中规则将重新屏蔽；{}".format(
                            source["name"], detail
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "取消放行未生效: {}".format(exc))
                    self.adult_allowed_sources = previous_allowed
                    self.adult_blocked_sources = previous_blocked
                    self.cache = previous_cache
                    self.status = previous_status
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    return {"code": 0, "msg": "取消放行未生效：{}".format(exc)}
        if action.startswith(self.ACTION_TOGGLE_IGNORE_PREFIX):
            source_id = action[len(self.ACTION_TOGGLE_IGNORE_PREFIX) :]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "源不存在，请重新扫描"}
            with self.lock:
                identity = source["identity"]
                ignored = identity not in self.ignored_sources
                previous_ignored = set(self.ignored_sources)
                previous_manual_ignored = set(self.manual_ignored_sources)
                previous_auto_blocked = set(self.auto_blocked_sources)
                previous_results = dict(self.site_test_results)
                previous_cache = self.cache
                previous_status = self.status
                if ignored:
                    self.manual_ignored_sources.add(identity)
                else:
                    self.manual_ignored_sources.discard(identity)
                    self.auto_blocked_sources.discard(identity)
                    self.site_test_results.pop(identity, None)
                self._sync_ignored_sources()
                try:
                    self._save_settings()
                    ok = self._refresh_locked(allow_empty=True)
                    if not ok:
                        raise ValueError(
                            self.status["error"] or self.status["write_state"]
                        )
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    return {
                        "code": 0,
                        "msg": "{}；{}".format(
                            "已忽略：{}".format(source["name"])
                            if ignored
                            else "已恢复：{}".format(source["name"]),
                            detail,
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "忽略设置未生效: {}".format(exc))
                    self.ignored_sources = previous_ignored
                    self.manual_ignored_sources = previous_manual_ignored
                    self.auto_blocked_sources = previous_auto_blocked
                    self.site_test_results = previous_results
                    self.cache = previous_cache
                    self.status = previous_status
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    return {"code": 0, "msg": "忽略设置未生效：{}".format(exc)}
        if action.startswith(self.ACTION_SOURCE_PREFIX):
            source_id = action[len(self.ACTION_SOURCE_PREFIX) :]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "源不存在，请重新扫描"}
            return {
                "code": 0,
                "msg": "{} · {}；已写入站点注入注册表".format(
                    source["type"], source["relative_in_root"]
                ),
            }
        if action in (self.ACTION_TEST_SITES, self.ACTION_RETEST_SITES):
            with self._site_test_control_lock:
                worker = self._site_test_thread
                if worker is not None and worker.is_alive():
                    return {
                        "code": 0,
                        "msg": "站点正在后台检测，进度会逐站通知",
                    }
            with self.lock:
                if not self.cache["sources"] and not self.cache["ignored"]:
                    return {"code": 0, "msg": "暂无扫描结果，请先点击一键扫描并加载"}
            force = action == self.ACTION_RETEST_SITES
            if not self._start_site_test_worker(force=force):
                return {
                    "code": 0,
                    "msg": "站点正在后台检测，进度会逐站通知",
                }
            return {
                "code": 0,
                "msg": "已开始后台{}，本批最多 {} 个，进度会逐站通知".format(
                    "重新检测" if force else "连通性检测",
                    self.MAX_SITE_TESTS,
                ),
            }
        if action == self.ACTION_CLEAR_SITES:
            with self.lock:
                previous_ignored = set(self.ignored_sources)
                previous_manual_ignored = set(self.manual_ignored_sources)
                previous_auto_blocked = set(self.auto_blocked_sources)
                previous_results = dict(self.site_test_results)
                previous_cache = self.cache
                previous_status = self.status
                previous_retest_pending = list(self._retest_pending)
                previous_retest_auto_blocked = set(
                    self._retest_auto_blocked
                )
                previous_auto_scan_suspended = self.auto_scan_suspended
                try:
                    self.manual_ignored_sources.clear()
                    self.auto_blocked_sources.clear()
                    self.ignored_sources.clear()
                    self.site_test_results.clear()
                    self._retest_pending = []
                    self._retest_auto_blocked.clear()
                    self.auto_scan_suspended = True
                    self._save_settings()
                    removed = self._clear_generated_registry()
                    self._set_manual_idle_status(
                        "已清除 {} 个自动站点及扫描状态".format(removed)
                    )
                    self._clear_scan_cache_file()
                    _, detail = self._reload_app_vod_config(expected_keys=set())
                    self.inited = True
                    return {
                        "code": 0,
                        "msg": "已清除 {} 个自动站点、忽略状态和检测缓存，手工站点及类型配置已保留；{}".format(
                            removed,
                            detail,
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "清除自动站点失败: {}".format(exc))
                    self.ignored_sources = previous_ignored
                    self.manual_ignored_sources = previous_manual_ignored
                    self.auto_blocked_sources = previous_auto_blocked
                    self.site_test_results = previous_results
                    self.cache = previous_cache
                    self.status = previous_status
                    self._retest_pending = previous_retest_pending
                    self._retest_auto_blocked = previous_retest_auto_blocked
                    self.auto_scan_suspended = previous_auto_scan_suspended
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    return {"code": 0, "msg": "清除失败：{}".format(exc)}
        if action == self.ACTION_DELETE_BACKUPS:
            with self.lock:
                try:
                    removed = self._delete_backup_files()
                    return {
                        "code": 0,
                        "msg": "已删除历史备份"
                        if removed
                        else "暂无历史备份",
                    }
                except Exception as exc:
                    self._log("ERROR", "历史备份删除失败: {}".format(exc))
                    return {"code": 0, "msg": "历史备份删除失败：{}".format(exc)}
        if action.startswith(self.ACTION_RESTORE_SNAPSHOT_PREFIX):
            name = os.path.basename(
                action[len(self.ACTION_RESTORE_SNAPSHOT_PREFIX) :]
            )
            path = os.path.join(self.backup_dir, name)
            with self.lock:
                try:
                    if not name.startswith("registry-") or not name.endswith(".json"):
                        raise ValueError("历史备份名称无效")
                    count = self._restore_registry_file(path)
                    self._suspend_auto_scan()
                    self._set_manual_idle_status(
                        "已恢复历史备份，等待手动扫描"
                    )
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    return {
                        "code": 0,
                        "msg": "已恢复历史备份（{} 个条目）；{}".format(
                            count,
                            detail,
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "历史备份恢复失败: {}".format(exc))
                    return {"code": 0, "msg": "历史备份恢复失败：{}".format(exc)}
        if action == self.ACTION_TOGGLE_AUTO_SCAN:
            with self.lock:
                previous_enabled = self.auto_scan_on_empty
                previous_suspended = self.auto_scan_suspended
                try:
                    self.auto_scan_on_empty = not previous_enabled
                    if self.auto_scan_on_empty:
                        self.auto_scan_suspended = False
                    self._save_settings()
                    return {
                        "code": 0,
                        "msg": "进入时自动补扫已{}".format(
                            "开启，无有效快照时进入管理页会自动扫描一次"
                            if self.auto_scan_on_empty
                            else "关闭，仅手动点击时扫描"
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "自动补扫开关保存失败: {}".format(exc))
                    self.auto_scan_on_empty = previous_enabled
                    self.auto_scan_suspended = previous_suspended
                    return {"code": 0, "msg": "自动补扫开关保存失败：{}".format(exc)}
        if action.startswith(self.ACTION_TOGGLE_TYPE_PREFIX):
            source_type = action[len(self.ACTION_TOGGLE_TYPE_PREFIX) :].upper()
            if source_type not in self.TYPE_ORDER:
                return {"code": 0, "msg": "未知站点类型"}
            with self.lock:
                previous = self.pending_type_enabled.get(
                    source_type, self.type_enabled.get(source_type, True)
                )
                try:
                    self._set_pending_type_settings(
                        {source_type: not previous}
                    )
                    return {
                        "code": 0,
                        "msg": "{} 扫描已设为{}，等待应用".format(
                            source_type,
                            "开启"
                            if self.pending_type_enabled[source_type]
                            else "关闭",
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "分类开关保存失败: {}".format(exc))
                    return {"code": 0, "msg": "分类开关保存失败：{}".format(exc)}
        if action == self.ACTION_APPLY_SCAN_CONFIG:
            action = self.ACTION_RESCAN
        if action != self.ACTION_RESCAN:
            return {"code": 0, "msg": "未知操作"}
        with self.lock:
            if self.config_dirty:
                try:
                    self._apply_pending_type_settings()
                except Exception as exc:
                    self._log("ERROR", "扫描配置应用失败: {}".format(exc))
                    return {"code": 0, "msg": "扫描配置应用失败：{}".format(exc)}
            ok = self._refresh_locked(
                allow_empty=not any(self.type_enabled.values())
            )
            self.inited = True
            if ok:
                self._show_author_scan_surprise()
                _, detail = self._reload_app_vod_config(
                    expected_keys=self._generated_registry_keys()
                )
                message = "扫描完成：{} 个源，{}；{}".format(
                    len(self.cache["sources"]),
                    "{} (+{} ~{} -{})".format(
                        self.status["write_state"],
                        self.status["added_sites"],
                        self.status["updated_sites"],
                        self.status["removed_sites"],
                    ),
                    detail,
                )
            else:
                message = "扫描未完成：{}".format(self.status["error"] or self.status["write_state"])
            return {"code": 0, "msg": message}

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": "",
            "header": {},
            "msg": "这是配置管理条目，不能作为媒体播放。",
        }

    def destroy(self):
        self._destroyed = True
        self._site_test_cancel.set()
        return "destroy"