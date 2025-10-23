package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"gocloud/dns"
	"gocloud/updater"
	"gocloud/config"
)

// IPItem 用于存储每条 IP 信息
type IPItem struct {
	IP string `json:"优选IP"`
}

// LineResult 存储单线路 IP
type LineResult struct {
	Active []IPItem
}

// LoadConfig 读取配置文件
func LoadConfig(path string) *config.Config {
	b, err := ioutil.ReadFile(path)
	if err != nil {
		log.Fatalf("读取配置文件失败: %v", err)
	}
	cfg := &config.Config{}
	if err := yaml.Unmarshal(b, cfg); err != nil {
		log.Fatalf("解析配置文件失败: %v", err)
	}
	return cfg
}

// 获取三网 IP 并返回 map
func FetchCloudflareIPs() map[string]LineResult {
	resp, err := http.Get("https://api.uouin.com/cloudflare.html?format=json")
	if err != nil {
		log.Fatalf("获取 Cloudflare IP 失败: %v", err)
	}
	defer resp.Body.Close()

	body, _ := ioutil.ReadAll(resp.Body)
	var data map[string]interface{}
	if err := json.Unmarshal(body, &data); err != nil {
		log.Fatalf("解析 Cloudflare JSON 失败: %v", err)
	}

	selected := make(map[string]LineResult)
	fullList := data["完整数据列表"].(map[string]interface{})
	opMap := map[string]string{"电信": "ct", "联通": "cu", "移动": "cm"}

	for opName, arr := range fullList {
		code, ok := opMap[opName]
		if !ok {
			continue
		}
		items := arr.([]interface{})
		var line LineResult
		for _, item := range items {
			ip := item.(map[string]interface{})["优选IP"].(string)
			line.Active = append(line.Active, IPItem{IP: ip})
		}
		selected[fmt.Sprintf("%s-v4", code)] = line
	}

	return selected
}

func main() {
	cfg := LoadConfig("config.yml")
	selected := FetchCloudflareIPs()

	updateCount, err := updater.UpdateAll(selected, cfg)
	if err != nil {
		log.Fatalf("更新失败: %v", err)
	}
	log.Printf("成功更新 %d 条 DNS 记录", updateCount)
}
