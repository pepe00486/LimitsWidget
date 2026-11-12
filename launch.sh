#!/bin/sh
# Start the local source with this project's Python environment.
set -eu

widget_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
widget_python="$widget_dir/.venv/bin/python"

show_error() {
    printf '%s\n' "$1" >&2
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="Limit Widget" --text="$1" || true
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send "Limit Widget" "$1" || true
    fi
}

desktop_launch=false
if [ "${1:-}" = "--desktop" ]; then
    desktop_launch=true
    shift
fi

if [ ! -x "$widget_python" ]; then
    show_error "Install the widget first. See $widget_dir/README.md."
    exit 1
fi

# Desktop launchers can have a smaller PATH than a terminal session.
PATH="${HOME}/.local/bin:${PATH:-/usr/local/bin:/usr/bin:/bin}"
export PATH
cd "$widget_dir"
if [ "$desktop_launch" = true ]; then
    umask 077
    log_file="$widget_dir/launcher.log"
    if "$widget_python" -m limit_widget "$@" >"$log_file" 2>&1; then
        exit 0
    else
        launch_status=$?
        show_error "The widget could not start. See $log_file for details."
        exit "$launch_status"
    fi
fi
exec "$widget_python" -m limit_widget "$@"
