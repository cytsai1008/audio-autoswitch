"""Build the standalone executable with PyInstaller.

uv run python build.py            # -> dist/audio-autoswitch.exe
uv run python build.py --clean    # discard PyInstaller caches first
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ICON = BUILD / "audio-autoswitch.ico"

# pystray and comtypes resolve their backends dynamically, so PyInstaller's
# static analysis cannot see them.
HIDDEN = ["pystray._win32", "comtypes.stream"]
EXCLUDE = ["tkinter", "unittest", "pydoc_data", "test"]

NAME = "audio-autoswitch"
ENTRY_MODULE = "audio_autoswitch.tray"

LAUNCHER = """from {module} import main

main()
"""


def write_launcher(name: str, module: str) -> Path:
    """PyInstaller runs its entry script as __main__, which breaks the package's
    relative imports -- so give it a launcher that imports absolutely instead."""
    path = BUILD / f"{name}-entry.py"
    path.write_text(LAUNCHER.format(module=module), encoding="utf-8")
    return path


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from audio_autoswitch.icons import write_ico

    if "--clean" in sys.argv:
        for path in (BUILD, DIST):
            shutil.rmtree(path, ignore_errors=True)

    BUILD.mkdir(parents=True, exist_ok=True)
    write_ico(ICON)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconfirm",
        # Windows GUI subsystem: no console flashes when the tray app starts. The
        # command-line modes attach or allocate a console for themselves at runtime.
        "--windowed",
        "--name",
        NAME,
        "--icon",
        str(ICON),
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD),
        str(write_launcher(NAME, ENTRY_MODULE)),
    ]
    for hidden in HIDDEN:
        cmd += ["--hidden-import", hidden]
    for excluded in EXCLUDE:
        cmd += ["--exclude-module", excluded]

    print(f"\n=== building {NAME}.exe ===")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    exe = DIST / f"{NAME}.exe"
    print(f"  {exe.name}  {exe.stat().st_size / 1_048_576:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
