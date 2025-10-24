import os
import json
import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.model.update_record_set_request import UpdateRecordSetRequest
from huaweicloudsdkdns.v2.model.update_record_set_request_body import UpdateRecordSetRequestBody
from huaweicloudsdkdns.v2.model.update_record_set_req import UpdateRecordSetReq

# ---------------- 配置 ----------------
ZONE_ID = os.getenv("ZONE_ID")
SUBDOMAIN = os.getenv("SUBDOMAIN")
DOMAIN = os.getenv("DOMAIN")
HUAWEI_REGION = os.getenv("HUAWEI_REGION")
CT_A_ID = os.getenv("CT_A_ID")
CU_A_ID = os.getenv("CU_A_ID")
CM_A_ID = os.getenv("CM_A_ID")

CREDENTIALS = BasicCredentials(HUAWEI_REGION, os.getenv("ACCESS_KEY"), os.getenv("SECRET_KEY"))

# Cloudflare IP 页面
CLOUDFLARE_URL = "https://api.uouin.com/cloudflare.html"

# 三网线路映射
LINE_TO_ID = {
    "电信": CT_A_ID,
    "联通": CU_A_ID,
    "移动": CM_A_ID
}

# ---------------- 抓取 Cloudflare IP ----------------
def fetch_cloudflare_ips():
    resp = requests.get(CLOUDFLARE_URL, headers={"User-Agent": "GitHubActionsBot/1.0"}, timeout=15)
    resp.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="table-striped")
    if not table:
        return {}

    full_data = {}
    headers = ["#", "线路", "优选IP", "丢包", "延迟", "速度", "带宽", "Colo", "时间"]
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all(["td", "th"])
        if len(tds) != len(headers):
            continue
        row = {headers[i]: tds[i].text.strip() for i in range(len(headers))}
        line = row["线路"]
        full_data.setdefault(line, []).append(row)
    return full_data

# ---------------- 选取最优 IP ----------------
def select_best_ip(full_data, line_name):
    ips = [r for r in full_data.get(line_name, []) if r["丢包"] == "0.00%"]
    if not ips:
        return None
    # 延迟升序、速度降序
    ips.sort(key=lambda x: (float(x["延迟"].replace("ms", "")), -float(x["速度"].replace("mb/s", ""))))
    return ips[0]["优选IP"]

# ---------------- 更新华为云 DNS ----------------
def update_huawei_dns(line_name, ip):
    if line_name not in LINE_TO_ID or not ip:
        print(f"❌ {line_name} DNS 更新失败: 无有效 IP 或未知线路")
        return

    client = DnsClient.new_builder()\
        .with_region(HUAWEI_REGION)\
        .with_credential(CREDENTIALS)\
        .build()
    
    record_id = LINE_TO_ID[line_name]

    body = UpdateRecordSetRequestBody(
        update_record_set=UpdateRecordSetReq(
            name=f"{SUBDOMAIN}.{DOMAIN}.",
            type="A",
            records=[ip],
            ttl=1
        )
    )
    req = UpdateRecordSetRequest(recordset_id=record_id, body=body)

    try:
        client.update_record_set(req)
        print(f"✅ {line_name} DNS 更新成功: {ip}")
    except Exception as e:
        print(f"❌ {line_name} DNS 更新失败: {e}")

# ---------------- 主流程 ----------------
def main():
    full_data = fetch_cloudflare_ips()
    for line in LINE_TO_ID.keys():
        best_ip = select_best_ip(full_data, line)
        update_huawei_dns(line, best_ip)

if __name__ == "__main__":
    main()
