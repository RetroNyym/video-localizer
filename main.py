from __future__ import annotations

import sys


def _fix_console() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_fix_console()

from videoloc.cli import main as cli_main  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        from videoloc.gui import run_app

        run_app()
        return 0
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
