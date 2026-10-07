# -*- mode: python ; coding: utf-8 -*-
import os
import platform
import re
from pathlib import Path

project_root = Path(SPECPATH).parent
version_source = (project_root / 'proxy' / '__init__.py').read_text()
version = re.search(r'__version__ = "([^"]+)"', version_source).group(1)
target_arch = os.environ.get('TG_WS_TARGET_ARCH', platform.machine())

a = Analysis(
    [str(project_root / 'macos.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        'rumps', 'objc', 'Foundation', 'AppKit', 'PyObjCTools.AppHelper',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.backends.openssl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL._avif', 'PIL._webp', 'PIL._imagingtk', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='TgWsProxyMac',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=target_arch,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TgWsProxyMac')
app = BUNDLE(
    coll,
    name='TG WS Proxy Mac.app',
    icon=str(project_root / 'assets' / 'icon.icns'),
    bundle_identifier='com.github.f4rceful.tgwsproxymac',
    info_plist={
        'CFBundleName': 'TG WS Proxy Mac',
        'CFBundleDisplayName': 'TG WS Proxy Mac',
        'CFBundleShortVersionString': version,
        'CFBundleVersion': version,
        'LSMinimumSystemVersion': '11.0',
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
        'NSAppleEventsUsageDescription': 'TG WS Proxy Mac needs to display dialogs.',
    },
)
