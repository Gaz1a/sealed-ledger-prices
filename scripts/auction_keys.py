"""Shared product key for auction comps (same product = same key, so prices can be compared over time)."""
import re

def comp_key(p, bucket=None):
    """Sealed: 'p<TCGplayer id>' (prices per box). Graded want: '<ledger id>|<grader> <grade>'."""
    if p.get("key"): return p["key"]
    m = re.search(r"/product/(\d+)", p.get("tcgUrl") or "") or (re.match(r"(\d+)$", str(p.get("tcgProductId") or "")))
    if m: return "p" + m.group(1)
    if p.get("wantId") and p.get("grade"):
        return f'{p["wantId"]}|{re.sub("(?i)beckett", "BGS", p["grade"]).upper()}'
    return None
