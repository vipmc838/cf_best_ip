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
	"time"

	"golang.org/x/net/html"

	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	dns "github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
)

type IPEntry struct {
	IP        string  `json:"优选IP"`
	Line      string  `json:"线路"`
	Latency   float64 `json:"延迟"`
	Speed     float64 `json:"速度"`
	Packet    string  `json:"丢包"`
	Bandwidth string  `json:"带宽"`
	Time      string  `json:"时间"`
}

type OutputData struct {
	GeneratedAt  string                 `json:"生成时间"`
	BestIP       map[string]interface{} `json:"最优IP推荐"`
	FullDataList map[string][]IPEntry   `json:"完整数据列表"`
}

type HuaweiDNSConfig struct {
	ProjectID string
	AccessKey string
	SecretKey string
	Region    string
	ZoneID    string
	Domain    string
	Subdomain string
	ARecord   map[string]string
}

func main() {
	cfg := HuaweiDNSConfig{
		ProjectID: os.Getenv("HUAWEI_PROJECT_ID"),
		AccessKey: os.Getenv("HUAWEI_ACCESS_KEY"),
		SecretKey: os.Getenv("HUAWEI_SECRET_KEY"),
		Region:    os.Getenv("HUAWEI_REGION"),
		ZoneID:    os.Getenv("ZONE_ID"),
		Domain:    os.Getenv("DOMAIN"),
		Subdomain: os.Getenv("SUBDOMAIN"),
		ARecord: map[string]string{
			"电信": os.Getenv("CT_A_ID"),
			"联通": os.Getenv("CU_A_ID"),
			"移动": os.Getenv("CM_A_ID"),
		},
	}

	cloudflareURL := "https://www.cloudflare.com/ips-v4/" // 示例
	fmt.Println("🚀 开始抓取 Cloudflare IP ...")
	fullData, err := fetchCloudflareIPs(cloudflareURL)
	if err != nil {
		log.Fatalf("抓取失败: %v", err)
	}

	output := OutputData{
		GeneratedAt:  time.Now().Format("2006-01-02 15:04:05"),
		FullDataList: fullData,
		BestIP:       make(map[string]interface{}),
	}

	// 选择最优 IP
	for line, entries := range fullData {
		if len(entries) > 0 {
			output.BestIP[line] = entries[0].IP
		}
	}

	dataBytes, _ := json.MarshalIndent(output, "", "  ")
	jsonFile := "cloudflare_ips.json"
	os.WriteFile(jsonFile, dataBytes, 0644)
	fmt.Printf("✅ JSON 文件已生成: %s\n", jsonFile)

	// 华为云 DNS 客户端
	auth := basic.NewCredentialsBuilder().
		WithAk(cfg.AccessKey).
		WithSk(cfg.SecretKey).
		WithProjectId(cfg.ProjectID).
		Build()

	client := dns.NewDnsClient(
		dns.DnsClientBuilder().
			WithRegion(cfg.Region).
			WithCredential(auth),
	)

	// 更新三网 A 记录
	for line, recordID := range cfg.ARecord {
		ips := []string{}
		if entries, ok := fullData[line]; ok && len(entries) > 0 {
			for _, e := range entries {
				ips = append(ips, e.IP)
			}
		}
		if len(ips) == 0 {
			fmt.Printf("❌ %s DNS 更新失败: 无 IP\n", line)
			continue
		}

		reqBody := &model.UpdateRecordSetReq{
			Name:    cfg.Subdomain + "." + cfg.Domain + ".",
			Type:    "A",
			Records: ips,
			Ttl:     1,
		}

		req := &model.UpdateRecordSetRequest{
			ZoneId:      cfg.ZoneID,
			RecordsetId: recordID,
			Body:        reqBody,
		}

		_, err := client.UpdateRecordSet(req)
		if err != nil {
			fmt.Printf("❌ %s DNS 更新失败: %v\n", line, err)
			continue
		}
		fmt.Printf("✅ %s DNS 已更新: %v\n", line, ips)
	}
}

// 抓取 Cloudflare IP 页面
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
