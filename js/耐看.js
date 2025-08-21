import "assets://js/lib/crypto-js.js";

async function init(cfg) {
cfg.skey = '';
cfg.stype = '3';
}

let host = 'https://nkvod.com'

async function request(reqUrl) {
  const res = await req(reqUrl, {
    method: 'get',
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36 Edg/100.0.1185.29',
      'referer': host
    }
  });
  return res.content;
}

//分类
async function home (filter) {
let html = await request(host);

//一级
let classes = [{"type_id":"1","type_name":"电影"},{"type_id":"2","type_name":"电视剧"},{"type_id":"3","type_name":"综艺"},{"type_id":"4","type_name":"动漫"}]

let res = html.match(/热播[\s\S]*?<\/div>\s*<\/div>\s*<\/div>\s*<\/div>\s*<\/div>/)
let regex = /<img.*?class="lazy.*?data-src="(.*?)".*?<a.*?href="(.*?)" title="(.*?)">.*?<div.*?>(.*?)<\/div>/g;

let videos = [];
let match;

while ((match = regex.exec(res)) !== null) {
    videos.push({
      vod_id: match[2],
      vod_name: match[3],
      vod_pic: match[1], 
      vod_remarks: match[4]
    });
}

return JSON.stringify({
    class: classes,
    list: videos
});
}


//主页推荐
async function homeVod() {
}

//分类
async function category (tid, pg, filter, extend) {

let html = await request(`${host}/show/${tid}--hits------${pg}---.html`);
let res = html.match(/<div class="box-width wow fadeInUp">.*?<\/div><\/div><\/div><\/div>/)
let regex = /<a.*?class="public-list-exp".*?href="(.*?)".*?title="(.*?)">[\s\S]*?<img.*?class="lazy.*?data-src="(.*?)".*?>[\s\S]*?<div class="public-list-subtitle.*?>(.*?)<\/div>/g;

let videos = [];
let match;

while ((match = regex.exec(res)) !== null) {
    videos.push({
      vod_id: match[1],
      vod_name: match[2],
      vod_pic: match[3], 
      vod_remarks: match[4],
    });
}

  return JSON.stringify ({
    page: pg,
    pagecount: 99999,
    limit: 40,
    total: 99999,
    list: videos
  });
}

//详情
async function detail (id) {
let html = await request(`${host}${id}`);
let res = (html.match(/<i class="fa ds-dianying">.*?<li.*?<\/div><\/div><\/div><\/div>/)).join('')
//线路
let play_from = Array.from(res.matchAll(/<\/i>(.*?)<.*?>/g),match => match[1].replace(/&nbsp;/g, '')).join('$$$'); 
// 提取每个播放源对应的剧集链接
let play_url = Array.from(res.matchAll(/<ul.*?>([\s\S]*?)<\/ul>/g)) //线路列表
   .map(m => Array.from(m[1].matchAll(/<a.*?href="(.*?)">(.*?)<\/a>/g)) //剧名+地址
      .map(ep => `${ep[2]}$${ep[1]}`).join('#'))
   .join('$$$');

var vod = [{
  "vod_play_from": play_from, 
  "vod_play_url": play_url
}];  

  return JSON.stringify ({
    list: vod
  })

}


//播放
async function play (flag, id, flags) {
let html = await request(`${host}${id}`);
let url = JSON.parse(html.match(/var player_aaaa=(.*?)</)[1]).url
//
if (url.indexOf("m3u8") > -1){
return JSON.stringify ({
    parse: 0,
    url: url,
})
}else{
let html = await request(`https://op.yrmq.cn/pi.php?url=${url}`);
let aa = html.match(/getrandom\('(.*?)'/)[1]
let bb = CryptoJS.enc.Base64.parse(aa.slice(8)).toString(CryptoJS.enc.Utf8)
let cc = decodeURIComponent(bb.slice(8, -8))
return JSON.stringify ({
    parse: 0,
    url: cc,
})
}
}
//搜索
async function search (wd, quick) {

}

export function __jsEvalReturn() {
  return {
      init: init,
      home: home,
      homeVod: homeVod,
      category: category,
      detail: detail,
      play: play,
      search: search
  };
}