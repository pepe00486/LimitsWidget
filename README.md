# Limit Widget

A small Linux window that shows your remaining Codex 5-hour and weekly limits.
It has a transparent background and refreshes every 30 seconds.

## Setup

Use Python 3.11 or later with `pip` and `venv`. Install Codex CLI and sign in
with your ChatGPT account under the same Linux user.

```bash
cd LimitsWidget
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./launch.sh
```

The editable installation uses the local source after each restart.
Run `./launch.sh --demo` to preview the window without a Codex connection.
Run `./launch.sh --interval 60` to refresh every 60 seconds.
Use `./launch.sh --codex /path/to/codex` to select the Codex executable.
The minimum refresh period is 15 seconds.

## Desktop starter

After setup, run this command from the repository directory:

```bash
python3 install-launcher.py
```

The installer creates `LimitWidget.desktop` on your desktop and in your user
application directory. Double-click **Codex Limit Widget** on your desktop
to start the widget. You can also select it from the application menu.
The starter uses `.venv` and opens the widget without a terminal.

If the shortcut opens as text, right-click the desktop shortcut and select
**Allow Launching** or **Trust and Launch**, if available. Some file managers
open `.desktop` files as text inside project folders. Use the installed desktop
shortcut or application menu entry.

The shortcuts contain an absolute path to `launch.sh`. If you move or rename
the repository, repeat setup and run `python3 install-launcher.py` again.
Recreate `.venv` if its installed commands still use the old path.

If the widget does not start, check `launcher.log` in the repository directory.
Run `./launch.sh` from a terminal to see errors directly.

## Controls

- Drag the window to move it. Its position is saved on exit.
- Click **×** or press `Ctrl+Q` to close it.
- Right-click to refresh or change **Always on top**.
- Hover over the window to see reset times, errors, and the refresh countdown.

A dash means no value is available. Yellow text with an asterisk marks old
values after an error. A request times out after 20 seconds. The next scheduled
refresh retries the connection. Server percentages can stay the same between updates.

## Linux display support

On Wayland, the widget uses XWayland when an X display and the Qt X11 libraries
are available. This supports **Always on top**. An explicit `QT_QPA_PLATFORM`
setting takes priority. Without XWayland, your compositor controls stacking and
can ignore the request. X11 transparency needs a compositing window manager.

For missing XCB libraries, see [Qt's Linux requirements](https://doc.qt.io/qt-6/linux-requirements.html).
For example, Ubuntu uses these runtime packages:

```bash
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0
```

## Development

`limit_widget/` is a flat package:

- `app.py`: window, timers, and display setup.
- `models.py`: shared limit data.
- `providers.py`: provider interface, Codex connection, and response parser.

Codex manages its existing login through its local app server. The widget
inherits `CODEX_HOME` and does not read or copy credentials. API-key login does
not provide ChatGPT plan limits. No model requests are sent.
See the [official protocol documentation](https://developers.openai.com/codex/app-server).

To add Claude, implement `UsageProvider.refresh()` and `close()` in `providers.py`.
Emit `Usage` through `updated` and safe messages through `failed`. Keep I/O
asynchronous. Add provider selection in `app.py` when the implementation exists.

Use four spaces, `snake_case` functions, and `PascalCase` classes.
Tests use a local fake server and an offscreen Qt display. They need the installed
dependencies but no network access or credentials.

```bash
.venv/bin/python -m unittest discover -s tests -v
```
