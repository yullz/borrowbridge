# BorrowBridge

A local Strands agent that prepares the next shift at a community lending library: record a verified return, reserve eligible items, flag unresolved requests and produce a volunteer's desk pack.

**Working prototype with fictional records.** No real borrowers, library partnership or measured staff-time savings are claimed. This project was newly created on September 9, 2026 for a candidate entry in the AWS Agents for Humans hackathon. AWS account registration is complete; a hackathon entry has not yet been submitted.

## Run the demo

Tested on Windows with Python 3.12.10, `strands-agents==1.55.0`, Ollama and `qwen3:8b`. Dependencies and hashes are locked in `uv.lock`. Requires an installed [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com/), a browser, and enough memory for the model. The test machine has an NVIDIA RTX 4070 SUPER with 12 GB VRAM. Other hardware and operating systems have not been validated.

From this directory:

```powershell
uv sync --locked
ollama pull qwen3:8b
uv run --locked python server.py
```

Open **http://127.0.0.1:8768**. Ollama must be serving its local API on port 11434. Its desktop app normally starts that service; if it is stopped, run `ollama serve` in another terminal. The first model download is about 5.2 GB. The app makes no paid model calls and uses no AWS credentials. Local electricity and your existing hardware are not included in any cost claim.

No frontend install or build is needed. HTML, CSS and JavaScript are served directly. No remote fonts, analytics, generative chat UI or messaging integration. The Python HTTP server is for a **localhost demonstration only**; do not expose it directly to the internet.

To run without the UI:

```powershell
uv run --locked python worker.py --reset
```

The CLI saves its database, execution report and `desk-pack.md` under `private/cli-demo/`. The web demo uses `private/web-demo/`. These are separate synthetic workspaces. `private/` is excluded from version control. Normal application refresh preserves records; the **Reset demo** button clears and reseeds the web workspace.

## A complete walkthrough

1. Read the three handover notes. P-01 has an authenticated synthetic staff return ticket. The note about S-02 is explicitly unverified and cannot clear its maintenance hold.
2. Select **Prepare this shift**. The real Strands agent calls typed tools against SQLite. Expect P-01 assigned to R-201, S-01 to R-202, R-203 flagged for an overlapping booking, and R-204 flagged for a maintenance hold.
3. Inspect the register events and tool trace. **Download the desk pack** produces actual pickup checklists, exceptions and unsent notice drafts. It is generated from database records, not model prose.
4. Run again. Existing reservations, notices and return records are idempotent; a successful repeat should leave the register revision unchanged.
5. Select **Cancel R-202 & reopen the queue**, then **Prepare this shift**. R-202's draft is voided, and S-01 can be assigned to R-203. P-01 and the maintenance holds remain unchanged.
6. Reset to replay.

The UI action is the explicit authorization to process the synthetic shift. There is no scheduled background worker in this prototype. A future authenticated library-system webhook could start the same workflow, but that integration is not implemented.

## What Strands does

`worker.py` constructs a real `strands.Agent` with `OllamaModel` and six typed tools. Strands runs model inference, passes tool calls to the application and lets the model react to their results. Tool input and result records provide an execution trace. The invocation has turn and token budgets. Ollama is configured with `think: false` through the SDK's `additional_args`; this avoids exhausting the response budget on reasoning output in the tested Qwen model.

The agent must discover and apply the return dependency before it can allocate the projector. It must handle each request against fresh state. An invalid model proposal returns a specific error and can be corrected within the bounded loop. Successful model prose alone never marks the shift complete.

## Architecture and data rules

See [ARCHITECTURE.md](ARCHITECTURE.md) for the diagram and design decisions.

- `domain.py`: original synthetic records, queue policy, time-window checks, return tickets, atomic reservation/outbox writes and deterministic desk-pack generation.
- `worker.py`: Strands model/tool loop, bounded invocation and execution reports.
- `server.py`: localhost UI/API server and single-run coordination.
- `static/`: original interface, with no frontend dependency or build step.
- `test_domain.py`: deterministic regression tests, independent of a model.
- `verify_live.py`: opt-in three-phase integration check using the real local model.

Reservation windows are half-open intervals: a booking ending at 16:00 does not overlap one starting at 16:00. Times are fixed local library times in the fictional scenario; timezone/DST conversion is not implemented. Available stock can have future reservations. Maintenance and loan status are separate from reservation windows.

Modifying tools use SQLite `BEGIN IMMEDIATE` transactions. Booking and notice creation either both commit or neither does. A revision supplied by the inspection detects intervening changes. Duplicate reservations and return tickets are safe to repeat. Cancellation voids an old notice and reopens relevant exceptions.

## Validation

```powershell
uv run --locked python -m unittest -v test_domain
uv run --locked python verify_live.py
```

The first command makes no network calls. The second requires the local model and changes only `private/live-check/`. It verifies initial allocation, a repeat with no new register changes, and reassignment after cancellation. Actual observations and limitations are in [TEST_REPORT.md](TEST_REPORT.md).

Responsive layout harness: open **http://127.0.0.1:8768/layout-test**. Choose a frame width, then **Measure layout**. It measures real CSS layouts inside same-origin iframes; this does not emulate touch hardware or a mobile browser engine.

## Limits and next work

- No real inventory-system import, borrower authentication, email delivery, staff-release integration or cloud deployment. Tickets are trusted only inside the seeded fictional demo.
- Four fixed requests demonstrate the flow; this is not a tested large-scale scheduler. First-in-queue is a declared demo policy, not a claim of universal fairness.
- No equipment safety inspection is performed by the model. Staff releases are external facts supplied by the demo fixture.
- Model behavior varies. A failed/incomplete run leaves committed records visible for review and retry. Tests of several scenarios do not prove general model reliability.
- The local server and SQLite design need authentication, authorization, retention policies, operational monitoring and integration review before use with real library records.

## Licensing and credits

Original application code, copy, CSS, fictional datasets and generated sample outputs are provided under the [MIT license](LICENSE). No third-party artwork or web fonts are bundled. The system font stack uses the fonts installed on the viewer's device.

- [Strands Agents SDK](https://github.com/strands-agents/harness-sdk): Apache-2.0; see the installed distribution and upstream notices.
- [Ollama](https://github.com/ollama/ollama): MIT; runs separately.
- [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B): model downloaded separately, under its own model license. Tested Ollama manifest: `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
- Other Python dependencies retain their respective upstream licenses; exact versions and distribution hashes are in `uv.lock`. Model weights and dependency source are not bundled in this repository.

The entry does not imply an endorsement by AWS, any library or any dependency author.
