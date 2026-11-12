"""FORGE free odds feed (2026-10-16; PREREG_FREEFEED_2026-10-16). OddsPapi's free plan (250 requests/month) ran out and Drew can't pay right now.
A GitHub runner can read two public sportsbook feeds with no key: FanDuel's sportsbook JSON and Pinnacle's guest API (probe 2026-10-16; DraftKings'
sportsbook returns 403). This module

  capture(games)       one snapshot per game -> odds_free/<season>/W<wk>_<AWAY>_at_<HOME>.jsonl (append-only; each line = one read, stamped when read)
  export_pull(game)    every snapshot so far -> a pull zip in the OddsPapi layout forge_market.board() reads
                       (raw/fixtures.json, raw/markets.json, raw/<AWAY>_at_<HOME>_historical.json, raw/pid_names.json)

What goes in (same markets FORGE's market projections v1.1 use; FanDuel is the book, Pinnacle is captured for BET-1's no-vig reference only):
  FanDuel  player pass yds / pass TDs / rush yds / receptions / rec yds (main O/U lines), anytime TD + 2+ / 3+ TDs, game spread + total.
  Pinnacle player props (same stats where offered) + game spread / total.
Not available free: DraftKings prices, kicker points, interceptions (FanDuel page does not list them) -> those players/markets fall back exactly as v1.1
already does when a book lacks a market. History: a quote's time is when FORGE read it (no posting-time history like OddsPapi).
usage: python3 tools/free_odds.py capture SEA@DEN [DAL@GB ...]   |   python3 tools/free_odds.py export DAL@GB [out_dir]"""
import os, sys, json, re, io, zipfile, time, datetime as dt
import requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(ROOT, 'data', 'live', 'odds_free'); SEASON = 2026
WEEK1_TUESDAY = dt.date(2026, 9, 8)
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', 'Accept': 'application/json'}
FD = 'https://sbapi.oh.sportsbook.fanduel.com/api'; FD_AK = 'FhMFpcPWXMeyZxOx'      # FanDuel's public web app key (in its page source)
FD_TABS = (None, 'passing-props', 'receiving-props', 'rushing-props', 'td-scorer-props')
PIN = 'https://guest.api.arcadia.pinnacle.com/0.1'; PIN_KEY = 'CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R'   # Pinnacle's public guest key (in its page source)
# FanDuel marketType prefix -> OddsPapi market name used by forge_market (MT table)
FD_OU = {'PLAYER_X_PASSING_YARDS': 'Over Under Player Pass Yards', 'PLAYER_X_PASSING_TOUCHDOWNS': 'Over Under Player TD Passes',
         'PLAYER_X_RUSHING_YARDS': 'Over Under Player Rush Yards', 'PLAYER_X_RECEPTIONS': 'Over Under Player Receptions',
         'PLAYER_X_RECEIVING_YARDS': 'Over Under Player Receiving Yards', 'PLAYER_X_INTERCEPTIONS': 'Over Under Player Interceptions'}
FD_TD = {'ANY_TIME_TOUCHDOWN_SCORER': 'Yes', 'TO_SCORE_2+_TOUCHDOWNS': '2+', 'TO_SCORE_3+_TOUCHDOWNS': '3+'}
PIN_OU = {'Passing Yards': 'Over Under Player Pass Yards', 'Touchdown Passes': 'Over Under Player TD Passes', 'Rushing Yards': 'Over Under Player Rush Yards',
          'Receptions': 'Over Under Player Receptions', 'Receiving Yards': 'Over Under Player Receiving Yards', 'Interceptions': 'Over Under Player Interceptions'}

def _get(url, headers=None, tries=3):
    for k in range(tries):
        try:
            r = requests.get(url, headers=dict(UA, **(headers or {})), timeout=45)
            if r.status_code == 200: return r.json()
            print('HTTP', r.status_code, url[:120], flush=True)
        except Exception as e: print('ERR', type(e).__name__, str(e)[:120], url[:120], flush=True)
        time.sleep(2 + 3 * k)
    return None

