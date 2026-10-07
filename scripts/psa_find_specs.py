#!/usr/bin/env python3
"""Find PSA spec IDs automatically: eBay Browse (graded PSA listings -> certification numbers) -> PSA GetByCertNumber -> verify -> psa_specs.json.
Verification (all must hold): card number, year (+-1 of set release), subject/name tokens, language, edition (1st/Shadowless), set tokens. Never guesses.
Hand-added entries in psa_specs.json (anything not source 'auto') are never touched. Never prints secrets."""
import base64, json, os, re, sys, time, datetime, urllib.request, urllib.parse, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm
TODAY = datetime.date.today().isoformat()
PSA_TOKEN = os.environ.get("PSA_TOKEN", "")
CID, CSEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
DAILY = int(os.environ.get("PSA_DAILY_LIMIT", "90"))
FIND_BUDGET = int(os.environ.get("PSA_FIND_BUDGET", "40"))   # cert lookups per run; the rest of the daily budget is left for population calls
RETRY_DAYS = 14
STOP = {"the", "of", "and", "pokemon", "ex", "gx", "v", "vmax", "vstar", "holo", "rare", "reverse", "foil", "card", "promo", "full", "art", "alternate", "illustration", "special", "secret"}
LANG = re.compile(r"JAPANESE|KOREAN|CHINESE|GERMAN|FRENCH|ITALIAN|SPANISH|PORTUGUESE|DUTCH|THAI|INDONESIAN", re.I)

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def toks(s): return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 1 and w not in STOP}
def num_norm(n): return re.sub(r"^0+(?=\d)", "", (n or "").upper().strip())

class Stop(Exception): pass
psa_calls = 0
def http(url, hdr, data=None, tries=2):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr), timeout=40) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 401, 403) and "psacard" in url: raise Stop(f"PSA HTTP {e.code}")
            if e.code == 429: time.sleep(5); continue
            return e.code, None
        except Exception: time.sleep(2)
    return 0, None
def psa_cert(cert):
    global psa_calls
    if psa_calls >= FIND_BUDGET: raise Stop("find budget used")
    psa_calls += 1; time.sleep(1.1)
    st, j = http(f"https://api.psacard.com/publicapi/cert/GetByCertNumber/{cert}", {"Authorization": "Bearer " + PSA_TOKEN, "Accept": "application/json"})
    return (j or {}).get("PSACert") if isinstance(j, dict) else None
def ebay_token():
    st, j = http("https://api.ebay.com/identity/v1/oauth2/token", {"Authorization": "Basic " + base64.b64encode(f"{CID}:{CSEC}".encode()).decode(), "Content-Type": "application/x-www-form-urlencoded"},
                 urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode())
    return (j or {}).get("access_token")

