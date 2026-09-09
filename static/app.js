"use strict";
const $ = id => document.getElementById(id);
let busy = false, polling, lastFingerprint = "", lastStatus = "";
function el(tag, text, className) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; }
const categoryName = {projector: "Projector", sewing: "Sewing kit", ladder: "Folding ladder"};
const stateName = {pending: "In queue", reserved: "Pickup prepared", attention: "Needs a person", cancelled: "Cancelled"};
function shortTime(value) { const [day, time] = value.split("T"); return `${day.slice(8)} Sep, ${time}`; }
function eventTitle(event) {
  const d = event.details;
  return {return_recorded: `${d.item_id} returned to stock using staff ticket ${d.ticket_id}.`, reservation_created: `${d.request_id}: ${d.item_id} reserved; pickup notice prepared.`, needs_attention: `${d.request_id} left for a volunteer: ${d.reason}.`, request_cancelled: `${d.request_id} cancelled; its notice was voided and the queue reopened.`}[event.event] || event.event;
}
function draw(s) {
  const running = s.job.status === "running";
  $("run").disabled = running || busy; $("reset").disabled = running || busy;
  $("cancel").disabled = running || busy || !s.requests.some(r => r.id === "R-202" && r.state === "reserved");
  $("reserved-count").textContent = s.summary.reserved; $("attention-count").textContent = s.summary.attention;
  $("revision").textContent = `REGISTER ${s.revision}`;
  const titles = {idle: "Ready when you are", running: "Preparing the next shift…", complete: "The next shift is ready", incomplete: "The shift still needs attention", failed: "The run stopped"};
  $("status-heading").textContent = titles[s.job.status] || "Ready when you are";
  $("status-detail").textContent = running ? `${s.job.events.length} actions checked. Local inference can take a few minutes.` : s.job.status === "complete" ? `${s.summary.reserved} pickups prepared. ${s.summary.attention} exceptions. All notices remain unsent.` : s.job.status === "failed" ? "Your register is preserved. Check that Ollama is running, then try again." : s.job.status === "incomplete" ? "The agent reached its limit before finishing. Review the trace; committed bookings are preserved." : "Read the handover, then let the assistant update the register.";
  if (lastStatus !== s.job.status && s.job.status !== "idle") $("message").textContent = $("status-heading").textContent;
  lastStatus = s.job.status;
  if (running && !polling) polling = setInterval(refresh, 1500);
  if (!running && polling) { clearInterval(polling); polling = null; }
  const fingerprint = JSON.stringify([s.revision, s.job.events]);
  if (fingerprint === lastFingerprint) return;
  lastFingerprint = fingerprint;
  $("notes").replaceChildren(...s.handover.map(n => { const a = el("article", undefined, "note"); a.append(el("span", `${n.id} · ${n.kind}`, `note-label ${n.kind === "unverified note" ? "unverified" : ""}`), el("p", n.text)); return a; }));
  $("requests").replaceChildren(...s.requests.map(r => { const a = el("article", undefined, "request"); const top = el("div", undefined, "request-top"); top.append(el("span", `${r.id} · ${categoryName[r.category]}`, "request-title"), el("span", stateName[r.state], `state ${r.state}`)); a.append(top, el("p", `${shortTime(r.starts)} → ${shortTime(r.ends)}`, "time"), el("p", r.item_id ? `${r.item_id} assigned · borrower ${r.borrower} · notice saved as draft` : r.reason || r.note)); return a; }));
  $("events").replaceChildren(...(s.audit.length ? s.audit.map(e => { const li = el("li", eventTitle(e)); li.append(el("span", `Register revision ${e.revision} · event ${e.id}`, "event-proof")); return li; }) : [el("li", "No changes yet. Preparing the shift will create a record here.")]));
  $("tool-events").replaceChildren(...s.job.events.map(e => el("li", `${e.seconds}s · ${e.tool} · ${e.status}${e.status === "rejected" ? `: ${e.result.error}` : ""}`)));
  $("inventory").replaceChildren(...s.items.map(i => { const row = el("tr"); row.append(el("td", `${i.id} · ${i.name}`), el("td", i.location), el("td", i.status.replaceAll("_", " "))); return row; }));
}
async function refresh() { try { const r = await fetch("/api/state"); if (!r.ok) throw Error("Could not read the register."); draw(await r.json()); } catch (e) { $("message").textContent = "Connection interrupted. Your local register is preserved. Refresh when the server is available."; } }
async function act(action) {
  if (busy) return; busy = true; $("message").textContent = "";
  try { const r = await fetch(`/api/${action}`, {method: "POST", headers: {"X-BorrowBridge": "local-demo"}}); const j = await r.json(); if (!r.ok) throw Error(j.error); if (action === "cancel") $("message").textContent = "R-202 cancelled. Prepare the shift again to allocate the released kit."; if (action === "reset") $("message").textContent = "Demo reset. All fictional bookings and notices cleared."; }
  catch (e) { $("message").textContent = e.message; }
  finally { busy = false; await refresh(); }
}
$("run").addEventListener("click", () => act("run"));
$("reset").addEventListener("click", () => act("reset"));
$("cancel").addEventListener("click", () => act("cancel"));
refresh();
