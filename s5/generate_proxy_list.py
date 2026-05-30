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
        # 使用 Session 保持登录状态
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_cn_time(self):
        """获取中国时间"""
        return datetime.now(self.cn_tz)

    def login(self):
        """
        登录网站，获取认证 Session
        从环境变量 TOMCAT1235 读取凭据，格式: 用户名-----密码
        """
        tomcat_cred = os.environ.get('TOMCAT1235', '')
        if not tomcat_cred:
            print("⚠️  未配置 TOMCAT1235 环境变量，将以未登录状态抓取（IP可能不完整）")
            return False

        # 解析凭据：用户名-----密码
        if '-----' not in tomcat_cred:
            print("⚠️  TOMCAT1235 格式错误，应为 用户名-----密码")
            return False

        parts = tomcat_cred.split('-----', 1)
        username = parts[0].strip()
        password = parts[1].strip()

        if not username or not password:
            print("⚠️  TOMCAT1235 用户名或密码为空")
            return False

        print(f"🔑 正在登录: {self.login_url} (用户: {username})")

        try:
            # 先访问登录页面，获取可能的 CSRF token 或 cookies
            login_page = self.session.get(self.login_url, timeout=30)
            login_page.raise_for_status()

            # 尝试从页面提取 CSRF token（如果有）
            soup = BeautifulSoup(login_page.text, 'html.parser')
            csrf_token = None
            csrf_input = soup.find('input', {'name': re.compile(r'csrf|_token|token', re.I)})
            if csrf_input:
                csrf_token = csrf_input.get('value', '')
                print(f"  找到 CSRF token: {csrf_token[:20]}...")

            # 构造登录数据
            login_data = {
                'username': username,
                'password': password,
            }
            if csrf_token:
                # 使用找到的实际 CSRF 字段名
                csrf_field_name = csrf_input.get('name', 'csrf_token')
                login_data[csrf_field_name] = csrf_token

            # 提交登录表单
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

            # 检查登录是否成功
            # 方法1: 检查是否重定向到非登录页面
            if '/login' not in response.url:
                print(f"✅ 登录成功 (重定向到: {response.url})")
                return True

            # 方法2: 检查响应内容是否包含登录失败标志
            resp_text = response.text.lower()
            fail_keywords = ['密码错误', '用户名或密码', 'invalid', 'incorrect', '登录失败', 'wrong password']
            for kw in fail_keywords:
                if kw in resp_text:
                    print(f"❌ 登录失败: 检测到错误关键词 '{kw}'")
                    return False

            # 方法3: 检查是否有登出链接（表示已登录）
            soup_after = BeautifulSoup(response.text, 'html.parser')
            logout_link = soup_after.find('a', href=re.compile(r'logout|sign.?out', re.I))
            if logout_link:
                print("✅ 登录成功 (检测到登出链接)")
                return True

            # 方法4: 检查响应页面是否还是登录表单
            login_form = soup_after.find('form')
            password_field = soup_after.find('input', {'type': 'password'})
            if login_form and password_field:
                print("⚠️  登录可能失败（响应页面仍包含密码输入框）")
                # 仍返回 True，让后续步骤继续尝试抓取
                return True

            print(f"✅ 登录请求完成 (状态码: {response.status_code})")
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
        """清理并提取地理位置信息，同时返回是否为家宽"""
        if not td_element:
            return "未知", False

        span = td_element.find('span')
        if not span:
            return "未知", False

        # 提取类型标签
        type_tag = ""
        is_residential = False
        if span.find('span', class_='datacenter-tag'):
            type_tag = "[机房] "
        elif span.find('span', class_='residential-tag'):
            type_tag = "[家宽] "
            is_residential = True

        # 提取 fraud badge
        fraud_tag = ""
        fraud_badge = span.find('span', class_='fraud-badge')
        if fraud_badge:
            fraud_tag = f" {fraud_badge.get_text(strip=True)}"

        # 移除不需要的元素
        for button in span.find_all('button'):
            button.decompose()
        for copy_ok in span.find_all('span', class_='copy-ok'):
            copy_ok.decompose()
        for tag_span in span.find_all('span', class_=['datacenter-tag', 'residential-tag', 'fraud-badge']):
            tag_span.decompose()
        # 移除时间信息
        for muted in span.find_all('span', class_='text-muted'):
            muted.decompose()
        # 移除按钮容器
        for inline_span in span.find_all('span', class_=lambda c: c and 'd-none' in c):
            inline_span.decompose()

        # 获取主要地理信息文本
        flex_text = span.find('span', class_='flex-text')
        if flex_text:
            location = flex_text.get_text(strip=True)
        else:
            # 获取剩余文本
            text_parts = []
            for item in span.children:
                if isinstance(item, str):
                    text = item.strip()
                    if text and text not in ['复制', '已复制']:
                        text_parts.append(text)
            location = ' '.join(text_parts)

        location = re.sub(r'\s+', ' ', location).strip()
        full_location = f"{type_tag}{fraud_tag.strip()} {location}".strip() if fraud_tag else f"{type_tag}{location}"
        full_location = re.sub(r'\s+', ' ', full_location).strip()

        return (full_location if full_location else "未知"), is_residential

    def parse_proxy_table(self, html_content):
        """
        解析代理列表 HTML，根据实际表格结构提取数据
        表格列: 类型 | IP | 端口 | 地理信息
        IP 列中包含完整 IP（登录后）或掩码 IP（未登录）
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        table = soup.find('table')
        if not table:
            print("❌ 未找到代理数据表格")
            # 调试: 保存响应内容
            debug_file = '/tmp/proxy_page_debug.html'
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content[:5000])
            print(f"  页面前5000字符已保存到 {debug_file}")
            return [], []

        proxies_str = []
        all_proxies = []

        rows = table.find_all('tr')[1:]  # 跳过表头
        print(f"  找到 {len(rows)} 行数据")

        for i, row in enumerate(rows):
            cells = row.find_all('td')

            # 根据 HTML 结构，表格有4列: 类型、IP、端口、地理信息
            if len(cells) < 4:
                continue

            try:
                # 列0: 类型（badge）
                protocol_badge = cells[0].find('span', class_='badge')
                protocol = protocol_badge.get_text(strip=True).lower() if protocol_badge else "socks5"

                # 列1: IP 地址
                # HTML: <strong class="d-sm-none">socks5 </strong>8.217.6.165<span ...>:1080</span>
                # 需要提取纯文本中的 IP 部分
                ip_cell = cells[1]
                # 移除 <strong> 和端口 <span>
                ip_text = ip_cell.get_text(strip=True)
                # 移除协议前缀（如 "socks5 "）
                ip_text = re.sub(r'^(socks5|socks4|http|https)\s+', '', ip_text, flags=re.I)
                # 移除端口后缀（如 ":1080"）
                ip_text = re.sub(r':\d+$', '', ip_text).strip()
                ip = ip_text

                # 列2: 端口
                port = cells[2].get_text(strip=True)

                # 列3: 地理信息
                location, is_residential = self.clean_location(cells[3])

                # 提取时间戳
                time_span = cells[3].find('span', class_='text-muted')
                timestamp = time_span.get_text(strip=True) if time_span else ""

                # 验证数据
                if not protocol or not ip or not port:
                    print(f"  ⚠️  第{i+1}行数据不完整: protocol={protocol}, ip={ip}, port={port}")
                    continue

                # 检查 IP 是否被掩码（含 X）
                is_masked = 'X' in ip or 'x' in ip

                proxy_str = f"{protocol}://{ip}:{port}"
                if timestamp:
                    proxy_str += f" [{timestamp}]"
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
        """抓取代理列表（先登录，再抓取完整数据）"""
        # 1. 尝试登录
        login_success = self.login()

        # 2. 抓取代理列表页面
        try:
            print(f"\n📥 正在抓取代理列表: {self.proxy_list_url}")
            response = self.session.get(self.proxy_list_url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'

            # 3. 解析数据
            all_proxies, proxies_str = self.parse_proxy_table(response.text)

            if all_proxies:
                masked_count = sum(1 for p in all_proxies if p.get('is_masked', False))
                residential_count = sum(1 for p in all_proxies if p['is_residential'])
                print(f"✅ 成功抓取到 {len(proxies_str)} 个代理")
                print(f"   其中家宽: {residential_count} 个")
                print(f"   IP被掩码: {masked_count} 个 {'(登录可能失败)' if masked_count > 0 and login_success else ''}")

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
        """通用代理可用性检测（支持 SOCKS5 和 HTTP/HTTPS）"""
        protocol = proxy_info['protocol']
        ip = proxy_info['ip']
        port = proxy_info['port']

        # 跳过掩码 IP（无法连接）
        if proxy_info.get('is_masked', False):
            return False

        # 跳过明显无效的 IP
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
            return False

        if protocol in ('socks5', 'socks5h'):
            proxy_url = f'socks5://{ip}:{port}'
        elif protocol in ('http', 'https'):
            proxy_url = f'http://{ip}:{port}'
        else:
            return False

        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }

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
        """并发检测所有代理的可用性"""
        if not proxy_list:
            print("没有代理需要检测")
            return []

        # 过滤掉掩码 IP
        valid_proxies = [p for p in proxy_list if not p.get('is_masked', False)]
        masked_proxies = [p for p in proxy_list if p.get('is_masked', False)]

        if masked_proxies:
            print(f"⚠️  跳过 {len(masked_proxies)} 个掩码IP（需要完整登录权限）")

        if not valid_proxies:
            print("没有有效代理可以检测")
            return []

        print(f"\n{'='*50}")
        print(f"开始检测 {len(valid_proxies)} 个代理的可用性...")
        print(f"{'='*50}")

        alive_proxies = []

        def _check_one(proxy_info):
            start = time.time()
            ok = self.check_proxy_availability(proxy_info, timeout=10)
            elapsed = time.time() - start
            label = f"{proxy_info['protocol']}://{proxy_info['ip']}:{proxy_info['port']}"
            return proxy_info, ok, elapsed, label

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check_one, p): p for p in valid_proxies}
            for future in concurrent.futures.as_completed(futures):
                proxy_info, ok, elapsed, label = future.result()
                if ok:
                    print(f"  ✅ {label} - 可用 ({elapsed:.1f}s)")
                    alive_proxies.append(proxy_info)
                else:
                    print(f"  ❌ {label} - 不可用 ({elapsed:.1f}s)")

        print(f"\n检测完成: {len(alive_proxies)}/{len(valid_proxies)} 个代理可用")
        return alive_proxies

    def save_alive_proxies(self, alive_proxies, filename='alive.txt'):
        """保存可用代理到文件"""
        if not alive_proxies:
            print("没有可用的代理，跳过保存")
            return False

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, filename)

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

    def save_to_file(self, proxies_str, all_proxies=None, filename='proxy.txt'):
        """保存原始代理列表到文件"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# 代理列表更新时间: {self.get_cn_time().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 总计: {len(proxies_str)} 个代理\n\n")
                for proxy in proxies_str:
                    f.write(f"{proxy}\n")

            print(f"✅ 代理列表已保存到 {filepath}")
            return True

        except Exception as e:
            print(f"❌ 保存文件错误: {e}")
            return False

    def send_telegram_notification(self, alive_proxies):
        """发送Telegram通知"""
        if not self.tg_bot_token or not self.tg_user_id:
            print("未配置TG_BOT_TOKEN或TG_USER_ID，跳过Telegram通知")
            return False

        if not alive_proxies:
            print("没有可用代理，跳过Telegram通知")
            return True

        try:
            current_time = self.get_cn_time().strftime('%m-%d %H:%M')
            total = len(alive_proxies)
            message = f"🌐 <b>可用代理</b> | {current_time} | 共{total}个\n\n"

            display_proxies = alive_proxies[:10]
            for proxy in display_proxies:
                proxy_url = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                loc = proxy['location']
                message += f"<code>{proxy_url}</code>\n"
                message += f"└ {loc}\n"

            if total > 10:
                message += f"\n... 等共 {total} 个代理"

            url = f"https://api.telegram.org/bot{self.tg_bot_token}/sendMessage"
            payload = {
                'chat_id': self.tg_user_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }

            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

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
        # 1. 保存全部代理到 proxy.txt
        scraper.save_to_file(proxies_str, all_proxies)

        # 2. 检测可用性
        alive_proxies = scraper.check_all_proxies(all_proxies)

        # 3. 保存可用代理到 alive.txt
        scraper.save_alive_proxies(alive_proxies, filename='alive.txt')

        # 4. 发送 Telegram 通知
        scraper.send_telegram_notification(alive_proxies)

        print("\n✅ 代理列表处理完成！")
    else:
        print("未能获取到代理数据")


if __name__ == "__main__":
    main()
