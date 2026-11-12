"""Test the real Qt event loop and process transport without a desktop or account."""

import os
from pathlib import Path
import shutil
import tempfile
import unittest

from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limit_widget.app import DEFAULT_REFRESH_SECONDS, LimitWidget
from limit_widget.providers import CodexProvider


class WidgetTests(unittest.TestCase):
    """Check window controls, polling, and provider failures."""

    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(self.temp))
        self.results = []
        self.errors = []

    def provider(self, scenario="normal"):
        """Create a fake Codex provider and register cleanup."""
        provider = CodexProvider(str(Path(__file__).with_name("fake_codex.py")))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("WIDGET_TEST_SCENARIO", scenario)
        environment.insert("WIDGET_TEST_MARKER", str(self.temp / "first-request"))
        provider.process.setProcessEnvironment(environment)
        provider.updated.connect(self.results.append)
        provider.failed.connect(self.errors.append)
        self.addCleanup(provider.close)
        return provider

    def window(self, provider, demo=False):
        """Create and show a widget for the selected provider."""
        widget = LimitWidget(provider, demo=demo)
        self.addCleanup(widget.close)
        widget.show()
        return widget

    def wait_until(self, condition):
        """Process Qt events until the condition succeeds or the test times out."""
        for _ in range(500):
            if condition():
                return
            QTest.qWait(10)
        self.fail(f"Timed out. Provider errors: {self.errors}")

    def test_handshake_and_refresh(self):
        """Complete initialization and read updated values."""
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
        """Update both limits through the automatic timer."""
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
        """Retry automatically after a request timeout."""
        provider = self.provider("timeout")
        provider.timeout.setInterval(80)
        widget = self.window(provider)
        widget.poll.setInterval(100)
        self.wait_until(lambda: bool(self.errors))
        self.wait_until(lambda: bool(self.results))
        self.assertIn("did not respond", self.errors[0])
        self.assertFalse(widget.error)

    def test_signed_out_account_reports_error(self):
        """Report a signed-out account without starting a login flow."""
        self.provider("signed-out").refresh()
        self.wait_until(lambda: bool(self.errors))
        self.assertIn("codex login", self.errors[0])

    def test_missing_executable_reports_error(self):
        """Report a missing Codex executable."""
        provider = self.provider()
        provider.executable = str(self.temp / "missing")
        provider.refresh()
        self.wait_until(lambda: bool(self.errors))
        self.assertIn("Cannot start Codex", self.errors[0])

    def test_invalid_response_reports_error(self):
        """Report malformed protocol responses."""
        self.provider("malformed").refresh()
        self.wait_until(lambda: bool(self.errors))
        self.assertIn("invalid response", self.errors[0])

    def test_close_button_stops_timers_and_process(self):
        """Stop timers and the provider when the close button is clicked."""
        provider = self.provider()
        widget = self.window(provider)
        self.wait_until(lambda: bool(self.results))
        QTest.mouseClick(widget.close_button, Qt.MouseButton.LeftButton)
        self.assertFalse(widget.isVisible())
        self.assertFalse(widget.poll.isActive())
        self.assertFalse(widget.clock.isActive())
        self.assertEqual(provider.process.state(), QProcess.ProcessState.NotRunning)

    def test_error_keeps_last_successful_values(self):
        """Keep the last successful values after a connection error."""
        widget = self.window(self.provider(), demo=True)
        usage, updated = widget.usage, widget.last_update
        widget.provider.failed.emit("Connection lost")
        self.assertEqual(widget.usage, usage)
        self.assertEqual(widget.last_update, updated)
        self.assertIn("Connection lost", widget.toolTip())
        self.assertFalse(widget.poll.isActive())
