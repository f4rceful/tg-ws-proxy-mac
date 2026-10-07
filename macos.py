"""Native menu bar app: AppKit on the main thread, proxy work in the background."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sys
import logging
import logging.handlers

import AppKit as A
import Foundation as F
from PyObjCTools import AppHelper

from native_ui import NativeUI
from proxy import __version__
from utils.macos_common import (
    DEFAULT_CONFIG, FIRST_RUN_MARKER, LOG_FILE, acquire_lock, ensure_dirs,
    load_config, log, release_lock, save_config, setup_logging, tg_proxy_url,
)
from utils.proxy_service import ProxyService
from utils.update_check import RELEASES_PAGE_URL, get_status, run_check
from utils import macos_integration as mac_integration
from utils.i18n import t
from proxy.utils import build_github_opener


class MacApp:
    def __init__(self, preview=False, settings_preview=False):
        self.preview = preview
        self.settings_preview = settings_preview
        self.first_run_pending = False
        self.bundle = None if preview else mac_integration.app_bundle()
        self.update_status = {}
        self.check_pending = False
        self.config = deepcopy(DEFAULT_CONFIG)
        if preview:
            self.config['secret'] = '0' * 32
            self.config['language'] = F.NSBundle.mainBundle().objectForInfoDictionaryKey_('TGWSPreviewLanguage') or 'auto'
        self.ui = NativeUI.alloc().init()
        self.disk = ThreadPoolExecutor(max_workers=1, thread_name_prefix='settings')
        self.background = ThreadPoolExecutor(max_workers=1, thread_name_prefix='updates')
        self.service = None if preview else ProxyService(self._state_changed)
        self.ui.configure({
            'started': self.boot, 'telegram': self.open_telegram, 'copy': self.copy_link,
            'restart': self.restart, 'logs': self.open_logs, 'save': self.save,
            'save_preferences': self.save_preferences,
            'release': lambda: self.open_url(RELEASES_PAGE_URL),
            'help': lambda: self.open_url('https://github.com/f4rceful/tg-ws-proxy-mac/blob/main/docs/CfWorker.md'),
            'update': self.request_update,
            'check_updates': lambda: self.schedule_check(True),
            'quit': self.quit,
        }, self.config, startup_available=preview or self.bundle is not None)

    def boot(self):
        if self.preview:
            self.ui.update_state('running')
            if F.NSBundle.mainBundle().objectForInfoDictionaryKey_('TGWSPreviewUpdate'):
                self._checked({'has_update': True, 'latest': '0.4.0'}, False)
            if self.settings_preview:
                self.ui.settings_(None)
            else:
                self.ui.show_first_run()
            return
        def load():
            ensure_dirs()
            config = load_config()
            if self.bundle:
                config['autostart'] = mac_integration.startup_enabled(self.bundle)
                try:
                    mac_integration.cleanup_old_updates(self.bundle)
                except OSError:
                    log.exception('Could not clean old update backups')
            save_config(config)
            setup_logging(config.get('verbose', False), config.get('log_max_mb', 5))
            first_run = not FIRST_RUN_MARKER.exists()
            if first_run:
                FIRST_RUN_MARKER.touch()
            return config, first_run
        self.disk.submit(load).add_done_callback(self._loaded)

    def _loaded(self, future):
        try:
            config, first_run = future.result()
        except Exception as exc:
            AppHelper.callAfter(self.ui.show_message, t('Не удалось открыть настройки'), str(exc))
            return
        AppHelper.callAfter(self._finish_load, config, first_run)

    def _finish_load(self, config, first_run):
        self.config = config
        self.ui.update_config(config)
        self.first_run_pending = first_run
        self.restart()
        if config.get('check_updates', True):
            self.schedule_check()

    def _state_changed(self, state, detail):
        AppHelper.callAfter(self._show_state, state, detail)

    def _show_state(self, state, detail):
        self.ui.update_state(state, detail)
        if state == 'running' and self.first_run_pending:
            self.first_run_pending = False
            self.ui.show_first_run()

    def restart(self):
        self.ui.update_state('starting')
        if self.preview:
            AppHelper.callLater(0.25, self.ui.update_state, 'running')
        else:
            self.service.restart(self.config)

    def open_url(self, url):
        return A.NSWorkspace.sharedWorkspace().openURL_(F.NSURL.URLWithString_(url))

    def open_telegram(self):
        if self.preview:
            return
        if not self.open_url(tg_proxy_url(self.config)):
            self.copy_link()
            self.ui.show_message(t('Ссылка скопирована'), 'Откройте Telegram Desktop, вставьте ссылку в «Избранное» и нажмите на неё.')

    def copy_link(self):
        pasteboard = A.NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(tg_proxy_url(self.config), A.NSPasteboardTypeString)

    def open_logs(self):
        if LOG_FILE.exists():
            A.NSWorkspace.sharedWorkspace().openURL_(F.NSURL.fileURLWithPath_(str(LOG_FILE)))
        else:
            self.ui.show_message(t('Журнал пока пуст'), 'Записи появятся после запуска прокси.')

    def save(self, config):
        if self.preview:
            self.config = config
            self.ui.update_config(config)
            self.ui.settings_saved()
            return
        self.disk.submit(self._persist_settings, config).add_done_callback(lambda future: self._saved(future, config, True))

    def _persist_settings(self, config):
        previous = mac_integration.startup_enabled(self.bundle) if self.bundle else False
        if self.bundle:
            try:
                mac_integration.set_startup(self.bundle, bool(config.get('autostart')))
            except (ValueError, OSError) as exc:
                raise ValueError(t('Не удалось изменить автозапуск: {error}', error=t(str(exc)))) from exc
        try:
            save_config(config)
        except Exception:
            if self.bundle:
                mac_integration.set_startup(self.bundle, previous)
            raise

    def save_preferences(self, config):
        if self.preview:
            self.config = config
            self.ui.update_config(config)
            return
        self.disk.submit(save_config, config).add_done_callback(lambda future: self._saved(future, config, False))

    def _saved(self, future, config, settings_done):
        try:
            future.result()
        except Exception as exc:
            AppHelper.callAfter(self.ui.save_failed, t('Не удалось сохранить: {error}', error=t(str(exc))))
            return
        if settings_done:
            log.info('Settings saved')
        AppHelper.callAfter(self._apply_saved, config, settings_done)

    def _apply_saved(self, config, settings_done):
        self.config = config
        self.ui.update_config(config)
        if settings_done:
            root = logging.getLogger()
            root.setLevel(logging.DEBUG if config.get('verbose') else logging.INFO)
            for handler in root.handlers:
                if isinstance(handler, logging.handlers.RotatingFileHandler):
                    handler.maxBytes = max(32768, int(config.get('log_max_mb', 5) * 1024 * 1024))
            self.ui.settings_saved()

    def schedule_check(self, manual=False):
        if self.check_pending or self.ui.update_busy or self.ui._quitting:
            return
        self.check_pending = True
        self.ui.menu_items['check'].setEnabled_(False)
        self.background.submit(self.check_updates, manual)

    def check_updates(self, manual=False):
        try:
            run_check(__version__, force=manual)
            status = get_status()
            AppHelper.callAfter(self._checked, status, manual)
        except Exception as exc:
            log.exception('Update check failed')
            AppHelper.callAfter(self._checked, {'error': t('Не удалось проверить обновления: {error}', error=str(exc))}, manual)

    def _checked(self, status, manual):
        if self.ui._quitting:
            return
        self.check_pending = False
        self.ui.menu_items['check'].setEnabled_(not self.ui.update_busy)
        self.update_status = status
        self.ui.update_status(status)
        if status.get('has_update'):
            self.request_update()
        elif manual:
            message = status.get('error') or 'Обновлений пока нет.'
            self.ui.show_message(t('Обновление'), t(message))

    def request_update(self):
        if self.ui.update_busy or self.ui._saving or self.ui._quitting or not self.update_status.get('has_update'):
            return
        if self.bundle is None and not self.preview:
            self.open_url(self.update_status.get('html_url') or RELEASES_PAGE_URL)
            return
        self.ui.show_message(t('Доступно обновление'), t('Установить версию {version}? Прокси будет перезапущен. Предыдущая версия приложения будет сохранена для восстановления.', version=self.update_status['latest']), 'Установить', self._start_update)

    def _start_update(self):
        self.ui.show_update_progress()
        if self.preview:
            AppHelper.callLater(2.0, self.ui.update_progress, 'update.mac_preparing')
            AppHelper.callLater(6.0, self.ui.finish_update_progress)
            return
        status = deepcopy(self.update_status)
        def prepare():
            return mac_integration.prepare_update(self.bundle, status, build_github_opener(), progress=lambda key: AppHelper.callAfter(self.ui.update_progress, key))
        self.background.submit(prepare).add_done_callback(self._update_prepared)

    def _update_prepared(self, future):
        try:
            work = future.result()
        except Exception as exc:
            log.exception('macOS update preparation failed')
            AppHelper.callAfter(self._finish_update, None, str(exc))
        else:
            AppHelper.callAfter(self._finish_update, work, None)

    def _finish_update(self, work, error):
        self.ui.finish_update_progress()
        if not error:
            try:
                mac_integration.launch_installer(self.bundle, work)
            except OSError as exc:
                error = str(exc)
            else:
                self.ui.quit_(None)
                return
        self.ui.show_message(t('Обновление'), t('Не удалось установить обновление: {error}', error=t(error)))

    def quit(self):
        if self.preview:
            self._finish_quit()
            return
        future = self.service.close()
        future.add_done_callback(lambda result: AppHelper.callAfter(self._finish_quit))

    def _finish_quit(self):
        self.disk.shutdown(wait=False)
        self.background.shutdown(wait=False)
        release_lock()
        A.NSApplication.sharedApplication().terminate_(None)

    def run(self):
        app = A.NSApplication.sharedApplication()
        app.setActivationPolicy_(A.NSApplicationActivationPolicyAccessory)
        app.setDelegate_(self.ui)
        AppHelper.runEventLoop()


def main():
    if '--version' in sys.argv:
        print(__version__)
        return
    bundle_preview = bool(F.NSBundle.mainBundle().objectForInfoDictionaryKey_('TGWSPreview'))
    preview = bundle_preview or '--preview' in sys.argv or '--preview-settings' in sys.argv
    if not preview and not acquire_lock():
        # Notify the running app through the OS instead of blocking on an alert.
        for app in A.NSRunningApplication.runningApplicationsWithBundleIdentifier_('com.github.f4rceful.tgwsproxymac'):
            app.activateWithOptions_(A.NSApplicationActivateIgnoringOtherApps)
        return
    application = MacApp(preview=preview, settings_preview=bundle_preview or '--preview-settings' in sys.argv)
    try:
        application.run()
    finally:
        release_lock()


if __name__ == '__main__':
    main()
