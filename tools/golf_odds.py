"""Public golf odds from Pinnacle's free guest API (2026-11-18, FORGE PGA v0): every golf league's matchups (incl. outright 'specials' such as
winner / top-N / make cut, and head-to-head matchups) + straight markets. Public market data only. -> data/live/odds/golf/<YYYY-MM-DD>_raw.json"""
import os, json, datetime as dt, requests, time
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'live', 'odds', 'golf')
PIN = 'https://guest.api.arcadia.pinnacle.com/0.1'
H = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/126', 'Accept': 'application/json', 'X-API-Key': 'CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R'}
def get(u):
    for k in range(3):
        try:
            r = requests.get(u, headers=H, timeout=45)
            if r.status_code == 200: return r.json()
            print('HTTP', r.status_code, u)
        except Exception as e: print('ERR', e)
        time.sleep(3 + 3 * k)
    return None
now = dt.datetime.now(dt.timezone.utc); day = (now - dt.timedelta(hours=5)).strftime('%Y-%m-%d')
sports = get(f'{PIN}/sports') or []; gid = next((s['id'] for s in sports if str(s.get('name', '')).lower() == 'golf'), None)
print('golf sport id', gid)
L = get(f'{PIN}/sports/{gid}/leagues?all=false') or [] if gid else []
out = dict(read_utc=now.strftime('%Y-%m-%d %H:%M'), sport_id=gid, leagues=[])
for l in L:
    out['leagues'].append(dict(id=l['id'], name=l['name'], matchups=get(f"{PIN}/leagues/{l['id']}/matchups") or [], markets=get(f"{PIN}/leagues/{l['id']}/markets/straight") or []))
    time.sleep(1)
os.makedirs(ROOT, exist_ok=True); json.dump(out, open(os.path.join(ROOT, f'{day}_raw.json'), 'w'))
print('leagues', [x['name'] for x in out['leagues']], 'matchups', sum(len(x['matchups']) for x in out['leagues']), 'markets', sum(len(x['markets']) for x in out['leagues']))
