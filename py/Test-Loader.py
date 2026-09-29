# -*- coding: utf-8 -*-
# No Chinese inside file - ASCII only test
try:
    from base.spider import Spider as BaseSpider
except:
    class BaseSpider:
        pass

class Spider(BaseSpider):
    def getName(self):
        return "TestLoader"

    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        return {
            "class": [{"type_name": "Test", "type_id": "1"}],
            "list": [
                {
                    "vod_id": "test1",
                    "vod_name": "TEST ITEM 1 - If you see this, loader works",
                    "vod_pic": "",
                    "vod_remarks": "OK"
                }
            ],
            "filters": {}
        }

    def categoryContent(self, tid, pg, filter, extend):
        return self.homeContent(filter)

    def detailContent(self, array):
        return {
            "list": [{
                "vod_id": array[0],
                "vod_name": "Test Detail",
                "vod_pic": "",
                "vod_remarks": "Detail OK",
                "vod_content": "This is detail content"
            }]
        }

    def searchContent(self, key, quick):
        return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": "", "header": {}, "msg": "Player OK: " + str(id)}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass
