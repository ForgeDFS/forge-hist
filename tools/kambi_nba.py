"""(2026-11-11 BOOKS-1) BetRivers (Kambi) NBA odds, raw and lossless: the NBA event list + every event's full bet offer (player props included).
One snapshot per run: data/live/odds_free/nba_betrivers/<YYYY-MM-DD>/<HHMMZ>.json. Public market data only."""
import os, json, datetime as dt, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); B = 'https://eu-offering-api.kambicdn.com/offering/v2018/rsiuspa'
Q = {'lang': 'en_US', 'market': 'US'}; H = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
now = dt.datetime.now(dt.timezone.utc); out = dict(read_utc=now.isoformat(), events=[])
L = requests.get(f'{B}/listView/basketball/nba.json', params=Q, headers=H, timeout=30).json()
for e in L.get('events', []):
    ev = e.get('event', {}); eid = ev.get('id')
    if not eid: continue
    try: bo = requests.get(f'{B}/betoffer/event/{eid}.json', params=dict(Q, includeParticipants='true'), headers=H, timeout=30).json()
    except Exception as x: bo = dict(error=repr(x)[:200])
    out['events'].append(dict(event=ev, betoffers=bo))
D = os.path.join(ROOT, 'data', 'live', 'odds_free', 'nba_betrivers', now.strftime('%Y-%m-%d')); os.makedirs(D, exist_ok=True)
json.dump(out, open(os.path.join(D, now.strftime('%H%MZ') + '.json'), 'w'), separators=(',', ':'))
n = sum(len((x['betoffers'] or {}).get('betOffers', []) or []) for x in out['events']); print('betrivers events', len(out['events']), 'bet offers', n)
