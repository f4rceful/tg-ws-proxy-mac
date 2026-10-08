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


class FlippedView(A.NSView):
    def isFlipped(self):
        return True


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
        self.menu_items = {}
        self.localized_items = []
        self._saving = False
        self.update_busy = False
        self.update_info = {}
        self._quitting = False
        return self

    @objc.python_method
    def configure(self, callbacks, config, startup_available=False):
        self.callbacks = callbacks
        self.config = deepcopy(config)
        self.startup_available = startup_available
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
        appearance = {'light': A.NSAppearanceNameAqua, 'dark': A.NSAppearanceNameDarkAqua}.get(config.get('appearance'))
        A.NSApplication.sharedApplication().setAppearance_(A.NSAppearance.appearanceNamed_(appearance) if appearance else None)
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
        if 'settings' in self.windows:
            self.form_update_button.setHidden_(not available)
            self.form_update_button.setTitle_(t('Обновить до {version}', version=status.get('latest') or '?'))
            self.form_update_button.setEnabled_(available and not self.update_busy)
            self.form_update_label.setStringValue_(t('Доступно обновление') if available else t('Версия {version}', version=__version__))

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
        if 'settings' not in self.windows or self.form_language != self.config.get('language', 'auto'):
            if 'settings' in self.windows:
                self.windows['settings'].close()
            self._build_settings_form()
        if not self.windows['settings'].isVisible():
            self._populate_settings()
        self._show('settings')

    @objc.python_method
    def _build_settings_form(self):
        self.form_language = self.config.get('language', 'auto')
        window, content = glass_window('Настройки', 460, 560)
        self.windows['settings'] = window
        self.fields = {}
        self.settings_scroll = A.NSScrollView.alloc().initWithFrame_(rect(20, 104, 420, 412))
        self.settings_scroll.setHasVerticalScroller_(True)
        self.settings_scroll.setAutohidesScrollers_(True)
        self.settings_scroll.setDrawsBackground_(False)
        self.form = FlippedView.alloc().initWithFrame_(rect(0, 0, 400, 1100))
        self.settings_scroll.setDocumentView_(self.form)
        content.addSubview_(self.settings_scroll)
        y = 0

        def section(title):
            nonlocal y
            if y:
                y += 16
            label(self.form, title, 0, y, 400, 24, size=13, bold=True)
            y += 32

        section('Интерфейс')
        self._popup('language', 'Language', ('auto', 'ru', 'en'), ('Авто', 'Русский', 'English'), 0, y, 192)
        self._popup('appearance', 'Тема', ('auto', 'light', 'dark'), ('Авто', 'Светлая', 'Тёмная'), 208, y, 192)
        y += 68
        section('Подключение MTProto')
        self._form_field('host', 'IP-адрес', 0, y, 264)
        self._form_field('port', 'Порт', 280, y, 120)
        y += 64
        self._form_field('secret', 'Secret', 0, y, 400)
        y += 64
        section('Датацентры Telegram (DC → IP)')
        label(self.form, 'По одному правилу на строку, формат: номер:IP', 0, y, 400, 22, size=11, secondary=True)
        y += 26
        routes_scroll = A.NSScrollView.alloc().initWithFrame_(rect(0, y, 400, 72))
        routes_scroll.setHasVerticalScroller_(True)
        routes_scroll.setBorderType_(A.NSBezelBorder)
        routes = A.NSTextView.alloc().initWithFrame_(rect(0, 0, 380, 72))
        routes.setRichText_(False)
        routes.setFont_(A.NSFont.systemFontOfSize_(13))
        routes.setTextContainerInset_(A.NSMakeSize(6, 6))
        routes.setAutoresizingMask_(A.NSViewWidthSizable)
        routes.textContainer().setWidthTracksTextView_(True)
        routes.setAccessibilityLabel_(t('Датацентры Telegram (DC → IP)'))
        routes_scroll.setDocumentView_(routes)
        self.form.addSubview_(routes_scroll)
        self.fields['dc_ip'] = routes
        y += 80
        section('Cloudflare Proxy')
        self._form_check('cfproxy', 'Включить CF-прокси', y)
        y += 36
        self._form_field('cfproxy_user_domain', 'Свои домены (через запятую)', 0, y, 400)
        y += 60
        label(self.form, 'Пустое поле — автоматический выбор.', 0, y, 400, 20, size=11, secondary=True)
        y += 24
        section('Cloudflare Worker')
        self._form_field('cfproxy_worker_domain', 'Домены (через запятую)', 0, y, 400)
        y += 62
        button(self.form, 'Как настроить Worker', 0, y, 210, self, 'workerHelp:')
        y += 44
        section('Логи и производительность')
        self._form_check('verbose', 'Подробное логирование (verbose)', y)
        y += 36
        for key, title in (('buf_kb', 'Буфер, КБ'), ('pool_size', 'Пул WebSocket-сессий'), ('log_max_mb', 'Макс. размер лога, МБ')):
            label(self.form, title, 0, y + 4, 272, 26, size=12)
            self._form_field(key, '', 288, y, 112, inline=True)
            y += 38
        section('Обновления')
        self._form_check('check_updates', 'Проверять обновления при запуске', y)
        y += 34
        self.form_update_label = label(self.form, '', 0, y, 400, 24, size=12, secondary=True)
        y += 28
        self.form_update_button = button(self.form, '', 0, y, 400, self, 'installUpdate:')
        y += 44
        if self.startup_available:
            section('Вход в macOS')
            self._form_check('autostart', 'Запускать при входе в macOS', y)
            y += 34
            label(self.form, 'После перемещения приложения включите автозапуск заново.', 0, y, 400, 36, size=11, secondary=True)
            y += 40
        self.form.setFrameSize_(A.NSMakeSize(400, y + 12))
        self.error_label = label(content, '', 20, 62, 420, 36, size=11, secondary=True)
        self.cancel_button = button(content, 'Отмена', 20, 16, 128, self, 'closeSettings:')
        self.cancel_button.setKeyEquivalent_('\x1b')
        self.save_button = button(content, 'Сохранить', 288, 16, 152, self, 'saveSettings:', primary=True)
        self.save_button.setKeyEquivalent_('\r')
        window.setInitialFirstResponder_(self.fields['host'])
        self.update_status(self.update_info)

    @objc.python_method
    def _form_field(self, key, title, x, y, width, inline=False):
        if not inline:
            label(self.form, title, x, y, width, 22, size=12)
        field = A.NSTextField.alloc().initWithFrame_(rect(x, y if inline else y + 26, width, 30))
        field.setFont_(A.NSFont.systemFontOfSize_(13))
        field.setBezeled_(True)
        field.setBezelStyle_(A.NSTextFieldRoundedBezel)
        numeric_titles = {'buf_kb': 'Буфер, КБ', 'pool_size': 'Пул WebSocket-сессий', 'log_max_mb': 'Макс. размер лога, МБ'}
        field.setAccessibilityLabel_(t(title or numeric_titles.get(key, key)))
        self.form.addSubview_(field)
        self.fields[key] = field

    @objc.python_method
    def _popup(self, key, title, values, titles, x, y, width):
        label(self.form, title, x, y, width, 22, size=12)
        control = A.NSPopUpButton.alloc().initWithFrame_pullsDown_(rect(x, y + 26, width, 30), False)
        control.addItemsWithTitles_([t(text) for text in titles])
        control.setAccessibilityLabel_(t(title))
        self.form.addSubview_(control)
        self.fields[key] = control
        setattr(self, key + '_values', values)

    @objc.python_method
    def _form_check(self, key, title, y):
        control = A.NSButton.checkboxWithTitle_target_action_(t(title), None, None)
        control.setFrame_(rect(0, y, 400, 28))
        self.form.addSubview_(control)
        self.fields[key] = control

    @objc.python_method
    def _populate_settings(self):
        for key, field in self.fields.items():
            value = self.config.get(key)
            if key in ('language', 'appearance'):
                values = getattr(self, key + '_values')
                field.selectItemAtIndex_(values.index(value) if value in values else 0)
            elif key in ('cfproxy', 'check_updates', 'verbose', 'autostart'):
                field.setState_(A.NSControlStateValueOn if value else A.NSControlStateValueOff)
            elif key == 'dc_ip':
                field.setString_('\n'.join(value or []))
            else:
                field.setStringValue_(', '.join(value) if isinstance(value, list) else str(value))
        self.error_label.setStringValue_('')
        self.save_button.setEnabled_(True)
        self.cancel_button.setEnabled_(True)
        self._saving = False
        self.settings_scroll.contentView().scrollToPoint_(A.NSMakePoint(0, 0))
        self.settings_scroll.reflectScrolledClipView_(self.settings_scroll.contentView())

    def saveSettings_(self, sender):
        if self._saving:
            return
        values = {}
        for key, field in self.fields.items():
            if key in ('language', 'appearance'):
                values[key] = getattr(self, key + '_values')[field.indexOfSelectedItem()]
            elif key in ('cfproxy', 'check_updates', 'verbose', 'autostart'):
                values[key] = field.state() == A.NSControlStateValueOn
            elif key == 'dc_ip':
                values[key] = field.string()
            else:
                values[key] = field.stringValue()
        try:
            candidate = validate_settings(values, self.config)
        except ValueError as exc:
            self.error_label.setStringValue_(t(str(exc)))
            self.error_label.setTextColor_(A.NSColor.systemRedColor())
            return
        for key in ('language', 'appearance', 'autostart'):
            if key in values:
                candidate[key] = values[key]
        self._saving = True
        self.error_label.setStringValue_(t('Сохраняем настройки…'))
        self.error_label.setTextColor_(A.NSColor.secondaryLabelColor())
        self.save_button.setEnabled_(False)
        self.cancel_button.setEnabled_(False)
        self.form_update_button.setEnabled_(False)
        self.callbacks['save'](candidate)

    def closeSettings_(self, sender):
        if not self._saving:
            self.windows['settings'].orderOut_(None)

    @objc.python_method
    def settings_saved(self):
        self.windows['settings'].orderOut_(None)
        self._saving = False
        self.show_message('TG WS Proxy Mac', 'Настройки сохранены.\n\nПерезапустить прокси сейчас?', choices=(('Закрыть', None), ('Нет', None), ('Да', self.callbacks['restart'])))

    @objc.python_method
    def save_failed(self, message):
        self._saving = False
        if 'settings' in self.windows and self.windows['settings'].isVisible():
            self.error_label.setStringValue_(t(message))
            self.error_label.setTextColor_(A.NSColor.systemRedColor())
            self.save_button.setEnabled_(True)
            self.cancel_button.setEnabled_(True)
            self.update_status(self.update_info)
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
