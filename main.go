package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"golang.org/x/net/html"
	"io/ioutil"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"
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
	BestIP       map[string]IPEntry    `json:"最优IP推荐"`
	FullDataList map[string][]IPEntry  `json:"完整数据列表"`
}

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

func main() {
	url := "https://www.cloudflare.com/zh-cn/ips/"
	fullData, err := fetchCloudflareIPs(url)
	if err != nil {
		fmt.Println("❌ 抓取 Cloudflare IP 失败:", err)
		return
	}

	output := OutputData{
		GeneratedAt:  time.Now().Format("2006/01/02 15:04:05"),
		BestIP:       make(map[string]IPEntry),
		FullDataList: fullData,
	}

	// 按延迟和速度选出每条线路的最优 IP
	for line, entries := range fullData {
		if len(entries) > 0 {
			output.BestIP[line] = entries[0]
		}
	}

	data, _ := json.MarshalIndent(output, "", "  ")
	ioutil.WriteFile("cloudflare_ips.json", data, 0644)
	fmt.Println("✅ JSON 文件已生成: cloudflare_ips.json")

	// 模拟 DNS 更新逻辑
	huawei := HuaweiDNSConfig{
		ProjectID:  os.Getenv("HW_PROJECT_ID"),
		AccessKey:  os.Getenv("HW_AK"),
		SecretKey:  os.Getenv("HW_SK"),
		Region:     os.Getenv("HW_REGION"),
		ZoneID:     os.Getenv("HW_ZONE_ID"),
		Domain:     os.Getenv("HW_DOMAIN_NAME"),
		Subdomain:  os.Getenv("HW_SUBDOMAIN"),
		ARecord:    make(map[string]string),
		AAAARecord: make(map[string]string),
	}

	for line, entry := range output.BestIP {
		if entry.IP == "" {
			fmt.Printf("❌ %s DNS 更新失败: 未知运营商或无 IP\n", line)
			continue
		}

		if strings.Contains(entry.IP, ":") { // IPv6
			huawei.AAAARecord[line] = entry.IP
		} else { // IPv4
			huawei.ARecord[line] = entry.IP
		}

		// 这里只是打印模拟，不调用真实 API
		fmt.Printf("✅ %s 更新 %s => %s\n", line, huawei.Subdomain, entry.IP)
	}

	fmt.Println("✅ DNS 更新完成。")
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

	// 按延迟升序、速度降序排序
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
