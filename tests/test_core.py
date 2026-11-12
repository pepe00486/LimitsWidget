"""Check quota parsing and Linux display selection."""

import unittest

from limit_widget.models import Limit
from limit_widget.providers import parse_codex_usage
from limit_widget.app import configure_display


def window(used=25, minutes=300, reset=1900000000):
    """Build a server quota window for parser tests."""
    return {"usedPercent": used, "windowDurationMins": minutes, "resetsAt": reset}


class UsageTests(unittest.TestCase):
    """Check quota values, durations, and invalid responses."""

    def test_legacy_response(self):
        """Read both limits from a legacy response."""
        usage = parse_codex_usage({"rateLimits": {
            "primary": window(), "secondary": window(60, 10080)
        }})
        self.assertEqual(usage.five_hour.remaining, 75)
        self.assertEqual(usage.weekly.remaining, 40)
        self.assertEqual(usage.five_hour.resets_at, 1900000000)

    def test_select_codex_instead_of_other_model_bucket(self):
        """Select the Codex bucket when other buckets are present."""
        usage = parse_codex_usage({"rateLimitsByLimitId": {
            "codex_other": {"primary": window(99)},
            "codex": {"primary": window(12)}
        }})
        self.assertEqual(usage.five_hour.remaining, 88)
        self.assertIsNone(usage.weekly)

    def test_identify_windows_by_duration_not_position(self):
        """Identify windows by duration when their positions are reversed."""
        usage = parse_codex_usage({"rateLimits": {
            "primary": window(30, 10080), "secondary": window(70)
        }})
        self.assertEqual(usage.five_hour.remaining, 30)
        self.assertEqual(usage.weekly.remaining, 70)

    def test_do_not_mislabel_other_duration(self):
        """Reject windows with an unrelated duration."""
        with self.assertRaises(ValueError):
            parse_codex_usage({"rateLimits": {"primary": window(25, 15)}})

    def test_do_not_use_another_bucket_as_codex(self):
        """Reject responses that omit the Codex bucket."""
        with self.assertRaises(ValueError):
            parse_codex_usage({"rateLimitsByLimitId": {
                "codex_other": {"primary": window()}
            }, "rateLimits": {"primary": window()}})

    def test_invalid_percent_is_rejected(self):
        """Reject invalid percentage values."""
        for value in (True, "20", None, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_codex_usage({"rateLimits": {"primary": window(value)}})

    def test_invalid_reset_is_rejected(self):
        """Reject invalid reset timestamps."""
        with self.assertRaises(ValueError):
            parse_codex_usage({"rateLimits": {"primary": window(reset="tomorrow")}})

    def test_missing_reset_is_allowed(self):
        """Allow a limit without a reset timestamp."""
        usage = parse_codex_usage({"rateLimits": {"primary": window(reset=None)}})
        self.assertIsNone(usage.five_hour.resets_at)

    def test_remaining_is_bounded(self):
        """Keep the remaining percentage between zero and 100."""
        self.assertEqual(Limit(-10).remaining, 100)
        self.assertEqual(Limit(110).remaining, 0)

    def test_empty_response_is_unavailable(self):
        """Reject an empty response."""
        with self.assertRaises(ValueError):
            parse_codex_usage({})


class DisplayTests(unittest.TestCase):
    """Check backend selection and explicit overrides."""

    def test_wayland_with_xwayland_selects_xcb(self):
        """Select XCB when XWayland is available."""
        env = {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}
        configure_display(env, xcb_available=True)
        self.assertEqual(env["QT_QPA_PLATFORM"], "xcb")

    def test_wayland_display_without_session_type_selects_xcb(self):
        """Detect Wayland from its display variable."""
        env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
        configure_display(env, xcb_available=True)
        self.assertEqual(env["QT_QPA_PLATFORM"], "xcb")

    def test_wayland_without_xwayland_keeps_default(self):
        """Keep the default backend when XWayland is unavailable."""
        env = {"XDG_SESSION_TYPE": "wayland"}
        configure_display(env, xcb_available=True)
        self.assertNotIn("QT_QPA_PLATFORM", env)

    def test_explicit_backend_is_preserved(self):
        """Preserve an explicit backend selection."""
        for backend in ("wayland", "offscreen", "xcb"):
            env = {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0",
                   "QT_QPA_PLATFORM": backend}
            configure_display(env, xcb_available=True)
            self.assertEqual(env["QT_QPA_PLATFORM"], backend)

    def test_x11_keeps_default(self):
        """Keep the default backend in an X11 session."""
        env = {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
        configure_display(env, xcb_available=True)
        self.assertNotIn("QT_QPA_PLATFORM", env)

    def test_missing_xcb_libraries_keep_default(self):
        """Keep the default backend when XCB libraries are missing."""
        env = {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}
        configure_display(env, xcb_available=False)
        self.assertNotIn("QT_QPA_PLATFORM", env)
