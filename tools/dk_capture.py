"""FORGE DraftKings capture (2026-10-14). Runs on GitHub's runners, which CAN read DraftKings' www endpoints (probe 2026-10-14:
www.draftkings.com lobby / salary CSV / contest detail = HTTP 200; api.draftkings.com = 403, as from Colab and Claude's workspace).

Every run (writes only under dk/):
  1. NFL lobby -> dk/draftgroups.csv (every NFL draft group seen: id, game type, start, games, description) and dk/contests.csv
     (static contest facts: id, name, fee, max entries, entries per user, prize pool, draft group, start). Append-only by id.
  2. For every NFL draft group that has not started: the official DKSalaries.csv (same file as the 'Export to CSV' button), saved as
     dk/salaries/<season>/<startET>_<desc>_dg<id>__<capturedUTC>.csv ONLY when its content changed (status / price changes) -> a dated version
     history up to lock. Showdown (game type 96) and Classic (game type 1) and any other NFL type.
  3. Payout tables for contests in FORGE's tiers (names in TIERS, fee <= MAX_FEE): dk/payouts/<contestId>.csv (lo, hi, prize), once per contest.
mode 'fresh' (on-demand, see .github/workflows/fetch_now.yml): only step 2 for the requested draft groups, always saved."""
import os, sys, re, csv, json, time, hashlib, datetime as dt, html
import requests

ROOT = os.environ.get('DKROOT') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'live'); SPORT = os.environ.get('SPORT', 'NFL').upper()   # (2026-10-21) SPORT=NBA -> dk/nba/...
DK = os.path.join(ROOT, 'dk', SPORT.lower())
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'}
SEASON = 2026; MAX_FEE = 5.0
TIERS = ('Dime Package', 'Quarter Jukebox', 'Daily Dollar', 'mini-MAX', 'Singleback', 'First Down', 'Play-Action', 'Wildcat', 'Lightening Drive',
         'Draft Time', 'Flea Flicker', 'Hail Mary', 'Nickel', 'Penny', 'Single Entry',
         'And-One', 'Four Point Play', 'High Five', 'Fadeaway', 'Tiers')   # (2026-10-30) NBA contests Drew enters: their tables were never saved
NOW = dt.datetime.now(dt.timezone.utc); STAMP = NOW.strftime('%Y%m%dT%H%MZ'); LOG = []

def log(*a): s = ' '.join(str(x) for x in a); print(s, flush=True); LOG.append(s)

def get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=120)
            if r.status_code == 200: return r
            log('HTTP', r.status_code, url)
        except Exception as e: log('ERR', e, url)
        time.sleep(3 * (i + 1))
    return None

def dkdate(s):
    m = re.search(r'/Date\((\d+)\)/', str(s)); return dt.datetime.fromtimestamp(int(m.group(1)) / 1000, dt.timezone.utc) if m else None

def upsert(path, rows, key):
    old = list(csv.DictReader(open(path, newline=''))) if os.path.exists(path) else []
    have = {r[key] for r in old}; new = [r for r in rows if str(r[key]) not in have]
    if not new: return 0
    cols = list(rows[0].keys()); os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); [w.writerow({c: r.get(c, '') for c in cols}) for r in old + new]
    return len(new)

def slug(s): return re.sub(r'[^A-Za-z0-9@]+', '-', str(s)).strip('-')

def _sig(body):
    """change signature of a DKSalaries.csv: every column except AvgPointsPerGame (DK servers round it differently, 14.04 vs 14), row order ignored."""
    import csv as _csv, io as _io
    try:
        R = list(_csv.reader(_io.StringIO(body.decode('utf-8-sig')))); h = [c.strip() for c in R[0]]; k = h.index('AvgPointsPerGame') if 'AvgPointsPerGame' in h else None
        rows = sorted(','.join(c for i, c in enumerate(r) if i != k) for r in R[1:] if r)
        return hashlib.md5('\n'.join([','.join(h)] + rows).encode()).hexdigest()
    except Exception: return hashlib.md5(body).hexdigest()

