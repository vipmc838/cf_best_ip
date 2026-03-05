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
        """抓取代理列表，返回所有代理的字典列表和原始字符串列表"""
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

            proxies_str = []      # 原始格式的字符串列表（用于保存到 proxy.txt）
            all_proxies = []      # 字典列表，包含每个代理的详细信息

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
                        proxy_str = f"{protocol}://{ip}:{port} [{timestamp}] {location}"
                        proxies_str.append(proxy_str)

                        all_proxies.append({
                            'protocol': protocol,
                            'ip': ip,
                            'port': port,
                            'timestamp': timestamp,
                            'location': location,
                            'is_residential': is_residential
                        })

            print(f"成功抓取到 {len(proxies_str)} 个代理，其中家宽 {sum(1 for p in all_proxies if p['is_residential'])} 个")
            return all_proxies, proxies_str

        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            return [], []
        except Exception as e:
            print(f"抓取错误: {e}")
            import traceback
            traceback.print_exc()
            return [], []

    def check_proxy_availability(self, proxy_info, timeout=10):
        """
        通用代理可用性检测（支持 SOCKS5 和 HTTP）
        使用 requests 库通过代理访问 httpbin.org/ip，成功返回 True
        """
        protocol = proxy_info['protocol']
        ip = proxy_info['ip']
        port = proxy_info['port']

        # 构造代理 URL
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
            # 使用代理访问一个简单的 HTTP 端点
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
        """
        并发检测所有代理的可用性，返回可用的代理列表
        """
        if not proxy_list:
            print("没有代理需要检测")
            return []

        print(f"\n{'='*50}")
        print(f"开始检测 {len(proxy_list)} 个代理的可用性...")
        print(f"{'='*50}")

        alive_proxies = []

        def _check_one(proxy_info):
            start = time.time()
            ok = self.check_proxy_availability(proxy_info, timeout=10)
            elapsed = time.time() - start
            label = f"{proxy_info['protocol']}://{proxy_info['ip']}:{proxy_info['port']}"
            return proxy_info, ok, elapsed, label

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_check_one, p): p for p in proxy_list}
            for future in concurrent.futures.as_completed(futures):
                proxy_info, ok, elapsed, label = future.result()
                if ok:
                    print(f"  ✅ {label} - 可用 ({elapsed:.1f}s)")
                    alive_proxies.append(proxy_info)
                else:
                    print(f"  ❌ {label} - 不可用 ({elapsed:.1f}s)")

        print(f"\n检测完成: {len(alive_proxies)}/{len(proxy_list)} 个代理可用")
        return alive_proxies

    def save_alive_proxies(self, alive_proxies, filename='alive.txt'):
        """保存可用的代理到文件（每行 protocol://ip:port）"""
        if not alive_proxies:
            print("没有可用的代理，跳过保存")
            return False

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                for proxy in alive_proxies:
                    f.write(f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}\n")

            print(f"可用代理已保存到 {filepath}，共 {len(alive_proxies)} 个")
            return True

        except Exception as e:
            print(f"保存文件错误: {e}")
            import traceback
            traceback.print_exc()
            return False

    def send_telegram_notification(self, alive_proxies):
        """发送Telegram通知，仅显示前10个可用代理及总数"""
        if not self.tg_bot_token or not self.tg_user_id:
            print("未配置TG_BOT_TOKEN或TG_USER_ID，跳过Telegram通知")
            return False

        if not alive_proxies:
            print("没有可用代理，跳过Telegram通知")
            return True

        try:
            # 构建消息
            current_time = self.get_cn_time().strftime('%m-%d %H:%M')
            total = len(alive_proxies)
            message = f"🌐 <b>可用代理</b> | {current_time} | 共{total}个\n"

            # 最多显示前10个
            display_proxies = alive_proxies[:10]
            for proxy in display_proxies:
                proxy_url = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                loc = proxy['location']
                message += f"<code>{proxy_url}</code>\n"
                message += f"└ {loc}\n"

            if total > 10:
                message += f"\n... 等共 {total} 个代理"

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
                print(f"Telegram通知发送成功，共 {total} 个可用代理")
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

    def save_to_file(self, proxies_str, filename='proxy.txt'):
        """保存原始代理列表到文件（带时间戳和位置信息）"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# 代理列表更新时间: {self.get_cn_time().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 总计: {len(proxies_str)} 个代理\n\n")

                for proxy in proxies_str:
                    f.write(f"{proxy}\n")

            print(f"代理列表已保存到 {filepath}")
            return True

        except Exception as e:
            print(f"保存文件错误: {e}")
            return False

def main():
    """主函数"""
    scraper = ProxyListScraper()
    all_proxies, proxies_str = scraper.scrape_proxy_list()

    if all_proxies:
        # 1. 保存全部代理到 proxy.txt（保留原始格式）
        scraper.save_to_file(proxies_str)

        # 2. 检测所有代理的可用性
        alive_proxies = scraper.check_all_proxies(all_proxies)

        # 3. 保存可用代理到 alive.txt
        scraper.save_alive_proxies(alive_proxies, filename='alive.txt')

        # 4. 发送 Telegram 通知（只发送可用代理）
        scraper.send_telegram_notification(alive_proxies)

        print("代理列表处理完成！")
    else:
        print("未能获取到代理数据")

if __name__ == "__main__":
    main()
