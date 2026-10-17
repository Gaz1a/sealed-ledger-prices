"""Read-only probe: which Portuguese/Brazilian retailer search pages can be fetched (honest UA, robots.txt respected), and what do they say about the Devir Pokemon illustrated booklets?
One GET per URL; blocked/forbidden pages are skipped and reported, never worked around."""
import json, re, time, urllib.request, urllib.parse, urllib.robotparser, urllib.error
UA = "sealed-ledger-stock-check/1.0 (personal collection tracker; one request per page per day)"
ISBN = "9788575322611"
SITES = {
 "devir.pt": ["https://www.devir.pt/search?q={q}", "https://www.devir.pt/?s={q}"],
 "cubosluminosos.pt": ["https://www.cubosluminosos.pt/pesquisa?controller=search&s={q}", "https://www.cubosluminosos.pt/search?q={q}"],
 "americana.pt": ["https://www.americana.pt/search?q={q}", "https://www.americana.pt/?s={q}"],
 "worten.pt": ["https://www.worten.pt/search?query={q}"],
 "wook.pt": ["https://www.wook.pt/pesquisa/{q}"],
 "bertrand.pt": ["https://www.bertrand.pt/pesquisa/{q}"],
 "forretas.com": ["https://www.forretas.com/search?q={q}", "https://www.forretas.com/?s={q}"],
 "devir.com.br": ["https://www.devir.com.br/search?q={q}", "https://www.devir.com.br/?s={q}", "https://www.devir.com.br/busca?q={q}"],
 "mercadolivre.com.br": ["https://lista.mercadolivre.com.br/{qh}"],
}
QS = [ISBN, "Pokemon Livro Ilustrado Gengar", "Pokemon Estampas Ilustradas"]
out = {}
for site, pats in SITES.items():
    base = "https://" + pats[0].split("/")[2]
    rp = urllib.robotparser.RobotFileParser(); rec = {"robots": None, "tries": []}
    try:
        rp.set_url(base + "/robots.txt"); rp.read(); rec["robots"] = "read"
    except Exception as e: rec["robots"] = "unreadable " + type(e).__name__; rp = None
    for pat in pats:
        for q in QS:
            url = pat.format(q=urllib.parse.quote(q), qh=urllib.parse.quote(q.lower().replace(" ", "-")))
            t = {"url": url}
            if rp and not rp.can_fetch(UA, url): t["status"] = "disallowed by robots.txt"; rec["tries"].append(t); continue
            time.sleep(2)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-PT,pt;q=0.9"}), timeout=30) as r:
                    html = r.read(600000).decode("utf-8", "replace"); t["status"] = r.status; t["bytes"] = len(html)
            except urllib.error.HTTPError as e: t["status"] = e.code; rec["tries"].append(t); continue
            except Exception as e: t["status"] = type(e).__name__; rec["tries"].append(t); continue
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I); t["title"] = m.group(1).strip()[:120] if m else None
            t["hasGengar"] = bool(re.search(r"gengar", html, re.I)); t["hasISBN"] = ISBN in html
            t["snips"] = [re.sub(r"\s+", " ", html[max(0, x.start() - 150):x.end() + 250]) for x in re.finditer(r"gengar|livro ilustrado|estampas ilustradas", html, re.I)][:3]
            t["links"] = sorted(set(re.findall(r'href="([^"]*(?:gengar|ilustrad|estampas|9788575)[^"]*)"', html, re.I)))[:8]
            rec["tries"].append(t)
    out[site] = rec
json.dump(out, open("devir_retail_probe.json", "w"), indent=1, ensure_ascii=False)
