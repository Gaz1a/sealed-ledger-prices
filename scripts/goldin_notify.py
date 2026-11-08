#!/usr/bin/env python3
"""Turn goldin.json + fanatics.json into one GitHub issue (GitHub emails Gaz): the auction bid sheet with max bids.
--lastcall: only lots closing in the next 36 hours that are still at or under their max bid (Sunday midday run).
Closes the previous bid-sheet issue. Uses the gh CLI with the workflow token."""
import json, os, subprocess, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAST = "--lastcall" in sys.argv
NOW = datetime.datetime.now(datetime.timezone.utc)

def load(f):
    try: return json.load(open(os.path.join(ROOT, f)))
    except Exception: return {}

HOUSES = [("Goldin", load("goldin.json"), load("goldin_sold.json")), ("Fanatics Collect", load("fanatics.json"), load("fanatics_sold.json"))]
horizon = (NOW + datetime.timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M")

def keep(p):
    if not p.get("top"): return False
    if LAST:
        return (p.get("ends") or "z") <= horizon and p.get("maxBid") is not None and p["currentBid"] <= p["maxBid"]
    return True

def line(p, house):
    units = f" ({p['units']} x ${p['unitValue']:,.2f})" if p.get("units") and p.get("unitValue") else ""
    what = p.get("product") or p.get("grade") or ""
    out = [f"**{p['title'][:110]}**" + (f" — {p['flag']}" if p.get("flag") else ""),
           f"Value ${p['value']:,.2f}{units} · {what}",
           f"Now ${p['allInNow']:,.2f} all-in ({p['bids']} bids) · **MAX BID ${p['maxBid']:,}** (hammer; {house} adds {p['buyerPremiumPct']:g}% + ~${p['shipEst']:.0f} shipping)",
           f"Ends {p['endsPT']} · [{house}]({p['url']})" + (f" · [TCGplayer]({p['tcgUrl']})" if p.get("tcgUrl") else "")]
    return "\n".join(out)

body, n_w, n_s, firsts = [], 0, 0, []
for house, d, sold in HOUSES:
    if not d: continue
    wants = [p for p in d.get("wants", []) if keep(p)]
    sealed = [p for p in d.get("sealed", []) if keep(p)]
    body.append(f"## {house}")
    body.append(f"Scan {d.get('generated')} · {d.get('lotsScanned')} live Pokémon lots checked.")
    if sold.get("medianPctOfValue"):
        body.append(f"Last {sold.get('days')} days: sealed lots closed at a median **{round(sold['medianPctOfValue'] * 100)}%** of TCGplayer value "
                    f"({sold.get('valued')} priced lots), so most max bids get outbid; the ones that land are the bargains.")
        for r in (sold.get("cheap") or [])[:3]:
            body.append(f"- Closed cheap: {r['title'][:80]}: ${r['allIn']:,.2f} vs ${r['value']:,.2f} ({round(r['pctOfValue'] * 100)}%)")
    body.append("")
    if wants: body += ["### Your wants", ""] + [line(p, house) + "\n" for p in wants]
    if sealed: body += ["### Sealed multi-packs (undervalued / overlooked)", ""] + [line(p, house) + "\n" for p in sealed]
    if not wants and not sealed: body += ["Nothing qualifies right now.", ""]
    n_w += len(wants); n_s += len(sealed)
    firsts += [p for p in wants + sealed]
if not firsts:
    print("no picks"); sys.exit(0)
res = load("auction_results.json").get("summary")
if res and res.get("closed"):
    body.append(f"Track record so far: {res['closed']} picks have closed; the max bid would have won {res['maxBidWouldHaveWon']}.")
body += ["", "Max bid = highest hammer bid that keeps hammer + buyer's premium + est. shipping at or under 85% of value. "
         "Enter it as your max bid on the site and walk away. Values: TCGplayer min(market, lowest listing) x units; graded wants from "
         "PriceCharting. Check the photos and quantity before bidding. @Gaz1a"]
first = min(firsts, key=lambda p: p.get("ends") or "z")
title = (("LAST CALL (still under max): " if LAST else "Auction bid sheet: ") + f"{n_w} wants, {n_s} sealed — first close {first.get('endsPT')}")

def gh(*a, inp=None):
    return subprocess.run(["gh", *a], input=inp, text=True, capture_output=True)
gh("label", "create", "goldin", "--color", "C9A227", "--description", "Auction bid sheet (Goldin, Fanatics Collect)")
old = gh("issue", "list", "--label", "goldin", "--state", "open", "--json", "number", "--jq", ".[].number").stdout.split()
r = gh("issue", "create", "--title", title, "--label", "goldin", "--body-file", "-", inp="\n".join(body))
print(r.stdout or r.stderr)
for n in old:
    gh("issue", "close", n, "--comment", "Superseded by the newer bid sheet.")
