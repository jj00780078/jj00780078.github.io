function main(ctx) {
  if (jz.mode == 3) {
    return GetChannelList(ctx);
  } else if (jz.mode == 1) {
    const playUrl = GetPlayUrl(ctx);
    return { url: playUrl };
  }
}

/* =========================
 * 频道分组（mode == 3）
 * ========================= */

function GetChannelList(ctx) {
  let api = "https://api2.4gtv.tv/Channel/GetChannelFastTV";
  let headers = {
    "user-agent":
      "Mozilla/5.0 (iPhone; CPU iPhone OS 15_6 like Mac OS X) AppleWebKit/605.1.15"
  };

  let resp = fetch(api, { headers, ...ctx });
  let data = resp.body.Data;

  let channels = [];
  let groups = [];

  for (const item of data) {
    channels.push({
      name: item.fsNAME,
      logo: item.fsLOGO_MOBILE,
      tvg: item.fsNAME,
      seasons: [
        {
          episodes: [
            {
              links: [
                {
                  url:
                    "https://www.4gtv.tv/channel/" +
                    item.fs4GTV_ID +
                    "?set=1&ch=" +
                    item.fnID,
                  js: jz.path
                }
              ]
            }
          ]
        }
      ]
    });
  }

  groups.push({
    name: "飛速看",
    channels
  });

  api = "https://api2.4gtv.tv/Channel/GetChannelBySetId/1/pc/L";
  resp = fetch(api, { headers, ...ctx });
  data = resp.body.Data;

  let typeList = [];

  for (const item of data) {
    let found = false;
    for (const t of typeList) {
      if (t === GetTypeName(item.fsTYPE_NAME)) {
        found = true;
      }
    }
    if (!found) {
      typeList.push(GetTypeName(item.fsTYPE_NAME));
    }
  }

  for (const type of typeList) {
    channels = [];
    for (const item of data) {
      if (type === GetTypeName(item.fsTYPE_NAME)) {
        channels.push({
          name: item.fsNAME,
          logo: item.fsLOGO_MOBILE,
          tvg: item.fsNAME,
          seasons: [
            {
              episodes: [
                {
                  links: [
                    {
                      url:
                        "https://www.4gtv.tv/channel/" +
                        item.fs4GTV_ID +
                        "?set=1&ch=" +
                        item.fnID,
                      js: jz.path
                    }
                  ]
                }
              ]
            }
          ]
        });
      }
    }
    groups.push({ name: type, channels });
  }

  return { groups };
}

/* =========================
 * 类型名取前两个中文
 * ========================= */

function GetTypeName(str) {
  const reg = /[\u4e00-\u9fa5]/;
  let out = "";
  let count = 0;

  for (let i = 0; i < str.length; i++) {
    const c = str.charAt(i);
    if (reg.test(c)) {
      out += c;
      count++;
      if (count === 2) break;
    }
  }
  return out;
}

/* =========================
 * 随机数字生成
 * ========================= */