def save_salary(g, always=False):
    url = f"https://www.draftkings.com/lineup/getavailableplayerscsv?contestTypeId={g['ContestTypeId']}&draftGroupId={g['DraftGroupId']}"
    r = get(url)
    if r is None or not r.content.strip(): return None
    body = r.content; h = _sig(body)
    d = os.path.join(DK, 'salaries', str(SEASON)); os.makedirs(d, exist_ok=True)
    start = str(g.get('StartDateEst', ''))[:16].replace(':', '').replace('-', '')
    base = f"{start}_{slug(g.get('desc') or g.get('ContestStartTimeSuffix') or 'slate')}_gt{g.get('GameTypeId')}_dg{g['DraftGroupId']}"
    prev = sorted(f for f in os.listdir(d) if f.startswith(base + '__'))
    if prev and not always and _sig(open(os.path.join(d, prev[-1]), 'rb').read()) == h: return 'unchanged'
    p = os.path.join(d, f'{base}__{STAMP}.csv'); open(p, 'wb').write(body)
    n = body.count(b'\n') - 1; log(f"salary dg{g['DraftGroupId']} {g.get('desc')}: {n} rows -> {os.path.basename(p)}"); return p

def parse_payouts(page):
    t = html.unescape(re.sub(r'<[^>]+>', ' ', page)); i = t.find('Prize Payouts'); t = t[i:] if i >= 0 else t
    rows = []
    for m in re.finditer(r'(\d[\d,]*)(?:st|nd|rd|th)(?:\s*-\s*(\d[\d,]*)(?:st|nd|rd|th))?\s+\$([\d,]+(?:\.\d+)?)', t):
        rows.append((int(m.group(1).replace(',', '')), int((m.group(2) or m.group(1)).replace(',', '')), float(m.group(3).replace(',', ''))))
    return rows

def main(mode='scheduled', groups=()):
    os.makedirs(DK, exist_ok=True)
    r = get(f'https://www.draftkings.com/lobby/getcontests?sport={SPORT}')
    if r is None: log('lobby unavailable'); return finish()
    L = r.json(); GS = {g.get('GameSetKey'): g for g in L.get('GameSets') or []}
    DG = []
    for g in L.get('DraftGroups') or []:
        comps = (GS.get(g.get('GameSetKey')) or {}).get('Competitions') or []
        desc = ' '.join(c.get('Description', '') for c in comps[:3]) + (f' +{len(comps) - 3}' if len(comps) > 3 else '') if comps else str(g.get('ContestStartTimeSuffix') or '').strip(' ()')
        g = dict(g, desc=desc.strip()); DG.append(g)
    upsert(os.path.join(DK, 'draftgroups.csv'), [{'draft_group_id': g['DraftGroupId'], 'game_type_id': g.get('GameTypeId'), 'contest_type_id': g.get('ContestTypeId'),
           'start_utc': g.get('StartDate'), 'start_et': g.get('StartDateEst'), 'games': g.get('GameCount'), 'desc': g['desc'], 'tag': g.get('DraftGroupTag'),
           'first_seen_utc': STAMP} for g in DG], 'draft_group_id')
    C = L.get('Contests') or []
    added = upsert(os.path.join(DK, 'contests.csv'), [{'contest_id': c['id'], 'name': c.get('n'), 'fee': c.get('a'), 'max_entries': c.get('m'), 'per_user': c.get('mec'),
           'prize_pool': c.get('po'), 'draft_group_id': c.get('dg'), 'game_type_id': c.get('gameTypeId'), 'game_type': c.get('gameType'),
           'start_utc': dkdate(c.get('sd')).isoformat() if dkdate(c.get('sd')) else '', 'guaranteed': (c.get('attr') or {}).get('IsGuaranteed'), 'first_seen_utc': STAMP} for c in C], 'contest_id')
    log(f'lobby: {len(DG)} draft groups, {len(C)} contests (+{added} new)')
    want = {int(x) for x in groups}
    for g in DG:
        start = dt.datetime.fromisoformat(str(g['StartDate'])[:19]).replace(tzinfo=dt.timezone.utc)
        if want and g['DraftGroupId'] not in want: continue
        if not want and start <= NOW: continue
        save_salary(g, always=bool(want)); time.sleep(1)
    if mode == 'scheduled':
        pd_dir = os.path.join(DK, 'payouts'); os.makedirs(pd_dir, exist_ok=True); done = set(f.split('.')[0] for f in os.listdir(pd_dir)); k = 0
        pri = lambda c: next((i for i, t in enumerate(TIERS) if t.lower() in str(c.get('n', '')).lower()), 99)   # Drew's usual tiers first
        for c in sorted(C, key=pri):
            if str(c['id']) in done or float(c.get('a') or 0) > MAX_FEE or not any(t.lower() in str(c.get('n', '')).lower() for t in TIERS): continue
            p = get(f"https://www.draftkings.com/contest/detailspop?contestId={c['id']}")
            rows = parse_payouts(p.text) if p is not None else []
            if rows:
                with open(os.path.join(pd_dir, f"{c['id']}.csv"), 'w', newline='') as fh: w = csv.writer(fh); w.writerow(['lo', 'hi', 'prize']); w.writerows(rows)
                k += 1
            time.sleep(1)
            if k >= 150: break
        log(f'payout tables saved: {k}')
    finish()

