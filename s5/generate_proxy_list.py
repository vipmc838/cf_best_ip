#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import re
import os
import socket
import socks
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
        # 代理检测超时时间（秒）
        self.proxy_timeout = 10
        # 并发检测线程数
        self.max_workers = 20
    
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
    
    def check_socks5_proxy(self, proxy_info):
        """检测SOCKS5代理是否可用"""
        ip = proxy_info['ip']
        port = int(proxy_info['port'])
        protocol = proxy_info['protocol'].lower()
        
        # 只检测socks5代理
        if protocol != 'socks5':
            return False, proxy_info
        
        try:
            # 创建一个socks5代理socket
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, ip, port)
            s.settimeout(self.proxy_timeout)
            
            # 尝试连接一个常用网站来测试代理
            # 使用httpbin.org或其他可靠的测试端点
            test_host = "httpbin.org"
            test_port = 80
            
            s.connect((test_host, test_port))
            
            # 发送HTTP请求
            request = f"GET /ip HTTP/1.1\r\nHost: {test_host}\r\nConnection: close\r\n\r\n"
            s.sendall(request.encode())
            
            # 接收响应
            response = b""
            while True:
                try:
                    data = s.recv(4096)
                    if not data:
                        break
                    response += data
                except:
                    break
            
            s.close()
            
            # 检查是否收到有效的HTTP响应
            if b"200 OK" in response or b"HTTP/1.1 200" in response:
                print(f"✓ 代理可用: {ip}:{port}")
                return True, proxy_info
            else:
                print(f"✗ 代理响应异常: {ip}:{port}")
                return False, proxy_info
                
        except Exception as e:
            print(f"✗ 代理不可用: {ip}:{port} - {str(e)[:50]}")
            return False, proxy_info
    
    def check_proxy_with_requests(self, proxy_info):
        """使用requests库检测代理（备用方法）"""
        ip = proxy_info['ip']
        port = proxy_info['port']
        protocol = proxy_info['protocol'].lower()
        
        if protocol != 'socks5':
            return False, proxy_info
        
        proxy_url = f"socks5://{ip}:{port}"
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        try:
            # 使用代理访问测试网站
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxies,
                timeout=self.proxy_timeout
            )
            
            if response.status_code == 200:
                print(f"✓ 代理可用: {ip}:{port}")
                return True, proxy_info
            else:
                print(f"✗ 代理响应异常: {ip}:{port} - 状态码: {response.status_code}")
                return False, proxy_info
                
        except Exception as e:
            print(f"✗ 代理不可用: {ip}:{port} - {str(e)[:50]}")
            return False, proxy_info
    
    def check_proxies_batch(self, proxies):
        """批量检测代理"""
        if not proxies:
            return []
        
        print(f"\n开始检测 {len(proxies)} 个家宽代理...")
        valid_proxies = []
        
        # 使用线程池并发检测
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 优先使用requests方法（更可靠）
            futures = {executor.submit(self.check_proxy_with_requests, proxy): proxy for proxy in proxies}
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    is_valid, proxy_info = future.result()
                    if is_valid:
                        valid_proxies.append(proxy_info)
                except Exception as e:
                    print(f"检测异常: {e}")
        
        print(f"\n检测完成: {len(valid_proxies)}/{len(proxies)} 个代理可用")
        return valid_proxies
    
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
    
    def send_telegram_notification(self, residential_proxies):
        """发送Telegram通知 - 只发送可用的家宽代理"""
        if not self.tg_bot_token or not self.tg_user_id:
            print("未配置TG_BOT_TOKEN或TG_USER_ID，跳过Telegram通知")
            return False
        
        if not residential_proxies:
            print("没有可用的家宽代理，跳过Telegram通知")
            return True
        
        try:
            # 构建紧凑消息（使用中国时间）
            current_time = self.get_cn_time().strftime('%m-%d %H:%M')
            message = f"🏠 <b>可用家宽代理</b> | {current_time} | 共{len(residential_proxies)}个\n"
            
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
                print(f"Telegram通知发送成功，共 {len(residential_proxies)} 个可用家宽代理")
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
    
    def save_socks5_proxies(self, valid_proxies, filename='s5/socks5.txt'):
        """保存可用的家宽SOCKS5代理到文件"""
        try:
            # 获取脚本所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, filename)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for proxy in valid_proxies:
                    proxy_url = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                    f.write(f"{proxy_url}\n")
            
            print(f"可用家宽代理已保存到 {filepath}，共 {len(valid_proxies)} 个")
            return True
            
        except Exception as e:
            print(f"保存SOCKS5文件错误: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """主函数"""
    scraper = ProxyListScraper()
    proxies, residential_proxies = scraper.scrape_proxy_list()
    
    if proxies:
        # 保存所有代理到proxy.txt
        scraper.save_to_file(proxies)
        
        # 检测家宽代理可用性
        if residential_proxies:
            valid_residential = scraper.check_proxies_batch(residential_proxies)
            
            # 保存可用的家宽代理到s5/socks5.txt
            if valid_residential:
                scraper.save_socks5_proxies(valid_residential)
                # 发送Telegram通知（只发送可用的）
                scraper.send_telegram_notification(valid_residential)
            else:
                print("没有可用的家宽代理")
                # 创建空文件
                scraper.save_socks5_proxies([])
        else:
            print("没有找到家宽代理")
            # 创建空文件
            scraper.save_socks5_proxies([])
        
        print("代理列表抓取完成！")
    else:
        print("未能获取到代理数据")

if __name__ == "__main__":
    main()
