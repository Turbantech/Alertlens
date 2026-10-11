"""Guardrails: PII masking (input), injection scan (tool output), memo validator (output)."""
import json, re

# ---- 1. PII masking: regex, applied to everything before it reaches the LLM ----
PII = {
    "IBAN": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
    "CARD": r"\b(?:\d[ -]?){13,16}\b",
    "EMIRATES_ID": r"\b784-\d{4}-\d{7}-\d\b",
    "PHONE": r"\+\d{8,15}\b|\b05\d[\s-]?\d{3}[\s-]?\d{4}\b",
}
def mask_pii(text: str):
    """Returns (masked_text, number_of_items_masked)."""
    n = 0
    for label, pat in PII.items():
        text, k = re.subn(pat, f"[{label}_MASKED]", text)
        n += k
    return text, n

# ---- 2. Prompt-injection scan on tool results ----
INJECTION = [r"ignore (?:all )?(?:previous|prior|above) instructions", r"\bsystem\s*:",
             r"mark (?:this |the )?alert as clean", r"you are now", r"do not escalate",
             r"disregard (?:the )?(?:above|previous|policy)"]
def scan_injection(text: str):
    """Redacts matches. Returns (clean_text, list_of_matched_snippets)."""
    hits = []
    for pat in INJECTION:
        hits += [m.group(0) for m in re.finditer(pat, text, re.I)]
        text = re.sub(pat, "[REDACTED: suspected prompt injection]", text, flags=re.I)
    return text, hits

# ---- 3. Output validator (plain code, not an LLM) ----
TIPOFF = re.compile(r"(?<!not )(?<!never )\b(?:inform|notify|tell|alert|warn)\s+the\s+customer"
                    r"|let the customer know", re.I)
CITE = re.compile(r"([a-z_]+\.md)\s*§\s*(\d+\.\d+)")

def check_memo(memo: dict, called: set, policy_text: str) -> list[str]:
    """Returns a list of problems; empty list = memo passes."""
    problems = []
    for t in ("screen_sanctions", "search_policy"):          # a. mandatory tools
        if t not in called:
            problems.append(f"You must call {t} before writing the memo.")
    for i, f in enumerate(memo["red_flags"]):                # b. evidence + real citation
        if not f["evidence"]:
            problems.append(f"Red flag {i+1} has no evidence.")
        m = CITE.search(f["policy_citation"])
        if not m or f"[{m.group(1)} §{m.group(2)}]" not in policy_text:
            problems.append(f"Red flag {i+1}: citation '{f['policy_citation']}' was not in retrieved policy text.")
    if memo["recommendation"] not in ("ESCALATE", "RECOMMEND_CLOSE"):   # c. enum
        problems.append("Invalid recommendation.")
    if TIPOFF.search(json.dumps(memo)):                      # d. tipping-off
        problems.append("Memo contains tipping-off language. Remove it.")
    return problems