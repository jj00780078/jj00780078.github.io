/*
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '黄剧',
  lang: 'cat'
})
*/

// ============================================================
// 黄剧  huangju.net
// 修复重点：播放 403
//   /play/{id} 接口在返回 body 的同时，用 Set-Cookie 下发 3 个
//   CloudFront 签名凭证(CloudFront-Policy / -Signature / -Key-Pair-Id)。
//   播放器必须带着这 3 个 cookie 去请求 m3u8，否则 CloudFront 直接 403
//   (报错 MissingKey)。原版只取了 body 里的 url，cookie 全丢，所以播放 403。
// ============================================================

const DEFAULT_HOST = 'https://huangju.net';
const DEFAULT_API = 'https://api.huangju.net';
const UA = 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36';
const COOKIE_KEYS = ['CloudFront-Policy', 'CloudFront-Signature', 'CloudFront-Key-Pair-Id'];

let _token = '';
let _deviceId = '';
let _ext = {};

function mylog() {
    try {
        if (typeof console !== 'undefined' && console.log) {
            console.log.apply(console, ['[黄剧]'].concat(Array.prototype.slice.call(arguments)));
        }
    } catch (e) { /* ignore */ }
}

function safeJsonParse(json) {
    try {
        return typeof json === 'string' ? JSON.parse(json) : json;
    } catch (e) {
        return null;
    }
}

function str(v) {
    return (v === null || v === undefined) ? '' : String(v);
}

