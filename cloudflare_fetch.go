package main

import (
    "fmt"
    "log"

    "cloudflare-dns-updater/gocloud/config"
    "cloudflare-dns-updater/gocloud/dns"
    "cloudflare-dns-updater/gocloud/updater"
)

func main() {
    cfg, err := config.Load()
    if err != nil {
        log.Fatalf("加载配置失败: %v", err)
    }

    data, err := dns.FetchCloudflareIPs()
    if err != nil {
        log.Fatalf("抓取 Cloudflare 优选 IP 失败: %v", err)
    }

    count, err := updater.UpdateAll(data, cfg)
    if err != nil {
        log.Fatalf("更新华为云 DNS 失败: %v", err)
    }

    fmt.Printf("✅ 成功更新 %d 条记录。\n", count)
}
