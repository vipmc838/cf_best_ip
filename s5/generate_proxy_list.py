#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import requests
from bs4 import BeautifulSoup, NavigableString
import time
from datetime import datetime, timezone, timedelta
import re
import os
import concurrent.futures


class ProxyListScraper:
    def __init__(self):
        self.base_url = "https://proxy-socks5.com"
        self.login_url = f"{self.base_url}/login"
        self.proxy_list_url = f"{self.base_url}/proxy_list"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
            'Referer': self.base_url
        }
        self.tg_bot_token = os.environ.get('TG_BOT_TOKEN', '')
        self.tg_user_id = os.environ.get('TG_USER_ID', '')
        self.cn_tz = timezone(timedelta(hours=8))
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # 自建检测 API
        self.probe_url = 'https://mra8-api.hf.space/'

    def get_cn_time(self):
        return datetime.now(self.cn_tz)

    def login(self):
        """
        登录网站，从环境变量 TOMCAT1235 读取凭据
        格式: 用户名-----密码
        """
        tomcat_cred = os.environ.get('TOMCAT1235', '')
        if not tomcat_cred:
            print("⚠️  未配置 TOMCAT1235 环境变量，将以未登录状态抓取（IP可能被脱敏）")
            return False

        if '-----' not in tomcat_cred:
            print("⚠️  TOMCAT1235 格式错误，应为 用户名-----密码")
            return False

        parts = tomcat_cred.split('-----', 1)
        username = parts[0].strip()
        password = parts[1].strip()

        if not username or not password:
            print("⚠️  TOMCAT1235 用户名或密码为空")
            return False

        print(f"🔑 正在登录: {self.login_url}")

        try:
            login_page = self.session.get(self.login_url, timeout=30)
            login_page.raise_for_status()

            soup = BeautifulSoup(login_page.text, 'html.parser')

            csrf_token = None
            csrf_input = soup.find('input', {'name': re.compile(r'csrf|_token|token', re.I)})
            if csrf_input:
                csrf_token = csrf_input.get('value', '')

            login_data = {
                'username': username,
                'password': password,
            }
            if csrf_token:
                csrf_field_name = csrf_input.get('name', 'csrf_token')
                login_data[csrf_field_name] = csrf_token

            login_headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': self.login_url,
                'Origin': self.base_url
            }

            response = self.session.post(
                self.login_url,
                data=login_data,
                headers=login_headers,
                timeout=30,
                allow_redirects=True
            )
            response.raise_for_status()

            if '/login' not in response.url:
                print("✅ 登录成功")
                return True

            resp_text = response.text.lower()
            fail_keywords = ['密码错误', '用户名或密码', 'invalid', 'incorrect', '登录失败', 'wrong password']
            for kw in fail_keywords:
                if kw in resp_text:
                    print("❌ 登录失败: 凭据错误")
                    return False

            soup_after = BeautifulSoup(response.text, 'html.parser')
            logout_link = soup_after.find('a', href=re.compile(r'logout|sign.?out', re.I))
            if logout_link:
                print("✅ 登录成功")
                return True

            print("⚠️  登录状态不明确，继续尝试抓取")
            return True

        except requests.RequestException as e:
            print(f"❌ 登录请求错误: {e}")
            return False
        except Exception as e:
            print(f"❌ 登录错误: {e}")
            import traceback
            traceback.print_exc()
            return False

    def clean_location(self, td_element):
        """提取地理位置、类型标签、fraud标签"""
        if not td_element:
            return "未知", False

        # 提取类型标签
        type_tag = ""
        is_residential = False
        if td_element.find('span', class_='datacenter-tag'):
            type_tag = "[机房]"
        elif td_element.find('span', class_='residential-tag'):
            type_tag = "[家宽]"
            is_residential = True

        # 提取 fraud badge
        fraud_tag = ""
        fraud_badge = td_element.find('span', class_='fraud-badge')
        if fraud_badge:
            fraud_tag = fraud_badge.get_text(strip=True)

        # 提取主要地理文本
        location = ""
        flex_text_span = td_element.find('span', class_='flex-text')
        if flex_text_span:
            location = flex_text_span.get_text(strip=True)

        parts = [p for p in [type_tag, fraud_tag, location] if p]
        full_location = " ".join(parts)
        full_location = re.sub(r'\s+', ' ', full_location).strip()

        return (full_location if full_location else "未知"), is_residential

    def extract_ip_from_cell(self, ip_cell, row=None):
        """
        从 IP 列单元格提取纯 IP 地址
        优先从整行或单元格的 data-ip 属性获取，其次通过正则匹配形如 115.77.X.244 或 1.2.3.4
        """
        # 1. 尝试从复制按钮属性 data-ip 获取（最稳健）
        if row:
            btn = row.find(attrs={"data-ip": True})
            if btn and btn.get('data-ip'):
                return btn.get('data-ip').strip()

        # 2. 从单元格自身寻找 data-ip
        btn = ip_cell.find(attrs={"data-ip": True})
        if btn and btn.get('data-ip'):
            return btn.get('data-ip').strip()

        # 3. 正则匹配提取 IP 字符串（支持掩码 X）
        cell_text = ip_cell.get_text(separator=' ').strip()
        match = re.search(r'(\d{1,3}\.\d{1,3}\.(?:[Xx]|\d{1,3})\.\d{1,3})', cell_text)
        if match:
            return match.group(1).strip()

        # 4. 回退传统节点遍历
        ip = ""
        for node in ip_cell.children:
            if isinstance(node, NavigableString):
                text = str(node).strip()
                if text:
                    ip = text
                    break

        if ip:
            ip = re.sub(r'^(socks5h?|socks4a?|http|https)\s*', '', ip, flags=re.I).strip()
            ip = re.sub(r':\d+$', '', ip).strip()

        return ip

    def tcp_ping(self, ip, port, timeout=1.2):
        """
        第一阶段快速预检：尝试建立 TCP 握手
        绝大多数非真实 IP 不会开放该端口，能在 1 秒内超时/被拒绝
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, int(port)))
            sock.close()
            return result == 0
        except Exception:
            return False

    def check_proxy_availability(self, proxy_info, timeout=8):
        """
        检测代理可用性
        协议映射:
          socks5 / socks5h → socks5://ip:port
          socks4 / socks4a → socks4://ip:port
          http   / https   → http://ip:port

        探测目标: 自建 API https://mra8-api.hf.space/
        返回 JSON 形如: {"ip": "159.54.178.95", ...}
        只要返回 200 且包含 ip 字段，即认为代理链路可用。
        """
        protocol = proxy_info['protocol']
        ip       = proxy_info['ip']
        port     = proxy_info['port']

        if protocol in ('socks5', 'socks5h'):
            proxy_url = f'socks5://{ip}:{port}'
        elif protocol in ('socks4', 'socks4a'):
            proxy_url = f'socks4://{ip}:{port}'
        elif protocol in ('http', 'https'):
            proxy_url = f'http://{ip}:{port}'
        else:
            return False

        proxies = {'http': proxy_url, 'https': proxy_url}

        try:
            response = requests.get(
                self.probe_url,
                proxies=proxies,
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            if response.status_code != 200:
                return False

            data = response.json()
            return bool(data.get('ip'))

        except Exception:
            return False

    def unmask_and_verify_ip(self, masked_proxy_info, max_workers=64):
        """
        对脱敏的掩码 IP（例如 115.77.X.244）猜测 X 从 1 到 255：
        采用【二阶段快速检测】策略：
          1. 阶段一：64 并发短超时 (1.2s) TCP 端口扫描，快速排除不通的候选；
          2. 阶段二：对 TCP 连通的少数候选执行完整代理协议验证；
          3. 发现可用代理后触发早停（Early Stop），快速返回真实 IP。
        """
        masked_ip = masked_proxy_info['ip']
        port = masked_proxy_info['port']
        protocol = masked_proxy_info['protocol']

        # 检查是否包含 X 或 x
        if not re.search(r'[Xx]', masked_ip):
            return None

        print(f"\n🔍 正在爆破破解脱敏 IP: {protocol}://{masked_ip}:{port} (遍历 X: 1~255)...")

        found_real_info = None
        stop_event = threading.Event()

        # 生成 1~255 的候选 IP 列表
        candidates = []
        for octet in range(1, 256):
            cand_ip = re.sub(r'[Xx]', str(octet), masked_ip, count=1)
            candidates.append(cand_ip)

        def _test_candidate(cand_ip):
            if stop_event.is_set():
                return None

            # 阶段一：轻量 TCP 握手预检（避免发起慢速代理协议握手）
            if not self.tcp_ping(cand_ip, port, timeout=1.2):
                return None

            if stop_event.is_set():
                return None

            # 阶段二：TCP 已通，进行完整代理协议校验
            cand_info = dict(masked_proxy_info)
            cand_info['ip'] = cand_ip
            if self.check_proxy_availability(cand_info, timeout=6):
                stop_event.set()
                return cand_info
            return None

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ip = {executor.submit(_test_candidate, ip): ip for ip in candidates}
            for future in concurrent.futures.as_completed(future_to_ip):
                res = future.result()
                if res and not found_real_info:
                    found_real_info = res
                    break

        elapsed = time.time() - start_time
        if found_real_info:
            print(f"  🎯 成功破解！真实 IP 为: {found_real_info['ip']}:{port} (耗时 {elapsed:.2f}s)")
            return found_real_info
        else:
            print(f"  ⚠️  未能爆破出有效 IP (可能节点已下线，耗时 {elapsed:.2f}s)")
            return None

    def parse_proxy_table(self, html_content):
        """
        解析代理列表 HTML（4列: 类型 / IP / 端口 / 地理信息）
        并对脱敏的掩码 IP（如 115.77.X.244）进行猜测爆破还原
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        table = soup.find('table')
        if not table:
            print("❌ 未找到代理数据表格")
            debug_file = '/tmp/proxy_page_debug.html'
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html_content[:5000])
                print(f"  页面前5000字符已保存到 {debug_file}")
            except Exception:
                pass
            return [], []

        raw_items = []
        rows = table.find_all('tr')[1:]
        print(f"  找到 {len(rows)} 行网页数据")

        for i, row in enumerate(rows):
            cells = row.find_all('td')
            if len(cells) < 4:
                continue

            try:
                # ── 列0: 协议类型 ──
                protocol_badge = cells[0].find('span', class_='badge')
                protocol = protocol_badge.get_text(strip=True).lower() if protocol_badge else "socks5"

                # ── 列1: IP 地址 ──
                ip = self.extract_ip_from_cell(cells[1], row=row)

                # ── 列2: 端口 ──
                port = cells[2].get_text(strip=True)

                # ── 列3: 地理信息 + 时间戳 ──
                location, is_residential = self.clean_location(cells[3])
                time_span = cells[3].find('span', class_='text-muted')
                timestamp = time_span.get_text(strip=True) if time_span else ""

                if not protocol or not ip or not port:
                    continue

                raw_items.append({
                    'protocol': protocol,
                    'ip': ip,
                    'port': port,
                    'timestamp': timestamp,
                    'location': location,
                    'is_residential': is_residential,
                })

            except Exception as e:
                print(f"  ⚠️  解析第{i+1}行出错: {e}")
                continue

        all_proxies = []
        proxies_str = []
        masked_count = 0
        unmasked_success = 0

        for item in raw_items:
            ip = item['ip']
            is_masked = bool(re.search(r'\.[Xx](\.|$)', ip))

            if is_masked:
                masked_count += 1
                # 执行 1~255 爆破测试
                real_info = self.unmask_and_verify_ip(item, max_workers=64)
                if real_info:
                    unmasked_success += 1
                    all_proxies.append(real_info)
                    
                    p_str = f"{real_info['protocol']}://{real_info['ip']}:{real_info['port']}"
                    if real_info['timestamp']:
                        p_str += f" [{real_info['timestamp']}]"
                    if real_info['location']:
                        p_str += f" {real_info['location']}"
                    proxies_str.append(p_str)
            else:
                # 格式验证
                if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    print(f"  ⚠️  IP 格式异常，跳过: {ip!r}")
                    continue

                all_proxies.append(item)
                p_str = f"{item['protocol']}://{item['ip']}:{item['port']}"
                if item['timestamp']:
                    p_str += f" [{item['timestamp']}]"
                if item['location']:
                    p_str += f" {item['location']}"
                proxies_str.append(p_str)

        print(f"\n📊 统计: 共识别到 {masked_count} 个掩码脱敏 IP，成功爆破还原出 {unmasked_success} 个真实可用代理。")
        return all_proxies, proxies_str

    def scrape_proxy_list(self):
        """先登录，再抓取完整代理列表并还原掩码"""
        self.login()

        try:
            print(f"\n📥 正在抓取代理列表: {self.proxy_list_url}")
            response = self.session.get(self.proxy_list_url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'

            all_proxies, proxies_str = self.parse_proxy_table(response.text)

            if all_proxies:
                resident_count = sum(1 for p in all_proxies if p['is_residential'])
                print(f"✅ 成功获取 {len(proxies_str)} 个代理")
                print(f"   其中家宽: {resident_count} 个")

            return all_proxies, proxies_str

        except requests.RequestException as e:
            print(f"❌ 网络请求错误: {e}")
            return [], []
        except Exception as e:
            print(f"❌ 抓取错误: {e}")
            import traceback
            traceback.print_exc()
            return [], []

    def check_all_proxies(self, proxy_list, max_workers=20):
        """并发检测所有未验证或全部代理的可用性"""
        if not proxy_list:
            print("没有代理需要检测")
            return []

        print(f"\n{'='*50}")
        print(f"开始最终核验 {len(proxy_list)} 个代理的连通性（探测源: {self.probe_url}）...")
        print(f"{'='*50}")

        alive_proxies = []

        def _check_one(proxy_info):
            start   = time.time()
            ok      = self.check_proxy_availability(proxy_info, timeout=10)
            elapsed = time.time() - start
            label   = f"{proxy_info['protocol']}://{proxy_info['ip']}:{proxy_info['port']}"
            return proxy_info, ok, elapsed, label

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check_one, p): p for p in proxy_list}
            for future in concurrent.futures.as_completed(futures):
                proxy_info, ok, elapsed, label = future.result()
                if ok:
                    print(f"  ✅ {label} ({elapsed:.1f}s)")
                    alive_proxies.append(proxy_info)
                else:
                    print(f"  ❌ {label} ({elapsed:.1f}s)")

        print(f"\n检测完成: {len(alive_proxies)}/{len(proxy_list)} 个代理可用")
        return alive_proxies

    def save_alive_proxies(self, alive_proxies, filename='alive.txt'):
        """保存可用代理到 alive.txt（每行 protocol://ip:port）"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath   = os.path.join(script_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                for proxy in alive_proxies:
                    f.write(f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}\n")

            if alive_proxies:
                print(f"✅ 可用代理已保存到 {filepath}，共 {len(alive_proxies)} 个")
            else:
                print(f"⚠️  本次无可用代理，已写入空文件 {filepath}（避免旧数据残留）")
            return True

        except Exception as e:
            print(f"❌ 保存文件错误: {e}")
            import traceback
            traceback.print_exc()
            return False

    def save_to_file(self, proxies_str, filename='proxy.txt'):
        """保存全部代理到 proxy.txt（带时间戳和地理信息）"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath   = os.path.join(script_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# 代理列表更新时间: "
                        f"{self.get_cn_time().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 总计: {len(proxies_str)} 个代理\n\n")
                for proxy in proxies_str:
                    f.write(f"{proxy}\n")

            print(f"✅ 代理列表已保存到 {filepath}")
            return True

        except Exception as e:
            print(f"❌ 保存文件错误: {e}")
            return False

    def send_telegram_notification(self, alive_proxies):
        """发送 Telegram 通知（最多显示前10个）"""
        if not self.tg_bot_token or not self.tg_user_id:
            print("未配置TG_BOT_TOKEN或TG_USER_ID，跳过Telegram通知")
            return False

        if not alive_proxies:
            print("没有可用代理，跳过Telegram通知")
            return True

        try:
            current_time = self.get_cn_time().strftime('%m-%d %H:%M')
            total   = len(alive_proxies)
            message = f"🌐 <b>可用代理</b> | {current_time} | 共{total}个\n\n"

            for proxy in alive_proxies[:10]:
                proxy_url = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                message  += f"<code>{proxy_url}</code>\n"
                message  += f"└ {proxy['location']}\n"

            if total > 10:
                message += f"\n... 等共 {total} 个代理"

            url     = f"https://api.telegram.org/bot{self.tg_bot_token}/sendMessage"
            payload = {
                'chat_id': self.tg_user_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }

            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            if result.get('ok'):
                print(f"✅ Telegram通知发送成功，共 {total} 个可用代理")
                return True
            else:
                print(f"❌ Telegram通知发送失败: {result}")
                return False

        except Exception as e:
            print(f"❌ Telegram通知错误: {e}")
            return False


def main():
    scraper = ProxyListScraper()
    all_proxies, proxies_str = scraper.scrape_proxy_list()

    if all_proxies:
        scraper.save_to_file(proxies_str)
        # 对全部收集到的代理统一核验
        alive_proxies = scraper.check_all_proxies(all_proxies)
        scraper.save_alive_proxies(alive_proxies, filename='alive.txt')
        scraper.send_telegram_notification(alive_proxies)
        print("\n✅ 代理列表处理完成！")
    else:
        print("未能获取到代理数据")


if __name__ == "__main__":
    main()
