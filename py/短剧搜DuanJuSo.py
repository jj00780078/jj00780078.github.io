import re
import json
import base64
import requests
from urllib.parse import unquote, urlencode
from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    def getName(self):
        return "短剧搜Folder"

    def init(self, extend=""):
        requests.packages.urllib3.disable_warnings()
        self.ext={}
        if isinstance(extend,str) and extend.strip().startswith("{"):
            try:self.ext=json.loads(extend)
            except Exception:self.ext={}
        elif isinstance(extend,dict):self.ext=extend
        self.host=str(self.ext.get("host") or "https://duanjuso.online").rstrip("/")
        self.timeout=int(self.ext.get("timeout",20) or 20)
        self.page_size=int(self.ext.get("page_size",20) or 20)
        self.search_page_size=int(self.ext.get("search_page_size",20) or 20)
        self.max_search_pages=int(self.ext.get("max_search_pages",3) or 3)
        self.wait_video=self.ext.get("wait_video") or "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
        self.logo=self.host+"/favicon-96x96.png"
        self.ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        self.headers={"User-Agent":self.ua,"Accept":"application/json,text/plain,*/*","Referer":self.host+"/","Accept-Language":"zh-CN,zh;q=0.9,en;q=0.8"}
        self.session=requests.Session();self.session.trust_env=False;self.session.verify=False
        proxy=self.ext.get("site_proxy") or self.ext.get("proxy_url") or self.ext.get("proxy") or ""
        if proxy:self.session.proxies.update({"http":proxy,"https":proxy})
        self.cache={}
        self._init_check_config(self.ext)
        return {}

    def homeContent(self, filter):
        return {"class":self._classes(),"filters":{},"list":self._home_vods()}

    def homeVideoContent(self):
        return {"list":self._home_vods()}

    def categoryContent(self, tid, pg, filter, extend):
        tid=str(tid or "hot_all");page=self._page(pg)
        if tid.startswith("wp|"):
            typ,data=self._parse_id(tid)
            if typ=="title":return self._build_title_folder(data,page)
            if typ=="group":return self._build_group_page(data,page)
        if tid=="daily":return self._daily_page(page)
        if tid in ["manju_rebo","manju_xinju"]:return self._manju_page("rebo" if tid=="manju_rebo" else "xinju",page)
        if tid=="hot_new":return self._hot_page(page,"new")
        if tid.startswith("hot|"):return self._hot_page(page,tid.split("|",1)[1])
        return self._hot_page(page,"all")

    def detailContent(self, ids):
        vid=ids[0] if isinstance(ids,list) and ids else ids;vid=str(vid or "")
        if vid.startswith("wp|"):
            typ,data=self._parse_id(vid)
            if typ=="title":return self._detail_title(data)
            if typ=="pan":return self._detail_pan(data)
            if typ=="magnet":return self._detail_magnet(data)
            if typ=="ed2k":return self._detail_ed2k(data)
            if typ=="group":return {"list":[{"vod_id":vid,"vod_name":self._clean(data.get("name") or self._group_name(data.get("group"))),"vod_pic":data.get("pic") or self.logo,"vod_remarks":"目录","vod_content":"请选择目录内资源。","vod_play_from":"提示","vod_play_url":"等待视频$__WAIT__"}]}
        return {"list":[]}

    def searchContent(self, key, quick=False, pg="1"):
        return self.searchContentPage(key,quick,pg)

    def searchContentPage(self, key, quick=False, pg="1"):
        key=self._clean_key(key);page=self._page(pg)
        if not key:return {"list":[],"page":page,"pagecount":1,"limit":self.search_page_size,"total":0}
        data=self._api_search(key,page,self.search_page_size);token=data.get("token") or "";arr=[]
        for item in data.get("data",[]) or []:
            item=dict(item or {});name=self._clean(item.get("name") or key);pic=item.get("cover") or self.logo;remark=self._item_remark(item,"搜索")
            arr.append({"vod_id":self._make_id("title",{"kw":name,"name":name,"pic":pic,"remark":remark,"item":item,"token":token,"origin":"search"}),"vod_name":name,"vod_pic":pic,"vod_remarks":remark,"vod_tag":"folder"})
        return {"list":arr,"page":int(data.get("page") or page),"pagecount":int(data.get("total_pages") or 1),"limit":int(data.get("page_size") or self.search_page_size),"total":int(data.get("total") or len(arr))}

    def playerContent(self, flag, pid, vipFlags):
        flag=str(flag or "");pid=str(pid or "")
        if pid in ["__WAIT__","__ACK__","__EMPTY__"] or flag in ["0","提示"]:return self._wait()
        data=self._decode_payload(pid);url=data.get("url") if isinstance(data,dict) and data.get("url") else pid;pic=data.get("pic") or "" if isinstance(data,dict) else ""
        if str(self.ext.get("transfer","0")).lower() in ["1","true","yes","on"]:
            new_url=self._transfer(data if isinstance(data,dict) else {"url":url,"api_type":flag})
            if new_url:url=new_url
        if re.search(r"\.(m3u8|mp4|flv)(?:\?|$)",url,re.I):return {"parse":0,"playUrl":"","url":url,"header":self.headers}
        if self._normalize_magnet(url):return {"parse":0,"playUrl":"","url":self._normalize_magnet(url),"header":self.headers}
        if url.lower().startswith("ed2k://"):return {"parse":0,"playUrl":"","url":url,"header":self.headers}
        if self._is_pan_url(url) or url.startswith("http"):
            ret={"parse":0,"playUrl":"","url":url if url.startswith("push://") else "push://"+url,"header":self.headers}
            if pic:ret.update({"pic":pic,"poster":pic})
            return ret
        return {"parse":1,"playUrl":"","url":url,"header":self.headers}

    def localProxy(self, param):
        if isinstance(param,dict) and str(param.get("type","")).lower()=="img":
            url=unquote(str(param.get("url") or ""))
            try:
                r=self.session.get(url,headers=self.headers,timeout=self.timeout);b=r.content or b"";ct="image/jpeg"
                if b[:8]==b"\x89PNG\r\n\x1a\n":ct="image/png"
                elif b[:4]==b"RIFF" and b[8:12]==b"WEBP":ct="image/webp"
                return [200,ct,b]
            except Exception:return [404,"text/plain",b""]
        return None

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|avi|mkv|mov|ts)(?:\?|$)",str(url or ""),re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return ""

    def _classes(self):
        arr=[{"type_id":"hot_all","type_name":"短剧榜单"},{"type_id":"hot_new","type_name":"新剧"}]
        for g in self._hot_genres():arr.append({"type_id":"hot|"+g,"type_name":g})
        arr.extend([{"type_id":"manju_rebo","type_name":"漫剧热播榜"},{"type_id":"manju_xinju","type_name":"漫剧新剧榜"},{"type_id":"daily","type_name":"每日新增短剧"}])
        return arr

    def _home_vods(self):
        ck="home"
        if ck in self.cache:return self.cache[ck]
        vods=[]
        for x in (self._api_hot().get("data",[]) or [])[:20]:vods.append(self._hot_vod(x))
        for x in ((self._api_manju().get("data",{}) or {}).get("rebo",[]) or [])[:20]:vods.append(self._manju_vod(x,"rebo"))
        self.cache[ck]=vods
        return vods

    def _hot_genres(self):
        ck="hot_genres"
        if ck in self.cache:return self.cache[ck]
        cnt={}
        for x in self._api_hot().get("data",[]) or []:
            g=str(x.get("genre") or "").strip()
            if g:cnt[g]=cnt.get(g,0)+1
        arr=sorted(cnt.keys(),key=lambda k:(-cnt[k],k)) or ["都市爱情","女性成长","家庭伦理","古风爱情","青春","都市日常","职场婚恋","玄幻仙侠","宫斗宅斗","逆袭","剧情","古风权谋","抗战谍战","年代爱情"]
        self.cache[ck]=arr
        return arr

    def _hot_page(self,page,genre):
        data=self._api_hot().get("data",[]) or []
        if genre=="new":data=[x for x in data if x.get("is_new") is True]
        elif genre and genre!="all":data=[x for x in data if str(x.get("genre") or "")==genre]
        return self._slice([self._hot_vod(x) for x in data],page,self.page_size)

    def _manju_page(self,key,page):
        arr=((self._api_manju().get("data",{}) or {}).get(key,[]) or [])
        return self._slice([self._manju_vod(x,key) for x in arr],page,self.page_size)

    def _daily_page(self,page):
        data=self._api_daily(page);token=data.get("token") or "";arr=[]
        for item in data.get("data",[]) or []:
            item=dict(item or {});name=self._clean(item.get("name") or "短剧");remark=self._item_remark(item,"每日新增")
            arr.append({"vod_id":self._make_id("title",{"kw":name,"name":name,"pic":self.logo,"remark":remark,"item":item,"token":token,"origin":"daily"}),"vod_name":name,"vod_pic":self.logo,"vod_remarks":remark,"vod_tag":"folder"})
        return {"list":arr,"page":int(data.get("page") or page),"pagecount":int(data.get("total_pages") or 1),"limit":20,"total":int(data.get("total") or len(arr))}

    def _hot_vod(self,item):
        name=self._clean(item.get("name") or "短剧");pic=self._abs(item.get("cover") or "") or self.logo
        remark=" · ".join([x for x in ["No.%s"%item.get("rank") if item.get("rank") else "",item.get("genre") or "","新剧" if item.get("is_new") else "",item.get("tags") or ""] if x])
        return {"vod_id":self._make_id("title",{"kw":name,"name":name,"pic":pic,"remark":remark,"origin":"hot"}),"vod_name":name,"vod_pic":pic,"vod_remarks":remark,"vod_tag":"folder"}

    def _manju_vod(self,item,key="rebo"):
        name=self._clean(item.get("name") or "漫剧");pic=self._abs(item.get("cover") or "") or self.logo;typ=str(item.get("type") or "").strip()
        remark=" · ".join([x for x in ["热播榜" if key=="rebo" else "新剧榜","No.%s"%item.get("rank") if item.get("rank") else "",typ,"%s集"%item.get("episodes") if item.get("episodes") else "",item.get("heat") or ""] if x])
        return {"vod_id":self._make_id("title",{"kw":name,"name":name,"pic":pic,"remark":remark,"origin":"manju"}),"vod_name":name,"vod_pic":pic,"vod_remarks":remark,"vod_tag":"folder"}

    def _detail_title(self,data):
        name=self._clean(data.get("name") or data.get("kw") or "短剧");pic=data.get("pic") or self.logo;remark=data.get("remark") or "Folder分组";items=self._items_for_title(data)
        if not items:return {"list":[{"vod_id":self._make_id("title",data),"vod_name":name,"vod_pic":pic,"vod_remarks":"暂无网盘","vod_content":name,"vod_play_from":"提示","vod_play_url":"等待视频$__WAIT__"}]}
        groups=self._group_items(items);froms=[];urls=[]
        for g in self._group_order():
            arr=groups.get(g) or []
            if not arr:continue
            froms.append(self._group_name(g));eps=[]
            for i,item in enumerate(arr,1):eps.append("%s$%s"%(self._clean("%s-%s"%(self._group_name(g),i),80),self._payload(item)))
            urls.append("#".join(eps))
        return {"list":[{"vod_id":self._make_id("title",data),"vod_name":name,"vod_pic":pic,"vod_remarks":remark,"vod_content":"%s\n已按网盘类型分组：%s"%(name,"、".join(froms)),"vod_play_from":"$$$".join(froms),"vod_play_url":"$$$".join(urls),"vod_tag":"folder"}]}

    def _build_title_folder(self,data,page):
        name=self._clean(data.get("name") or data.get("kw") or "短剧");pic=data.get("pic") or self.logo;items=self._items_for_title(data);groups=self._group_items(items);folders=[]
        for g in self._group_order():
            arr=groups.get(g) or []
            if not arr:continue
            folders.append({"vod_id":self._make_id("group",{"kw":data.get("kw") or name,"name":name,"pic":pic,"group":g,"items":arr}),"vod_name":self._group_name(g),"vod_pic":pic,"vod_remarks":"%s条资源"%len(arr),"vod_content":"%s\n%s"%(name,self._group_name(g)),"vod_tag":"folder"})
        return {"list":folders,"page":1,"pagecount":1,"limit":len(folders),"total":len(folders)}

    def _build_group_page(self,data,page):
        group=str(data.get("group") or "");pic=data.get("pic") or self.logo;items=data.get("items") if isinstance(data.get("items"),list) else []
        if not items:items=(self._group_items(self._items_for_title(data)).get(group) or [])
        arr=self._sort_items(items);total=len(arr);pagecount=max(1,(total+self.page_size-1)//self.page_size);page=max(1,min(page,pagecount));start=(page-1)*self.page_size
        if self.check_enable:arr=self._apply_check_results(arr)
        videos=[];width=max(2,len(str(total))) if total else 2
        for idx,item in enumerate(arr[start:start+self.page_size]):
            name=self._clean(item.get("name") or data.get("name") or "资源");url=item.get("url") or "";remark=item.get("remark") or self._remark(item)
            if item.get("_check_status"):remark="%s · %s"%(item.get("_check_status"),remark)
            videos.append({"vod_id":self._make_id("pan",item),"vod_name":"%s. ⚪ %s"%(str(start+idx+1).zfill(width),name),"vod_pic":pic,"vod_remarks":remark,"vod_content":"%s\n%s"%(name,url),"vod_tag":"file"})
        return {"list":videos,"page":page,"pagecount":pagecount,"limit":self.page_size,"total":total}

    def _items_for_title(self,data):
        if isinstance(data.get("items"),list) and data.get("items"):return self._dedupe(data.get("items"))
        if isinstance(data.get("item"),dict):return self._dedupe(self._row_to_items(data.get("item"),data.get("token") or "",data.get("pic") or self.logo,data.get("origin") or ""))
        kw=self._clean_key(data.get("kw") or data.get("name"))
        if not kw:return []
        ck="items_exact|"+kw
        if ck in self.cache:return self.cache[ck]
        exact=[];loose=[];first=self._api_search(kw,1,50);pages=max(1,min(int(first.get("total_pages") or 1),self.max_search_pages));rows=list(first.get("data",[]) or [])
        for p in range(2,pages+1):rows.extend(self._api_search(kw,p,50).get("data",[]) or [])
        for item in rows:
            if self._same_title(kw,item.get("name") or item.get("name_norm") or ""):exact.extend(self._row_to_items(item,first.get("token") or "",data.get("pic") or self.logo,data.get("origin") or "search"))
            elif self._contains_title(kw,item.get("name") or item.get("name_norm") or ""):loose.extend(self._row_to_items(item,first.get("token") or "",data.get("pic") or self.logo,data.get("origin") or "search"))
        out=self._dedupe(exact if exact else loose[:4])
        if data.get("origin") in ["hot","manju"]:out=self._one_per_group(out)
        self.cache[ck]=out
        return self.cache[ck]

    def _one_per_group(self,items):
        best={}
        for item in self._sort_items(items or []):
            g=self._group_key(item.get("api_type"),item.get("url"))
            if g not in best:best[g]=item
        return [best[g] for g in self._group_order() if g in best]

    def _norm_title(self,text):
        text=str(text or "")
        text=re.sub(r"[（(][^）)]*(?:更至|更新|全|完结|集|季|版|合集)[^）)]*[）)]","",text)
        text=re.sub(r"[《》【】\[\]()（）{}<>〈〉『』「」\s·,，.。!！?？:：;；、_\-—]+","",text)
        text=re.sub(r"^(短剧|微短剧)","",text)
        return text.lower()

    def _same_title(self,a,b):
        na=self._norm_title(a);nb=self._norm_title(b)
        return bool(na and nb and na==nb)

    def _contains_title(self,a,b):
        na=self._norm_title(a);nb=self._norm_title(b)
        return bool(na and nb and (na in nb or nb in na))

    def _row_to_items(self,item,token="",pic="",origin=""):
        item=item or {};name=self._clean(item.get("name") or item.get("name_norm") or "短剧");remark=self._item_remark(item,origin);arr=[]
        for key,g in [("quark_url","quark"),("baidu_url","baidu")]:
            url=str(item.get(key) or "").strip()
            if not url:continue
            arr.append({"name":name,"url":url,"pic":pic or self.logo,"api_type":g,"token":token,"folder":name,"remark":remark,"episodes":item.get("episodes") or "","source_no":item.get("source_no") or "","id":item.get("id") or item.get("rank_no") or ""})
        return arr

    def _detail_pan(self,data):
        name=self._clean(data.get("name") or "网盘资源");url=data.get("url") or "";pic=data.get("pic") or self.logo;payload=self._payload(data)
        return {"list":[{"vod_id":"wp_pan","vod_name":name,"vod_pic":pic,"vod_remarks":self._group_name(self._group_key(data.get("api_type"),url)),"vod_content":"%s\n%s"%(name,url),"vod_play_from":"推送","vod_play_url":"自动推送$%s"%payload}]}

    def _detail_magnet(self,data):
        name=self._clean(data.get("name") or "磁力资源");url=self._normalize_magnet(data.get("url") or "");payload=self._payload({"type":"magnet","url":url,"pic":data.get("pic") or self.logo})
        return {"list":[{"vod_id":"wp_magnet","vod_name":name,"vod_pic":data.get("pic") or self.logo,"vod_remarks":"磁力推送","vod_content":"%s\n%s"%(name,url),"vod_play_from":"0$$$磁力","vod_play_url":"等待视频$__WAIT__$$$%s$%s"%(name,payload)}]}

    def _detail_ed2k(self,data):
        name=self._clean(data.get("name") or "电驴资源");url=data.get("url") or "";payload=self._payload({"type":"ed2k","url":url,"pic":data.get("pic") or self.logo})
        return {"list":[{"vod_id":"wp_ed2k","vod_name":name,"vod_pic":data.get("pic") or self.logo,"vod_remarks":"电驴推送","vod_content":"%s\n%s"%(name,url),"vod_play_from":"电驴","vod_play_url":"%s$%s"%(name,payload)}]}

    def _api(self,path):
        ck="api|"+path
        if ck in self.cache:return self.cache[ck]
        r=self.session.get(self.host+path,headers=self.headers,timeout=self.timeout,verify=False)
        if r.status_code!=200:raise Exception("HTTP %s %s"%(r.status_code,path))
        data=r.json();self.cache[ck]=data
        return data

    def _api_hot(self):return self._api("/api/hot")
    def _api_manju(self):return self._api("/api/manju")
    def _api_daily(self,page):return self._api("/api/daily_new?page=%s"%self._page(page))
    def _api_search(self,key,page=1,page_size=20):return self._api("/api/search?"+urlencode({"q":key,"page":self._page(page),"page_size":int(page_size or 20)}))

    def _transfer(self,data):
        url=data.get("url") or "";token=data.get("token") or "";name=data.get("name") or ""
        if not url or not token:return ""
        api_type=self._group_key(data.get("api_type"),url)
        path="/api/transfer_quark?"+urlencode({"url":url,"name":name,"token":token,"folder":data.get("folder") or name}) if api_type=="quark" else "/api/transfer?"+urlencode({"url":url,"name":name,"token":token}) if api_type=="baidu" else ""
        if not path:return ""
        try:
            d=self._api(path)
            return d.get("new_share_url") if d.get("success") else ""
        except Exception:return ""

    def _slice(self,arr,page,limit):
        total=len(arr);pagecount=max(1,(total+limit-1)//limit);page=max(1,min(page,pagecount));start=(page-1)*limit
        return {"list":arr[start:start+limit],"page":page,"pagecount":pagecount,"limit":limit,"total":total}

    def _item_remark(self,item,origin=""):
        parts=[]
        if origin:parts.append(str(origin))
        if item.get("episodes"):parts.append("%s集"%item.get("episodes"))
        if item.get("source_no"):parts.append("源%s"%item.get("source_no"))
        if item.get("id") or item.get("rank_no"):parts.append("ID%s"%(item.get("id") or item.get("rank_no")))
        links=[]
        if item.get("quark_url"):links.append("夸克")
        if item.get("baidu_url"):links.append("百度")
        if links:parts.append("/".join(links))
        return " · ".join([x for x in parts if x]) or "网盘资源"

    def _abs(self,url):
        u=str(url or "").strip()
        return "" if not u else u if u.startswith("http") else self.host+u

    def _clean_key(self,text):return re.sub(r"\s+"," ",str(text or "")).strip()
    def _clean(self,text,limit=160):
        text=str(text or "").replace("#","＃").replace("$","＄").replace("\r"," ").replace("\n"," ").replace("\t"," ");text=re.sub(r"\s+"," ",text).strip()
        return (text or "资源")[:limit]
    def _page(self,value):
        try:p=int(value);return p if p>0 else 1
        except Exception:return 1
    def _wait(self):return {"parse":0,"playUrl":"","url":self.wait_video,"header":self.headers}
    def _is_pan_url(self,url):return bool(re.search(r"pan\.quark\.cn|drive\.uc\.cn|aliyundrive\.com|alipan\.com|pan\.baidu\.com|115\.com|cloud\.189\.cn|caiyun\.139\.com|yun\.139\.com|123pan|123684|xunlei|pikpak",str(url or ""),re.I))
    def _group_items(self,items):
        groups={}
        for item in items or []:
            if isinstance(item,dict):groups.setdefault(self._group_key(item.get("api_type"),item.get("url")),[]).append(item)
        return groups
    def _group_key(self,api_type="",url=""):
        t=str(api_type or "").lower().strip();u=str(url or "").lower()
        if t in ["quark"] or "pan.quark.cn" in u:return "quark"
        if t in ["uc"] or "drive.uc.cn" in u:return "uc"
        if t in ["ali","aliyun","alipan"] or "aliyundrive.com" in u or "alipan.com" in u:return "aliyun"
        if t in ["baidu"] or "pan.baidu.com" in u:return "baidu"
        if t in ["115","a115"] or "115.com" in u:return "115"
        if t in ["xunlei"] or "xunlei" in u:return "xunlei"
        if t in ["123","123pan"] or "123pan" in u or "123684.com" in u:return "123"
        if t in ["tianyi","189"] or "cloud.189.cn" in u:return "tianyi"
        if t in ["mobile","139"] or "caiyun.139.com" in u or "yun.139.com" in u:return "mobile"
        if t in ["pikpak"] or "pikpak" in u:return "pikpak"
        if t in ["magnet"] or u.startswith("magnet:?"):return "magnet"
        if t in ["ed2k"] or u.startswith("ed2k://"):return "ed2k"
        return "other"
    def _group_order(self):return ["quark","baidu","uc","aliyun","115","xunlei","123","tianyi","mobile","pikpak","magnet","ed2k","other"]
    def _group_name(self,g):return {"quark":"🟢 夸克","baidu":"📘 百度","uc":"📱 UC","aliyun":"☁️ 阿里","115":"🟡 115","xunlei":"⚡ 迅雷","123":"📦 123盘","tianyi":"☎️ 天翼","mobile":"☁️ 移动云","pikpak":"📦 PikPak","magnet":"🧲 磁力","ed2k":"🔗 电驴","other":"📦 其他"}.get(str(g or ""),"📦 其他")
    def _sort_items(self,items):
        arr=list(items or []);arr.sort(key=lambda x:(self._group_order().index(self._group_key(x.get("api_type"),x.get("url"))) if self._group_key(x.get("api_type"),x.get("url")) in self._group_order() else 99,str(x.get("name") or ""),str(x.get("source_no") or "")))
        return arr
    def _remark(self,item):
        parts=[]
        if item.get("episodes"):parts.append("%s集"%item.get("episodes"))
        if item.get("source_no"):parts.append("源%s"%item.get("source_no"))
        parts.append(self._group_name(self._group_key(item.get("api_type"),item.get("url"))))
        return " · ".join([x for x in parts if x])
    def _normalize_magnet(self,url):
        url=unquote(str(url or "").strip()).replace("&amp;","&");m=re.search(r"(magnet:\?[^\s\"'<>]+)",url,re.I)
        if m:url=m.group(1)
        url=re.sub(r"\s+","",url)
        return url if url.startswith("magnet:?") and "urn:btih:" in url.lower() else ""
    def _dedupe(self,items):
        arr=[];seen=set()
        for x in items or []:
            if not isinstance(x,dict):continue
            url=str(x.get("url") or "").strip()
            if not url or url in seen:continue
            seen.add(url);arr.append(x)
        return arr
    def _make_id(self,typ,data):return "wp|%s|%s"%(typ,self._b64e(data or {}))
    def _parse_id(self,vid):
        arr=str(vid or "").split("|",2)
        return (arr[1],self._b64d(arr[2])) if len(arr)>=3 else ("",{})
    def _payload(self,data):return self._b64e(data or {})
    def _decode_payload(self,text):return self._b64d(text)
    def _b64e(self,obj):return base64.urlsafe_b64encode(json.dumps(obj,ensure_ascii=False,separators=(",",":")).encode("utf-8")).decode("utf-8").rstrip("=")
    def _b64d(self,text):
        try:
            text=str(text or "");text+="="*(-len(text)%4)
            return json.loads(base64.urlsafe_b64decode(text.encode("utf-8")).decode("utf-8"))
        except Exception:return {}
    def _init_check_config(self,ext):
        self.check_enable=str(ext.get("check_enable","0")).lower() in ["1","true","yes","on"];self.check_hide_bad=str(ext.get("check_hide_bad","0")).lower() in ["1","true","yes","on"];self.check_types=ext.get("check_types",["quark","baidu"]);self.check_timeout=int(ext.get("check_timeout",6) or 6)
    def _apply_check_results(self,items):
        arr=[]
        for item in items or []:
            g=self._group_key(item.get("api_type"),item.get("url"))
            if g not in self.check_types:item["_check_status"]="未检测";arr.append(item);continue
            ok,text=self._check_item(item);item["_check_status"]=text
            if ok or not self.check_hide_bad:arr.append(item)
        return arr
    def _check_item(self,item):
        url=str(item.get("url") or "").strip();g=self._group_key(item.get("api_type"),url)
        if not url:return False,"无链接"
        if g=="quark":return self._check_page_alive(url,["夸克网盘","分享","文件"])
        if g=="baidu":return self._check_page_alive(url,["百度网盘","pan.baidu.com","提取文件"])
        return True,"未检测"
    def _check_page_alive(self,url,good_words=None,bad_words=None):
        good_words=good_words or [];bad_words=bad_words or ["失效","不存在","已取消","违规","删除","过期","分享已失效","文件不存在"]
        try:
            r=self.session.get(url,headers=self.headers,timeout=self.check_timeout,allow_redirects=True,verify=False);html=r.text or ""
            if r.status_code in [404,410]:return False,"页面404"
            if any(x in html for x in bad_words):return False,"链接失效"
            if good_words and any(x in html for x in good_words):return True,"有效"
            if r.status_code==200:return True,"疑似有效"
            return False,"状态%s"%r.status_code
        except Exception:return False,"检测失败"
