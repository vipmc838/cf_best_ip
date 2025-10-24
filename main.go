package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	dns "github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/dnsregion"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
)

// 辅助指针函数
func stringPtr(s string) *string { return &s }
func int32Ptr(i int32) *int32    { return &i }

// DNS 线路配置
type LineConfig struct {
	Operator     string
	ARecordID    string
	AAAARecordID string
}

// 抓取到的 IP 数据
type IPInfo struct {
	IP     string
	Line   string
	Latency float64
	Speed   float64
	Loss    string
	Bandwidth string
	Time    string
}

// 解析网页获取三网 IP
func fetchIPs() (map[string][]IPInfo, IPInfo, error) {
	url := "https://api.uouin.com/cloudflare.html"
	resp, err := http.Get(url)
	if err != nil {
		return nil, IPInfo{}, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, IPInfo{}, err
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(body)))
	if err != nil {
		return nil, IPInfo{}, err
	}

	table := doc.Find("table.table.table-striped")
	if table.Length() == 0 {
		return nil, IPInfo{}, fmt.Errorf("未找到目标表格")
	}

	lines := map[string][]IPInfo{}
	var bestIP IPInfo
	ipMetrics := []IPInfo{}

	table.Find("tr").Slice(1, goquery.ToEnd).Each(func(i int, s *goquery.Selection) {
		cells := s.Find("th,td")
		if cells.Length() < 10 {
			return
		}
		line := strings.TrimSpace(cells.Eq(1).Text())
		ip := strings.TrimSpace(cells.Eq(2).Text())
		loss := strings.TrimSpace(cells.Eq(3).Text())
		latencyStr := strings.TrimSpace(cells.Eq(4).Text())
		speedStr := strings.TrimSpace(cells.Eq(5).Text())
		bandwidth := strings.TrimSpace(cells.Eq(6).Text())
		timeStr := strings.TrimSpace(cells.Eq(9).Text())

		latency := 0.0
		fmt.Sscanf(latencyStr, "%fms", &latency)
		speed := 0.0
		fmt.Sscanf(speedStr, "%fmb/s", &speed)

		info := IPInfo{
			IP: ip, Line: line, Latency: latency, Speed: speed,
			Loss: loss, Bandwidth: bandwidth, Time: timeStr,
		}

		lines[line] = append(lines[line], info)

		if loss == "0.00%" {
			ipMetrics = append(ipMetrics, info)
		}
	})

	// 选出最佳 IP
	if len(ipMetrics) > 0 {
		sort.Slice(ipMetrics, func(i, j int) bool {
			if ipMetrics[i].Latency != ipMetrics[j].Latency {
				return ipMetrics[i].Latency < ipMetrics[j].Latency
			}
			return ipMetrics[i].Speed > ipMetrics[j].Speed
		})
		bestIP = ipMetrics[0]
	}

	// 对每个线路按延迟排序
	for k := range lines {
		sort.Slice(lines[k], func(i, j int) bool {
			if lines[k][i].Latency != lines[k][j].Latency {
				return lines[k][i].Latency < lines[k][j].Latency
			}
			return lines[k][i].Speed > lines[k][j].Speed
		})
	}

	return lines, bestIP, nil
}

// 更新华为云 DNS
func updateHuaweiDNS(line LineConfig, ips []string) error {
	auth := basic.NewCredentialsBuilder().
		WithAk(os.Getenv("HUAWEI_ACCESS_KEY")).
		WithSk(os.Getenv("HUAWEI_SECRET_KEY")).
		WithProjectId(os.Getenv("HUAWEI_PROJECT_ID")).
		Build()

	client := dns.NewDnsClient(
		dns.DnsClientBuilder().
			WithRegion(dnsregion.ValueOf(os.Getenv("HUAWEI_REGION"))).
			WithCredential(auth).
			Build(),
	)

	fullName := fmt.Sprintf("%s.%s.", os.Getenv("SUBDOMAIN"), os.Getenv("DOMAIN"))

	req := &model.UpdateRecordSetRequest{
		ZoneId:      os.Getenv("ZONE_ID"),
		RecordsetId: line.ARecordID,
		Body: &model.UpdateRecordSetReq{
			Name:    stringPtr(fullName),
			Type:    stringPtr("A"),
			Records: &ips,
			Ttl:     int32Ptr(60),
		},
	}

	_, err := client.UpdateRecordSet(req)
	return err
}

func main() {
	log.Println("🚀 开始抓取 Cloudflare 三网 IP ...")
	lines, bestIP, err := fetchIPs()
	if err != nil {
		log.Fatal(err)
	}

	// 写入 cloudflare_ips.json
	output := map[string]interface{}{
		"生成时间":    time.Now().Format(time.RFC3339),
		"最优IP":     bestIP,
		"完整数据":   lines,
	}

	data, _ := json.MarshalIndent(output, "", "  ")
	err = os.WriteFile("cloudflare_ips.json", data, 0644)
	if err != nil {
		log.Fatal(err)
	}
	log.Println("✅ JSON 文件已生成: cloudflare_ips.json")

	// DNS 更新配置
	configs := []LineConfig{
		{"ct", os.Getenv("CT_A_ID"), os.Getenv("CT_AAAA_ID")},
		{"cu", os.Getenv("CU_A_ID"), os.Getenv("CU_AAAA_ID")},
		{"cm", os.Getenv("CM_A_ID"), os.Getenv("CM_AAAA_ID")},
	}

	for _, cfg := range configs {
		ipList := []string{}
		for _, info := range lines[cfg.Operator] {
			ipList = append(ipList, info.IP)
		}
		if len(ipList) == 0 {
			log.Printf("⚠️ [%s] 未找到有效 IP，跳过。", cfg.Operator)
			continue
		}
		err := updateHuaweiDNS(cfg, ipList)
		if err != nil {
			log.Printf("❌ [%s] 更新失败: %v", cfg.Operator, err)
		} else {
			log.Printf("✅ [%s] DNS 已更新: %v", cfg.Operator, ipList)
		}
	}

	log.Println("🎉 DNS 更新任务完成。")
}
