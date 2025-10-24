#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import json
import requests
from bs4 import BeautifulSoup
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.model.update_record_set_request import UpdateRecordSetRequest
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

class HuaWeiApi:
    def __init__(self, ak, sk, region):
        self.ak = ak
        self.sk = sk
        self.region = region
        self.client = DnsClient.new_builder()\
            .with_credentials(BasicCredentials(self.ak, self.sk))\
            .with_region(DnsRegion.value_of(self.region))\
            .build()
        self.zone_id = self.get_zones()

    def get_zones(self):
        from huaweicloudsdkdns.v2.model.list_public_zones_request import ListPublicZonesRequest
        request = ListPublicZonesRequest()
        response = self.client.list_public_zones(request)
        zones = {}
        for z in response.zones:
            zones[z.name] = z.id
        return zones

    def list_records(self, domain, subdomain, record_type='A'):
        from huaweicloudsdkdns.v2.model.list_record_sets_request import ListRecordSetsRequest
        request = ListRecordSetsRequest()
        request.zone_id = self.zone_id[domain]
        request.type = record_type
        request.name = f"{subdomain}.{domain}." if subdomain != '@' else f"{domain}."
        response = self.client.list_record_sets(request)
        return response.recordsets

    def update_record(self, domain, subdomain, value, record_type='A', ttl=1, line='默认'):
        records = self.list_records(domain, subdomain, record_type)
        record_to_update = None
        for r in records:
            if getattr(r, "line", None) == self.line_format(line):
                record_to_update = r
                break
        if not record_to_update:
            print(f"{subdomain}.{domain} 在线路 {line} 没找到记录，无法更新")
            return

        request = UpdateRecordSetRequest()
        request.zone_id = self.zone_id[domain]
        request.recordset_id = record_to_update.id
        request.body = {
            "name": f"{subdomain}.{domain}." if subdomain != '@' else f"{domain}.",
            "type": record_type,
            "ttl": ttl,
            "records": [value]
        }
        self.client.update_record_set(request)
        print(f"更新 {subdomain}.{domain} 线路 {line} -> {value} 成功")

    def line_format(self, line):
        lines = {
            '默认': 'default_view',
            '电信': 'Dianxin',
            '联通': 'Liantong',
            '移动': 'Yidong',
            '境外': 'Abroad',
            'default_view': '默认',
            'Dianxin': '电信',
            'Liantong': '联通',
            'Yidong': '移动',
            'Abroad': '境外',
        }
        return lines.get(line, None)

def fetch_cloudflare_ips(url="https://api.uouin.com/cloudflare.html"):
    try:
        r = requests.get(url, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table', {'class': 'table-striped'})
        if not table:
            print("未找到目标表格")
            return {}

        full_data = {}
        rows = table.find_all('tr')[1:]
        headers = ["#", "线路", "优选IP", "丢包", "延迟", "速度", "带宽", "Colo", "时间"]
        for tr in rows:
            tds = tr.find_all(['td','th'])
            if len(tds) != len(headers):
                continue
            entry = {}
            for i, td in enumerate(tds):
                text = td.text.strip()
                entry[headers[i]] = text
            line_type = entry["线路"]
            if line_type not in full_data:
                full_data[line_type] = []
            full_data[line_type].append(entry)
        return full_data
    except Exception as e:
        print("抓取失败:", e)
        return {}

if __name__ == '__main__':
    ak = os.environ['HUAWEI_ACCESS_KEY']
    sk = os.environ['HUAWEI_SECRET_KEY']
    region = os.environ['HUAWEI_REGION']
    domain = os.environ['DOMAIN']
    subdomain = os.environ['SUBDOMAIN']

    hw = HuaWeiApi(ak, sk, region)
    ip_data = fetch_cloudflare_ips()

    for line in ["电信", "联通", "移动", "默认"]:
        if line in ip_data and ip_data[line]:
            ip = ip_data[line][0]["优选IP"]
            hw.update_record(domain, subdomain, ip, line=line)
        else:
            print(f"{line} 没有获取到 IP")
