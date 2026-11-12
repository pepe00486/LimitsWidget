#!/usr/bin/env python3
"""Install a desktop shortcut and an application menu entry for this checkout."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess


def desktop_directory() -> Path:
    """Find the configured desktop directory or use the default location."""
    if shutil.which("xdg-user-dir"):
        result = subprocess.run(
            ["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            directory = Path(result.stdout.strip())
            if directory != Path.home():
                return directory
    return Path.home() / "Desktop"


def desktop_entry(launch: Path) -> str:
    """Quote the command, then escape backslashes for the desktop file format."""
    executable = str(launch).replace("\\", "\\\\")
    for character in ('"', '`', '$'):
        executable = executable.replace(character, "\\" + character)
    executable = executable.replace("\\", "\\\\").replace("%", "%%")
    return f'''[Desktop Entry]
Version=1.0
Type=Application
Name=Codex Limit Widget
Comment=Show the Codex 5-hour and weekly limits
Exec="{executable}" --desktop
Icon=utilities-system-monitor
Terminal=false
Categories=Utility;
StartupNotify=false
'''


def main() -> None:
    """Install shortcuts for the current repository location."""
    parser = argparse.ArgumentParser(description="Install the Limit Widget launcher.")
    parser.add_argument("--desktop-dir", type=Path)
    parser.add_argument("--applications-dir", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    launch = project / "launch.sh"
    launch.chmod(launch.stat().st_mode | 0o100)
    entry = desktop_entry(launch)
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    applications = args.applications_dir or data_home / "applications"
    desktop = args.desktop_dir or desktop_directory()
    for directory in (applications, desktop):
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "LimitWidget.desktop"
        target.write_text(entry, encoding="utf-8")
        target.chmod(0o755)
        if shutil.which("gio"):
            subprocess.run(["gio", "set", str(target), "metadata::trusted", "true"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        print(f"Installed: {target}")
    print("Open Codex Limit Widget from the application menu or your desktop.")
    print("If your desktop asks, select Allow Launching.")


if __name__ == "__main__":
    main()
