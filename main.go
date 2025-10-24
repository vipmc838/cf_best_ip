package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"os"

	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
	"github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/dns"
)

type IPEntry struct {
	IP   string `json:"优选IP"`
	Line string `json:"线路"`
}

type OutputData struct {
	FullDataList map[string][]IPEntry `json:"完整数据列表"`
}

func main() {
	// 读取 JSON 文件
	data, err := ioutil.ReadFile("cloudflare_ips.json")
	if err != nil {
		log.Fatalf("读取 JSON 文件失败: %v", err)
	}

	var output OutputData
	if err := json.Unmarshal(data, &output); err != nil {
		log.Fatalf("解析 JSON 失败: %v", err)
	}

	// 华为云参数
	region := os.Getenv("HUAWEI_REGION")
	projectID := os.Getenv("HUAWEI_PROJECT_ID")
	accessKey := os.Getenv("HUAWEI_ACCESS_KEY")
	secretKey := os.Getenv("HUAWEI_SECRET_KEY")
	zoneID := os.Getenv("ZONE_ID")
	subdomain := os.Getenv("SUBDOMAIN")
	domain := os.Getenv("DOMAIN")

	recordIDs := map[string]string{
		"电信": os.Getenv("CT_A_ID"),
		"联通": os.Getenv("CU_A_ID"),
		"移动": os.Getenv("CM_A_ID"),
	}

	// 创建华为云认证
	auth := basic.NewCredentialsBuilder().
		WithAk(accessKey).
		WithSk(secretKey).
		WithProjectId(projectID).
		Build()

	client := dns.NewDnsClient(
		dns.DnsClientBuilder().
			WithRegion(core.RegionValue(region)).
			WithCredential(auth),
	)

	for operator, recID := range recordIDs {
		entries, ok := output.FullDataList[operator]
		if !ok || len(entries) == 0 {
			log.Printf("❌ %s DNS 更新失败: 无 IP", operator)
			continue
		}

		var ips []string
		for _, e := range entries {
			ips = append(ips, e.IP)
		}

		fullName := fmt.Sprintf("%s.%s.", subdomain, domain)

		reqBody := &model.UpdateRecordSetRequestBody{
			Name:    &fullName,
			Type:    model.UpdateRecordSetRequestTypeA,
			Records: &ips,
			Ttl:     core.Int32Ptr(1),
		}

		req := &dns.UpdateRecordSetRequest{
			ZoneId:      zoneID,
			RecordsetId: recID,
			Body:        reqBody,
		}

		_, err := client.UpdateRecordSet(req)
		if err != nil {
			log.Printf("❌ %s DNS 更新失败: %v", operator, err)
			continue
		}

		log.Printf("✅ %s DNS 已更新: %v", operator, ips)
	}

	log.Println("✅ DNS 更新完成。")
}
