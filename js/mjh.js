function main(item) {
    jz.setRequest(item);
    const res = jz.get('https://i.mjh.nz/all/tv.json');
    if (!jz.isJSONObject(res)) {
        return {
            'error': '获取播放地址接口返回格式不正确！'
        };
    }
    const json = JSON.parse(res);

    let groups = [];
    let channels = [];
    for (const key in json) {
        const field = json[key];
        channels.push({
            name: field.name,
            logo: field.logo,
            links: [{
                link: [{
                    'url': field.mjh_master,
                    'headers': {
                        'user-agent': field.headers['user-agent']
                    }
                }]
            }]
        });
    }
    groups.push({
        name: 'mjh',
        channels: channels
    });
    return {
        groups: groups
    };
}