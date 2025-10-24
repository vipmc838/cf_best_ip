package main

import (
    "encoding/json"
    "fmt"
    "io"
    "log"
    "net/http"
    "os"
    "strings"

    dns "github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2"
    "github.com/huaweicloud/huaweicloud-sdk-go-v3/services/dns/v2/model"
    "github.com/huaweicloud/huaweicloud-sdk-go-v3/core/auth/basic"
)

type LineIPs struct {
    A    []string `json:"A"`
    AAAA []string `json:"AAAA"`
}

type AllIPs struct {
    CT LineIPs `json:"ct"`
    CU LineIPs `json:"cu"`
    CM LineIPs `json:"cm"`
}

func fetchIPs() (*AllIPs, error) {
    resp, err := http.Get("https://api.uouin.com/cloudflare.html")
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, err
    }
    htmlContent := string(body)

    result := &AllIPs{}

    lines := strings.Split(htmlContent, "\n")
    for _, line := range lines {
        line = strings.TrimSpace(line)
        if strings.Contains(line, "<td>ct</td>") {
            ip := extractIP(line)
            if ip != "" {
                result.CT.A = append(result.CT.A, ip)
            }
        } else if strings.Contains(line, "<td>cu</td>") {
            ip := extractIP(line)
            if ip != "" {
                result.CU.A = append(result.CU.A, ip)
            }
        } else if strings.Contains(line, "<td>cm</td>") {
            ip := extractIP(line)
            if ip != "" {
                result.CM.A = append(result.CM.A, ip)
            }
        }
    }

    return result, nil
}

func extractIP(line string) string {
    start := strings.Index(line, "<td>")
    end := strings.Index(line[start+4:], "</td>")
    if start >= 0 && end >= 0 {
        return strings.TrimSpace(line[start+4 : start+4+end])
    }
    return ""
}

func strPtr(s string) *string {
    return &s
}

func int32Ptr(i int32) *int32 {
    return &i
}

func updateHuaweiDNS(client *dns.DnsClient, zoneID, recordsetID, recordType string, ips []string, subdomain, domain string) error {
    fullName := fmt.Sprintf("%s.%s.", subdomain, domain)
    req := &model.UpdateRecordSetReq{
        Name:    strPtr(fullName),
        Type:    strPtr(recordType),
        Records: &ips,
        Ttl:     int32Ptr(1),
    }
    _, err := client.UpdateRecordSet(&model.UpdateRecordSetRequest{
        ZoneId:      zoneID,
        RecordsetId: recordsetID,
        Body:        req,
    })
    return err
}

func main() {
    zoneID := os.Getenv("ZONE_ID")
    domain := os.Getenv("DOMAIN")
    subdomain := os.Getenv("SUBDOMAIN")

    ctA := os.Getenv("CT_A_ID")
    cuA := os.Getenv("CU_A_ID")
    cmA := os.Getenv("CM_A_ID")
    ctAAAA := os.Getenv("CT_AAAA_ID")
    cuAAAA := os.Getenv("CU_AAAA_ID")
    cmAAAA := os.Getenv("CM_AAAA_ID")

    ak := os.Getenv("HUAWEI_ACCESS_KEY")
    sk := os.Getenv("HUAWEI_SECRET_KEY")
    projectID := os.Getenv("HUAWEI_PROJECT_ID")

    creds := basic.NewCredentialsBuilder().
        WithAk(ak).
        WithSk(sk).
        WithProjectId(projectID).
        Build()

    client := dns.NewDnsClient(
        dns.DnsClientBuilder().
            WithCredential(creds).
            WithEndpoint("https://dns.ap-southeast-1.myhuaweicloud.com").
            Build(),
    )

    ips, err := fetchIPs()
    if err != nil {
        log.Fatal("获取 IP 失败:", err)
    }

    jsonFile, _ := os.Create("cloudflare_ips.json")
    defer jsonFile.Close()
    json.NewEncoder(jsonFile).Encode(ips)
    log.Println("✅ JSON 文件已生成: cloudflare_ips.json")

    // 更新 A 记录
    if len(ips.CT.A) > 0 {
        if err := updateHuaweiDNS(client, zoneID, ctA, "A", ips.CT.A, subdomain, domain); err != nil {
            log.Println("❌ 电信 A DNS 更新失败:", err)
        } else {
            log.Println("✅ 电信 A DNS 已更新:", ips.CT.A)
        }
    }
    if len(ips.CU.A) > 0 {
        if err := updateHuaweiDNS(client, zoneID, cuA, "A", ips.CU.A, subdomain, domain); err != nil {
            log.Println("❌ 联通 A DNS 更新失败:", err)
        } else {
            log.Println("✅ 联通 A DNS 已更新:", ips.CU.A)
        }
    }
    if len(ips.CM.A) > 0 {
        if err := updateHuaweiDNS(client, zoneID, cmA, "A", ips.CM.A, subdomain, domain); err != nil {
            log.Println("❌ 移动 A DNS 更新失败:", err)
        } else {
            log.Println("✅ 移动 A DNS 已更新:", ips.CM.A)
        }
    }

    // 更新 AAAA 记录（示例用同样的 IPv4，可替换成真实 IPv6）
    if len(ips.CT.A) > 0 {
        if err := updateHuaweiDNS(client, zoneID, ctAAAA, "AAAA", ips.CT.A, subdomain, domain); err != nil {
            log.Println("❌ 电信 AAAA DNS 更新失败:", err)
        } else {
            log.Println("✅ 电信 AAAA DNS 已更新:", ips.CT.A)
        }
    }
    if len(ips.CU.A) > 0 {
        if err := updateHuaweiDNS(client, zoneID, cuAAAA, "AAAA", ips.CU.A, subdomain, domain); err != nil {
            log.Println("❌ 联通 AAAA DNS 更新失败:", err)
        } else {
            log.Println("✅ 联通 AAAA DNS 已更新:", ips.CU.A)
        }
    }
    if len(ips.CM.A) > 0 {
        if err := updateHuaweiDNS(client, zoneID, cmAAAA, "AAAA", ips.CM.A, subdomain, domain); err != nil {
            log.Println("❌ 移动 AAAA DNS 更新失败:", err)
        } else {
            log.Println("✅ 移动 AAAA DNS 已更新:", ips.CM.A)
        }
    }
}
