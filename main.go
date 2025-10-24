package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"

	"golang.org/x/net/html"

	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/region"
	dnsv2 "github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
)

type IPEntry struct {
	IP        string  `json:"优选IP"`
	Line      string  `json:"线路"`
	Latency   float64
	Speed     float64
	Packet    string `json:"丢包"`
	Bandwidth string `json:"带宽"`
	Time      string `json:"时间"`
}

type OutputData struct {
	GeneratedAt  string                 `json:"生成时间"`
	BestIP       map[string]interface{} `json:"最优IP推荐"`
	FullDataList map[string][]IPEntry   `json:"完整数据列表"`
}

func main() {
	url := "https://api.uouin.com/cloudflare.html"
	fullData, err := fetchCloudflareIPs(url)
	if err != nil {
		log.Fatalf("抓取失败: %v", err)
	}

	bestIP := make(map[string]interface{})
	for line, entries := range fullData {
		for _, e := range entries {
			if e.Packet == "0.00%" {
				bestIP[line] = map[string]interface{}{
					"优选IP":    e.IP,
					"延迟":      e.Latency,
					"速度":      e.Speed,
					"带宽":      e.Bandwidth,
					"测试时间":    e.Time,
				}
				break
			}
		}
	}

	output := OutputData{
		GeneratedAt:  fmt.Sprintf("%s", strings.Split(fmt.Sprintf("%v", os.Getenv("TZ")), " ")[0]),
		BestIP:       bestIP,
		FullDataList: fullData,
	}

	fileBytes, _ := json.MarshalIndent(output, "", "  ")
	jsonFile := "cloudflare_ips.json"
	os.WriteFile(jsonFile, fileBytes, 0644)
	log.Printf("✅ JSON 文件已生成: %s", jsonFile)

	// DNS 更新
	huaweiCfg := map[string]string{
		"电信": os.Getenv("CT_A_ID"),
		"联通": os.Getenv("CU_A_ID"),
		"移动": os.Getenv("CM_A_ID"),
	}

	auth := basic.NewCredentialsBuilder().
		WithAk(os.Getenv("HUAWEI_ACCESS_KEY")).
		WithSk(os.Getenv("HUAWEI_SECRET_KEY")).
		WithProjectId(os.Getenv("HUAWEI_PROJECT_ID")).
		Build()

	hwRegion := region.NewRegion("ap-southeast-1", "https://dns.ap-southeast-1.myhuaweicloud.com")
	client := dnsv2.NewDnsClient(dnsv2.DnsClientBuilder().WithRegion(hwRegion).WithCredential(auth).Build())

	for line, entries := range fullData {
		var ips []string
		for _, e := range entries {
			ips = append(ips, e.IP)
		}
		if recordID, ok := huaweiCfg[line]; ok && len(ips) > 0 {
			if err := updateHuaweiDNS(client, recordID, ips, os.Getenv("SUBDOMAIN"), os.Getenv("DOMAIN")); err != nil {
				log.Printf("❌ %s DNS 更新失败: %v", line, err)
			} else {
				log.Printf("✅ %s DNS 已更新: %v", line, ips)
			}
		} else {
			log.Printf("❌ %s DNS 更新失败: 未知运营商或无 IP", line)
		}
	}
}

func updateHuaweiDNS(client *dnsv2.DnsClient, recordID string, ips []string, subdomain, domain string) error {
	fullName := fmt.Sprintf("%s.%s.", subdomain, domain)
	reqBody := &model.UpdateRecordSetReq{
		Name:    &fullName,
		Type:    stringPtr("A"),
		Records: &ips,
		Ttl:     int32Ptr(1),
	}
	req := &model.UpdateRecordSetRequest{
		ZoneId:      recordID,
		RecordsetId: recordID,
		Body:        reqBody,
	}
	_, err := client.UpdateRecordSet(req)
	return err
}

func stringPtr(s string) *string { return &s }
func int32Ptr(i int32) *int32   { return &i }

func fetchCloudflareIPs(url string) (map[string][]IPEntry, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	doc, err := html.Parse(resp.Body)
	if err != nil {
		return nil, err
	}

	var table *html.Node
	var f func(*html.Node)
	f = func(n *html.Node) {
		if n.Type == html.ElementNode && n.Data == "table" {
			for _, a := range n.Attr {
				if a.Key == "class" && strings.Contains(a.Val, "table-striped") {
					table = n
					return
				}
			}
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			f(c)
		}
	}
	f(doc)
	if table == nil {
		return nil, fmt.Errorf("未找到目标表格")
	}

	fullData := make(map[string][]IPEntry)
	trs := []*html.Node{}
	for c := table.FirstChild; c != nil; c = c.NextSibling {
		if c.Type == html.ElementNode && c.Data == "tbody" {
			for tr := c.FirstChild; tr != nil; tr = tr.NextSibling {
				if tr.Type == html.ElementNode && tr.Data == "tr" {
					trs = append(trs, tr)
				}
			}
		}
	}

	headers := []string{"#", "线路", "优选IP", "丢包", "延迟", "速度", "带宽", "Colo", "时间"}
	for _, tr := range trs {
		tds := []*html.Node{}
		for td := tr.FirstChild; td != nil; td = td.NextSibling {
			if td.Type == html.ElementNode && (td.Data == "td" || td.Data == "th") {
				tds = append(tds, td)
			}
		}
		if len(tds) != len(headers) {
			continue
		}
		entry := IPEntry{}
		var latency, speed float64
		for i, td := range tds {
			text := strings.TrimSpace(getNodeText(td))
			switch headers[i] {
			case "线路":
				entry.Line = text
			case "优选IP":
				entry.IP = text
			case "丢包":
				entry.Packet = text
			case "延迟":
				fmt.Sscanf(text, "%fms", &latency)
				entry.Latency = latency
			case "速度":
				fmt.Sscanf(text, "%fmb/s", &speed)
				entry.Speed = speed
			case "带宽":
				entry.Bandwidth = text
			case "时间":
				entry.Time = text
			}
		}
		fullData[entry.Line] = append(fullData[entry.Line], entry)
	}

	// 排序
	for k := range fullData {
		sort.Slice(fullData[k], func(i, j int) bool {
			if fullData[k][i].Latency != fullData[k][j].Latency {
				return fullData[k][i].Latency < fullData[k][j].Latency
			}
			return fullData[k][i].Speed > fullData[k][j].Speed
		})
	}

	return fullData, nil
}

func getNodeText(n *html.Node) string {
	if n.Type == html.TextNode {
		return n.Data
	}
	var buf bytes.Buffer
	for c := n.FirstChild; c != nil; c = c.NextSibling {
		buf.WriteString(getNodeText(c))
	}
	return buf.String()
}
