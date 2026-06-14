"""代理池模块：抓取、验证、管理 HTTP 代理"""

import re
import random
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


# ==================== 内置备用代理列表 ====================
FALLBACK_PROXIES = [
    "47.88.22.138:3128",
    "47.91.65.23:3128",
    "47.74.14.251:3128",
    "47.254.36.213:3128",
    "47.56.236.141:3128",
    "103.149.162.194:8080",
    "20.206.106.192:80",
    "50.174.7.100:80",
    "50.168.163.179:80",
]


class ProxyPool:
    """线程安全的 HTTP 代理池"""

    def __init__(self, fetch_proxy=None, test_url="https://www.baidu.com", timeout=8):
        """
        Args:
            fetch_proxy: 抓取代理列表时用的代理（因为 free-proxy-list.net 需翻墙）
            test_url: 验证代理时的测试地址
            timeout: 代理验证超时秒数
        """
        self._lock = threading.Lock()
        self._proxies = []
        self._index = 0
        self.fetch_proxy = fetch_proxy
        self.test_url = test_url
        self.timeout = timeout

    @property
    def proxies(self):
        """返回当前代理列表的副本"""
        with self._lock:
            return list(self._proxies)

    @property
    def count(self):
        with self._lock:
            return len(self._proxies)

    def fetch_from_web(self, limit=50):
        """从 free-proxy-list.net 抓取匿名代理

        Returns:
            list[str]: 代理字符串列表，如 ["1.2.3.4:8080", ...]
        """
        url = "https://free-proxy-list.net/"
        proxies_to_fetch = {"http": self.fetch_proxy, "https": self.fetch_proxy} if self.fetch_proxy else None

        try:
            resp = requests.get(url, proxies=proxies_to_fetch, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            if resp.status_code != 200:
                print(f"[ProxyPool] 抓取代理列表失败，HTTP {resp.status_code}")
                return []
        except Exception as e:
            print(f"[ProxyPool] 抓取代理列表异常: {e}")
            return []

        # 用正则从 HTML 表格中提取 IP:Port（只取匿名的）
        pattern = re.compile(
            r'<tr>\s*<td>(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})</td>\s*<td>(\d+)</td>\s*<td>[^<]*</td>\s*<td[^>]*>(?:anonymous|elite proxy)',
            re.IGNORECASE
        )

        raw_list = [f"{m.group(1)}:{m.group(2)}" for m in pattern.finditer(resp.text)]

        if not raw_list:
            # 宽松匹配：把所有 IP:Port 都抓出来
            loose = re.findall(r'<td>(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})</td>\s*<td>(\d+)</td>', resp.text)
            raw_list = [f"{ip}:{port}" for ip, port in loose]

        print(f"[ProxyPool] 从网页解析到 {len(raw_list)} 个代理")
        return raw_list[:limit]

    def validate_proxy(self, proxy):
        """验证单个代理是否可用

        Args:
            proxy: 代理字符串，如 "1.2.3.4:8080"

        Returns:
            str | None: 可用返回 proxy，不可用返回 None
        """
        proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        try:
            resp = requests.get(self.test_url, proxies=proxies, timeout=self.timeout,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                return proxy
        except Exception:
            pass
        return None

    def validate_batch(self, proxy_list, max_workers=10):
        """并发验证一批代理

        Args:
            proxy_list: 待验证的代理列表
            max_workers: 并发线程数

        Returns:
            list[str]: 通过验证的代理列表
        """
        working = []
        total = len(proxy_list)
        print(f"[ProxyPool] 开始验证 {total} 个代理（并发 {max_workers} 线程）...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.validate_proxy, p): p for p in proxy_list}
            done = 0
            for future in as_completed(futures):
                done += 1
                result = future.result()
                if result:
                    working.append(result)
                if done % 20 == 0 or done == total:
                    print(f"[ProxyPool] 验证进度: {done}/{total}, 已通过: {len(working)}")

        print(f"[ProxyPool] 验证完成，可用代理: {len(working)}/{total}")
        return working

    def refresh(self, target_count=5, fetch_limit=50):
        """刷新代理池：从网页抓取 → 验证 → 存入池中

        Args:
            target_count: 目标有效代理数量
            fetch_limit: 从网页抓取的最大数量

        Returns:
            int: 最终池中代理数量
        """
        raw = self.fetch_from_web(limit=fetch_limit)

        if not raw:
            print("[ProxyPool] 在线抓取失败，使用内置备用代理")
            raw = FALLBACK_PROXIES.copy()
            random.shuffle(raw)

        working = self.validate_batch(raw)

        if len(working) < target_count:
            print(f"[ProxyPool] 可用代理不足（{len(working)}），补充备用代理")
            fallback = FALLBACK_PROXIES.copy()
            random.shuffle(fallback)
            working += self.validate_batch(fallback[:10])

        with self._lock:
            self._proxies = working
            self._index = 0

        print(f"[ProxyPool] 代理池已刷新，共 {self.count} 个可用代理")
        return self.count

    def random_proxy(self):
        """随机获取一个代理（线程安全）

        Returns:
            str | None: 代理字符串，池为空时返回 None
        """
        with self._lock:
            if not self._proxies:
                return None
            return random.choice(self._proxies)

    def next_proxy(self):
        """轮询获取一个代理（线程安全，适合多线程均匀分配）

        Returns:
            str | None: 代理字符串，池为空时返回 None
        """
        with self._lock:
            if not self._proxies:
                return None
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            return proxy

    def get_unique_proxies(self, count):
        """获取不重复的 N 个代理

        Returns:
            list[str]: 代理列表（可能少于 count 如果池不够大）
        """
        with self._lock:
            if not self._proxies:
                return []
            return random.sample(self._proxies, min(count, len(self._proxies)))


# ==================== 便捷函数 ====================

def quick_pool(fetch_proxy=None, target_count=5):
    """快速创建并刷新一个代理池

    Args:
        fetch_proxy: 抓取代理列表时用的代理，如 "127.0.0.1:7897"
        target_count: 目标有效代理数

    Returns:
        ProxyPool
    """
    pool = ProxyPool(fetch_proxy=fetch_proxy)
    pool.refresh(target_count=target_count)
    return pool


if __name__ == "__main__":
    # 测试：用本地代理翻墙抓取
    pool = quick_pool(fetch_proxy="127.0.0.1:7897", target_count=5)
    for i in range(5):
        print(f"  随机代理 {i+1}: {pool.random_proxy()}")
