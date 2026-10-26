# Near Mint photo rubric (raw cards)

The ledger buys raw cards in Near Mint or Mint only. A buy must look like a PSA 8 (NM-MT) or better
in the photos; TCGplayer "Near Mint" is the floor, not the target. Seller-stated NM is never enough.

## Sources
- PSA grading standards (as republished at gamestop.com/psa): MINT 9, NM-MT 8, NM 7, EX-MT 6.
- CGC grading scale (cgccards.uk/card-grading/grading-scale): Mint 9, NM/Mint 8, Near Mint 7.
- TCGplayer Card Conditioning Overview (help.tcgplayer.com): Near Mint vs Lightly Played.

| Grade | Corners | Edges | Surface | Centering front / back |
|---|---|---|---|---|
| PSA 9 / CGC 9 | sharp, one minor flaw at most | slight minor flaws | one minor print spot | 60/40 / 90/10 |
| PSA 8 / CGC 8 (our bar) | sharp to the naked eye; slightest fraying on 1-2 corners | relatively smooth, minor touches of wear | original gloss, a few minor print spots | 65/35 / 90/10 |
| PSA 7 / CGC 7 | slight fraying / touch of wear on 3+ corners | slightly rough | slight surface wear on close look | 70/30 / 90/10 |
| TCGplayer NM | crisp corners | unblemished outside a few slight flaws | nearly unmarked; a couple of minor scratches | not defined |
| TCGplayer LP | minor wear | minor edge wear, scuffs | scuffs or scratches noticeable | not defined |

## Verdict from photos
- **PASS (buy):** front and back photos sharp enough to see edges; no visible whitening on any back edge
  (blue border stays solid blue to the edge; a speck or two at magnification is OK); corners sharp in the
  3x zooms (at most a hint of fraying on 1-2 corners); no crease, dent, bend, scratch line, scuff, dirt or
  silvering; holo shows no scratches where glare allows; front centering 65/35 or better if measurable.
  Right print confirmed from the front (set symbol, number, holo / reverse / non-holo, edition, not a
  reprint / Celebrations / metal card).
- **BORDERLINE (watch, not buy):** looks NM but a photo is too small/blurry/glared to judge, or one
  corner shows slight fraying with everything else clean, or centering 65/35-70/30. Action: ask the
  seller for sharp back photos, or pass.
- **FAIL:** any visible white along a back edge or corner, rounded or soft corners, scratches, scuffs,
  print lines on the back, bends, wrong print, no back photo, stock photo.

## Measured aids (scripts/photo_check.py, photos branch)
- Back whitening % per side (outer 3.5% band) and per corner (7% squares). A clean back is ~0%.
  Flag thresholds (side > 4%, corner > 20% because rounded corners leak background; a clean back measured 0-1%, one clean-looking scan 3.4% on one side) are uncalibrated: tune them against cards Gaz rejects or
  accepts (log each verdict on the recs doc as photoCheck).
- Front centering from border widths; n/a on full-art or borderless cards.
- Card height in pixels: under 700px is too small to judge edges.
