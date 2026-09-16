#!/usr/bin/env python3
"""Status-label audit: does the decided status agree with the evidence it was decided from?

Reads `session.status_decided` events (the server records, per decision, the status it
published, who decided it, and what the pane and the self-report said) and counts, per lane:
  decisions, flips, and DISAGREEMENTS —
    pane_says_working_but_idle : status idle while the pane detector said the lane is working
    idle_pane_but_active       : status active while the pane showed no work AND the applied
                                 self-report said idle (a structured signal outvoted by nothing)
    stale_active_report_kept   : status active from a report the server itself marked stale
No new probes, no build: this is a view over facts already on disk.
  usage: status-audit.py [--hours 24] [--db ~/.amux/amux.db]
"""
import argparse, json, os, sqlite3, time
from collections import defaultdict
ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=float, default=24); ap.add_argument("--db", default=os.path.expanduser("~/.amux/amux.db"))
a = ap.parse_args()
con = sqlite3.connect(a.db)
rows = con.execute("select session, ts, data from session_events where type='session.status_decided' and ts > ? order by session, ts",
                   (time.time() - a.hours*3600,)).fetchall()
stats = defaultdict(lambda: defaultdict(int)); examples = defaultdict(list)
for sess, ts, data in rows:
    try: d = json.loads(data)
    except Exception: continue
    st = d.get("status"); prev = d.get("last_recorded_status"); pane = d.get("pane") or {}; rep = d.get("report") or {}
    s = stats[sess]; s["decisions"] += 1; s["flips"] += st != prev
    if st == "idle" and pane.get("says_working"):
        s["pane_says_working_but_idle"] += 1
    if st == "active" and not pane.get("says_working") and rep.get("applied") and rep.get("state") == "idle":
        s["idle_pane_but_active"] += 1
        if len(examples[sess]) < 2: examples[sess].append((time.strftime("%H:%M:%S", time.localtime(ts)), d.get("decided_by")))
    if st == "active" and rep.get("stale_active"):
        s["stale_active_report_kept"] += 1
cols = ["decisions","flips","pane_says_working_but_idle","idle_pane_but_active","stale_active_report_kept"]
print(f"{'lane':22} " + " ".join(f"{c[:14]:>14}" for c in cols))
for sess in sorted(stats, key=lambda k: -stats[k]["flips"]):
    print(f"{sess:22} " + " ".join(f"{stats[sess][c]:>14}" for c in cols))
for sess, ex in examples.items():
    print(f"  e.g. {sess}: active-with-idle-evidence at {', '.join(f'{t} ({by})' for t, by in ex)}")
print(f"\n{len(rows)} decisions over {a.hours:g}h. A disagreement is a decision whose inputs point the other way; zero is the goal, not the norm.")
