#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代理列表抓取脚本
从指定网站抓取代理列表并保存到文件
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
        location = cell.text.strip()
        is_residential = False
        
        residential_badge = cell.find('span', class_='badge')
        if residential_badge and '家宽' in residential_badge.text:
            is_residential = True
            location = location.replace(residential_badge.text, '').strip()
        
        location = ' '.join(location.split())
        
        return location, is_residential
    
    def scrape_proxy_list(self):
        try:
            print("Fetching proxy list: {}".format(self.url))
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            table = soup.find('table')
            if not table:
                print("No proxy table found")
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
                        proxy = "{}://{}:{} [{}] {}".format(protocol, ip, port, timestamp, location)
                        proxies.append(proxy)
                        
                        if is_residential:
                            residential_proxies.append({
                                'protocol': protocol,
                                'ip': ip,
                                'port': port,
                                'timestamp': timestamp,
                                'location': location
                            })
            
            print("Found {} proxies, {} residential".format(len(proxies), len(residential_proxies)))
            return proxies, residential_proxies
            
        except requests.RequestException as e:
            print("Network error: {}".format(e))
            return [], []
        except Exception as e:
            print("Scrape error: {}".format(e))
            import traceback
            traceback.print_exc()
            return [], []
    
    def check_socks5_proxy(self, proxy, timeout=10):
        try:
            proxy_url = "socks5://{}:{}".format(proxy['ip'], proxy['port'])
            proxies_dict = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxies_dict,
                timeout=timeout
            )
            
            return response.status_code == 200
            
        except Exception:
            return False
    
    def check_residential_proxies(self, residential_proxies):
        if not residential_proxies:
            print("No residential proxies found")
            return []
        
        print("\nChecking {} residential proxies...".format(len(residential_proxies)))
        
        valid_proxies = []
        for proxy in residential_proxies:
            ip_port = "{}:{}".format(proxy['ip'], proxy['port'])
            if self.check_socks5_proxy(proxy):
                print("[OK] {}".format(ip_port))
                valid_proxies.append(proxy)
            else:
                print("[FAIL] {}".format(ip_port))
        
        print("\nDone: {}/{} available".format(len(valid_proxies), len(residential_proxies)))
        return valid_proxies
    
    def save_proxies(self, proxies, filename='proxy.txt'):
        try:
            filepath = os.path.join(self.script_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("# Updated: {}\n".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                f.write("# Total: {} proxies\n\n".format(len(proxies)))
                
                for proxy in proxies:
                    f.write(proxy + '\n')
            
            print("Saved to {}".format(filepath))
            return True
            
        except Exception as e:
            print("Save error: {}".format(e))
            return False
    
    def save_socks5_proxies(self, valid_proxies, filename='socks5.txt'):
        try:
            filepath = os.path.join(self.script_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for proxy in valid_proxies:
                    proxy_url = "{}://{}:{}".format(proxy['protocol'], proxy['ip'], proxy['port'])
                    f.write(proxy_url + '\n')
            
            print("Residential proxies saved to {}, count: {}".format(filepath, len(valid_proxies)))
            return True
            
        except Exception as e:
            print("Save socks5 error: {}".format(e))
            return False
    
    def send_telegram_notification(self, valid_proxies):
        bot_token = os.environ.get('TG_BOT_TOKEN')
        user_id = os.environ.get('TG_USER_ID')
        
        if not bot_token or not user_id:
            print("Telegram not configured")
            return False
        
        try:
            if not valid_proxies:
                message = "Proxy check done\n\nNo available residential proxies"
            else:
                message = "Proxy check done\n\nFound {} residential proxies:\n\n".format(len(valid_proxies))
                for proxy in valid_proxies:
                    proxy_url = "{}://{}:{}".format(proxy['protocol'], proxy['ip'], proxy['port'])
                    location = proxy.get('location', 'Unknown')
                    message += "{}\n{}\n\n".format(proxy_url, location)
            
            url = "https://api.telegram.org/bot{}/sendMessage".format(bot_token)
            data = {
                'chat_id': user_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                print("Telegram notification sent")
                return True
            else:
                print("Telegram failed: {}".format(response.text))
                return False
                
        except Exception as e:
            print("Telegram error: {}".format(e))
            return False


def main():
    scraper = ProxyScraper()
    
    proxies, residential_proxies = scraper.scrape_proxy_list()
    
    if proxies:
        scraper.save_proxies(proxies)
        valid_residential = scraper.check_residential_proxies(residential_proxies)
        scraper.save_socks5_proxies(valid_residential)
        scraper.send_telegram_notification(valid_residential)
    else:
        print("Failed to fetch proxy list")
        scraper.save_socks5_proxies([])
    
    print("Done!")


if __name__ == '__main__':
    main()