def teams():
    """DK abbreviation <-> full team name, from FORGE's fixture metadata (OddsPapi uses LA for the Rams; DK uses LAR)."""
    F = json.load(open(os.path.join(ROOT, 'data', 'live', 'meta', f'fixtures_{SEASON}.json'))); m = {}
    for f in F.values():
        for k in ('1', '2'): m[f[f'participant{k}Name']] = f[f'participant{k}Abbr']
    ab = {v: k for k, v in m.items()}; ab['LAR'] = ab.get('LA'); return m, ab

def week_of(kick): return (kick.date() - WEEK1_TUESDAY).days // 7 + 1
def ts(s): return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
def path_for(away, home, kick): return os.path.join(OUT, str(SEASON), f'W{week_of(kick):02d}_{away}_at_{home}.jsonl')
def dec(american):
    a = float(american); return 1 + (a / 100 if a > 0 else 100 / -a)

def fd_events():
    d = _get(f'{FD}/content-managed-page?page=CUSTOM&customPageId=nfl&_ak={FD_AK}') or {}
    return {e['name']: e for e in ((d.get('attachments') or {}).get('events') or {}).values() if ' @ ' in e.get('name', '')}

def fd_quotes(event_id, away_name, home_name):
    mk = {}
    for tab in FD_TABS:
        d = _get(f'{FD}/event-page?_ak={FD_AK}&eventId={event_id}' + (f'&tab={tab}' if tab else ''))
        if d: mk.update((d.get('attachments') or {}).get('markets') or {})
    Q, team_of = [], {}
    slug = lambda s: re.sub(r'[^a-z]', '', s.lower())
    for m in mk.values():
        if m.get('marketStatus') != 'OPEN' or m.get('inPlay'): continue
        t = m.get('marketType', '')
        for r in m.get('runners') or []:                               # team of each player from the jersey logo on TD runners
            lg = slug(r.get('secondaryLogo') or r.get('logo') or '')
            if r.get('isPlayerSelection') and lg:
                if slug(home_name) in lg: team_of[r['runnerName']] = 'home'
                elif slug(away_name) in lg: team_of[r['runnerName']] = 'away'
        base = re.sub(r'_(HIGH|LOW|MEDIUM)$', '', t)
        if base in FD_OU:
            for r in m.get('runners') or []:
                nm, side = r['runnerName'].rsplit(' ', 1)
                if side not in ('Over', 'Under'): continue
                Q.append(dict(book='fanduel', market=FD_OU[base], handicap=float(r['handicap']), outcome=side, player=nm,
                              price=float(r['winRunnerOdds']['trueOdds']['decimalOdds']['decimalOdds']), active=r.get('runnerStatus') == 'ACTIVE'))
        elif t in FD_TD:
            for r in m.get('runners') or []:
                Q.append(dict(book='fanduel', market='Player To Score TD', handicap=0.0, outcome=FD_TD[t], player=r['runnerName'],
                              price=float(r['winRunnerOdds']['trueOdds']['decimalOdds']['decimalOdds']), active=r.get('runnerStatus') == 'ACTIVE'))
        elif t == 'MATCH_HANDICAP_(2-WAY)':
            R = {r['runnerName']: r for r in m.get('runners') or []}
            if home_name in R and away_name in R:
                h = float(R[home_name]['handicap'])
                for nm, oc in ((home_name, '1'), (away_name, '2')):
                    Q.append(dict(book='fanduel', market='Handicap', mtype='spreads', handicap=h, outcome=oc, player='',
                                  price=float(R[nm]['winRunnerOdds']['trueOdds']['decimalOdds']['decimalOdds']), active=R[nm].get('runnerStatus') == 'ACTIVE'))
        elif t == 'TOTAL_POINTS_(OVER/UNDER)':
            for r in m.get('runners') or []:
                if r['runnerName'] in ('Over', 'Under'):
                    Q.append(dict(book='fanduel', market='Total', mtype='totals', handicap=float(r['handicap']), outcome=r['runnerName'], player='',
                                  price=float(r['winRunnerOdds']['trueOdds']['decimalOdds']['decimalOdds']), active=r.get('runnerStatus') == 'ACTIVE'))
    for q in Q:
        if q['player']: q['side'] = team_of.get(q['player'])
    return Q

