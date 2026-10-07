import hashlib
import io
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from utils import macos_integration as mac


class MacIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = self.root / "Proxy with ' quotes.app"
        (self.app / 'Contents/MacOS').mkdir(parents=True)
        (self.app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': mac.BUNDLE_ID, 'CFBundleExecutable': 'proxy',
        }))
        binary = self.app / 'Contents/MacOS/proxy'
        binary.write_text('old')
        binary.chmod(0o755)

    def test_startup_roundtrip_and_moved_application(self):
        path = self.root / 'LaunchAgents/proxy.plist'
        mac.set_startup(self.app, True, path)
        self.assertTrue(mac.startup_enabled(self.app, path))
        self.assertFalse(mac.startup_enabled(self.root / 'moved.app', path))
        self.assertEqual(plistlib.loads(path.read_bytes())['ProgramArguments'][-1], str(self.app))
        mac.set_startup(self.app, False, path)
        mac.set_startup(self.app, False, path)
        self.assertFalse(path.exists())

    def test_startup_rejects_uninstalled_application(self):
        with self.assertRaises(ValueError):
            mac.set_startup(self.root / 'missing.app', True, self.root / 'agent.plist')

    def test_asset_requires_expected_origin_and_digest(self):
        asset = {'name': mac.ASSET_NAME,
                 'url': 'https://github.com/f4rceful/tg-ws-proxy-mac/releases/download/v2/a.dmg',
                 'digest': 'sha256:' + 'a' * 64}
        self.assertEqual(mac.update_asset({'assets': [asset]}), asset)
        for update in [{'digest': ''}, {'url': 'https://example.com/a.dmg'}, {'name': 'windows.exe'}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                mac.update_asset({'assets': [dict(asset, **update)]})

    def test_download_verifies_content(self):
        data = b'dmg bytes'
        asset = {'url': 'https://example.com/a', 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}
        opener = Mock()
        opener.open.return_value = io.BytesIO(data)
        mac.download_release(asset, self.root / 'download', opener)
        opener.open.return_value = io.BytesIO(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            mac.download_release(asset, self.root / 'download', opener)

    def test_bundle_rejects_wrong_identifier(self):
        mac.validate_bundle(self.app)
        (self.app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'another.app', 'CFBundleExecutable': 'proxy',
        }))
        with self.assertRaises(ValueError):
            mac.validate_bundle(self.app)

    @unittest.skipUnless(os.name == 'posix', 'POSIX installer helper')
    def test_installer_success_and_launch_failure_rollback(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                folder = self.root / str(fail)
                folder.mkdir()
                target = folder / 'current app'
                stage = folder / 'next app'
                backup = folder / 'previous app'
                target.mkdir()
                stage.mkdir()
                (target / 'marker').write_text('old')
                (stage / 'marker').write_text('new')
                # Never invoke Launch Services in a unit test.
                command = '/usr/bin/false' if fail else '/usr/bin/true'
                script = mac.UPDATE_HELPER.replace('/usr/bin/open -n', command)
                result = subprocess.run(['/bin/sh', '-c', script, 'installer', '99999999',
                                         str(target), str(stage), str(backup)], capture_output=True)
                self.assertEqual((target / 'marker').read_text(), 'old' if fail else 'new')
                self.assertEqual(result.returncode == 0, not fail)
                if not fail:
                    self.assertEqual((backup / 'marker').read_text(), 'old')

    def test_bad_download_does_not_change_installed_app(self):
        asset = {'name': mac.ASSET_NAME,
                 'url': 'https://github.com/f4rceful/tg-ws-proxy-mac/releases/download/v2/a.dmg',
                 'digest': 'sha256:' + 'a' * 64}
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'invalid')
        with self.assertRaises(ValueError):
            mac.prepare_update(self.app, {'assets': [asset]}, opener)
        self.assertEqual((self.app / 'Contents/MacOS/proxy').read_text(), 'old')
        self.assertFalse(list(self.root.glob(mac.UPDATE_PREFIX + '*')))

    @unittest.skipUnless(os.name == 'posix', 'POSIX installer helper')
    def test_installer_does_not_replace_running_app(self):
        stage = self.root / 'next.app'
        stage.mkdir()
        backup = self.root / 'previous.app'
        script = mac.UPDATE_HELPER.replace('"$count" -ge 60', '"$count" -ge 1')
        result = subprocess.run(['/bin/sh', '-c', script, 'installer', str(os.getpid()),
                                 str(self.app), str(stage), str(backup)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.app.exists())
        self.assertFalse(backup.exists())

    def test_bundle_rejects_executable_outside_bundle(self):
        binary = self.app / 'Contents/MacOS/proxy'
        binary.unlink()
        binary.symlink_to('/bin/sh')
        with self.assertRaises(ValueError):
            mac.validate_bundle(self.app)

    def test_cleanup_keeps_newest_valid_recovery(self):
        updates = []
        for index in range(3):
            folder = self.root / f'{mac.UPDATE_PREFIX}{index}'
            folder.mkdir()
            shutil.copytree(self.app, folder / 'previous.app')
            (folder / 'install.log').write_text('installed')
            os.utime(folder, ns=(index + 1, index + 1))
            updates.append(folder)
        invalid = self.root / (mac.UPDATE_PREFIX + 'invalid')
        invalid.mkdir()

        mac.cleanup_old_updates(self.app)

        self.assertFalse(updates[0].exists())
        self.assertFalse(updates[1].exists())
        self.assertTrue(updates[2].exists())
        self.assertTrue(invalid.exists())

    def test_startup_refuses_mounted_and_translocated_apps(self):
        for location in ('/Volumes/Installer', '/private/AppTranslocation/Test'):
            with self.subTest(location=location), unittest.mock.patch.object(Path, 'is_file', return_value=True):
                with self.assertRaises(ValueError):
                    mac.set_startup(Path(location) / mac.APP_NAME, True, self.root / 'agent.plist')
        self.assertFalse((self.root / 'agent.plist').exists())

    def test_update_never_accepts_original_repository(self):
        asset = {'name': mac.ASSET_NAME, 'url': 'https://github.com/Flowseal/tg-ws-proxy/releases/download/v2/a.dmg', 'digest': 'sha256:' + 'a' * 64}
        with self.assertRaises(ValueError):
            mac.update_asset({'assets': [asset]})

    @unittest.skipUnless(os.sys.platform == 'darwin', 'native macOS disk image and signature verification')
    def test_real_signed_dmg_is_staged_without_replacing_running_application(self):
        source = self.root / 'image' / mac.APP_NAME
        (source / 'Contents/MacOS').mkdir(parents=True)
        (source / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': mac.BUNDLE_ID,
            'CFBundleExecutable': 'proxy',
            'CFBundleShortVersionString': '0.4.0',
        }))
        shutil.copyfile('/usr/bin/true', source / 'Contents/MacOS/proxy')
        (source / 'Contents/MacOS/proxy').chmod(0o755)
        subprocess.run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', str(source)], check=True, capture_output=True)
        image = self.root / 'test.dmg'
        subprocess.run(['/usr/bin/hdiutil', 'create', '-srcfolder', str(source.parent), '-format', 'UDZO', '-fs', 'HFS+', str(image)], check=True, capture_output=True, timeout=120)
        asset = {'name': mac.ASSET_NAME, 'url': 'https://github.com/f4rceful/tg-ws-proxy-mac/releases/download/v0.4.0/' + mac.ASSET_NAME, 'digest': 'sha256:' + hashlib.sha256(image.read_bytes()).hexdigest()}
        opener = Mock()
        opener.open.return_value = image.open('rb')
        phases = []
        work = mac.prepare_update(self.app, {'assets': [asset], 'latest': '0.4.0'}, opener, phases.append)
        self.assertEqual(phases, ['update.downloading', 'update.mac_preparing'])
        self.assertEqual((self.app / 'Contents/MacOS/proxy').read_text(), 'old')
        self.assertTrue((work / 'next.app/Contents/MacOS/proxy').is_file())
        self.assertFalse((work / 'release.dmg').exists())
        self.assertFalse(os.path.ismount(work / 'mount'))
        self.assertTrue((work / 'install.sh').is_file())
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(work / 'next.app')], check=True, capture_output=True)
