package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

// 配置结构
type Config struct {
	Huawei struct {
		ProjectID string
		AccessKey string
		SecretKey string
		Region    string
	}
	DNS struct {
		ZoneID    string
		Domain    string
		Subdomain string
		CT_A_ID    string
		CU_A_ID    string
		CM_A_ID    string
		CT_AAAA_ID string
		CU_AAAA_ID string
		CM_AAAA_ID string
	}
}

// API 响应格式
type IPTable struct {
	CT []string `json:"ct"`
	CU []string `json:"cu"`
	CM []string `json:"cm"`
}

// 更新 DNS 请求结构
type UpdateRecordRequest struct {
	Name    string   `json:"name"`
	Type    string   `json:"type"`
	Records []string `json:"records"`
	TTL     int      `json:"ttl"`
}

// 更新 DNS 返回结构
type UpdateRecordResponse struct {
	ID      string   `json:"id"`
	Name    string   `json:"name"`
	Type    string   `json:"type"`
	Records []string `json:"records"`
}

func loadConfig() Config {
	var cfg Config
	cfg.Huawei.ProjectID = os.Getenv("HUAWEI_PROJECT_ID")
	cfg.Huawei.AccessKey = os.Getenv("HUAWEI_ACCESS_KEY")
	cfg.Huawei.SecretKey = os.Getenv("HUAWEI_SECRET_KEY")
	cfg.Huawei.Region = os.Getenv("HUAWEI_REGION")
	cfg.DNS.ZoneID = os.Getenv("ZONE_ID")
	cfg.DNS.Domain = os.Getenv("DOMAIN")
	cfg.DNS.Subdomain = os.Getenv("SUBDOMAIN")
	cfg.DNS.CT_A_ID = os.Getenv("CT_A_ID")
	cfg.DNS.CU_A_ID = os.Getenv("CU_A_ID")
	cfg.DNS.CM_A_ID = os.Getenv("CM_A_ID")
	cfg.DNS.CT_AAAA_ID = os.Getenv("CT_AAAA_ID")
	cfg.DNS.CU_AAAA_ID = os.Getenv("CU_AAAA_ID")
	cfg.DNS.CM_AAAA_ID = os.Getenv("CM_AAAA_ID")
	return cfg
}

// 获取 Cloudflare 三网 IP
func fetchIPs() (IPTable, error) {
	var table IPTable
	resp, err := http.Get("https://api.uouin.com/cloudflare.html")
	if err != nil {
		return table, err
	}
	defer resp.Body.Close()
	body, _ := ioutil.ReadAll(resp.Body)
	if err := json.Unmarshal(body, &table); err != nil {
		return table, err
	}
	return table, nil
}

// 调用华为云 DNS API 更新记录
func updateDNS(cfg Config, recordID, ipType string, ips []string) error {
	url := fmt.Sprintf("https://dns.%s.myhuaweicloud.com/v2/zones/%s/recordsets/%s", cfg.Huawei.Region, cfg.DNS.ZoneID, recordID)

	reqBody := UpdateRecordRequest{
		Name:    fmt.Sprintf("%s.%s", cfg.DNS.Subdomain, cfg.DNS.Domain),
		Type:    ipType,
		Records: ips,
		TTL:     1,
	}

	data, _ := json.Marshal(reqBody)
	req, _ := http.NewRequest("PUT", url, bytes.NewBuffer(data))
	req.Header.Set("Content-Type", "application/json;charset=utf8")
	req.Header.Set("X-Auth-Project-Id", cfg.Huawei.ProjectID)
	req.Header.Set("X-Auth-Token", cfg.Huawei.AccessKey) // 简化示例，可使用 AK/SK 签名方式

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	respData, _ := ioutil.ReadAll(resp.Body)
	log.Printf("更新响应: %s\n", string(respData))
	return nil
}

func main() {
	log.Println("🚀 开始抓取 Cloudflare 三网 IP ...")
	cfg := loadConfig()

	ips, err := fetchIPs()
	if err != nil {
		log.Fatal("❌ 获取 IP 失败:", err)
	}

	log.Printf("✅ 获取 IP 完成: CT=%v, CU=%v, CM=%v\n", ips.CT, ips.CU, ips.CM)

	if len(ips.CT) > 0 {
		if err := updateDNS(cfg, cfg.DNS.CT_A_ID, "A", ips.CT); err != nil {
			log.Println("❌ 电信 A 更新失败:", err)
		} else {
			log.Println("✅ 电信 A 更新成功")
		}
		if err := updateDNS(cfg, cfg.DNS.CT_AAAA_ID, "AAAA", ips.CT); err != nil {
			log.Println("❌ 电信 AAAA 更新失败:", err)
		} else {
			log.Println("✅ 电信 AAAA 更新成功")
		}
	}

	if len(ips.CU) > 0 {
		if err := updateDNS(cfg, cfg.DNS.CU_A_ID, "A", ips.CU); err != nil {
			log.Println("❌ 联通 A 更新失败:", err)
		} else {
			log.Println("✅ 联通 A 更新成功")
		}
		if err := updateDNS(cfg, cfg.DNS.CU_AAAA_ID, "AAAA", ips.CU); err != nil {
			log.Println("❌ 联通 AAAA 更新失败:", err)
		} else {
			log.Println("✅ 联通 AAAA 更新成功")
		}
	}

	if len(ips.CM) > 0 {
		if err := updateDNS(cfg, cfg.DNS.CM_A_ID, "A", ips.CM); err != nil {
			log.Println("❌ 移动 A 更新失败:", err)
		} else {
			log.Println("✅ 移动 A 更新成功")
		}
		if err := updateDNS(cfg, cfg.DNS.CM_AAAA_ID, "AAAA", ips.CM); err != nil {
			log.Println("❌ 移动 AAAA 更新失败:", err)
		} else {
			log.Println("✅ 移动 AAAA 更新成功")
		}
	}

	// 写回 JSON 文件
	outFile := "cloudflare_ips.json"
	allIPs := map[string][]string{"CT": ips.CT, "CU": ips.CU, "CM": ips.CM}
	data, _ := json.MarshalIndent(allIPs, "", "  ")
	if err := ioutil.WriteFile(outFile, data, 0644); err != nil {
		log.Println("❌ 写 JSON 文件失败:", err)
	} else {
		log.Printf("✅ JSON 文件已生成: %s\n", outFile)
	}
}
