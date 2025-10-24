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
    ListRecordSetsWithLineRequest,
    CreateRecordSetWithLineReq,
    CreateRecordSetWithLineRequest,
    UpdateRecordSetReq,
    UpdateRecordSetRequest
)

OUTPUT_FILE = "cloudflare_bestip.json"

# -------------------------
# 华为云 API 封装
# -------------------------
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

    def line_format(self, line):
        lines = {
            '默认' : 'default_view',
            '电信' : 'Dianxin',
            '联通' : 'Liantong',
            '移动' : 'Yidong',
            '境外' : 'Abroad',
            'default_view' : '默认',
            'Dianxin' : '电信',
            'Liantong' : '联通',
            'Yidong' : '移动',
            'Abroad' : '境外',
        }
        return lines.get(line, None)

    def get_record(self, domain, sub_domain, record_type='A'):
        request = ListRecordSetsWithLineRequest()
        request.limit = 100
        request.type = record_type
        if sub_domain == '@':
            request.name = domain + "."
        else:
            request.name = sub_domain + "." + domain + "."
        data = self.client.list_record_sets_with_line(request)
        result = []
        for record in data.recordsets:
            result.append(record)
        return result

    def create_record(self, domain, sub_domain, value, record_type='A', line='默认', ttl=1):
        request = CreateRecordSetWithLineRequest()
        request.zone_id = self.zone_id[domain + "."]
        name = domain + "." if sub_domain == '@' else sub_domain + "." + domain + "."
        request.body = CreateRecordSetWithLineReq(
            type=record_type,
            name=name,
            ttl=ttl,
            weight=1,
            records=[value],
            line=self.line_format(line)
        )
        return self.client.create_record_set_with_line(request)

    def change_record(self, domain, record_id, sub_domain, value, record_type='A', ttl=1):
        request = UpdateRecordSetRequest()
        request.zone_id = self.zone_id[domain + "."]
        request.recordset_id = record_id
        name = domain + "." if sub_domain == '@' else sub_domain + "." + domain + "."
        request.body = UpdateRecordSetReq(
            name=name,
            type=record_type,
            ttl=ttl,
            records=[value]
        )
        return self.client.update_record_set(request)

# -------------------------
# 抓取 Cloudflare IP
# -------------------------
def fetch_cloudflare_ips(url="https://api.uouin.com/cloudflare.html"):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class": "table-striped"})
    if not table:
        return {}

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

    # 按延迟升序、速度降序
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

    # 更新三网记录
    for line, entries in full_data.items():
        ip = entries[0]["IP"]  # 每线路最优 IP
        records = hw.get_record(domain, subdomain)
        if records:
            for record in records:
                try:
                    hw.change_record(domain, record.id, subdomain, ip)
                    print(f"{line} DNS 更新成功: {ip}")
                except Exception as e:
                    print(f"{line} DNS 更新失败:", e)
        else:
            try:
                hw.create_record(domain, subdomain, ip, line=line)
                print(f"{line} DNS 创建成功: {ip}")
            except Exception as e:
                print(f"{line} DNS 创建失败:", e)

    # 保存 JSON 文件
    output_json = {
        "生成时间": json.dumps(os.environ.get("GITHUB_RUN_ID")),
        "最优IP推荐": best_ip,
        "完整数据列表": full_data
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=4)
    print(f"结果已保存到 {OUTPUT_FILE}")
