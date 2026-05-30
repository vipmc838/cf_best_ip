#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import re
import os
import concurrent.futures

class ProxyListScraper:
    def __init__(self):
        self.base_url = "https://tomcat1235.nyc.mn"
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

    def get_cn_time(self):
        return datetime.now(self.cn_tz)

    def login(self):
        """
        登录网站，从环境变量 TOMCAT1235 读取凭据
        格式: 用户名-----密码
        注意: 不打印用户名/密码，避免日志泄露
        """
        tomcat_cred = os.environ.get('TOMCAT1235', '')
        if not tomcat_cred:
            print("⚠️  未配置 TOMCAT1235 环境变量，将以未登录状态抓取（IP可能不完整）")
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

        # ✅ 不打印用户名，避免日志泄露
        print(f"🔑 正在登录: {self.login_url}")

        try:
            # 先访问登录页面获取 cookies/CSRF
            login_page = self.session.get(self.login_url, timeout=30)
            login_page.raise_for_status()

            soup = BeautifulSoup(login_page.text, 'html.parser')

            # 尝试提取 CSRF token
            csrf_token = None
            csrf_input = soup.find('input', {'name': re.compile(r'csrf|_token|token', re.I)})
            if csrf_input:
                csrf_token = csrf_input.get('value', '')

            # 构造登录数据
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

            # 检查登录结果（不打印包含用户名的重定向URL）
            if '/login' not in response.url:
                print("✅ 登录成功")
                return True

            resp_text = response.text.lower()
            fail_keywords = ['密码错误', '用户名或密码', 'invalid', 'incorrect', '登录失败', 'wrong password']
            for kw in fail_keywords:
                if kw in resp_text:
                    print(f"❌ 登录失败: 凭据错误")
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

        # 克隆元素避免破坏原始数据
        import copy
        td_copy = copy.copy(td_element)

        span = td_copy.find('span')
        if not span:
            return "未知", False

        # 提取类型标签
        type_tag = ""
        is_residential = False
        datacenter_span = span.find('span', class_='datacenter-tag')
        residential_span = span.find('span', class_='residential-tag')
        if datacenter_span:
            type_tag = "[机房]"
        elif residential_span:
            type_tag = "[家宽]"
            is_residential = True

        # 提取 fraud badge
        fraud_tag = ""
        fraud_badge = span.find('span', class_='fraud-badge')
        if fraud_badge:
            fraud_tag = fraud_badge.get_text(strip=True)

        # 提取主要地理文本
        location = ""
        flex_text_span = span.find('span', class_='flex-text')
        if flex_text_span:
            location = flex_text_span.get_text(strip=True)

        # 拼接结果
        parts = [p for p in [type_tag, fraud_tag, location] if p]
        full_location = " ".join(parts)
        full_location = re.sub(r'\s+', ' ', full_location).strip()

        return (full_location if full_location else "未知"), is_residential

    def extract_ip_from_cell(self, ip_cell, protocol):
        """
        从 IP 列单元格中提取纯 IP 地址
        
        HTML 结构:
        <td>
          <strong class="d-sm-none">socks5 </strong>
          8.217.6.165
          <span class="d-sm-none fw-bold text-info ms-1">:1080</span>
        </td>
        
        问题: get_text() 会把 <strong> 里的协议名也拼进来
        解法: 只取直接子文本节点（NavigableString）
        """
        from bs4 import NavigableString

        ip = ""
        for node in ip_cell.children:
            # 只处理直接文本节点，跳过 <strong>、<span> 等标签
            if isinstance(node, NavigableString):
                text = str(node).strip()
                if text:
                    ip = text
                    break

        # 清理可能残留的协议前缀（保险起见）
        if ip:
            ip = re.sub(
                r'^(socks5h?|socks4a?|http|https)\s*',
                '',
                ip,
                flags=re.I
            ).strip()
            # 清理端口后缀
            ip = re.sub(r':\d+$', '', ip).strip()

        return ip

    def parse_proxy_table(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')

        table = soup.find('table')
        if not table:
            print("❌ 未找到代理数据表格")
            debug_file = '/tmp/proxy_page_debug.html'
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content[:5000])
            print(f"  页面前5000字符已保存到 {debug_file}")
            return [], []

        proxies_str = []
        all_proxies = []

        rows = table.find_all('tr')[1:]
        print(f"  找到 {len(rows)} 行数据")

        for i, row in enumerate(rows):
            cells = row.find_all('td')
            if len(cells) < 4:
                continue

            try:
                # ── 列0: 协议类型 ──────────────────────────────────────
                protocol_badge = cells[0].find('span', class_='badge')
                protocol = protocol_badge.get_text(strip=True).lower() if protocol_badge else "socks5"

                # ── 列1: IP 地址（只取直接文本节点）──────────────────
                ip = self.extract_ip_from_cell(cells[1], protocol)

                # ── 列2: 端口 ─────────────────────────────────────────
                port = cells[2].get_text(strip=True)

                # ── 列3: 地理信息 + 时间戳 ───────────────────────────
                location, is_residential = self.clean_location(cells[3])
                time_span = cells[3].find('span', class_='text-muted')
                timestamp = time_span.get_text(strip=True) if time_span else ""

                # ── 数据验证 ──────────────────────────────────────────
                if not protocol or not ip or not port:
                    print(f"  ⚠️  第{i+1}行数据不完整: "
                          f"protocol={protocol!r}, ip={ip!r}, port={port!r}")
                    continue

                # 验证 IP 格式（允许掩码 IP 如 103.18.X.11）
                ip_pattern = r'^\d{1,3}(\.\d{1,3}|\.[Xx]){3}$'
                if not re.match(ip_pattern, ip):
                    # 宽松匹配：至少含点的字符串
                    if '.' not in ip:
                        print(f"  ⚠️  第{i+1}行 IP 格式异常: {ip!r}")
                        continue

                is_masked = bool(re.search(r'\.[Xx]\.|\.[Xx]$|^[Xx]\.', ip))

                # ── 构造输出字符串 ────────────────────────────────────
                proxy_str = f"{protocol}://{ip}:{port}"
                if timestamp:
                    proxy_str += f" [{timestamp}]"
                if location:
                    proxy_str += f" {location}"

                proxies_str.append(proxy_str)
                all_proxies.append({
                    'protocol': protocol,
                    'ip': ip,
                    'port': port,
                    'timestamp': timestamp,
                    'location': location,
                    'is_residential': is_residential,
                    'is_masked': is_masked
                })

            except Exception as e:
                print(f"  ⚠️  解析第{i+1}行出错: {e}")
                continue

        return all_proxies, proxies_str

    def scrape_proxy_list(self):
        """先登录，再抓取完整代理列表"""
        login_success = self.login()

        try:
            print(f"\n📥 正在抓取代理列表: {self.proxy_list_url}")
            response = self.session.get(self.proxy_list_url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'

            all_proxies, proxies_str = self.parse_proxy_table(response.text)

            if all_proxies:
                masked_count  = sum(1 for p in all_proxies if p.get('is_masked'))
                resident_count = sum(1 for p in all_proxies if p['is_residential'])
                print(f"✅ 成功抓取到 {len(proxies_str)} 个代理")
                print(f"   其中家宽: {resident_count} 个")
                if masked_count:
                    note = "（登录失败或权限不足）" if login_success else "（未登录）"
                    print(f"   IP被掩码: {masked_count} 个 {note}")

            return all_proxies, proxies_str

        except requests.RequestException as e:
            print(f"❌ 网络请求错误: {e}")
            return [], []
        except Exception as e:
            print(f"❌ 抓取错误: {e}")
            import traceback
            traceback.print_exc()
            return [], []

    def check_proxy_availability(self, proxy_info, timeout=10):
        """
        检测代理可用性
        
        协议映射:
          socks5 / socks5h  → socks5://ip:port
          socks4 / socks4a  → socks4://ip:port
          http / https      → http://ip:port
        """
        protocol = proxy_info['protocol']
        ip       = proxy_info['ip']
        port     = proxy_info['port']

        # 跳过掩码 IP
        if proxy_info.get('is_masked'):
            return False

        # 验证 IP 格式
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
            return False

        # 构造代理 URL
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
                'http://httpbin.org/ip',
                proxies=proxies,
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            return response.status_code == 200
        except Exception:
            return False

    def check_all_proxies(self, proxy_list, max_workers=20):
        """并发检测所有代理可用性"""
        if not proxy_list:
            print("没有代理需要检测")
            return []

        valid_proxies  = [p for p in proxy_list if not p.get('is_masked')]
        masked_proxies = [p for p in proxy_list if p.get('is_masked')]

        if masked_proxies:
            print(f"⚠️  跳过 {len(masked_proxies)} 个掩码IP")

        if not valid_proxies:
            print("没有有效代理可以检测")
            return []

        print(f"\n{'='*50}")
        print(f"开始检测 {len(valid_proxies)} 个代理的可用性...")
        print(f"{'='*50}")

        alive_proxies = []

        def _check_one(proxy_info):
            start = time.time()
            ok    = self.check_proxy_availability(proxy_info, timeout=10)
            elapsed = time.time() - start
            label = f"{proxy_info['protocol']}://{proxy_info['ip']}:{proxy_info['port']}"
            return proxy_info, ok, elapsed, label

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check_one, p): p for p in valid_proxies}
            for future in concurrent.futures.as_completed(futures):
                proxy_info, ok, elapsed, label = future.result()
                if ok:
                    print(f"  ✅ {label} ({elapsed:.1f}s)")
                    alive_proxies.append(proxy_info)
                else:
                    print(f"  ❌ {label} ({elapsed:.1f}s)")

        print(f"\n检测完成: {len(alive_proxies)}/{len(valid_proxies)} 个代理可用")
        return alive_proxies

    def save_alive_proxies(self, alive_proxies, filename='alive.txt'):
        """保存可用代理到 alive.txt（每行 protocol://ip:port）"""
        if not alive_proxies:
            print("没有可用的代理，跳过保存")
            return False

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath   = os.path.join(script_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                for proxy in alive_proxies:
                    f.write(f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}\n")

            print(f"✅ 可用代理已保存到 {filepath}，共 {len(alive_proxies)} 个")
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
        alive_proxies = scraper.check_all_proxies(all_proxies)
        scraper.save_alive_proxies(alive_proxies, filename='alive.txt')
        scraper.send_telegram_notification(alive_proxies)
        print("\n✅ 代理列表处理完成！")
    else:
        print("未能获取到代理数据")


if __name__ == "__main__":
    main()
