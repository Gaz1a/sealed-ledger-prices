import sys, os, json, time
sys.path.insert(0, "scripts")
import fanatics_scan as fs
S = fs.Search(); cut = int(time.time()) - 10*86400
base = 'category:"Pokémon" AND status:"Sold"'
out = []
for label, req in [("numeric end", {"query": "booster box", "hitsPerPage": 3, "filters": base, "numericFilters": f"auctionEndDatetime>{cut}"}),
                   ("in filter", {"query": "booster box", "hitsPerPage": 3, "filters": base + f" AND auctionEndDatetime > {cut}"}),
                   ("week", {"query": "booster box", "hitsPerPage": 3, "filters": base + " AND auctionEndYearWeek >= 202644"}),
                   ("plain", {"query": "booster box", "hitsPerPage": 3, "filters": base})]:
    r = S.multi([req])[0]
    out.append(f"{label}: nb {r.get('nbHits')} msg {r.get('message')} first {[ (h['title'][:50], h.get('auctionEndDatetime')) for h in r.get('hits',[])[:3]]}")
idx = []
for name in ["prod_item_state_v1_sale_date_desc", "prod_item_state_v1_end_date_desc", "prod_item_state_v1_recent_desc"]:
    S2 = fs.INDEX; fs.INDEX = name
    r = S.multi([{"query": "booster box", "hitsPerPage": 2, "filters": base}])[0]; fs.INDEX = S2
    out.append(f"{name}: nb {r.get('nbHits')} msg {r.get('message')} {[ (h['title'][:40], h.get('auctionEndDatetime')) for h in r.get('hits',[])[:2]]}")
open("fan_probe.txt", "w").write("\n".join(out))
