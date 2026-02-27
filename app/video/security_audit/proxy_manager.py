import asyncio
import aiohttp
from typing import List, Optional, Dict
from dataclasses import dataclass

@dataclass
class ProxyNode:
    url: str
    failures: int = 0
    avg_response_time: float = 0.0
    is_valid: bool = True

class AsyncProxyPool:
    def __init__(self, initial_proxies: List[str] = None, max_failures: int = 3, check_url: str = 'http://httpbin.org/ip'):
        self.proxies: Dict[str, ProxyNode] = {}
        self.max_failures = max_failures
        self.check_url = check_url
        self._lock = asyncio.Lock()
        if initial_proxies:
            self.add_proxies(initial_proxies)

    def add_proxies(self, proxy_urls: List[str]):
        for url in proxy_urls:
            if url not in self.proxies:
                self.proxies[url] = ProxyNode(url=url)

    async def validate_proxy(self, proxy: ProxyNode, session: aiohttp.ClientSession) -> bool:
        try:
            start = asyncio.get_event_loop().time()
            async with session.get(self.check_url, proxy=proxy.url, timeout=5) as resp:
                if resp.status == 200:
                    proxy.avg_response_time = asyncio.get_event_loop().time() - start
                    proxy.failures = 0
                    proxy.is_valid = True
                    return True
                else:
                    proxy.failures += 1
                    return False
        except:
            proxy.failures += 1
            return False

    async def refresh_pool(self, session: aiohttp.ClientSession):
        async with self._lock:
            tasks = [self.validate_proxy(p, session) for p in self.proxies.values()]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for proxy, ok in zip(self.proxies.values(), results):
                if isinstance(ok, Exception) or not ok:
                    if proxy.failures > self.max_failures:
                        proxy.is_valid = False

    async def get_best_proxy(self) -> Optional[ProxyNode]:
        async with self._lock:
            available = [p for p in self.proxies.values() if p.is_valid and p.failures <= self.max_failures]
            if not available:
                return None
            available.sort(key=lambda p: p.avg_response_time)
            return available[0]

    async def report_failure(self, url: str):
        async with self._lock:
            if url in self.proxies:
                self.proxies[url].failures += 1
                if self.proxies[url].failures > self.max_failures:
                    self.proxies[url].is_valid = False
