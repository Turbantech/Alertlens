import argparse, json
from agent import investigate

p = argparse.ArgumentParser()
p.add_argument("--alert", required=True)
alert = json.load(open(p.parse_args().alert, encoding="utf-8"))
r = investigate(alert)
print("\n=== MEMO ===\n" + json.dumps(r["memo"], indent=2, ensure_ascii=False))
print("\n=== TRACE ===")
for t in r["trace"]:
    print(f"- {t.get('tool', t['step'])} {t.get('args', '')} -> {t['result'][:90]}")
print("\n=== GUARDRAIL LOG ===")
for e in r["guardrail_log"]:
    print(f"- {e['type']}: {e['detail'][:150]}")