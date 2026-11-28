#!/usr/bin/env python3
"""Best buyable listing per wanted ledger row, plus seller baskets.

Free daily job (GitHub Actions). Reads wants_auto.json (wanted rows with tcgProductId,
target, kind) and verified.json (eBay listings already checked live by verify_listings.py),
asks TCGplayer's listing search (the same data its product page loads; unofficial, may
change) for the cheapest live listings of the exact product, and picks:

  tcg   cheapest listing (price + shipping) from a seller with 99%+ rating and 1000+ sales,
        Near Mint English for cards (reverse holo only on -rev rows), sealed for items
  ebay  cheapest live eBay listing for the row from verified.json (known shipping, not eBay Live)
  baskets  sellers that carry 2+ wanted cards at or under target, only when buying them
           together beats buying each one separately

Writes best_listings.json (compact; the Tracker copies it into the ledger DB as meta/listings).
"""
import json, os, re, sys, time, urllib.request, datetime

API = 'https://mp-search-api.tcgplayer.com/v1/product/{pid}/listings'
MIN_RATING, MIN_SALES = 99.0, 1000
SIZE = 25
LIMIT = int(os.environ.get('BL_LIMIT', '400'))


def sales_num(v):
    if v is None:
        return 0
    s = str(v).replace(',', '').replace('+', '').strip()
    m = re.match(r'([\d.]+)\s*([kK])?', s)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * 1000) if m.group(2) else int(n)


def query(pid, card, rev):
    size = SIZE if card else 50
    term = {'sellerStatus': 'Live', 'channelId': 0, 'language': ['English']}
    if card:
        term['condition'] = ['Near Mint']
        if rev:
            term['printing'] = ['Reverse Holofoil']
    body = {
        'filters': {'term': term, 'range': {'quantity': {'gte': 1}}, 'exclude': {'channelExclusion': 0}},
        'from': 0, 'size': size,
        'sort': {'field': 'price+shipping', 'order': 'asc'},
        'context': {'shippingCountry': 'US', 'cart': {}},
        'aggregations': ['listingType'],
    }
    req = urllib.request.Request(API.format(pid=pid), data=json.dumps(body).encode(), method='POST',
                                 headers={'content-type': 'application/json', 'accept': 'application/json',
                                          'user-agent': 'Mozilla/5.0 (ledger price check; personal use)'})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.load(r)
    res = (d.get('results') or [{}])[0].get('results') or []
    out = []
    for x in res:
        pr = x.get('printing') or ''
        if card and not rev and 'reverse' in pr.lower():
            continue
        price = x.get('price')
        ship = x.get('shippingPrice') if x.get('shippingPrice') is not None else x.get('sellerShippingPrice')
        if price is None:
            continue
        ship = float(ship or 0)
        out.append({
            'p': round(float(price), 2), 's': round(ship, 2), 'a': round(float(price) + ship, 2),
            'sel': x.get('sellerName') or '', 'key': x.get('sellerKey') or '',
            'r': float(x.get('sellerRating') or 0), 'n': sales_num(x.get('sellerSales')),
            'c': x.get('condition') or '', 'pr': pr, 'q': x.get('quantity'),
            'd': bool(x.get('directSeller') or x.get('directProduct')),
            'lt': x.get('listingType') or '', 'ttl': ((x.get('customData') or {}).get('title') or '')[:80],
        })
    if os.environ.get('BL_DEBUG') and res:
        os.makedirs('bl_debug', exist_ok=True)
        json.dump(res[:3], open(f'bl_debug/{pid}.json', 'w'), indent=1)
    return out


