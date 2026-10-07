import asyncio
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from proxy import proxy_config
from proxy._aes import Cipher, algorithms, modes
from proxy import tg_ws_proxy
from utils import macos_common, update_check
from utils.default_config import default_tray_config


class MacOSIntegrationTests(unittest.TestCase):
    def test_single_instance_lock_and_release(self):
        probe = (
            'import sys; from pathlib import Path; from utils import macos_common as m; '
            'm.APP_DIR = Path(sys.argv[1]); print(m.acquire_lock()); m.release_lock()'
        )
        with tempfile.TemporaryDirectory() as directory, patch.object(macos_common, 'APP_DIR', Path(directory)):
            try:
                self.assertTrue(macos_common.acquire_lock())
                result = subprocess.check_output([sys.executable, '-c', probe, directory], text=True)
                self.assertEqual(result.strip(), 'False')
            finally:
                macos_common.release_lock()
            result = subprocess.check_output([sys.executable, '-c', probe, directory], text=True)
            self.assertEqual(result.strip(), 'True')

    def test_settings_survive_save_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(macos_common, 'APP_DIR', root), patch.object(macos_common, 'CONFIG_FILE', root / 'config.json'):
                config = default_tray_config()
                config.update(port=2443, cfproxy_worker_domain=['example.workers.dev'])
                macos_common.save_config(config)
                loaded = macos_common.load_config()
                self.assertEqual(loaded, config)
                self.assertIn('port=2443', macos_common.tg_proxy_url(loaded))
                self.assertIn('secret=dd' + config['secret'], macos_common.tg_proxy_url(loaded))

    def test_updates_use_fork_without_original_app_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(update_check.Path, 'home', return_value=Path(directory)):
            cache = update_check._cache_file()
            self.assertIn('TgWsProxyMac', cache.parts)
            self.assertEqual(update_check.REPO, 'f4rceful/tg-ws-proxy-mac')
            release = {'tag_name': 'v0.1.1', 'html_url': update_check.RELEASES_PAGE_URL, 'assets': []}
            with patch.object(update_check, 'fetch_latest_release', return_value=(release, 'etag', 200)):
                update_check.run_check('0.1.0')
            self.assertTrue(update_check.get_status()['has_update'])
            self.assertEqual(update_check.get_status()['latest'], '0.1.1')

    def test_native_clipboard(self):
        import macos
        config = default_tray_config()
        with patch.object(macos, '_config', config), patch.object(macos.subprocess, 'run') as clipboard:
            macos._on_copy_link()
            clipboard.assert_called_once_with(['pbcopy'], input=macos_common.tg_proxy_url(config).encode(), check=True)

    def test_aes_ctr_known_vector(self):
        key = bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
        iv = bytes.fromhex('f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff')
        plain = bytes.fromhex('6bc1bee22e409f96e93d7e117393172a')
        expected = bytes.fromhex('874d6191b620e3261bef6864990db6ce')
        self.assertEqual(Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor().update(plain), expected)


class ProxyLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_server_accepts_connection_and_stops(self):
        saved = deepcopy(vars(proxy_config))
        proxy_config.host = '127.0.0.1'
        proxy_config.port = 0
        proxy_config.fallback_cfproxy = False
        stop = asyncio.Event()
        task = None
        try:
            with patch.object(tg_ws_proxy.ws_pool, 'warmup', new_callable=AsyncMock), patch.object(tg_ws_proxy.cf_worker_pool, 'warmup', new_callable=AsyncMock):
                task = asyncio.create_task(tg_ws_proxy._run(stop))
                for _ in range(100):
                    if task.done():
                        await task
                    if tg_ws_proxy._server_instance is not None:
                        break
                    await asyncio.sleep(0.01)
                self.assertIsNotNone(tg_ws_proxy._server_instance)
                port = tg_ws_proxy._server_instance.sockets[0].getsockname()[1]
                reader, writer = await asyncio.open_connection('127.0.0.1', port)
                writer.close()
                await writer.wait_closed()
                stop.set()
                await asyncio.wait_for(task, timeout=3)
                self.assertIsNone(tg_ws_proxy._server_instance)
        finally:
            stop.set()
            if task and not task.done():
                await asyncio.wait_for(task, timeout=3)
            vars(proxy_config).update(saved)


if __name__ == '__main__':
    unittest.main()