// ---------- 站点地址（支持 ext 换域名，不改代码） ----------
function normHost(s) {
    s = str(s).trim();
    if (!s) return '';
    if (!/^https?:\/\//i.test(s)) s = 'https://' + s;
    return s.replace(/\/+$/, '').replace(/\/(home|index\.html)$/i, '');
}

function siteHost() {
    const h = normHost(_ext.site || _ext.host || _ext.domain);
    return h || DEFAULT_HOST;
}

function siteApi() {
    const a = normHost(_ext.api);
    if (a) return a;
    try {
        const d = siteHost().replace(/^https?:\/\//i, '').split('/')[0].replace(/^www\./i, '');
        return 'https://api.' + d;
    } catch (e) {
        return DEFAULT_API;
    }
}

function baseHeaders() {
    return {
        'User-Agent': UA,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': siteHost() + '/',
        'Origin': siteHost()
    };
}

// ---------- token ----------
function genDeviceId() {
    const s = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx';
    return s.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

async function getToken(force) {
    if (_token && !force) return _token;
    if (force) _token = '';
    if (!_deviceId) _deviceId = genDeviceId();
    const url = siteApi() + '/auth/guest';
    const header = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Referer': siteHost() + '/',
        'Origin': siteHost()
    };
    const tries = [
        { method: 'post', headers: header, body: JSON.stringify({ deviceId: _deviceId }), postType: 'json' },
        { method: 'post', headers: header, data: { deviceId: _deviceId }, postType: 'json' }
    ];
    for (let i = 0; i < tries.length; i++) {
        try {
            const res = await req(url, Object.assign({ timeout: 15000 }, tries[i]));
            const data = safeJsonParse(res && res.content);
            const tk = data && (data.token || (data.data && data.data.token));
            if (tk) {
                _token = tk;
                mylog('token ok');
                return _token;
            }
            mylog('token fail', res && res.content);
        } catch (e) {
            mylog('token err', e.message);
        }
    }
    return _token;
}

// 带鉴权的请求；401/403 或异常时自动清 token 重试一次
async function apiReq(url, opt) {
    opt = opt || {};
    for (let attempt = 0; attempt < 2; attempt++) {
        const tk = await getToken(attempt > 0);
        const headers = Object.assign(baseHeaders(), opt.headers || {});
        if (tk && opt.auth !== false) headers['Authorization'] = 'Bearer ' + tk;
        try {
            const res = await req(url, {
                method: opt.method || 'get',
                headers: headers,
                timeout: opt.timeout || 15000
            });
            const st = res && (res.status || res.code);
            if ((st === 401 || st === 403) && attempt === 0 && opt.auth !== false) {
                mylog('auth retry', st, url);
                _token = '';
                continue;
            }
            return res;
        } catch (e) {
            if (attempt === 0 && opt.auth !== false) {
                mylog('retry after err', e.message);
                _token = '';
                continue;
            }
            mylog('apiReq err', url, e.message);
            return null;
        }
    }
    return null;
}

async function apiJson(url, opt) {
    const res = await apiReq(url, opt);
    if (!res) return null;
    return safeJsonParse(res.content);
}

// ---------- 响应头 -> 文本（兼容各种返回形态） ----------
function headersToText(h) {
    if (!h) return '';
    try {
        if (typeof h === 'string') return h;
        const tag = Object.prototype.toString.call(h);
        if (tag === '[object Map]' || (typeof h.forEach === 'function' && typeof h.get === 'function')) {
            let out = '';
            h.forEach(function (v, k) {
                out += headerLine(k, v);
            });
            return out;
        }
        if (Array.isArray(h)) {
            let out = '';
            for (let i = 0; i < h.length; i++) {
                const it = h[i];
                if (!it) continue;
                if (typeof it === 'string') { out += it + '\n'; continue; }
                if (Array.isArray(it)) { out += headerLine(it[0], it[1]); continue; }
                out += headerLine(it.name || it.key, it.value || it.val);
            }
            return out;
        }
        if (typeof h === 'object') {
            let out = '';
            const keys = Object.keys(h);
            for (let i = 0; i < keys.length; i++) {
                out += headerLine(keys[i], h[keys[i]]);
            }
            return out;
        }
    } catch (e) { /* ignore */ }
    return '';
}

function headerLine(k, v) {
    if (v === null || v === undefined) return '';
    if (Array.isArray(v)) {
        let s = '';
        for (let i = 0; i < v.length; i++) s += str(k) + ': ' + str(v[i]) + '\n';
        return s;
    }
    return str(k) + ': ' + str(v) + '\n';
}

// 把响应里所有可能藏 set-cookie 的地方都翻出来
function dumpHeaders(res) {
    if (!res) return '';
    let text = '';
    text += headersToText(res.headers);
    text += headersToText(res.header);
    text += headersToText(res.headersText);
    text += headersToText(res['set-cookie']);
    text += headersToText(res['Set-Cookie']);
    text += headersToText(res.cookie);
    return text;
}

// 从文本里抠出 CloudFront 签名三件套
function pickSignedCookies(text) {
    const out = {};
    if (!text) return out;
    const re = /CloudFront-(Policy|Signature|Key-Pair-Id)\s*[=:]\s*([^;,\s"']+)/g;
    let m;
    while ((m = re.exec(text)) !== null) {
        out['CloudFront-' + m[1]] = m[2];
    }
    return out;
}

function cookiesComplete(c) {
    for (let i = 0; i < COOKIE_KEYS.length; i++) {
        if (!c || !c[COOKIE_KEYS[i]]) return false;
    }
    return true;
}

function cookieString(c) {
    const parts = [];
    for (let i = 0; i < COOKIE_KEYS.length; i++) {
        if (c && c[COOKIE_KEYS[i]]) parts.push(COOKIE_KEYS[i] + '=' + c[COOKIE_KEYS[i]]);
    }
    return parts.join('; ');
}

function absUrl(u) {
    u = str(u);
    if (!u) return '';
    if (/^https?:\/\//i.test(u)) return u;
    if (u.charAt(0) === '/') return siteHost() + u;
    return siteHost() + '/' + u;
}

// ---------- 列表/详情 ----------
function fmtItem(it) {
    const total = it.totalEpisodes || 0;
    const remarks = [];
    if (total) remarks.push('共' + total + '集');
    if (it.status === 'completed') remarks.push('完结');
    else if (it.status === 'ongoing') remarks.push('更新中');
    if (it.score) remarks.push('评分' + it.score);
    return {
        vod_id: str(it.slug) + '-' + it.id,
        vod_name: str(it.title),
        vod_pic: absUrl(it.coverUrl),
        vod_remarks: remarks.join(' · ')
    };
}

function pageCountOf(data, page, size) {
    const total = data && data.total ? parseInt(data.total) : 0;
    const ps = (data && data.pageSize) ? parseInt(data.pageSize) : (size || 20);
    if (total && ps) return Math.ceil(total / ps);
    return page || 1;
}

async function init(cfg) {
    try {
        let ext = cfg && (cfg.ext || cfg) ? (cfg.ext || cfg) : {};
        if (typeof ext === 'string') {
            ext = safeJsonParse(ext) || {};
        }
        _ext = ext && typeof ext === 'object' ? ext : {};
    } catch (e) {
        _ext = {};
    }
    mylog('init', siteHost(), siteApi(), JSON.stringify(_ext));
}

async function home(filter) {
    let classList = [{ type_id: 'hot', type_pid: 0, type_name: '热门' }];
    const cats = await apiJson(siteApi() + '/categories');
    if (Array.isArray(cats)) {
        cats.forEach(function (c) {
            if (!c || !c.slug) return;
            if (c.slug === 'hot') return;
            classList.push({ type_id: c.slug, type_pid: 0, type_name: c.name || c.slug });
        });
    } else {
        mylog('home: categories empty, fallback');
        classList = classList.concat([
            { type_id: 'adult', type_pid: 0, type_name: '成人' },
            { type_id: 'urban', type_pid: 0, type_name: '都市' },
            { type_id: 'qing-chun', type_pid: 0, type_name: '青春' },
            { type_id: 'chuan-yue', type_pid: 0, type_name: '穿越' }
        ]);
    }
    const sortFilter = {
        key: 'sort',
        name: '排序',
        value: [
            { n: '默认', v: '' },
            { n: '最热', v: 'hot' },
            { n: '最新', v: 'new' }
        ]
    };
    const filters = {};
    classList.forEach(function (c) {
        filters[c.type_id] = [sortFilter];
    });
    return JSON.stringify({ class: classList, filters: filters });
}

async function homeVod() {
    const data = await apiJson(siteApi() + '/dramas?page=1&sort=hot');
    return JSON.stringify({ list: ((data && data.items) || []).map(fmtItem) });
}

async function category(tid, pg, filter, extend) {
    const page = pg ? parseInt(pg) : 1;
    const sort = (extend && extend.sort) ? extend.sort : '';
    let url;
    if (!tid || tid === 'hot') {
        url = siteApi() + '/dramas?page=' + page + '&sort=' + (sort || 'hot');
    } else {
        url = siteApi() + '/dramas?page=' + page + '&category=' + encodeURIComponent(tid);
        if (sort) url += '&sort=' + sort;
    }
    mylog('category', url);
    const data = await apiJson(url);
    const list = ((data && data.items) || []).map(fmtItem);
    return JSON.stringify({
        list: list,
        page: page,
        limit: 20,
        total: (data && data.total) || list.length,
        pagecount: pageCountOf(data, page, 20)
    });
}

async function detail(id) {
    const it = await apiJson(siteApi() + '/dramas/' + encodeURIComponent(id));
    if (!it || !it.id) {
        mylog('detail empty', id);
        return JSON.stringify({ list: [] });
    }
    const eps = (it.episodes || []).filter(function (e) {
        return e && e.playable !== false;
    }).sort(function (a, b) {
        return (a.epNo || 0) - (b.epNo || 0);
    });
    const playArr = eps.map(function (e, i) {
        const no = e.epNo || (i + 1);
        return '第' + no + '集$' + e.id;
    });
    const remarks = [];
    if (it.totalEpisodes) remarks.push('共' + it.totalEpisodes + '集');
    if (it.status === 'completed') remarks.push('完结');
    else if (it.status === 'ongoing') remarks.push('更新中');
    const vod = {
        vod_id: id,
        vod_name: str(it.title),
        vod_pic: absUrl(it.coverUrl),
        type_name: str(it.region || ''),
        vod_year: str(it.year),
        vod_area: str(it.region),
        vod_lang: '',
        vod_score: it.score ? str(it.score) : '',
        vod_remarks: remarks.join(' · '),
        vod_content: str(it.description),
        vod_play_from: '黄剧',
        vod_play_url: playArr.join('#')
    };
    return JSON.stringify({ list: [vod] });
}

async function search(wd, quick, pg) {
    const page = pg ? parseInt(pg) : 1;
    const url = siteApi() + '/dramas?page=' + page + '&q=' + encodeURIComponent(wd);
    mylog('search', url);
    const data = await apiJson(url);
    let list = ((data && data.items) || []).map(fmtItem);
    let pc = pageCountOf(data, page, 20);
    if (quick && page === 1) {
        const cap = (parseInt(quick) > 0) ? parseInt(quick) : 20;
        if (list.length > cap) pc = 1;
        list = list.slice(0, cap);
    }
    return JSON.stringify({ list: list, pagecount: pc });
}

// ---------- 播放（核心修复） ----------
function isDirectVideoUrl(url) {
    const s = str(url);
    return s.indexOf('m3u') >= 0 || s.indexOf('mp4') >= 0;
}

async function buildPlayHeaders(epId) {
    const url = siteApi() + '/play/' + encodeURIComponent(epId);
    const header = baseHeaders();

    // 1) 常规请求（带鉴权），从响应头里抠签名 cookie
    for (let round = 0; round < 3; round++) {
        let res = null;
        try {
            if (round === 2) {
                // 第三轮：不带鉴权再试（部分情况下游客 token 反而多余）
                res = await req(url, { method: 'get', headers: baseHeaders(), timeout: 15000 });
            } else {
                if (round === 1) await getToken(true);
                const tk = await getToken(round === 1);
                const h = Object.assign({}, header);
                if (tk) h['Authorization'] = 'Bearer ' + tk;
                res = await req(url, { method: 'get', headers: h, timeout: 15000 });
            }
        } catch (e) {
            mylog('play req err', round, e.message);
            continue;
        }
        const data = safeJsonParse(res && res.content);
        const cookies = pickSignedCookies(dumpHeaders(res));
        mylog('play round', round, 'cookie', cookiesComplete(cookies) ? '3/3' : Object.keys(cookies).length + '/3');
        if (data && data.url) {
            return { url: data.url, cookies: cookies, expiresAt: data.expiresAt };
        }
    }
    return null;
}

async function play(flag, id, flags) {
    mylog('play start', id);
    try {
        if (isDirectVideoUrl(id)) {
            return JSON.stringify({ parse: 0, url: id });
        }
        const info = await buildPlayHeaders(id);
        if (!info || !info.url) {
            return JSON.stringify({ parse: 0, url: '', msg: '获取播放链接失败' });
        }
        let url = info.url;

        // 播放器请求头：CloudFront 签名 cookie 必须带上（m3u8 里的分片是相对
        // 路径，播放器解析时不会继承 URL 参数，所以只能靠 Cookie 头往下传）
        const header = {
            'User-Agent': UA,
            'Referer': siteHost() + '/',
            'Origin': siteHost()
        };
        const ck = cookieString(info.cookies);
        if (ck) {
            header['Cookie'] = ck;
        } else {
            // 兜底：签名参数拼到 URL 上（至少主清单能过）
            if (info.cookies && info.cookies['CloudFront-Policy']) {
                url += (url.indexOf('?') >= 0 ? '&' : '?') +
                    'Policy=' + encodeURIComponent(info.cookies['CloudFront-Policy']) +
                    '&Signature=' + encodeURIComponent(info.cookies['CloudFront-Signature']) +
                    '&Key-Pair-Id=' + encodeURIComponent(info.cookies['CloudFront-Key-Pair-Id']);
            }
            mylog('play: cookie missing, url-sign mode');
        }
        mylog('play ok', url);
        return JSON.stringify({
            parse: 0,
            url: url,
            header: header,
            headers: header
        });
    } catch (e) {
        mylog('play fail', e.message);
        return JSON.stringify({ parse: 0, url: '', msg: e.message });
    }
}

export default {
    init,
    home,
    homeVod,
    category,
    detail,
    search,
    play
};
