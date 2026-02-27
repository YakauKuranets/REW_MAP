"""Celery worker entrypoint.

Запуск:
    celery -A celery_worker.celery worker --loglevel=info
"""

import asyncio
import logging
import os
import re
import subprocess

from celery.schedules import crontab

from app import create_app
from app.extensions import celery_app, db, redis_client

# Импорты для брутфорсера
from app.video.security_audit.async_auditor import AsyncSecurityAuditor, AsyncProxyPool, PasswordGenerator, TargetDevice
from app.video.security_audit.vuln_check import VulnerabilityScanner
from app.video.models import CameraAuditResult, HandshakeAnalysis, WifiAuditResult
from app.wordlists.models import Wordlist
from app.tasks_utils import publish_progress

flask_app = create_app()
flask_app.app_context().push()

celery = celery_app
celery.autodiscover_tasks(["app"])


HASHCAT_MODES = {
    "WPA2": "2500",
    "WPA2-PMKID": "16800",
    "WPA3": "22000",
    "WPA3-SAE": "22001",
    "WPA3-PMKID": "22000",
    "WPA3-HANDSHAKE": "22001",
}

celery.conf.beat_schedule = {
    "update-nvd-cve-daily": {
        "task": "app.tasks.cve_updater.update_nvd_cve",
        "schedule": crontab(hour=2, minute=30),
    },
    "update-wordlists-weekly": {
        "task": "app.tasks.wordlist_updater.update_wordlists",
        "schedule": crontab(day_of_week="sun", hour=3, minute=0),
    },
    "prepare-diagnostics-feedback-dataset-weekly": {
        "task": "app.ai.finetune.prepare_finetune_dataset",
        "schedule": crontab(day_of_week="mon", hour=2, minute=0),
    },
    "run-diagnostics-model-optimization-monthly": {
        "task": "app.ai.finetune.run_finetuning",
        "schedule": crontab(day_of_month="1", hour=3, minute=0),
    },
    "export-siem-events": {
        "task": "app.tasks.siem_tasks.export_pending_events",
        "schedule": crontab(minute="*/5"),
    },
    "retry-failed-siem": {
        "task": "app.tasks.siem_tasks.retry_failed_events",
        "schedule": crontab(minute=0),
    },
    "cleanup-old-siem": {
        "task": "app.tasks.siem_tasks.cleanup_old_events",
        "schedule": crontab(hour=2, minute=0),
    },
    "run-red-swarm-nightly": {
        "task": "app.tasks.diagnostics_tasks.trigger_red_swarm",
        "schedule": crontab(hour=3, minute=0),
    },
}




