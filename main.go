package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"
)

// HuaweiRecordSet 定义更新结构
type HuaweiRecordSet struct {
	Name    string   `json:"name"`
	Type    string   `json:"type"`
	TTL     int      `json:"ttl"`
	Records []string `json:"records"`
}

// 从页面提取三网 IP
func fetchIPs() (map[string][]string, error) {
	url := "https://api.uouin.com/cloudflare.html"
	resp, err := http.Get(url)
	if err != nil {
		return nil, fmt.Errorf("获取 %s 失败: %v", url, err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	html := string(body)

	re := regexp.MustCompile(`((?:\d{1,3}\.){3}\d{1,3})`)
	lines := strings.Split(html, "\n")

	result := map[string][]string{
		"ct": {}, // 中国电信
		"cu": {}, // 中国联通
		"cm": {}, // 中国移动
	}

	for _, line := range lines {
		ips := re.FindAllString(line, -1)
		if len(ips) == 0 {
			continue
		}
		if strings.Contains(line, "电信") {
			result["ct"] = append(result["ct"], ips...)
		} else if strings.Contains(line, "联通") {
			result["cu"] = append(result["cu"], ips...)
		} else if strings.Contains(line, "移动") {
			result["cm"] = append(result["cm"], ips...)
		}
	}

	return result, nil
}

// 更新 DNS（简化调用，使用 BasicAuth 模拟）
func updateHuaweiCloud(recordType string, records []string) error {
	projectID := os.Getenv("HUAWEI_PROJECT_ID")
	ak := os.Getenv("HUAWEI_ACCESS_KEY")
	sk := os.Getenv("HUAWEI_SECRET_KEY")
	zoneID := os.Getenv("ZONE_ID")
	domain := os.Getenv("DOMAIN")
	subdomain := os.Getenv("SUBDOMAIN")

	if projectID == "" || ak == "" || sk == "" {
		return fmt.Errorf("华为云认证信息不完整，请设置机密变量")
	}

	recordset := HuaweiRecordSet{
		Name:    fmt.Sprintf("%s.%s.", subdomain, domain),
		Type:    recordType,
		TTL:     1,
		Records: records,
	}

	body, _ := json.Marshal(recordset)

	apiURL := fmt.Sprintf("https://dns.myhuaweicloud.com/v2/zones/%s/recordsets", zoneID)
	req, _ := http.NewRequest("PUT", apiURL, strings.NewReader(string(body)))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(ak, sk)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode >= 300 {
		return fmt.Errorf("华为云响应错误 (%d): %s", resp.StatusCode, string(respBody))
	}
	log.Printf("✅ 已更新 [%s] 记录: %v", recordType, records)
	return nil
}

func main() {
	log.Println("🚀 开始从 uouin.com 获取三网 Cloudflare IP ...")
	ipMap, err := fetchIPs()
	if err != nil {
		log.Fatalf("❌ 获取 IP 失败: %v", err)
	}

	for op, ips := range ipMap {
		if len(ips) == 0 {
			log.Printf("⚠️ [%s] 未找到有效 IP，跳过。", op)
			continue
		}
		log.Printf("📡 [%s] 检测到 %d 个 IP: %v", op, len(ips), ips)
		if err := updateHuaweiCloud("A", ips); err != nil {
			log.Printf("❌ [%s] 更新失败: %v", op, err)
		}
	}
	log.Println("✅ DNS 更新任务完成。")
}
