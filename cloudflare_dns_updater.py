#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.model import ListPublicZonesRequest, ListRecordSetsWithLineRequest, UpdateRecordSetRequest, UpdateRecordSetReq
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

class HuaWeiApi:
    def __init__(self, ak, sk, region='ap-southeast-1'):
        self.ak = ak
        self.sk = sk
        self.region = region
        self.client = DnsClient.new_builder() \
            .with_credentials(BasicCredentials(self.ak, self.sk)) \
            .with_region(DnsRegion.value_of(self.region)) \
            .build()
        self.zone_id = self.get_zones()

    def get_zones(self):
        request = ListPublicZonesRequest()
        response = self.client.list_public_zones(request)
        zones = {}
        for zone in response.zones:
            zones[zone.name] = zone.id
        return zones

    def get_record(self, domain, sub_domain, record_type='A'):
        request = ListRecordSetsWithLineRequest()
        request.zone_id = self.zone_id[domain + '.']
        request.name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."
        request.type = record_type
        response = self.client.list_record_sets_with_line(request)
        return response.recordsets

    def update_record(self, domain, sub_domain, value, record_type='A', ttl=1):
        records = self.get_record(domain, sub_domain, record_type)
        if not records:
            print(f"{domain} {sub_domain} 没有找到记录，无法更新")
            return
        record_id = records[0].id
        request = UpdateRecordSetRequest()
        request.zone_id = self.zone_id[domain + '.']
        request.recordset_id = record_id
        request.body = UpdateRecordSetReq(
            name=f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}.",
            type=record_type,
            ttl=ttl,
            records=[value]
        )
        resp = self.client.update_record_set(request)
        print(f"更新 {sub_domain}.{domain} -> {value} 成功")
        return resp

# -------------------------
# Cloudflare IP 抓取
# -------------------------
def fetch_cloudflare_ips():
    url = "https://api.uouin.com/cloudflare.html"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, 'html.parser')
    table = soup.find("table", class_="table-striped")
    if not table:
        return {}
    full_data = {}
    headers = ["#", "线路", "优选IP", "丢包", "延迟", "速度", "带宽", "Colo", "时间"]
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all(["td","th"])
        if len(tds) != len(headers):
            continue
        entry = {}
        for i, td in enumerate(tds):
            text = td.get_text(strip=True)
            entry[headers[i]] = text
        line = entry["线路"]
        ip = entry["优选IP"]
        if line not in full_data:
            full_data[line] = []
        full_data[line].append(entry)
    return full_data

# -------------------------
# 主函数
# -------------------------
def main():
    ak = os.environ.get("HUAWEI_ACCESS_KEY")
    sk = os.environ.get("HUAWEI_SECRET_KEY")
    region = os.environ.get("HUAWEI_REGION", "ap-southeast-1")
    domain = os.environ.get("DOMAIN")
    subdomain = os.environ.get("SUBDOMAIN", "cf")

    hw = HuaWeiApi(ak, sk, region)
    ip_data = fetch_cloudflare_ips()

    # 按三网更新
    for line in ["电信","联通","移动"]:
        if line in ip_data and ip_data[line]:
            ip = ip_data[line][0]["优选IP"]
            hw.update_record(domain, subdomain, ip)
        else:
            print(f"{line} 没有获取到 IP")

if __name__ == "__main__":
    main()
