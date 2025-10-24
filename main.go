package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
)

// DNSLine 表示一条 DNS 线路配置
type DNSLine struct {
	Operator       string
	ARecordsetID   string
	AAAARecordsetID string
}

// LineResult 表示抓取到的一条线路 IP 信息
type LineResult struct {
	IP      string
	Latency float64
	Speed   float64
	Line    string
}

// Output JSON 结构
type Output struct {
	GeneratedAt string                         `json:"生成时间"`
	Lines       map[string][]LineResult        `json:"三网IP"`
}

// 华为云 DNS 更新请求结构
type HuaweiRecord struct {
	Name    string   `json:"name"`
	Type    string   `json:"type"`
	TTL     int      `json:"ttl"`
	Records []string `json:"records"`
}

// 获取环境变量
func getenv(key string) string {
	val := os.Getenv(key)
	if val == "" {
		log.Fatalf("❌ 环境变量 %s 未设置", key)
	}
	return val
}

// 抓取 HTML 表格并解析三网 IP
func fetchCloudflareIPs(url string) (map[string][]LineResult, error) {
	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, err
	}

	lines := make(map[string][]LineResult)

	doc.Find("table.table.table-striped tbody tr").Each(func(i int, s *goquery.Selection) {
		tds := s.Find("td")
		if tds.Length() < 7 {
			return
		}
		line := strings.TrimSpace(tds.Eq(1).Text())
		ip := strings.TrimSpace(tds.Eq(2).Text())
		loss := strings.TrimSpace(tds.Eq(3).Text())
		latencyStr := strings.TrimSpace(tds.Eq(4).Text())
		speedStr := strings.TrimSpace(tds.Eq(5).Text())

		if loss != "0.00%" {
			return
		}

		var latency, speed float64
		fmt.Sscanf(latencyStr, "%f", &latency)
		fmt.Sscanf(speedStr, "%f", &speed)

		lines[line] = append(lines[line], LineResult{
			IP:      ip,
			Latency: latency,
			Speed:   speed,
			Line:    line,
		})
	})

	return lines, nil
}

// 更新华为云 DNS
func updateHuaweiDNS(zoneID, recordsetID, recordName, recordType string, ips []string, region string, ak, sk, projectID string) error {
	if recordsetID == "" || len(ips) == 0 {
		return fmt.Errorf("记录集ID为空或无有效 IP，跳过")
	}

	url := fmt.Sprintf("https://dns.%s.myhuaweicloud.com/v2/%s/recordsets/%s", region, projectID, recordsetID)
	body := HuaweiRecord{
		Name:    recordName,
		Type:    recordType,
		TTL:     1,
		Records: ips,
	}
	data, _ := json.Marshal(body)

	req, _ := http.NewRequest("PUT", url, bytes.NewReader(data))
	req.Header.Set("Content-Type", "application/json;charset=UTF-8")
	req.SetBasicAuth(ak, sk) // 简单 auth，可根据华为云实际签名方式修改

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	respBody, _ := ioutil.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return fmt.Errorf("更新失败: %s", string(respBody))
	}
	return nil
}

func main() {
	log.Println("🚀 抓取网页并解析三网 Cloudflare IP ...")
	url := "https://api.uouin.com/cloudflare.html"
	lines, err := fetchCloudflareIPs(url)
	if err != nil {
		log.Fatalf("❌ 抓取失败: %v", err)
	}

	output := Output{
		GeneratedAt: time.Now().Format(time.RFC3339),
		Lines:       lines,
	}

	file := "cloudflare_ips.json"
	data, _ := json.MarshalIndent(output, "", "    ")
	ioutil.WriteFile(file, data, 0644)
	log.Printf("✅ 成功保存到 %s", file)

	// 华为云配置
	projectID := getenv("HUAWEI_PROJECT_ID")
	ak := getenv("HUAWEI_ACCESS_KEY")
	sk := getenv("HUAWEI_SECRET_KEY")
	zoneID := getenv("ZONE_ID")
	domain := getenv("DOMAIN")
	subdomain := getenv("SUBDOMAIN")
	region := "ap-southeast-1" // 固定区域

	// 记录集 ID
	dnsLines := []DNSLine{
		{"ct", getenv("CT_A_ID"), getenv("CT_AAAA_ID")},
		{"cu", getenv("CU_A_ID"), getenv("CU_AAAA_ID")},
		{"cm", getenv("CM_A_ID"), getenv("CM_AAAA_ID")},
	}

	fullRecordName := fmt.Sprintf("%s.%s.", subdomain, domain)

	for _, line := range dnsLines {
		ips, ok := lines[line.Operator]
		if !ok || len(ips) == 0 {
			log.Printf("⚠️ 线路 %s 没有有效 IP，跳过", line.Operator)
			continue
		}

		var ipList []string
		for _, ip := range ips {
			ipList = append(ipList, ip.IP)
		}

		// 更新 A
		if err := updateHuaweiDNS(zoneID, line.ARecordsetID, fullRecordName, "A", ipList, region, ak, sk, projectID); err != nil {
			log.Printf("❌ 更新 A 记录失败: %v", err)
		} else {
			log.Printf("✅ 成功更新 A 记录: %s", line.Operator)
		}

		// 更新 AAAA
		if err := updateHuaweiDNS(zoneID, line.AAAARecordsetID, fullRecordName, "AAAA", ipList, region, ak, sk, projectID); err != nil {
			log.Printf("❌ 更新 AAAA 记录失败: %v", err)
		} else {
			log.Printf("✅ 成功更新 AAAA 记录: %s", line.Operator)
		}
	}

	log.Println("✅ DNS 更新完成")
}
