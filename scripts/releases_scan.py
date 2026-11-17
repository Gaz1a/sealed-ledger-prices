#!/usr/bin/env python3
"""Weekly release calendar feed (Gaz, Nov 17): upcoming Pokémon TCG sets and products from free public sources.
Writes releases.json {generated, sources {name: status}, items [{date, name, lang, kind, source, url, confirmed}]}.
The Tracker copies upcoming items into the ledger's calendar (auto entries). Sources:
  tcgplayer-en / tcgplayer-jp : TCGplayer catalog via tcgcsv (sets with a publishedOn date from 30 days ago to 9 months ahead)
  serebii-en / serebii-jp    : Serebii set lists (English and Japanese release dates)
  pokemon-news               : official pokemon.com news page (TCG headlines naming a future date)
  (PokeBeach and the official RSS feeds block or 404 from GitHub; probed Nov 17)
  pokemon-card-jp            : Pokémon Japan's card site product list (Japanese release dates, 2-3 months ahead of English)
Each source fails independently; the status says which worked."""
import json, os, re, datetime, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TODAY = datetime.date.today()
MONTHS = {m: i for i, m in enumerate(["january","february","march","april","may","june","july","august","september","october","november","december"], 1)}
def fetch(url, accept="*/*"):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}), timeout=40) as r:
        return r.read()
def window(d): return d and TODAY - datetime.timedelta(days=30) <= d <= TODAY + datetime.timedelta(days=270)
def en_dates(t):
    out = []
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", t, re.I):
        try: out.append(datetime.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))))
        except ValueError: pass
    return out
items, status = [], {}
def add(date, name, lang, kind, source, url, confirmed):
    if window(date): items.append({"date": date.isoformat(), "name": name.strip()[:160], "lang": lang, "kind": kind, "source": source, "url": url, "confirmed": confirmed})
# 1. TCGplayer catalog (tcgcsv)
for cat, lang in ((3, "EN"), (85, "JP")):
    try:
        g = json.loads(fetch(f"https://tcgcsv.com/tcgplayer/{cat}/groups"))["results"]; n0 = len(items)
        g = sorted(g, key=lambda x: x["groupId"], reverse=True)[:40]   # newest groups only: old ones carry today's date
        for x in g:
            try: d = datetime.date.fromisoformat(x["publishedOn"][:10])
            except Exception: continue
            add(d, x["name"], lang, "set", "TCGplayer catalog", f"https://www.tcgplayer.com/search/pokemon{'-japan' if cat == 85 else ''}/{x.get('abbreviation') or ''}".rstrip('/'), True)
        status[f"tcgplayer-{lang.lower()}"] = f"ok ({len(items) - n0} in window)"
    except Exception as e: status[f"tcgplayer-{lang.lower()}"] = f"failed: {e}"[:120]
def text_of(h): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", h, flags=re.S)))
DATE = r"(" + "|".join(m.capitalize() for m in MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)"
# 2. Serebii set lists (English and Japanese): 'Delta Reign - November 6th 2026'
for name, url, lang in (("serebii-en", "https://www.serebii.net/card/english.shtml", "EN"), ("serebii-jp", "https://www.serebii.net/card/japanese.shtml", "JP")):
    try:
        t = text_of(fetch(url).decode("latin-1", "ignore")); n0 = len(items)
        for m in re.finditer(r"([A-Z0-9][\w'&:.\- ]{2,60}?)\s+\d{2,3}\s+" + DATE, t):   # table: name | cards | date
            try: d = datetime.date(int(m.group(4)), MONTHS[m.group(2).lower()], int(m.group(3)))
            except ValueError: continue
            add(d, m.group(1).strip(), lang, "set", "Serebii", url, False)
        status[name] = f"ok ({len(items) - n0} in window)"
    except Exception as e: status[name] = f"failed: {e}"[:120]
# 3. Official Pokemon news page: TCG headlines that name a date
try:
    t = text_of(fetch("https://www.pokemon.com/us/pokemon-news").decode("utf-8", "ignore")); n0 = len(items)
    for m in re.finditer(r"([^.!?]{0,160}\b(?:TCG|Trading Card Game|Elite Trainer|Booster|Collection|expansion)\b[^.!?]{0,160}?)" + DATE, t):
        try: d = datetime.date(int(m.group(4)), MONTHS[m.group(2).lower()], int(m.group(3)))
        except ValueError: continue
        if d > TODAY: add(d, m.group(1).strip()[-140:], "EN", "news", "pokemon.com news", "https://www.pokemon.com/us/pokemon-news", True)
    status["pokemon-news"] = f"ok ({len(items) - n0} dated)"
except Exception as e: status["pokemon-news"] = f"failed: {e}"[:120]
# 3b. Google News RSS (works from GitHub; the news job already uses it): headlines and snippets that name a future date
for name, q in (("googlenews-release", '"Pokemon TCG" "release date"'), ("googlenews-preorder", '"Pokemon TCG" preorder release'), ("googlenews-jp", '"Pokemon Card Game" Japan new set release')):
    try:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        root = ET.fromstring(fetch(url, "application/rss+xml")); n0 = len(items)
        for it in root.iter("item"):
            title = html.unescape(it.findtext("title") or ""); link = it.findtext("link") or ""
            body = text_of(it.findtext("description") or "")
            for d in en_dates(title + " " + body)[:2]:
                if d > TODAY: add(d, title, "EN", "news", "news (" + (it.findtext("source") or "Google News") + ")", link, False)
        status[name] = f"ok ({len(items) - n0} dated)"
    except Exception as e: status[name] = f"failed: {e}"[:120]
# 4. Pokémon Japan card site: product list with 発売日 (release date)
try:
    t = fetch("https://www.pokemon-card.com/info/").decode("utf-8", "ignore") + fetch("https://www.pokemon-card.com/products/").decode("utf-8", "ignore"); n0 = len(items)
    for m in re.finditer(r"(20\d\d)年\s*(\d{1,2})月\s*(\d{1,2})日", t):
        try: d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: continue
        near = text_of(t[max(0, m.start() - 500): m.end() + 500])
        if "発売" not in near: continue
        nm = [x.group(0).strip("「」") for x in re.finditer(r"「[^」]{3,60}」|[^\s「」]{0,30}(?:拡張パック|強化拡張パック|ハイクラスパック|スペシャルデッキ|スターターデッキ|ボックス|コレクション|セット)[^\s「」]{0,30}", near)]
        name = next((x for x in nm if len(x) > 3), "")
        if not name: continue
        add(d, html.unescape(name), "JP", "product", "pokemon-card.com", "https://www.pokemon-card.com/products/", True)
    status["pokemon-card-jp"] = f"ok ({len(items) - n0} dated)"
except Exception as e: status["pokemon-card-jp"] = f"failed: {e}"[:120]
# de-duplicate (same date + similar name), sort
seen, out = set(), []
for x in sorted(items, key=lambda x: (x["date"], not x["confirmed"])):
    k = (x["date"], re.sub(r"[^a-z0-9]", "", x["name"].lower())[:24])
    if k in seen: continue
    seen.add(k); out.append(x)
json.dump({"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "note": "Upcoming and recent (last 30 days) Pokemon TCG releases. confirmed = official or TCGplayer catalog; news items are reported dates, verify.",
           "sources": status, "items": out}, open(os.path.join(ROOT, "releases.json"), "w"), indent=1, ensure_ascii=False)
print(json.dumps(status, indent=1)); print(len(out), "items")
