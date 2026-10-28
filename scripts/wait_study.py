#!/usr/bin/env python3
"""Wait test: when a price drops to or under target, does waiting get it cheaper, and for how long?

Part 1 (history backtest): every time an item's market crosses below its tier-rule ceiling
(of the trailing 30-day median), track the price 1/3/7/14/30 days later; split by segment,
price band and how fast it fell. Part 2 (live flags): recs docs that carry `follow`
({"d1": {"date", "market", "low", "ebayLow"}, ...}) written by the Tracker; compares the price
at flag time (price0) with each later point.

Usage: python3 -I scripts/wait_study.py <export dir with ledger/*.json [and recs/*.json]> [out.json]
Prints a plain summary; writes the numbers to out.json if given."""
import json,glob,datetime as dt,statistics as st,sys,collections
D=sys.argv[1]
def tier(m): return 1.0 if m<10 else .9 if m<100 else .85 if m<300 else .8
def seg_kind(d):
    i=d['id']
    if i.startswith(('gy-','mk-','kg-')): return 'collector singles'
    if i.startswith(('k-','bs-')): return 'vintage Kanto'
    if d.get('kind')=='items' or i.startswith(('bk-','rp-','w-','radar-','h-')) and d.get('kind')!='singles': return 'sealed'
    return 'modern singles'
H=[1,3,7,14,30]
ev=[]
for f in glob.glob(D+'/ledger/*.json'):
    d=json.load(open(f)); h=d.get('history') or []
    if len(h)<60: continue
    s={}
    for day,p in h:
        if isinstance(p,(int,float)) and p>0: s[dt.date.fromisoformat(day[:10])]=p
    if len(s)<60: continue
    days=sorted(s); a=days[0]; b=days[-1]
    ser=[];last=None;gap=0
    for k in range((b-a).days+1):
        x=a+dt.timedelta(k)
        if x in s: last=s[x];gap=0
        else: gap+=1
        ser.append(last if gap<=3 else None)
    if len(set(p for p in ser if p))<5: continue
    below=False
    for t in range(30,len(ser)-30):
        p=ser[t]
        if p is None: below=False; continue
        prior=[q for q in ser[t-30:t] if q]
        if len(prior)<20: continue
        med=st.median(prior); c=tier(med)*med
        if med<5: continue
        if p<=c and not below:
            fut=ser[t:t+31]
            if any(q is None for q in fut): below=True; continue
            p7=ser[t-7]
            e=dict(id=d['id'],seg=seg_kind(d),p=p,c=c,med=med,
                   band='<$20' if med<20 else '$20-100' if med<100 else '$100+',
                   pre='sharp drop' if p7 and p/p7<=0.9 else 'gradual')
            for k in H: e[f'r{k}']=fut[k]/p; e[f'min{k}']=min(fut[1:k+1])/p; e[f'miss{k}']=fut[k]>c
            # stabilise strategy: buy first day d>=1 where price did not fall vs previous day for 2 days in a row, max 30
            buy=None
            for dd in range(2,31):
                if fut[dd]>=fut[dd-1] and fut[dd-1]>=fut[dd-2]: buy=dd;break
            buy=buy or 30
            e['stab']=fut[buy]/p; e['stabday']=buy
            ev.append(e)
        below = p<=c
print('events',len(ev),'items',len({e['id'] for e in ev}))
def summ(g,name):
    if len(g)<8: print(f'{name}: n={len(g)} (too few)');return
    row=f'{name}: n={len(g)} items={len({e["id"] for e in g})}'
    for k in H:
        r=[e[f'r{k}'] for e in g]
        row+=f' | d{k} med {100*(st.median(r)-1):+.1f}% lower {100*sum(x<0.995 for x in r)/len(r):.0f}% miss {100*sum(e[f"miss{k}"] for e in g)/len(g):.0f}%'
    sb=[e['stab'] for e in g]
    row+=f' | stabilise: med {100*(st.median(sb)-1):+.1f}% day~{st.median([e["stabday"] for e in g]):.0f}'
    print(row)
summ(ev,'ALL')
for key in ('seg','band','pre'):
    for v in sorted({e[key] for e in ev}): summ([e for e in ev if e[key]==v],f'{key}={v}')
# ---- part 2: live flags with follow-up prices ----
flags=[]
for f in glob.glob(D+'/recs/*.json'):
    r=json.load(open(f)); fo=r.get('follow') or {}; p0=r.get('price0')
    if not fo or not p0: continue
    ref=r.get('ref') or ''
    seg='sealed' if r.get('kind')=='items' else 'collector singles' if ref.startswith(('gy-','mk-','kg-')) else 'vintage Kanto' if ref.startswith(('k-','bs-')) else 'singles'
    row={'ref':ref,'seg':seg,'source':r.get('source'),'p0':p0}
    for k in H:
        x=fo.get(f'd{k}') or {}
        cands=[v for v in (x.get('low'),x.get('ebayLow')) if isinstance(v,(int,float)) and v>0]
        if cands: row[f'r{k}']=min(cands)/p0   # cheapest listing then, landed, vs what we flagged
    flags.append(row)
print('\nLIVE FLAGS with follow-ups:',len(flags))
for seg in sorted({x['seg'] for x in flags}):
    g=[x for x in flags if x['seg']==seg]
    line=f'{seg}: n={len(g)}'
    for k in H:
        r=[x[f'r{k}'] for x in g if f'r{k}' in x]
        if len(r)>=5: line+=f' | d{k} med {100*(st.median(r)-1):+.1f}% cheaper-share {100*sum(v<0.97 for v in r)/len(r):.0f}% (n={len(r)})'
    print(line)
if len(sys.argv)>2:
    json.dump({'events':ev,'flags':flags},open(sys.argv[2],'w'))
