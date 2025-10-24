#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
from huaweicloudsdkdns.v2.model import ListPublicZonesRequest, ListRecordSetsWithLineRequest
from huaweicloudsdkdns.v2.model import UpdateRecordSetRequest, UpdateRecordSetReq
from huaweicloudsdkdns.v2.model import CreateRecordSetRequest

MAX_IP_PER_LINE = 50

class HuaWeiApi:
    def __init__(self, ak, sk, region="ap-southeast-1"):
        self.ak = ak
        self.sk = sk
        self.region = region
        self.client = DnsClient.new_builder()\
            .with_credentials(BasicCredentials(self.ak, self.sk))\
            .with_region(DnsRegion.value_of(self.region)).build()
        self.zone_id = self.get_zones()

    def get_zones(self):
        request = ListPublicZonesRequest()
        response = self.client.list_public_zones(request)
        zones = {}
        for z in response.zones:
            name = z.name.rstrip('.')
            zones[name] = z.id
        return zones

    def list_records(self, domain, sub_domain, record_type="A", line="默认"):
        zone_id = self.zone_id[domain.rstrip('.')]
        request = ListRecordSetsWithLineRequest()
        request.zone_id = zone_id
        request.name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."
        request.type = record_type
        request.limit = 100
        response = self.client.list_record_sets_with_line(request)
        line_map = {'默认':'default_view','电信':'Dianxin','联通':'Liantong','移动':'Yidong','全网':'default_view'}
        line_value = line_map.get(line,'default_view')
        return [r for r in response.recordsets if getattr(r,'line',None)==line_value]

    def set_records(self, domain, sub_domain, ips, record_type="A", line="默认", ttl=1):
        """
        覆盖更新 IP 列表，不累加
        """
        zone_id = self.zone_id[domain.rstrip('.')]
        line_map = {'默认':'default_view','电信':'Dianxin','联通':'Liantong','移动':'Yidong','全网':'default_view'}
        line_value = line_map.get(line,'default_view')

        # 限制最多 50 个 IP
        ips = ips[:MAX_IP_PER_LINE]

        # 查找现有记录
        existing = self.list_records(domain, sub_domain, record_type, line)
        if existing:
            for r in existing:
                req = UpdateRecordSetRequest()
                req.zone_id = zone_id
                req.recordset_id = r.id
                req.body = UpdateRecordSetReq(
                    name=r.name,
                    type=record_type,
                    ttl=ttl,
                    records=ips
                )
                self.client.update_record_set(req)
        else:
            # 创建新记录
            req = CreateRecordSetRequest()
            req.zone_id = zone_id
            req.body = {
                "name": f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}.",
                "type": record_type,
                "ttl": ttl,
                "records": ips,
                "line": line_value
            }
            self.client.create_record_set(req)

def fetch_cloudflare_ips():
    url = "https://api.uouin.com/cloudflare.html"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class":"table-striped"})
    full_data = {}
    best_ips = {"默认":[], "电信":[], "联通":[], "移动":[], "全网":[], "IPv6":[], "IPv6全网":[]}

    if not table:
        return full_data, best_ips

    rows = table.find_all("tr")[1:]
    for row in rows:
        cols = [c.text.strip() for c in row.find_all(["td","th"])]
        if len(cols) < 9:
            continue
        line = cols[1]
        ip = cols[2]
        ip_type = "IPv6" if ":" in ip else "A"
        packet = cols[3]
        latency = float(cols[4].replace("ms","") or 999)
        speed = float(cols[5].replace("mb/s","") or 0)

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

        if packet=="0.00%":
            # 覆盖逻辑：默认和全网只更新一次
            if ip_type=="A":
                if line in ["默认","全网","电信","联通","移动"]:
                    best_ips[line].append(ip)
                    if line=="默认":  # 默认即全网
                        best_ips["全网"] = best_ips["默认"]
            else:
                best_ips["IPv6"].append(ip)
                best_ips["IPv6全网"] = best_ips["IPv6"]

    # 每条线路最多 50 个
    for k,v in best_ips.items():
        best_ips[k] = v[:MAX_IP_PER_LINE]

    return full_data, best_ips

if __name__=="__main__":
    ak = os.environ["HUAWEI_ACCESS_KEY"]
    sk = os.environ["HUAWEI_SECRET_KEY"]
    region = os.environ.get("HUAWEI_REGION","ap-southeast-1")
    domain = os.environ["DOMAIN"]
    subdomain = os.environ["SUBDOMAIN"]

    hw = HuaWeiApi(ak, sk, region)
    full_data, best_ips = fetch_cloudflare_ips()

    updated_lines = set()
    for line, ips in best_ips.items():
        # 避免全网和默认重复
        if line in ["全网"] and "默认" in updated_lines:
            continue
        try:
            hw.set_records(domain, subdomain, ips, line=line)
            print(f"{line} 更新成功 -> {ips}")
            updated_lines.add(line)
        except Exception as e:
            print(f"{line} 更新失败: {e}")

    out_file = "cloudflare_bestip.json"
    json.dump({"最优IP": best_ips, "完整数据": full_data}, open(out_file,"w",encoding="utf-8"), ensure_ascii=False, indent=4)
    print(f"结果保存到 {out_file}")
