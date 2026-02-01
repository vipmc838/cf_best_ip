#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import re
import os

class ProxyListScraper:
    def __init__(self):
        self.url = "https://tomcat1235.nyc.mn/proxy_list"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
        }
    
    def clean_location(self, td_element):
        """清理并提取地理位置信息"""
        if not td_element:
            return "未知"
        
        span = td_element.find('span')
        if not span:
            return "未知"
        
        # 提取类型标签
        type_tag = ""
        if span.find('span', class_='datacenter-tag'):
            type_tag = "[机房] "
        elif span.find('span', class_='residential-tag'):
            type_tag = "[家宽] "
        
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
        
        return f"{type_tag}{location}" if location else "未知"
    
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
                return []
            
            proxies = []
            rows = table.find_all('tr')[1:]
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 5:
                    protocol_badge = cells[0].find('span', class_='badge')
                    protocol = protocol_badge.text.strip().lower() if protocol_badge else "socks5"
                    ip = cells[1].text.strip()
                    port = cells[2].text.strip()
                    timestamp = cells[3].text.strip()
                    location = self.clean_location(cells[4])
                    
                    if protocol and ip and port:
                        proxy = f"{protocol}://{ip}:{port} [{timestamp}] {location}"
                        proxies.append(proxy)
            
            print(f"成功抓取到 {len(proxies)} 个代理")
            return proxies
            
        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            return []
        except Exception as e:
            print(f"抓取错误: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def save_to_file(self, proxies, filename='proxy.txt'):
        """保存代理列表到文件"""
        try:
            # 获取脚本所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(script_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# 代理列表更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
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
    proxies = scraper.scrape_proxy_list()
    
    if proxies:
        scraper.save_to_file(proxies)
        print("代理列表抓取完成！")
    else:
        print("未能获取到代理数据")

if __name__ == "__main__":
    main()
