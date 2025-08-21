import json
import re
import os
import requests
from urllib.parse import urljoin, quote
from typing import Optional, List, Dict, Any

# 忽略 InsecureRequestWarning 警告
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning

    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    pass


class PanyqSearcher:
    """
    一个功能完备且全自动的 panyq.com 搜索引擎客户端。

    此版本移除了所有用户交互，实现了 Action ID 的自动获取、验证、失效更新和重试机制。
    """

    BASE_URL = "https://panyq.com"
    CONFIG_FILE = "panyq_config.json"
    ID_KEYS = ["credential_action_id", "intermediate_action_id", "final_link_action_id"]

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化客户端。自动加载或发现 Action ID。
        """
        self.config_path = config_path or self.CONFIG_FILE
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        # 启动时自动管理 Action ID
        self.action_ids = self._load_or_discover_ids()

    # ==========================================================================
    # 核心逻辑: Action ID 自动管理
    # ==========================================================================

    def _load_or_discover_ids(self) -> Dict[str, str]:
        """主调度函数：加载、验证并按需发现 Action ID。"""
        local_ids = self._load_ids_from_file()

        if all(key in local_ids for key in self.ID_KEYS):
            print("[+] 本地配置完整，开始验证有效性...")
            if self._validate_credential_id(local_ids[self.ID_KEYS[0]]):
                print("[+] 本地 Action ID 验证通过，可继续使用。")
                return local_ids
            else:
                print("[!] 警告: 本地配置已失效，将触发完整的重新发现流程。")
                return self._discover_and_validate_all_ids()

        print("[i] 信息: 本地配置不完整或不存在，进入发现与验证模式。")
        return self._discover_and_validate_all_ids(existing_ids=local_ids)

    def _force_refresh_ids(self):
        """
        强制刷新所有 Action ID。会删除现有配置文件并重新执行发现流程。
        """
        print("\n[!] 触发 Action ID 强制刷新机制...")
        if os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
                print(f"[*] 已删除旧的配置文件 '{self.config_path}' 以进行刷新。")
            except OSError as e:
                print(f"[!] 警告: 删除配置文件失败: {e}。将继续尝试重新发现。")

        # 重新调用核心发现逻辑
        self.action_ids = self._discover_and_validate_all_ids()

    def _load_ids_from_file(self) -> Dict[str, str]:
        """从 JSON 文件加载 ID"""
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"[!] 警告: 读取配置文件 '{self.config_path}' 时出错，将忽略。")
            return {}

    def _save_ids_to_file(self, ids: Dict[str, str]):
        """将 ID 保存到 JSON 文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(ids, f, indent=4)
        print(f"[+] 配置已更新并保存至 '{self.config_path}'")

    def _discover_and_validate_all_ids(self, existing_ids: Dict[str, str] = None) -> Dict[str, str]:
        """核心发现与验证流程，支持断点续传。"""
        if existing_ids is None: existing_ids = {}

        print("\n--- 开始自动发现和验证 Action ID ---")
        potential_ids = self._find_potential_action_ids_from_site()
        if not potential_ids:
            raise RuntimeError("无法从网站发现任何潜在的 Action ID。")

        validated_values = set(existing_ids.values())
        candidate_ids = [pid for pid in potential_ids if pid not in validated_values]

        final_ids = {}

        # 1. 验证 credential_action_id
        print(f"\n[1/3] 正在从 {len(candidate_ids)} 个候选中验证 '{self.ID_KEYS[0]}'...")
        for p_id in candidate_ids:
            if self._validate_credential_id(p_id):
                print(f"    -> [成功] '{self.ID_KEYS[0]}': {p_id}")
                final_ids[self.ID_KEYS[0]] = p_id
                candidate_ids.remove(p_id)
                break
        if self.ID_KEYS[0] not in final_ids:
            raise RuntimeError(f"自动验证失败：未能找到有效的 '{self.ID_KEYS[0]}'")

        test_creds = self._internal_get_credentials("热门", final_ids[self.ID_KEYS[0]])
        if not test_creds: raise RuntimeError("获取测试凭证失败，无法继续验证后续ID。")

        # 2. 验证 intermediate_action_id
        print(f"\n[2/3] 正在从 {len(candidate_ids)} 个候选中验证 '{self.ID_KEYS[1]}'...")
        for p_id in candidate_ids:
            if self._validate_intermediate_id(p_id, test_creds['hash'], test_creds['sha']):
                print(f"    -> [成功] '{self.ID_KEYS[1]}': {p_id}")
                final_ids[self.ID_KEYS[1]] = p_id
                candidate_ids.remove(p_id)
                break
        if self.ID_KEYS[1] not in final_ids:
            raise RuntimeError(f"自动验证失败：未能找到有效的 '{self.ID_KEYS[1]}'")

        hits = self._internal_get_search_results(test_creds['sign'])
        if not hits: raise RuntimeError("获取测试结果列表失败，无法继续验证。")
        test_eid = hits[0]['eid']

        # 3. 验证 final_link_action_id
        print(f"\n[3/3] 正在从 {len(candidate_ids)} 个候选中验证 '{self.ID_KEYS[2]}'...")
        for p_id in candidate_ids:
            self._internal_perform_intermediate_step(final_ids[self.ID_KEYS[1]], test_creds['hash'],
                                                     test_creds['sha'], test_eid)
            if self._validate_final_link_id(p_id, test_eid):
                print(f"    -> [成功] '{self.ID_KEYS[2]}': {p_id}")
                final_ids[self.ID_KEYS[2]] = p_id
                break
        if self.ID_KEYS[2] not in final_ids:
            raise RuntimeError(f"自动验证失败：未能找到有效的 '{self.ID_KEYS[2]}'")

        print("\n[+] 所有 Action ID 均已成功验证！")
        self._save_ids_to_file(final_ids)
        return final_ids

    # ==========================================================================
    # 辅助函数与网络请求 (此部分基本保持不变)
    # ==========================================================================

    def _find_potential_action_ids_from_site(self) -> List[str]:
        print("[i] 正在访问主页并寻找 JS 文件...")
        try:
            response = self.session.get(self.BASE_URL, timeout=15, verify=False)
            response.raise_for_status()
            js_links = re.findall(r'<script src="(/_next/static/[^"]+\.js)"', response.text)
            if not js_links: return []
            all_ids = set()
            print(f"[i] 发现 {len(js_links)} 个 JS 文件，开始扫描...")
            for link in js_links:
                js_url = urljoin(self.BASE_URL, link)
                try:
                    js_content = self.session.get(js_url, timeout=15, verify=False).text
                    found = re.findall(r'["\']([a-f0-9]{40})["\']', js_content)
                    if found: all_ids.update(found)
                except requests.RequestException:
                    continue
            print(f"[+] 扫描完成，发现 {len(all_ids)} 个潜在的 Action ID。")
            return list(all_ids)
        except requests.RequestException as e:
            print(f"[!] 错误: 获取网站主页失败 - {e}")
            return []

    def _validate_credential_id(self, action_id: str) -> bool:
        # print(f"    -> 测试ID '{action_id[:10]}...' 用于获取凭证...")
        return self._internal_get_credentials("validation_test", action_id) is not None

    def _validate_intermediate_id(self, action_id: str, test_hash: str, test_sha: str) -> bool:
        # print(f"    -> 测试ID '{action_id[:10]}...' 用于中间步骤...")
        response_text = self._internal_perform_intermediate_step(action_id, test_hash, test_sha,
                                                                 "fake_eid_for_validation")
        return response_text is not None and len(response_text) > 2

    def _validate_final_link_id(self, action_id: str, test_eid: str) -> bool:
        # print(f"    -> 测试ID '{action_id[:10]}...' 用于获取最终链接...")
        link_text = self._internal_get_final_link(action_id, test_eid)
        return link_text is not None and any(kw in link_text for kw in ["http", "magnet", "aliyundrive", '"url"'])

    def _extract_credentials(self, response_text: str) -> Optional[Dict[str, str]]:
        sign_match = re.search(r'"sign":"([^"]+)"', response_text)
        sha_match = re.search(r'"sha":"([a-f0-9]{64})"', response_text)
        hash_match = re.search(r'"hash","([^"]+)"', response_text)
        sign = sign_match.group(1) if sign_match else None
        sha = sha_match.group(1) if sha_match else None
        hash_val = hash_match.group(1) if hash_match else None
        if all([sign, sha, hash_val]):
            return {"sign": sign, "sha": sha, "hash": hash_val}
        return None

    def _internal_get_credentials(self, query: str, action_id: str) -> Optional[Dict[str, str]]:
        payload = json.dumps([{"cat": "all", "query": query, "pageNum": 1}])
        headers = {'next-action': action_id, 'Content-Type': 'text/plain;charset=UTF-8'}
        try:
            r = self.session.post(self.BASE_URL, headers=headers, data=payload, timeout=15, verify=False)
            r.raise_for_status()
            return self._extract_credentials(r.text)
        except requests.RequestException:
            return None

    def _internal_get_search_results(self, sign: str) -> Optional[List[Dict]]:
        try:
            url = f"{self.BASE_URL}/api/search?sign={sign}"
            r = self.session.get(url, timeout=15, verify=False)
            r.raise_for_status()
            data = r.json().get('data', {})
            return data.get('hits')
        except (requests.RequestException, json.JSONDecodeError):
            return None

    def _internal_perform_intermediate_step(self, action_id: str, hash_val: str, sha_val: str, eid: str) -> Optional[
        str]:
        url = f"{self.BASE_URL}/search/{hash_val}"
        ro_tree = quote(json.dumps(["", {"children": ["search", {
            "children": [["hash", hash_val, "d"], {"children": ["__PAGE__", {}, f"/search/{hash_val}", "refresh"]}]}]},
                                    None, None, True], separators=(',', ':')))
        headers = {'next-action': action_id, 'Referer': url, 'next-router-state-tree': ro_tree}
        payload = json.dumps([{"eid": eid, "sha": sha_val, "page_num": "1"}])
        try:
            r = self.session.post(url, headers=headers, data=payload, timeout=15, verify=False)
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            return None

    def _internal_get_final_link(self, action_id: str, eid: str) -> Optional[str]:
        url = f"{self.BASE_URL}/go/{eid}"
        ro_tree = quote(json.dumps(["", {"children": ["go", {
            "children": [["eid", eid, "d"], {"children": ["__PAGE__", {}, f"/go/{eid}", "refresh"]}]}]}, None, None,
                                    True], separators=(',', ':')))
        headers = {'next-action': action_id, 'Referer': url, 'next-router-state-tree': ro_tree}
        payload = json.dumps([{"eid": eid}])
        try:
            r = self.session.post(url, headers=headers, data=payload, timeout=15, verify=False)
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            return None

    # ==========================================================================
    # 公开的搜索接口 (Public API) - 增加自动重试机制
    # ==========================================================================

    def search(self, query: str, top_n: int = 3, max_retries: int = 1) -> List[Dict[str, Any]]:
        """
        执行完整四步搜索流程，并在 Action ID 失效时自动刷新并重试。
        """
        for attempt in range(max_retries + 1):
            if not all(key in self.action_ids for key in self.ID_KEYS):
                print("[x] 错误：Action ID 配置不完整，无法执行搜索。")
                if attempt < max_retries:
                    self._force_refresh_ids()
                    continue
                return []

            print(f"\n--- (第 {attempt + 1} 次尝试) 开始搜索关键词: '{query}' ---")

            # 1. 获取凭证
            creds = self._internal_get_credentials(query, self.action_ids[self.ID_KEYS[0]])
            if not creds:
                print("[!] 警告: 未能获取搜索凭证。这可能是由于 Action ID 已失效。")
                if attempt < max_retries:
                    self._force_refresh_ids()
                    continue  # 进入下一次重试循环
                else:
                    print("[x] 失败: 重试后仍无法获取搜索凭证。")
                    return []

            # 2. 获取结果列表
            hits = self._internal_get_search_results(creds['sign'])
            if not hits:
                print("[x] 结果: 未找到与关键词相关的任何结果。")
                return []  # 这是正常情况，非错误，直接返回

            print(f"[*] 找到 {len(hits)} 条相关结果。正在处理前 {min(top_n, len(hits))} 条...")
            final_results = []
            all_successful = True
            for item in hits[:top_n]:
                eid, desc = item.get('eid'), item.get('desc', 'N/A')
                if not eid: continue

                print(f"    -> 正在为 '{desc[:40].strip()}...' (eid: {eid[:10]}...) 获取链接")

                # 3. 中间步骤 & 4. 最终链接
                self._internal_perform_intermediate_step(self.action_ids[self.ID_KEYS[1]], creds['hash'], creds['sha'],
                                                         eid)
                link_text = self._internal_get_final_link(self.action_ids[self.ID_KEYS[2]], eid)

                final_link = None
                if link_text:
                    try:
                        link_data = json.loads(link_text.splitlines()[-1])
                        if isinstance(link_data, list) and len(link_data) > 1 and isinstance(link_data[1], dict) and \
                                link_data[1].get('url'):
                            final_link = link_data[1]['url']
                    except (json.JSONDecodeError, IndexError, TypeError):
                        url_match = re.search(r'(https?://[^\s"\'<>]+|magnet:\?[^\s"\'<>]+)', link_text)
                        if url_match: final_link = url_match.group(0)

                if final_link:
                    print(f"    -> [成功] 链接: {final_link[:80]}...")
                    final_results.append({"title": desc, "size": item.get('size_str', 'N/A'), "link": final_link})
                else:
                    print(f"    -> [失败] 未能获取该条目的有效链接。")
                    all_successful = False

            # 如果所有步骤都顺利，即使部分链接获取失败，也视为成功并返回结果
            if all_successful or len(final_results) > 0:
                return final_results
            # 如果所有结果都获取链接失败，可能意味着后续 ID 失效，触发重试
            else:
                print("[!] 警告: 所有条目的链接都获取失败，可能中间或最终Action ID已失效。")
                if attempt < max_retries:
                    self._force_refresh_ids()
                    continue
                else:
                    print("[x] 失败: 重试后仍然无法获取任何链接。")
                    return []

        return []  # 所有重试都失败后返回空列表


# ==========================================================================
# 程序主入口 (已移除交互)
# ==========================================================================

if __name__ == "__main__":
    try:
        # 实例化过程会自动处理配置加载或创建
        searcher = PanyqSearcher()

        search_keyword = "瑞克和莫蒂"
        # search方法现在会自动处理ID失效和重试
        results = searcher.search(search_keyword, top_n=3)

        if results:
            print(f"\n✅ === '{search_keyword}' 的最终搜索结果 === ✅")
            for i, res in enumerate(results, 1):
                print(
                    f"--- 结果 {i} ---\n  标题: {res['title']}\n  大小: {res['size']}\n  链接: {res['link']}\n" + "-" * 15)
        else:
            print(f"\n❌ 未能为 '{search_keyword}' 找到任何可用的下载链接。")

    except RuntimeError as e:
        print(f"\n[程序终止] 发生严重错误: {e}")
    except KeyboardInterrupt:
        print("\n[程序终止] 用户手动中断。")
    except Exception as e:
        print(f"\n[程序终止] 发生未知错误: {e}")
