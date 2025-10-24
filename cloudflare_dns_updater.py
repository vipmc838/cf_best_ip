#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import json
import requests
from bs4 import BeautifulSoup
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
from huaweicloudsdkdns.v2.model import (
    RecordSet,
    CreateRecordSetRequest,
    UpdateRecordSetRequest,
    ListRecordSetsRequest
)

OUTPUT_FILE = "cloudflare_bestip.json"

class HuaWeiApi:
    def __init__(self, access_key, secret_key, region):
        self.AK = access_key
        self.SK = secret_key
        self.region = region
        self.client = DnsClient.new_builder()\
            .with_credentials(BasicCredentials(self.AK, self.SK))\
            .with_region(DnsRegion.value_of(self.region))\
            .build()
        self.zone_id = self.get_zones()

    def get_zones(self):
        zones = {}
        for zone in self.client.list_public_zones().zones:
            zones[zone.name] = zone.id
        return zones

    def get_records(self, domain, record_type='A'):
        request = ListRecordSetsRequest()
        request.zone_id = self.zone_id[domain + "."]
        request.type = record_type
        return self.client.list_record_sets(request).recordsets

    def create_record(self, domain, name, ip, record_type='A', ttl=600):
        req = CreateRecordSetRequest(
            zone_id=self.zone_id[domain + "."],
            body=RecordSet(
                name=name,
                type=record_type,
                ttl=ttl,
                records=[ip]
            )
        )
        return self.client.create_record_set(req)

    def update_record(self, domain, record_id, name, ip, record_type='A', ttl=600):
        req = UpdateRecordSetRequest(
            zone_id=self.zone_id[domain + "."],
            recordset_id=record_id,
            body=RecordSet(
                name=name,
                type=record_type,
                ttl=ttl,
                records=[ip]
            )
        )
        return self.client.update_record_set(req)

# -------------------------
# 抓取 Cloudflare IP
# -------------------------
def fetch_cloudflare_ips(url="https://api.uouin.com/cloudflare.html"):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class": "table-striped"})
    if not table:
        return {}, {}

    headers = ["#", "线路", "优选IP", "丢包", "延迟", "速度", "带宽", "Colo", "时间"]
    full_data = {}
    ip_metrics = []

    for row in table.find_all("tr")[1:]:
        cols = row.find_all(["th", "td"])
        if len(cols) != len(headers):
            continue
        entry = {}
        metrics = {}
        for i, col in enumerate(cols):
            text = col.get_text(strip=True)
            if headers[i] == "线路":
                entry["线路"] = text
            elif headers[i] == "优选IP":
                entry["IP"] = text
            elif headers[i] == "丢包":
                entry["丢包"] = text
            elif headers[i] == "延迟":
                metrics["latency"] = float(text.replace("ms",""))
                entry["延迟"] = text
            elif headers[i] == "速度":
                metrics["speed"] = float(text.replace("mb/s",""))
                entry["速度"] = text
            elif headers[i] == "带宽":
                entry["带宽"] = text
            elif headers[i] == "时间":
                entry["时间"] = text
        line = entry.get("线路")
        if line:
            full_data.setdefault(line, []).append({**entry, **metrics})
        if entry.get("丢包") == "0.00%":
            ip_metrics.append({**entry, **metrics})

    for line in full_data:
        full_data[line].sort(key=lambda x: (x["latency"], -x["speed"]))

    best_ip = {}
    if ip_metrics:
        ip_metrics.sort(key=lambda x: (x["latency"], -x["speed"]))
        best = ip_metrics[0]
        best_ip = {
            "线路": best["线路"],
            "IP": best["IP"],
            "延迟": best["延迟"],
            "速度": best["速度"],
            "带宽": best["带宽"],
            "时间": best["时间"]
        }

    return full_data, best_ip

# -------------------------
# 主程序
# -------------------------
if __name__ == "__main__":
    ak = os.environ["HUAWEI_ACCESS_KEY"]
    sk = os.environ["HUAWEI_SECRET_KEY"]
    region = os.environ["HUAWEI_REGION"]
    domain = os.environ["DOMAIN"]
    subdomain = os.environ["SUBDOMAIN"]

    hw = HuaWeiApi(ak, sk, region)
    full_data, best_ip = fetch_cloudflare_ips()

    for line, entries in full_data.items():
        ip = entries[0]["IP"]
        name = subdomain + "." + domain + "."
        records = hw.get_records(domain)
        if records:
            for record in records:
                hw.update_record(domain, record.id, name, ip)
                print(f"{line} DNS 更新成功: {ip}")
        else:
            hw.create_record(domain, name, ip)
            print(f"{line} DNS 创建成功: {ip}")

    # 保存 JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "最优IP": best_ip,
            "完整数据": full_data
        }, f, ensure_ascii=False, indent=4)
    print(f"结果已保存到 {OUTPUT_FILE}")
