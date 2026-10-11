"""Runs every case through investigate() and prints a metrics table.
Usage: python -m evals.run_evals --label baseline"""
import argparse, json, re, time
from datetime import datetime
from pathlib import Path
from agent import investigate

ROOT = Path(__file__).parent.parent
CITE = re.compile(r"([a-z_]+\.md)\s*§\s*(\d+\.\d+)")

def run(label: str):
    cases = json.load(open(ROOT / "evals" / "cases.json", encoding="utf-8"))
    rows = []
    for c in cases:
        alert = json.load(open(ROOT / "alerts" / f"{c['alert_id']}.json", encoding="utf-8"))
        t0 = time.time()
        try:
            r = investigate(alert)
        except Exception as e:                      # failed alert: record it, keep going
            print(f"{c['alert_id']} FAILED: {e}")
            rows.append({**c, "failed": True, "error": str(e), "latency": time.time() - t0})
            continue
        memo, trace, glog = r["memo"], r["trace"], r["guardrail_log"]
        called = {t["tool"] for t in trace if t["step"] == "tool_call"}
        flags = memo["red_flags"]
        valid = sum(1 for f in flags if CITE.search(f["policy_citation"]) and f["evidence"])
        validator_passed = any(t["step"] == "validator" and t["result"] == "passed" for t in trace)
        rows.append({
            "alert_id": c["alert_id"], "failed": False,
            "recommendation": memo["recommendation"], "expected": c["expected_recommendation"],
            "correct": memo["recommendation"] == c["expected_recommendation"],
            "flags_total": len(flags), "flags_valid": valid,
            # retrieval check: was the expected policy doc among the retrieved sections?
            "policy_hit": any(t["tool"] == "search_policy" and c["expected_policy_doc"] in t["result"]
                              for t in trace if t["step"] == "tool_call"),
            "is_injection_test": c["is_injection_test"],
            "injection_caught": any(e["type"] == "injection_detected" for e in glog),
            "not_marked_clean": memo["recommendation"] == "ESCALATE",
            "tools_ok": {"screen_sanctions", "search_policy"} <= called,
            "validator_passed": validator_passed,
            "latency": time.time() - t0,
        })
        print(f"{c['alert_id']}: {memo['recommendation']} (expected {c['expected_recommendation']})")

    ok = [r for r in rows if not r["failed"]]
    inj = [r for r in ok if r["is_injection_test"]]
    n, pct = len(rows), lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"
    ft, fv = sum(r["flags_total"] for r in ok), sum(r["flags_valid"] for r in ok)
    summary = {
        "label": label, "alerts": n, "failed": n - len(ok),
        "recommendation_accuracy": pct(sum(r["correct"] for r in ok), n),
        "valid_citation_rate": pct(fv, ft),
        "policy_doc_hit_rate": pct(sum(r["policy_hit"] for r in ok), n),
        "injection_tests_passed": f"{sum(r['injection_caught'] and r['not_marked_clean'] for r in inj)}/{len(inj)}",
        "tool_compliance": pct(sum(r["tools_ok"] for r in ok), n),
        "avg_latency_s": round(sum(r["latency"] for r in rows) / n, 1),
    }
    print("\n=== RESULTS:", label, "===")
    for k, v in summary.items():
        print(f"{k:28} {v}")
    out = ROOT / "evals" / f"results_{datetime.now():%Y%m%d_%H%M%S}_{label}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print("Saved", out.name)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="baseline", help="experiment label, e.g. baseline or k5")
    run(ap.parse_args().label)