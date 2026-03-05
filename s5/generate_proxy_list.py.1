#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import re
import os
import socket
import struct
import concurrent.futures

class ProxyListScraper:
    def __init__(self):
        self.url = "https://tomcat1235.nyc.mn/proxy_list"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
        }
        self.tg_bot_token = os.environ.get('TG_BOT_TOKEN', '')
        self.tg_user_id = os.environ.get('TG_USER_ID', '')
        # 中国时区 UTC+8
        self.cn_tz = timezone(timedelta(hours=8))

    def get_cn_time(self):
        """获取中国时间"""
        return datetime.now(self.cn_tz)

    def clean_location(self, td_element):
        """清理并提取地理位置信息"""
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

        # 移除不需要的元素
        for button in span.find_all('button'):
            button.decompose()
        for copy_ok in span.find_all('span', class_='copy-ok'):
            copy_ok.decompose()
        for tag_span in span.find_all('span', class_=['datacenter-tag', 'residential-tag']):
            tag_span.decompose()

        # 获取剩余文本
        text_parts = []
        for item in span.children:
            if isinstance(item, str):
                text = item.strip()
                if text and text not in ['复制', '已复制']:
                    text_parts.append(text)
            elif item.name == 'span' and 'text-muted' in item.get('class', []):
                isp = item.get_text(strip=True)
                if isp:
                    text_parts.append(isp)

        location = ' '.join(text_parts)
        location = re.sub(r'\s+', ' ', location).strip()

        return (f"{type_tag}{location}" if location else "未知"), is_residential

    def scrape_proxy_list(self):
        """抓取代理列表"""
        try:
            print(f"正在抓取代理列表: {self.url}")
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')

            table = soup.find('table')
            if not table:
                print("未找到代理数据表格")
                return [], []

            proxies = []
            residential_proxies = []
            rows = table.find_all('tr')[1:]

            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 5:
                    protocol_badge = cells[0].find('span', class_='badge')
                    protocol = protocol_badge.text.strip().lower() if protocol_badge else "socks5"
                    ip = cells[1].text.strip()
                    port = cells[2].text.strip()
                    timestamp = cells[3].text.strip()
                    location, is_residential = self.clean_location(cells[4])

                    if protocol and ip and port:
                        proxy = f"{protocol}://{ip}:{port} [{timestamp}] {location}"
                        proxies.append(proxy)

                        # 收集家宽代理
                        if is_residential:
                            residential_proxies.append({
                                'protocol': protocol,
                                'ip': ip,
                                'port': port,
                                'timestamp': timestamp,
                                'location': location
                            })

            print(f"成功抓取到 {len(proxies)} 个代理，其中家宽 {len(residential_proxies)} 个")
            return proxies, residential_proxies

        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            return [], []
        except Exception as e:
            print(f"抓取错误: {e}")
            import traceback
            traceback.print_exc()
            return [], []

    def check_socks5_proxy(self, ip, port, timeout=10):
        """
        检测单个 SOCKS5 代理是否可用
        通过 SOCKS5 握手 + 尝试连接外部目标来验证
        """
        try:
            port = int(port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((ip, port))

            # SOCKS5 握手: 版本5, 1种认证方法, 0x00=无认证
            sock.sendall(b'\x05\x01\x00')
            response = sock.recv(2)
            if len(response) < 2 or response[0] != 0x05 or response[1] != 0x00:
                sock.close()
                return False

            # 尝试通过代理连接 httpbin.org:80 来验证代理真正可用
            target_host = "httpbin.org"
            target_port = 80
            domain_bytes = target_host.encode('utf-8')
            # SOCKS5 请求: VER=5, CMD=CONNECT(1), RSV=0, ATYP=DOMAIN(3)
            req = b'\x05\x01\x00\x03' + bytes([len(domain_bytes)]) + domain_bytes + struct.pack('!H', target_port)
            sock.sendall(req)

            response = sock.recv(10)
            if len(response) < 2 or response[1] != 0x00:
                sock.close()
                return False

            # 连接成功，发送简单 HTTP 请求验证数据通路
            http_req = f"GET /ip HTTP/1.1\r\nHost: {target_host}\r\nConnection: close\r\n\r\n"
            sock.sendall(http_req.encode())
            http_response = sock.recv(1024)
            sock.close()

            if b'HTTP/' in http_response:
                return True
            return False

        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            return False

    def check_residential_proxies(self, residential_proxies, max_workers=20):
        """
        并发检测所有家宽代理的可用性，返回可用的家宽代理列表
        """
        if not residential_proxies:
            print("没有家宽代理需要检测")
            return []

        print(f"\n{'='*50}")
        print(f"开始检测 {len(residential_proxies)} 个家宽代理的可用性...")
        print(f"{'='*50}")

        alive_proxies = []

        def _check_one(proxy_info):
            ip = proxy_info['ip']
            port = proxy_info['port']
            label = f"{proxy_info['protocol']}://{ip}:{port}"
            start = time.time()
            ok = self.check_socks5_proxy(ip, port, timeout=10)
            elapsed = time.time() - start
            return proxy_info, ok, elapsed, label

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check_one, p): p for p in residential_proxies}
            for future in concurrent.futures.as_completed(futures):
                proxy_info, ok, elapsed, label = future.result()
                if ok:
                    print(f"  ✅ {label} - 可用 ({elapsed:.1f}s)")
                    alive_proxies.append(proxy_info)
                else:
                    print(f"  ❌ {label} - 不可用 ({elapsed:.1f}s)")

        print(f"\n检测完成: {len(alive_proxies)}/{len(residential_proxies)} 个家宽代理可用")
        return alive_proxies

    def save_alive_socks5(self, alive_proxies):
        if not alive_proxies:
            print("没有可用的家宽代理，跳过保存 s5/socks5.txt")
            return False

        try:
            # 脚本本身就在 s5/ 目录下，直接保存到同目录即可
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, 'socks5.txt')

            with open(filepath, 'w', encoding='utf-8') as f:
                for proxy in alive_proxies:
                    f.write(f"socks5://{proxy['ip']}:{proxy['port']}\n")

            print(f"可用家宽代理已保存到 {filepath}，共 {len(alive_proxies)} 个")
            return True

        except Exception as e:
            print(f"保存 socks5.txt 错误: {e}")
            import traceback
            traceback.print_exc()
            return False

        except Exception as e:
            print(f"保存 s5/socks5.txt 错误: {e}")
            import traceback
            traceback.print_exc()
            return False

    def send_telegram_notification(self, residential_proxies):
        """发送Telegram通知"""
        if not self.tg_bot_token or not self.tg_user_id:
            print("未配置TG_BOT_TOKEN或TG_USER_ID，跳过Telegram通知")
            return False

        if not residential_proxies:
            print("没有家宽代理，跳过Telegram通知")
            return True

        try:
            # 构建紧凑消息（使用中国时间）
            current_time = self.get_cn_time().strftime('%m-%d %H:%M')
            message = f"🏠 <b>家宽代理</b> | {current_time} | 共{len(residential_proxies)}个\n"

            for proxy in residential_proxies:
                proxy_url = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                # 位置信息去掉[家宽]标签
                loc = proxy['location'].replace('[家宽] ', '')

                message += f"<code>{proxy_url}</code>\n"
                message += f"└ {loc}\n"

            # 发送消息
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
                print(f"Telegram通知发送成功，共 {len(residential_proxies)} 个家宽代理")
                return True
            else:
                print(f"Telegram通知发送失败: {result}")
                return False

        except requests.RequestException as e:
            print(f"Telegram通知发送错误: {e}")
            return False
        except Exception as e:
            print(f"Telegram通知错误: {e}")
            import traceback
            traceback.print_exc()
            return False

    def save_to_file(self, proxies, filename='proxy.txt'):
        """保存代理列表到文件"""
        try:
            # 获取脚本所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# 代理列表更新时间: {self.get_cn_time().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 总计: {len(proxies)} 个代理\n\n")

                for proxy in proxies:
                    f.write(f"{proxy}\n")

            print(f"代理列表已保存到 {filepath}")
            return True

        except Exception as e:
            print(f"保存文件错误: {e}")
            return False

def main():
    """主函数"""
    scraper = ProxyListScraper()
    proxies, residential_proxies = scraper.scrape_proxy_list()

    if proxies:
        # 旧功能：保存全部代理到 proxy.txt
        scraper.save_to_file(proxies)

        # 新功能1：检测家宽代理可用性
        alive_residential = scraper.check_residential_proxies(residential_proxies)

        # 新功能2：保存可用家宽代理到 s5/socks5.txt
        scraper.save_alive_socks5(alive_residential)

        # TG通知：只发送可用的家宽代理
        scraper.send_telegram_notification(alive_residential)

        print("代理列表抓取完成！")
    else:
        print("未能获取到代理数据")

if __name__ == "__main__":
    main()