function BuildencKey(len) {
  if (len <= 0) return 0;
  const min = Math.pow(10, len - 1);
  const max = Math.pow(10, len) - 1;
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/* =========================
 * 请求真实播放地址
 * ========================= */

function GetPlayUrl(ctx) {
  const ch = jz.getQuery(ctx.url, "ch");
  const assetId = ctx.url.split("?")[0].split("/")[4];

  const auth = Get4gtvauth();

  const encKey =
    BuildencKey(4) +
    "B" +
    BuildencKey(3) +
    "-" +
    BuildencKey(2) +
    "FA-45E8-8FA8-5C" +
    BuildencKey(6) +
    "A" +
    BuildencKey(3);

  const headers = {
    "content-type": "application/json",
    fsenc_key: encKey,
    accept: "*/*",
    fsdevice: "iOS",
    fsvalue: "",
    "accept-language": "zh-CN,zh-Hans;q=0.9",
    "4gtv_auth": auth,
    "user-agent": "okhttp/3.12.11",
    fsversion: "3.1.0"
  };

  const body = {
    fsASSET_ID: assetId,
    fnCHANNEL_ID: ch,
    clsAPP_IDENTITY_VALIDATE_ARUS: {
      fsVALUE: "",
      fsENC_KEY: encKey
    },
    fsDEVICE_TYPE: "mobile"
  };

  const resp = fetch("https://api2.4gtv.tv/App/GetChannelUrl2", {
    headers,
    method: "POST",
    body,
    ...ctx
  });

  const data = resp.body.Data;

  if (!data || !Array.isArray(data.flstURLs)) {
    return { error: "無法取得直播源！" };
  }

  const index = Math.floor(Math.random() * data.flstURLs.length);
  return (
    data.flstURLs[index] +
    "#" +
    data.flstURLs.length +
    "-" +
    (index + 1)
  );

}

/* =========================
 * 4gtv_auth 生成（完整链）
 * ========================= */

function Get4gtvauth() {
  const xorKey = "20241010-20241012";

  const encData =
    "YklifmQCBFlkAHljd3xnQAVZUl5DWQlCd25LQENHSX1BBkF7WH5eCQRjZgYDWgQJVlcZWAFcVmZcWGRUYWNwH38GBnBcaEBtRwl1Vlp5G0dRBEdmWVUNDw==";
  const encKey =
    "W1xLdgMJa1RfR0VjXnIEBHhacnBmBl8DahVlegACZ1c=";
  const encIV =
    "eGV/TEdmfF1eSEFnYFR7Xw==";

  const data = Base64toXOR(encData, xorKey);
  const key = Base64toXOR(encKey, xorKey);
  const iv = Base64toXOR(encIV, xorKey);

  const today = GetToday();

  const decrypted = jz.opensslDecrypt(
    data,
    "AES-256-CBC",
    key,
    0,
    iv
  );

  const clean = decrypted.replace(/\0+$/, "");

  return Hex2Base64(
    jz.digest("sha512", today + clean)
  );
}

/* =========================
 * 日期 YYYYMMDD
 * ========================= */

function GetToday() {
  return new Date().toISOString().split("T")[0].replace(/-/g, "");
}

/* =========================
 * Base64 → XOR
 * ========================= */

function Base64toXOR(b64, key) {
  const raw = Base64Decode(b64);
  let out = "";
  for (let i = 0; i < raw.length; i++) {
    out += String.fromCharCode(
      raw.charCodeAt(i) ^ key.charCodeAt(i % key.length)
    );
  }
  return out;
}

/* =========================
 * Base64 decode
 * ========================= */

function Base64Decode(input) {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";
  let str = String(input).replace(/=+$/, "");
  let output = "";

  if (str.length % 4 === 1) {
    throw new Error("Invalid base64");
  }

  for (
    let bc = 0, bs, buffer, idx = 0;
    (buffer = str.charAt(idx++));
    ~buffer &&
      ((bs = bc % 4 ? bs * 64 + buffer : buffer),
        bc++ % 4)
      ? (output += String.fromCharCode(
        255 & (bs >> ((-2 * bc) & 6))
      ))
      : 0
  ) {
    buffer = chars.indexOf(buffer);
  }

  return output;
}

/* =========================
 * hex → base64
 * ========================= */

function Hex2Base64(hex) {
  let bin = "";
  if (typeof hex === "string") {
    if (!/^[0-9a-fA-F]+$/.test(hex)) return "";
    for (let i = 0; i < hex.length; i += 2) {
      bin += String.fromCharCode(parseInt(hex.substr(i, 2), 16));
    }
  }
  return Base64Encode(bin);
}

/* =========================
 * base64 encode
 * ========================= */

function Base64Encode(str) {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";
  let out = "";
  let i = 0;

  while (i < str.length) {
    const c1 = str.charCodeAt(i++);
    const c2 = str.charCodeAt(i++);
    const c3 = str.charCodeAt(i++);

    const e1 = c1 >> 2;
    const e2 = ((c1 & 3) << 4) | (c2 >> 4);
    const e3 = isNaN(c2) ? 64 : ((c2 & 15) << 2) | (c3 >> 6);
    const e4 = isNaN(c3) ? 64 : c3 & 63;

    out +=
      chars.charAt(e1) +
      chars.charAt(e2) +
      chars.charAt(e3) +
      chars.charAt(e4);
  }

  return out;
}