from __future__ import annotations

import fcntl
import json
import os
import tempfile
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from proxy import get_link_host, parse_dc_ip_list, proxy_config, coerce_domain_list
from utils.default_config import default_tray_config

log = logging.getLogger("tg-ws-tray")
APP_NAME = "TgWsProxyMac"
APP_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
CONFIG_FILE = APP_DIR / "config.json"
LOG_FILE = APP_DIR / "proxy.log"
FIRST_RUN_MARKER = APP_DIR / ".first_run_done_mtproto"
IPV6_WARN_MARKER = APP_DIR / ".ipv6_warned"
DEFAULT_CONFIG: Dict[str, Any] = default_tray_config()
IS_FROZEN = bool(getattr(sys, "frozen", False))
_lock_file: Optional[TextIO] = None


def ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def acquire_lock() -> bool:
    """Keep an OS lock for the lifetime of the app, including source launches."""
    global _lock_file
    if _lock_file is not None:
        return True
    ensure_dirs()
    candidate = (APP_DIR / ".instance.lock").open("a+")
    try:
        fcntl.flock(candidate.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        candidate.close()
        return False
    except OSError:
        candidate.close()
        raise
    _lock_file = candidate
    return True


def release_lock() -> None:
    global _lock_file
    if _lock_file is not None:
        _lock_file.close()
        _lock_file = None


def load_config() -> dict:
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception as exc:
            log.warning("Failed to load config: %s", repr(exc))
    from copy import deepcopy
    return deepcopy(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    ensure_dirs()
    fd, name = tempfile.mkstemp(dir=APP_DIR, prefix='.config-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(cfg, stream, indent=2, ensure_ascii=False)
        os.replace(name, CONFIG_FILE)
    finally:
        Path(name).unlink(missing_ok=True)


def setup_logging(verbose: bool = False, log_max_mb: float = 5) -> None:
    ensure_dirs()
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    fh = logging.handlers.RotatingFileHandler(
        str(LOG_FILE), maxBytes=max(32 * 1024, int(log_max_mb * 1024 * 1024)),
        backupCount=0, encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-5s  %(name)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)
    if not IS_FROZEN:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s", datefmt="%H:%M:%S"))
        root.addHandler(ch)


def apply_proxy_config(cfg: dict) -> bool:
    try:
        dc_redirects = parse_dc_ip_list(cfg.get("dc_ip", DEFAULT_CONFIG["dc_ip"]))
    except ValueError as exc:
        log.error("Bad config dc_ip: %s", exc)
        return False
    pc = proxy_config
    pc.port = cfg.get("port", DEFAULT_CONFIG["port"])
    pc.host = cfg.get("host", DEFAULT_CONFIG["host"])
    pc.secret = cfg.get("secret", DEFAULT_CONFIG["secret"])
    pc.dc_redirects = dc_redirects
    pc.buffer_size = max(4, cfg.get("buf_kb", DEFAULT_CONFIG["buf_kb"])) * 1024
    pc.pool_size = max(0, cfg.get("pool_size", DEFAULT_CONFIG["pool_size"]))
    pc.fallback_cfproxy = cfg.get("cfproxy", DEFAULT_CONFIG["cfproxy"])
    pc.cfproxy_user_domains = coerce_domain_list(cfg.get("cfproxy_user_domain", DEFAULT_CONFIG["cfproxy_user_domain"]))
    pc.cfproxy_worker_domains = coerce_domain_list(cfg.get("cfproxy_worker_domain", DEFAULT_CONFIG["cfproxy_worker_domain"]))
    return True


def tg_proxy_url(cfg: dict) -> str:
    host = get_link_host(cfg.get("host", DEFAULT_CONFIG["host"]))
    port = cfg.get("port", DEFAULT_CONFIG["port"])
    secret = cfg.get("secret", DEFAULT_CONFIG["secret"])
    return f"tg://proxy?server={host}&port={port}&secret=dd{secret}"