def backfill(req_path):
    """2026-10-15: past contests (FORGE_history) -> payout table + draft group id + that draft group's salary CSV, read from the public contest page.
    requests/dk_backfill.json = {"contests": [cid, ...]}; result -> requests/dk_backfill_result.json. Raw pages kept in dk/backfill/ for audit."""
    req = json.load(open(req_path)); out = {}; bd = os.path.join(DK, 'backfill'); os.makedirs(bd, exist_ok=True)
    pd_dir = os.path.join(DK, 'payouts'); os.makedirs(pd_dir, exist_ok=True); dgs = {}
    for cid in req.get('contests', []):
        p = get(f"https://www.draftkings.com/contest/detailspop?contestId={cid}")
        if p is None: out[str(cid)] = 'page unavailable'; continue
        open(os.path.join(bd, f'{cid}_detailspop.html'), 'w', encoding='utf-8').write(p.text)
        rows = parse_payouts(p.text); m = None
        for u in (None, f"https://www.draftkings.com/draft/contest/{cid}", f"https://www.draftkings.com/contest/gamecenter/{cid}", f"https://www.draftkings.com/contest/detailspop?contestId={cid}&showDraftGroup=true"):
            t = p.text if u is None else ((get(u) or type('x', (), {'text': ''})).text)
            ids = [x for x in re.findall(r'draft[_ ]?group[_ ]?id["\'=:\s]+(\d+)', t, re.I) + re.findall(r'draftGroupId=(\d+)', t) if int(x) > 0]
            if u is not None and t: open(os.path.join(bd, f'{cid}_{u.split("/")[-2] if "?" not in u else "dp2"}.html'), 'w', encoding='utf-8').write(t)
            if ids: m = re.match(r'(\d+)', ids[0]); break
        ct = re.search(r'contestTypeId["\'=:\s]+(\d+)', p.text, re.I)
        if rows:
            with open(os.path.join(pd_dir, f"{cid}.csv"), 'w', newline='') as fh: w = csv.writer(fh); w.writerow(['lo', 'hi', 'prize']); w.writerows(rows)
        out[str(cid)] = dict(payout_rows=len(rows), dg=int(m.group(1)) if m else None, contest_type=int(ct.group(1)) if ct else None, bytes=len(p.text))
        if m: dgs[int(m.group(1))] = int(ct.group(1)) if ct else None
        time.sleep(1)
    for dg, ctid in dgs.items():
        for t in ([ctid] if ctid else []) + [21, 96, 159, 1]:
            r = get(f"https://www.draftkings.com/lineup/getavailableplayerscsv?contestTypeId={t}&draftGroupId={dg}")
            if r is not None and r.content.strip() and b'Name' in r.content[:300]:
                f = os.path.join(DK, 'salaries', str(SEASON), f'backfill_dg{dg}__{STAMP}.csv'); os.makedirs(os.path.dirname(f), exist_ok=True); open(f, 'wb').write(r.content)
                out[f'dg{dg}'] = dict(contest_type=t, rows=r.content.count(b'\n') - 1, file=os.path.relpath(f, ROOT) if 'ROOT' in globals() else f); break
            time.sleep(1)
        else: out[f'dg{dg}'] = 'salary csv unavailable'
    json.dump(out, open(os.path.join(os.path.dirname(req_path), 'dk_backfill_result.json'), 'w'), indent=1); log('backfill', json.dumps(out)[:3000]); finish()

def finish():
    os.makedirs(os.path.join(DK, 'logs'), exist_ok=True)
    with open(os.path.join(DK, 'logs', f'{NOW:%Y-%m}.log'), 'a') as fh: fh.write(f'== {STAMP}\n' + '\n'.join(LOG) + '\n')

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'scheduled'
    if mode == 'backfill': backfill(sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'requests', 'dk_backfill.json'))
    else: main(mode, sys.argv[2:])
