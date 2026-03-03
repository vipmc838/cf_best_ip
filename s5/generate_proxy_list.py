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
        # 获取脚本所在目录
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
    
    def fetch_proxies(self):
        """抓取代理列表"""
        try:
            print(f"正在抓取代理列表: {self.url}")
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找代理列表容器
            proxy_list = soup.find('ul', class_='proxy-list')
            if not proxy_list:
                print("未找到代理列表")
                return []
            
            proxies = []
            residential_count = 0
            
            # 遍历所有代理项
            for item in proxy_list.find_all('li', class_='proxy-item'):
                proxy_data = self.parse_proxy_item(item)
                if proxy_data:
                    proxies.append(proxy_data)
                    if proxy_data.get('is_residential'):
                        residential_count += 1
            
            print(f"成功抓取到 {len(proxies)} 个代理，其中家宽 {residential_count} 个")
            return proxies
            
        except requests.RequestException as e:
            print(f"请求错误: {e}")
            return []
        except Exception as e:
            print(f"抓取错误: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def parse_proxy_item(self, item):
        """解析单个代理项"""
        try:
            # 获取协议类型
            protocol_tag = item.find('span', class_='protocol-tag')
            protocol = protocol_tag.get_text(strip=True).lower() if protocol_tag else 'socks5'
            
            # 获取IP地址
            ip_elem = item.find('span', class_='ip')
            ip = ip_elem.get_text(strip=True) if ip_elem else None
            
            # 获取端口
            port_elem = item.find('span', class_='port')
            port = port_elem.get_text(strip=True).replace(':', '') if port_elem else None
            
            if not ip or not port:
                return None
            
            # 获取更新时间
            time_elem = item.find('span', class_='update-time')
            update_time = time_elem.get_text(strip=True) if time_elem else ''
            
            # 获取位置信息
            location_elem = item.find('div', class_='location')
            location = location_elem.get_text(strip=True) if location_elem else ''
            
            # 获取ISP信息
            isp_elem = item.find('div', class_='isp')
            isp = isp_elem.get_text(strip=True) if isp_elem else ''
            
            # 检查是否为家宽
            is_residential = False
            residential_tag = item.find('span', class_='residential-tag')
            if residential_tag:
                is_residential = True
            elif item.get('class') and 'residential' in ' '.join(item.get('class', [])):
                is_residential = True
            
            # 获取类型标签
            type_tag = item.find('span', class_='type-tag')
            type_text = type_tag.get_text(strip=True) if type_tag else ''
            if '家宽' in type_text or '住宅' in type_text:
                is_residential = True
            
            return {
                'protocol': protocol,
                'ip': ip,
                'port': port,
                'update_time': update_time,
                'location': location,
                'isp': isp,
                'is_residential': is_residential,
                'type': type_text if type_text else ('家宽' if is_residential else '机房')
            }
            
        except Exception as e:
            print(f"解析代理项错误: {e}")
            return None
    
    def check_socks5_proxy(self, proxy, timeout=10):
        """检测SOCKS5代理是否可用"""
        try:
            proxy_url = f"socks5://{proxy['ip']}:{proxy['port']}"
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # 使用httpbin测试代理
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxies,
                timeout=timeout
            )
            
            if response.status_code == 200:
                return True
            return False
            
        except Exception as e:
            return False
    
    def check_residential_proxies(self, proxies):
        """检测所有家宽代理的可用性"""
        # 筛选家宽代理
        residential_proxies = [p for p in proxies if p.get('is_residential')]
        
        if not residential_proxies:
            print("没有找到家宽代理")
            return []
        
        print(f"\n开始检测 {len(residential_proxies)} 个家宽代理...")
        
        valid_proxies = []
        for proxy in residential_proxies:
            ip_port = f"{proxy['ip']}:{proxy['port']}"
            try:
                if self.check_socks5_proxy(proxy):
                    print(f"✓ 代理可用: {ip_port}")
                    valid_proxies.append(proxy)
                else:
                    print(f"✗ 代理不可用: {ip_port}")
            except Exception as e:
                error_msg = str(e)[:50]
                print(f"✗ 代理不可用: {ip_port} - {error_msg}")
        
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
                    line = f"{proxy['protocol']}://{proxy['ip']}:{proxy['port']}"
                    if proxy.get('update_time'):
                        line += f" [{proxy['update_time']}]"
                    if proxy.get('type'):
                        line += f" [{proxy['type']}]"
                    if proxy.get('location'):
                        line += f" {proxy['location']}"
                    if proxy.get('isp'):
                        line += f" [{proxy['isp']}]"
                    f.write(line + '\n')
            
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
            import traceback
            traceback.print_exc()
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
                print(f"Telegram通知发送成功，共 {len(valid_proxies)} 个可用家宽代理")
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
    proxies = scraper.fetch_proxies()
    
    if proxies:
        # 保存完整代理列表
        scraper.save_proxies(proxies)
        
        # 检测家宽代理可用性
        valid_residential = scraper.check_residential_proxies(proxies)
        
        # 保存可用的家宽代理
        scraper.save_socks5_proxies(valid_residential)
        
        # 发送Telegram通知
        scraper.send_telegram_notification(valid_residential)
    else:
        print("未能抓取到代理列表")
        # 创建空文件
        scraper.save_socks5_proxies([])
    
    print("代理列表抓取完成！")


if __name__ == '__main__':
    main()
