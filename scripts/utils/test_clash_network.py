"""
测试 Clash API 和网络连接
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 添加clash_manager路径
skill_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                          '.trae', 'skills', 'clash-manager')
sys.path.insert(0, skill_path)

from clash_manager import ClashManager

def test_clash_api():
    """测试Clash API"""
    print("\n" + "="*60)
    print("测试1: Clash API")
    print("="*60)
    
    manager = ClashManager()
    
    # 检查运行状态
    print(f"\n→ Clash运行状态: {manager.is_running()}")
    
    # 获取代理列表
    proxies = manager.get_proxy_nodes()
    print(f"→ 可用代理节点数: {len(proxies)}")
    
    if proxies:
        print(f"→ 前5个节点: {proxies[:5]}")
    
    # 检查当前模式
    try:
        r = manager.session.get(f"{manager.API_BASE}/configs")
        if r.status_code == 200:
            mode = r.json().get('mode', 'unknown')
            print(f"→ 当前模式: {mode}")
        else:
            print(f"→ 获取配置失败: {r.status_code}")
    except Exception as e:
        print(f"→ API错误: {e}")
    
    return manager


def test_network(manager, url, name):
    """测试网络连接"""
    print(f"\n→ 测试访问 {name}...")
    
    try:
        # 先尝试直连
        r = requests.get(url, timeout=10, proxies={'http': None, 'https': None})
        print(f"  直连: {r.status_code} ✓")
        return "direct"
    except Exception as e:
        pass
    
    # 尝试代理
    try:
        proxies = {'http': manager.PROXY_URL, 'https': manager.PROXY_URL}
        r = requests.get(url, timeout=15, proxies=proxies)
        print(f"  代理: {r.status_code} ✓")
        return "proxy"
    except Exception as e:
        print(f"  失败: {str(e)[:50]}")
        return "failed"


import requests

def main():
    # 测试1: Clash API
    manager = test_clash_api()
    
    print("\n" + "="*60)
    print("测试2: 切换到Global模式")
    print("="*60)
    
    # 切换到Global模式
    if manager.set_mode("global"):
        print("✓ 已切换到 Global 模式")
    else:
        print("✗ 切换失败")
    
    import time
    time.sleep(2)
    
    print("\n" + "="*60)
    print("测试3: 网络连接测试")
    print("="*60)
    
    # 测试网站
    test_sites = [
        ("https://nominatim.openstreetmap.org", "OSM"),
        ("https://github.com", "GitHub"),
        ("https://www.youtube.com", "YouTube"),
    ]
    
    for url, name in test_sites:
        result = test_network(manager, url, name)
        print(f"  结果: {result}")


if __name__ == "__main__":
    main()
