# Конфигурация приложения macOS

TG WS Proxy Mac хранит файлы в `~/Library/Application Support/TgWsProxyMac`:

- `config.json` — настройки.
- `proxy.log` — журнал работы.
- `.update_check_cache.json` — кэш проверки релизов этого форка.
- `.instance.lock` — блокировка повторного запуска приложения.

Каталог отдельный от оригинального TG WS Proxy. Чтобы перенести настройки оригинала, закройте оба приложения и скопируйте только `config.json` из `~/Library/Application Support/TgWsProxy` в новый каталог.

Пример конфигурации:

```json
{
  "host": "127.0.0.1",
  "port": 1443,
  "secret": "...",
  "dc_ip": ["2:149.154.167.220", "4:149.154.167.220"],
  "verbose": false,
  "buf_kb": 256,
  "pool_size": 4,
  "log_max_mb": 5,
  "check_updates": true,
  "cfproxy": true,
  "cfproxy_user_domain": [],
  "cfproxy_worker_domain": []
}
```

`secret` замените собственным ключом из 32 шестнадцатеричных символов; приложение создаёт его при первом запуске. Значение `...` в примере — только обозначение поля.

При `check_updates: true` приложение проверяет GitHub Releases репозитория `f4rceful/tg-ws-proxy-mac` и предлагает открыть страницу загрузки. Обновления автоматически не устанавливаются; черновики релизов не учитываются.
