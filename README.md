# 🌐 Cloudflare IP 优选

自动获取 Cloudflare 优选 IP 并更新到华为云 DNS

## 📊 最新更新报告

<!-- REPORT_START -->
### ✅ DNS 更新成功

更新时间: 2026/09/12 21:57:10

- ✅ **默认 A记录:** 30 个IP
- ✅ **电信 A记录:** 10 个IP
- ✅ **联通 A记录:** 10 个IP
- ✅ **移动 A记录:** 10 个IP
- ✅ **IPv6 AAAA记录:** 10 个IP
<!-- REPORT_END -->

## 📖 使用说明

1. Fork 本仓库
2. 设置 Secrets
3. 启用 Actions

## ⚙️ 配置项

| 变量名 | 说明 | 示例 | 
|--------|------|------|
| `FULL_DOMAIN` | 要更新的完整域名（包括子域名），对应华为云 DNS 的记录集 | `cdn.example.com` || 必填 |
| `HUAWEI_ACCESS_KEY` | 华为云账户 AK（Access Key），用于 API 认证 | `ABCD1234EFGH5678` |
| `HUAWEI_SECRET_KEY` | 华为云账户 SK（Secret Key），用于 API 认证 | `abcd1234efgh5678ijkl9012mnop3456` |
| `HUAWEI_REGION` | 华为云 DNS 服务所在区域 | `ap-southeast-1` 或 `cn-south-1` |
| `API_URL` | 私有 API 地址，多个地址换行分隔 | `http://xxx.com/cf/api/results?token=123456` |
| `TG_BOT_TOKEN` | Telegram Bot Token | `123456:ABC-DEF...` |
| `TG_USER_ID` | Telegram User ID | `123456789` |

- API返回JSON格式，字段是中文（IP地址、平均延迟、下载速度等）
```
[
  {
    "IP 地址": "162.159.39.21",
    "已发送": "5",
    "已接收": "5",
    "丢包率": "0.00",
    "平均延迟": "44.85",
    "下载速度(MB/s)": "13.98",
    "地区码": "NRT"
  },
  {
    "IP 地址": "172.64.144.132",
    "已发送": "5",
    "已接收": "5",
    "丢包率": "0.00",
    "平均延迟": "64.40",
    "下载速度(MB/s)": "13.98",
    "地区码": "SIN"
  }
]
```

## 📥 下载文件

- [cloudflare_bestip.json](cloudflare_bestip.json) - JSON 格式
- [cloudflare_bestip.txt](cloudflare_bestip.txt) - 纯文本格式
