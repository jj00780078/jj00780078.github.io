# -*- coding: utf-8 -*-
# @Author  : Doubebly (For 贾雨辰 - 支持子文件夹)
# @Time    : 2025/12/10
# @Desc    : 递归加载 /lz/json/**/*.json + /lz/wj/**/*.txt

import os
import json
import glob
import base64
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "LocalMixed"

    def init(self, extend):
        base_path = extend.strip() if extend and extend.strip() else "/storage/emulated/0/lz"
        self.json_base = os.path.join(base_path, "json")
        self.wj_base = os.path.join(base_path, "wj")

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ---------- 递归获取所有 .json 文件路径 ----------
    def _get_json_files(self):
        if not os.path.isdir(self.json_base):
            return []
        pattern = os.path.join(self.json_base, "**", "*.json")
        return glob.glob(pattern, recursive=True)

    # ---------- 递归获取所有 .txt 文件路径 ----------
    def _get_txt_files(self):
        if not os.path.isdir(self.wj_base):
            return []
        pattern = os.path.join(self.wj_base, "**", "*.txt")
        return glob.glob(pattern, recursive=True)

    # ---------- 解析 wj 的 #genre# TXT ----------
    def _parse_wj_txt(self, file_path):
        filename = os.path.basename(file_path)
        rel_path = os.path.relpath(file_path, self.wj_base)
        source_name = os.path.splitext(rel_path.replace(os.sep, "/"))[0]  # 如 "直播/央视"

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.rstrip("\r\n") for line in f.readlines()]
        except Exception:
            return None, []

        has_genre = any(",#genre#" in line for line in lines)
        categories = []
        detail_items = []

        if not has_genre:
            cat_id = base64.b64encode(f"{source_name}|默认,#genre#".encode()).decode()
            categories.append({"type_id": cat_id, "type_name": f"{source_name}（默认）"})
            play_urls = []
            count = 1
            for line in lines:
                if "," in line and "http" in line:
                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        name, url = parts[0].strip(), parts[1].strip()
                        if url:
                            play_urls.append(f"{count}、{name}${base64.b64encode(url.encode()).decode()}")
                            count += 1
            detail_items.append({
                "vod_id": cat_id,
                "vod_name": f"{source_name}（默认）",
                "vod_pic": "https://via.placeholder.com/300x400?text=Default",
                "vod_remarks": source_name,
                "vod_content": f"来自 {source_name}",
                "vod_play_from": "默认",
                "vod_play_url": "#".join(play_urls),
            })
        else:
            current_cat = None
            current_lines = []
            blocks = []

            for line in lines:
                if ",#genre#" in line:
                    if current_cat is not None:
                        blocks.append((current_cat, current_lines))
                    current_cat = line.split(",", 1)[0].strip()
                    current_lines = []
                elif current_cat is not None and line.strip() and "," in line:
                    current_lines.append(line)

            if current_cat is not None:
                blocks.append((current_cat, current_lines))

            for cat_name, cat_lines in blocks:
                display_name = f"{source_name} - {cat_name}"
                cat_id = base64.b64encode(f"{source_name}|{cat_name},#genre#".encode()).decode()
                categories.append({"type_id": cat_id, "type_name": display_name})
                play_urls = []
                count = 1
                for line in cat_lines:
                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        name, url = parts[0].strip(), parts[1].strip()
                        if url:
                            play_urls.append(f"{count}、{name}${base64.b64encode(url.encode()).decode()}")
                            count += 1
                detail_items.append({
                    "vod_id": cat_id,
                    "vod_name": display_name,
                    "vod_pic": "https://via.placeholder.com/300x400?text=" + cat_name[:10],
                    "vod_remarks": source_name,
                    "vod_content": f"来自 {source_name} 的 {cat_name}",
                    "vod_play_from": cat_name,
                    "vod_play_url": "#".join(play_urls),
                })

        return categories, detail_items

    # ---------- 加载全部数据 ----------
    def _load_all_data(self):
        all_categories = []
        all_items = []

        # --- 加载所有 json/**/*.json ---
        for file in self._get_json_files():
            try:
                rel_path = os.path.relpath(file, self.json_base)
                title = os.path.splitext(rel_path.replace(os.sep, "/"))[0]  # 保留路径结构作为分类名
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("list"), list):
                    all_categories.append({"type_id": rel_path, "type_name": title})
                    for item in data["list"]:
                        if isinstance(item, dict) and item.get("vod_id") is not None:
                            all_items.append(item)
            except Exception:
                continue

        # --- 加载所有 wj/**/*.txt ---
        for file in self._get_txt_files():
            try:
                cats, items = self._parse_wj_txt(file)
                if cats:
                    all_categories.extend(cats)
                    all_items.extend(items)
            except Exception:
                continue

        return all_categories, all_items

    # ---------- 首页 ----------
    def homeContent(self, filter):
        categories, _ = self._load_all_data()
        return {"class": categories, "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    # ---------- 分类内容 ----------
    def categoryContent(self, tid, pg, filter, ext):
        # JSON 分类：tid 是相对路径，如 "影视/电影.json"
        json_file = os.path.join(self.json_base, tid)
        if os.path.isfile(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = data.get("list", [])
            except Exception:
                items = []
        else:
            # WJ 分类：tid 是 base64 ID
            _, all_items = self._load_all_data()
            items = [item for item in all_items if str(item.get("vod_id")) == tid]

        page = int(pg) if pg.isdigit() else 1
        limit = 20
        total = len(items)
        start = (page - 1) * limit
        paginated = items[start : start + limit]
        pagecount = (total + limit - 1) // limit

        return {
            "page": page,
            "pagecount": pagecount,
            "limit": limit,
            "total": total,
            "list": paginated,
        }

    # ---------- 详情 ----------
    def detailContent(self, array):
        if not array:
            return {"list": []}
        vod_id = str(array[0])
        _, all_items = self._load_all_data()
        for item in all_items:
            if str(item.get("vod_id")) == vod_id:
                return {"list": [item]}
        return {"list": []}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        if not key:
            return {"list": []}
        _, all_items = self._load_all_data()
        key_lower = key.lower()
        matched = []
        for item in all_items:
            text = " ".join(str(item.get(k, "")) for k in ["vod_name", "vod_remarks", "vod_actor", "vod_director", "vod_content"])
            if key_lower in text.lower():
                matched.append(item)
        return {"list": matched}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        try:
            url = base64.b64decode(id).decode()
        except Exception:
            url = id
        headers = {"User-Agent": "okhttp/3.12.0"}
        return {"url": url, "header": headers, "parse": 0, "jx": 0}

    def localProxy(self, params):
        return [200, "video/MP2T", "", ""]

    def destroy(self):
        return "destroy"


if __name__ == "__main__":
    pass