def pin_quotes(away_name, home_name):
    H = {'X-API-Key': PIN_KEY}; M = _get(f'{PIN}/leagues/889/matchups', H); K = _get(f'{PIN}/leagues/889/markets/straight', H)
    if not M or not K: return []
    game = [m for m in M if m.get('type') == 'matchup' and not m.get('parentId') and {p.get('name') for p in m.get('participants') or []} == {away_name, home_name}]
    if len(game) != 1: return []
    gid = game[0]['id']; home_pid = {p['alignment']: p for p in game[0]['participants']}
    props = {m['id']: m for m in M if m.get('parentId') == gid and (m.get('special') or {}).get('category') == 'Player Props' and m.get('units') in PIN_OU}
    Q = []
    for k in K:
        if k.get('period') != 0: continue
        if k['matchupId'] in props and k.get('type') == 'total':
            m = props[k['matchupId']]; nm = re.sub(r'\s*\(.*\)$', '', m['special']['description']).replace(' Total ' + m['units'], '').replace(' ' + m['units'], '').strip()
            side = {p['id']: p['name'] for p in m['participants']}
            for p in k['prices']:
                Q.append(dict(book='pinnacle', market=PIN_OU[m['units']], handicap=float(p['points']), outcome=side.get(p['participantId']), player=nm, price=dec(p['price']), active=True))
        elif k['matchupId'] == gid and k.get('type') in ('spread', 'total') and k.get('key') in ('s;0;s', 's;0;ou'):
            for p in k['prices']:
                if k['type'] == 'total':
                    Q.append(dict(book='pinnacle', market='Total', mtype='totals', handicap=float(p['points']), outcome=p.get('designation', '').title(), player='', price=dec(p['price']), active=True))
                elif p.get('designation') in ('home', 'away'):
                    hh = [x for x in k['prices'] if x.get('designation') == 'home'][0]['points']
                    Q.append(dict(book='pinnacle', market='Handicap', mtype='spreads', handicap=float(hh), outcome='1' if p['designation'] == 'home' else '2', player='', price=dec(p['price']), active=True))
    return Q

def capture(games):
    name_of, ab = teams(); ev = fd_events(); now = dt.datetime.now(dt.timezone.utc); out = {}
    for g in games:
        a, h = g.upper().split('@'); an, hn = ab.get(a), ab.get(h)
        e = ev.get(f'{an} @ {hn}')
        if not e: out[g] = 'not on FanDuel'; continue
        kick = ts(e['openDate'])
        if kick <= now: out[g] = 'kicked off'; continue
        Q = fd_quotes(e['eventId'], an, hn); P = pin_quotes(an, hn)
        p = path_for(a, h, kick); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'a') as fh: fh.write(json.dumps(dict(read_utc=now.strftime('%Y-%m-%dT%H:%M:%SZ'), kickoff=e['openDate'], away=a, home=h, away_name=an, home_name=hn,
                                                       fd_event=e['eventId'], quotes=Q + P), separators=(',', ':')) + '\n')
        out[g] = f"{sum(q['book'] == 'fanduel' for q in Q)} FanDuel + {len(P)} Pinnacle quotes -> {os.path.relpath(p, ROOT)}"
    return out

MTYPE = {'Over Under Player Pass Yards': 'playertotals-passyards', 'Over Under Player Rush Yards': 'playertotals-rushyards', 'Over Under Player Receptions': 'playertotals-receptions',
         'Over Under Player Receiving Yards': 'playertotals-receivingyards', 'Over Under Player TD Passes': 'playertotals-passtds', 'Over Under Player Interceptions': 'playertotals-interceptions',
         'Player To Score TD': 'players-td'}   # OddsPapi marketType names (2026-10-16: the card's prop model filters on them)

