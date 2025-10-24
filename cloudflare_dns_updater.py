import os
import json
import time
import requests
from lxml import html
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions
from huaweicloudsdkdns.v2 import DnsClient, UpdateRecordSetRequest, UpdateRecordSetRequestBody

# ================== 配置 ==================
HUAWEI_PROJECT_ID = os.getenv("HUAWEI_PROJECT_ID")
HUAWEI_ACCESS_KEY = os.getenv("HUAWEI_ACCESS_KEY")
HUAWEI_SECRET_KEY = os.getenv("HUAWEI_SECRET_KEY")
HUAWEI_REGION = os.getenv("HUAWEI_REGION")
ZONE_ID = os.getenv("ZONE_ID")
DOMAIN = os.getenv("DOMAIN")
SUBDOMAIN = os.getenv("SUBDOMAIN")

A_RECORDS = {
    "电信": os.getenv("CT_A_ID"),
    "联通": os.getenv("CU_A_ID"),
    "移动": os.getenv("CM_A_ID"),
}

CLOUDFLARE_URL = "https://www.cloudflare.com/ips-v4/"  # 示例，可替换为你的表格 URL

# ================== 抓取 Cloudflare IP ==================
def fetch_cloudflare_ips(url):
    resp = requests.get(url)
    resp.raise_for_status()
    tree = html.fromstring(resp.text)

    # 假设网页有 table.table-striped
    table = tree.xpath('//table[contains(@class,"table-striped")]')[0]
    rows = table.xpath('.//tbody/tr')

    full_data = {}
    for row in rows:
        tds = row.xpath('./td')
        if len(tds) < 8:
            continue
        entry = {
            "Line": tds[1].text_content().strip(),
            "IP": tds[2].text_content().strip(),
            "Packet": tds[3].text_content().strip(),
            "Latency": float(tds[4].text_content().replace("ms","").strip()),
            "Speed": float(tds[5].text_content().replace("mb/s","").strip()),
            "Bandwidth": tds[6].text_content().strip(),
            "Time": tds[8].text_content().strip()
        }
        full_data.setdefault(entry["Line"], []).append(entry)

    # 按延迟升序、速度降序排序
    for k in full_data:
        full_data[k].sort(key=lambda x: (x["Latency"], -x["Speed"]))

    return full_data

# ================== 初始化华为云 DNS 客户端 ==================
def get_dns_client():
    credentials = BasicCredentials(HUAWEI_ACCESS_KEY, HUAWEI_SECRET_KEY, HUAWEI_PROJECT_ID)
    client = DnsClient.new_builder() \
        .with_credentials(credentials) \
        .with_region(HUAWEI_REGION) \
        .build()
    return client

# ================== 更新 DNS ==================
def update_dns(client, line, record_id, ips):
    if not ips:
        print(f"❌ {line} DNS 更新失败: 无 IP")
        return
    name = f"{SUBDOMAIN}.{DOMAIN}."
    body = UpdateRecordSetRequestBody(
        name=name,
        type="A",
        ttl=1,
        records=ips
    )
    req = UpdateRecordSetRequest(zone_id=ZONE_ID, recordset_id=record_id, body=body)
    try:
        client.update_record_set(req)
        print(f"✅ {line} DNS 已更新: {ips}")
    except exceptions.ClientRequestException as e:
        print(f"❌ {line} DNS 更新失败: {e}")

# ================== 主流程 ==================
def main():
    print("🚀 开始抓取 Cloudflare 三网 IP ...")
    full_data = fetch_cloudflare_ips(CLOUDFLARE_URL)

    output = {
        "生成时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "完整数据列表": full_data,
        "最优IP推荐": {k: v[0]["IP"] for k, v in full_data.items() if v}
    }

    json_file = "cloudflare_ips.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 文件已生成: {json_file}")

    client = get_dns_client()

    for line, record_id in A_RECORDS.items():
        ips = [entry["IP"] for entry in full_data.get(line, [])]
        update_dns(client, line, record_id, ips)

if __name__ == "__main__":
    main()
