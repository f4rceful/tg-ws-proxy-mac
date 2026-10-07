from copy import deepcopy
from threading import Event
import time
import unittest
from unittest.mock import patch

from utils.default_config import default_tray_config
from utils.proxy_service import ProxyService
from utils.settings import validate_settings


def form(config):
    return {key: ', '.join(value) if isinstance(value, list) else value for key, value in config.items()}


class SettingsTests(unittest.TestCase):
    def test_invalid_form_does_not_modify_current_settings(self):
        config = default_tray_config()
        original = deepcopy(config)
        for field, invalid in [('port', '70000'), ('host', 'not-an-ip'), ('secret', 'abc'), ('pool_size', '-1'), ('log_max_mb', 'nan'), ('dc_ip', 'bad-address')]:
            with self.subTest(field=field):
                values = form(config)
                values[field] = invalid
                with self.assertRaises(ValueError):
                    validate_settings(values, config)
                self.assertEqual(config, original)

    def test_valid_form_keeps_unknown_preferences_and_normalizes_routes(self):
        config = default_tray_config()
        config['future_preference'] = 'keep'
        values = form(config)
        values.update(port='2443', cfproxy_worker_domain='a.workers.dev, a.workers.dev, b.workers.dev', log_max_mb='2,5')
        result = validate_settings(values, config)
        self.assertEqual(result['port'], 2443)
        self.assertEqual(result['cfproxy_worker_domain'], ['a.workers.dev', 'b.workers.dev'])
        self.assertEqual(result['log_max_mb'], 2.5)
        self.assertEqual(result['future_preference'], 'keep')


class ProxyServiceTests(unittest.TestCase):
    def test_restart_returns_while_old_proxy_is_still_stopping(self):
        entered, release = Event(), Event()
        service = ProxyService(lambda state, detail: None)
        def delayed_stop():
            entered.set()
            release.wait(timeout=2)
        try:
            with patch.object(service, '_stop_current', side_effect=delayed_stop), patch.object(service, '_serve'):
                start = time.monotonic()
                future = service.restart(default_tray_config())
                elapsed = time.monotonic() - start
                self.assertTrue(entered.wait(timeout=1))
                self.assertLess(elapsed, 0.1)
                self.assertFalse(future.done())
                release.set()
                future.result(timeout=2)
        finally:
            release.set()
            service.close().result(timeout=2)

    def test_service_can_start_restart_and_close_a_local_proxy(self):
        from proxy import proxy_config
        saved = deepcopy(vars(proxy_config))
        running = Event()
        errors = []
        def notify(state, detail):
            if state == 'running':
                running.set()
            if state == 'error':
                errors.append(detail)
        service = ProxyService(notify)
        config = default_tray_config()
        config.update(port=0, cfproxy=False, pool_size=0)
        try:
            service.restart(config).result(timeout=2)
            self.assertTrue(running.wait(timeout=3))
            running.clear()
            service.restart(config).result(timeout=3)
            self.assertTrue(running.wait(timeout=3))
            self.assertFalse(errors)
        finally:
            service.close().result(timeout=5)
            vars(proxy_config).update(saved)
        self.assertIsNone(service.restart(config))

