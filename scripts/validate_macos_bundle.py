"""Check every Mach-O architecture and the app version before producing a DMG."""
from pathlib import Path
import plistlib
import re
import subprocess
import sys


def validate(bundle: Path, target: str) -> int:
    expected = {"arm64", "x86_64"} if target == "universal2" else {target}
    root = Path(__file__).resolve().parent.parent
    version = re.search(r'__version__ = "([^"]+)"', (root / "proxy/__init__.py").read_text()).group(1)
    with (bundle / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    if info["CFBundleShortVersionString"] != version or info["CFBundleVersion"] != version:
        raise ValueError("Bundle version differs from the source version")
    macho_magic = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
    count = 0
    for path in bundle.rglob("*"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) not in macho_magic:
                continue
        archs = set(subprocess.check_output(["lipo", "-archs", str(path)], text=True).split())
        if archs != expected:
            raise ValueError(f"{path}: expected {expected}, found {archs}")
        count += 1
    if not count:
        raise ValueError("No Mach-O binaries found")
    return count


if __name__ == "__main__":
    print(f"Validated {validate(Path(sys.argv[1]), sys.argv[2])} Mach-O binaries ({sys.argv[2]}).")
