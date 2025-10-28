#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import sys
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
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
HIDE_DOMAIN = os.environ.get("HIDE_DOMAIN", "false").lower() == "true"

def mask_domain(domain):
    """隐藏域名显示"""
    if not HIDE_DOMAIN or not domain:
        return domain
    parts = domain.split('.')
    if len(parts) >= 2:
        return f"***.{parts[-2]}.{parts[-1]}"
    return "***"

def send_telegram(message):
    """发送 Telegram 通知"""
    bot_token = os.environ.get("TG_BOT_TOKEN")
    user_id = os.environ.get("TG_USER_ID")
    
    if not bot_token or not user_id:
        print("⚠️  Telegram 未配置")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": user_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram 通知发送成功")
            return True
        else:
            print(f"❌ Telegram 通知失败")
            return False
    except Exception as e:
        print(f"❌ Telegram 异常: {e}")
        return False


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
            raise KeyError(f"Domain not in Huawei zone list")
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
            print(f"{record_type} | {line} 无有效 IP，跳过")
            return

        if record_type == "A":
            ips = [ip for ip in ips if "." in ip]
        elif record_type == "AAAA":
            ips = [ip for ip in ips if ":" in ip]

        if not ips:
            print(f"{record_type} | {line} 无匹配 IP，跳过")
            return

        ips = list(dict.fromkeys(ips))[:MAX_IP_PER_LINE]
        zone_id = self.zone_id.get(domain.rstrip('.'))
        if zone_id is None:
            raise Exception(f"Domain not found in zone")

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
                    print(f"✅ 更新 {line} {record_type} => {len(ips)} 个IP")
                else:
                    print(f"ℹ️  {line} {record_type} 无变化")
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
            print(f"✅ 创建 {line} {record_type} => {len(ips)} 个IP")


def fetch_cloudflare_ips():
    """使用 Playwright 渲染页面获取 Cloudflare IP"""
    url = "https://api.uouin.com/cloudflare.html"
    print(f"🌐 访问: {url}")
    
    with sync_playwright() as p:
        print("🚀 启动浏览器...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )
        page = browser.new_page()
        
        print("📥 加载页面...")
        page.goto(url, wait_until='networkidle', timeout=30000)
        
        print("⏱️  等待数据渲染...")
        page.wait_for_timeout(6000)
        
        html_content = page.content()
        browser.close()
        print("✅ 页面加载完成")
    
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", {"class": "table-striped"})
    best = {"默认": [], "电信": [], "联通": [], "移动": [], "IPv6": []}
    full = {}

    if not table:
        raise Exception("无法获取 Cloudflare IP 表格数据")

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

        if ":" in ip:
            best["IPv6"].append(ip)
        else:
            if line not in ("电信","联通","移动"):
                best["默认"].append(ip)
            else:
                best[line].append(ip)

    for k in best:
        best[k] = list(dict.fromkeys(best[k]))[:MAX_IP_PER_LINE]
    
    print(f"📊 统计: 默认={len(best['默认'])}, 电信={len(best['电信'])}, 联通={len(best['联通'])}, 移动={len(best['移动'])}, IPv6={len(best['IPv6'])}")

    return full, best


if __name__ == "__main__":
    full_domain = os.environ.get("FULL_DOMAIN")
    ak = os.environ.get("HUAWEI_ACCESS_KEY")
    sk = os.environ.get("HUAWEI_SECRET_KEY")
    region = os.environ.get("HUAWEI_REGION", "ap-southeast-1")

    if not all([full_domain, ak, sk]):
        error_msg = "环境变量未完整设置"
        print(f"❌ {error_msg}")
        send_telegram(f"🚨 <b>DNS 更新失败</b>\n\n❌ {error_msg}")
        sys.exit(1)

    try:
        masked_domain = mask_domain(full_domain)
        print(f"🚀 开始更新 DNS: {masked_domain}")
        
        hw = HuaWeiApi(ak, sk, region)
        full_data, best_ips = fetch_cloudflare_ips()
        
        update_summary = []

        # 更新 IPv4
        for line in ["默认", "电信", "联通", "移动"]:
            ip_list = best_ips.get(line, [])
            if ip_list:
                hw.set_records(full_domain, ip_list, record_type="A", line=line)
                update_summary.append(f"✅ {line} A: {len(ip_list)}个")

        # 更新 IPv6
        ip_list_v6 = best_ips.get("IPv6", [])
        if ip_list_v6:
            hw.set_records(full_domain, ip_list_v6, record_type="AAAA", line="默认")
            update_summary.append(f"✅ IPv6: {len(ip_list_v6)}个")

        # 保存 JSON
        with open("cloudflare_bestip.json", "w", encoding="utf-8") as f:
            json.dump({"最优IP": best_ips, "完整数据": full_data}, f, ensure_ascii=False, indent=4)
        print("📄 JSON 已保存")

        # 保存 TXT
        china_tz = timezone(timedelta(hours=8))
        now = datetime.now(china_tz).strftime("%Y/%m/%d %H:%M:%S")
        txt_lines = []

        for line in ["默认", "电信", "联通", "移动", "IPv6"]:
            ip_list = best_ips.get(line, [])
            if not ip_list:
                continue
            txt_lines.append(now)
            for ip in ip_list:
                if ":" in ip:
                    txt_lines.append(f"[{ip}]#{line}")
                else:
                    txt_lines.append(f"{ip}#{line}")
            txt_lines.append("")

        with open("cloudflare_bestip.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines))
        print("📄 TXT 已保存")
        
        success_msg = f"""✅ <b>DNS 更新成功</b>

📋 域名: <code>{masked_domain}</code>
🕐 时间: {now}

{chr(10).join(update_summary)}
"""
        send_telegram(success_msg)
        print("✅ 完成")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 错误: {error_msg}")
        
        china_tz = timezone(timedelta(hours=8))
        now = datetime.now(china_tz).strftime("%Y/%m/%d %H:%M:%S")
        
        fail_msg = f"""🚨 <b>DNS 更新失败</b>

📋 域名: <code>{mask_domain(full_domain)}</code>
🕐 时间: {now}
❌ 错误: <code>{error_msg}</code>
"""
        send_telegram(fail_msg)
        sys.exit(1)
