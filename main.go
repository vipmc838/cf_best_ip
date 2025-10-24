package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	dns "github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
)

type LineResult struct {
	Active []struct {
		IP string `json:"ip"`
	} `json:"active"`
}

type CloudflareData struct {
	CT []string `json:"ct"`
	CU []string `json:"cu"`
	CM []string `json:"cm"`
}

func fetchCloudflareIPs() (*CloudflareData, error) {
	resp, err := http.Get("https://api.uouin.com/cloudflare.html")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := ioutil.ReadAll(resp.Body)

	var data CloudflareData
	if err := json.Unmarshal(body, &data); err != nil {
		return nil, err
	}
	return &data, nil
}

func saveJSON(data *CloudflareData, filename string) error {
	bs, err := json.MarshalIndent(data, "", "    ")
	if err != nil {
		return err
	}
	return ioutil.WriteFile(filename, bs, 0644)
}

func updateHuaweiDNS(client *dns.DnsClient, zoneID, recordsetID, recordType, fullName string, ips []string) error {
	var records []model.CreateRecordSetReq
	for _, ip := range ips {
		records = append(records, model.CreateRecordSetReq{
			Line:    "default",
			Type:    recordType,
			Name:    fullName,
			Records: []string{ip},
			TTL:     1,
		})
	}

	req := &model.UpdateRecordSetRequest{
		ZoneId:      zoneID,
		RecordsetId: recordsetID,
		Body: &model.UpdateRecordSetReq{
			Name:    fullName,
			Type:    recordType,
			Records: ips,
			TTL:     1,
		},
	}

	_, err := client.UpdateRecordSet(req)
	return err
}

func main() {
	log.Println("🚀 开始抓取 Cloudflare 三网 IP...")

	data, err := fetchCloudflareIPs()
	if err != nil {
		log.Fatalf("抓取失败: %v", err)
	}

	if err := saveJSON(data, "cloudflare_ips.json"); err != nil {
		log.Fatalf("保存 JSON 失败: %v", err)
	}
	log.Println("✅ JSON 文件已生成: cloudflare_ips.json")

	auth := basic.NewCredentialsBuilder().
		WithAk(os.Getenv("HUAWEI_ACCESS_KEY")).
		WithSk(os.Getenv("HUAWEI_SECRET_KEY")).
		WithProjectId(os.Getenv("HUAWEI_PROJECT_ID")).
		Build()

	client := dns.NewDnsClient(
		dns.DnsClientBuilder().WithRegion(dns.RegionValue(os.Getenv("HUAWEI_REGION"))).WithCredential(auth),
	)

	zoneID := os.Getenv("ZONE_ID")
	subdomain := os.Getenv("SUBDOMAIN")
	domain := os.Getenv("DOMAIN")

	operatorMap := map[string][]string{
		"ct": data.CT,
		"cu": data.CU,
		"cm": data.CM,
	}

	recordIDMap := map[string]struct {
		A    string
		AAAA string
	}{
		"ct": {A: os.Getenv("CT_A_ID"), AAAA: os.Getenv("CT_AAAA_ID")},
		"cu": {A: os.Getenv("CU_A_ID"), AAAA: os.Getenv("CU_AAAA_ID")},
		"cm": {A: os.Getenv("CM_A_ID"), AAAA: os.Getenv("CM_AAAA_ID")},
	}

	for op, ips := range operatorMap {
		if len(ips) == 0 {
			log.Printf("⚠️ [%s] 未找到有效 IP，跳过。", op)
			continue
		}

		fullName := fmt.Sprintf("%s.%s.", subdomain, domain)
		// 更新 A 记录
		if recordIDMap[op].A != "" {
			if err := updateHuaweiDNS(client, zoneID, recordIDMap[op].A, "A", fullName, ips); err != nil {
				log.Printf("[error] 更新 %s A 记录失败: %v", op, err)
			} else {
				log.Printf("✅ %s DNS 已更新: %v", strings.ToUpper(op), ips)
			}
		}
		// 更新 AAAA 记录
		if recordIDMap[op].AAAA != "" {
			if err := updateHuaweiDNS(client, zoneID, recordIDMap[op].AAAA, "AAAA", fullName, ips); err != nil {
				log.Printf("[error] 更新 %s AAAA 记录失败: %v", op, err)
			} else {
				log.Printf("✅ %s DNS AAAA 已更新: %v", strings.ToUpper(op), ips)
			}
		}
	}

	log.Println("✅ 所有 DNS 更新任务完成。")
}
