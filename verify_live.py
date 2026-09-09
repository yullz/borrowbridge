"""Opt-in integration check against the real local model; never a mocked agent."""
import json
from pathlib import Path

from domain import Library
from worker import run_shift

root = Path("private/live-check")
library = Library(root / "library.sqlite3")
library.initialize()
library.reset()
reports = []
for phase in ("initial", "repeat", "cancellation"):
    before = library.snapshot()
    if phase == "cancellation":
        library.cancel("R-202")
    result = run_shift(library, root / phase)
    assert result["status"] == "complete", f"{phase}: {result.get('error', result['status'])}"
    current = library.snapshot()
    rows = {r["id"]: r for r in current["requests"]}
    assert rows["R-201"]["item_id"] == "P-01"
    assert rows["R-204"]["state"] == "attention"
    assert all(i["status"] == "maintenance" for i in current["items"] if i["id"] in ("S-02", "L-01"))
    if phase in ("initial", "repeat"):
        assert rows["R-202"]["item_id"] == "S-01"
        assert rows["R-203"]["state"] == "attention"
        assert len(current["outbox"]) == 2
    if phase == "repeat":
        assert current["revision"] == before["revision"], "Repeat run changed already resolved records"
        assert current["audit"] == before["audit"]
    if phase == "cancellation":
        assert rows["R-202"]["state"] == "cancelled"
        assert rows["R-203"]["item_id"] == "S-01"
        assert [n["request_id"] for n in current["outbox"] if n["status"] == "draft"] == ["R-201", "R-203"]
    assert (root / phase / "desk-pack.md").read_text(encoding="utf-8") == library.desk_pack()
    reports.append({"phase": phase, "status": "passed", "seconds": result["seconds"],
                    "tool_calls": result["tool_calls"], "rejected_actions": sum(e["status"] == "rejected" for e in result["trace"]),
                    "revision": current["revision"], "summary": current["summary"]})
    print(json.dumps(reports[-1]), flush=True)
(root / "verification.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
