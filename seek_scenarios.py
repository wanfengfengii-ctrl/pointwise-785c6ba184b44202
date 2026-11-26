import unittest

from tests.test_http import HttpCase, sample, scenario, single_edition


class SeekScenarios(HttpCase):
    def seek(self, show_id, position, target_tick, status=200):
        result = self.call("seek", {
            "show_id": show_id, "target_tick": target_tick, "position": position,
        }, status)
        if status == 200:
            observed = tuple(result[key] for key in ("show_id", "next_tick", "position"))
            self.assertEqual(observed, (show_id, target_tick, position + 1))
        return result

    def step(self, show_id, position, tick):
        return self.call("advance", {"show_id": show_id, "position": position, "tick": tick})

    def test_rewind_and_close_after_restart(self):
        programme = sample("seek")
        show_id = self.mount_and_start(self.issue(self.submit(programme)))
        self.advance(show_id, 0)
        before = self.read_show(show_id)
        self.seek(show_id, 1, 0, 409)
        self.assertEqual(self.read_show(show_id), before)
        self.advance(show_id, 1)
        self.seek(show_id, 2, 0)
        self.restart_server()
        resumed = self.read_show(show_id)
        self.assertEqual(resumed["show"]["position"], 3)
        for extra in ({}, {"position": 0}):
            self.call("advance", {"show_id": show_id, "tick": 0, **extra}, 409)
        self.seek(show_id, 2, 1, 409)
        self.assertEqual(self.read_show(show_id), resumed)
        transfer = self.call("handover", {"booth": "main", "show_id": show_id, "operator": "Zhou"})
        self.assertEqual(transfer["show"]["position"], 3)
        self.assertEqual(transfer["intervals"], resumed["intervals"])
        first = self.step(show_id, 3, 0)
        self.assertEqual(first["action"], {"kind": "start", "segment_id": "B"})
        before_close = self.read_show(show_id)
        self.assertIsNone(before_close["intervals"][-1]["end_position"])
        self.call("close", {"show_id": show_id}, 409)
        self.assertEqual(self.read_show(show_id), before_close)
        self.assertEqual(self.step(show_id, 4, 1)["ended_segment"], "B")
        self.seek(show_id, 5, 1)
        expected = {
            "seeks": [
                {"position": 2, "from_tick": 2, "target_tick": 0},
                {"position": 5, "from_tick": 2, "target_tick": 1},
            ],
            "intervals": [
                {"segment_id": name, "start_tick": 0, "end_tick": 2,
                 "start_position": start, "end_position": end}
                for name, start, end in [("A", 0, 2), ("B", 3, 5)]
            ],
        }
        summary = self.finish(show_id)
        self.assertEqual(summary["closed_at_tick"], 1)
        self.restart_server()
        stored = self.call("read", {"closeout_id": summary["closeout_id"]})
        self.assertEqual(stored, self.read_show(show_id))
        self.assertEqual(stored["closeout"], summary)
        self.assertEqual(self.finish(show_id), summary)
        observed = {key: stored[key] for key in expected}
        self.assertEqual(observed, expected)
        self.assertEqual({key: summary[key] for key in expected}, expected)
        scenario(
            "seek_same_film_span", {"programme": programme, "targets": [0, 1]},
            {"position": 3}, {"position": resumed["show"]["position"]}, expected, observed,
            ["booth/application.py", "show/clock.py", "record/ledger.py", "record/closeout.py"],
            "两段共用影片 [0,2)，现场实播分别占 [0,2) 和 [3,5)，两次定位各占一个序位。",
        )

    def test_confirmed_cut_rejects_unfinishable_seek(self):
        programme = sample("branching")
        next(edition for edition in programme["editions"] if edition["edition_id"] == "beta")["length"] = 6
        show_id = self.mount_and_start(self.issue(self.submit(programme)))
        initial = self.read_show(show_id)
        self.seek(show_id, 0, 1, 409)
        self.assertEqual(self.read_show(show_id), initial)
        for tick, signal in [(0, None), (1, None), (2, "beta")]:
            self.advance(show_id, tick, signal)
        before = self.read_show(show_id)
        self.seek(show_id, 3, 5, 409)
        self.assertEqual(self.read_show(show_id), before)
        self.seek(show_id, 3, 2)
        for position, tick in [(4, 2), (5, 3)]:
            self.assertEqual(self.step(show_id, position, tick)["action"]["kind"], "wait")
        self.assertEqual(self.step(show_id, 6, 4)["ended_segment"], "B")
        summary = self.finish(show_id)
        self.assertEqual((summary["edition_id"], summary["signal"]), ("beta", "beta"))
        self.assertEqual([(row["start_tick"], row["end_tick"]) for row in summary["intervals"]],
                         [(0, 2), (4, 5)])

    def test_forward_seek_replans_an_issued_start(self):
        programme = single_edition(sample("branching"), "alpha")
        programme["editions"][0]["sound_windows"] = [[2, 3]]
        programme["segments"][1]["deadlines"]["alpha"] = 5
        show_id = self.mount_and_start(self.issue(self.submit(programme)))
        for tick in (0, 1):
            self.advance(show_id, tick)
        self.seek(show_id, 2, 4)
        self.assertEqual(self.step(show_id, 3, 4)["ended_segment"], "B")
        summary = self.finish(show_id)
        self.assertEqual([(row["start_tick"], row["end_tick"]) for row in summary["intervals"]],
                         [(0, 2), (4, 5)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
