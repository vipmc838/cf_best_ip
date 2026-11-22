#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import sys
import requests
import html
from datetime import datetime, timezone, timedelta
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

def send_telegram(message):
    """
    发送 Telegram 通知
    """
    bot_token = os.environ.get("TG_BOT_TOKEN")
    user_id = os.environ.get("TG_USER_ID")

    if not bot_token or not user_id:
        print("⚠️ TG_BOT_TOKEN 或 TG_USER_ID 未设置，跳过通知")
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
            print(f"❌ Telegram 通知发送失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram 通知异常: {str(e)}")
        return False


class HuaWeiApi:
    def __init__(self, ak, sk, region="ap-southeast-1"):
        self.client = DnsClient.new_builder() \
            .with_credentials(BasicCredentials(ak, sk)) \
            .with_region(DnsRegion.value_of(region)).build()
        self.zone_id = self._get_zones()

    def _get_zones(self):
        try:
            request = ListPublicZonesRequest()
            response = self.client.list_public_zones(request)
            if response.zones:
                return response.zones[0].id
            else:
                raise Exception("未找到任何 Public Zone")
        except Exception as e:
            print(f"获取 Zone ID 失败: {e}")
            raise e

    def get_records(self, full_domain, record_type="A", line="默认"):
        record_name = f"{full_domain}."
        try:
            request = ListRecordSetsWithLineRequest()
            request.zone_id = self.zone_id
            response = self.client.list_record_sets_with_line(request)
            for record in response.recordsets:
                if record.name == record_name and record.type == record_type:
                    current_line = record.line if record.line else "默认"
                    if current_line == line:
                        return record
            return None
        except Exception as e:
            print(f"获取解析记录失败 ({line}): {e}")
            return None

    def set_records(self, full_domain, ip_list, record_type="A", line="默认"):
        record = self.get_records(full_domain, record_type, line)
        line_name = "默认" if line == "默认" else line
        if record:
            try:
                request = UpdateRecordSetRequest()
                request.zone_id = self.zone_id
                request.recordset_id = record.id
                request.body = UpdateRecordSetReq(records=ip_list, type=record_type, ttl=300)
                self.client.update_record_set(request)
                print(f"更新成功 [{line_name}] -> {ip_list}")
            except Exception as e:
                print(f"更新失败 [{line_name}]: {e}")
                raise e
        else:
            try:
                request = CreateRecordSetRequest()
                request.zone_id = self.zone_id
                body = {
                    "name": f"{full_domain}.",
                    "type": record_type,
                    "ttl": 300,
                    "records": ip_list,
                }
                if line != "默认":
                    body["line"] = line
                request.body = body
                self.client.create_record_set(request)
                print(f"添加成功 [{line_name}] -> {ip_list}")
            except Exception as e:
                print(f"添加失败 [{line_name}]: {e}")
                raise e


def fetch_cloudflare_ips():
    """
    爬取 Cloudflare IP 列表
    """
    url = "https://stock.hostmonit.com/CloudFlareYes"
    session = HTMLSession()
    try:
        response = session.get(url, timeout=15)
        response.html.render(timeout=20)
    except Exception as e:
        print(f"网页抓取/渲染失败: {e}")
        return {}, {}

    soup = BeautifulSoup(response.html.html, "html.parser")
    tables = soup.find_all("table")

    all_data = {}
    best_ips = {"电信": [], "联通": [], "移动": []}

    for table in tables:
        prev = table.find_previous(["h2", "h3"])
        title = prev.text.strip() if prev else "未知类型"
        headers = [th.text.strip() for th in table.find_all("th")]

        rows_data = []
        for tr in table.find_all("tr")[1:]:
            cells = [td.text.strip() for td in tr.find_all("td")]
            if len(cells) == len(headers):
                row_dict = dict(zip(headers, cells))
                rows_data.append(row_dict)

                ip = row_dict.get("IP地址")
                line = row_dict.get("线路")
                if ip and line in best_ips and len(best_ips[line]) < MAX_IP_PER_LINE:
                    best_ips[line].append(ip)

        all_data[title] = rows_data

    # 构建默认线路（电信+联通+移动混合）
    default_ips = []
    max_len = max(len(v) for v in best_ips.values()) if best_ips else 0
    for i in range(max_len):
        for line in ["电信", "联通", "移动"]:
            if i < len(best_ips[line]):
                default_ips.append(best_ips[line][i])
    best_ips["默认"] = list(dict.fromkeys(default_ips))[:MAX_IP_PER_LINE]

    return all_data, best_ips


