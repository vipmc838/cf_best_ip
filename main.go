package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/region"
)

type IPInfo struct {
	IP        string  `json:"ip"`
	Latency   float64 `json:"latency"`
	Speed     float64 `json:"speed"`
	Loss      string  `json:"loss"`
	Bandwidth string  `json:"bandwidth"`
	Time      string  `json:"time"`
}

type OutputJSON struct {
	GeneratedAt string              `json:"生成时间"`
	BestIPs     map[string]IPInfo   `json:"最优IP推荐"`
	AllIPs      map[string][]IPInfo `json:"完整数据列表"`
}

var lineMap = map[string]string{
	"ct": "中国电信",
	"cu": "中国联通",
	"cm": "中国移动",
}

// 抓取三网 Cloudflare IP
func fetchCloudflareIPs(url string) (map[string][]IPInfo, map[string]IPInfo, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, nil, fmt.Errorf("HTTP 状态码: %d", resp.StatusCode)
	}
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, nil, err
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(bodyBytes)))
	if err != nil {
		return nil, nil, err
	}

	allIPs := make(map[string][]IPInfo)
	bestIPs := make(map[string]IPInfo)

	doc.Find("table.table.table-striped tbody tr").Each(func(i int, s *goquery.Selection) {
		cells := s.Find("th,td")
		if cells.Length() < 9 {
			return
		}

		line := strings.TrimSpace(cells.Eq(1).Text())
		ip := strings.TrimSpace(cells.Eq(2).Text())
		loss := strings.TrimSpace(cells.Eq(3).Text())
		latencyStr := strings.TrimSpace(cells.Eq(4).Text())
		speedStr := strings.TrimSpace(cells.Eq(5).Text())
		bandwidth := strings.TrimSpace(cells.Eq(6).Text())
		timestamp := strings.TrimSpace(cells.Eq(8).Text())

		latency := 9999.0
		speed := 0.0
		fmt.Sscanf(latencyStr, "%f", &latency)
		fmt.Sscanf(speedStr, "%f", &speed)

		info := IPInfo{
			IP: ip, Latency: latency, Speed: speed, Loss: loss,
			Bandwidth: bandwidth, Time: timestamp,
		}

		allIPs[line] = append(allIPs[line], info)

		if loss == "0.00%" {
			if exist, ok := bestIPs[line]; !ok || info.Latency < exist.Latency || (info.Latency == exist.Latency && info.Speed > exist.Speed) {
				bestIPs[line] = info
			}
		}
	})

	// 延迟排序
	for k := range allIPs {
		sort.Slice(allIPs[k], func(i, j int) bool {
			if allIPs[k][i].Latency != allIPs[k][j].Latency {
				return allIPs[k][i].Latency < allIPs[k][j].Latency
			}
			return allIPs[k][i].Speed > allIPs[k][j].Speed
		})
	}

	return allIPs, bestIPs, nil
}

// 更新 DNS
func updateHuaweiDNS(client *dns.DnsClient, zoneID, recordsetID, recordType, fullName string, ips []string) error {
	req := &model.UpdateRecordSetRequest{
		ZoneId:      zoneID,
		RecordsetId: recordsetID,
		Body: &model.UpdateRecordSetReq{
			Name:    &fullName,
			Type:    &recordType,
			Records: &ips,
			Ttl:     int32Ptr(60),
		},
	}
	_, err := client.UpdateRecordSet(req)
	return err
}

func int32Ptr(i int32) *int32 { return &i }

func main() {
	url := "https://api.uouin.com/cloudflare.html"

	allIPs, bestIPs, err := fetchCloudflareIPs(url)
	if err != nil {
		fmt.Println("抓取失败:", err)
		return
	}

	output := OutputJSON{
		GeneratedAt: time.Now().Format(time.RFC3339),
		BestIPs:     bestIPs,
		AllIPs:      allIPs,
	}

	jsonFile := "cloudflare_ips.json"
	data, _ := json.MarshalIndent(output, "", "    ")
	os.WriteFile(jsonFile, data, 0644)
	fmt.Println("✅ JSON 文件已生成:", jsonFile)

	ak := os.Getenv("HUAWEI_ACCESS_KEY")
	sk := os.Getenv("HUAWEI_SECRET_KEY")
	projectID := os.Getenv("HUAWEI_PROJECT_ID")
	regionID := "ap-southeast-1"
	zoneID := os.Getenv("ZONE_ID")

	auth := basic.NewCredentialsBuilder().
		WithAk(ak).
		WithSk(sk).
		WithProjectId(projectID).
		Build()

	client := dns.NewDnsClient(
		dns.DnsClientBuilder().
			WithRegion(region.ValueOf(regionID)).
			WithCredential(auth).
			Build(),
	)

	lines := map[string]struct {
		AID    string
		AAAAID string
	}{
		"ct": {AID: os.Getenv("CT_A_ID"), AAAAID: os.Getenv("CT_AAAA_ID")},
		"cu": {AID: os.Getenv("CU_A_ID"), AAAAID: os.Getenv("CU_AAAA_ID")},
		"cm": {AID: os.Getenv("CM_A_ID"), AAAAID: os.Getenv("CM_AAAA_ID")},
	}

	subdomain := os.Getenv("SUBDOMAIN")
	domain := os.Getenv("DOMAIN")
	fullName := fmt.Sprintf("%s.%s.", subdomain, domain)

	for op, cfg := range lines {
		var ips []string
		for _, ipinfo := range allIPs[op] {
			ips = append(ips, ipinfo.IP)
		}
		if len(ips) == 0 {
			fmt.Printf("⚠️ [%s] 未找到有效 IP，跳过。\n", lineMap[op])
			continue
		}

		if cfg.AID != "" {
			err := updateHuaweiDNS(client, zoneID, cfg.AID, "A", fullName, ips)
			if err != nil {
				fmt.Printf("❌ [%s] A 记录更新失败: %v\n", lineMap[op], err)
			} else {
				fmt.Printf("✅ [%s] A 记录已更新: %v\n", lineMap[op], ips)
			}
		}
		if cfg.AAAAID != "" {
			err := updateHuaweiDNS(client, zoneID, cfg.AAAAID, "AAAA", fullName, ips)
			if err != nil {
				fmt.Printf("❌ [%s] AAAA 记录更新失败: %v\n", lineMap[op], err)
			} else {
				fmt.Printf("✅ [%s] AAAA 记录已更新: %v\n", lineMap[op], ips)
			}
		}
	}

	fmt.Println("✅ DNS 更新任务完成。")
}
