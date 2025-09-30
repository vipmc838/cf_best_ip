# Cloudflare IP 优选抓取与解析

## 项目简介

这是一个基于 GitHub Actions 的自动化项目，用于抓取和解析 Cloudflare 优选 IP 数据。项目通过定时任务每两小时自动从指定网站获取最新的 Cloudflare IP 性能数据，并智能分析出最优的 IP 地址供用户使用。

## 功能特性

- 🕐 **自动定时抓取**: 每两小时自动运行一次
- 🎯 **智能优选算法**: 基于延迟和速度综合评估，筛选出最优 IP
- 📊 **完整数据保存**: 保存所有 IP 的详细性能数据
- 🔄 **自动更新**: 自动提交最新数据到仓库
- 📦 **制品保存**: 生成可下载的数据制品
- 🚀 **手动触发**: 支持通过 GitHub 网页界面手动触发

## 工作原理

1. **数据抓取**: 使用 Node.js 和 axios 从 [麒麟域名检测](https://api.uouin.com/cloudflare.html) 抓取 Cloudflare IP 数据
2. **数据解析**: 使用 cheerio 解析 HTML 表格，提取 IP 性能指标
3. **智能排序**: 优先选择丢包率为 0.00% 的 IP，然后按延迟升序、速度降序排序
4. **结果输出**: 生成包含最优 IP 推荐和完整数据列表的 JSON 文件

## 输出数据格式

项目会生成 `cloudflare_bestip_ranking.json` 文件，包含以下结构：

```json
{
  "最优IP推荐": {
    "最优线路": "联通",
    "最优IP": "104.26.4.90",
    "最低延迟": "68.57ms",
    "最高速度": "10.27mb/s",
    "带宽": "82.16mb",
    "测试时间": "2024/04/09 01:32:04"
  },
  "完整数据列表": [
    {
      "线路": "电信",
      "优选IP": "172.64.82.114",
      "丢包": "0.00%",
      "延迟": "136.85ms",
      "速度": "6.92mb/s",
      "带宽": "55.36mb",
      "Colo链接": "http://172.64.82.114/cdn-cgi/trace",
      "时间": "2024/04/09 01:42:07"
    }
  ]
}
```

## 使用方法

### 自动运行
项目已配置为每天自动运行，无需手动干预。

### 手动触发
1. 进入 GitHub 仓库的 Actions 页面
2. 选择 "Cloudflare IP 优选抓取与解析" 工作流
3. 点击 "Run workflow" 按钮手动触发

### 获取数据
- **最新数据**: 查看仓库中的 `cloudflare_bestip_ranking.json` 文件
- **历史数据**: 在 Actions 页面的制品 (Artifacts) 中下载

## 技术栈

- **GitHub Actions**: 自动化工作流
- **Node.js 20**: 运行环境
- **axios**: HTTP 客户端
- **cheerio**: HTML 解析器
- **JSON**: 数据格式

## 文件结构

```
cf_best_ip/
├── .github/
│   └── workflows/
│       └── 优选ip.yml          # GitHub Actions 工作流配置
├── cloudflare_bestip_ranking.json  # 生成的优选 IP 数据文件
└── README.md                   # 项目说明文档
```

## 配置说明

### 定时任务
```yaml
schedule:
  - cron: '0 */2 * * *'  # 每两小时运行一次
```

### 数据源
- **目标网站**: https://api.uouin.com/cloudflare.html
- **更新频率**: 每10分钟更新一次（数据源）
- **抓取频率**: 每两小时一次（本项目）

## 注意事项

- 项目仅用于学习和研究目的
- 请遵守目标网站的使用条款
- 建议合理使用抓取频率，避免对目标网站造成压力
- 生成的 IP 数据仅供参考，实际使用效果可能因网络环境而异

## 致谢

### 数据源提供者
感谢 [麒麟域名检测](https://api.uouin.com/cloudflare.html) 网站提供优质的 Cloudflare IP 性能数据。该网站每10分钟更新一次数据，为网络优化提供了宝贵的信息。

### 平台支持
感谢 [GitHub](https://github.com) 提供的免费 CI/CD 服务，使得这个自动化项目能够稳定运行。

### 开源社区
感谢以下开源项目的贡献：
- [GitHub Actions](https://github.com/features/actions) - 自动化工作流平台
- [Node.js](https://nodejs.org/) - JavaScript 运行环境
- [axios](https://github.com/axios/axios) - HTTP 客户端库
- [cheerio](https://github.com/cheeriojs/cheerio) - 服务器端 jQuery 实现

## 许可证

本项目仅供学习和研究使用。请遵守相关网站的使用条款和当地法律法规。

---

**免责声明**: 本项目仅用于技术学习和研究，使用者需自行承担使用风险。作者不对因使用本项目而产生的任何问题负责。
