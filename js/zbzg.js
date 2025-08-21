/*
 * 脚本框架参考nox。仅作播放器功能测试，不得用于商业或非法用途，您必须在下载后24小时内，从设备中删除，否则后果自负。
 */function main(item) {
    const id = item.id || '30167';
    const cacheKey = 'zbzg_' + id;
    const cachedUrl = ku9.getCache(cacheKey);

    if (cachedUrl) {
        return { url: cachedUrl };
    }

    function getCommonHeaders() {
        const deviceId = ku9.md5(Date.now().toString()) + ku9.md5(Date.now().toString() + "salt");
        return {
            'Content-Type': 'application/json',
            'charset': 'UTF-8',
            'Accept': 'application/json',
            'channelId': 'store_samsung',
            'deviceType': '1',
            'releaseVersion': '1.2.6',
            'releaseVersionCode': '126',
            'uId': '',
            'os': 'Android',
            'User-Agent': 'okhttp/3.14.9',
            'deviceId': deviceId,
            'API-VERSION': '2',
            'orgCode': '',
            'token': ''
        };
    }

    function generateSign(input, flag) {
        const ts = Math.floor(Date.now() / 1000);
        const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
        let randStr = '';
        const randLen = Math.floor(Math.random() * 4) + 4;

        for (let i = 0; i < randLen; i++) {
            randStr += chars.charAt(Math.floor(Math.random() * chars.length));
        }

        const suffix = flag ? '01234ibcp9' : '0123456789';
        const s1 = `${input}-${ts}-${randStr}-${suffix}`;
        return `${ts}-${randStr}-${ku9.md5(s1)}`;
    }

    try {
        // 第一次POST请求
        const firstSign = generateSign('/v1/resourceProductRightsAuth', true);
        const headers1 = getCommonHeaders();
        headers1.sign = firstSign;
        headers1.Host = 'saleservice.5gtv.com.cn';

        const res1 = ku9.request(
            'https://saleservice.5gtv.com.cn/v1/resourceProductRightsAuth',
            'POST',
            headers1,
            JSON.stringify({ resId: id, resourceStreamId: id })
        );

        if (!res1 || res1.code !== 200) {
            throw new Error(`首次请求失败: ${res1 ? res1.code : '无响应'}`);
        }

        const json1 = JSON.parse(res1.body);
        if (!json1 || !json1.data || !json1.data.url) {
            throw new Error('首次API响应格式错误');
        }

        const firstUrl = json1.data.url + '&t=1&v=126';

        // 手动提取路径和查询参数 - 替代 ku9.Uri
        const urlParts = firstUrl.split('://')[1].split('/');
        const domain = urlParts[0];
        const pathAndQuery = '/' + urlParts.slice(1).join('/');

        // 第二次GET请求
        const secondSign = generateSign(pathAndQuery, true);
        const headers2 = getCommonHeaders();
        headers2.sign = secondSign;
        headers2.Host = 'live-dispatcher.5gtv.com.cn';

        const res2 = ku9.request(firstUrl, 'GET', headers2);
        if (!res2 || res2.code !== 200) {
            throw new Error(`二次请求失败: ${res2 ? res2.code : '无响应'}`);
        }

        const json2 = JSON.parse(res2.body);
        if (!json2 || !json2.data || !json2.data.url) {
            throw new Error('二次API响应格式错误');
        }

        const playUrl = json2.data.url;
        ku9.setCache(cacheKey, playUrl, 600000); // 缓存10分钟
        return { url: playUrl };
        
    } catch (error) {
        // 增强错误信息
        const debugInfo = {
            error: error.message,
            res1: res1 ? {
                code: res1.code,
                body: res1.body.substring(0, 200) + '...' // 截取部分响应体
            } : '无响应',
            res2: res2 ? {
                code: res2.code,
                body: res2.body.substring(0, 200) + '...'
            } : '无响应'
        };
        
        ku9.setCache('error_log', JSON.stringify(debugInfo), 300000);
        return { 
            url: '', 
            error: '播放地址获取失败',
            debug: debugInfo
        };
    }
}