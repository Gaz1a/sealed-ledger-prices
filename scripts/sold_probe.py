"""One-off probe: can eBay's APIs return the final price of ENDED auctions? Writes data/sold_probe.json."""
import json, os, sys, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_ebay_wants import token
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ids = list(json.load(open(os.path.join(ROOT, "data/sold_queue.json"))))[:6]
T = token(); out = {}
def call(url, h):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=25) as r:
            return r.status, r.read().decode()[:3000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:800]
    except Exception as e:
        return None, str(e)[:300]
for i in ids:
    out[i] = {
        "browse": call(f"https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id={i}",
                       {"Authorization": "Bearer " + T, "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}),
        "shopping": call(f"https://open.api.ebay.com/shopping?callname=GetSingleItem&responseencoding=JSON&siteid=0&version=1199&ItemID={i}&IncludeSelector=Details,ShippingCosts",
                         {"X-EBAY-API-IAF-TOKEN": T}),
    }
json.dump(out, open(os.path.join(ROOT, "data/sold_probe.json"), "w"), indent=1)
