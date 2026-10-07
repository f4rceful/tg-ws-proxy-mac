"""Russian and English strings for the native macOS interface."""
import re

_language = 'ru'
EN = {
    'Закрыть': 'Close', 'Да': 'Yes', 'Нет': 'No', 'Выход': 'Quit',
    'Настройки...': 'Settings...', 'Скопировать ссылку': 'Copy link',
    'Перезапустить прокси': 'Restart proxy', 'Открыть логи': 'Open logs',
    'Страница релиза на GitHub…': 'GitHub release page…',
    'Открыть в Telegram ({address})': 'Open in Telegram ({address})',
    'Версия {version}': 'Version {version}',
    '✓ Проверять обновления при запуске': '✓ Check for updates at launch',
    'Проверять обновления при запуске (выкл)': 'Check for updates at launch (off)',
    'Проверить обновления…': 'Check for updates…',
    'Обновить {current} → {version}': 'Update {current} → {version}',
    'Обновить до {version}': 'Update to {version}',
    'Правка': 'Edit', 'Окно': 'Window', 'Вырезать': 'Cut', 'Копировать': 'Copy',
    'Вставить': 'Paste', 'Выбрать всё': 'Select All',
    'Запуск прокси…': 'Starting proxy…', 'Прокси работает': 'Proxy is running',
    'Ошибка запуска': 'Startup failed', 'Завершение…': 'Quitting…',
    'Не удалось запустить прокси.': 'Could not start the proxy.',
    'IP-адрес прокси:': 'Proxy IP address:', 'Порт прокси:': 'Proxy port:',
    'MTProto Secret (32 hex символа):': 'MTProto Secret (32 hex characters):',
    'DC → IP маппинги (через запятую, формат DC:IP):\nНапример: 2:149.154.167.220, 4:149.154.167.220':
        'DC → IP mappings (comma separated, DC:IP):\nExample: 2:149.154.167.220, 4:149.154.167.220',
    'Включить подробное логирование (verbose)?': 'Enable verbose logging?',
    'Расширенные настройки (буфер KB, WS пул, лог MB):\nФормат: buf_kb,pool_size,log_max_mb':
        'Advanced settings (buffer KB, WS pool, log MB):\nFormat: buf_kb,pool_size,log_max_mb',
    'Включить Cloudflare Proxy (CfProxy)?': 'Enable Cloudflare Proxy (CfProxy)?',
    'Свои CF-домены через запятую (оставьте пустым для автоматического выбора):\nDNS записи kws1-kws5,kws203 должны указывать на IP датацентров Telegram через Cloudflare.':
        'Custom CF domains, comma separated (leave blank for automatic selection):\nDNS records kws1-kws5,kws203 must point to Telegram data centre IPs through Cloudflare.',
    'Cloudflare Worker домены через запятую (например, name.account.workers.dev):':
        'Cloudflare Worker domains, comma separated (e.g. name.account.workers.dev):',
    'Запускать TG WS Proxy Mac при входе в macOS?\nПосле перемещения приложения включите автозапуск заново.':
        'Start TG WS Proxy Mac at macOS login?\nEnable startup again after moving the application.',
    'Введите три числа через запятую: буфер KB, WS пул, лог MB.':
        'Enter three comma-separated numbers: buffer KB, WS pool, log MB.',
    'Сохраняем настройки…': 'Saving settings…',
    'Настройки сохранены.\n\nПерезапустить прокси сейчас?': 'Settings saved.\n\nRestart the proxy now?',
    'Прокси работает в строке меню.\n\nКак подключить Telegram Desktop:\nНажмите «Открыть в Telegram» в меню.\n\nВручную: Настройки → Продвинутые → Тип подключения → Прокси\nMTProto → {host} : {port}\nSecret: dd{secret}\n\nОткрыть прокси в Telegram сейчас?':
        'The proxy runs in the menu bar.\n\nTo connect Telegram Desktop:\nChoose “Open in Telegram” in the menu.\n\nManually: Settings → Advanced → Connection type → Proxy\nMTProto → {host} : {port}\nSecret: dd{secret}\n\nOpen the proxy in Telegram now?',
    'Не удалось открыть настройки': 'Could not load settings',
    'Не удалось сохранить: {error}': 'Could not save settings: {error}',
    'Не удалось изменить автозапуск: {error}': 'Could not change login startup: {error}',
    'Ссылка скопирована': 'Link copied',
    'Откройте Telegram Desktop, вставьте ссылку в «Избранное» и нажмите на неё.':
        'Open Telegram Desktop, paste the link into Saved Messages and click it.',
    'Журнал пока пуст': 'No logs yet',
    'Записи появятся после запуска прокси.': 'Logs will appear after the proxy starts.',
    'Доступно обновление': 'Update available', 'Обновление': 'Update',
    'Открыть релиз': 'Open release', 'Установить': 'Install',
    'Установить версию {version}? Прокси будет перезапущен. Предыдущая версия приложения будет сохранена для восстановления.':
        'Install version {version}? The proxy will restart. The previous application will be kept for recovery.',
    'Загрузка обновления…': 'Downloading update…',
    'Проверка и подготовка приложения…': 'Verifying and preparing application…',
    'Дождитесь завершения подготовки обновления.': 'Please wait until update preparation completes.',
    'Не удалось установить обновление: {error}': 'Could not install update: {error}',
    'Обновлений пока нет.': 'No updates available.',
    'В этом форке пока нет опубликованных релизов.': 'This fork has no published releases yet.',
    'Проверяем обновления…': 'Checking for updates…',
    'Не удалось проверить обновления: {error}': 'Could not check for updates: {error}',
    'В релизе нет универсальной сборки macOS с контрольной суммой SHA-256.':
        'No universal macOS release with a SHA-256 digest is available.',
    'Сначала перенесите приложение из DMG в папку Applications.': 'Move the application out of the DMG into Applications first.',
    'Установите приложение перед включением автозапуска.': 'Install the application before enabling login startup.',
    'Введите корректный IPv4-адрес, например 127.0.0.1.': 'Enter a valid IPv4 address, e.g. 127.0.0.1.',
    'Secret должен содержать 32 шестнадцатеричных символа.': 'Secret must contain 32 hexadecimal characters.',
    'Размер журнала: введите число.': 'Log size: enter a number.',
    'Размер журнала: допустимо от 0,1 до 1024 МБ.': 'Log size: valid range is 0.1–1024 MB.',
    'Порт': 'Port', 'Размер буфера': 'Buffer size', 'Размер пула': 'Pool size',
}


def set_language(language='auto'):
    global _language
    if language not in ('ru', 'en'):
        import Foundation as F
        preferred = F.NSLocale.preferredLanguages()
        language = 'ru' if preferred and str(preferred[0]).startswith('ru') else 'en'
    _language = language


def t(text, **values):
    if _language == 'en':
        translated = EN.get(text)
        if translated is None:
            match = re.fullmatch(r'(Порт|Размер буфера|Размер пула): допустимо от (.+) до (.+)\.', text)
            if match:
                translated = f'{EN[match[1]]}: valid range is {match[2]}–{match[3]}.'
            elif text.endswith(': введите целое число.'):
                translated = EN.get(text.split(':')[0], text.split(':')[0]) + ': enter a whole number.'
        text = translated or text
    return text.format(**values) if values else text