def export_pull(game, out_dir=None, stamp=None):
    """All snapshots of one game -> OddsPapi-layout pull zip. Returns the zip path (None if nothing captured)."""
    import glob
    a, h = game.upper().split('@'); fs = sorted(glob.glob(os.path.join(OUT, str(SEASON), f'W*_{a}_at_{h}.jsonl')))
    if not fs: return None
    snaps = [json.loads(l) for l in open(fs[-1]) if l.strip()]
    if not snaps: return None
    s0 = snaps[-1]; tf = {'LAR': 'LA'}; ha, aa = tf.get(h, h), tf.get(a, a)
    fx = [dict(fixtureId=f"fd{s0['fd_event']}", participant1Id=1, participant2Id=2, participant1Abbr=ha, participant2Abbr=aa, participant1Name=s0['home_name'],
               participant2Name=s0['away_name'], startTime=s0['kickoff'], statusName='Pre-Game', source='free feed (FanDuel public JSON + Pinnacle guest API)')]
    mk, mid_of, oid_of, names, pid_of = [], {}, {}, {}, {}
    def mid(market, mtype, hcap, outcomes):
        k = (market, hcap)
        if k not in mid_of:
            i = 900000 + len(mk) * 10; mid_of[k] = i
            mk.append(dict(marketId=i, marketName=market + ' (incl. overtime)', playerProp=mtype is None, sportId=14, handicap=hcap, period='result',
                           marketType=mtype or MTYPE.get(market, 'playerprop'), outcomes=[dict(outcomeId=i + j + 1, outcomeName=o) for j, o in enumerate(outcomes)]))
            for j, o in enumerate(outcomes): oid_of[(i, o)] = i + j + 1
        return mid_of[k]
    OUTC = {'Player To Score TD': ['Yes', 'No', '2+', '3+'], 'Handicap': ['1', '2'], 'Total': ['Over', 'Under']}
    H = {'fixtureId': fx[0]['fixtureId'], 'bookmakers': {}}
    for s in snaps:
        t = s['read_utc'].replace('Z', '.000Z')
        for q in s['quotes']:
            if not q.get('outcome'): continue
            m = mid(q['market'], q.get('mtype'), q['handicap'], OUTC.get(q['market'], ['Over', 'Under']))
            if q['player']:
                key = q['player']
                if key not in pid_of: pid_of[key] = f"fx{len(pid_of) + 1}"; names[pid_of[key]] = [key, {'home': 1, 'away': 2}.get(q.get('side'))]
                pid = pid_of[key]
            else: pid = '0'
            L = H['bookmakers'].setdefault(q['book'], {'markets': {}})['markets'].setdefault(str(m), {'outcomes': {}})['outcomes'].setdefault(
                str(oid_of[(m, q['outcome'])]), {'players': {}})['players'].setdefault(pid, [])
            if L and L[-1]['price'] == q['price'] and L[-1]['active'] == q['active']: continue   # unchanged since the last read
            L.append(dict(createdAt=t, price=q['price'], active=q['active']))
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%MZ')
    od = out_dir or os.path.join(ROOT, 'pulls'); os.makedirs(od, exist_ok=True); zp = os.path.join(od, f'prop_history_{a}{h}_{stamp}_free.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as Z:
        Z.writestr('raw/fixtures.json', json.dumps(fx)); Z.writestr('raw/markets.json', json.dumps(mk))
        Z.writestr(f'raw/{aa}_at_{ha}_historical.json', json.dumps(H)); Z.writestr('raw/pid_names.json', json.dumps(names))
        Z.writestr('raw/SOURCE.txt', f'FORGE free odds feed: FanDuel public JSON + Pinnacle guest API, {len(snaps)} snapshot(s) from {os.path.relpath(fs[-1], ROOT)}; quote time = when FORGE read it\n')
    return zp

def upcoming(hours=30):
    """Every FanDuel NFL game kicking off within `hours` -> capture (DK abbreviations from FORGE's fixture metadata)."""
    name_of, _ = teams(); now = dt.datetime.now(dt.timezone.utc); G = []
    for nm, e in fd_events().items():
        k = ts(e['openDate']); a, h = nm.split(' @ ')
        if now < k <= now + dt.timedelta(hours=hours) and a in name_of and h in name_of:
            G.append(f"{'LAR' if name_of[a] == 'LA' else name_of[a]}@{'LAR' if name_of[h] == 'LA' else name_of[h]}")
    return capture(G) if G else {'note': f'no game within {hours} h'}

if __name__ == '__main__':
    if sys.argv[1] == 'upcoming': print(json.dumps(upcoming(float(sys.argv[2]) if len(sys.argv) > 2 else 30), indent=1))
    elif sys.argv[1] == 'capture': print(json.dumps(capture(sys.argv[2:]), indent=1))
    elif sys.argv[1] == 'export': print(export_pull(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
