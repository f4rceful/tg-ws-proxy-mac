# Разработка и сборка для macOS

## Запуск из исходников

Клонируйте форк и установите его в отдельное окружение Python:

```bash
git clone https://github.com/f4rceful/tg-ws-proxy-mac.git
cd tg-ws-proxy-mac
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
tg-ws-proxy-tray-macos
```

Для консольного режима используйте `tg-ws-proxy`. Описание аргументов и примеры находятся в [инструкции по запуску из исходников](./BuildFromSource.md#консольный-режим-из-исходников).

## Сборка приложения

Проект унаследовал инфраструктуру сборки оригинального проекта:

- [`macos.py`](../macos.py) — приложение в строке меню macOS.
- [`packaging/macos.spec`](../packaging/macos.spec) — спецификация PyInstaller для `TG WS Proxy.app` с архитектурой `universal2`.
- [`.github/workflows/build.yml`](../.github/workflows/build.yml) — workflow сборки; задача `build-macos` собирает приложение и образ `TgWsProxy_macos_universal.dmg`, проверяя наличие Intel и Apple Silicon в бинарных файлах.

Workflow запускается вручную и пока также содержит задачи для других ОС. Собственные бинарные релизы форка ещё не опубликованы.

## Расширенная настройка

- [Cloudflare Worker](./CfWorker.md).
- [Собственный Cloudflare-домен](./CfProxy.md).
- [Fake TLS и upstream в Nginx](./FakeTlsNginx.md).
- [Файлы конфигурации приложения](./TrayConfig.md).

[Вернуться к README](./README.md).
