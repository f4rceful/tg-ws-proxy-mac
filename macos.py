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


class MacApp:
    def __init__(self, preview=False, settings_preview=False):
        self.preview = preview
        self.settings_preview = settings_preview
        self.first_run_pending = False
        self.config = deepcopy(DEFAULT_CONFIG)
        if preview:
            self.config['secret'] = '0' * 32
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
            'quit': self.quit,
        }, self.config)

    def boot(self):
        if self.preview:
            self.ui.update_state('running')
            if self.settings_preview:
                self.ui.settings_(None)
            else:
                self.ui.show_first_run()
            return
        def load():
            ensure_dirs()
            config = load_config()
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
            AppHelper.callAfter(self.ui.show_message, 'Не удалось открыть настройки', str(exc))
            return
        AppHelper.callAfter(self._finish_load, config, first_run)

    def _finish_load(self, config, first_run):
        self.config = config
        self.ui.update_config(config)
        self.first_run_pending = first_run
        self.restart()
        if config.get('check_updates', True):
            self.background.submit(self.check_updates)

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
            self.ui.show_message('Ссылка скопирована', 'Откройте Telegram Desktop, вставьте ссылку в «Избранное» и нажмите на неё.')

    def copy_link(self):
        pasteboard = A.NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(tg_proxy_url(self.config), A.NSPasteboardTypeString)

    def open_logs(self):
        if LOG_FILE.exists():
            A.NSWorkspace.sharedWorkspace().openURL_(F.NSURL.fileURLWithPath_(str(LOG_FILE)))
        else:
            self.ui.show_message('Журнал пока пуст', 'Записи появятся после запуска прокси.')

    def save(self, config):
        if self.preview:
            self.config = config
            self.ui.update_config(config)
            self.ui.settings_saved()
            return
        self.disk.submit(save_config, config).add_done_callback(lambda future: self._saved(future, config, True))

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
            AppHelper.callAfter(self.ui.save_failed, f'Не удалось сохранить: {exc}')
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

    def check_updates(self):
        try:
            run_check(__version__)
            status = get_status()
            if status.get('has_update'):
                url = status.get('html_url') or RELEASES_PAGE_URL
                AppHelper.callAfter(self.ui.show_message, 'Доступно обновление', f"Версия {status['latest']} готова к установке.", 'Открыть релиз', lambda: self.open_url(url))
        except Exception:
            log.exception('Update check failed')

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
