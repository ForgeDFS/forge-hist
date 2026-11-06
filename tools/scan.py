"""Public DraftKings draft-group scanner (FORGE history; public salary data only).
For each draft-group ID: www.draftkings.com/lineup/getavailableplayers?draftGroupId=<id> (JSON: players, salaries, positions, teams, game
start times) -> one compact row per draft group in data/index_<from>_<to>.csv, and the full player list for NBA/NFL groups in
data/dg/<id>.json.gz. One request at a time, ~2 per second; resumable (skips IDs already in data/)."""
import sys, os, json, gzip, time, re, csv, requests
UA = {'User-Agent': 'Mozilla/5.0 (compatible; FORGE-history/1.0)'}; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NBA = {'PG', 'SG', 'SF', 'PF', 'C', 'G', 'F'}; NFL = {'QB', 'RB', 'WR', 'TE', 'DST', 'K'}
def sport(pl):
    pos = {str(p.get('pn', '')).split('/')[0] for p in pl}
    if pos & NFL and not pos & {'PG', 'SG', 'PF', 'LW', 'SP'}: return 'NFL'
    if pos & {'PG', 'SG', 'PF'}: return 'NBA'
    return 'OTHER'
def ts(s): m = re.search(r'(\d{10,13})', str(s)); return int(m.group(1)) // 1000 if m else None
def main(a, b, step=1):
    os.makedirs(os.path.join(ROOT, 'data', 'dg'), exist_ok=True); out = os.path.join(ROOT, 'data', f'index_{a}_{b}_{step}.csv')
    done = set()
    if os.path.exists(out): done = {r['dg'] for r in csv.DictReader(open(out))}
    fh = open(out, 'a', newline=''); w = csv.DictWriter(fh, fieldnames=['dg', 'status', 'sport', 'players', 'games', 'teams', 'first_start_utc', 'last_start_utc', 'max_salary'])
    if not done: w.writeheader()
    t0 = time.time()
    for dg in range(a, b + 1, step):
        if str(dg) in done: continue
        if time.time() - t0 > float(os.environ.get('MAX_SECONDS', '19800')): break
        try: r = requests.get(f'https://www.draftkings.com/lineup/getavailableplayers?draftGroupId={dg}', headers=UA, timeout=30)
        except Exception as e: w.writerow(dict(dg=dg, status='err')); time.sleep(2); continue
        if r.status_code != 200: w.writerow(dict(dg=dg, status=r.status_code)); time.sleep(0.5); continue
        try: j = r.json()
        except Exception: w.writerow(dict(dg=dg, status='nojson')); continue
        pl = j.get('playerList') or []; tl = j.get('teamList') or {}
        if not pl: w.writerow(dict(dg=dg, status='empty')); time.sleep(0.5); continue
        st = sorted(t for t in (ts(g.get('tz')) for g in tl.values()) if t); sp = sport(pl)
        w.writerow(dict(dg=dg, status='ok', sport=sp, players=len(pl), games=len(tl), teams=' '.join(sorted({f"{g.get('at')}@{g.get('ht')}" for g in tl.values()})),
                        first_start_utc=time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime(st[0])) if st else '', last_start_utc=time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime(st[-1])) if st else '',
                        max_salary=max((p.get('s') or 0) for p in pl)))
        if sp in ('NBA', 'NFL'):
            with gzip.open(os.path.join(ROOT, 'data', 'dg', f'{dg}.json.gz'), 'wt') as g: json.dump(j, g)
        fh.flush(); time.sleep(0.5)
if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2]); step = int(sys.argv[3]) if len(sys.argv) > 3 else 1; main(a, b, step)