class NativeWindowTests(unittest.TestCase):
    def test_original_menu_and_stepwise_settings_with_glass_fallback(self):
        import AppKit as A
        from native_ui import NativeUI
        import native_ui
        A.NSApplication.sharedApplication()
        for glass in (False, native_ui.has_liquid_glass()):
            saved, restarted = [], []
            callbacks = {key: (lambda *args: None) for key in ('started', 'telegram', 'copy', 'restart', 'logs', 'save', 'save_preferences', 'release', 'help', 'quit')}
            callbacks['save'] = saved.append
            callbacks['restart'] = lambda: restarted.append(True)
            with self.subTest(glass=glass), patch.object(native_ui, 'has_liquid_glass', return_value=glass):
                ui = NativeUI.alloc().init()
                config = default_tray_config()
                config['language'] = 'ru'
                ui.configure(callbacks, config)
                ui._build_menu()
                self.assertEqual(list(ui.menu_items), ['telegram', 'copy', 'restart', 'settings', 'logs', 'release', 'update', 'check', 'updates', 'version', 'quit'])
                self.assertEqual(ui.menu_items['telegram'].title(), 'Открыть в Telegram (127.0.0.1:1443)')
                ui.settings_(None)
                self.assertEqual(ui.step_field.stringValue(), config['host'])
                self.assertEqual(ui.next_button.bezelStyle(), A.NSBezelStyleGlass if glass else A.NSBezelStyleRounded)
                ui.nextStep_(None)
                ui.step_field.setStringValue_('70000')
                ui.nextStep_(None)
                self.assertEqual(ui.step_index, 1)
                self.assertIn('65535', ui.error_label.stringValue())
                self.assertFalse(saved)
                ui.step_field.setStringValue_('2443')
                ui.nextStep_(None)
                # Cancelling after editing must leave the live config untouched.
                ui.closeSettings_(None)
                self.assertEqual(ui.config, config)
                self.assertFalse(saved)
                ui.settings_(None)
                for key, _ in ui.STEPS:
                    if key in ('verbose', 'cfproxy'):
                        ui._advance(config[key])
                    else:
                        if key == 'port':
                            ui.step_field.setStringValue_('2443')
                        ui.nextStep_(None)
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]['port'], 2443)
                self.assertEqual(ui.config, config)
                self.assertFalse(restarted)
                ui.update_config(saved[0])
                ui.settings_saved()
                # Saving only offers a restart; it never restarts automatically.
                self.assertFalse(restarted)
                no = A.NSButton.alloc().init()
                no.setTag_(1)
                ui.messageChoice_(no)
                self.assertFalse(restarted)
                ui.settings_saved()
                yes = A.NSButton.alloc().init()
                yes.setTag_(2)
                ui.messageChoice_(yes)
                self.assertEqual(restarted, [True])
                for window in ui.windows.values():
                    window.close()
                A.NSStatusBar.systemStatusBar().removeStatusItem_(ui.status_item)

    def test_coordinator_waits_for_restart_choice_after_save(self):
        from macos import MacApp
        application = MacApp(preview=True, settings_preview=True)
        try:
            application.ui.settings_(None)
            config = deepcopy(application.config)
            config['port'] = 2443
            with patch.object(application, 'restart') as restart:
                application.save(config)
                restart.assert_not_called()
            self.assertEqual(application.config['port'], 2443)
            self.assertTrue(application.ui.windows['message'].isVisible())
        finally:
            for window in application.ui.windows.values():
                window.close()
            application.disk.shutdown(wait=False)
            application.background.shutdown(wait=False)

    def test_desktop_actions_keep_drafts_and_do_not_write_startup_before_save(self):
        import AppKit as A
        from native_ui import NativeUI
        from utils.i18n import set_language
        A.NSApplication.sharedApplication()
        saved, quit_calls = [], []
        callbacks = {key: (lambda *args: None) for key in ('started', 'telegram', 'copy', 'restart', 'logs', 'save', 'save_preferences', 'release', 'help', 'update', 'check_updates', 'quit')}
        callbacks['save'] = saved.append
        callbacks['quit'] = lambda: quit_calls.append(True)
        ui = NativeUI.alloc().init()
        config = default_tray_config()
        config['language'] = 'ru'
        ui.configure(callbacks, config, startup_available=True)
        try:
            ui._build_menu()
            ui.update_state('running')
            self.assertTrue(ui.menu_items['update'].isHidden())
            self.assertTrue(ui.status_item.button().image().isTemplate())
            ui.settings_(None)
            ui.step_field.setStringValue_('127.0.0.2')
            ui.update_status({'has_update': True, 'latest': '0.4.0'})
            self.assertFalse(ui.menu_items['update'].isHidden())
            self.assertEqual(ui.step_field.stringValue(), '127.0.0.2')
            surface = ui.windows['settings'].contentView()
            content = surface.contentView() if hasattr(surface, 'contentView') else surface
            buttons = [view.title() for view in content.subviews() if isinstance(view, A.NSButton)]
            self.assertIn('Обновить до 0.4.0', buttons)
            ui.step_index = len(ui.steps) - 1
            ui._render_step()
            self.assertEqual(ui.steps[ui.step_index][0], 'autostart')
            self.assertFalse(saved)
            ui.answerYes_(None)
            self.assertEqual(len(saved), 1)
            self.assertTrue(saved[0]['autostart'])
            self.assertFalse(config['autostart'])
            ui.show_update_progress()
            self.assertFalse(ui.menu_items['restart'].isEnabled())
            self.assertFalse(ui.windowShouldClose_(ui.windows['progress']))
            ui.quit_(None)
            self.assertFalse(quit_calls)
            self.assertFalse(ui._quitting)
            ui.update_progress('update.mac_preparing')
            self.assertIn('подготовка', ui.progress_label.stringValue())
            ui.finish_update_progress()
            self.assertTrue(ui.menu_items['restart'].isEnabled())
            config['language'] = 'en'
            ui.update_config(config)
            self.assertEqual(ui.menu_items['settings'].title(), 'Settings...')
            self.assertEqual(ui.menu_items['telegram'].title(), 'Open in Telegram (127.0.0.1:1443)')
        finally:
            set_language('ru')
            for window in ui.windows.values():
                window.close()
            A.NSStatusBar.systemStatusBar().removeStatusItem_(ui.status_item)
