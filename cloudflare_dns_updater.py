#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import requests
from bs4 import BeautifulSoup
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
from huaweicloudsdkdns.v2.model import (
    ListPublicZonesRequest,
    ListRecordSetsWithLineRequest,
    UpdateRecordSetRequest,
    UpdateRecordSetReq,
    CreateRecordSetRequest
)

MAX_IP_PER_LINE = 50

class HuaWeiApi:
    def __init__(self, ak, sk, region="ap-southeast-1"):
        self.ak = ak
        self.sk = sk
        self.region = region
        self.client = DnsClient.new_builder()\
            .with_credentials(BasicCredentials(self.ak, self.sk))\
            .with_region(DnsRegion.value_of(self.region)).build()
        self.zone_id = self._get_zones()

    def _get_zones(self):
        req = ListPublicZonesRequest()
        resp = self.client.list_public_zones(req)
        zones = {}
        for z in resp.zones:
            name = z.name.rstrip('.')  # 去掉末尾的点
            zones[name] = z.id
        return zones

    def list_records(self, domain, sub_domain, record_type="A", line="默认"):
        zone_key = domain.rstrip('.')
        zone_id = self.zone_id.get(zone_key)
        if zone_id is None:
            raise KeyError(f"Domain {domain} not in Huawei zone list")
        req = ListRecordSetsWithLineRequest()
        req.zone_id = zone_id
        req.name = f"{sub_domain}.{domain}." if sub_domain != "@" else f"{domain}."
        req.type = record_type
        req.limit = 100
        resp = self.client.list_record_sets_with_line(req)
        # map your line name to SDK line value
        line_map = {
            "默认": "default_view",
            "全网": "default_view",
            "电信": "Dianxin",
            "联通": "Liantong",
            "移动": "Yidong"
        }
        sdk_line = line_map.get(line, "default_view")
        return [r for r in resp.recordsets if getattr(r, "line", None) == sdk_line]

    def set_records(self, domain, sub_domain, ips, record_type="A", line="默认", ttl=300):
        """
        覆盖更新：将记录覆盖为 ips（最多 MAX_IP_PER_LINE），如果不存在则创建
        """
        if not ips:
            print(f"{record_type} | {line} 无有效 IP，跳过更新")
            return

        # 按类型过滤
        if record_type == "A":
            ips = [ip for ip in ips if "." in ip]
        elif record_type == "AAAA":
            ips = [ip for ip in ips if ":" in ip]

        if not ips:
            print(f"{record_type} | {line} 无匹配 IP 格式，跳过")
            return

        zone_key = domain.rstrip('.')
        zone_id = self.zone_id.get(zone_key)
        if zone_id is None:
            print(f"Domain {domain} not found in zone")
            return

        existing = self.list_records(domain, sub_domain, record_type, line)
        # 限制数量
        ips = ips[:MAX_IP_PER_LINE]

        if existing:
            for r in existing:
                # 仅在内容不同才更新
                existing_vals = getattr(r, "records", []) or []
                if sorted(existing_vals) != sorted(ips):
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
                    print(f"更新 {line} {record_type} => {ips}")
                else:
                    print(f"{line} {record_type} 无变化，跳过")
        else:
            # 创建记录
            req = CreateRecordSetRequest()
            req.zone_id = zone_id
            req.body = {
                "name": f"{sub_domain}.{domain}." if sub_domain != "@" else f"{domain}.",
                "type": record_type,
                "ttl": ttl,
                "records": ips,
                "line": ( "default_view" if line in ("默认","全网") else
                          ("Dianxin" if line == "电信" else
                           ("Liantong" if line == "联通" else
                            ("Yidong" if line == "移动" else "default_view"))))
            }
            self.client.create_record_set(req)
            print(f"创建 {line} {record_type} => {ips}")

def fetch_cloudflare_ips():
    """
    抓取 Cloudflare 表格，返回 full_data 和 best_ips 字典。
    best_ips 按线路 + IPv6 分类，值为 IP 列表。
    """
    url = "https://api.uouin.com/cloudflare.html"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class": "table-striped"})
    full = {}
    best = {
        "默认": [],
        "全网": [],
        "电信": [],
        "联通": [],
        "移动": [],
        "IPv6": [],
        "IPv6全网": []
    }
    if not table:
        return full, best

    rows = table.find_all("tr")[1:]
    for tr in rows:
        cols = [c.text.strip() for c in tr.find_all(["td", "th"])]
        if len(cols) < 9:
            continue
        line = cols[1]
        ip = cols[2]
        packet = cols[3]
        # 只记录零丢包 IP
        if packet != "0.00%":
            continue
        if line not in full:
            full[line] = []
        # 延迟 / 速度作为辅助，不用于最终记录
        full[line].append({
            "IP": ip,
            "带宽": cols[6],
            "时间": cols[8]
        })
        # IPv4 or IPv6
        if ":" in ip:
            best["IPv6"].append(ip)
            best["IPv6全网"].append(ip)
        else:
            best[line].append(ip)
            # 默认 / 全网 聚合
            best["默认"].append(ip)
            best["全网"].append(ip)

    # 限制每条线路最多的 IP 数量
    for k in best:
        best[k] = best[k][:MAX_IP_PER_LINE]

    return full, best

if __name__ == "__main__":
    ak = os.environ.get("HUAWEI_ACCESS_KEY")
    sk = os.environ.get("HUAWEI_SECRET_KEY")
    region = os.environ.get("HUAWEI_REGION", "ap-southeast-1")
    domain = os.environ.get("DOMAIN")
    subdomain = os.environ.get("SUBDOMAIN")

    if not all([ak, sk, domain, subdomain]):
        print("环境变量 HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY / DOMAIN / SUBDOMAIN 必须设置")
        exit(1)

    hw = HuaWeiApi(ak, sk, region)
    full_data, best_ips = fetch_cloudflare_ips()

    processed = set()
    # 处理 IPv4 三网 + 默认 / 全网
    for line in ["默认", "电信", "联通", "移动", "全网"]:
        # 避免 默认 和 全网 重复
        if line == "全网" and "默认" in processed:
            continue
        processed.add(line)
        ip_list = best_ips.get(line, [])
        hw.set_records(domain, subdomain, ip_list, record_type="A", line=line)

    # 处理 IPv6
    processed_v6 = set()
    for line in ["IPv6", "IPv6全网"]:
        if line == "IPv6全网" and "IPv6" in processed_v6:
            continue
        processed_v6.add(line)
        ip_list = best_ips.get(line, [])
        hw.set_records(domain, subdomain, ip_list, record_type="AAAA", line=line)

    # 保存 JSON 输出
    out = {
        "最优IP": best_ips,
        "完整数据": full_data
    }
    fname = "cloudflare_bestip.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)
    print(f"结果保存到 {fname}")
