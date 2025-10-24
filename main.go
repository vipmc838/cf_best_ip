package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"time"
)

// 记录结构
type LineData struct {
	IP      string `json:"ip"`
	Latency string `json:"latency"`
	Speed   string `json:"speed"`
	Line    string `json:"line"`
}

// 输出 JSON 结构
type Output struct {
	GeneratedAt string              `json:"生成时间"`
	Lines       map[string][]LineData `json:"三网IP"`
}

// 简单抓取网页并解析三网 IP
func fetchCloudflareIPs(url string) (map[string][]LineData, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := ioutil.ReadAll(resp.Body)

	// 这里简化解析：你可按实际 HTML 表格解析逻辑替换
	// 假设网页返回 JSON 格式
	var data map[string][]LineData
	if err := json.Unmarshal(body, &data); err != nil {
		return nil, err
	}
	return data, nil
}

// 保存 JSON 文件
func saveJSON(file string, output Output) error {
	data, err := json.MarshalIndent(output, "", "    ")
	if err != nil {
		return err
	}
	return ioutil.WriteFile(file, data, 0644)
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
	if err := saveJSON(file, output); err != nil {
		log.Fatalf("❌ 保存 JSON 失败: %v", err)
	}
	log.Printf("✅ 成功保存到 %s", file)

	// 此处可以调用华为云 API 更新 DNS（略，可用你现有 updater 函数）
	fmt.Println("📌 可在这里调用华为云 API 更新 DNS")
}
