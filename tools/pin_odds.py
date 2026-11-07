"""Public sportsbook odds (Pinnacle's free guest API) for leagues FORGE does not capture elsewhere: game lines (moneyline, main spread, main total)
+ player props, each with the no-vig fair probability. Public market data only. -> data/live/odds/<league>/<YYYY-MM-DD>.json and latest.md
usage: python3 tools/pin_odds.py NHL NCAAF NCAAB"""
import os, sys, json, time, datetime as dt, requests
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'live', 'odds')
PIN = 'https://guest.api.arcadia.pinnacle.com/0.1'; KEY = 'CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', 'Accept': 'application/json', 'X-API-Key': KEY}
LEAGUES = {'NHL': [1456], 'NCAAF': [880], 'NCAAB': [493], 'NBA': [487], 'NFL': [889]}
def get(u):
    for k in range(3):
        try:
            r = requests.get(u, headers=UA, timeout=45)
            if r.status_code == 200: return r.json()
            print('HTTP', r.status_code, u, flush=True)
        except Exception as e: print('ERR', e, flush=True)
        time.sleep(3 + 3 * k)
    return None
def dec(a): return 1 + (a / 100 if a > 0 else 100 / -a)
def am(p): d = 1 / p; return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))
def fair(ps): inv = [1 / dec(p) for p in ps]; s = sum(inv); return [x / s for x in inv]
def league(name, lid):
    info = get(f'{PIN}/leagues/{lid}') or {}; M = get(f'{PIN}/leagues/{lid}/matchups') or []; K = get(f'{PIN}/leagues/{lid}/markets/straight') or []
    G = {m['id']: m for m in M if m.get('type') == 'matchup' and not m.get('parentId')}
    PR = {m['id']: m for m in M if m.get('parentId') in G and (m.get('special') or {}).get('category') == 'Player Props'}
    out = {gid: dict(away=next((p['name'] for p in g['participants'] if p['alignment'] == 'away'), None), home=next((p['name'] for p in g['participants'] if p['alignment'] == 'home'), None),
                     start=g.get('startTime'), lines=[], props=[]) for gid, g in G.items()}
    for k in K:
        if k.get('period') != 0 or k.get('isAlternate'): continue
        pr = k.get('prices') or []
        if len(pr) < 2: continue
        fp = fair([p['price'] for p in pr])
        if k['matchupId'] in G and k.get('type') in ('moneyline', 'spread', 'total'):
            for p, q in zip(pr, fp): out[k['matchupId']]['lines'].append(dict(type=k['type'], side=p.get('designation'), points=p.get('points'), american=p['price'], fair_prob=round(q, 4), fair_american=am(q)))
        elif k['matchupId'] in PR:
            m = PR[k['matchupId']]; side = {p['id']: p['name'] for p in m['participants']}
            for p, q in zip(pr, fp): out[m['parentId']]['props'].append(dict(desc=m['special'].get('description'), units=m.get('units'), outcome=side.get(p.get('participantId'), p.get('designation')),
                                                                          points=p.get('points'), american=p['price'], fair_prob=round(q, 4), fair_american=am(q)))
    return info.get('name'), list(out.values())
if __name__ == '__main__':
    now = dt.datetime.now(dt.timezone.utc); day = (now - dt.timedelta(hours=5)).strftime('%Y-%m-%d')
    for name in (sys.argv[1:] or ['NHL', 'NCAAF', 'NCAAB']):
        games = []; lname = []
        for lid in LEAGUES[name]:
            n, g = league(name, lid); lname.append(n); games += g
        d = os.path.join(ROOT, name.lower()); os.makedirs(d, exist_ok=True)
        json.dump(dict(read_utc=now.strftime('%Y-%m-%d %H:%M'), league=lname, games=games), open(os.path.join(d, f'{day}.json'), 'w'), indent=1)
        L = [f'# {name} ({lname}) Pinnacle no-vig, read {now:%Y-%m-%d %H:%M} UTC: {len(games)} games, {sum(len(g["props"]) for g in games)} props', '']
        for g in sorted(games, key=lambda g: g['start'] or '')[:80]:
            L.append(f"## {g['away']} @ {g['home']}  {g['start']}")
            L += [f"- {x['type']} {x['side']} {'' if x['points'] is None else x['points']}: {x['american']} (fair {x['fair_american']})" for x in g['lines']]
        open(os.path.join(d, 'latest.md'), 'w').write('\n'.join(L)); print(L[0], flush=True)
