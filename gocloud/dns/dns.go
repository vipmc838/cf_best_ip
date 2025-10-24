package dns

import (
    "fmt"
    "net/http"
    "strings"
    "time"

    "github.com/tidwall/gjson"
)

type LineResult struct {
    IP     string
    Delay  float64
    Loss   float64
    Speed  float64
    Source string
}

// FetchCloudflareIPs 从网页抓取 Cloudflare 优选 IP 数据
func FetchCloudflareIPs() (map[string][]LineResult, error) {
    url := "https://api.uouin.com/cloudflare.html"
    client := &http.Client{Timeout: 15 * time.Second}

    resp, err := client.Get(url)
    if err != nil {
        return nil, fmt.Errorf("请求失败: %v", err)
    }
    defer resp.Body.Close()

    buf := new(strings.Builder)
    _, err = buf.ReadFrom(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("读取响应失败: %v", err)
    }

    html := buf.String()
    results := make(map[string][]LineResult)

    // 用正则或简单解析 (uouin 页面是 JSON 格式片段)
    tableData := gjson.Get(html, "data").String()
    if tableData == "" {
        // 如果不是 JSON 格式，说明页面是 HTML 表格结构
        // 简化版提取
        segments := strings.Split(html, "<tr>")
        for _, seg := range segments {
            if strings.Contains(seg, "</tr>") && strings.Contains(seg, "<td>") {
                cols := strings.Split(seg, "<td>")
                if len(cols) < 5 {
                    continue
                }
                ip := extractText(cols[3])
                latency := extractFloat(cols[4])
                speed := extractFloat(cols[6])
                loss := extractFloat(cols[5])

                line := "unknown"
                if strings.Contains(seg, "电信") {
                    line = "ct"
                } else if strings.Contains(seg, "联通") {
                    line = "cu"
                } else if strings.Contains(seg, "移动") {
                    line = "cm"
                }

                results[line] = append(results[line], LineResult{
                    IP: ip, Delay: latency, Speed: speed, Loss: loss, Source: line,
                })
            }
        }
    }

    return results, nil
}

// 提取文本内容
func extractText(s string) string {
    s = strings.Split(s, "</td>")[0]
    return strings.TrimSpace(s)
}

// 提取浮点值
func extractFloat(s string) float64 {
    s = extractText(s)
    s = strings.ReplaceAll(s, "ms", "")
    s = strings.ReplaceAll(s, "%", "")
    s = strings.ReplaceAll(s, "mb/s", "")
    s = strings.TrimSpace(s)
    var v float64
    fmt.Sscanf(s, "%f", &v)
    return v
}
