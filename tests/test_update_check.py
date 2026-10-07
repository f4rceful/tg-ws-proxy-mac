from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from utils import update_check as updates
from utils.i18n import set_language, t


class ReleaseCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'cache.json'
        self.original = deepcopy(updates._state)
        self.addCleanup(lambda: updates._state.update(self.original))
        self.asset = {'name': 'TgWsProxyMac_universal2.dmg', 'browser_download_url': 'https://github.com/f4rceful/tg-ws-proxy-mac/releases/download/v0.4.0/TgWsProxyMac_universal2.dmg', 'digest': 'sha256:' + 'a' * 64}

    def test_download_metadata_survives_cached_and_304_checks(self):
        data = {'tag_name': 'v0.4.0', 'assets': [self.asset]}
        with patch.object(updates, '_cache_file', return_value=self.path), patch.object(updates, 'fetch_latest_release', return_value=(data, 'etag', 200)) as fetch:
            updates.run_check('0.3.0')
            first = updates.get_status()
            self.assertTrue(first['has_update'])
            self.assertEqual(first['assets'][0]['digest'], self.asset['digest'])
            updates.run_check('0.3.0')
            self.assertEqual(updates.get_status()['assets'], first['assets'])
            self.assertEqual(fetch.call_count, 1)
            fetch.return_value = (None, 'etag', 304)
            updates.run_check('0.3.0', force=True)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(updates.get_status()['assets'], first['assets'])

    def test_failure_clears_stale_install_action(self):
        updates._state.update(has_update=True, assets=[self.asset])
        with patch.object(updates, '_cache_file', return_value=self.path), patch.object(updates, 'fetch_latest_release', side_effect=OSError('offline')):
            updates.run_check('0.3.0', force=True)
        self.assertFalse(updates.get_status()['has_update'])
        self.assertEqual(updates.get_status()['assets'], [])

    def test_extract_assets_rejects_incomplete_entries(self):
        data = {'assets': [None, {'name': 'a'}, {'browser_download_url': 'b'}, self.asset]}
        self.assertEqual(updates._extract_assets(data), [{'name': self.asset['name'], 'url': self.asset['browser_download_url'], 'digest': self.asset['digest']}])
        self.assertEqual(updates._extract_assets(None), [])

    def test_native_update_strings_have_both_languages(self):
        text = 'Установить версию {version}? Прокси будет перезапущен. Предыдущая версия приложения будет сохранена для восстановления.'
        try:
            set_language('ru')
            self.assertTrue(t(text, version='0.4.0').startswith('Установить'))
            set_language('en')
            self.assertTrue(t(text, version='0.4.0').startswith('Install'))
            self.assertEqual(t('Порт: допустимо от 1 до 65535.'), 'Port: valid range is 1–65535.')
        finally:
            set_language('ru')
