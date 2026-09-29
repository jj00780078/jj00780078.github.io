#!/usr/bin/python
# -*- coding: utf-8 -*-
import re, json, base64, requests
from urllib.parse import quote
from base.spider import Spider

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

class Spider(Spider):
    def getName(self): return "观影"
    def init(self, extend=""):
        self.host="https://www.xn--10vr61a3xc5x3b.com"
        self.img="https://s.tutu.pm/img"
        self.cookie=""
        self.ua="Mozilla/5.0 (Linux; Android 16; Pixel 9 Pro Build/BP1A.250305.019) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7743.101 Mobile Safari/537.36"
        self.classes={"mv":"电影","tv":"剧集","ac":"动漫"}
        self.session=requests.Session()
        self.session.verify=False
        self.session.headers.update({"User-Agent":self.ua,"Accept":"*/*","Referer":self.host+"/","X-Requested-With":"XMLHttpRequest","Accept-Language":"zh-CN,zh;q=0.9"})
        if extend:
            try: self.cookie=json.loads(extend).get("cookie","")
            except Exception: self.cookie=extend
        if self.cookie:
            self.session.headers.update({"Cookie":self.cookie})
            for x in self.cookie.split(";"):
                if "=" in x:
                    k,v=x.strip().split("=",1)
                    self.session.cookies.set(k,v,domain="www.xn--10vr61a3xc5x3b.com",path="/")
        self._pow()
    def destroy(self):
        try: self.session.close()
        except Exception: return None
    def _pow(self):
        try:
            r=self.session.get(self.host,timeout=15)
            if "powSolve" not in r.text: return True
            d=self.session.get(self.host+"/res/pow",timeout=15).json()
            if "N" not in d: return False
            n=int(d["N"],16); y=int(d["x"],16)
            for i in range(int(d["t"])): y=(y*y)%n
            return self.session.post(self.host+"/res/pow",data={"y":format(y,"x")},timeout=20).json().get("success")
        except Exception:
            return False
    def _get(self,u,ref=""):
        try:
            url=self.host+u if u.startswith("/") else u
            r=self.session.get(url,headers={"Referer":ref or self.host+"/","User-Agent":self.ua,"Accept":"*/*","X-Requested-With":"XMLHttpRequest"},timeout=20)
            r.encoding=r.apparent_encoding or "utf-8"
            if "powSolve" in r.text or '"refresh":1' in r.text:
                self._pow()
                r=self.session.get(url,headers={"Referer":ref or self.host+"/","User-Agent":self.ua,"Accept":"*/*","X-Requested-With":"XMLHttpRequest"},timeout=20)
                r.encoding=r.apparent_encoding or "utf-8"
            return r.text
        except Exception:
            return ""
    def _json_get(self,u,ref=""):
        try: return json.loads(self._get(u,ref))
        except Exception: return {}
    def _b64e(self,o):
        s=o if isinstance(o,str) else json.dumps(o,ensure_ascii=False,separators=(",",":"))
        return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
    def _b64d(self,s):
        try: return json.loads(base64.urlsafe_b64decode((s+"="*(-len(s)%4)).encode()).decode())
        except Exception:
            try: return base64.urlsafe_b64decode((s+"="*(-len(s)%4)).encode()).decode()
            except Exception: return s
    def _obj(self,h,k):
        p="_obj."+k
        i=h.find(p)
        if i<0: return None
        i=h.find("=",i)
        if i<0: return None
        i+=1
        while i<len(h) and h[i].isspace(): i+=1
        if i>=len(h) or h[i] not in "[{": return None
        q=h[i]; end={"{":"}","[":"]"}[q]; deep=0; ins=False; esc=False; out=[]
        for c in h[i:]:
            out.append(c)
            if esc:
                esc=False
                continue
            if c=="\\":
                esc=True
                continue
            if c=='"':
                ins=not ins
                continue
            if ins: continue
            if c==q: deep+=1
            elif c==end:
                deep-=1
                if deep==0: break
        s="".join(out).replace("\\/","/").replace("\\'","'")
        try: return json.loads(s)
        except Exception:
            s=re.sub(r",\s*([}\]])",r"\1",s)
            try: return json.loads(s)
            except Exception: return None
    def _pic(self,d,i): return f"{self.img}/{d}/{i}/256.webp" if d and i else ""
    def _vod(self,name,i,d,remarks="",extra=None):
        item={"title":name or "未知","id":str(i or ""),"dir":str(d or ""),"remarks":str(remarks or "")}
        if isinstance(extra,dict): item.update(extra)
        return {"vod_id":self._b64e(item),"vod_name":item["title"],"vod_pic":self._pic(item["dir"],item["id"]),"vod_remarks":item["remarks"]}
    def _list_from_inlist(self,x):
        if not x: return []
        arr=[]
        if isinstance(x,list):
            for block in x: arr+=self._list_from_inlist(block)
            return arr
        ts=x.get("t",[]); ids=x.get("i",[]); ty=x.get("ty",""); gs=x.get("g",[]); qs=x.get("q",[])
        for n,name in enumerate(ts):
            i=ids[n] if n<len(ids) else ""
            r=gs[n] if n<len(gs) else ""
            q=" ".join(qs[n]) if n<len(qs) and isinstance(qs[n],list) else ""
            arr.append(self._vod(name,i,ty,(r+" "+q).strip()))
        return arr
    def _list_from_search(self,x):
        if not x or not isinstance(x,dict): return []
        l=x.get("l",{}); titles=l.get("title",[]) or l.get("t",[]); ids=l.get("i",[]) or l.get("id",[]); ds=l.get("d",[]) or l.get("dir",[]); years=l.get("year",[])
        return [self._vod(titles[i],ids[i] if i<len(ids) else "",ds[i] if i<len(ds) else "mv",years[i] if i<len(years) else "") for i in range(len(titles))]
    def _suggest_items(self,tid="",page=1):
        kws={"mv":["2025","电影","最新电影","人生"],"tv":["剧集","2025","黑袍","庆余年"],"ac":["动漫","星辰变","斗罗","瑞克"],"":["2025","星辰变","黑袍","人生"]}.get(str(tid),[str(tid)])
        arr=[]; seen=set()
        for kw in kws:
            d=self._json_get("/res/search_suggest?q="+quote(kw))
            if not isinstance(d,list): continue
            for v in d:
                dr=str(v.get("dir","mv"))
                if tid and dr!=str(tid): continue
                key=dr+str(v.get("id",""))
                if key in seen: continue
                seen.add(key); arr.append(self._vod(v.get("title",""),v.get("id",""),dr,v.get("year",""),v))
            if len(arr)>=24: break
        return arr
    def homeContent(self,filter):
        h=self._get("/")
        items=self._list_from_inlist(self._obj(h,"inlist"))[:24]
        if not items: items=self._suggest_items("")[:24]
        return {"class":[{"type_id":k,"type_name":v} for k,v in self.classes.items()],"list":items,"filters":{}}
    def homeVideoContent(self):
        h=self._get("/")
        items=self._list_from_inlist(self._obj(h,"inlist"))[:24]
        if not items: items=self._suggest_items("")[:24]
        return {"list":items}
    def categoryContent(self,tid,pg,filter,extend):
        tid=str(tid); page=int(pg) if str(pg).isdigit() else 1
        if tid not in self.classes: return {"list":[],"page":page,"pagecount":1,"limit":30,"total":0}
        if page==1:
            h=self._get("/"+tid)
            items=self._list_from_inlist(self._obj(h,"inlist"))
            if not items: items=self._suggest_items(tid,page)
            p=self._obj(h,"page") or {}
            return {"list":items,"page":page,"pagecount":int(p.get("pages",100) or 100),"limit":60,"total":int(p.get("pages",100) or 100)*60}
        d=self._json_get(f"/res/change/{tid}/{page}",self.host+"/"+tid)
        items=self._list_from_inlist(d)
        if not items: items=self._suggest_items(tid,page)
        return {"list":items,"page":page,"pagecount":100,"limit":12,"total":1200}
    def searchContent(self,key,quick,pg="1"):
        page=int(pg) if str(pg).isdigit() else 1
        if not key: return {"list":[],"page":page,"pagecount":1,"limit":30,"total":0}
        h=self._get("/search?q="+quote(key)+(f"&p={page}" if page>1 else ""))
        x=self._obj(h,"search"); p=self._obj(h,"page") or {}; items=self._list_from_search(x)
        if not items:
            d=self._json_get("/res/search_suggest?q="+quote(key))
            items=[self._vod(v.get("title",""),v.get("id",""),v.get("dir","mv"),v.get("year",""),v) for v in d] if isinstance(d,list) else []
        return {"list":items,"page":page,"pagecount":int(p.get("pages",1) or 1),"limit":30,"total":len(items)}
    def detailContent(self,ids):
        item=self._b64d(ids[0])
        if not isinstance(item,dict): return {"list":[]}
        dr=item.get("dir","mv"); vid=item.get("id",""); h=self._get(f"/{dr}/{vid}")
        d=self._obj(h,"d") or item
        down=self._json_get(f"/res/downurl/{dr}/{vid}",self.host+f"/{dr}/{vid}")
        pf,pu=[],[]
        pan=down.get("panlist",{}) if isinstance(down,dict) else {}
        if pan.get("id"):
            groups={}; tnames=pan.get("tname",[])
            for i,u in enumerate(pan.get("url",[])):
                if not u: continue
                tp=pan.get("type",[0])[i] if i<len(pan.get("type",[])) else 0
                name=tnames[tp] if isinstance(tp,int) and tp<len(tnames) else "网盘"
                title=pan.get("name",["网盘链接"])[i] if i<len(pan.get("name",[])) else "网盘链接"
                pwd=pan.get("p",[""])[i] if i<len(pan.get("p",[])) else ""
                if pwd and "pwd=" not in u: u+=("&" if "?" in u else "?")+"pwd="+pwd
                groups.setdefault(name,["点击选择$noop"]).append(title.replace("#","＃").replace("$","￥")+"$"+self._b64e(u.replace("\\/","/")))
            for k,v in groups.items(): pf.append(k); pu.append("#".join(v))
        dl=down.get("downlist",{}).get("list",{}) if isinstance(down,dict) else {}
        if dl.get("m"):
            eps=["点击选择$noop"]
            for i,m in enumerate(dl.get("m",[])[:30]):
                title=dl.get("t",["磁力"])[i] if i<len(dl.get("t",[])) else "磁力"
                eps.append(title.replace("#","＃").replace("$","￥")+"$"+self._b64e("magnet:?xt=urn:btih:"+m+"&dn="+quote(title)))
            pf.append("磁力"); pu.append("#".join(eps))
        pl=down.get("playlist",[]) if isinstance(down,dict) else []
        for line in pl:
            if not isinstance(line,dict): continue
            eps=["点击选择$noop"]+[str(n)+"$"+self._b64e("py://"+line.get("i","")+"/"+str(idx+1)) for idx,n in enumerate(line.get("list",[]))]
            if len(eps)>1: pf.append(line.get("t","在线")); pu.append("#".join(eps))
        return {"list":[{"vod_id":ids[0],"vod_name":d.get("title",item.get("title","")),"vod_pic":self._pic(dr,vid),"vod_year":str(d.get("year","")),"vod_area":" / ".join(d.get("diqu",[])) if isinstance(d.get("diqu"),list) else "","vod_actor":" / ".join(d.get("zhuyan",[])) if isinstance(d.get("zhuyan"),list) else "","vod_content":d.get("summary",""),"vod_remarks":d.get("status","").replace("<em>","").replace("</em>",""),"vod_play_from":"$$$".join(pf) if pf else "暂无播放源","vod_play_url":"$$$".join(pu)}]}
    def playerContent(self,flag,id,vipFlags):
        if not id or id=="noop": return {"parse":1,"jx":0,"url":""}
        u=self._b64d(id)
        if isinstance(u,dict): u=u.get("url","")
        if isinstance(u,str) and u.startswith("py://"):
            a=u.replace("py://","").split("/")
            return {"parse":1,"jx":0,"url":self.host+"/py/"+a[0]+"/"+a[1] if len(a)>=2 else ""}
        if isinstance(u,str) and u.startswith("http"): return {"parse":0,"jx":0,"url":u if u.startswith("push://") else "push://"+u}
        if isinstance(u,str) and (u.startswith("magnet:") or u.startswith("ed2k://")): return {"parse":0,"jx":0,"url":u}
        return {"parse":0,"jx":0,"url":""}
