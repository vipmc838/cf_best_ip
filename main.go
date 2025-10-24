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

	"github.com/PuerkitoBio/goquery"
)

// ===== 数据结构 =====
type RowData struct {
	线路   string `json:"线路"`
	优选IP string `json:"优选IP"`
	丢包   string `json:"丢包"`
	延迟   string `json:"延迟"`
	速度   string `json:"速度"`
	带宽   string `json:"带宽"`
	时间   string `json:"时间"`

	latency float64
	speed   float64
}

type OutputJSON struct {
	生成时间      string                 `json:"生成时间"`
	最优IP推荐    map[string]string      `json:"最优IP推荐"`
	完整数据列表 map[string][]RowData   `json:"完整数据列表"`
}

type HuaweiConfig struct {
	Enabled   bool
	ProjectID string
	AccessKey string
	SecretKey string
	Region    string
	ZoneID    string
	Domain    string
	Subdomain string
	ARecord   map[string]string // 线路 -> A记录ID
	AAAARecord map[string]string // 线路 -> AAAA记录ID
}

// ===== 工具函数 =====
func parseFloat(s string) float64 {
	var val float64
	fmt.Sscanf(s, "%f", &val)
	return val
}

// ===== 抓取网页并解析三网 IP =====
func fetchAndParseData(url string) (map[string][]RowData, map[string]string, error) {
	ipMap := make(map[string][]RowData)
	bestIp := make(map[string]string)

	client := &http.Client{Timeout: 15 * time.Second}
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("User-Agent", "GitHubActionsBot/1.0")
	resp, err := client.Do(req)
	if err != nil {
		return nil, nil, fmt.Errorf("请求网页失败: %v", err)
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, nil, fmt.Errorf("解析 HTML 失败: %v", err)
	}

	table := doc.Find("table.table.table-striped")
	if table.Length() == 0 {
		return nil, nil, fmt.Errorf("未找到目标表格")
	}

	table.Find("tr").Slice(1, goquery.ToEnd).Each(func(i int, s *goquery.Selection) {
		tds := s.Find("th, td")
		if tds.Length() < 9 {
			return
		}

		row := RowData{
			线路:   strings.TrimSpace(tds.Eq(1).Text()),
			优选IP: strings.TrimSpace(tds.Eq(2).Text()),
			丢包:  strings.TrimSpace(tds.Eq(3).Text()),
			延迟:  strings.TrimSpace(tds.Eq(4).Text()),
			速度:  strings.TrimSpace(tds.Eq(5).Text()),
			带宽:  strings.TrimSpace(tds.Eq(6).Text()),
			时间:  strings.TrimSpace(tds.Eq(8).Text()),
		}

		row.latency = parseFloat(strings.TrimSuffix(row.延迟, "ms"))
		row.speed = parseFloat(strings.TrimSuffix(row.速度, "mb/s"))

		ipMap[row.线路] = append(ipMap[row.线路], row)
	})

	// 挑选最优IP (丢包0%，延迟最低、速度最高)
	for line, rows := range ipMap {
		filter := make([]RowData, 0)
		for _, r := range rows {
			if r.丢包 == "0.00%" {
				filter = append(filter, r)
			}
		}
		if len(filter) == 0 {
			continue
		}

		sort.Slice(filter, func(i, j int) bool {
			if filter[i].latency != filter[j].latency {
				return filter[i].latency < filter[j].latency
			}
			return filter[i].speed > filter[j].speed
		})

		best := filter[0]
		bestIp[line] = best.优选IP

		// 删除临时字段
		for idx := range ipMap[line] {
			ipMap[line][idx].latency = 0
			ipMap[line][idx].speed = 0
		}
	}

	return ipMap, bestIp, nil
}

// ===== 华为云 API 更新 DNS =====
func updateHuaweiDNS(cfg HuaweiConfig, line string, ip string, recordType string) error {
	recordID := ""
	if recordType == "A" {
		recordID = cfg.ARecord[line]
	} else {
		recordID = cfg.AAAARecord[line]
	}
	if recordID == "" {
		log.Printf("⚠️ 线路 %s 的 %s 记录ID为空，跳过", line, recordType)
		return nil
	}

	url := fmt.Sprintf("https://dns.myhuaweicloud.com/v2/%s/zones/%s/recordsets/%s", cfg.ProjectID, cfg.ZoneID, recordID)

	bodyMap := map[string]interface{}{
		"name": fmt.Sprintf("%s.%s.", cfg.Subdomain, cfg.Domain),
		"type": recordType,
		"records": []string{ip},
		"ttl": 1,
	}
	bodyJSON, _ := json.Marshal(bodyMap)

	req, _ := http.NewRequest("PUT", url, bytes.NewReader(bodyJSON))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Auth-Token", cfg.AccessKey) // 简化示例，实际可使用AK/SK签名

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("请求失败: %v", err)
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode >= 300 {
		return fmt.Errorf("更新失败: %s", string(respBody))
	}

	log.Printf("✅ 成功更新 %s 线路 %s 为 %s", line, recordType, ip)
	return nil
}

func main() {
	outputFile := "cloudflare_ips.json"
	if envFile := os.Getenv("OUTPUT_FILE"); envFile != "" {
		outputFile = envFile
	}

	url := "https://api.uouin.com/cloudflare.html"
	log.Println("🚀 抓取网页并解析三网 Cloudflare IP ...")
	fullData, bestIp, err := fetchAndParseData(url)
	if err != nil {
		log.Fatalf("❌ 解析失败: %v", err)
	}

	// ===== 华为云 DNS 配置 =====
	cfg := HuaweiConfig{
		Enabled:   true,
		ProjectID: os.Getenv("HUAWEI_PROJECT_ID"),
		AccessKey: os.Getenv("HUAWEI_ACCESS_KEY"),
		SecretKey: os.Getenv("HUAWEI_SECRET_KEY"),
		Region:    "cn-north-4",
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

	if cfg.Enabled {
		for line, ip := range bestIp {
			if ip == "" {
				log.Printf("⚠️ [%s] 未找到有效 IP，跳过更新", line)
				continue
			}
			if err := updateHuaweiDNS(cfg, line, ip, "A"); err != nil {
				log.Printf("❌ 更新 A 记录失败: %v", err)
			}
			if err := updateHuaweiDNS(cfg, line, ip, "AAAA"); err != nil {
				log.Printf("❌ 更新 AAAA 记录失败: %v", err)
			}
		}
	}

	// 写入 JSON
	out := OutputJSON{
		生成时间:      time.Now().Format(time.RFC3339),
		最优IP推荐:    bestIp,
		完整数据列表: fullData,
	}
	data, _ := json.MarshalIndent(out, "", "    ")
	if err := os.WriteFile(outputFile, data, 0644); err != nil {
		log.Fatalf("❌ 写入文件失败: %v", err)
	}

	// GitHub Actions 输出
	if githubOutput := os.Getenv("GITHUB_OUTPUT"); githubOutput != "" {
		b, _ := json.Marshal(bestIp)
		os.WriteFile(githubOutput, []byte(fmt.Sprintf("best_ip_json=%s\n", string(b))), 0644)
	}

	fmt.Printf("✅ DNS 更新完成，数据已保存到 %s\n", outputFile)
}
