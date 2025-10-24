package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/region"
	dnsv2 "github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
)

type IPEntry struct {
	线路    string  `json:"线路"`
	优选IP  string  `json:"优选IP"`
	丢包    string  `json:"丢包"`
	延迟    float64 `json:"延迟"`
	速度    float64 `json:"速度"`
	带宽    string  `json:"带宽"`
	时间    string  `json:"时间"`
}

type OutputJSON struct {
	生成时间      string                `json:"生成时间"`
	最优IP推荐    map[string]string     `json:"最优IP推荐"`
	完整数据列表  map[string][]IPEntry  `json:"完整数据列表"`
}

func fetchCloudflareIPs() (map[string][]IPEntry, map[string]string, error) {
	url := "https://api.uouin.com/cloudflare.html"
	resp, err := http.Get(url)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, nil, err
	}

	fullData := make(map[string][]IPEntry)
	bestIP := make(map[string]string)

	doc.Find("table.table-striped tbody tr").Each(func(i int, s *goquery.Selection) {
		tds := s.Find("th,td")
		if tds.Length() < 9 {
			return
		}
		line := strings.TrimSpace(tds.Eq(1).Text())
		ip := strings.TrimSpace(tds.Eq(2).Text())
		packet := strings.TrimSpace(tds.Eq(3).Text())
		latencyStr := strings.TrimSpace(tds.Eq(4).Text())
		speedStr := strings.TrimSpace(tds.Eq(5).Text())
		bandwidth := strings.TrimSpace(tds.Eq(6).Text())
		timeStr := strings.TrimSpace(tds.Eq(8).Text())

		latency := 9999.0
		fmt.Sscanf(latencyStr, "%fms", &latency)
		speed := 0.0
		fmt.Sscanf(speedStr, "%fmb/s", &speed)

		entry := IPEntry{
			线路:   line,
			优选IP: ip,
			丢包:   packet,
			延迟:   latency,
			速度:   speed,
			带宽:   bandwidth,
			时间:   timeStr,
		}
		fullData[line] = append(fullData[line], entry)

		if packet == "0.00%" {
			if _, ok := bestIP[line]; !ok {
				bestIP[line] = ip
			} else {
				existing := fullData[line][0]
				if entry.延迟 < existing.延迟 || (entry.延迟 == existing.延迟 && entry.速度 > existing.速度) {
					bestIP[line] = ip
				}
			}
		}
	})

	for line, entries := range fullData {
		sort.Slice(entries, func(i, j int) bool {
			if entries[i].延迟 != entries[j].延迟 {
				return entries[i].延迟 < entries[j].延迟
			}
			return entries[i].速度 > entries[j].速度
		})
		fullData[line] = entries
	}

	return fullData, bestIP, nil
}

func stringPtr(s string) *string       { return &s }
func int32Ptr(i int32) *int32          { return &i }
func strSlicePtr(s []string) *[]string { return &s }

func updateHuaweiDNS(operator string, ips []string) error {
	// 中文线路映射到代码
	opMap := map[string]string{
		"电信": "ct",
		"联通": "cu",
		"移动": "cm",
	}
	code, ok := opMap[operator]
	if !ok {
		return fmt.Errorf("未知运营商: %s", operator)
	}

	auth := basic.NewCredentialsBuilder().
		WithAk(os.Getenv("HUAWEI_ACCESS_KEY")).
		WithSk(os.Getenv("HUAWEI_SECRET_KEY")).
		WithProjectId(os.Getenv("HUAWEI_PROJECT_ID")).
		Build()

	myRegion := region.NewRegion("ap-southeast-1", "https://dns.ap-southeast-1.myhuaweicloud.com")

	client := dnsv2.NewDnsClient(
		dnsv2.DnsClientBuilder().
			WithRegion(myRegion).
			WithCredential(auth).
			Build(),
	)

	var recordID string
	switch code {
	case "ct":
		recordID = os.Getenv("CT_A_ID")
	case "cu":
		recordID = os.Getenv("CU_A_ID")
	case "cm":
		recordID = os.Getenv("CM_A_ID")
	default:
		return fmt.Errorf("未知运营商: %s", code)
	}

	fullName := fmt.Sprintf("%s.%s.", os.Getenv("SUBDOMAIN"), os.Getenv("DOMAIN"))

	reqBody := &model.UpdateRecordSetReq{
		Name:    stringPtr(fullName),
		Type:    stringPtr("A"),
		Records: strSlicePtr(ips),
		Ttl:     int32Ptr(1),
	}

	req := &model.UpdateRecordSetRequest{
		ZoneId:      recordID,
		RecordsetId: recordID,
		Body:        reqBody,
	}

	_, err := client.UpdateRecordSet(req)
	if err != nil {
		return err
	}

	log.Printf("✅ %s DNS 已更新: %v", operator, ips)
	return nil
}


func main() {
	log.Println("🚀 开始抓取 Cloudflare 三网 IP ...")
	fullData, bestIP, err := fetchCloudflareIPs()
	if err != nil {
		log.Fatalf("抓取失败: %v", err)
	}

	output := OutputJSON{
		生成时间:     time.Now().Format(time.RFC3339),
		最优IP推荐:   bestIP,
		完整数据列表: fullData,
	}

	file, _ := os.Create("cloudflare_ips.json")
	defer file.Close()
	enc := json.NewEncoder(file)
	enc.SetIndent("", "    ")
	enc.Encode(output)
	log.Println("✅ JSON 文件已生成: cloudflare_ips.json")

	for op, ip := range bestIP {
		if err := updateHuaweiDNS(op, []string{ip}); err != nil {
			log.Printf("❌ %s DNS 更新失败: %v", op, err)
		}
	}
	log.Println("✅ DNS 更新完成。")
}
