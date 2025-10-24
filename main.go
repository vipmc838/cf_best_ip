package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"golang.org/x/net/html"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"

	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
)

// IPEntry 表示单个 IP 信息
type IPEntry struct {
	IP        string  `json:"优选IP"`
	Line      string  `json:"线路"`
	Latency   float64 `json:"延迟"`
	Speed     float64 `json:"速度"`
	Packet    string  `json:"丢包"`
	Bandwidth string  `json:"带宽"`
	Time      string  `json:"时间"`
}

// OutputData 表示最终 JSON 输出结构
type OutputData struct {
	GeneratedAt  string                 `json:"生成时间"`
	BestIP       map[string]interface{} `json:"最优IP推荐"`
	FullDataList map[string][]IPEntry   `json:"完整数据列表"`
}

// HuaweiDNSConfig 配置
type HuaweiDNSConfig struct {
	ProjectID  string
	AccessKey  string
	SecretKey  string
	Region     string
	ZoneID     string
	Domain     string
	Subdomain  string
	ARecord    map[string]string
	AAAARecord map[string]string
}

// 获取 Cloudflare IP
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

	// 按延迟升序，速度降序排序
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

// 更新华为云 DNS
func updateHuaweiDNS(cfg HuaweiDNSConfig, line string, ips []string) error {
	auth := basic.NewCredentialsBuilder().
		WithAk(cfg.AccessKey).
		WithSk(cfg.SecretKey).
		WithProjectId(cfg.ProjectID).
		Build()

	client := v2.NewDnsClient(
		v2.DnsClientBuilder().
			WithRegion(core.RegionValue(cfg.Region)).
			WithCredential(auth),
	)

	recordID := ""
	if line == "电信" {
		recordID = cfg.ARecord["ct"]
	} else if line == "联通" {
		recordID = cfg.ARecord["cu"]
	} else if line == "移动" {
		recordID = cfg.ARecord["cm"]
	} else {
		return fmt.Errorf("未知运营商: %s", line)
	}

	req := &model.UpdateRecordSetRequest{
		RecordsetId: recordID,
		ZoneId:      cfg.ZoneID,
		UpdateRecordSet: &model.UpdateRecordSetReq{
			Name:    cfg.Subdomain + "." + cfg.Domain + ".",
			Type:    "A",
			Records: ips,
			Ttl:     1,
		},
	}

	_, err := client.UpdateRecordSet(req)
	return err
}

func main() {
	url := "https://www.cloudflare.com/zh-cn/ips/"
	data, err := fetchCloudflareIPs(url)
	if err != nil {
		log.Fatalf("抓取 Cloudflare IP 失败: %v", err)
	}

	// 输出 JSON
	output := OutputData{
		GeneratedAt:  fmt.Sprintf("%v", os.Args),
		FullDataList: data,
	}
	file, _ := json.MarshalIndent(output, "", "  ")
	_ = ioutil.WriteFile("cloudflare_ips.json", file, 0644)
	log.Println("✅ JSON 文件已生成: cloudflare_ips.json")

	// 配置华为云 DNS
	cfg := HuaweiDNSConfig{
		ProjectID: os.Getenv("HUAWEI_PROJECT_ID"),
		AccessKey: os.Getenv("HUAWEI_ACCESS_KEY"),
		SecretKey: os.Getenv("HUAWEI_SECRET_KEY"),
		Region:    os.Getenv("HUAWEI_REGION"),
		ZoneID:    os.Getenv("ZONE_ID"),
		Domain:    os.Getenv("DOMAIN"),
		Subdomain: os.Getenv("SUBDOMAIN"),
		ARecord: map[string]string{
			"ct": os.Getenv("CT_A_ID"),
			"cu": os.Getenv("CU_A_ID"),
			"cm": os.Getenv("CM_A_ID"),
		},
	}

	for line, list := range data {
		if len(list) == 0 {
			continue
		}
		bestIPs := []string{}
		for _, ip := range list {
			bestIPs = append(bestIPs, ip.IP)
		}
		err := updateHuaweiDNS(cfg, line, bestIPs)
		if err != nil {
			log.Printf("❌ %s DNS 更新失败: %v", line, err)
		} else {
			log.Printf("✅ %s DNS 已更新: %v", line, bestIPs)
		}
	}

	log.Println("✅ DNS 更新完成。")
}
