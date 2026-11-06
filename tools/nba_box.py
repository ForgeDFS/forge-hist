"""NBA box scores from ESPN's public JSON, one season per run -> data/box/nba_<season>.csv.
Columns: date, event, team, player, espn_id, min, pts, fg3m, reb, ast, stl, blk, tov, dk (DraftKings Classic points).
Resumable per date. Usage: python tools/nba_box.py 2024-10-22 2025-06-30"""
import sys, os, csv, time, datetime as dt, requests
SB = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={}'
SM = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={}'
F = ['date','event','team','opp','home','player','espn_id','starter','min','pts','fg3m','reb','ast','stl','blk','tov','dk']
def dk(p, t, r, a, s, b, to):
    x = p + 0.5*t + 1.25*r + 1.5*a + 2*s + 2*b - 0.5*to
    dd = sum(v >= 10 for v in (p, r, a, s, b)); return x + (1.5 if dd >= 2 else 0) + (3 if dd >= 3 else 0)
def num(v):
    try: return float(str(v).split('-')[0])
    except: return 0.0
def get(u):
    for i in range(4):
        try:
            r = requests.get(u, timeout=20)
            if r.status_code == 200: return r.json()
        except Exception: pass
        time.sleep(2 + 3*i)
    return None
def main(a, b):
    a, b = dt.date.fromisoformat(a), min(dt.date.fromisoformat(b), dt.date.today())
    os.makedirs('data/box', exist_ok=True); out = f'data/box/nba_{a.isoformat()}.csv'
    done = set()
    if os.path.exists(out): done = {r['date'] for r in csv.DictReader(open(out))}
    fh = open(out, 'a', newline=''); w = csv.DictWriter(fh, F)
    if not done: w.writeheader()
    d = a
    while d <= b:
        ds = d.isoformat()
        if ds in done: d += dt.timedelta(1); continue
        sb = get(SB.format(d.strftime('%Y%m%d'))) or {}
        for ev in sb.get('events', []):
            if ev.get('status', {}).get('type', {}).get('completed') is not True: continue
            sm = get(SM.format(ev['id'])); time.sleep(0.2)
            if not sm: continue
            comp = ev['competitions'][0]['competitors']
            side = {c['team']['abbreviation']: c.get('homeAway') for c in comp}
            for tb in sm.get('boxscore', {}).get('players', []):
                tm = tb['team']['abbreviation']; opp = [t for t in side if t != tm]
                st = tb['statistics'][0]; L = st.get('labels') or st.get('names'); ix = {k: i for i, k in enumerate(L)}
                for ath in st.get('athletes', []):
                    s = ath.get('stats') or []
                    if not s or ath.get('didNotPlay'): continue
                    g = lambda k: num(s[ix[k]]) if k in ix and ix[k] < len(s) else 0.0
                    p, t, r, av, sl, bl, to = g('PTS'), g('3PT'), g('REB'), g('AST'), g('STL'), g('BLK'), g('TO')
                    w.writerow(dict(date=ds, event=ev['id'], team=tm, opp=opp[0] if opp else '', home=int(side.get(tm) == 'home'),
                        player=ath['athlete']['displayName'], espn_id=ath['athlete']['id'], starter=int(bool(ath.get('starter'))),
                        min=g('MIN'), pts=p, fg3m=t, reb=r, ast=av, stl=sl, blk=bl, tov=to, dk=round(dk(p, t, r, av, sl, bl, to), 2)))
        fh.flush(); d += dt.timedelta(1); time.sleep(0.2)
if __name__ == '__main__': main(*sys.argv[1:3])
