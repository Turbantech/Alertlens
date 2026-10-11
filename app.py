"""Streamlit UI: alert queue (left), memo + human decision (right)."""
import os, sys
try:  # Streamlit Cloud ships an old sqlite; swap in a newer one for Chroma
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass  # local Windows: not needed
import json
import time
from datetime import datetime,date
from pathlib import Path
import streamlit as st
try:  # Streamlit Cloud: copy secrets into env vars so the rest of the code works unchanged
    for k, v in st.secrets.items():
        if isinstance(v, str):
            os.environ.setdefault(k, v)
except Exception:
    pass  # running locally: .env is used instead
import rag
from agent import investigate

ROOT = Path(__file__).parent
st.set_page_config(page_title="AlertLens: Evidence-Backed AML Investigations", layout="wide")

# ---- custom CSS (delete this block for the plain version) ----
st.markdown("""
<style>
.block-container {padding-top: 4rem; max-width: 1300px;}
.banner {line-height: 1.5; overflow: visible;}
html, body, [class*="css"] {font-family: "Inter", "Segoe UI", sans-serif;}
.banner {background:#eef2ff; border:1px solid #c7d2fe; color:#3730a3; padding:10px 16px;
         border-radius:10px; font-size:0.9rem; margin-bottom:1rem;}
.card {background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:14px 18px;
       margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,0.06); color:#111827;}
.card small {color:#6b7280;}
.badge {display:inline-block; padding:3px 12px; border-radius:999px; font-weight:600;
        font-size:0.8rem; margin-right:6px;}
.HIGH, .ESCALATE {background:#fee2e2; color:#991b1b;}
.MEDIUM {background:#fef3c7; color:#92400e;}
.LOW, .RECOMMEND_CLOSE {background:#dcfce7; color:#166534;}
.review {background:#fff7ed; border:1px solid #fdba74; color:#9a3412; padding:10px 16px;
         border-radius:10px; margin-bottom:12px; font-weight:600;}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def setup():
    rag.ingest()          # idempotent, so safe to call once per server start
    return True
setup()
MAX_PER_SESSION, MAX_PER_DAY, COOLDOWN_S = 20, 100, 5

@st.cache_resource
def usage():
    return {"day": date.today(), "count": 0}   # shared by every visitor on this server

def limit_message():
    """Returns a message if the user is over a limit, else None."""
    u, s = usage(), st.session_state
    if u["day"] != date.today():
        u.update(day=date.today(), count=0)
    if s.get("n", 0) >= MAX_PER_SESSION:
        return f"Session limit reached ({MAX_PER_SESSION} investigations)."
    if time.time() - s.get("last", 0) < COOLDOWN_S:
        return f"Please wait {COOLDOWN_S}s between investigations."
    if u["count"] >= MAX_PER_DAY:
        return "Daily demo limit reached. Try again tomorrow."
    return None

st.info("Decision support on synthetic data. A human makes the final decision.")
st.title("AlertLens")
st.caption("Evidence-Backed AML Investigations")

alerts = {p.stem: json.loads(p.read_text(encoding="utf-8"))
          for p in sorted((ROOT / "alerts").glob("A-*.json"))}
results = st.session_state.setdefault("results", {})   # alert_id -> investigate() output

left, right = st.columns([1, 2], gap="large")

with left:
    st.subheader("Alert queue")
    chosen = st.radio("Alerts", list(alerts), label_visibility="collapsed",
                      format_func=lambda a: f"{a} · {alerts[a]['rule']}")
    alert = alerts[chosen]
    st.markdown(f'<div class="card"><b>{alert["alert_id"]}</b> · {alert["customer_id"]}<br>'
                f'<small>{alert["summary"]}</small></div>', unsafe_allow_html=True)
    with st.expander("Raw alert JSON"):
        st.json(alert)
    if st.button("Investigate", type="primary", use_container_width=True):
        msg = limit_message()
        if msg:
            st.warning(msg)
        else:
            st.session_state["n"] = st.session_state.get("n", 0) + 1
            st.session_state["last"] = time.time()
            usage()["count"] += 1
            with st.spinner("Agent investigating..."):
                try:
                    results[chosen] = investigate(alert)
                except Exception as e:
                    st.error(f"Investigation failed: {e}")

with right:
    st.subheader("Investigation memo")
    r = results.get(chosen)
    if not r:
        st.info("Select an alert and click Investigate.")
    else:
        memo, trace, glog = r["memo"], r["trace"], r["guardrail_log"]
        if memo.get("mandatory_human_review"):
            st.markdown('<div class="review">⚠ Mandatory human review: prompt injection detected in data.</div>',
                        unsafe_allow_html=True)
        st.markdown(f'<span class="badge {memo["risk_level"]}">Risk: {memo["risk_level"]}</span>'
                    f'<span class="badge {memo["recommendation"]}">Recommendation: {memo["recommendation"]}</span>',
                    unsafe_allow_html=True)
        st.write(memo["summary"])
        st.markdown(f'**Sanctions screening:** {memo["sanctions_result"]}')

        st.markdown("**Red flags**")
        if not memo["red_flags"]:
            st.caption("No red flags raised.")
        for f in memo["red_flags"]:
            st.markdown(f'<div class="card">{f["description"]}<br>'
                        f'<small>Evidence: {", ".join(f["evidence"])}<br>'
                        f'Policy: {f["policy_citation"]}</small></div>', unsafe_allow_html=True)

        with st.expander("Agent steps", expanded=True):
            st.write("  →  ".join(t.get("tool", t["step"]) + (" ✓" if t.get("result") == "passed" else "")
                                   for t in trace))
            for t in trace:
                st.caption(f'{t.get("tool", t["step"])} {t.get("args", "")} → {t["result"][:100]}')

        with st.expander("Guardrail log"):
            pii = sum(int(e["detail"].split()[0]) for e in glog if e["type"] == "pii_masked")
            inj = any(e["type"] == "injection_detected" for e in glog)
            val = next((e["detail"][:60] for e in reversed(glog) if e["type"] == "validator"), "n/a")
            st.write(f"PII items masked: **{pii}**  |  Injection detected: **{'yes' if inj else 'no'}**  |  Validator: **{val}**")
            for e in glog:
                st.caption(f'{e["type"]}: {e["detail"][:200]}')

        st.markdown("**Analyst decision**")
        c1, c2, _ = st.columns([1, 1, 3])
        for col, label in ((c1, "Approve"), (c2, "Reject")):
            if col.button(label, key=f"{label}-{chosen}", use_container_width=True):
                with open(ROOT / "decisions.log", "a", encoding="utf-8") as fh:
                    fh.write(f"{chosen}\t{label.upper()}\t{datetime.now().isoformat(timespec='seconds')}\n")
                st.success(f"{label} recorded for {chosen} (audit log: decisions.log)")