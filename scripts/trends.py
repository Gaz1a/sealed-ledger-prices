#!/usr/bin/env python3
"""HYPE SIGNAL ONLY - never a price source. Weekly Google Trends (pytrends, unofficial), YouTube Data API v3 and Reddit (official OAuth, if configured)
-> trends.json. Every source fails soft."""
import base64, json, os, re, sys, time, datetime, urllib.request, urllib.parse, urllib.error
TODAY = datetime.date.today()
YT, RID, RSEC = os.environ.get("YOUTUBE_API_KEY"), os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def terms():
    g = load("graded.json", {}).get("cards", {}); seen, out = set(), []
    for k, v in sorted(g.items(), key=lambda kv: -(kv[1].get("rawMarket") or 0)):
        base = re.sub(r"\s*[-—(].*$", "", v["name"]).strip()
        base = re.sub(r"\s+\d+/\d+.*$", "", base)
        if len(base) > 3 and base.lower() not in seen:
            seen.add(base.lower()); out.append(base + " pokemon card")
        if len(out) >= 20: break
    out += [s + " pokemon" for s in ("Ascended Heroes", "Chaos Rising", "Perfect Order", "Pitch Black", "Prismatic Evolutions")]
    return out
def getj(url, hdr=None, data=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr or {"User-Agent": "sealed-ledger/1.0"}), timeout=40) as r:
            return json.loads(r.read().decode())
    except Exception: return None
def google(ts):
    res = {}
    try:
        from pytrends.request import TrendReq
    except Exception as e: return res, f"pytrends unavailable: {type(e).__name__}"
    anchor, err = "Charizard card", None
    for i in range(0, len(ts), 4):
        batch = ts[i:i + 4]
        for attempt in range(3):
            try:
                pt = TrendReq(hl="en-US", tz=420, timeout=(10, 30)); pt.build_payload([anchor] + batch, timeframe="today 3-m", geo="US")
                df = pt.interest_over_time()
                if df.empty: break
                a = df[anchor].replace(0, 1)
                for t in batch:
                    s = (df[t] / a * 100).round(1).tolist(); n = len(s)
                    res[t] = {"latest": s[-1], "last4wAvg": round(sum(s[-4:]) / 4, 1) if n >= 4 else None, "prior4wAvg": round(sum(s[-8:-4]) / 4, 1) if n >= 8 else None,
                              "relativeToAnchor": "indexed to 'Charizard card' = 100"}
                break
            except Exception as e:
                err = f"{type(e).__name__}"; time.sleep(30 * (attempt + 1))
        time.sleep(15)
    return res, err
def youtube(ts):
    if not YT: return {}, "YOUTUBE_API_KEY not set"
    res, since = {}, (datetime.datetime.utcnow() - datetime.timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for t in ts:
        j = getj("https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode({"part": "id", "q": t, "type": "video", "publishedAfter": since, "maxResults": 50, "key": YT}))
        if not j: res[t] = None; continue
        ids = [x["id"]["videoId"] for x in j.get("items", []) if x.get("id", {}).get("videoId")]
        views = 0
        if ids:
            v = getj("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode({"part": "statistics", "id": ",".join(ids), "key": YT}))
            views = sum(int(x.get("statistics", {}).get("viewCount", 0)) for x in (v or {}).get("items", []))
        res[t] = {"videos14d": len(ids), "apiEstimateTotal": (j.get("pageInfo") or {}).get("totalResults"), "views14d": views}
        time.sleep(0.3)
    return res, None
def reddit(ts):
    if not (RID and RSEC): return {}, "REDDIT_CLIENT_ID/SECRET not set (official OAuth required; unauthenticated access not used)"
    ua = {"User-Agent": "sealed-ledger/1.0 (personal research)", "Authorization": "Basic " + base64.b64encode(f"{RID}:{RSEC}".encode()).decode()}
    tok = getj("https://www.reddit.com/api/v1/access_token", ua, b"grant_type=client_credentials")
    if not tok or "access_token" not in tok: return {}, "reddit token request failed"
    H = {"User-Agent": ua["User-Agent"], "Authorization": "bearer " + tok["access_token"]}; res = {}
    cut = time.time() - 14 * 86400
    for t in ts:
        q = t.replace(" pokemon card", "").replace(" pokemon", ""); cnt = {}
        for sub in ("PokemonTCGInvest", "PkmnTCG"):
            j = getj(f"https://oauth.reddit.com/r/{sub}/search?" + urllib.parse.urlencode({"q": q, "restrict_sr": 1, "sort": "new", "t": "month", "limit": 100}), H)
            cnt[sub] = None if not j else sum(1 for c in j["data"]["children"] if c["data"]["created_utc"] >= cut)
            time.sleep(1.1)
        res[t] = cnt
    return res, None
def main():
    ts = terms(); g, ge = google(ts); y, ye = youtube(ts); r, re_ = reddit(ts)
    out = {"generated": TODAY.isoformat(), "label": "HYPE SIGNAL ONLY - not a price source. Do not use for valuations.",
           "terms": ts, "sourceStatus": {"googleTrends": ge or "ok", "youtube": ye or "ok", "reddit": re_ or "ok"},
           "items": {t: {"googleTrends": g.get(t), "youtube14d": y.get(t), "reddit14d": r.get(t)} for t in ts}}
    json.dump(out, open("trends.json", "w"), indent=1)
    print("terms", len(ts), "| trends", len(g), "| youtube", sum(1 for v in y.values() if v), "| reddit", sum(1 for v in r.values() if v), "|", out["sourceStatus"])
if __name__ == "__main__": main()
