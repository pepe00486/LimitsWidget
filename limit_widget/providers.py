"""Read limits through Codex. Never read or copy its credential files."""

import json
from math import isfinite

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from . import __version__
from .models import Limit, Usage

REQUEST_TIMEOUT_SECONDS = 20


class UsageProvider(QObject):
    """Emit Usage objects or safe error messages without blocking the UI."""

    updated = Signal(object)
    failed = Signal(str)
    name = ""

    def refresh(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class CodexProvider(UsageProvider):
    name = "Codex"

    def __init__(self, executable: str = "codex", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.executable = executable
        self.process = QProcess(self)
        self.process.started.connect(self._initialize)
        self.process.readyReadStandardOutput.connect(self._read)
        # Discard stderr. It can contain private local paths or account details.
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._finished)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(REQUEST_TIMEOUT_SECONDS * 1000)
        self.timeout.timeout.connect(self._timed_out)
        self.ready = False
        self.pending: tuple[int, str] | None = None
        self.sequence = 0
        self.buffer = b""
        self.stopping = False
        self.reported_failure = False

    def refresh(self) -> None:
        if self.stopping or self.pending:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.ready = False
            self.buffer = b""
            self.reported_failure = False
            self.process.start(self.executable, ["app-server", "--listen", "stdio://"])
            self.timeout.start()
        elif self.ready:
            self._request("account/rateLimits/read")

    def _send(self, message: dict) -> None:
        self.process.write((json.dumps(message) + "\n").encode())

    def _request(self, method: str, params: dict | None = None) -> None:
        self.sequence += 1
        self.pending = (self.sequence, method)
        self._send({"id": self.sequence, "method": method, "params": params or {}})
        self.timeout.start()

    def _initialize(self) -> None:
        self._request("initialize", {"clientInfo": {
            "name": "codex_limit_widget",
            "title": "Limit Widget",
            "version": __version__,
        }})

    def _read(self) -> None:
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 2_000_000:
            self._abort("Codex returned an oversized response.")
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError
                self._message(message)
            except (ValueError, TypeError, KeyError):
                self._abort("Codex returned an invalid response. Try Refresh.")
                return

    def _message(self, message: dict) -> None:
        if "id" not in message:
            if message.get("method") == "account/rateLimits/updated":
                self._usage(message.get("params", {}))
            return
        # Refuse unsolicited server requests. This widget only reads limits.
        if "method" in message:
            self._send({"id": message["id"], "error": {
                "code": -32601, "message": "This widget only reads usage limits."
            }})
            return
        if self.pending is None or message["id"] != self.pending[0]:
            return
        _, method = self.pending
        self.pending = None
        self.timeout.stop()
        if "error" in message:
            self._abort("Cannot read Codex limits. Check your Codex login and connection.")
            return
        result = message.get("result", {})
        if not isinstance(result, dict):
            raise ValueError
        if method == "initialize":
            self._send({"method": "initialized", "params": {}})
            self._request("account/read", {"refreshToken": False})
        elif method == "account/read":
            account = result.get("account")
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                self._abort("Use your ChatGPT login in Codex first: codex login")
                return
            self.ready = True
            self._request("account/rateLimits/read")
        elif method == "account/rateLimits/read":
            self._usage(result)

    def _usage(self, result: dict) -> None:
        try:
            usage = parse_codex_usage(result)
        except ValueError as error:
            self.failed.emit(str(error))
        else:
            self.updated.emit(usage)

    def _reset(self) -> None:
        self.timeout.stop()
        self.pending = None
        self.ready = False

    def _abort(self, message: str) -> None:
        self._reset()
        self.reported_failure = True
        self.failed.emit(message)
        self.process.kill()

    def _timed_out(self) -> None:
        self._abort(f"Codex did not respond within {REQUEST_TIMEOUT_SECONDS} seconds. Try Refresh.")

    def _process_error(self, error):
        if self.stopping or self.reported_failure:
            return
        self._abort("Cannot start Codex. Check that the codex command is installed.")

    def _finished(self, *_):
        self._reset()
        if not self.stopping and not self.reported_failure:
            self.failed.emit("Codex stopped. The widget will retry on the next refresh.")

    def close(self) -> None:
        if self.stopping:
            return
        self.stopping = True
        self._reset()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.process.terminate()
        if not self.process.waitForFinished(1000):
            self.process.kill()
            self.process.waitForFinished(1000)


def parse_codex_usage(result: dict) -> Usage:
    """Select the Codex bucket and identify windows by their duration."""
    if not isinstance(result, dict):
        raise ValueError("Codex returned invalid limit data.")
    buckets = result.get("rateLimitsByLimitId")
    if isinstance(buckets, dict) and buckets:
        bucket = buckets.get("codex")
    else:
        bucket = result.get("rateLimits")
    if not isinstance(bucket, dict) or bucket.get("limitId") not in (None, "codex"):
        raise ValueError("Codex limits are unavailable for this account.")
    windows = {}
    for key in ("primary", "secondary"):
        raw = bucket.get(key)
        if not isinstance(raw, dict):
            continue
        duration = raw.get("windowDurationMins")
        if duration not in (300, 10080):
            continue
        used = raw.get("usedPercent")
        if isinstance(used, bool) or not isinstance(used, (int, float)) or not isfinite(used):
            raise ValueError("Codex returned an invalid usage value.")
        reset = raw.get("resetsAt")
        if reset is not None and (isinstance(reset, bool) or not isinstance(reset, int)):
            raise ValueError("Codex returned an invalid reset time.")
        windows[duration] = Limit(used, reset)
    if not windows:
        raise ValueError("Codex did not return 5-hour or weekly limits.")
    return Usage(windows.get(300), windows.get(10080))
