# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) ApexMind contributors
"""Now-playing info and transport controls for the music player on the computer running ApexMind.

macOS only (Music.app and Spotify, through ``osascript``); elsewhere ``available`` stays False and
the dashboard hides the music card. This controls the *computer's* player, never the phone that
shows the dashboard: a web page cannot reach the phone's own music app.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from collections.abc import Callable

PLAYERS = ("Spotify", "Music")
ACTIONS = ("playpause", "next", "previous", "volume_up", "volume_down")
VOLUME_STEP = 10
_SEP = "\x1f"

Runner = Callable[[str], str]


def _osascript(script: str) -> str:
    out = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=3, check=True
    )
    return out.stdout.strip()


def _probe_script(app: str) -> str:
    return (
        f'if application "{app}" is running then\n'
        f'  tell application "{app}"\n'
        "    set st to player state as text\n"
        '    set nm to ""\n    set ar to ""\n'
        "    try\n      set nm to name of current track\n      set ar to artist of current track\n    end try\n"
        f'    return st & "{_SEP}" & nm & "{_SEP}" & ar & "{_SEP}" & (sound volume as text)\n'
        "  end tell\n"
        'end if\nreturn ""'
    )


def _command_script(app: str, action: str) -> str:
    verb = {"playpause": "playpause", "next": "next track", "previous": "previous track"}.get(action)
    if verb:
        return f'tell application "{app}" to {verb}'
    delta = VOLUME_STEP if action == "volume_up" else -VOLUME_STEP
    return (
        f'tell application "{app}"\n'
        f"  set v to (sound volume) + ({delta})\n"
        "  if v > 100 then set v to 100\n  if v < 0 then set v to 0\n"
        "  set sound volume to v\nend tell"
    )


def parse_probe(app: str, raw: str) -> dict | None:
    parts = raw.split(_SEP)
    if len(parts) != 4:
        return None
    state, title, artist, volume = parts
    try:
        vol = int(float(volume))
    except ValueError:
        vol = None
    return {
        "player": app, "playing": state.strip() == "playing", "state": state.strip(),
        "title": title, "artist": artist, "volume": vol,
    }


class MediaController:
    def __init__(self, runner: Runner | None = None, platform: str | None = None) -> None:
        self._run = runner or _osascript
        plat = platform or sys.platform
        self.available = plat == "darwin" and (runner is not None or shutil.which("osascript") is not None)
        self._active: str | None = None
        self._lock = threading.Lock()

    def now_playing(self) -> dict:
        """The player that is playing, else a paused one, else ``{"player": None}``."""
        if not self.available:
            return {"available": False, "player": None}
        found: list[dict] = []
        for app in PLAYERS:
            try:
                info = parse_probe(app, self._run(_probe_script(app)))
            except (OSError, subprocess.SubprocessError):
                info = None
            if info is not None:
                found.append(info)
        found.sort(key=lambda i: not i["playing"])      # stable: playing players first
        best = found[0] if found else None
        with self._lock:
            self._active = best["player"] if best else None
        return {"available": True, **best} if best else {"available": True, "player": None}

    def command(self, action: str) -> bool:
        """Run a transport command on the active player. False when nothing could be done."""
        if action not in ACTIONS or not self.available:
            return False
        with self._lock:
            app = self._active
        if app is None:
            app = (self.now_playing() or {}).get("player")
        if app is None:
            return False
        try:
            self._run(_command_script(app, action))
        except (OSError, subprocess.SubprocessError):
            return False
        return True
