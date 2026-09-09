# BorrowBridge test report

Date: 2026-09-09. Test data is entirely synthetic. No real borrowers or children participated. These observations describe this prototype, not a general guarantee of model accuracy or accessibility conformance.

## Deterministic domain checks

Command: `uv run --locked python -m unittest -v test_domain`

**12 tests passed** on Python 3.12.10 / Windows. Latest measured suite time: 0.772 seconds.

| Case | Observed result |
| --- | --- |
| Matching staff return ticket | P-01 becomes available; duplicate ticket adds no event |
| Unverified note / held item | No release; held S-02 cannot be reserved |
| Wrong category / unknown ID | Rejected without a reservation |
| Queue order | R-203 cannot skip pending R-202 |
| Time overlap | Overlap rejected; touching half-open intervals accepted |
| Stale revision | Rejected without an outbox write |
| Repeated reservation | One booking, notice and event |
| Cancellation | Old notice void; next request reopens and can be reserved |
| Unnecessary exception | Cannot defer a request while eligible stock exists |
| Invalid time interval | Rejected |
| Two concurrent duplicate writes | One committed reservation and one idempotent result |
| Restart and reset | Restart preserves committed state; reset reseeds |

## Real-model integration

Command: `uv run --locked python verify_live.py`

Strands Agents 1.55.0; local Ollama `qwen3:8b`; `think: false`, temperature 0, seed 11; 16,384 context tokens. GPU: NVIDIA RTX 4070 SUPER, 12 GB VRAM. This test invokes the real model and real Strands tools. It does not use a scripted or mocked model response.

| Phase | Seconds | Tool calls | Rejected proposals | Observed result |
| --- | ---: | ---: | ---: | --- |
| Initial shift | 9.75 | 11 | 0 | 2 pickups, 2 exceptions, no pending requests; revision 5 |
| Repeat | 9.91 | 11 | 0 | Same bookings, audit and notices; revision stays 5 |
| Cancellation | 11.39 | 13 | 2 | R-202 cancelled, S-01 assigned to R-203, 1 maintenance exception; revision 7 |

All phase assertions passed. The saved Markdown was compared with a fresh deterministic desk pack and matched exactly after text decoding. Maintenance holds remained unchanged. The model's two invalid proposals during cancellation were rejected by the domain layer; the model recovered and completed the run. No messages were sent.

These are warm-model observations, not a benchmark claim. An earlier cold/untuned run took substantially longer. Early development runs also exposed a trace serialization error and exhausted model output tokens; explicit serializable tool arguments and the documented Ollama `think: false` setting fixed those issues before the successful three-phase run.

## Browser walkthrough

Tested in the connected Chrome browser on Windows, against the actual localhost Python server and local model:

- Selected **Prepare this shift** and observed two pickups and two exceptions in the register.
- Activated **Prepare this shift** with the Enter key. Keyboard Tab moved to **Reset demo**, confirmed as the focused control in the browser's accessibility snapshot.
- Selected **Cancel R-202 & reopen the queue**, then ran again. The interface showed two pickups, one exception, one cancellation and revision 7. The cancelled notice was void in the database and excluded from the desk pack.
- Selected **Reset demo** and observed a fresh synthetic queue before replay.
- Reloaded the interface without resetting and observed persisted state.
- Saved four JPEG screenshots in the locally prepared source archive's `evidence/` directory. The public GitHub repository currently includes the text evidence; those JPEG attachments have not been uploaded. The download endpoint creates a Markdown file from the current register; its content was inspected through the generated CLI artifact. A browser file-download completion has not been independently verified.

## Responsive layout

`/layout-test` renders the real interface in same-origin frames sized at 360, 768 and 1280 CSS pixels. In this Windows browser, the frame's vertical scrollbar takes 15 pixels, giving content widths of 345, 753 and 1265 pixels respectively.

At all three sizes, `documentElement.scrollWidth` equalled the content width. No measured main button, heading, request or panel crossed the content area's horizontal bounds. Primary, reset and cancellation buttons measured 51, 48 and 76 pixels high respectively. Locally saved screenshots record the actual layout. This checks responsive CSS in Chrome; it does not emulate mobile touch hardware, Safari or a different browser engine.

Visible keyboard-focus styles, text labels for status, semantic buttons and a labelled inventory table are implemented. There is no animation or audio. The CSS includes reduced-motion overrides. Screen-reader walkthroughs, forced-colors mode, mobile touch gestures, automated contrast measurement and an OS reduced-motion toggle have not yet been tested. **No WCAG conformance claim is made.**

## Reproducibility and limits

The lockfile pins dependency versions and distribution hashes. Model weights are not included. The tested Ollama model digest is recorded in README. Source is original and licensed MIT; the runtime dependencies retain their own licenses.

The public repository was independently cloned at revision `1ffa675427f12fd8760cfb45a0681631b1540914`. All executable source matched the tested local source after line-ending normalization. JSON evidence matched after ignoring a final newline. All 12 domain tests also passed from that public clone in 0.732 seconds. The browser demo was then run directly from this clone, verifying initial allocation, unchanged revision 5 on repeat, and revision 7 after cancellation reassignment.

Testing covers the seeded scenario and stated domain cases. No production library integration, public cloud deployment, large-load test, actual equipment inspection or field adoption study was performed. The local development server must remain bound to localhost.
