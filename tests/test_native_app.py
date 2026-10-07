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
    def test_native_settings_form_and_glass_fallback(self):
        import AppKit as A
        from native_ui import NativeUI
        import native_ui
        A.NSApplication.sharedApplication()
        callbacks = {key: (lambda *args: None) for key in ('started', 'telegram', 'copy', 'restart', 'logs', 'save', 'save_preferences', 'release', 'help', 'quit')}
        for glass in (False, native_ui.has_liquid_glass()):
            with self.subTest(glass=glass), patch.object(native_ui, 'has_liquid_glass', return_value=glass):
                ui = NativeUI.alloc().init()
                config = default_tray_config()
                ui.configure(callbacks, config)
                ui.dashboard_(None)
                ui.settings_(None)
                self.assertEqual(ui.fields['host'].stringValue(), config['host'])
                self.assertEqual(ui.fields['port'].stringValue(), str(config['port']))
                self.assertEqual(ui.fields['secret'].stringValue(), config['secret'])
                self.assertEqual(len(ui.pages), 3)
                self.assertEqual(ui.save_button.bezelStyle(), A.NSBezelStyleGlass if glass else A.NSBezelStyleRounded)
                ui.update_state('error', 'Порт занят')
                self.assertTrue(ui.save_button.isEnabled())
                ui.windows['dashboard'].close()
                ui.windows['settings'].close()
