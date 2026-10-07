"""Native, nonmodal AppKit windows with Liquid Glass on macOS 26+."""
from copy import deepcopy
import os

import AppKit as A
import Foundation as F
import objc

from proxy import __version__
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
    window.setTitleVisibility_(A.NSWindowTitleHidden)
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
    def init(self):
        self = objc.super(NativeUI, self).init()
        if self is None:
            return None
        self.callbacks = {}
        self.config = {}
        self.state = 'starting'
        self.detail = ''
        self.windows = {}
        self.fields = {}
        self.menu_items = {}
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
        image = A.NSImage.imageWithSystemSymbolName_accessibilityDescription_('paperplane.fill', 'TG WS Proxy Mac')
        if image is not None:
            image.setSize_(A.NSMakeSize(18, 18))
            image.setTemplate_(True)
            self.status_item.button().setImage_(image)
        else:
            self.status_item.button().setTitle_('TG')
        menu = A.NSMenu.alloc().initWithTitle_('TG WS Proxy Mac')
        menu.setAutoenablesItems_(False)
        entries = [
            ('status', 'Запуск прокси…', None),
            ('address', '', None),
            None,
            ('dashboard', 'Открыть окно', 'dashboard:'),
            ('telegram', 'Подключить Telegram', 'openTelegram:'),
            ('copy', 'Скопировать ссылку', 'copyLink:'),
            None,
            ('settings', 'Настройки…', 'settings:'),
            ('restart', 'Перезапустить прокси', 'restart:'),
            ('logs', 'Открыть логи', 'logs:'),
            None,
            ('updates', 'Проверять обновления при запуске', 'toggleUpdates:'),
            ('release', 'Страница релизов', 'release:'),
            ('version', f'Версия {__version__}', None),
            None,
            ('quit', 'Выход', 'quit:'),
        ]
        for entry in entries:
            if entry is None:
                menu.addItem_(A.NSMenuItem.separatorItem())
                continue
            key, text, action = entry
            item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(text, action, '')
            item.setTarget_(self)
            item.setEnabled_(action is not None)
            menu.addItem_(item)
            self.menu_items[key] = item
        self.menu_items['settings'].setKeyEquivalent_(',')
        self.menu_items['quit'].setKeyEquivalent_('q')
        self.status_item.setMenu_(menu)
        # Standard responder-chain commands keep keyboard editing native.
        main_menu = A.NSMenu.alloc().initWithTitle_('')
        for title, commands in (
            ('TG WS Proxy Mac', [('Настройки…', 'settings:', ',', self), ('Выход', 'quit:', 'q', self)]),
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
            self.menu_items['address'].setTitle_(f"{config['host']}:{config['port']}")
            self.menu_items['updates'].setState_(A.NSControlStateValueOn if config.get('check_updates', True) else A.NSControlStateValueOff)
        if 'dashboard' in self.windows:
            self.host_value.setStringValue_(str(config['host']))
            self.port_value.setStringValue_(str(config['port']))

    @objc.python_method
    def update_state(self, state, detail=''):
        self.state, self.detail = state, detail
        texts = {'starting': 'Запуск прокси…', 'running': 'Прокси готов', 'error': 'Требуется внимание', 'stopping': 'Завершение…'}
        text = texts.get(state, state)
        if self.menu_items:
            self.menu_items['status'].setTitle_(text)
            self.menu_items['restart'].setEnabled_(state in ('running', 'error'))
            self.menu_items['telegram'].setEnabled_(state == 'running')
        if 'dashboard' in self.windows:
            self.status_label.setStringValue_(text)
            self.status_label.setTextColor_(A.NSColor.systemGreenColor() if state == 'running' else A.NSColor.secondaryLabelColor())
            self.dashboard_detail.setStringValue_(detail or 'Выберите «Подключить Telegram», чтобы включить прокси.')
            self.restart_button.setEnabled_(state in ('running', 'error'))
            self.connect_button.setEnabled_(state == 'running')
        if 'settings' in self.windows and state in ('running', 'error'):
            self.saving_label.setStringValue_('Настройки применены' if state == 'running' else detail)
            self.saving_label.setTextColor_(A.NSColor.secondaryLabelColor() if state == 'running' else A.NSColor.systemRedColor())
            self.save_button.setEnabled_(True)

    @objc.python_method
    def _show(self, key):
        self.windows[key].makeKeyAndOrderFront_(None)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def dashboard_(self, sender):
        if 'dashboard' not in self.windows:
            window, content = glass_window('TG WS Proxy Mac', 540, 440)
            self.windows['dashboard'] = window
            icon = A.NSImageView.alloc().initWithFrame_(rect(30, 336, 48, 48))
            icon.setImage_(A.NSImage.imageWithSystemSymbolName_accessibilityDescription_('paperplane.circle.fill', 'Telegram proxy'))
            icon.setContentTintColor_(A.NSColor.controlAccentColor())
            icon.setImageScaling_(A.NSImageScaleProportionallyUpOrDown)
            content.addSubview_(icon)
            label(content, 'TG WS Proxy Mac', 94, 358, 270, size=18, bold=True)
            label(content, 'Локальный прокси для Telegram', 94, 334, 350, size=12, secondary=True)
            label(content, f'{__version__}', 450, 357, 65, size=12, secondary=True)
            label(content, 'Telegram, без ожидания.', 30, 272, 480, 44, size=28, bold=True)
            self.status_label = label(content, '', 30, 235, 470, 26, size=15, bold=True)
            self.dashboard_detail = label(content, '', 30, 188, 480, 42, size=13, secondary=True)
            label(content, 'СЕРВЕР', 30, 155, 240, size=10, bold=True, secondary=True)
            label(content, 'ПОРТ', 334, 155, 170, size=10, bold=True, secondary=True)
            self.host_value = label(content, '', 30, 123, 280, 30, size=21, bold=True)
            self.port_value = label(content, '', 334, 123, 170, 30, size=21, bold=True)
            self.restart_button = button(content, 'Перезапустить', 30, 68, 154, self, 'restart:')
            button(content, 'Настройки', 196, 68, 132, self, 'settings:')
            self.connect_button = button(content, 'Подключить Telegram', 338, 68, 180, self, 'openTelegram:', primary=True)
            button(content, 'Скопировать ссылку', 30, 18, 200, self, 'copyLink:')
            self.copy_note = label(content, '', 246, 27, 260, size=12, secondary=True)
        self.update_config(self.config)
        self.update_state(self.state, self.detail)
        self._show('dashboard')

    @objc.python_method
    def _field(self, page, key, title, x, y, width, hint=None, secure=False):
        label(page, title, x, y + 42, width, size=12, bold=True)
        cls = A.NSSecureTextField if secure else A.NSTextField
        field = cls.alloc().initWithFrame_(rect(x, y, width, 32))
        field.setFont_(A.NSFont.systemFontOfSize_(14))
        field.setAccessibilityLabel_(title)
        field.setBezeled_(True)
        field.setBezelStyle_(A.NSTextFieldRoundedBezel)
        page.addSubview_(field)
        self.fields[key] = field
        if hint:
            label(page, hint, x, y - 38, width, 32, size=11, secondary=True)
        return field

    @objc.python_method
    def _check(self, page, key, text, x, y):
        control = A.NSButton.checkboxWithTitle_target_action_(text, None, None)
        control.setFrame_(rect(x, y, 610, 30))
        page.addSubview_(control)
        self.fields[key] = control
        return control

    def settings_(self, sender):
        if 'settings' not in self.windows:
            window, content = glass_window('Настройки', 700, 650)
            self.windows['settings'] = window
            label(content, 'Настройки', 28, 565, 500, 36, size=26, bold=True)
            label(content, 'Все параметры прокси в одном окне.', 28, 535, 620, size=13, secondary=True)
            self.tab_buttons = []
            for i, title in enumerate(('Подключение', 'Сеть', 'Дополнительно')):
                tab = button(content, title, 28 + 215 * i, 474, 205, self, 'selectTab:')
                tab.setTag_(i)
                self.tab_buttons.append(tab)
            self.pages = []
            for _ in range(3):
                page = A.NSView.alloc().initWithFrame_(rect(28, 120, 644, 340))
                content.addSubview_(page)
                self.pages.append(page)
            connection, network, advanced = self.pages
            self._field(connection, 'host', 'Адрес сервера', 0, 238, 414, 'Обычно 127.0.0.1 — только на этом Mac.')
            self._field(connection, 'port', 'Порт', 450, 238, 194, 'От 1 до 65535.')
            self._field(connection, 'secret', 'Ключ подключения · Secret', 0, 114, 644, '32 символа. Ссылку с ключом можно скопировать в главном окне.', secure=True)
            button(connection, 'Создать новый ключ', 0, 34, 208, self, 'newSecret:')
            label(connection, 'Новый ключ потребует повторного подключения Telegram.', 224, 38, 420, 38, size=11, secondary=True)
            self._check(network, 'cfproxy', 'Использовать Cloudflare Proxy как резервный маршрут', 0, 292)
            self._field(network, 'dc_ip', 'Маршруты дата-центров', 0, 214, 644, 'Например: 2:149.154.167.220, 4:149.154.167.220. Можно оставить пустым.')
            self._field(network, 'cfproxy_user_domain', 'Свои Cloudflare-домены', 0, 116, 644, 'Через запятую. Пустое поле — автоматический выбор.')
            self._field(network, 'cfproxy_worker_domain', 'Cloudflare Worker', 0, 18, 644)
            button(network, 'Как настроить Worker', 422, 54, 222, self, 'workerHelp:')
            self._field(advanced, 'buf_kb', 'Буфер · КБ', 0, 236, 190, 'От 4 до 65536.')
            self._field(advanced, 'pool_size', 'Пул соединений', 222, 236, 190, 'От 0 до 32.')
            self._field(advanced, 'log_max_mb', 'Журнал · МБ', 444, 236, 200, 'От 0,1 до 1024.')
            self._check(advanced, 'check_updates', 'Проверять обновления при запуске', 0, 134)
            self._check(advanced, 'verbose', 'Подробный журнал работы', 0, 90)
            label(advanced, 'Изменения применяются без выхода из приложения.', 0, 30, 620, 38, size=12, secondary=True)
            self.saving_label = label(content, '', 28, 77, 644, 32, size=12, secondary=True)
            button(content, 'Закрыть', 28, 22, 120, self, 'closeSettings:')
            self.save_button = button(content, 'Сохранить и применить', 430, 22, 244, self, 'saveSettings:', primary=True)
            self.save_button.setKeyEquivalent_('\r')
            self._select_page(0)
        if not self.windows['settings'].isVisible():
            self._populate_settings()
        self._show('settings')

    @objc.python_method
    def _populate_settings(self):
        for key, field in self.fields.items():
            value = self.config.get(key)
            if key in ('cfproxy', 'check_updates', 'verbose'):
                field.setState_(A.NSControlStateValueOn if value else A.NSControlStateValueOff)
            else:
                field.setStringValue_(', '.join(value) if isinstance(value, list) else str(value))
        self.saving_label.setStringValue_('')
        self.save_button.setEnabled_(True)

    @objc.python_method
    def _select_page(self, index):
        for i, page in enumerate(self.pages):
            page.setHidden_(i != index)
            tab = self.tab_buttons[i]
            if has_liquid_glass():
                tab.setTintProminence_(A.NSTintProminenceSecondary if i == index else A.NSTintProminenceNone)
            else:
                tab.setBezelColor_(A.NSColor.controlAccentColor() if i == index else None)

    def selectTab_(self, sender):
        self._select_page(sender.tag())

    def newSecret_(self, sender):
        self.fields['secret'].setStringValue_(os.urandom(16).hex())
        self.saving_label.setStringValue_('Новый ключ будет применён после сохранения.')

    def saveSettings_(self, sender):
        values = {key: field.state() == A.NSControlStateValueOn if key in ('cfproxy', 'check_updates', 'verbose') else field.stringValue() for key, field in self.fields.items()}
        try:
            config = validate_settings(values, self.config)
        except ValueError as exc:
            self.saving_label.setTextColor_(A.NSColor.systemRedColor())
            self.saving_label.setStringValue_(str(exc))
            return
        self.saving_label.setTextColor_(A.NSColor.secondaryLabelColor())
        self.saving_label.setStringValue_('Сохраняем и применяем…')
        self.save_button.setEnabled_(False)
        self.callbacks['save'](config)

    @objc.python_method
    def save_failed(self, message):
        if 'settings' in self.windows:
            self.saving_label.setStringValue_(message)
            self.saving_label.setTextColor_(A.NSColor.systemRedColor())
            self.save_button.setEnabled_(True)

    def closeSettings_(self, sender):
        self.windows['settings'].orderOut_(None)

    @objc.python_method
    def show_message(self, title, text, action_title=None, action=None):
        window, content = glass_window(title, 520, 290)
        self.windows['message'] = window
        self.message_action = action
        label(content, title, 28, 197, 464, 44, size=22, bold=True)
        label(content, text, 28, 92, 464, 100, size=13, secondary=True)
        button(content, 'Закрыть', 28, 24, 120, self, 'closeMessage:')
        if action_title and action:
            button(content, action_title, 276, 24, 216, self, 'messageAction:', primary=True)
        self._show('message')

    def closeMessage_(self, sender):
        self.windows['message'].orderOut_(None)

    def messageAction_(self, sender):
        if self.message_action:
            self.message_action()
        self.closeMessage_(None)

    def openTelegram_(self, sender):
        self.callbacks['telegram']()

    def copyLink_(self, sender):
        self.callbacks['copy']()
        if 'dashboard' in self.windows:
            self.copy_note.setStringValue_('Ссылка скопирована')

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
