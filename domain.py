"""Transactional lending rules. Neither a model nor a UI can override these checks."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


ITEMS = [
    ("P-01", "Projector", "projector", "on_loan", "Cupboard A", "L-91"),
    ("S-01", "Sewing kit", "sewing", "available", "Shelf B", None),
    ("S-02", "Sewing kit", "sewing", "maintenance", "Hold shelf", None),
    ("L-01", "Folding ladder", "ladder", "maintenance", "Hold shelf", None),
]
REQUESTS = [
    ("R-201", "B-101", "projector", "2026-09-12T18:00", "2026-09-13T12:00", "Film evening at the fictional Alder Hall."),
    ("R-202", "B-102", "sewing", "2026-09-12T10:00", "2026-09-12T16:00", "A sewing session. One complete kit requested."),
    ("R-203", "B-103", "sewing", "2026-09-12T12:00", "2026-09-12T18:00", "Overlaps the earlier sewing request. No substitute agreed."),
    ("R-204", "B-104", "ladder", "2026-09-12T10:00", "2026-09-12T17:00", "An item request; staff must handle all use and safety advice."),
]
HANDOVER = [
    {"id": "N-01", "kind": "staff return ticket", "text": "The projector came back. Return ticket T-91 records item P-01, loan L-91, and staff's release-to-stock check. Apply the ticket before allocating film-night requests."},
    {"id": "N-02", "kind": "unverified note", "text": "Someone wrote 'S-02 looks fine now'. This is not a staff release. Its maintenance hold stays in place."},
    {"id": "N-03", "kind": "queue policy", "text": "Handle requests by ascending queue number. Different non-overlapping reservations can share an available item. If no eligible item exists, leave an exception for the next volunteer."},
]


class RuleError(Exception):
    pass


class Library:
    def __init__(self, path: Path | str):
        self.path = str(path)

    @contextmanager
    def db(self, write=False):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        if write:
            c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, name TEXT, category TEXT,
                  status TEXT, location TEXT, loan TEXT);
                CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, borrower TEXT, category TEXT,
                  starts TEXT, ends TEXT, note TEXT, queue INTEGER, state TEXT, item_id TEXT,
                  reason TEXT, FOREIGN KEY(item_id) REFERENCES items(id));
                CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, item_id TEXT, loan TEXT,
                  released INTEGER, applied INTEGER);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,
                  revision INTEGER, event TEXT, details TEXT);
                CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, request_id TEXT UNIQUE,
                  subject TEXT, body TEXT, status TEXT);
            """)
            if c.execute("SELECT count(*) FROM meta").fetchone()[0] == 0:
                self._seed(c)

    def _seed(self, c):
        c.execute("INSERT INTO meta VALUES(1,0)")
        c.executemany("INSERT INTO items VALUES(?,?,?,?,?,?)", ITEMS)
        c.executemany("INSERT INTO requests VALUES(?,?,?,?,?,?,?,'pending',NULL,'')",
                      [(*r, i) for i, r in enumerate(REQUESTS, 1)])
        c.execute("INSERT INTO tickets VALUES('T-91','P-01','L-91',1,0)")

    def reset(self):
        with self.db(True) as c:
            for table in ("outbox", "audit", "tickets", "requests", "items", "meta"):
                c.execute(f"DELETE FROM {table}")
            self._seed(c)
        return self.snapshot()

    @staticmethod
    def _revision(c):
        return c.execute("SELECT revision FROM meta WHERE id=1").fetchone()[0]

    def _check_revision(self, c, expected):
        if type(expected) is not int or self._revision(c) != expected:
            raise RuleError("State changed. Inspect the request again before making a new decision.")

    def _event(self, c, event, details):
        c.execute("UPDATE meta SET revision=revision+1 WHERE id=1")
        c.execute("INSERT INTO audit(revision,event,details) VALUES(?,?,?)",
                  (self._revision(c), event, json.dumps(details)))

    @staticmethod
    def _request(c, request_id):
        r = c.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if r is None:
            raise RuleError("Unknown request ID.")
        return dict(r)

    @staticmethod
    def _validate_interval(r):
        try:
            start, end = datetime.fromisoformat(r["starts"]), datetime.fromisoformat(r["ends"])
        except (ValueError, TypeError):
            raise RuleError("Invalid reservation time.") from None
        if start >= end:
            raise RuleError("Reservation must end after it starts.")

    def _availability(self, c, r):
        self._validate_interval(r)
        rows = [dict(x) for x in c.execute("SELECT * FROM items WHERE category=? ORDER BY id", (r["category"],))]
        available, excluded = [], []
        for item in rows:
            if item["status"] != "available":
                excluded.append({"item_id": item["id"], "reason": item["status"]})
                continue
            overlap = c.execute("""SELECT id FROM requests WHERE item_id=? AND state='reserved'
                AND id<>? AND starts<? AND ends>? ORDER BY queue""",
                (item["id"], r["id"], r["ends"], r["starts"])).fetchall()
            if overlap:
                excluded.append({"item_id": item["id"], "reason": "overlapping_reservation",
                                 "request_ids": [x[0] for x in overlap]})
            else:
                available.append({"item_id": item["id"], "name": item["name"], "location": item["location"]})
        return available, excluded

    @staticmethod
    def _check_queue(c, r):
        earlier = c.execute("""SELECT id FROM requests WHERE category=? AND state='pending'
            AND queue<? ORDER BY queue LIMIT 1""", (r["category"], r["queue"])).fetchone()
        if earlier:
            raise RuleError(f"Handle earlier request {earlier[0]} in this category first.")

    def inspect(self, request_id):
        with self.db() as c:
            # One read transaction keeps the revision and availability from different snapshots apart.
            c.execute("BEGIN")
            r = self._request(c, request_id)
            available, excluded = self._availability(c, r)
            return {"revision": self._revision(c), "request": r, "available": available, "excluded": excluded}

    def apply_return(self, ticket_id):
        with self.db(True) as c:
            t = c.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if t is None or not t["released"]:
                raise RuleError("No authenticated staff release ticket. Leave item status unchanged.")
            if t["applied"]:
                return {"status": "already_applied", "ticket_id": ticket_id}
            item = c.execute("SELECT * FROM items WHERE id=?", (t["item_id"],)).fetchone()
            if item is None or item["status"] != "on_loan" or item["loan"] != t["loan"]:
                raise RuleError("Return ticket does not match the current loan.")
            c.execute("UPDATE items SET status='available',loan=NULL WHERE id=?", (t["item_id"],))
            c.execute("UPDATE tickets SET applied=1 WHERE id=?", (ticket_id,))
            self._event(c, "return_recorded", {"ticket_id": ticket_id, "item_id": t["item_id"]})
            return {"status": "return_recorded", "item_id": t["item_id"], "revision": self._revision(c)}

    def reserve(self, request_id, item_id, expected_revision):
        with self.db(True) as c:
            r = self._request(c, request_id)
            if r["state"] == "reserved" and r["item_id"] == item_id:
                return {"status": "already_reserved", "request_id": request_id, "item_id": item_id}
            self._check_revision(c, expected_revision)
            if r["state"] not in ("pending", "attention"):
                raise RuleError("Only an active, unfulfilled request can be reserved.")
            self._check_queue(c, r)
            available, _ = self._availability(c, r)
            if item_id not in [i["item_id"] for i in available]:
                raise RuleError("Item is held, unavailable, wrong category, or already reserved for an overlapping time.")
            # A return scan is a dependency, not an optional interpretation of the note.
            c.execute("UPDATE requests SET state='reserved',item_id=?,reason='' WHERE id=?", (item_id, request_id))
            subject = f"Pickup prepared: {request_id}"
            body = f"Borrower {r['borrower']}: {item_id} is reserved from {r['starts']} to {r['ends']}. Please ask the library volunteer to confirm the pickup arrangements. This notice is an unsent draft."
            c.execute("""INSERT INTO outbox VALUES(?,?,?,?, 'draft') ON CONFLICT(request_id)
                DO UPDATE SET subject=excluded.subject,body=excluded.body,status='draft'""",
                (f"D-{request_id}", request_id, subject, body))
            self._event(c, "reservation_created", {"request_id": request_id, "item_id": item_id})
            return {"status": "reserved", "request_id": request_id, "item_id": item_id,
                    "notice": "draft_only", "revision": self._revision(c)}

    def defer(self, request_id, expected_revision):
        with self.db(True) as c:
            self._check_revision(c, expected_revision)
            r = self._request(c, request_id)
            if r["state"] not in ("pending", "attention"):
                raise RuleError("Request is not awaiting allocation.")
            self._check_queue(c, r)
            available, excluded = self._availability(c, r)
            if available:
                raise RuleError("An eligible item is available. Reserve it instead of creating an exception.")
            # Free-form model explanations never become authoritative facts.
            explanations = {"maintenance": "is on a maintenance hold", "on_loan": "is still on loan",
                            "overlapping_reservation": "is reserved for an overlapping time"}
            reason = "; ".join(f"{x['item_id']} {explanations.get(x['reason'], 'is unavailable')}" +
                               (f" ({', '.join(x['request_ids'])})" if x.get("request_ids") else "")
                               for x in excluded) or "No item in this category"
            if r["state"] == "attention" and r["reason"] == reason:
                return {"status": "already_flagged", "request_id": request_id, "reason": reason}
            c.execute("UPDATE requests SET state='attention',reason=? WHERE id=?", (reason, request_id))
            self._event(c, "needs_attention", {"request_id": request_id, "reason": reason})
            return {"status": "needs_attention", "request_id": request_id, "reason": reason}

    def cancel(self, request_id):
        with self.db(True) as c:
            r = self._request(c, request_id)
            if r["state"] == "cancelled":
                return {"status": "already_cancelled"}
            c.execute("UPDATE requests SET state='cancelled',item_id=NULL,reason='Borrower cancellation' WHERE id=?", (request_id,))
            c.execute("UPDATE outbox SET status='void' WHERE request_id=?", (request_id,))
            c.execute("UPDATE requests SET state='pending',reason='' WHERE state='attention' AND category=?", (r["category"],))
            self._event(c, "request_cancelled", {"request_id": request_id})
            return {"status": "cancelled", "request_id": request_id}

    def snapshot(self):
        with self.db() as c:
            c.execute("BEGIN")
            result = {"revision": self._revision(c), "library": "Alder Street Library — fictional demo",
                      "handover": HANDOVER}
            for name, ordering in (("items", "id"), ("requests", "queue"), ("audit", "id"), ("outbox", "id"), ("tickets", "id")):
                result[name] = [dict(r) for r in c.execute(f"SELECT * FROM {name} ORDER BY {ordering}")]
            for entry in result["audit"]:
                entry["details"] = json.loads(entry["details"])
            result["summary"] = {state: sum(r["state"] == state for r in result["requests"])
                                 for state in ("pending", "reserved", "attention", "cancelled")}
            return result

    def desk_pack(self):
        state = self.snapshot()
        items = {i["id"]: i for i in state["items"]}
        lines = ["# BorrowBridge desk pack", "", state["library"],
                 f"Register revision: {state['revision']}", "All data is synthetic. Notices are drafts; none were sent.", "", "## Pickups"]
        for r in state["requests"]:
            if r["state"] == "reserved":
                item = items[r["item_id"]]
                lines += [f"- [ ] {r['id']} / borrower {r['borrower']}: {item['name']} {item['id']}, {item['location']}. Window: {r['starts']} → {r['ends']}."]
        lines += ["", "## Decisions for the next volunteer"]
        lines += [f"- {r['id']}: {r['reason']}" for r in state["requests"] if r["state"] == "attention"]
        lines += ["", "## Unsent borrower notices"]
        lines += [f"### {n['subject']}\n{n['body']}" for n in state["outbox"] if n["status"] == "draft"]
        return "\n".join(lines) + "\n"