def candidate_certs(H, name_core, number, tried):
    """Return distinct PSA cert numbers read from item specifics of graded listings."""
    out = []
    for grade in ("PSA 10", "PSA 9"):
        q = f"{name_core} {number} {grade}"
        st, j = http("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode({"q": q, "limit": 25}), H); time.sleep(0.4)
        if not j: continue
        n = 0
        for it in j.get("itemSummaries", []):
            t = (it.get("title") or "").lower()
            if "psa" not in t or number.split("/")[0].lstrip("0").lower() not in t: continue
            if not (toks(name_core) & toks(t)): continue
            if n >= 10: break
            n += 1
            st, d = http("https://api.ebay.com/buy/browse/v1/item/" + urllib.parse.quote(it["itemId"], safe=""), H); time.sleep(0.3)
            if not d: continue
            asp = {a.get("name", "").lower(): a.get("value", "") for a in d.get("localizedAspects", []) or []}
            if "psa" not in (asp.get("professional grader", "") or "").lower(): continue
            cert = re.sub(r"\D", "", asp.get("certification number", "") or "")
            if 7 <= len(cert) <= 9 and cert not in out and cert not in tried: out.append(cert)
            if len(out) >= 3: return out
    return out

def verify(c, cert):
    """Return (ok, reason). c = our card context; cert = PSACert dict from PSA."""
    g = lambda k: str(next((v for kk, v in cert.items() if kk.lower() == k.lower()), "") or "")
    spec, cn, year, brand, subj, var = g("SpecID"), num_norm(g("CardNumber")), g("Year"), g("Brand").upper(), g("Subject"), g("Variety").upper()
    if not spec.isdigit(): return False, "no SpecID"
    if c["number"] and cn != num_norm(c["number"].split("/")[0]): return False, f"card number {cn} != {c['number']}"
    if c["year"] and year.isdigit() and abs(int(year) - c["year"]) > 1: return False, f"year {year} vs set {c['year']}"
    if not (c["nameToks"] and c["nameToks"] <= toks(subj) | toks(brand) | toks(var)): return False, f"subject '{subj}' vs name"
    ours = c["name"].upper()
    if LANG.search(brand + " " + var + " " + subj) and "JAPAN" not in ours: return False, "language differs"
    if "JAPAN" in ours and "JAPANESE" not in (brand + var).upper(): return False, "language differs (expected Japanese)"
    ed = brand + " " + var
    for tag, key in (("1ST EDITION", "1ST EDITION"), ("SHADOWLESS", "SHADOWLESS")):
        if (key in ours) != (tag in ed): return False, f"edition mismatch ({tag})"
    if c["setToks"]:
        hit = c["setToks"] & toks(brand + " " + year)
        need = 1 if len(c["setToks"]) <= 2 else max(1, len(c["setToks"]) // 2)
        if len(hit) < need: return False, f"set mismatch ('{brand}' vs '{c['set']}')"
    return True, f"{year} {brand} {subj} #{cn} {var}".strip()

def main():
    if not (PSA_TOKEN and CID and CSEC): sys.exit("PSA_TOKEN / EBAY keys not set")
    specs = load("psa_specs.json", {}); state = load("psa_find_state.json", {"cards": {}})
    g = load("graded.json", {}).get("cards", {}); sg = {c["productId"]: c for c in load("untracked_singles.json", {}).get("cards", [])}
    gmap = load("group-map.json", {})
    groups = {x["groupId"]: x for x in (sm.get(f"{sm.BASE}/3/groups") or {}).get("results", [])}
    if state.get("callsDate") != TODAY: state["callsDate"], state["callsUsed"] = TODAY, 0
    global FIND_BUDGET
    FIND_BUDGET = min(FIND_BUDGET, max(0, DAILY - 20 - state["callsUsed"]))   # always leave >= 20 calls for population pulls
    order = sorted([(k, v) for k, v in g.items() if v.get("rawMarket")], key=lambda kv: -kv[1]["rawMarket"])[:60]
    H = {"Authorization": "Bearer " + (ebay_token() or ""), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    summary = {"confirmed": 0, "rejected": 0, "no_certs": 0, "skipped": 0}; stopped = None
    try:
        for cid, v in order:
            ent = specs.get(cid)
            if ent and not (isinstance(ent, dict) and ent.get("source") == "auto" and not ent.get("verified")): continue   # manual or already confirmed
            st = state["cards"].get(cid, {})
            if st.get("status") in ("rejected", "no_certs") and st.get("lastTried", "0") > (datetime.date.today() - datetime.timedelta(days=RETRY_DAYS)).isoformat():
                summary["skipped"] += 1; continue
            name = v["name"]; pid = v["productId"]
            grp = groups.get((gmap.get(str(pid)) or [0, 0])[1]) or groups.get((sg.get(pid) or {}).get("groupId"))
            setname = (grp or {}).get("name") or (sg.get(pid) or {}).get("set") or ""
            year = int(((grp or {}).get("publishedOn") or "0000")[:4]) or None
            m = re.search(r"(\d+[A-Za-z]*|TG\d+|GG\d+|SWSH\d+|SVP?\d+)\s*/\s*(\w+)", name) or None
            number = (m.group(0).replace(" ", "") if m else None) or (sg.get(pid) or {}).get("number")
            core = re.sub(r"\s*[-—(\[].*$", "", name).strip(); core = re.sub(r"\s+[\d/]+\s*.*$", "", core).strip()
            if not number or not core:
                state["cards"][cid] = {"status": "no_certs", "lastTried": TODAY, "reason": "no card number/name"}; summary["no_certs"] += 1; continue
            ctx = {"name": name, "number": number, "year": year, "set": setname, "nameToks": toks(core), "setToks": toks(re.sub(r"^[A-Za-z0-9\-\.]+:\s*", "", setname))}
            tried = set(st.get("certsTried", []))
            certs = candidate_certs(H, core, number, tried)
            rec = {"lastTried": TODAY, "certsTried": sorted(tried | set(certs)), "rejects": []}
            if not certs:
                rec["status"] = "no_certs"; state["cards"][cid] = rec; summary["no_certs"] += 1; continue
            for cert in certs:
                c = psa_cert(cert)
                if not c: rec["rejects"].append(f"{cert}: lookup failed"); continue
                ok, why = verify(ctx, c)
                if ok:
                    sid = int(next(v2 for k2, v2 in c.items() if k2.lower() == "specid"))
                    specs[cid] = {"specId": sid, "cert": cert, "verified": True, "source": "auto", "matched": why, "foundOn": TODAY}
                    rec["status"] = "confirmed"; summary["confirmed"] += 1; break
                rec["rejects"].append(f"{cert}: {why}")
            else:
                rec["status"] = "rejected"; summary["rejected"] += 1
            state["cards"][cid] = rec
    except Stop as e: stopped = str(e)
    state["callsUsed"] += psa_calls; state["lastRun"] = TODAY; state["stopped"] = stopped
    json.dump(specs, open("psa_specs.json", "w"), indent=1, sort_keys=True)
    json.dump(state, open("psa_find_state.json", "w"), indent=1, sort_keys=True)
    print(json.dumps(summary), "| psa cert calls", psa_calls, "| stopped:", stopped)
if __name__ == "__main__": main()
