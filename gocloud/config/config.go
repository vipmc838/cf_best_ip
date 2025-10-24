package config

import (
    "os"
)

type HuaweiConfig struct {
    Enabled    bool
    ProjectID  string
    AccessKey  string
    SecretKey  string
    Region     string
}

type Line struct {
    Operator         string
    ARecordsetID     string
    AAAARecordsetID  string
    Cap              int
}

type DNSConfig struct {
    ZoneId    string
    Domain    string
    Subdomain string
    TTL       int
    Lines     []Line
}

type Config struct {
    Huawei HuaweiConfig
    DNS    DNSConfig
}

// 从环境变量加载配置
func Load() (*Config, error) {
    cfg := &Config{
        Huawei: HuaweiConfig{
            Enabled:   true,
            ProjectID: os.Getenv("HUAWEI_PROJECT_ID"),
            AccessKey: os.Getenv("HUAWEI_ACCESS_KEY"),
            SecretKey: os.Getenv("HUAWEI_SECRET_KEY"),
            Region:    "cn-north-4",
        },
        DNS: DNSConfig{
            ZoneId:    os.Getenv("HUAWEI_ZONE_ID"),
            Domain:    os.Getenv("HUAWEI_DOMAIN"),
            Subdomain: os.Getenv("HUAWEI_SUBDOMAIN"),
            TTL:       1,
            Lines: []Line{
                {Operator: "ct", ARecordsetID: os.Getenv("HUAWEI_CT_A_ID"), AAAARecordsetID: os.Getenv("HUAWEI_CT_AAAA_ID"), Cap: 2},
                {Operator: "cu", ARecordsetID: os.Getenv("HUAWEI_CU_A_ID"), AAAARecordsetID: os.Getenv("HUAWEI_CU_AAAA_ID"), Cap: 2},
                {Operator: "cm", ARecordsetID: os.Getenv("HUAWEI_CM_A_ID"), AAAARecordsetID: os.Getenv("HUAWEI_CM_AAAA_ID"), Cap: 2},
            },
        },
    }
    return cfg, nil
}
