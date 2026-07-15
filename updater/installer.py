from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from updater.extractor import extract_zip
from updater.fileops import copy_tree_contents, remove_tree
from updater.rollback import restore_backup


@dataclass(frozen=True)
class InstallPlan:
    package_path: Path
    app_dir: Path
    main_exe: str
    restart: bool = True


class UpdateInstaller:
    def __init__(self, plan: InstallPlan, logger):
        self.plan = plan
        self.logger = logger
        self.logs_dir = self.plan.app_dir / "logs"
        self.backup_root = self.plan.app_dir / "backup"
        self.temp_root = self.plan.app_dir / "update-cache"
        self.skip_file_names = {"DLP Master Updater.exe"}

    def install(self) -> int:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_dir = self.backup_root / timestamp
        extract_dir = self.temp_root / f"extract-{timestamp}"

        try:
            self.logger.info("Starting update install")
            self._validate_inputs()

            self.logger.info("Creating backup: %s", backup_dir)
            copy_tree_contents(self.plan.app_dir, backup_dir, skip_file_names=set())

            self.logger.info("Extracting package: %s", self.plan.package_path)
            extract_zip(self.plan.package_path, extract_dir)

            source_root = self._detect_source_root(extract_dir)
            expected_main = source_root / self.plan.main_exe
            if not expected_main.exists():
                raise FileNotFoundError(f"Package does not contain {self.plan.main_exe}")

            self._wait_for_main_app_to_exit()

            self.logger.info("Copying update files from %s to %s", source_root, self.plan.app_dir)
            copy_tree_contents(source_root, self.plan.app_dir, skip_file_names=self.skip_file_names)

            if self.plan.restart:
                self._restart_main_app()

            remove_tree(extract_dir)
            self.logger.info("Update install completed")
            return 0
        except Exception:
            self.logger.exception("Update install failed; restoring backup")
            try:
                restore_backup(backup_dir, self.plan.app_dir, skip_file_names=self.skip_file_names)
            except Exception:
                self.logger.exception("Rollback failed")
                return 2
            return 1

    def _validate_inputs(self):
        if not self.plan.package_path.exists():
            raise FileNotFoundError(self.plan.package_path)
        if not self.plan.app_dir.exists():
            raise FileNotFoundError(self.plan.app_dir)

    def _detect_source_root(self, extract_dir: Path) -> Path:
        direct_main = extract_dir / self.plan.main_exe
        if direct_main.exists():
            return extract_dir
        children = [child for child in extract_dir.iterdir() if child.is_dir()]
        for child in children:
            if (child / self.plan.main_exe).exists():
                return child
        return extract_dir

    def _wait_for_main_app_to_exit(self, timeout_seconds: int = 45):
        main_exe = self.plan.app_dir / self.plan.main_exe
        if not main_exe.exists():
            return

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                with main_exe.open("r+b"):
                    return
            except PermissionError:
                self.logger.info("Waiting for main app to exit: %s", main_exe)
                time.sleep(1)

        raise TimeoutError(f"Main app did not exit within {timeout_seconds}s: {main_exe}")

    def _restart_main_app(self):
        main_exe = self.plan.app_dir / self.plan.main_exe
        if not main_exe.exists():
            self.logger.warning("Main executable not found for restart: %s", main_exe)
            return
        self.logger.info("Restarting main app: %s", main_exe)
        subprocess.Popen([str(main_exe)], cwd=str(self.plan.app_dir))
