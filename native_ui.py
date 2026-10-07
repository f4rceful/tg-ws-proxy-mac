"""Native, nonmodal AppKit windows with Liquid Glass on macOS 26+."""
from copy import deepcopy
from pathlib import Path

import AppKit as A
import Foundation as F
import objc

from proxy import __version__, get_link_host
from utils.settings import validate_settings
from utils.i18n import set_language, t


def rect(x, y, w, h):
    return A.NSMakeRect(x, y, w, h)


def has_liquid_glass():
    return F.NSProcessInfo.processInfo().operatingSystemVersion()[0] >= 26 and hasattr(A, 'NSGlassEffectView')


def label(parent, text, x, y, w, h=22, size=13, bold=False, secondary=False):
    field = A.NSTextField.labelWithString_(t(text))
    field.setFrame_(rect(x, y, w, h))
    field.setFont_(A.NSFont.systemFontOfSize_weight_(size, A.NSFontWeightSemibold if bold else A.NSFontWeightRegular))
    field.setTextColor_(A.NSColor.secondaryLabelColor() if secondary else A.NSColor.labelColor())
    field.setLineBreakMode_(A.NSLineBreakByWordWrapping)
    field.setMaximumNumberOfLines_(0)
    parent.addSubview_(field)
    return field


def button(parent, text, x, y, w, target, action, primary=False):
    control = A.NSButton.buttonWithTitle_target_action_(t(text), target, action)
    control.setFrame_(rect(x, y, w, 40))
    control.setFont_(A.NSFont.systemFontOfSize_weight_(13, A.NSFontWeightMedium))
    if has_liquid_glass() and hasattr(A, 'NSBezelStyleGlass'):
        control.setBezelStyle_(A.NSBezelStyleGlass)
        control.setBorderShape_(A.NSControlBorderShapeCapsule)
        control.setTintProminence_(A.NSTintProminencePrimary if primary else A.NSTintProminenceNone)
    else:
        control.setBezelStyle_(A.NSBezelStyleRounded)
    if primary:
        control.setBezelColor_(A.NSColor.controlAccentColor())
    parent.addSubview_(control)
    return control


def glass_window(title, width, height):
    style = A.NSWindowStyleMaskTitled | A.NSWindowStyleMaskClosable | A.NSWindowStyleMaskMiniaturizable | A.NSWindowStyleMaskFullSizeContentView
    window = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(rect(0, 0, width, height), style, A.NSBackingStoreBuffered, False)
    window.setTitle_(t(title))
    window.setTitleVisibility_(A.NSWindowTitleVisible)
    window.setTitlebarAppearsTransparent_(True)
    window.setReleasedWhenClosed_(False)
    window.setOpaque_(False)
    window.setBackgroundColor_(A.NSColor.clearColor())
    if has_liquid_glass():
        surface = A.NSGlassEffectView.alloc().initWithFrame_(rect(0, 0, width, height))
        surface.setStyle_(A.NSGlassEffectViewStyleRegular)
        surface.setCornerRadius_(22)
        content = A.NSView.alloc().initWithFrame_(rect(0, 0, width, height))
        surface.setContentView_(content)
    else:
        surface = A.NSVisualEffectView.alloc().initWithFrame_(rect(0, 0, width, height))
        surface.setMaterial_(A.NSVisualEffectMaterialUnderWindowBackground)
        surface.setBlendingMode_(A.NSVisualEffectBlendingModeBehindWindow)
        surface.setState_(A.NSVisualEffectStateActive)
        content = surface
    window.setContentView_(surface)
    window.center()
    return window, content


