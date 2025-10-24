package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"golang.org/x/net/html"
)

type IPEntry struct {
	IP       string `json:"优选IP"`
	Line     string `json:"线路"`
	Latency  float64
	Speed    float64
	Packet   string `json:"丢包"`
	Bandwidth string `json:"带宽"`
	Time     string `json:"时间"`
}

type OutputData struct {
	GeneratedAt  string                 `json:"生成时间"`
	BestIP       map[string]interface{} `json:"最优IP推荐"`
	FullDataList map[string][]IPEntry   `json:"完整数据列表"`
}

type HuaweiDNSConfig struct {
	ProjectID    string
	AccessKey    string
	SecretKey    string
	Region       string
	ZoneID       string
	Domain       string
	Subdomain    string
	ARecord      map[string]string
	AAAARecord   map[string]string
}

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

func updateHuaweiDNS(cfg HuaweiDNSConfig, line string, ipType string, ips []string) error {
	// 华为云 DNS API v2：更新记录集
	recordSetID := ""
	if ipType == "A" {
		recordSetID = cfg.ARecord[line]
	} else {
		recordSetID = cfg.AAAARecord[line]
	}
	if recordSetID == "" || len(ips) == 0 {
		log.Printf("⚠️ %s-%s 无可用 IP 或未配置记录集 ID，跳过。", line, ipType)
		return nil
	}

	url := fmt.Sprintf("https://dns.%s.myhuaweicloud.com/v2/zones/%s/recordsets/%s", cfg.Region, cfg.ZoneID, recordSetID)
	bodyMap := map[string]interface{}{
		"records": ips,
	}
	bodyBytes, _ := json.Marshal(bodyMap)

	req, err := http.NewRequest("PUT", url, bytes.NewReader(bodyBytes))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(cfg.AccessKey, cfg.SecretKey)

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		data, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("更新失败: %s", string(data))
	}
	return nil
}

func main() {
	outputFile := os.Getenv("OUTPUT_FILE")
	url := "https://api.uouin.com/cloudflare.html"

	fullData, err := fetchCloudflareIPs(url)
	if err != nil {
		log.Println("抓取失败:", err)
		return
	}

	bestIP := map[string]interface{}{}
	for _, line := range []string{"电信", "联通", "移动"} {
		if entries, ok := fullData[line]; ok && len(entries) > 0 {
			bestIP[line] = map[string]string{
				"优选IP": entries[0].IP,
				"带宽":   entries[0].Bandwidth,
				"时间":   entries[0].Time,
			}
		}
	}

	out := OutputData{
		GeneratedAt:  time.Now().Format(time.RFC3339),
		BestIP:       bestIP,
		FullDataList: fullData,
	}

	jsonBytes, _ := json.MarshalIndent(out, "", "    ")
	if err := os.WriteFile(outputFile, jsonBytes, 0644); err != nil {
		log.Println("写入 JSON 文件失败:", err)
		return
	}
	log.Println("✅ JSON 文件已生成:", outputFile)

	// 读取华为云配置
	cfg := HuaweiDNSConfig{
		ProjectID: os.Getenv("HUAWEI_PROJECT_ID"),
		AccessKey: os.Getenv("HUAWEI_ACCESS_KEY"),
		SecretKey: os.Getenv("HUAWEI_SECRET_KEY"),
		Region:    "ap-southeast-1",
		ZoneID:    os.Getenv("ZONE_ID"),
		Domain:    os.Getenv("DOMAIN"),
		Subdomain: os.Getenv("SUBDOMAIN"),
		ARecord: map[string]string{
			"电信": os.Getenv("CT_A_ID"),
			"联通": os.Getenv("CU_A_ID"),
			"移动": os.Getenv("CM_A_ID"),
		},
		AAAARecord: map[string]string{
			"电信": os.Getenv("CT_AAAA_ID"),
			"联通": os.Getenv("CU_AAAA_ID"),
			"移动": os.Getenv("CM_AAAA_ID"),
		},
	}

	// 调用华为云 API 更新 DNS
	for _, line := range []string{"电信", "联通", "移动"} {
		if entries, ok := fullData[line]; ok && len(entries) > 0 {
			var ips []string
			for _, e := range entries {
				ips = append(ips, e.IP)
			}
			if strings.Contains(ips[0], ":") {
				_ = updateHuaweiDNS(cfg, line, "AAAA", ips)
			} else {
				_ = updateHuaweiDNS(cfg, line, "A", ips)
			}
			log.Printf("✅ %s DNS 已更新: %v", line, ips)
		} else {
			log.Printf("⚠️ %s 未抓取到有效 IP", line)
		}
	}
}
