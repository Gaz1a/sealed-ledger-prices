"""Read-only discovery of Devir Pokemon booklet product pages: robots.txt sitemaps only (no search pages, no scraping around blocks), then a small URL-pattern probe on devir.pt/cubosluminosos.pt
for deck numbers. Honest UA, 1-2 s between requests. Output devir_discovery.json."""
import json, re, time, urllib.request, urllib.parse, urllib.robotparser, urllib.error, gzip, io
UA = "sealed-ledger-stock-check/1.0 (personal collection tracker; one request per page per day)"
SITES = ["https://devir.pt", "https://cubosluminosos.pt", "https://americana.pt", "https://forretas.com", "https://www.wook.pt", "https://www.bertrand.pt", "https://www.worten.pt", "https://www.shop4nerds.pt", "https://www.devir.com.br"]
NAMES = {"bk-golem": "golem", "bk-hooh": "ho-oh", "bk-lugia": "lugia", "bk-machamp": "machamp", "bk-omastar": "omastar", "bk-ralts": "ralts", "bk-treecko": "treecko", "bk-exploud": "exploud", "bk-mudkip": "mudkip", "bk-rayquaza": "rayquaza", "bk-torchic": "torchic", "h-gengar-deck": "gengar"}
def get(u, n=3000000):
    time.sleep(1.5)
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Encoding": "identity"}), timeout=40) as r:
            b = r.read(n)
            if u.endswith(".gz"):
                try: b = gzip.decompress(b)
                except Exception: pass
            return r.status, b.decode("utf-8", "replace")
    except urllib.error.HTTPError as e: return e.code, ""
    except Exception as e: return type(e).__name__, ""
out = {"sitemaps": {}, "candidates": [], "pattern": {}}
KW = re.compile(r"origem-das-lendas|livro-ilustrado|estampas-ilustradas|baralho-\d+", re.I)
for base in SITES:
    rec = {"robots": None, "sitemapUrls": [], "fetched": 0, "hits": 0}
    rp = urllib.robotparser.RobotFileParser()
    try: rp.set_url(base + "/robots.txt"); rp.read(); rec["robots"] = "read"
    except Exception: rec["robots"] = "unreadable"
    sms = list(rp.site_maps() or []) if rec["robots"] == "read" else []
    sms = sms or [base + "/sitemap.xml"]
    seen, queue = set(), sms[:3]
    while queue and rec["fetched"] < 12:
        u = queue.pop(0)
        if u in seen: continue
        seen.add(u)
        if rec["robots"] == "read" and not rp.can_fetch(UA, u): rec["sitemapUrls"].append([u, "disallowed"]); continue
        code, txt = get(u); rec["fetched"] += 1; rec["sitemapUrls"].append([u, code])
        if code != 200: continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", txt)
        for l in locs:
            if l.endswith((".xml", ".xml.gz")) and re.search(r"product|produto|item|pokemon|jogo|brinqued|livro", l, re.I): queue.append(l)
            elif KW.search(l) and re.search(r"pokemon", l, re.I):
                out["candidates"].append({"site": base, "url": l}); rec["hits"] += 1
    out["sitemaps"][base] = rec
# deck-number pattern probe (only sites whose robots allow the path)
for base in ("https://devir.pt", "https://cubosluminosos.pt"):
    rp = urllib.robotparser.RobotFileParser()
    try: rp.set_url(base + "/robots.txt"); rp.read()
    except Exception: continue
    for rid, nm in NAMES.items():
        if rid in ("h-gengar-deck", "bk-machamp", "bk-omastar"): continue
        for n in range(1, 17):
            u = f"{base}/pokemon-baralho-{n:02d}-origem-das-lendas-{nm}" if False else f"{base}/pokemon-baralho-{n}-origem-das-lendas-{nm}"
            if not rp.can_fetch(UA, u): out["pattern"][u] = "disallowed"; break
            code, txt = get(u, 600000)
            if code == 200 and nm in txt.lower():
                isbn = re.findall(r"97[89]\d{10}", txt); ref = re.findall(r"PKLIVLM\d+", txt)
                out["pattern"][u] = {"http": 200, "isbn": sorted(set(isbn))[:3], "ref": sorted(set(ref))[:2], "title": (re.search(r"<title[^>]*>(.*?)</title>", txt, re.S | re.I) or [0, ""])[1].strip()[:100]}
json.dump(out, open("devir_discovery.json", "w"), indent=1, ensure_ascii=False)
print(len(out["candidates"]), "sitemap candidates;", sum(1 for v in out["pattern"].values() if isinstance(v, dict)), "pattern hits")
