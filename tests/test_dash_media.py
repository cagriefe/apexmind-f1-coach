# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) ApexMind contributors
import json
import unittest
import urllib.error
import urllib.request

from apexmind.engineer.delta import DeltaTracker
from apexmind.media import MediaController, parse_probe
from apexmind.telemetry.packets import LapData
from apexmind.webserver import LiveHub, start_server

SEP = "\x1f"


class FakeOsa:
    def __init__(self, states):
        self.states = states        # app -> raw probe output ("" = not running)
        self.commands = []

    def __call__(self, script):
        if script.startswith("if application"):
            app = script.split('"')[1]
            return self.states.get(app, "")
        self.commands.append(script)
        return ""


def raw(state, title="Song", artist="Band", vol=50):
    return SEP.join([state, title, artist, str(vol)])


class MediaTests(unittest.TestCase):
    def test_not_available_off_macos(self):
        self.assertFalse(MediaController(platform="linux").available)
        self.assertFalse(MediaController(platform="linux").command("playpause"))

    def test_parse_probe(self):
        info = parse_probe("Music", raw("playing", vol=70))
        self.assertEqual((info["player"], info["playing"], info["volume"]), ("Music", True, 70))
        self.assertIsNone(parse_probe("Music", ""))

    def test_playing_player_wins_and_gets_commands(self):
        osa = FakeOsa({"Spotify": raw("paused"), "Music": raw("playing", "Track", "Artist")})
        mc = MediaController(osa, platform="darwin")
        np = mc.now_playing()
        self.assertEqual((np["player"], np["title"], np["playing"]), ("Music", "Track", True))
        self.assertTrue(mc.command("next"))
        self.assertIn('tell application "Music" to next track', osa.commands[-1])
        self.assertTrue(mc.command("volume_up"))
        self.assertIn("+ (10)", osa.commands[-1])

    def test_unknown_action_and_no_player(self):
        mc = MediaController(FakeOsa({}), platform="darwin")
        self.assertEqual(mc.now_playing(), {"available": True, "player": None})
        self.assertFalse(mc.command("playpause"))
        self.assertFalse(mc.command("rm -rf"))


class DashServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.osa = FakeOsa({"Spotify": raw("playing", "Hi", "There")})
        cls.hub = LiveHub()
        cls.server = start_server(cls.hub, "localhost", 0, MediaController(cls.osa, platform="darwin"))
        cls.base = "ht" + f"tp://localhost:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def post(self, path, headers=None):
        req = urllib.request.Request(self.base + path, data=b"", method="POST", headers=headers or {})
        return urllib.request.urlopen(req, timeout=3)

    def test_dash_page_is_served(self):
        with urllib.request.urlopen(self.base + "/dash", timeout=3) as r:
            self.assertIn(b"ApexMind Dash", r.read())
        for asset in ("/dash.css", "/dash.js"):
            with urllib.request.urlopen(self.base + asset, timeout=3) as r:
                self.assertEqual(r.status, 200)

    def test_media_command_and_snapshot(self):
        with self.post("/api/media/playpause") as r:
            self.assertEqual(json.loads(r.read()), {"ok": True})
        self.assertIn('tell application "Spotify" to playpause', self.osa.commands[-1])
        with urllib.request.urlopen(self.base + "/api/live", timeout=3) as r:
            self.assertEqual(json.loads(r.read())["media"]["title"], "Hi")

    def test_bad_action_and_cross_site_post_are_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/media/format-disk")
        self.assertEqual(ctx.exception.code, 409)
        n = len(self.osa.commands)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/media/next", {"Origin": "https://evil.example"})
        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(len(self.osa.commands), n)


class LiveDeltaTests(unittest.TestCase):
    def test_live_delta_against_best_lap(self):
        d = DeltaTracker(lambda *_: None)
        d.best_ms = 60_000
        d.best_trace = [(float(x), x * 20) for x in range(0, 3001, 5)]   # 20 ms per metre
        lap = LapData(lap_distance=1000.0, current_lap_num=2, current_lap_time_ms=20_500)
        self.assertEqual(d.live_delta_ms(lap), 500)
        lap.current_lap_time_ms = 19_800
        self.assertEqual(d.live_delta_ms(lap), -200)
        self.assertIsNone(d.live_delta_ms(None))
        d.broken = True
        self.assertIsNone(d.live_delta_ms(lap))