def main():
    wa = json.load(open('wants_auto.json')).get('items', {})
    try:
        ver = json.load(open('verified.json')).get('items', {})
    except Exception:
        ver = {}
    rows = [(i, w) for i, w in wa.items() if str(w.get('tcgProductId') or '').isdigit()]
    rows.sort(key=lambda x: -(float(x[1].get('market') or 0)))
    rows = rows[:LIMIT]
    items, offers, errors = {}, {}, 0
    for n, (i, w) in enumerate(rows):
        pid = int(w['tcgProductId'])
        card = w.get('kind') != 'items'
        rev = bool(re.search(r'-rev$|reverseholofoil$', i))
        try:
            ls = query(pid, card, rev)
        except Exception as e:
            errors += 1
            items[i] = {'err': str(e)[:80]}
            if errors >= 15 and errors > n // 2:
                print('too many errors, stopping:', e, file=sys.stderr)
                break
            time.sleep(2)
            continue
        mkt = float(w.get('market') or 0)
        BAD = re.compile(r'chinese|japanese|korean|thai|indonesian|\\bjp\\b|\\bjpn\\b|promo|no pack|cards only|empty|opened|damag|read desc|art card|code card|proxy|custom|replica|lot of|bundle of', re.I)
        def sane(x):
            if x['ttl'] and BAD.search(x['ttl']):
                return False
            if not card and x['lt'] and x['lt'] != 'standard':
                return False  # sealed: custom listings are mostly partial contents (playmat only, no packs)
            # far below market: usually a partial / wrong product filed under this id, or a bait listing
            return not (mkt >= 20 and x['a'] < 0.6 * mkt)
        sus = [x for x in ls if not sane(x)]
        ls = [x for x in ls if sane(x)]
        ok = [x for x in ls if x['r'] >= MIN_RATING and x['n'] >= MIN_SALES]
        best = ok[0] if ok else None
        rec = {'pid': pid, 'nl': len(ls), 'ok': len(ok)}
        if sus:
            rec['sus'] = len(sus)
            rec['susLow'] = {k: sus[0][k] for k in ('a', 'sel', 'lt', 'ttl')}
        if best:
            rec['tcg'] = {k: best[k] for k in ('p', 's', 'a', 'sel', 'r', 'n', 'c', 'pr', 'd', 'lt')}
        elif ls:
            rec['cheapest'] = {k: ls[0][k] for k in ('p', 's', 'a', 'sel', 'r', 'n')}
            rec['why'] = 'no seller with 99%+ rating and 1000+ sales'
        offers[i] = ok
        items[i] = rec
        time.sleep(0.8)
    # eBay: cheapest live, known-shipping listing per ledger row from verified.json
    for it_id, v in ver.items():
        ref = v.get('ref')
        if not ref or not v.get('live') or not v.get('shipKnown') or v.get('ebayLive'):
            continue
        if v.get('landed') is None or not str(v.get('url', '')).startswith('https://www.ebay.com/itm/'):
            continue
        cur = items.setdefault(ref, {}).get('ebay')
        if cur is None or v['landed'] < cur['a']:
            items[ref]['ebay'] = {'a': round(float(v['landed']), 2), 'url': v['url'], 'fmt': v.get('format'),
                                  'ends': v.get('ends'), 'sel': v.get('seller'), 'r': v.get('feedbackPct'),
                                  'n': v.get('feedbackScore'), 'src': v.get('src')}
    # Seller baskets: wanted singles a seller offers at or under target; only when it beats separate buys
    bysel = {}
    for i, ok in offers.items():
        w = wa[i]
        tgt = float(w.get('target') or 0)
        if w.get('kind') == 'items' or w.get('status') != 'want' or tgt <= 0:
            continue
        seen = set()
        for x in ok:
            if x['key'] in seen or x['p'] > tgt:
                continue
            seen.add(x['key'])
            bysel.setdefault(x['key'], {'sel': x['sel'], 'r': x['r'], 'n': x['n'], 'cards': {}})
            b = bysel[x['key']]['cards']
            if i not in b or x['p'] < b[i]['p']:
                b[i] = {'p': x['p'], 's': x['s']}
    baskets = []
    for key, b in bysel.items():
        cards = b['cards']
        if len(cards) < 2:
            continue
        sep = sum(items[i]['tcg']['a'] for i in cards if items.get(i, {}).get('tcg'))
        tog = sum(c['p'] for c in cards.values()) + max(c['s'] for c in cards.values())
        if sep - tog <= 0.5:
            continue
        baskets.append({'sel': b['sel'], 'key': key, 'r': b['r'], 'n': b['n'],
                        'ids': sorted(cards), 'items': round(sum(c['p'] for c in cards.values()), 2),
                        'ship': round(max(c['s'] for c in cards.values()), 2), 'all': round(tog, 2),
                        'save': round(sep - tog, 2)})
    baskets.sort(key=lambda x: (-len(x['ids']), -x['save']))
    out = {'generated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
           'rule': 'TCGplayer: cheapest price+shipping from sellers with 99%+ rating and 1000+ sales; NM English for cards',
           'checked': len(rows), 'errors': errors, 'items': items, 'baskets': baskets[:8]}
    json.dump(out, open('best_listings.json', 'w'), separators=(',', ':'))
    print(f"checked {len(rows)}, errors {errors}, with tcg pick {sum(1 for v in items.values() if v.get('tcg'))}, "
          f"with ebay {sum(1 for v in items.values() if v.get('ebay'))}, baskets {len(baskets)}, "
          f"bytes {os.path.getsize('best_listings.json')}")
    if errors and errors >= len(rows) * 0.5:
        sys.exit(1)


if __name__ == '__main__':
    main()
