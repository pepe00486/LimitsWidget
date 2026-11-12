"""A transparent, movable display with two usage rows."""

import argparse
import os
import sys
from collections.abc import MutableMapping
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLibrary, QLibraryInfo, QPoint, QRect, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QToolButton, QWidget

from .models import Limit, Usage
from .providers import CodexProvider, UsageProvider

DEFAULT_REFRESH_SECONDS = 30


def configure_display(
    environment: MutableMapping[str, str] | None = None,
    *,
    xcb_available: bool | None = None,
) -> None:
    """Prefer XWayland for window stacking when an X display is available."""
    env = os.environ if environment is None else environment
    wayland = env.get("XDG_SESSION_TYPE") == "wayland" or bool(env.get("WAYLAND_DISPLAY"))
    if not wayland or not env.get("DISPLAY") or env.get("QT_QPA_PLATFORM"):
        return
    if xcb_available is None:
        plugins = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
        xcb_available = QLibrary(str(Path(plugins) / "platforms/libqxcb.so")).load()
    if xcb_available:
        env["QT_QPA_PLATFORM"] = "xcb"


class LimitWidget(QWidget):
    def __init__(
        self, provider: UsageProvider, interval: int = DEFAULT_REFRESH_SECONDS, demo: bool = False
    ) -> None:
        super().__init__()
        self.provider = provider
        self.demo = demo
        self.usage = Usage()
        self.error = "Connecting to Codex…"
        self.last_update = None
        self.drag_offset = None
        self.settings = QSettings("LimitWidget", "LimitWidget")
        self._setup_window()
        self.provider.updated.connect(self._updated)
        self.provider.failed.connect(self._failed)
        self.poll = QTimer(self)
        self.poll.setTimerType(Qt.TimerType.PreciseTimer)
        self.poll.setInterval(interval * 1000)
        self.poll.timeout.connect(self.provider.refresh)
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._tick)
        self.clock.start()
        if demo:
            self._updated(Usage(Limit(23), Limit(48)))
        else:
            self.poll.start()
            QTimer.singleShot(0, self.provider.refresh)
            self._tick()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

    def _setup_window(self) -> None:
        self.setWindowTitle("Codex limits")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(236, 94)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setAccessibleName("Codex usage limits")
        self._create_close_button()
        position = self.settings.value("position", QPoint(80, 80))
        if isinstance(position, QPoint) and any(
            screen.availableGeometry().contains(QRect(position, self.size()))
            for screen in QApplication.screens()
        ):
            self.move(position)

    def _create_close_button(self) -> None:
        self.close_button = QToolButton(self)
        self.close_button.setText("×")
        self.close_button.setGeometry(self.width() - 24, 5, 18, 18)
        self.close_button.setToolTip("Close widget")
        self.close_button.setAccessibleName("Close widget")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QToolButton { color: #aeb8c7; background: transparent;"
            " border: none; border-radius: 4px; font-size: 16px; }"
            "QToolButton:hover, QToolButton:focus { color: white; background: #9c3945; }"
            "QToolButton:pressed { background: #742a33; }"
        )
        self.close_button.clicked.connect(self.close)

    def _updated(self, usage: Usage) -> None:
        self.usage = usage
        self.error = ""
        self.last_update = datetime.now().astimezone()
        self._tick()
        self.update()

    def _failed(self, message: str) -> None:
        self.error = message
        self._tick()
        self.update()

    def _tick(self) -> None:
        lines = ["Demo data" if self.demo else "Codex · percentage remaining"]
        if self.last_update:
            lines.append("Last update: " + self.last_update.strftime("%H:%M:%S"))
        if not self.demo and self.poll.isActive():
            seconds = max(0, (self.poll.remainingTime() + 999) // 1000)
            lines.append(f"Automatic refresh: every {self.poll.interval() / 1000:g} seconds")
            lines.append(f"Next refresh: in {seconds} seconds")
        for title, limit in self.usage.rows():
            if limit and limit.resets_at is not None:
                try:
                    reset = datetime.fromtimestamp(limit.resets_at).astimezone()
                    lines.append(f"{title} resets: {reset:%a %d %b %H:%M %Z}")
                except (ValueError, OverflowError, OSError):
                    pass
        if self.error:
            lines.append(self.error)
        lines.append("Drag to move. Right-click for controls.")
        description = "\n".join(lines)
        self.setToolTip(description)
        self.setAccessibleDescription(description)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The window is transparent. A faint panel keeps text readable.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 23, 30, 155))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        for index, (label, limit) in enumerate(self.usage.rows()):
            y = 12 + index * 38
            stale = bool(self.error)
            value = "—" if limit is None else f"{limit.remaining:.0f}% left"
            if stale and limit is not None:
                value += " *"
            painter.setFont(QFont("Sans Serif", 10))
            painter.setPen(QColor("#aeb8c7"))
            painter.drawText(QRect(16, y, 64, 23), Qt.AlignmentFlag.AlignVCenter, label)
            painter.setFont(QFont("Sans Serif", 11, QFont.Weight.DemiBold))
            color = "#e6edf3" if not stale else "#edc777"
            painter.setPen(QColor(color))
            painter.drawText(
                QRect(82, y, 118, 23),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                value,
            )
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle and handle.startSystemMove():
                self.drag_offset = None
            else:
                self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        refresh = menu.addAction("Refresh now", self.provider.refresh)
        refresh.setEnabled(not self.demo)
        top = menu.addAction("Always on top")
        top.setCheckable(True)
        top.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        top.triggered.connect(self._set_on_top)
        menu.addSeparator()
        menu.addAction("Quit", self.close)
        menu.exec(event.globalPos())

    def _set_on_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()

    def closeEvent(self, event):
        self.poll.stop()
        self.clock.stop()
        self.settings.setValue("position", self.pos())
        self.provider.close()
        event.accept()


def main() -> None:
    parser = argparse.ArgumentParser(description="Show Codex usage limits on Linux.")
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_REFRESH_SECONDS, metavar="SECONDS",
        help=f"Refresh period in seconds (default: {DEFAULT_REFRESH_SECONDS}).",
    )
    parser.add_argument("--codex", default="codex", metavar="PATH")
    parser.add_argument("--demo", action="store_true", help="Show sample data without connecting.")
    args = parser.parse_args()
    if args.interval < 15:
        parser.error("--interval must be at least 15 seconds")
    configure_display()
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Limit Widget")
    provider = CodexProvider(args.codex)
    window = LimitWidget(provider, args.interval, args.demo)
    app.aboutToQuit.connect(provider.close)
    window.show()
    sys.exit(app.exec())
