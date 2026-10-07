# Своя сборка для macOS

Репозиторий содержит приложение только для macOS и его сетевое ядро. Для разработки и сборки используется Python 3.12 или новее; GitHub Actions собирает универсальную версию на Python 3.12.

## Сборка через GitHub

1. Откройте [Actions → Build macOS](https://github.com/f4rceful/tg-ws-proxy-mac/actions/workflows/build.yml).
2. Нажмите **Run workflow**, выберите `main` и запустите сборку.
3. После успешного завершения откройте запуск и скачайте архив из раздела **Artifacts**. Для скачивания нужно войти в GitHub.
4. Распакуйте архив: внутри будут `TgWsProxyMac_universal2.dmg` и файл контрольной суммы `.sha256`.

Один DMG содержит приложение для Apple Silicon и Intel. Изменения кода в `main` также запускают сборку автоматически.

### Черновик релиза

Чтобы вместе со сборкой подготовить релиз, отметьте **Create a draft release with the DMG** при запуске workflow. Готовый черновик появится в [Releases](https://github.com/f4rceful/tg-ws-proxy-mac/releases). Проверьте описание и вложения, затем опубликуйте его кнопкой **Publish release**.

Версия берётся из `__version__` в [`proxy/__init__.py`](../proxy/__init__.py) и используется в приложении, DMG-артефакте и теге релиза. Для следующего выпуска сначала измените версию, например на `0.1.1`. Отправка тега `v0.1.1` тоже запускает сборку и создаёт черновик; версия тега должна совпадать с версией приложения.

## Локальный запуск

```bash
git clone https://github.com/f4rceful/tg-ws-proxy-mac.git
cd tg-ws-proxy-mac
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
tg-ws-proxy-tray-macos
```

Для консольного режима используйте `tg-ws-proxy`. [Аргументы и примеры](./BuildFromSource.md).

## Локальная сборка DMG

На Mac с Python 3.12 или новее выполните из папки проекта:

```bash
source .venv/bin/activate
python -m pip install '.[build]'
python -m unittest discover -s tests -v
BUILD_PYTHON="$PWD/.venv/bin/python" bash scripts/build_macos.sh
```

Результат появится в `dist/`: `TG WS Proxy Mac.app`, `TgWsProxyMac_arm64.dmg` на Apple Silicon или `TgWsProxyMac_x86_64.dmg` на Intel и контрольная сумма DMG. Локальная сборка предназначена для архитектуры текущего Mac.

Для универсального DMG используйте GitHub Actions: там устанавливается universal2 Python и объединяются необходимые зависимости для двух архитектур. Обычного Python из Homebrew для этого недостаточно.

Сборка проверяет архитектуры всех бинарных файлов, версию приложения, целостность DMG и служебную подпись приложения. Подпись Apple Developer и нотарификация не настроены, поэтому macOS может попросить подтвердить первый запуск. Старые версии macOS отдельно ещё не протестированы.

## Файлы сборки

- [`packaging/macos.spec`](../packaging/macos.spec) — приложение и его версия, иконка, идентификатор и минимальная версия macOS (11.0).
- [`assets/icon.icns`](../assets/icon.icns) — иконка в формате macOS, преобразованная из иконки оригинального проекта.
- [`scripts/build_macos.sh`](../scripts/build_macos.sh) — сборка и проверка приложения и DMG.
- [`scripts/prepare_universal2.sh`](../scripts/prepare_universal2.sh) — зависимости универсальной сборки.
- [`.github/workflows/build.yml`](../.github/workflows/build.yml) — сборка на GitHub и подготовка черновика релиза.

## Расширенная настройка

- [Cloudflare Worker](./CfWorker.md).
- [Собственный Cloudflare-домен](./CfProxy.md).
- [Файлы конфигурации приложения](./TrayConfig.md).

[Вернуться к README](./README.md).
