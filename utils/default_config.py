"""Значения по умолчанию для приложения macOS."""
from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Dict

_DEFAULTS: Dict[str, Any] = {
    "port": 1443,
    "host": "127.0.0.1",
    "dc_ip": ["2:149.154.167.220", "4:149.154.167.220"],
    "verbose": False,
    "check_updates": True,
    "log_max_mb": 5,
    "buf_kb": 256,
    "pool_size": 4,
    "cfproxy": True,
    "cfproxy_user_domain": [],
    "cfproxy_worker_domain": [],
}


def default_tray_config() -> Dict[str, Any]:
    cfg = deepcopy(_DEFAULTS)
    cfg["secret"] = os.urandom(16).hex()
    return cfg