def fetch_api_ips():
    """
    从私有 API 获取 Cloudflare IP
    """
    api_url = "https://api.uouin.com/cloudflare.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("info") == "SUCCESS" and "data" in data:
            ips = [item["ip"] for item in data["data"] if "ip" in item]
            print(f"成功从 API 获取到 {len(ips)} 个 IP")
            return ips
        else:
            print("API 返回格式异常或无数据")
            return []
    except Exception as e:
        print(f"请求 API 失败: {e}")
        return []


if __name__ == "__main__":
    full_domain = os.environ.get("FULL_DOMAIN")
    ak = os.environ.get("HUAWEI_ACCESS_KEY")
    sk = os.environ.get("HUAWEI_SECRET_KEY")
    region = os.environ.get("HUAWEI_REGION", "ap-southeast-1")

    china_tz = timezone(timedelta(hours=8))
    now = datetime.now(china_tz).strftime("%Y/%m/%d %H:%M:%S")

    if not all([full_domain, ak, sk]):
        missing_envs = "环境变量 FULL_DOMAIN / HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY 必须设置"
        print(missing_envs)
        domain_display = full_domain if full_domain else "未知"
        fail_msg = (
            "<b>🚨 DNS 更新失败</b>\n\n"
            f"域名: {html.escape(domain_display)}\n"
            f"错误: {html.escape(missing_envs)}\n"
            "请检查日志并手动处理！\n\n"
            f"时间: {now}"
        )
        send_telegram(fail_msg)
        sys.exit(1)

    try:
        print(f"开始更新 DNS: {full_domain}")

        hw = HuaWeiApi(ak, sk, region)
        full_data, best_ips = fetch_cloudflare_ips()

        api_ips = fetch_api_ips()
        if api_ips:
            api_ipv4 = [ip for ip in api_ips if ":" not in ip]
            api_ipv6 = [ip for ip in api_ips if ":" in ip]

            if api_ipv4:
                print(f"➕ 合并 {len(api_ipv4)} 个 IPv4 到默认线路")
                combined = best_ips.get("默认", []) + api_ipv4
                best_ips["默认"] = list(dict.fromkeys(combined))[:MAX_IP_PER_LINE]

            if api_ipv6:
                print(f"➕ 合并 {len(api_ipv6)} 个 IPv6 到 IPv6 线路")
                combined_v6 = best_ips.get("IPv6", []) + api_ipv6
                best_ips["IPv6"] = list(dict.fromkeys(combined_v6))[:MAX_IP_PER_LINE]

            if "API" not in full_data:
                full_data["API"] = []
            full_data["API"].extend([{"IP": ip} for ip in api_ips])

        update_summary = []

        for line in ["默认", "电信", "联通", "移动"]:
            ip_list = best_ips.get(line, [])
            if ip_list:
                hw.set_records(full_domain, ip_list, record_type="A", line=line)
                update_summary.append(f"{line} A记录: {len(ip_list)} 个IP")

        ip_list_v6 = best_ips.get("IPv6", [])
        if ip_list_v6:
            hw.set_records(full_domain, ip_list_v6, record_type="AAAA", line="默认")
            update_summary.append(f"IPv6 AAAA记录: {len(ip_list_v6)} 个IP")

        with open("cloudflare_bestip.json", "w", encoding="utf-8") as f:
            json.dump({"最优IP": best_ips, "完整数据": full_data}, f, ensure_ascii=False, indent=4)
        print("JSON 文件保存到 cloudflare_bestip.json")

        txt_lines = [now]

        for line in ["默认", "电信", "联通", "移动", "IPv6"]:
            ip_list = best_ips.get(line, [])
            if not ip_list:
                continue
            for ip in ip_list:
                if ":" in ip:
                    txt_lines.append(f"[{ip}]#{line}")
                else:
                    txt_lines.append(f"{ip}#{line}")
            txt_lines.append("")

        if txt_lines and txt_lines[-1] == "":
            txt_lines.pop()

        with open("cloudflare_bestip.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines))

        print("TXT 文件保存到 cloudflare_bestip.txt")

        success_msg = "\n".join(
            ["<b>✅ DNS 更新成功</b>", "", f"域名: {html.escape(full_domain)}"]
            + update_summary
            + ["", f"时间: {now}"]
        )
        send_telegram(success_msg)
        print("✅ DNS 更新完成")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 错误: {error_msg}")

        fail_msg = "\n".join([
            "<b>🚨 DNS 更新失败</b>",
            "",
            f"域名: {html.escape(full_domain)}",
            f"错误: {html.escape(error_msg)}",
            "请检查日志并手动处理！",
            "",
            f"时间: {now}"
        ])
        send_telegram(fail_msg)
        sys.exit(1)
