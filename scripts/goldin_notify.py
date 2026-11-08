#!/usr/bin/env python3
"""Turn goldin.json into a GitHub issue (GitHub emails Gaz): the Goldin bid sheet with max bids.
Closes the previous bid-sheet issue. Uses the gh CLI with the workflow token."""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
g = json.load(open(os.path.join(ROOT, "goldin.json")))
try: sold = json.load(open(os.path.join(ROOT, "goldin_sold.json")))
except Exception: sold = {}
wants = [p for p in g.get("wants", []) if p.get("top")]
sealed = [p for p in g.get("sealed", []) if p.get("top")]
if not wants and not sealed:
    print("no Goldin picks"); sys.exit(0)

def line(p):
    units = f" ({p['units']} x ${p['unitValue']:,.2f})" if p.get("units") and p.get("unitValue") else ""
    what = p.get("product") or p.get("grade") or ""
    out = [f"**{p['title'][:110]}**",
           f"Value ${p['value']:,.2f}{units} · {what}",
           f"Now ${p['allInNow']:,.2f} all-in ({p['bids']} bids) · **MAX BID ${p['maxBid']:,}** (hammer; Goldin adds {p['buyerPremiumPct']:g}% + ~${p['shipEst']:.0f} shipping)",
           f"Ends {p['endsPT']} · [Goldin]({p['url']})" + (f" · [TCGplayer]({p['tcgUrl']})" if p.get("tcgUrl") else "")]
    if p.get("flag"): out[0] += f" — {p['flag']}"
    return "\n".join(out)

ends = sorted(p["endsPT"] for p in wants + sealed if p.get("endsPT"))
first = min(wants + sealed, key=lambda p: p.get("ends") or "z")
body = [f"Goldin scan {g['generated']} · {g.get('lotsScanned')} live Pokémon lots checked.", ""]
if sold.get("medianPctOfValue"):
    body.append(f"Reality check: over the last {sold.get('days')} days Goldin sealed lots closed at a median of "
                f"**{round(sold['medianPctOfValue'] * 100)}%** of TCGplayer value ({sold.get('valued')} priced lots), "
                f"so most max bids below will be outbid; the ones that land are the bargains. Set each as your max bid on goldin.co.")
    cheap = sold.get("cheap") or []
    if cheap:
        body.append("")
        body.append("Closed cheap recently (what a win looks like):")
        for r in cheap[:5]:
            body.append(f"- {r['title'][:90]}: ${r['allIn']:,.2f} all-in vs ${r['value']:,.2f} value ({round(r['pctOfValue'] * 100)}%) [link]({r['url']})")
body.append("")
if wants:
    body += ["### Your wants", ""] + [line(p) + "\n" for p in wants]
if sealed:
    body += ["### Sealed multi-packs (undervalued / overlooked)", ""] + [line(p) + "\n" for p in sealed]
body += ["", "Max bid = highest hammer bid that keeps hammer + buyer's premium + est. shipping at or under 85% of value. "
         "Values: TCGplayer min(market, lowest listing) x units; graded wants from PriceCharting. Check the photos and quantity before bidding. @Gaz1a"]
title = f"Goldin bid sheet: {len(wants)} wants, {len(sealed)} sealed — first close {first.get('endsPT')}"

def gh(*a, inp=None):
    return subprocess.run(["gh", *a], input=inp, text=True, capture_output=True)
gh("label", "create", "goldin", "--color", "C9A227", "--description", "Goldin bid sheet")
old = gh("issue", "list", "--label", "goldin", "--state", "open", "--json", "number", "--jq", ".[].number").stdout.split()
r = gh("issue", "create", "--title", title, "--label", "goldin", "--body-file", "-", inp="\n".join(body))
print(r.stdout or r.stderr)
for n in old:
    gh("issue", "close", n, "--comment", "Superseded by the newer Goldin bid sheet.")
