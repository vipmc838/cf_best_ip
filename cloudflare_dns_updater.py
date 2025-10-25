#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 自动抓取 Cloudflare IP 并更新华为云 DNS
# 线路: 电信 / 联通 / 移动 / 多线(默认) + IPV6

import os
import json
import requests
from bs4 import BeautifulSoup
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
from huaweicloudsdkdns.v2.model import ListRecordSetsWithLineRequest, UpdateRecordSetReq, UpdateRecordSetRequest, CreateRecordSetRequest

MAX_IPS = 50

# 从环境变量读取华为云凭据和域名
AK = os.getenv("HUAWEI_ACCESS_KEY")
SK = os.getenv("HUAWEI_SECRET_KEY")
REGION = os.getenv("HUAWEI_REGION", "cn-east-3")
DOMAIN = os.getenv("DOMAIN")
SUBDOMAIN = os.getenv("SUBDOMAIN", "cf")

# 线路映射
LINE_MAPPING = {
    "电信": "Dianxin",
    "联通": "Liantong",
    "移动": "Yidong",
    "多线": "default_view"
}

IPV6_LINE = "default_view"

class HuaWeiApi:
    def __init__(self, ak, sk, region):
        self.client = DnsClient.new_builder()\
            .with_credentials(BasicCredentials(ak, sk))\
            .with_region(DnsRegion.value_of(region)).build()
        self.zone_id = self.get_zone_id(DOMAIN)

    def get_zone_id(self, domain):
        zones = self.client.list_public_zones().zones
        for z in zones:
            if z.name == domain:
                return z.id
        raise ValueError(f"未找到域名 {domain} 的 Zone ID")

    def list_records(self, subdomain, record_type="A", line=None):
        req = ListRecordSetsWithLineRequest()
        req.zone_id = self.zone_id
        req.type = record_type
        name = DOMAIN + "." if subdomain == "@" else f"{subdomain}.{DOMAIN}."
        req.name = name
        records = self.client.list_record_sets_with_line(req).recordsets
        if line:
            records = [r for r in records if r.line == line]
        return records

    def update_record(self, subdomain, record_type, line, ips, ttl=600):
        if not ips:
            print(f"{line} {record_type} 无 IP，跳过更新")
            return

        # 截取最多 MAX_IPS 个
        ips = ips[:MAX_IPS]
        existing = self.list_records(subdomain, record_type, line=line)

        name = DOMAIN + "." if subdomain == "@" else f"{subdomain}.{DOMAIN}."

        if existing:
            # 更新已有记录
            record_id = existing[0].id
            body = UpdateRecordSetReq(
                name=name,
                type=record_type,
                ttl=ttl,
                records=ips
            )
            req = UpdateRecordSetRequest()
            req.zone_id = self.zone_id
            req.recordset_id = record_id
            req.body = body
            try:
                self.client.update_record_set(req)
                print(f"{line} {record_type} 更新成功 -> {ips}")
            except Exception as e:
                print(f"{line} {record_type} 更新失败: {e}")
        else:
            # 创建新记录
            body = CreateRecordSetRequest(
                zone_id=self.zone_id,
                name=name,
                type=record_type,
                ttl=ttl,
                records=ips,
                line=line
            )
            try:
                self.client.create_record_set(body)
                print(f"{line} {record_type} 创建成功 -> {ips}")
            except Exception as e:
                print(f"{line} {record_type} 创建失败: {e}")

def fetch_cloudflare_ips():
    url = "https://api.uouin.com/cloudflare.html"
    res = requests.get(url, timeout=15, headers={"User-Agent": "GithubActions"})
    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.find("table")
    if not table:
        return {}, {}

    best = {"电信": [], "联通": [], "移动": [], "多线": [], "IPV6": []}
    full_data = {"电信": [], "联通": [], "移动": [], "多线": [], "IPV6": []}

    for row in table.find_all("tr")[1:]:
        cols = row.find_all(["th", "td"])
        if len(cols) < 10:
            continue
        line_name = cols[1].text.strip()
        ip = cols[2].text.strip()
        latency = cols[4].text.strip()
        speed = cols[5].text.strip()
        pkg_loss = cols[3].text.strip()

        if pkg_loss != "0.00%":
            continue

        # 多线归到默认
        if line_name not in best:
            line_name = "多线"

        best[line_name].append(ip)
        full_data[line_name].append({
            "IP": ip,
            "延迟": latency,
            "速度": speed
        })

    # 把 IPV6 单独归类
    # 这里假设网页里 IPV6 数据在最后一列或自定义，你可以根据实际情况调整
    ipv6_ips = [row["IP"] for row in full_data.get("多线", []) if ":" in row["IP"]]
    best["IPV6"] = ipv6_ips[:MAX_IPS]

    # 删除多线里的 IPV6
    full_data["多线"] = [r for r in full_data["多线"] if ":" not in r["IP"]]
    best["多线"] = [ip for ip in best["多线"] if ":" not in ip]

    return full_data, best

if __name__ == "__main__":
    hw = HuaWeiApi(AK, SK, REGION)
    full_data, best_ips = fetch_cloudflare_ips()

    # 更新 DNS
    for line in ["电信", "联通", "移动", "多线"]:
        hw.update_record(SUBDOMAIN, "A", LINE_MAPPING[line], best_ips.get(line, []))
    hw.update_record(SUBDOMAIN, "AAAA", LINE_MAPPING["多线"], best_ips.get("IPV6", []))

    # 保存 JSON
    output = {
        "生成时间": __import__("datetime").datetime.now().isoformat(),
        "最佳 IP": best_ips,
        "完整数据": full_data
    }
    with open("cloudflare_bestip.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    print("结果保存到 cloudflare_bestip.json")
