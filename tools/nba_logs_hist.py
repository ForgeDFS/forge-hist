"""NBA box scores for every player (2026-10-22, Drew: "get lines on every single player ... if you cannot, research why"). Free ESPN public JSON, read
from GitHub's runners (probe 2026-10-22: site.api.espn.com 200; cdn.nba.com 403; stats.nba.com unreachable). This workspace cannot reach it.
For every date from 2025-10-20 to today: scoreboard -> each final game -> summary boxscore: per player minutes, points, FG, 3PT, FT, rebounds, assists,
turnovers, steals, blocks, starter / did-not-play (+ the reason ESPN gives). Incremental: games already saved are skipped.
  python3 tools/nba_logs.py [start YYYYMMDD]  -> nba/logs/espn_box.parquet (one row per player-game), nba/logs/injuries_latest.json (today's reports)"""
import os, sys, json, time, datetime as dt, urllib.request, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(ROOT, "data", "box"); os.makedirs(OUT, exist_ok=True); PQ = os.path.join(OUT, "espn_box_" + sys.argv[1] + ".parquet")
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', 'Accept': 'application/json'}
B = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
def get(url, tries=3):
    for k in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40))
        except Exception as e:
            if k == tries - 1: raise
            time.sleep(2 + 3 * k)
def num(x):
    try: return float(x)
    except Exception: return None
def made(x):
    try: m, a = str(x).split('-'); return float(m), float(a)
    except Exception: return None, None
def main(start='20251020', stop=None):
    old = pd.read_parquet(PQ) if os.path.exists(PQ) else pd.DataFrame(); have = set(old.game_id.astype(str)) if len(old) else set()
    d = dt.datetime.strptime(start, '%Y%m%d').date(); end = min(dt.datetime.now(dt.timezone.utc).date(), dt.datetime.strptime(stop, '%Y%m%d').date()) if stop else dt.datetime.now(dt.timezone.utc).date(); rows = []; n_new = 0; inj = {}
    while d <= end:
        try: sb = get(f'{B}/scoreboard?dates={d:%Y%m%d}')
        except Exception as e: print(d, 'scoreboard failed', e); d += dt.timedelta(days=1); continue
        for ev in sb.get('events') or []:
            gid = str(ev['id']); fin = (ev.get('status') or {}).get('type', {}).get('name') == 'STATUS_FINAL'
            if not fin and d >= end - dt.timedelta(days=1):                # upcoming / live: keep its injury report
                try: S = get(f'{B}/summary?event={gid}'); inj[gid] = dict(name=ev.get('name'), date=str(d), injuries=S.get('injuries') or [])
                except Exception: pass
                continue
            if not fin or gid in have: continue
            try: S = get(f'{B}/summary?event={gid}')
            except Exception as e: print(gid, 'summary failed', e); continue
            try: rows += parse(S, gid, d)
            except Exception as e: print(gid, 'parse failed', repr(e)[:300]); continue
            n_new += 1; have.add(gid); time.sleep(0.15)
            if n_new % 150 == 0: _save(old, rows); print('saved progress', n_new, 'games', flush=True)
        d += dt.timedelta(days=1)
    _save(old, rows)
    json.dump(dict(read_utc=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), games=inj), open(os.path.join(OUT, 'injuries_latest.json'), 'w'), indent=1)
    print('new games', n_new, 'rows', len(old) + len(rows), 'upcoming games with injury reports', len(inj))

def _save(old, rows):
    D = pd.concat([old, pd.DataFrame(rows)], ignore_index=True) if rows else old
    if len(D):
        for c in ('game_id', 'espn_id', 'player', 'team', 'opp', 'pos', 'reason', 'date'): D[c] = D[c].astype('string')
        D.drop_duplicates(['game_id', 'espn_id'], keep='last').to_parquet(PQ, index=False)

def parse(S, gid, d):
    rows = []
    if True:
            season = (S.get('header') or {}).get('season', {}).get('year'); stype = (S.get('header') or {}).get('season', {}).get('type')
            teams = [t['team']['abbreviation'] for t in (S.get('boxscore') or {}).get('players') or []]
            for k, T in enumerate((S.get('boxscore') or {}).get('players') or []):
                tm = T['team']['abbreviation']; opp = teams[1 - k] if len(teams) == 2 else None
                for st in T.get('statistics') or []:
                    lab = st.get('labels') or st.get('names') or []
                    for a in st.get('athletes') or []:
                        v = dict(zip(lab, a.get('stats') or [])); fgm, fga = made(v.get('FG')); tpm, tpa = made(v.get('3PT')); ftm, fta = made(v.get('FT'))
                        rows.append(dict(game_id=gid, date=str(d), season=season, season_type=stype, team=tm, opp=opp, player=a['athlete']['displayName'], espn_id=str(a['athlete']['id']),
                                         pos=(a['athlete'].get('position') or {}).get('abbreviation'), starter=bool(a.get('starter')), dnp=bool(a.get('didNotPlay')), reason=a.get('reason'),
                                         min=num(v.get('MIN')), pts=num(v.get('PTS')), fgm=fgm, fga=fga, tpm=tpm, tpa=tpa, ftm=ftm, fta=fta, reb=num(v.get('REB')), ast=num(v.get('AST')),
                                         tov=num(v.get('TO')), stl=num(v.get('STL')), blk=num(v.get('BLK')), oreb=num(v.get('OREB')), dreb=num(v.get('DREB'))))
    return rows
if __name__ == '__main__': main(*sys.argv[1:])
