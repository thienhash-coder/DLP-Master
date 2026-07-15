from __future__ import annotations

import argparse
import sys
from pathlib import Path

from updater.installer import InstallPlan, UpdateInstaller
from updater.logger import get_logger


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DLP Master standalone updater")
    parser.add_argument("--package", required=True, help="Path to release ZIP package")
    parser.add_argument("--app-dir", required=True, help="Application directory to update")
    parser.add_argument("--main-exe", required=True, help="Main executable name")
    parser.add_argument("--restart", action="store_true", help="Restart main app after update")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    app_dir = Path(args.app_dir).resolve()
    logger = get_logger("dlp_master_updater", app_dir / "logs" / "installer.log")
    plan = InstallPlan(
        package_path=Path(args.package).resolve(),
        app_dir=app_dir,
        main_exe=args.main_exe,
        restart=bool(args.restart),
    )
    return UpdateInstaller(plan, logger).install()


if __name__ == "__main__":
    raise SystemExit(main())

