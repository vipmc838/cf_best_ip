#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime

class ProxyScraper:
    def __init__(self):
        self.url = "https://tomcat1235.nyc.mn/proxy_list"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
    
    def clean_location(self, cell):
        """清理位置信息并判断是否为家宽"""
        location = cell.text.strip()
        is_residential = False
        
        # 检查是否有家宽标签
        residential_badge = cell.find('span', class_='badge')
        if residential_badge and '家宽' in residential_badge.text:
            is_residential = True
            # 移除家宽标签文本
            location = location.replace(residential_badge.text, '').strip()
        
        # 清理多余空白
        location = ' '.join(location.split())
        
        return location, is_residential
    
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
    
    def check_socks5_proxy(self, proxy, timeout=10):
        """检测SOCKS5代理是否可用"""
        try:
            proxy_url = f"socks5://{proxy['ip']}:{proxy['port']}"
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxies,
                timeout=timeout
            )
            
            return response.status_code == 200
            
        except Exception:
            return False
    
    def check_residential_proxies(self, residential_proxies):
        """检测所有家宽代理的可用性"""
        if not residential_proxies:
            print("没有找到家宽代理")
            return []
        
        print(f"\n开始检测 {len(residential_proxies)} 个家宽代理...")
        
        valid_proxies = []
        for proxy in residential_proxies:
            ip_port = f"{proxy['ip']}:{proxy['port']}"
            if self.check_socks5_proxy(proxy):
                print(f"✓ 代理可用: {ip_port}")
                valid_proxies.append(proxy)
            else:
                print(f"✗ 代理不可用: {ip_port}")
        
        print(f"\n检测完成: {len(valid_proxies)}/{len(residential_proxies)} 个代理可用")
        return valid_proxies
    
    def save_proxies(self, proxies, filename='proxy.txt'):
        """保存代理列表到文件"""
        try:
            filepath = os.path.join(self.script_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# 代理列表更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 总计: {len(proxies)} 个代理\n\n")
                
                for proxy in proxies:
                    f.write(proxy + '\n')
            
            print(f"代理列表已保存到 {filepath}")
            return True
            
        except Exception as e:
            print(f"保存文件错误: {e}")
            return False
    
    def save_socks5_proxies(self, valid_proxies, filename='socks5.txt'):
        """保存可用的家宽SOCKS5代理到文件"""
        try:
            filepath = os.path.join(self.script_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for proxy in valid_proxies:
                    proxy_url = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                    f.write(f"{proxy_url}\n")
            
            print(f"可用家宽代理已保存到 {filepath}，共 {len(valid_proxies)} 个")
            return True
            
        except Exception as e:
            print(f"保存SOCKS5文件错误: {e}")
            return False
    
    def send_telegram_notification(self, valid_proxies):
        """发送Telegram通知"""
        bot_token = os.environ.get('TG_BOT_TOKEN')
        user_id = os.environ.get('TG_USER_ID')
        
        if not bot_token or not user_id:
            print("未配置Telegram通知")
            return False
        
        try:
            if not valid_proxies:
                message = "🔍 代理检测完成\n\n❌ 没有可用的家宽代理"
            else:
                message = f"🔍 代理检测完成\n\n✅ 发现 {len(valid_proxies)} 个可用家宽代理:\n\n"
                for proxy in valid_proxies:
                    proxy_url = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                    location = proxy.get('location', '未知')
                    message += f"📍 {proxy_url}\n   {location}\n\n"
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': user_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                print(f"Telegram通知发送成功")
                return True
            else:
                print(f"Telegram通知发送失败: {response.text}")
                return False
                
        except Exception as e:
            print(f"发送Telegram通知错误: {e}")
            return False


def main():
    scraper = ProxyScraper()
    
    # 抓取代理列表
    proxies, residential_proxies = scraper.scrape_proxy_list()
    
    if proxies:
        # 保存完整代理列表
        scraper.save_proxies(proxies)
        
        # 检测家宽代理可用性
        valid_residential = scraper.check_residential_proxies(residential_proxies)
        
        # 保存可用的家宽代理
        scraper.save_socks5_proxies(valid_residential)
        
        # 发送Telegram通知
        scraper.send_telegram_notification(valid_residential)
    else:
        print("未能抓取到代理列表")
        scraper.save_socks5_proxies([])
    
    print("代理列表抓取完成！")


if __name__ == '__main__':
    main()
