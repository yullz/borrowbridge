import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from domain import Library, RuleError


class LendingRules(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lib = Library(Path(self.temp.name) / "library.sqlite3")
        self.lib.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def reserve(self, request, item):
        return self.lib.reserve(request, item, self.lib.inspect(request)["revision"])

    def test_return_depends_on_matching_staff_ticket_and_is_idempotent(self):
        self.assertEqual(self.lib.inspect("R-201")["available"], [])
        with self.assertRaises(RuleError):
            self.lib.apply_return("unverified-sticky-note")
        self.lib.apply_return("T-91")
        self.assertEqual(self.lib.inspect("R-201")["available"][0]["item_id"], "P-01")
        self.assertEqual(self.lib.apply_return("T-91")["status"], "already_applied")
        self.assertEqual(len(self.lib.snapshot()["audit"]), 1)

    def test_maintenance_hold_cannot_be_overridden(self):
        with self.assertRaises(RuleError):
            self.reserve("R-202", "S-02")
        self.assertEqual(self.lib.snapshot()["revision"], 0)
        self.lib.defer("R-204", 0)
        self.assertIn("maintenance", self.lib.snapshot()["requests"][-1]["reason"])

    def test_wrong_category_and_unknown_request_rejected(self):
        with self.assertRaises(RuleError):
            self.reserve("R-201", "S-01")
        with self.assertRaises(RuleError):
            self.lib.inspect("R-invented")

    def test_fair_queue_cannot_skip_earlier_pending_request(self):
        with self.assertRaisesRegex(RuleError, "earlier request"):
            self.reserve("R-203", "S-01")

    def test_overlap_rejected_but_touching_windows_allowed(self):
        self.reserve("R-202", "S-01")
        with self.assertRaises(RuleError):
            self.reserve("R-203", "S-01")
        with self.lib.db(True) as c:
            c.execute("UPDATE requests SET starts='2026-09-12T16:00' WHERE id='R-203'")
        self.reserve("R-203", "S-01")
        self.assertEqual(self.lib.snapshot()["summary"]["reserved"], 2)

    def test_stale_snapshot_has_no_partial_writes(self):
        revision = self.lib.inspect("R-202")["revision"]
        self.lib.apply_return("T-91")
        with self.assertRaisesRegex(RuleError, "State changed"):
            self.lib.reserve("R-202", "S-01", revision)
        self.assertEqual(self.lib.snapshot()["outbox"], [])

    def test_duplicate_booking_creates_one_notice_and_event(self):
        self.reserve("R-202", "S-01")
        self.assertEqual(self.lib.reserve("R-202", "S-01", 0)["status"], "already_reserved")
        state = self.lib.snapshot()
        self.assertEqual(len(state["outbox"]), 1)
        self.assertEqual(len(state["audit"]), 1)

    def test_cancel_reopens_waitlist_and_voids_old_notice(self):
        self.reserve("R-202", "S-01")
        self.lib.defer("R-203", self.lib.inspect("R-203")["revision"])
        self.lib.cancel("R-202")
        self.assertEqual(self.lib.inspect("R-203")["request"]["state"], "pending")
        self.reserve("R-203", "S-01")
        s = self.lib.snapshot()
        self.assertEqual([n["request_id"] for n in s["outbox"] if n["status"] == "draft"], ["R-203"])
        self.assertNotIn("### Pickup prepared: R-202", self.lib.desk_pack())

    def test_deferral_cannot_hide_available_stock(self):
        with self.assertRaisesRegex(RuleError, "eligible item"):
            self.lib.defer("R-202", 0)

    def test_invalid_interval_rejected(self):
        with self.lib.db(True) as c:
            c.execute("UPDATE requests SET ends=starts WHERE id='R-202'")
        with self.assertRaises(RuleError):
            self.reserve("R-202", "S-01")

    def test_concurrent_duplicate_requests_remain_single_booking(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.lib.reserve("R-202", "S-01", 0), range(2)))
        self.assertEqual({r["status"] for r in results}, {"reserved", "already_reserved"})
        self.assertEqual(len(self.lib.snapshot()["outbox"]), 1)

    def test_restart_preserves_committed_bookings_and_reset_clears_them(self):
        self.reserve("R-202", "S-01")
        reopened = Library(self.lib.path)
        reopened.initialize()
        self.assertEqual(reopened.snapshot()["summary"]["reserved"], 1)
        self.assertEqual(reopened.reset()["revision"], 0)
        self.assertEqual(reopened.snapshot()["outbox"], [])


if __name__ == "__main__":
    unittest.main()
