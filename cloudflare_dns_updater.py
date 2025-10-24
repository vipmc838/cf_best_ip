#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
from huaweicloudsdkdns.v2.model import RecordSet, ListRecordSetsWithLineRequest, CreateRecordSetRequest, UpdateRecordSetRequest, ListPublicZonesRequest

class HuaWeiApi:
    def __init__(self, ak, sk, region="ap-southeast-1"):
        self.ak = ak
        self.sk = sk
        self.region = region
        self.client = DnsClient.new_builder()\
            .with_credentials(BasicCredentials(self.ak, self.sk))\
            .with_region(DnsRegion.value_of(self.region))\
            .build()
        self.zone_id = self.get_zones()
        self.line_map = {'默认':'default_view','电信':'Dianxin','联通':'Liantong','移动':'Yidong'}

    def get_zones(self):
        request = ListPublicZonesRequest()
        response = self.client.list_public_zones(request)
        zones = {}
        for z in response.zones:
            zones[z.name.rstrip('.')] = z.id
        return zones

    def list_records(self, domain, sub_domain, record_type="A"):
        zone_id = self.zone_id[domain.rstrip('.')]
        request = ListRecordSetsWithLineRequest()
        request.zone_id = zone_id
        request.name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."
        request.type = record_type
        request.limit = 100
        response = self.client.list_record_sets_with_line(request)
        return response.recordsets

    def update_record(self, domain, sub_domain, ip, record_type="A", line="默认", ttl=1):
        zone_id = self.zone_id[domain.rstrip('.')]
        line_value = self.line_map.get(line, 'default_view')

        records = self.list_records(domain, sub_domain, record_type)
        matched = False
        for r in records:
            if r.line == line_value:
                req = UpdateRecordSetRequest()
                req.zone_id = zone_id
                req.recordset_id = r.id
                req.body = RecordSet(
                    name=r.name,
                    type=r.type,
                    ttl=ttl,
                    records=[ip],
                    line=r.line
                )
                self.client.update_record_set(req)
                matched = True

        if not matched:
            # 没有匹配到该线路，则创建
            req = CreateRecordSetRequest()
            req.zone_id = zone_id
            name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."
            req.body = RecordSet(
                name=name,
                type=record_type,
                ttl=ttl,
                records=[ip],
                line=line_value
            )
            self.client.create_record_set(req)

        return True

def fetch_cloudflare_ips(max_per_line=50):
    url = "https://api.uouin.com/cloudflare.html"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class":"table-striped"})
    full_data = {}
    best_ips = {}
    if not table:
        return full_data, best_ips
    rows = table.find_all("tr")[1:]
    line_count = {}
    for row in rows:
        cols = [c.text.strip() for c in row.find_all(["td","th"])]
        if len(cols) < 9:
            continue
        line = cols[1]
        ip = cols[2]
        packet = cols[3]
        latency = float(cols[4].replace("ms","") or 999)
        speed = float(cols[5].replace("mb/s","") or 0)

        # 限制每条线路最多 max_per_line 个 IP
        line_count.setdefault(line, 0)
        if line_count[line] >= max_per_line:
            continue
        line_count[line] += 1

        if line not in full_data:
            full_data[line] = []
        full_data[line].append({
            "IP": ip,
            "丢包": packet,
            "延迟": latency,
            "速度": speed,
            "带宽": cols[6],
            "时间": cols[8]
        })
        # 只考虑丢包为0的IP，取延迟最低作为最佳
        if packet=="0.00%" and line not in best_ips:
            best_ips[line] = ip
    return full_data, best_ips

if __name__ == "__main__":
    ak = os.environ["HUAWEI_ACCESS_KEY"]
    sk = os.environ["HUAWEI_SECRET_KEY"]
    region = os.environ.get("HUAWEI_REGION","ap-southeast-1")
    domain = os.environ["DOMAIN"]
    subdomain = os.environ["SUBDOMAIN"]

    hw = HuaWeiApi(ak, sk, region)
    full_data, best_ips = fetch_cloudflare_ips(max_per_line=50)

    for line, ip in best_ips.items():
        try:
            hw.update_record(domain, subdomain, ip, line=line)
            print(f"{ip} {line} 更新成功")
        except Exception as e:
            print(f"{ip} {line} 更新失败: {e}")

    out_file = "cloudflare_bestip.json"
    json.dump({"最优IP": best_ips, "完整数据": full_data}, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print(f"结果保存到 {out_file}")
