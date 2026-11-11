"""NBA props capture (2026-10-21, Drew: "models for everything Vegas has player props on"). Runs on a GitHub runner (this workspace cannot reach the books).
Dumps EVERY open FanDuel NBA market (player points / rebounds / assists / threes / PRA and other combos / steals / blocks / double-doubles, game lines,
team totals) plus Pinnacle's NBA player props and lines, raw and lossless, one snapshot per run:  odds_free/nba/<YYYY-MM-DD>/<HHMMZ>.json
usage: python3 tools/nba_props.py"""
import os, json, re, time, datetime as dt, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', 'Accept': 'application/json'}
FD = 'https://sbapi.oh.sportsbook.fanduel.com/api'; AK = 'FhMFpcPWXMeyZxOx'
PIN = 'https://guest.api.arcadia.pinnacle.com/0.1'; PK = 'CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R'
TABS = [None, 'player-points', 'player-rebounds', 'player-assists', 'player-threes', 'player-combos', 'player-defense', 'player-props', 'popular', 'quick-bets', 'game-lines', 'team-props']
def get(u, h=None):
    for k in range(3):
        try:
            r = requests.get(u, headers=dict(UA, **(h or {})), timeout=45)
            if r.status_code == 200: return r.json()
            print('HTTP', r.status_code, u[:110])
        except Exception as e: print('ERR', e, u[:110])
        time.sleep(2 + 3 * k)
def odds(r):
    try: return float(r['winRunnerOdds']['trueOdds']['decimalOdds']['decimalOdds'])
    except Exception: return None
def fanduel():
    d = get(f'{FD}/content-managed-page?page=CUSTOM&customPageId=nba&_ak={AK}') or {}
    ev = {e['eventId']: e for e in ((d.get('attachments') or {}).get('events') or {}).values() if ' @ ' in e.get('name', '')}
    out = []
    for eid, e in ev.items():
        mk = {}; tabs_seen = []
        base = get(f'{FD}/event-page?_ak={AK}&eventId={eid}') or {}
        lay = json.dumps(base.get('layout') or {}); found = sorted(set(re.findall(r'"([a-z0-9]+(?:-[a-z0-9]+)+)"', lay)))   # tab slugs named in the page layout
        for tab in TABS + [t for t in found if t not in TABS][:25]:
            dd = base if tab is None else get(f'{FD}/event-page?_ak={AK}&eventId={eid}&tab={tab}')
            if dd and (dd.get('attachments') or {}).get('markets'): mk.update(dd['attachments']['markets']); tabs_seen.append(tab or 'main')
        M = [dict(id=k, type=m.get('marketType'), name=m.get('marketName'), status=m.get('marketStatus'), inplay=m.get('inPlay'),
                  runners=[dict(name=r.get('runnerName'), hcp=r.get('handicap'), odds=odds(r), status=r.get('runnerStatus'), logo=r.get('secondaryLogo') or r.get('logo')) for r in m.get('runners') or []])
             for k, m in mk.items() if m.get('marketStatus') == 'OPEN' and not m.get('inPlay')]
        out.append(dict(event_id=eid, name=e['name'], open=e.get('openDate'), tabs=tabs_seen, markets=M)); print(e['name'], len(M), 'markets', tabs_seen, flush=True)
    return out
def draftkings():
    """(2026-10-21, Drew bets on DraftKings) DraftKings sportsbook NBA lines, raw. Probed hosts/states; returns {url: json} for any that answer."""
    out = {}
    for st in ('dkusoh', 'dkusnj', 'dkuspa', 'dkusil'):
        for path in ('leagues/42648', 'leagues/42648/categories/1215', 'leagues/42648/categories/1216', 'leagues/42648/categories/1217', 'leagues/42648/categories/1218', 'leagues/42648/categories/583'):
            u = f'https://sportsbook-nash.draftkings.com/api/sportscontent/{st}/v1/{path}'
            try:
                r = requests.get(u, headers=dict(UA, Origin='https://sportsbook.draftkings.com', Referer='https://sportsbook.draftkings.com/'), timeout=30); print('DK', r.status_code, u, flush=True)
                if r.status_code == 200: out[u] = r.json()
            except Exception as e: print('DK ERR', e, u)
        if out: break
    return out
def pinnacle():
    H = {'X-API-Key': PK}; return dict(matchups=get(f'{PIN}/leagues/487/matchups', H), markets=get(f'{PIN}/leagues/487/markets/straight', H))
if __name__ == '__main__':
    now = dt.datetime.now(dt.timezone.utc); D = os.path.join(ROOT, 'data', 'live', 'odds_free', 'nba', now.strftime('%Y-%m-%d')); os.makedirs(D, exist_ok=True)
    snap = dict(read_utc=now.strftime('%Y-%m-%dT%H:%M:%SZ'), fanduel=fanduel(), pinnacle=pinnacle(), draftkings=draftkings())
    p = os.path.join(D, now.strftime('%H%MZ') + '.json'); json.dump(snap, open(p, 'w'), separators=(',', ':'))
    print('saved', p, os.path.getsize(p) // 1000, 'KB;', len(snap['fanduel']), 'FanDuel games')
