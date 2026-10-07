"""Native, nonmodal AppKit windows with Liquid Glass on macOS 26+."""
from copy import deepcopy

import AppKit as A
import Foundation as F
import objc

from proxy import __version__, get_link_host
from utils.settings import validate_settings


def rect(x, y, w, h):
    return A.NSMakeRect(x, y, w, h)


def has_liquid_glass():
    return F.NSProcessInfo.processInfo().operatingSystemVersion()[0] >= 26 and hasattr(A, 'NSGlassEffectView')


def label(parent, text, x, y, w, h=22, size=13, bold=False, secondary=False):
    field = A.NSTextField.labelWithString_(text)
    field.setFrame_(rect(x, y, w, h))
    field.setFont_(A.NSFont.systemFontOfSize_weight_(size, A.NSFontWeightSemibold if bold else A.NSFontWeightRegular))
    field.setTextColor_(A.NSColor.secondaryLabelColor() if secondary else A.NSColor.labelColor())
    field.setLineBreakMode_(A.NSLineBreakByWordWrapping)
    field.setMaximumNumberOfLines_(0)
    parent.addSubview_(field)
    return field


def button(parent, text, x, y, w, target, action, primary=False):
    control = A.NSButton.buttonWithTitle_target_action_(text, target, action)
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
    window.setTitle_(title)
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
        self.draft = None
        self._saving = False
        self._quitting = False
        return self

    @objc.python_method
    def configure(self, callbacks, config):
        self.callbacks = callbacks
        self.config = deepcopy(config)

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
        # The original round T icon, drawn natively for both appearances.
        image = A.NSImage.alloc().initWithSize_(A.NSMakeSize(18, 18))
        image.lockFocus()
        A.NSColor.blackColor().setFill()
        A.NSBezierPath.bezierPathWithOvalInRect_(rect(0, 0, 18, 18)).fill()
        text = F.NSString.stringWithString_('T')
        attributes = {A.NSFontAttributeName: A.NSFont.boldSystemFontOfSize_(12), A.NSForegroundColorAttributeName: A.NSColor.whiteColor()}
        text.drawAtPoint_withAttributes_(A.NSMakePoint(5, 2), attributes)
        image.unlockFocus()
        image.setTemplate_(False)
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
            ('updates', '', 'toggleUpdates:'),
            None,
            ('version', f'Версия {__version__}', None),
            ('quit', 'Выход', 'quit:'),
        ]
        for entry in entries:
            if entry is None:
                menu.addItem_(A.NSMenuItem.separatorItem())
                continue
            key, title, action = entry
            item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, '')
            item.setTarget_(self)
            item.setEnabled_(action is not None)
            menu.addItem_(item)
            self.menu_items[key] = item
        self.menu_items['quit'].setKeyEquivalent_('q')
        self.status_item.setMenu_(menu)
        main_menu = A.NSMenu.alloc().initWithTitle_('')
        for title, commands in (
            ('TG WS Proxy Mac', [('Настройки...', 'settings:', ',', self), ('Выход', 'quit:', 'q', self)]),
            ('Правка', [('Вырезать', 'cut:', 'x', None), ('Копировать', 'copy:', 'c', None), ('Вставить', 'paste:', 'v', None), ('Выбрать всё', 'selectAll:', 'a', None)]),
            ('Окно', [('Закрыть', 'performClose:', 'w', None)]),
        ):
            parent = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, '')
            submenu = A.NSMenu.alloc().initWithTitle_(title)
            for text, action, key, target in commands:
                item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(text, action, key)
                item.setTarget_(target)
                submenu.addItem_(item)
            parent.setSubmenu_(submenu)
            main_menu.addItem_(parent)
        A.NSApplication.sharedApplication().setMainMenu_(main_menu)
        self.update_config(self.config)
        self.update_state(self.state, self.detail)

    @objc.python_method
    def update_config(self, config):
        self.config = deepcopy(config)
        if self.menu_items:
            address = f"{get_link_host(config['host'])}:{config['port']}"
            self.menu_items['telegram'].setTitle_(f'Открыть в Telegram ({address})')
            on = config.get('check_updates', True)
            self.menu_items['updates'].setTitle_('✓ Проверять обновления при запуске' if on else 'Проверять обновления при запуске (выкл)')

    @objc.python_method
    def update_state(self, state, detail=''):
        self.state, self.detail = state, detail
        text = {'starting': 'Запуск прокси…', 'running': 'Прокси работает', 'error': detail or 'Ошибка запуска', 'stopping': 'Завершение…'}.get(state, state)
        if self.menu_items:
            self.status_item.button().setToolTip_(f'TG WS Proxy Mac — {text}')
            self.menu_items['restart'].setEnabled_(state in ('running', 'error'))
            self.menu_items['telegram'].setEnabled_(state == 'running')
        if state == 'error' and not self._quitting:
            self.show_message('TG WS Proxy Mac', detail or 'Не удалось запустить прокси.')

    @objc.python_method
    def _show(self, key):
        self.windows[key].makeKeyAndOrderFront_(None)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def settings_(self, sender):
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
        key, prompt = self.STEPS[self.step_index]
        boolean = key in ('verbose', 'cfproxy')
        height = 200 if boolean else 270 if len(prompt) > 80 else 220
        window, content = glass_window('TG WS Proxy Mac', 520, height)
        self.windows['settings'] = window
        label(content, prompt, 24, 96 if boolean else 146, 472, height - (136 if boolean else 186), size=13)
        self.step_field = None
        if not boolean:
            self.step_field = A.NSTextField.alloc().initWithFrame_(rect(24, 104, 472, 30))
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
        self.error_label = label(content, '', 24, 58, 472, 40, size=11, secondary=True)
        self.cancel_button = button(content, 'Закрыть', 24, 16, 116, self, 'closeSettings:')
        self.cancel_button.setKeyEquivalent_('\x1b')
        if boolean:
            no = button(content, 'Нет', 252, 16, 116, self, 'answerNo:')
            no.setTag_(0)
            self.next_button = button(content, 'Да', 380, 16, 116, self, 'answerYes:', primary=True)
        else:
            if key == 'cfproxy_worker_domain':
                button(content, '?', 316, 16, 52, self, 'workerHelp:')
            self.next_button = button(content, 'OK', 380, 16, 116, self, 'nextStep:', primary=True)
        self.next_button.setKeyEquivalent_('\r')
        self._saving = False
        self._show('settings')

    @objc.python_method
    def _advance(self, answer=None):
        key, _ = self.STEPS[self.step_index]
        values = {k: ', '.join(v) if isinstance(v, list) else v for k, v in self.draft.items()}
        if key in ('verbose', 'cfproxy'):
            values[key] = answer
        elif key == 'advanced':
            parts = [part.strip() for part in self.step_field.stringValue().split(',')]
            if len(parts) != 3:
                self.error_label.setStringValue_('Введите три числа через запятую: буфер KB, WS пул, лог MB.')
                self.error_label.setTextColor_(A.NSColor.systemRedColor())
                return
            values.update(zip(('buf_kb', 'pool_size', 'log_max_mb'), parts))
        else:
            values[key] = self.step_field.stringValue()
        try:
            candidate = validate_settings(values, self.draft)
        except ValueError as exc:
            self.error_label.setStringValue_(str(exc))
            self.error_label.setTextColor_(A.NSColor.systemRedColor())
            return
        self.draft = candidate
        if self.step_index < len(self.STEPS) - 1:
            self.step_index += 1
            self._render_step()
        else:
            self._saving = True
            self.error_label.setStringValue_('Сохраняем настройки…')
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
            self.error_label.setStringValue_(message)
            self.error_label.setTextColor_(A.NSColor.systemRedColor())
            self.next_button.setEnabled_(True)
            self.cancel_button.setEnabled_(True)
        else:
            self.show_message('TG WS Proxy Mac', message)

    @objc.python_method
    def show_first_run(self):
        host, port = get_link_host(self.config['host']), self.config['port']
        text = (f'Прокси работает в строке меню.\n\n'
                f'Как подключить Telegram Desktop:\n'
                f'Нажмите «Открыть в Telegram» в меню.\n\n'
                f'Вручную: Настройки → Продвинутые → Тип подключения → Прокси\n'
                f'MTProto → {host} : {port}\nSecret: dd{self.config["secret"]}\n\n'
                f'Открыть прокси в Telegram сейчас?')
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

    def quit_(self, sender):
        if self._quitting:
            return
        self._quitting = True
        self.update_state('stopping')
        self.callbacks['quit']()
