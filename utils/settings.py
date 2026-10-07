"""Validation shared by the native settings window and its tests."""
from copy import deepcopy
from ipaddress import IPv4Address
import math

from proxy import coerce_domain_list, parse_dc_ip_list


def validate_settings(values: dict, current: dict) -> dict:
    result = deepcopy(current)
    host = str(values['host']).strip()
    try:
        IPv4Address(host)
    except ValueError:
        raise ValueError('Введите корректный IPv4-адрес, например 127.0.0.1.') from None
    result['host'] = host
    for key, label, minimum, maximum in (
        ('port', 'Порт', 1, 65535),
        ('buf_kb', 'Размер буфера', 4, 65536),
        ('pool_size', 'Размер пула', 0, 32),
    ):
        try:
            number = int(str(values[key]).strip())
        except ValueError:
            raise ValueError(f'{label}: введите целое число.') from None
        if not minimum <= number <= maximum:
            raise ValueError(f'{label}: допустимо от {minimum} до {maximum}.')
        result[key] = number
    try:
        size = float(str(values['log_max_mb']).strip().replace(',', '.'))
    except ValueError:
        raise ValueError('Размер журнала: введите число.') from None
    if not math.isfinite(size) or not 0.1 <= size <= 1024:
        raise ValueError('Размер журнала: допустимо от 0,1 до 1024 МБ.')
    result['log_max_mb'] = size
    secret = str(values['secret']).strip().lower()
    if len(secret) != 32 or any(c not in '0123456789abcdef' for c in secret):
        raise ValueError('Secret должен содержать 32 шестнадцатеричных символа.')
    result['secret'] = secret
    redirects = [item.strip() for item in str(values['dc_ip']).replace(',', '\n').splitlines() if item.strip()]
    parse_dc_ip_list(redirects)
    result['dc_ip'] = redirects
    for key in ('cfproxy_user_domain', 'cfproxy_worker_domain'):
        result[key] = coerce_domain_list(values[key])
    for key in ('verbose', 'check_updates', 'cfproxy'):
        result[key] = bool(values[key])
    return result