class NativeUI(F.NSObject):
    # Keep the original dialog order and one decision per window.
    STEPS = (
        ('host', 'IP-адрес прокси:'),
        ('port', 'Порт прокси:'),
        ('secret', 'MTProto Secret (32 hex символа):'),
        ('dc_ip', 'DC → IP маппинги (через запятую, формат DC:IP):\nНапример: 2:149.154.167.220, 4:149.154.167.220'),
        ('verbose', 'Включить подробное логирование (verbose)?'),
        ('advanced', 'Расширенные настройки (буфер KB, WS пул, лог MB):\nФормат: buf_kb,pool_size,log_max_mb'),
        ('cfproxy', 'Включить Cloudflare Proxy (CfProxy)?'),
        ('cfproxy_user_domain', 'Свои CF-домены через запятую (оставьте пустым для автоматического выбора):\nDNS записи kws1-kws5,kws203 должны указывать на IP датацентров Telegram через Cloudflare.'),
        ('cfproxy_worker_domain', 'Cloudflare Worker домены через запятую (например, name.account.workers.dev):'),
    )

    def init(self):
        self = objc.super(NativeUI, self).init()
        if self is None:
            return None
        self.callbacks = {}
        self.config = {}
        self.state = 'starting'
        self.detail = ''
        self.windows = {}
        self.menu_items = {}
        self.localized_items = []
        self.draft = None
        self._saving = False
        self.update_busy = False
        self.update_info = {}
        self._quitting = False
        return self

    @objc.python_method
    def configure(self, callbacks, config, startup_available=False):
        self.callbacks = callbacks
        self.config = deepcopy(config)
        self.steps = self.STEPS + ((('autostart', 'Запускать TG WS Proxy Mac при входе в macOS?\nПосле перемещения приложения включите автозапуск заново.'),) if startup_available else ())
        set_language(config.get('language', 'auto'))

    def applicationDidFinishLaunching_(self, notification):
        self._build_menu()
        self.callbacks['started']()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False

    def applicationShouldTerminate_(self, app):
        if self._quitting:
            return A.NSTerminateNow
        self.quit_(None)
        return A.NSTerminateCancel

    @objc.python_method
    def _build_menu(self):
        self.status_item = A.NSStatusBar.systemStatusBar().statusItemWithLength_(A.NSVariableStatusItemLength)
        image = A.NSImage.alloc().initWithContentsOfFile_(str(Path(__file__).parent / 'assets/tray-icon.png'))
        if image is None:
            image = A.NSImage.imageWithSystemSymbolName_accessibilityDescription_('t.circle.fill', 'TG WS Proxy Mac')
        image.setSize_(A.NSMakeSize(22, 22))
        image.setTemplate_(True)
        self.status_item.button().setImage_(image)
        self.status_item.button().setToolTip_('TG WS Proxy Mac')
        menu = A.NSMenu.alloc().initWithTitle_('TG WS Proxy Mac')
        menu.setAutoenablesItems_(False)
        entries = [
            ('telegram', '', 'openTelegram:'),
            ('copy', 'Скопировать ссылку', 'copyLink:'),
            None,
            ('restart', 'Перезапустить прокси', 'restart:'),
            ('settings', 'Настройки...', 'settings:'),
            ('logs', 'Открыть логи', 'logs:'),
            None,
            ('release', 'Страница релиза на GitHub…', 'release:'),
            ('update', '', 'installUpdate:'),
            ('check', 'Проверить обновления…', 'checkUpdates:'),
            ('updates', '', 'toggleUpdates:'),
            None,
            ('version', t('Версия {version}', version=__version__), None),
            ('quit', 'Выход', 'quit:'),
        ]
        for entry in entries:
            if entry is None:
                menu.addItem_(A.NSMenuItem.separatorItem())
                continue
            key, title, action = entry
            item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(t(title), action, '')
            item.setTarget_(self)
            item.setEnabled_(action is not None)
            menu.addItem_(item)
            self.menu_items[key] = item
            if key not in ('telegram', 'updates', 'update', 'version'):
                self.localized_items.append((item, title))
        self.menu_items['quit'].setKeyEquivalent_('q')
        self.status_item.setMenu_(menu)
        main_menu = A.NSMenu.alloc().initWithTitle_('')
        for title, commands in (
            ('TG WS Proxy Mac', [('Настройки...', 'settings:', ',', self), ('Выход', 'quit:', 'q', self)]),
            ('Правка', [('Вырезать', 'cut:', 'x', None), ('Копировать', 'copy:', 'c', None), ('Вставить', 'paste:', 'v', None), ('Выбрать всё', 'selectAll:', 'a', None)]),
            ('Окно', [('Закрыть', 'performClose:', 'w', None)]),
        ):
            parent = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(t(title), None, '')
            submenu = A.NSMenu.alloc().initWithTitle_(t(title))
            self.localized_items.extend(((parent, title), (submenu, title)))
            for text, action, key, target in commands:
                item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(t(text), action, key)
                item.setTarget_(target)
                submenu.addItem_(item)
                self.localized_items.append((item, text))
            parent.setSubmenu_(submenu)
            main_menu.addItem_(parent)
        A.NSApplication.sharedApplication().setMainMenu_(main_menu)
        self.update_config(self.config)
        self.update_state(self.state, self.detail)
        self.update_status(self.update_info)

    @objc.python_method
    def update_config(self, config):
        self.config = deepcopy(config)
        set_language(config.get('language', 'auto'))
        for item, title in self.localized_items:
            item.setTitle_(t(title))
        if self.menu_items:
            self.menu_items['version'].setTitle_(t('Версия {version}', version=__version__))
            address = f"{get_link_host(config['host'])}:{config['port']}"
            self.menu_items['telegram'].setTitle_(t('Открыть в Telegram ({address})', address=address))
            on = config.get('check_updates', True)
            self.menu_items['updates'].setTitle_(t('✓ Проверять обновления при запуске' if on else 'Проверять обновления при запуске (выкл)'))

    @objc.python_method
    def update_state(self, state, detail=''):
        self.state, self.detail = state, detail
        text = {'starting': 'Запуск прокси…', 'running': 'Прокси работает', 'error': detail or 'Ошибка запуска', 'stopping': 'Завершение…'}.get(state, state)
        if self.menu_items:
            self.status_item.button().setToolTip_(f'TG WS Proxy Mac — {t(text)}')
            self.menu_items['restart'].setEnabled_(state in ('running', 'error') and not self.update_busy)
            self.menu_items['telegram'].setEnabled_(state == 'running')
        if state == 'error' and not self._quitting:
            self.show_message('TG WS Proxy Mac', detail or 'Не удалось запустить прокси.')

    @objc.python_method
    def update_status(self, status):
        self.update_info = deepcopy(status)
        available = bool(status.get('has_update'))
        if self.menu_items:
            item = self.menu_items['update']
            item.setHidden_(not available)
            item.setTitle_(t('Обновить {current} → {version}', current=__version__, version=status.get('latest') or '?'))
            item.setEnabled_(available and not self.update_busy)
        if 'settings' in self.windows and self.windows['settings'].isVisible() and not self._saving:
            value = self.step_field.stringValue() if self.step_field else None
            self._render_step()
            if value is not None:
                self.step_field.setStringValue_(value)

    @objc.python_method
    def show_update_progress(self):
        self.update_busy = True
        if 'message' in self.windows:
            self.windows['message'].orderOut_(None)
        if 'settings' in self.windows:
            self.windows['settings'].orderOut_(None)
        self.update_state(self.state, self.detail)
        for key in ('settings', 'update', 'check'):
            self.menu_items[key].setEnabled_(False)
        window, content = glass_window(t('Обновление'), 420, 180)
        self.windows['progress'] = window
        window.setDelegate_(self)
        window.standardWindowButton_(A.NSWindowCloseButton).setEnabled_(False)
        self.progress_label = label(content, 'Загрузка обновления…', 24, 92, 372, 44)
        self.progress_bar = A.NSProgressIndicator.alloc().initWithFrame_(rect(24, 44, 372, 18))
        self.progress_bar.setStyle_(A.NSProgressIndicatorStyleBar)
        self.progress_bar.setIndeterminate_(True)
        content.addSubview_(self.progress_bar)
        self.progress_bar.startAnimation_(None)
        self._show('progress')

    @objc.python_method
    def update_progress(self, key):
        self.progress_label.setStringValue_(t('Загрузка обновления…' if key == 'update.downloading' else 'Проверка и подготовка приложения…'))

    @objc.python_method
    def finish_update_progress(self):
        self.update_busy = False
        self.progress_bar.stopAnimation_(None)
        self.windows['progress'].orderOut_(None)
        for key in ('settings', 'check'):
            self.menu_items[key].setEnabled_(True)
        self.update_status(self.update_info)
        self.update_state(self.state, self.detail)

    def windowShouldClose_(self, window):
        return not (self.update_busy and window == self.windows.get('progress'))

    @objc.python_method
    def _show(self, key):
        self.windows[key].makeKeyAndOrderFront_(None)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def settings_(self, sender):
        if self.update_busy:
            return
        if 'settings' in self.windows and self.windows['settings'].isVisible():
            self._show('settings')
            return
        self.draft = deepcopy(self.config)
        self.step_index = 0
        self._render_step()

    @objc.python_method
    def _render_step(self):
        if 'settings' in self.windows:
            self.windows['settings'].orderOut_(None)
        key, prompt = self.steps[self.step_index]
        boolean = key in ('verbose', 'cfproxy', 'autostart')
        prompt = t(prompt)
        base_height = 200 if boolean else 270 if len(prompt) > 80 else 220
        offset = 58 if self.update_info.get('has_update') else 0
        height = base_height + offset
        window, content = glass_window('TG WS Proxy Mac', 520, height)
        self.windows['settings'] = window
        label(content, prompt, 24, (96 if boolean else 146) + offset, 472, base_height - (136 if boolean else 186), size=13)
        self.step_field = None
        if not boolean:
            self.step_field = A.NSTextField.alloc().initWithFrame_(rect(24, 104 + offset, 472, 30))
            self.step_field.setFont_(A.NSFont.systemFontOfSize_(13))
            self.step_field.setBezeled_(True)
            self.step_field.setBezelStyle_(A.NSTextFieldRoundedBezel)
            self.step_field.setAccessibilityLabel_(prompt)
            if key == 'advanced':
                value = ','.join(str(self.draft[k]) for k in ('buf_kb', 'pool_size', 'log_max_mb'))
            else:
                value = self.draft[key]
                if isinstance(value, list):
                    value = ', '.join(value)
            self.step_field.setStringValue_(str(value))
            content.addSubview_(self.step_field)
            window.setInitialFirstResponder_(self.step_field)
        self.error_label = label(content, '', 24, 58 + offset, 472, 40, size=11, secondary=True)
        self.cancel_button = button(content, 'Закрыть', 24, 16 + offset, 116, self, 'closeSettings:')
        self.cancel_button.setKeyEquivalent_('\x1b')
        if boolean:
            no = button(content, 'Нет', 252, 16 + offset, 116, self, 'answerNo:')
            no.setTag_(0)
            self.next_button = button(content, 'Да', 380, 16 + offset, 116, self, 'answerYes:', primary=True)
        else:
            if key == 'cfproxy_worker_domain':
                button(content, '?', 316, 16 + offset, 52, self, 'workerHelp:')
            self.next_button = button(content, 'OK', 380, 16 + offset, 116, self, 'nextStep:', primary=True)
        if offset:
            button(content, t('Обновить до {version}', version=self.update_info['latest']), 24, 16, 472, self, 'installUpdate:')
        self.next_button.setKeyEquivalent_('\r')
        self._saving = False
        self._show('settings')

    @objc.python_method
    def _advance(self, answer=None):
        key, _ = self.steps[self.step_index]
        values = {k: ', '.join(v) if isinstance(v, list) else v for k, v in self.draft.items()}
        if key in ('verbose', 'cfproxy', 'autostart'):
            values[key] = answer
        elif key == 'advanced':
            parts = [part.strip() for part in self.step_field.stringValue().split(',')]
            if len(parts) != 3:
                self.error_label.setStringValue_(t('Введите три числа через запятую: буфер KB, WS пул, лог MB.'))
                self.error_label.setTextColor_(A.NSColor.systemRedColor())
                return
            values.update(zip(('buf_kb', 'pool_size', 'log_max_mb'), parts))
        else:
            values[key] = self.step_field.stringValue()
        try:
            candidate = validate_settings(values, self.draft)
        except ValueError as exc:
            self.error_label.setStringValue_(t(str(exc)))
            self.error_label.setTextColor_(A.NSColor.systemRedColor())
            return
        self.draft = candidate
        if key == 'autostart':
            self.draft['autostart'] = bool(answer)
        if self.step_index < len(self.steps) - 1:
            self.step_index += 1
            self._render_step()
        else:
            self._saving = True
            self.error_label.setStringValue_(t('Сохраняем настройки…'))
            self.error_label.setTextColor_(A.NSColor.secondaryLabelColor())
            self.next_button.setEnabled_(False)
            self.cancel_button.setEnabled_(False)
            self.callbacks['save'](deepcopy(self.draft))

    def nextStep_(self, sender):
        if not self._saving:
            self._advance()

    def answerYes_(self, sender):
        self._advance(True)

    def answerNo_(self, sender):
        self._advance(False)

    def closeSettings_(self, sender):
        self.windows['settings'].orderOut_(None)
        self.draft = None

    @objc.python_method
    def settings_saved(self):
        self.windows['settings'].orderOut_(None)
        self.draft = None
        self._saving = False
        self.show_message('TG WS Proxy Mac', 'Настройки сохранены.\n\nПерезапустить прокси сейчас?', choices=(('Закрыть', None), ('Нет', None), ('Да', self.callbacks['restart'])))

    @objc.python_method
    def save_failed(self, message):
        self._saving = False
        if 'settings' in self.windows and self.windows['settings'].isVisible():
            self.error_label.setStringValue_(t(message))
            self.error_label.setTextColor_(A.NSColor.systemRedColor())
            self.next_button.setEnabled_(True)
            self.cancel_button.setEnabled_(True)
        else:
            self.show_message('TG WS Proxy Mac', message)

    @objc.python_method
    def show_first_run(self):
        host, port = get_link_host(self.config['host']), self.config['port']
        text = t('Прокси работает в строке меню.\n\nКак подключить Telegram Desktop:\nНажмите «Открыть в Telegram» в меню.\n\nВручную: Настройки → Продвинутые → Тип подключения → Прокси\nMTProto → {host} : {port}\nSecret: dd{secret}\n\nОткрыть прокси в Telegram сейчас?', host=host, port=port, secret=self.config['secret'])
        self.show_message('TG WS Proxy Mac', text, choices=(('Закрыть', None), ('Нет', None), ('Да', self.callbacks['telegram'])))

    @objc.python_method
    def show_message(self, title, text, action_title=None, action=None, choices=None):
        if 'message' in self.windows:
            self.windows['message'].orderOut_(None)
        height = 410 if len(text) > 250 else 260
        window, content = glass_window(title, 520, height)
        self.windows['message'] = window
        label(content, text, 24, 80, 472, height - 125, size=13)
        if choices is None:
            choices = [('OK', None)] if not action_title else [('Закрыть', None), (action_title, action)]
        self.message_actions = [callback for _, callback in choices]
        for index, (title, _) in enumerate(choices):
            width = 116 if len(choices) != 2 else 220
            x = 496 - (len(choices) - index) * (width + 12) + 12
            control = button(content, title, x, 20, width, self, 'messageChoice:', primary=index == len(choices) - 1)
            control.setTag_(index)
            if index == len(choices) - 1:
                control.setKeyEquivalent_('\r')
            elif index == 0:
                control.setKeyEquivalent_('\x1b')
        self._show('message')

    def messageChoice_(self, sender):
        callback = self.message_actions[sender.tag()]
        self.windows['message'].orderOut_(None)
        if callback:
            callback()

    def openTelegram_(self, sender):
        self.callbacks['telegram']()

    def copyLink_(self, sender):
        self.callbacks['copy']()

    def restart_(self, sender):
        self.callbacks['restart']()

    def logs_(self, sender):
        self.callbacks['logs']()

    def toggleUpdates_(self, sender):
        config = deepcopy(self.config)
        config['check_updates'] = not config.get('check_updates', True)
        self.callbacks['save_preferences'](config)

    def release_(self, sender):
        self.callbacks['release']()

    def workerHelp_(self, sender):
        self.callbacks['help']()

    def installUpdate_(self, sender):
        if not self.update_busy:
            self.callbacks['update']()

    def checkUpdates_(self, sender):
        if not self.update_busy:
            self.callbacks['check_updates']()

    def quit_(self, sender):
        if self.update_busy:
            self._show('progress')
            return
        if self._quitting:
            return
        self._quitting = True
        self.update_state('stopping')
        self.callbacks['quit']()
