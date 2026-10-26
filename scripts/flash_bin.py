#!/usr/bin/env python3
"""Flash bargains: every 3 hours, look for NEW buy-it-now listings of wanted products
priced at or under Gaz's target, so a momentary dip is not missed between daily runs.

Scope: want-list rows (wants_auto.json) with a target of $10+; sealed product must be
eBay condition New with no opened/resealed wording; raw cards must be Ungraded with the
seller stating Near Mint or better. US sellers only, shipping known, seller 97%+ / 50+.
All-in = (price + shipping) x 1.10 (LA tax) must be at or under target.

Output: flash.json (hits from the last 7 days, newest first) and, for NEW hits, one GitHub
issue per run (GitHub emails/pushes it to the repo owner). The daily Buy Hunter task then
verifies each hit against sold comps and logs it to the ledger.
Uses ~1 search call per want per run (~700/day), inside the 5,000/day Browse API quota."""
import datetime, json, os, re, subprocess, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_ebay_wants import (NOISE, UNGRADED, get, has_num, nm_check, parse, price_of,  # noqa: E402
                             search, seller_ok, ship_of, token)
from scan_ebay_sealed import BAD_WORDS, NEW_CONDITION  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAX = 1.10
MIN_TARGET = 10
KEEP_DAYS = 7
NOW = datetime.datetime.now(datetime.timezone.utc)


def load(n, d):
    try:
        return json.load(open(os.path.join(ROOT, n)))
    except Exception:
        return d


def tcg_url(pid, cond):
    if not pid:
        return None
    u = f"https://www.tcgplayer.com/product/{pid}"
    return u + ("?Condition=Near+Mint&Language=English" if cond == "nm" else "")


def words(s):
    return [w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", s)
            if w.lower() not in {"pokemon", "the", "and", "box", "with", "pack", "packs", "card", "cards", "tcg"}]


def main():
    wa = load("wants_auto.json", {}).get("items", {})
    prices = load("prices.json", {}).get("prices", {})
    old = load("flash.json", {})
    hits = [h for h in old.get("hits", []) if (NOW - datetime.datetime.fromisoformat(h["found"])).days < KEEP_DAYS]
    seen = {h["itemId"] for h in hits}
    H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}

    rows = [(k, v) for k, v in wa.items()
            if (v.get("target") or 0) >= MIN_TARGET and v.get("cond") in ("sealed", "nm")
            and not k.startswith(("bk-", "jumbo-"))]
    rows.sort(key=lambda kv: -kv[1]["target"])
    new, nq = [], 0
    for wid, w in rows:
        tgt, cond, title = float(w["target"]), w["cond"], w.get("title") or ""
        market = (prices.get(wid) or {}).get("market") or w.get("market")
        pid = (prices.get(wid) or {}).get("productId") or w.get("tcgProductId")
        hi = max(2, round(tgt / TAX, 2))   # item price alone can't exceed target/1.10
        lo = max(1, round(tgt * 0.35))      # far below target is usually the wrong product
        if cond == "sealed":
            setn = w.get("set") or ""
            q = f"{setn} {title}".strip() if setn and setn.lower() not in title.lower() else title
            filt = f"price:[{lo}..{hi}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE}},conditionIds:{{{NEW_CONDITION}}},itemLocationCountry:US"
            need = words(q)[:4]
        else:
            name, num, clean = parse(title)
            q = f"{name} {num}" if num else clean
            filt = f"price:[{lo}..{hi}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE}},conditionIds:{{{UNGRADED}}},itemLocationCountry:US"
            need = None
        nq += 1
        for h in search(q, H, filt, 25, 0, "newlyListed"):
            iid, t = h.get("itemId"), h.get("title", "")
            if not iid or iid in seen or not seller_ok(h):
                continue
            if cond == "sealed":
                if BAD_WORDS.search(t) or not all(x in t.lower() for x in need):
                    continue
            else:
                if NOISE.search(t) and "[JP]" not in title:
                    continue
                if name.lower() not in t.lower() or (num and not has_num(t, num)):
                    continue
            price, sh = price_of(h), ship_of(h)
            if price is None or sh is None:
                continue
            all_in = round((price + sh) * TAX, 2)
            if all_in > tgt:
                continue
            if cond == "nm" and nm_check(iid, H) is not True:
                continue
            seen.add(iid)
            new.append({"itemId": iid, "found": NOW.isoformat(timespec="minutes"), "wantId": wid, "want": title,
                        "cond": cond, "listing": t, "url": h.get("itemWebUrl"), "price": price, "shipping": sh,
                        "allIn": all_in, "target": tgt, "market": market,
                        "pctUnderTarget": round(100 * (1 - all_in / tgt), 1),
                        "tcgUrl": tcg_url(pid, cond), "seller": (h.get("seller") or {}).get("username"),
                        "feedbackPct": (h.get("seller") or {}).get("feedbackPercentage"),
                        "feedbackScore": (h.get("seller") or {}).get("feedbackScore"),
                        "listed": h.get("itemCreationDate"), "image": (h.get("image") or {}).get("imageUrl")})
        time.sleep(0.2)

    new.sort(key=lambda x: -x["pctUnderTarget"])
    hits = new + hits
    json.dump({"generated": NOW.isoformat(timespec="minutes"), "queries": nq, "wants": len(rows), "hits": hits},
              open(os.path.join(ROOT, "flash.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{nq} queries, {len(new)} new hits, {len(hits)} in the last {KEEP_DAYS} days")

    if new and os.environ.get("GH_TOKEN"):
        top = new[0]
        head = f"Bargain: {top['want'][:60]} ${top['allIn']:.2f} all-in (target ${top['target']:.2f})"
        if len(new) > 1:
            head += f" +{len(new) - 1} more"
        lines = ["Buy-it-now listings at or under your target, found by the 3-hourly scan. "
                 "Not yet checked against sold comps: the morning Buy Hunter verifies and logs them. @Gaz1a", ""]
        for x in new[:10]:
            mk = f", market ${x['market']:.2f}" if x.get("market") else ""
            lines += [f"**{x['want']}** ({'sealed' if x['cond'] == 'sealed' else 'NM, seller-stated'})",
                      f"Buy it now ${x['allIn']:.2f} all-in (${x['price']:.2f} + ${x['shipping']:.2f} ship, with tax) "
                      f"vs target ${x['target']:.2f}{mk}; {x['pctUnderTarget']}% under target",
                      f"Seller {x['seller']} ({x['feedbackPct']}%, {x['feedbackScore']})",
                      f"eBay: {x['url']}"]
            if x.get("tcgUrl"):
                lines.append(f"TCGplayer: {x['tcgUrl']}")
            lines.append("")
        subprocess.run(["gh", "issue", "create", "--title", head, "--label", "bargain", "--body", "\n".join(lines)],
                       check=False)


if __name__ == "__main__":
    main()
