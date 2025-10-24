#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.model import UpdateRecordSetReq

# ===== 配置 =====
HUAWEI_PROJECT_ID = os.getenv("HUAWEI_PROJECT_ID")
HUAWEI_ACCESS_KEY = os.getenv("HUAWEI_ACCESS_KEY")
HUAWEI_SECRET_KEY = os.getenv("HUAWEI_SECRET_KEY")
HUAWEI_REGION = os.getenv("HUAWEI_REGION", "ap-southeast-1")
ZONE_ID = os.getenv("ZONE_ID")
DOMAIN = os.getenv("DOMAIN")
SUBDOMAIN = os.getenv("SUBDOMAIN")
CT_A_ID = os.getenv("CT_A_ID")
CU_A_ID = os.getenv("CU_A_ID")
CM_A_ID = os.getenv("CM_A_ID")

CLOUDFLARE_URL = "https://www.cloudflare.com/ips-v4/"  # 或你抓 IP 的页面

LINE_MAP = {
    "电信": CT_A_ID,
    "联通": CU_A_ID,
    "移动": CM_A_ID
}

# ===== 抓取 Cloudflare IP =====
def fetch_cloudflare_ips():
    resp = requests.get(CLOUDFLARE_URL, timeout=10)
    resp.raise_for_status()
    ips = [line.strip() for line in resp.text.splitlines() if line.strip()]
    return ips

# ===== 更新华为云 DNS =====
def update_huawei_dns(recordset_id, ips):
    auth = BasicCredentials(
        ak=HUAWEI_ACCESS_KEY,
        sk=HUAWEI_SECRET_KEY,
        project_id=HUAWEI_PROJECT_ID
    )
    client = DnsClient.new_builder()\
        .with_credentials(auth)\
        .with_region(HUAWEI_REGION)\
        .build()
    
    body = UpdateRecordSetReq(
        name=f"{SUBDOMAIN}.{DOMAIN}.",
        type="A",
        records=ips,
        ttl=1
    )
    resp = client.update_record_set(recordset_id=recordset_id, body=body)
    return resp

# ===== 主流程 =====
def main():
    try:
        ips = fetch_cloudflare_ips()
        print(f"✅ Cloudflare IP 已抓取: {ips}")
        # 保存 JSON
        with open("cloudflare_ips.json", "w", encoding="utf-8") as f:
            json.dump(ips, f, ensure_ascii=False, indent=2)

        # 更新三网 DNS
        for line, record_id in LINE_MAP.items():
            if not record_id:
                print(f"❌ {line} DNS ID 未配置, 跳过")
                continue
            try:
                resp = update_huawei_dns(record_id, ips)
                print(f"✅ {line} DNS 已更新: {ips}")
            except Exception as e:
                print(f"❌ {line} DNS 更新失败: {e}")

    except Exception as e:
        print(f"❌ 脚本执行失败: {e}")

if __name__ == "__main__":
    main()
