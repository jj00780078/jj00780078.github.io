var rule = {
    author: '书虫/250604/第1版',
    title: '豆瓣影院',
    类型: '影视',
    //主页 网页的域名根
    host: 'https://m.hiqifu.com/',
    hostJs: ``,
    headers: {
        'User-Agen': 'Mozilla/5.0'
    },
    //不填就默认utf-8，根据网页源码所显示的格式填，根据需要可填UTF-8，GBK，GB2312
    编码: 'utf-8',
    timeout: 5000,
    //首页链接，可以是完整路径或者相对路径,用于分类获取和推荐获取
    homeUrl: '/',
    //分类链接,分类参数用fyclasss,页码用fypage，带筛选的用fyfilter，第一页无页码的用[]括起，处理方式同xbpq方式，fyfilter代表filter_url里内容
    
     
//  https://m.hiqifu.com/vod-type-id-7-pg-2.html

    url: 'https://m.hiqifu.com/vod-type-id-fyclass-pg-fypage.html',

    filter_url: '',
    detailUrl: 'https://m.hiqifu.com/vod-detail-id-fyid.html',
    //搜索链接 可以是完整路径或者相对路径,用于分类获取和推荐获取 **代表搜索词 fypage代表页数
    searchUrl: 'https://m.hiqifu.com/vod-search-pg-fypage-wd-**.html',

    //  搜索页找参数  数组标题图片副标题链接
    搜索: '*',
    //rss搜索写法
  //    searchUrl: '/rss/index.xml?wd=**&page=fypage',
    //  ajax搜索写法
//      searchUrl: '/index.php/ajax/suggest?mid=1&wd=**&page=fypage&limit=30',
      
 //     搜索: 'json:list;name;pic;en;id',  

    searchable: 1,
    quickSearch: 1,
    filterable: 1,
    limit: 10,
    double: false,
    class_name: '电影&电视剧&综艺&动漫&动作片&喜剧片&爱情片&科幻片&恐怖片&剧情片&战争片&国产剧&港台剧&日韩剧&欧美剧&海外剧&悬疑片&犯罪片&午夜剧&短剧',
    //静态分类值
    class_url: '1&2&3&4&5&6&7&8&9&10&11&12&13&14&15&16&17&18&26&27',


    filter_def: {
        
        
    },
    
    
    //推荐列表可以单独写也是几个参数，和一级列表部分参数一样的可以用*代替，不一样写不一样的，全和一级一样，可以用一个*代替
    推荐: '*',
    //推荐页的json模式
    //推荐: 'json:list;vod_name;vod_pic;vod_remarks;vod_id',
    //数组、标题、图片、副标题、链接，分类页找参数
    一级: 'li:has(.t-pic);.t-tit&&Text;img&&src;.t-fen&&Text;a&&href',


    //数组、标题、图片、副标题、链接，分类页找参数

    //一级: `js:
    //let klist=pdfa(request(input),'.vertical-box');
    // let k=[];
    //klist.forEach(it=>{
    // k.push({
    //title: pdfh(it,'.title&&Text'),
    // pic_url: !pdfh(it,'.lazyload&&data-original').startsWith('http') ? HOST + pdfh(it,'.lazyload&&data-original') : pdfh(it,'.lazyload&&data-original'),

    //desc: pdfh(it,''),
    // url: pdfh(it,'a&&href'),
    //content: ''    
    // })
    //});
    //setResult(k)
    //`,

    //普通搜索模板  搜索数组标题图片副标题链接
    //搜索: `js:

    //let klist=pdfa(request(input),'.hzixunui-vodlist__thumb');
    // let k=[];
    //klist.forEach(it=>{
    //k.push({
    //        title: pdfh(it,'a&&title'),
    //       pic_url: !pdfh(it,'a&&data-original').startsWith('http') ? HOST + pdfh(it,'a&&data-original') : pdfh(it,'a&&data-original'),
    //       desc: pdfh(it,'.text-right&&Text'),
    //        url: pdfh(it,'a&&href'),
    //        content: ''    
    //     })
    // });
    // setResult(k)
    // `,

    //rss搜索模板
    //  搜索: `js:
    //let klist=pdfa(request(input),'rss&&item');
    //   let k=[];
    //   klist.forEach(it=>{
    //    it=it.replace(/title|link|author|pubdate|description/g,'p');
    //    k.push({
    //         title: pdfh(it,'p:eq(0)&&Text'),
    //         pic_url: '',
    //       desc: pdfh(it,'p:eq(3)&&Text'),
    //         url: pdfh(it,'p:eq(1)&&Text').replace('cc','la'),    
    //      content: pdfh(it,'p:eq(4)&&Text')    
    //     })
    //     });
    // setResult(k)
    //" `,

    //详情页找参数
    //第一部分分别是对应参数式中的标题、类型、图片、备注、年份、地区、导演、主演、简介
    //第二部分分别对应参数式中的线路数组和线路标题
    //第三部分分别对应参数式中的播放数组、播放列表、播放标题、播放链接

    二级: `js:
let html = request(input);
VOD = {};
 VOD.vod_id = input;
VOD.vod_name = pdfh(html, 'h1&&Text');
 VOD.type_name = pdfh(html, 'li:contains(类型)&&Text').replace('类型：','');
 VOD.vod_pic = pd(html, 'img&&src', input);
 VOD.vod_remarks = pdfh(html, '.t-text.clearfix&&li:lt(1)&&Text');
 VOD.vod_year = pdfh(html, 'li:contains(年代)&&Text').replace('年代：','');
VOD.vod_area = pdfh(html, 'li:contains(地区)&&Text').replace('地区：','');
 
VOD.vod_director = pdfh(html, '.t_li4:contains(导演)&&Text').replace('导演：','');
 VOD.vod_actor = pdfh(html, 'li:contains(主演：)&&Text').replace('主演：','');
 VOD.vod_content = '书虫祝您观影愉快！现为您介绍剧情:' + pdfh(html, '.t-textinfo&&Text');
 
 let r_ktabs = pdfa(html,'.clickTab-hd&&a');
 let ktabs = r_ktabs.map(it => pdfh(it, 'Text'));
 VOD.vod_play_from = ktabs.join('$$$');
 

let klists = [];
 let r_plists = pdfa(html, '.t-playNumList');
 r_plists.forEach((rp) => {
     let klist = pdfa(rp, 'body&&a').reverse().map((it) => {
     return pdfh(it, 'a&&Text') + '$' + pd(it, 'a&&href', input);
     });
     klist = klist.join('#');
     klists.push(klist);
 });
 VOD.vod_play_url = klists.join('$$$')
 

 `,
    //是否启用辅助嗅探: 1,0
    sniffer: 0,
    // 辅助嗅探规则
    isVideo: 'http((?!http).){26,}\\.(m3u8|mp4|flv|avi|mkv|wmv|mpg|mpeg|mov|ts|3gp|rm|rmvb|asf|m4a|mp3|wma)',
    
    play_parse: false,
    //播放地址通用解析
    lazy: $js.toString(() => {
let kcode = JSON.parse(fetch(input).split('aaaa=')[1].split('<')[0]);
let kurl = kcode.url;
if (/\.(m3u8|mp4)/.test(kurl)) {
    input = { jx: 0, parse: 0, url: kurl, header: {'User-Agent': MOBILE_UA, 'Referer': getHome(kurl)} }
} else {
    input = { jx: 0, parse: 1, url: input }
}
}),


    
    filter: {
        "1": [
        
        
        {
                "key": "cateId",
                "name": "类型",
                "value":[
    {"n": "全部", "v": "1"},
    {"n": "短视频", "v": "36"},
    {"n": "动作片", "v": "6"},
    {"n": "喜剧片", "v": "7"},
    {"n": "爱情片", "v": "8"},
    {"n": "科幻片", "v": "9"},
    {"n": "恐怖片", "v": "10"},
    {"n": "战争片", "v": "12"}
]

},

{
                "key": "area",
                "name": "地区",
                "value":[
  {"n": "全部", "v": ""},
  {"n": "大陆", "v": "大陆"},
  {"n": "香港", "v": "香港"},
  {"n": "台湾", "v": "台湾"},
  {"n": "美国", "v": "美国"},
  {"n": "法国", "v": "法国"},
  {"n": "英国", "v": "英国"},
  {"n": "日本", "v": "日本"},
  {"n": "韩国", "v": "韩国"},
  {"n": "德国", "v": "德国"},
  {"n": "泰国", "v": "泰国"},
  {"n": "印度", "v": "印度"},
  {"n": "意大利", "v": "意大利"},
  {"n": "西班牙", "v": "西班牙"}
]
}
                ],
        "2": [
        
        {
                "key": "cateId",
                "name": "类型",
                "value":[
    {"n": "全部", "v": "2"},
    {"n": "国产剧", "v": "13"},
    {"n": "港台剧", "v": "14"},
    {"n": "韩剧", "v": "15"},
    {"n": "美剧", "v": "16"},
    {"n": "海外剧", "v": "27"},
    {"n": "日剧", "v": "26"}
]


},

{
                "key": "area",
                "name": "地区",
                "value":[
  {"n": "全部", "v": ""},
  {"n": "内地", "v": "内地"},
  {"n": "韩国", "v": "韩国"},
  {"n": "香港", "v": "香港"},
  {"n": "台湾", "v": "台湾"},
  {"n": "日本", "v": "日本"},
  {"n": "美国", "v": "美国"},
  {"n": "泰国", "v": "泰国"},
  {"n": "英国", "v": "英国"},
  {"n": "新加坡", "v": "新加坡"},
  {"n": "其他", "v": "其他"}
]
}
                       
        
        ],

"3": [
        
        
       
        {
                "key": "area",
                "name": "地区",
                "value":[
  {"n": "全部", "v": ""},
  {"n": "内地", "v": "内地"},
  {"n": "港台", "v": "港台"},
  {"n": "日韩", "v": "日韩"},
  {"n": "欧美", "v": "欧美"}
]


            }
            
        ],
        
        "4": [
        
                {
                "key": "area",
                "name": "地区",
                "value":[
  {"n": "全部", "v": ""},
  {"n": "内地", "v": "内地"},
  {"n": "港台", "v": "港台"},
  {"n": "日韩", "v": "日韩"},
  {"n": "欧美", "v": "欧美"}
]


}

            
        ]

        
    }
}