"""Public UFC odds from Pinnacle's free guest API: raw matchups + straight markets for every MMA league named UFC (sport 22).
Public market data only. -> data/live/odds/ufc/<YYYY-MM-DD>_raw.json"""
import os, json, datetime as dt, requests, time
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'live', 'odds', 'ufc')
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
L = [l for l in (get(f'{PIN}/sports/22/leagues?all=false') or []) if 'UFC' in (l.get('name') or '').upper()]
out = dict(read_utc=now.strftime('%Y-%m-%d %H:%M'), leagues=[])
for l in L:
    out['leagues'].append(dict(id=l['id'], name=l['name'], matchups=get(f"{PIN}/leagues/{l['id']}/matchups") or [], markets=get(f"{PIN}/leagues/{l['id']}/markets/straight") or []))
os.makedirs(ROOT, exist_ok=True); json.dump(out, open(os.path.join(ROOT, f'{day}_raw.json'), 'w'))
print('leagues', len(L), 'matchups', sum(len(x['matchups']) for x in out['leagues']), 'markets', sum(len(x['markets']) for x in out['leagues']))
