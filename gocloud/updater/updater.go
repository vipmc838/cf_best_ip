package updater

import (
    "bytes"
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "time"

    "cloudflare-dns-updater/gocloud/config"
    "cloudflare-dns-updater/gocloud/dns"
)

type updatePayload struct {
    Name        string   `json:"name"`
    Type        string   `json:"type"`
    TTL         int      `json:"ttl"`
    Records     []string `json:"records"`
    Description string   `json:"description,omitempty"`
}

// UpdateAll 将抓取到的 IP 更新到华为云 DNS
func UpdateAll(selected map[string][]dns.LineResult, cfg *config.Config) (int, error) {
    if !cfg.Huawei.Enabled {
        log.Println("[info] 华为云更新功能已禁用，跳过。")
        return 0, nil
    }

    count := 0
    for _, line := range cfg.DNS.Lines {
        if ips, ok := selected[line.Operator]; ok && len(ips) > 0 {
            var records []string
            for i, ip := range ips {
                if i >= line.Cap {
                    break
                }
                records = append(records, ip.IP)
            }

            recordsetID := line.ARecordsetID
            apiURL := fmt.Sprintf(
                "https://dns.myhuaweicloud.com/v2/zones/%s/recordsets/%s",
                cfg.DNS.ZoneId, recordsetID,
            )

            payload := updatePayload{
                Name:        fmt.Sprintf("%s.%s.", cfg.DNS.Subdomain, cfg.DNS.Domain),
                Type:        "A",
                TTL:         cfg.DNS.TTL,
                Records:     records,
                Description: fmt.Sprintf("自动更新于 %s", time.Now().Format(time.RFC3339)),
            }

            body, _ := json.Marshal(payload)
            req, _ := http.NewRequest("PUT", apiURL, bytes.NewReader(body))
            req.Header.Set("X-Auth-Token", cfg.Huawei.AccessKey)
            req.Header.Set("Content-Type", "application/json")

            resp, err := http.DefaultClient.Do(req)
            if err != nil {
                log.Printf("[error] 更新 %s 线路失败: %v", line.Operator, err)
                continue
            }
            resp.Body.Close()

            if resp.StatusCode >= 200 && resp.StatusCode < 300 {
                log.Printf("[ok] 更新 %s 成功: %v", line.Operator, records)
                count++
            } else {
                log.Printf("[fail] 更新 %s 返回状态码 %d", line.Operator, resp.StatusCode)
            }
        }
    }

    return count, nil
}