def _load_active_wordlist_entries(limit: int = 20000) -> list[str]:
    active = Wordlist.query.filter_by(is_active=True).order_by(Wordlist.updated_at.desc().nullslast(), Wordlist.created_at.desc()).first()
    if not active or not active.file_path or not os.path.exists(active.file_path):
        return []

    entries: list[str] = []
    try:
        with open(active.file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                pwd = line.strip()
                if not pwd:
                    continue
                entries.append(pwd)
                if len(entries) >= limit:
                    break
    except Exception:
        logging.exception("Failed to load active wordlist entries")
        return []

    return entries



def detect_security_type(pcap_path: str) -> str | None:
    """Определяет тип безопасности из handshake файла через hcxpcapngtool."""
    try:
        result = subprocess.run(
            ["hcxpcapngtool", "-i", pcap_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        output = output.upper()
        if "WPA3" in output or "SAE" in output:
            return "WPA3-SAE" if "SAE" in output else "WPA3"
        if "WPA2" in output:
            return "WPA2"
    except FileNotFoundError:
        logging.info("hcxpcapngtool is not installed; using client provided security_type")
    except Exception:
        logging.exception("Error detecting security type from %s", pcap_path)
    return None

def _publish_wifi_audit_event(task_id: str, payload: dict) -> None:
    channel = f"wifi_audit:{task_id}"
    try:
        import json

        redis_client.publish(channel, json.dumps(payload, ensure_ascii=False))
    except Exception:
        logging.debug("Unable to publish wifi audit event", exc_info=True)



def resolve_hashcat_mode(security_type: str | None, attack_type: str) -> tuple[str, int]:
    """Подобрать режим hashcat и оценку времени (сек)."""
    sec = (security_type or "WPA2").upper()
    atk = (attack_type or "handshake").lower()

    if sec.startswith("WPA3"):
        key = "WPA3-PMKID" if atk == "pmkid" else ("WPA3-SAE" if sec == "WPA3-SAE" else "WPA3-HANDSHAKE")
        return HASHCAT_MODES.get(key, "22000"), (1800 if atk == "pmkid" else 2400)

    if atk == "pmkid":
        return HASHCAT_MODES.get("WPA2-PMKID", "16800"), 900
    return HASHCAT_MODES.get("WPA2", "2500"), 1200


def convert_capture_to_22000(handshake_path: str) -> str:
    """Конвертирует capture в формат hashcat 22000 с помощью hcxpcapngtool."""
    if handshake_path.endswith(".22000"):
        return handshake_path

    target_path = f"{handshake_path}.22000"
    cmd = ["hcxpcapngtool", "-o", target_path, handshake_path]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
    except FileNotFoundError as exc:
        raise RuntimeError("hcxpcapngtool not found. Please install hcxtools.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"hcxpcapngtool failed: {stderr}") from exc

    if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
        raise RuntimeError("hcxpcapngtool produced empty 22000 output")

    return target_path


def find_cached_handshake_result(bssid: str, security_type: str | None = None) -> HandshakeAnalysis | None:
    """Ищет успешный результат по BSSID, чтобы избежать повторного перебора."""
    if not bssid:
        return None

    query = HandshakeAnalysis.query.filter(HandshakeAnalysis.bssid == bssid)
    query = query.filter(HandshakeAnalysis.password_found.isnot(None))
    query = query.filter(HandshakeAnalysis.status == "completed")

    sec = (security_type or "").strip().upper()
    if sec:
        query = query.filter(HandshakeAnalysis.security_type == sec)

    return query.order_by(HandshakeAnalysis.created_at.desc()).first()



def detect_attack_type(file_path: str, requested_attack_type: str | None = None) -> str:
    """Определить тип атаки: handshake или pmkid."""
    if requested_attack_type in {"handshake", "pmkid"}:
        return requested_attack_type

    lower_name = (file_path or '').lower()
    if 'pmkid' in lower_name or lower_name.endswith('.pmkid'):
        return 'pmkid'

    try:
        if os.path.exists(file_path) and os.path.getsize(file_path) < 1024:
            with open(file_path, 'rb') as f:
                head = f.read(256).lower()
            if b'pmkid' in head:
                return 'pmkid'
    except Exception:
        pass

    return 'handshake'


@celery.task
def run_handshake_task(task_id, handshake_path, bssid, essid, attack_type=None, security_type=None):
    """Запускает hashcat для анализа handshake и публикует прогресс."""
    with flask_app.app_context():
        analysis = HandshakeAnalysis.query.filter_by(task_id=task_id).first()
        if not analysis:
            return

        analysis.status = "running"
        analysis.progress = 0
        db.session.commit()

        wordlist = flask_app.config.get("HASHCAT_WORDLIST", "/data/wordlists/rockyou_optimized.txt")
        resolved_attack_type = detect_attack_type(handshake_path, attack_type)
        detected_security_type = detect_security_type(handshake_path)
        resolved_security_type = (security_type or analysis.security_type or detected_security_type or "WPA2").upper()
        _hashcat_mode, estimated_time = resolve_hashcat_mode(resolved_security_type, resolved_attack_type)
        analysis.security_type = resolved_security_type
        analysis.estimated_time = estimated_time
        analysis.attack_type = resolved_attack_type

        cached_result = find_cached_handshake_result(bssid, resolved_security_type)
        if cached_result and cached_result.password_found:
            analysis.status = "completed"
            analysis.progress = 100
            analysis.password_found = cached_result.password_found
            db.session.commit()
            publish_progress(
                task_id,
                100,
                100,
                found=True,
                password=cached_result.password_found,
                estimated_time=0,
            )
            return

        try:
            hashcat_target_path = convert_capture_to_22000(handshake_path)
            hashcat_mode = "22000"

            output_file = f"/tmp/{task_id}_found.txt"
            cmd = [
                "hashcat",
                "-m", hashcat_mode,
                "-a", "0",
                "-w", "3",
                "-O",
                "--status",
                "--status-timer", "1",
                "-o", output_file,
                hashcat_target_path,
                wordlist,
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

            if process.stdout is not None:
                for line in process.stdout:
                    if "Progress" not in line:
                        continue
                    match = re.search(r"(\d+)/(\d+)", line)
                    if not match:
                        continue
                    current = int(match.group(1))
                    total = int(match.group(2))
                    analysis.progress = int(current / total * 100) if total else 0
                    db.session.commit()
                    publish_progress(task_id, current, total, found=False, estimated_time=estimated_time)

            process.wait()

            if process.returncode == 0:
                analysis.status = "completed"
                analysis.progress = 100
                if os.path.exists(output_file):
                    with open(output_file, "r", encoding="utf-8", errors="ignore") as f:
                        result_line = (f.readline() or "").strip()
                    if ":" in result_line:
                        password = result_line.rsplit(":", 1)[1]
                        analysis.password_found = password
                        publish_progress(task_id, 100, 100, found=True, password=password, estimated_time=estimated_time)
                    else:
                        publish_progress(task_id, 100, 100, found=False, estimated_time=estimated_time)
                else:
                    publish_progress(task_id, 100, 100, found=False, estimated_time=estimated_time)
            else:
                analysis.status = "failed"
                analysis.progress = 100
                publish_progress(task_id, 100, 100, found=False, estimated_time=estimated_time)
        except Exception:
            logging.exception("Handshake task failed for %s", task_id)
            analysis.status = "failed"
            analysis.progress = 100
            publish_progress(task_id, 100, 100, found=False, estimated_time=estimated_time)
            raise
        finally:
            db.session.commit()


@celery.task
def run_audit_task(task_id, ip, port=None, username='admin', password=None, proxy_list=None, use_vuln_check=True):
    with flask_app.app_context():
        result = CameraAuditResult.query.filter(
            CameraAuditResult.details['task_id'].astext == task_id
        ).first()
        if not result:
            return

        # Если порт не указан, используем 80 (можно добавить обнаружение позже)
        target_port = port or 80
        target = TargetDevice(ip=ip, port=target_port)

        # 1. Проверка уязвимостей
        if use_vuln_check:
            vuln = VulnerabilityScanner(target)
            vuln_result = vuln.scan()
            if vuln_result:
                result.success = True
                result.method = vuln_result['method']
                result.password_found = vuln_result.get('password', '')
                result.details = {"vuln_data": vuln_result, "status": "completed"}
                db.session.commit()
                return

        # 2. Асинхронный брутфорс
        proxy_pool = AsyncProxyPool(initial_proxies=proxy_list or [])
        gen = PasswordGenerator(vendor=target.vendor)
        dynamic_wordlist = _load_active_wordlist_entries()
        if dynamic_wordlist:
            gen.set_wordlist(dynamic_wordlist)
        auditor = AsyncSecurityAuditor(
            target=target,
            proxy_pool=proxy_pool,
            password_gen=gen,
            username=username,
            auth_type='basic',  # можно параметризовать
            concurrency=50
        )
        try:
            found = asyncio.run(auditor.run())
        except Exception as e:
            result.success = False
            result.details = {"error": f"Bruteforce failed: {str(e)}", "status": "failed"}
            db.session.commit()
            return

        result.success = bool(found)
        result.password_found = found
        result.method = 'bruteforce' if found else 'none'
        result.details = {"status": "completed"}
        db.session.commit()


@celery.task(bind=True)
def run_wifi_audit_task(self, task_id, bssid, essid, security_type, region="ru"):
    from app.video.security_audit.wifi_auditor import WifiAuditor

    auditor = WifiAuditor(region=region)

    with flask_app.app_context():
        record = WifiAuditResult.query.filter_by(task_id=task_id).first()
        if record:
            details = dict(record.details or {})
            details.update({"status": "running", "message": "Задача выполняется", "progress": max(record.progress or 1, 1)})
            record.details = details
            record.progress = max(record.progress or 1, 1)
            db.session.commit()
            _publish_wifi_audit_event(task_id, {"status": "running", "progress": int(record.progress or 1)})
            publish_progress(task_id, int(record.progress or 1), 100, found=False)

    def _progress_callback(state=None, meta=None, **kwargs):
        payload = meta or kwargs.get("meta") or {}
        try:
            self.update_state(state=state or "PROGRESS", meta=payload)
        except Exception:
            pass
        percent = int(payload.get("progress", 0) or 0)
        found = bool(payload.get("found", False))
        publish_progress(task_id, percent, 100, found=found)

    try:
        analysis = auditor.audit(
            bssid,
            essid,
            security_type,
            progress_callback=_progress_callback,
        )
    except Exception as exc:
        logging.exception("Wifi audit task failed for %s", task_id)
        with flask_app.app_context():
            record = WifiAuditResult.query.filter_by(task_id=task_id).first()
            if record:
                record.progress = 100
                record.details = {
                    "status": "failed",
                    "progress": 100,
                    "message": f"Ошибка выполнения аудита: {exc}",
                }
                db.session.commit()
                _publish_wifi_audit_event(task_id, record.details)
                publish_progress(task_id, 100, 100, found=False)
        raise

    with flask_app.app_context():
        record = WifiAuditResult.query.filter_by(task_id=task_id).first()
        if record:
            record.is_vulnerable = analysis.get('is_vulnerable', False)
            record.vulnerability_type = analysis.get('vulnerability_type')
            record.found_password = analysis.get('password')
            details = analysis.get('details', {})
            details["status"] = details.get("status", "completed")
            details["progress"] = int(details.get("progress", 100) or 100)
            record.estimated_time_seconds = int(details.get('estimatedTime', details.get('estimated_time_seconds', record.estimated_time_seconds or 0)) or 0)
            record.progress = int(details.get('progress', 100) or 100)
            if record.progress <= 0:
                record.progress = 100
            record.details = details
            db.session.commit()
            _publish_wifi_audit_event(task_id, details)
            # Финальный сигнал завершения задачи для realtime-клиентов
            publish_progress(task_id, 100, 100, found=True)
