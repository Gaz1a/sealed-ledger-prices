#!/usr/bin/env python3
"""Daily retailer in-stock check for the Portuguese/Brazilian Devir Pokemon illustrated booklets -> stock_check.json.
Honest UA, one request per page per day, robots.txt respected: disallowed or blocked pages are skipped and reported, never worked around.
(1) product-page URLs listed in devir_retail_urls.json: reads schema.org availability/price (JSON-LD / microdata), falls back to sold-out wording.
(2) Devir Brasil (devir.com.br) WordPress search for each booklet name (static HTML, robots-allowed).
(3) per-site status: robots.txt verdict for each retailer's search path, so skipped sites are reported every day."""
import json, os, re, time, datetime, html, urllib.request, urllib.parse, urllib.robotparser, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "sealed-ledger-stock-check/1.0 (personal collection tracker; one request per page per day)"
TODAY = datetime.date.today().isoformat()
NAMES = {"bk-golem": "Golem", "bk-hooh": "Ho-Oh", "bk-lugia": "Lugia", "bk-machamp": "Machamp", "bk-omastar": "Omastar", "bk-ralts": "Ralts", "bk-treecko": "Treecko",
         "bk-exploud": "Exploud", "bk-mudkip": "Mudkip", "bk-rayquaza": "Rayquaza", "bk-torchic": "Torchic", "h-gengar-deck": "Gengar"}
SITES = {"devir.pt": "https://www.devir.pt/search?q=x", "cubosluminosos.pt": "https://www.cubosluminosos.pt/search?q=x", "americana.pt": "https://www.americana.pt/?s=x",
         "worten.pt": "https://www.worten.pt/search?query=x", "wook.pt": "https://www.wook.pt/pesquisa/x", "bertrand.pt": "https://www.bertrand.pt/pesquisa/x",
         "forretas.com": "https://www.forretas.com/search?q=x", "devir.com.br": "https://www.devir.com.br/?s=x", "mercadolivre.com.br": "https://lista.mercadolivre.com.br/x"}
JS_ONLY = {"americana.pt": "search results are rendered by JavaScript (page loads, no readable results)", "forretas.com": "price-comparison site rendered by JavaScript (no readable results)"}
def robots(url):
    p = urllib.parse.urlparse(url); rp = urllib.robotparser.RobotFileParser()
    try: rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt"); rp.read()
    except Exception: return None
    return rp.can_fetch(UA, url)
def fetch(url):
    time.sleep(2)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-PT,pt;q=0.9"}), timeout=30) as r: return r.status, r.read(800000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e: return e.code, ""
    except Exception as e: return type(e).__name__, ""
def ldict(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
cfg = ldict("devir_retail_urls.json", {"urls": {}, "isbn": {}})
out = {"generated": TODAY, "label": "unverified: retailer pages, stock can change within the day", "sites": {}, "products": [], "devirBrasil": {}, "inStock": []}
for s, u in SITES.items():
    ok = robots(u)
    out["sites"][s] = {"robots": "allowed" if ok else "DISALLOWED (skipped)" if ok is False else "robots.txt unreadable (skipped)", "note": JS_ONLY.get(s)}
for rid, urls in cfg.get("urls", {}).items():
    for url in urls:
        host = urllib.parse.urlparse(url).netloc.replace("www.", ""); rec = {"id": rid, "name": NAMES.get(rid), "url": url, "site": host}
        ok = robots(url)
        if ok is not True: rec["status"] = "skipped: robots.txt disallows or unreadable"; out["products"].append(rec); continue
        code, h = fetch(url); rec["http"] = code
        if code != 200: rec["status"] = "skipped: HTTP %s (blocked or missing)" % code; out["products"].append(rec); continue
        isbn = cfg.get("isbn", {}).get(rid); rec["isbnOnPage"] = (isbn in h) if isbn else None
        avail = re.findall(r'"availability"\s*:\s*"(?:https?://schema\.org/)?(\w+)"', h) or re.findall(r'itemprop="availability"[^>]*href="(?:https?://schema\.org/)?(\w+)"', h)
        price = re.findall(r'"price"\s*:\s*"?([0-9]+[.,]?[0-9]*)"?', h); cur = re.findall(r'"priceCurrency"\s*:\s*"(\w+)"', h)
        if avail: st = "in_stock" if re.search(r"InStock|LimitedAvailability|OnlineOnly|PreOrder", avail[0]) else "out_of_stock"
        elif re.search(r"esgotado|indispon[ií]vel|sold out|out of stock|sem stock", h, re.I): st = "out_of_stock"
        elif re.search(r"adicionar ao carrinho|comprar agora|em stock|dispon[ií]vel", h, re.I): st = "in_stock (wording only)"
        else: st = "unknown"
        rec.update({"stock": st, "price": float(price[0].replace(",", ".")) if price else None, "currency": cur[0] if cur else None, "title": (re.search(r"<title[^>]*>(.*?)</title>", h, re.S | re.I) or [None, None])[1]})
        if rec["title"]: rec["title"] = html.unescape(re.sub(r"\s+", " ", rec["title"]))[:120]
        out["products"].append(rec)
        bad_isbn = rec["isbnOnPage"] is False
        if st.startswith("in_stock") and rec["price"] is not None and rec["currency"] in ("EUR", None) and rec["price"] <= 30 and not bad_isbn:
            out["inStock"].append({**rec, "shippingToBurbank": "not shown on product page; check checkout", "allInStatus": "shipping unknown"})
# Devir Brasil static search for each booklet
if out["sites"]["devir.com.br"]["robots"] == "allowed":
    for rid, nm in NAMES.items():
        q = urllib.parse.quote(f"Pokemon Livro Ilustrado {nm}"); code, h = fetch(f"https://www.devir.com.br/?s={q}")
        links = sorted({u for u, t in re.findall(r'href="(https://(?:www\.)?devir\.com\.br/[^"#?]+)"[^>]*>([^<]*)', h) if re.search(re.escape(nm), t, re.I) and "/search/" not in u})
        out["devirBrasil"][rid] = {"http": code, "productLinks": links[:5]}
json.dump(out, open(os.path.join(ROOT, "stock_check.json"), "w"), indent=1, ensure_ascii=False)
print({s: v["robots"] for s, v in out["sites"].items()}, "products", len(out["products"]), "inStock", len(out["inStock"]), "devirBrasil hits", sum(1 for v in out["devirBrasil"].values() if v["productLinks"]))
