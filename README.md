# 🌐 Cloudflare IP 优选

自动获取 Cloudflare 优选 IP 并更新到华为云 DNS

## 📊 最新更新报告

<!-- REPORT_START -->
### ✅ DNS 更新成功

🕐 **更新时间:** 2025/12/02 06:25:53

- ✅ **默认 A记录:** 10 个IP
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
| `TG_BOT_TOKEN` | Telegram Bot Token | `123456:ABC-DEF...` |
| `TG_USER_ID` | Telegram User ID | `123456789` |

## 📥 下载文件

- [cloudflare_bestip.json](cloudflare_bestip.json) - JSON 格式
- [cloudflare_bestip.txt](cloudflare_bestip.txt) - 纯文本格式
