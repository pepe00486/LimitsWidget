"""Test the real Qt event loop and process transport without a desktop or account."""

import os
from pathlib import Path
import tempfile
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limit_widget.app import DEFAULT_REFRESH_SECONDS, LimitWidget
from limit_widget.providers import CodexProvider


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, self.temp.name)
        self.results = []
        self.errors = []

    def provider(self, scenario="normal"):
        provider = CodexProvider(str(Path(__file__).with_name("fake_codex.py")))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("WIDGET_TEST_SCENARIO", scenario)
        environment.insert("WIDGET_TEST_MARKER", str(Path(self.temp.name) / "first-request"))
        provider.process.setProcessEnvironment(environment)
        provider.updated.connect(self.results.append)
        provider.failed.connect(self.errors.append)
        self.addCleanup(provider.close)
        return provider

    def window(self, provider, demo=False):
        widget = LimitWidget(provider, demo=demo)
        self.addCleanup(widget.close)
        widget.show()
        return widget

    def wait_until(self, condition):
        for _ in range(500):
            if condition():
                return
            QTest.qWait(10)
        self.fail(f"Timed out. Provider errors: {self.errors}")

    def test_handshake_and_refresh(self):
        provider = self.provider()
        provider.refresh()
        self.wait_until(lambda: len(self.results) == 1)
        self.assertEqual(self.results[0].five_hour.remaining, 77)
        self.assertEqual(self.results[0].weekly.remaining, 52)
        provider.refresh()
        self.wait_until(lambda: len(self.results) == 2)
        self.assertEqual(self.results[1].five_hour.remaining, 76)
        self.assertEqual(self.results[1].weekly.remaining, 51)
        self.assertFalse(self.errors)

    def test_timer_updates_both_limits(self):
        widget = self.window(self.provider())
        self.assertEqual(widget.poll.interval(), DEFAULT_REFRESH_SECONDS * 1000)
        self.assertIn("Automatic refresh: every 30 seconds", widget.toolTip())
        widget.poll.setInterval(100)
        self.wait_until(lambda: len(self.results) >= 3)
        self.assertNotEqual(self.results[-1].five_hour, self.results[-2].five_hour)
        self.assertNotEqual(self.results[-1].weekly, self.results[-2].weekly)
        self.assertEqual(widget.usage, self.results[-1])
        self.assertIsNotNone(widget.last_update)
        self.assertFalse(widget.error)

    def test_timer_recovers_after_timeout(self):
        provider = self.provider("timeout")
        provider.timeout.setInterval(80)
        widget = self.window(provider)
        widget.poll.setInterval(100)
        self.wait_until(lambda: bool(self.errors))
        self.wait_until(lambda: bool(self.results))
        self.assertIn("did not respond", self.errors[0])
        self.assertFalse(widget.error)

    def test_signed_out_account_reports_error(self):
        self.provider("signed-out").refresh()
        self.wait_until(lambda: bool(self.errors))
        self.assertIn("codex login", self.errors[0])

    def test_missing_executable_reports_error(self):
        provider = self.provider()
        provider.executable = str(Path(self.temp.name) / "missing")
        provider.refresh()
        self.wait_until(lambda: bool(self.errors))
        self.assertIn("Cannot start Codex", self.errors[0])

    def test_invalid_response_reports_error(self):
        self.provider("malformed").refresh()
        self.wait_until(lambda: bool(self.errors))
        self.assertIn("invalid response", self.errors[0])

    def test_close_button_stops_timers_and_process(self):
        provider = self.provider()
        widget = self.window(provider)
        self.wait_until(lambda: bool(self.results))
        QTest.mouseClick(widget.close_button, Qt.MouseButton.LeftButton)
        self.assertFalse(widget.isVisible())
        self.assertFalse(widget.poll.isActive())
        self.assertFalse(widget.clock.isActive())
        self.assertEqual(provider.process.state(), QProcess.ProcessState.NotRunning)

    def test_error_keeps_last_successful_values(self):
        widget = self.window(self.provider(), demo=True)
        usage, updated = widget.usage, widget.last_update
        widget.provider.failed.emit("Connection lost")
        self.assertEqual(widget.usage, usage)
        self.assertEqual(widget.last_update, updated)
        self.assertIn("Connection lost", widget.toolTip())
        self.assertFalse(widget.poll.isActive())
