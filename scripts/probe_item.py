import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from scan_ebay_wants import get, token
H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
     "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DUS%2Czip%3D91505"}
for i in os.environ["IDS"].split(","):
    d = get("https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id=" + i, H, tries=2) or {}
    for k in ("description", "image", "additionalImages", "localizedAspects", "product", "seller", "primaryProductReviewRating", "shipToLocations", "shippingOptions", "itemLocation"): d.pop(k, None)
    print(i, json.dumps({k:(v if len(json.dumps(v))<400 else "<%d chars>"%len(json.dumps(v))) for k,v in d.items()}, indent=1))
