#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
from requests_html import HTMLSession
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
        self.client = DnsClient.new_builder()\
            .with_credentials(BasicCredentials(ak, sk))\
            .with_region(DnsRegion.value_of(region)).build()
        self.zone_id = self._get_zones()

    def _get_zones(self):
        req = ListPublicZonesRequest()
        resp = self.client.list_public_zones(req)
        return {z.name.rstrip('.'): z.id for z in resp.zones}

    def list_records(self, domain, record_type="A", line="默认"):
        zone_id = self.zone_id.get(domain.rstrip('.'))
        if zone_id is None:
            raise KeyError(f"Domain {domain} not in Huawei zone list")
        req = ListRecordSetsWithLineRequest()
        req.zone_id = zone_id
        req.name = f"{domain}."
        req.type = record_type
        req.limit = 100
        resp = self.client.list_record_sets_with_line(req)
        line_map = {
            "默认": "default_view",
            "电信": "Dianxin",
            "联通": "Liantong",
            "移动": "Yidong"
        }
        sdk_line = line_map.get(line, "default_view")
        return [r for r in resp.recordsets if getattr(r, "line", None) == sdk_line]

    def set_records(self, domain, ips, record_type="A", line="默认", ttl=300):
        if not ips:
            print(f"{record_type} | {line} 无有效 IP，跳过更新")
            return

        # 过滤 IP 类型
        if record_type == "A":
            ips = [ip for ip in ips if "." in ip]
        elif record_type == "AAAA":
            ips = [ip for ip in ips if ":" in ip]

        if not ips:
            print(f"{record_type} | {line} 无匹配 IP，跳过")
            return

        # 去重
        ips = list(dict.fromkeys(ips))[:MAX_IP_PER_LINE]

        zone_id = self.zone_id.get(domain.rstrip('.'))
        if zone_id is None:
            print(f"Domain {domain} not found in zone")
            return

        existing = self.list_records(domain, record_type, line)

        if existing:
            for r in existing:
                existing_vals = list(dict.fromkeys(getattr(r, "records", []) or []))
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
            req = CreateRecordSetRequest()
            req.zone_id = zone_id
            req.body = {
                "name": f"{domain}.",
                "type": record_type,
                "ttl": ttl,
                "records": ips,
                "line": ("default_view" if line == "默认" else
                         ("Dianxin" if line == "电信" else
                          ("Liantong" if line == "联通" else
                           ("Yidong" if line == "移动" else "default_view"))))
            }
            self.client.create_record_set(req)
            print(f"创建 {line} {record_type} => {ips}")


def fetch_cloudflare_ips():
    """
    使用 requests-html 渲染页面获取最新 Cloudflare IP
    """
    url = "https://api.uouin.com/cloudflare.html"
    session = HTMLSession()
    r = session.get(url, timeout=20)
    r.html.render(sleep=6, timeout=20)

    soup = BeautifulSoup(r.html.html, "html.parser")
    table = soup.find("table", {"class": "table-striped"})
    best = {"默认": [], "电信": [], "联通": [], "移动": [], "IPv6": []}
    full = {}

    if not table:
        return full, best

    for tr in table.find_all("tr")[1:]:
        cols = [c.text.strip() for c in tr.find_all(["td","th"])]
        if len(cols) < 9:
            continue
        line = cols[1]
        ip = cols[2]
        packet = cols[3]
        if packet != "0.00%":
            continue

        if line not in full:
            full[line] = []
        full[line].append({"IP": ip, "带宽": cols[6], "时间": cols[8]})

        # 分类 IP
        if ":" in ip:
            best["IPv6"].append(ip)
        else:
            # 多线 / 全网 / 默认 都算默认
            if line not in ("电信","联通","移动"):
                best["默认"].append(ip)
            else:
                best[line].append(ip)

    # 去重 + 限制数量
    for k in best:
        best[k] = list(dict.fromkeys(best[k]))[:MAX_IP_PER_LINE]

    return full, best


if __name__ == "__main__":
    full_domain = os.environ.get("FULL_DOMAIN")
    ak = os.environ.get("HUAWEI_ACCESS_KEY")
    sk = os.environ.get("HUAWEI_SECRET_KEY")
    region = os.environ.get("HUAWEI_REGION", "ap-southeast-1")

    if not all([full_domain, ak, sk]):
        print("环境变量 FULL_DOMAIN / HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY 必须设置")
        exit(1)

    hw = HuaWeiApi(ak, sk, region)
    full_data, best_ips = fetch_cloudflare_ips()

    # 更新 IPv4
    for line in ["默认", "电信", "联通", "移动"]:
        ip_list = best_ips.get(line, [])
        hw.set_records(full_domain, ip_list, record_type="A", line=line)

    # 更新 IPv6
    ip_list_v6 = best_ips.get("IPv6", [])
    hw.set_records(full_domain, ip_list_v6, record_type="AAAA", line="默认")

    # 保存结果
    out = {"最优IP": best_ips, "完整数据": full_data}
    with open("cloudflare_bestip.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)
    print("结果保存到 cloudflare_bestip.json")
