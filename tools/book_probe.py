"""(2026-11-11) Which sportsbooks' public NBA feeds answer a GitHub runner? Status code + size only; nothing stored but the summary."""
import requests, json, datetime as dt, os
H = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
U = {
 'betrivers_kambi': 'https://eu-offering-api.kambicdn.com/offering/v2018/rsiuspa/listView/basketball/nba.json?lang=en_US&market=US',
 'unibet_kambi': 'https://eu-offering-api.kambicdn.com/offering/v2018/ubusnj/listView/basketball/nba.json?lang=en_US&market=US',
 'betmgm': 'https://sports.nj.betmgm.com/en/sports/api/widget/widgetdata?layoutSize=Large&page=CompetitionLobby&sportId=7&regionId=9&competitionId=6004',
 'caesars': 'https://api.americanwagering.com/regions/us/locations/nj/brands/czr/sb/v3/sports/basketball/events/schedule/?competitionIds=5806c896-4eec-4de1-874f-afed93114b8c',
 'draftkings_sb': 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/42648',
 'espnbet': 'https://sportsbook.espnbet.com/sportsbook/v1/api/getCompetitionEvents?competitionId=2f5c7e0e-0ef5-4c2b-a0e7-b5b4e5c2b4a2',
 'bovada': 'https://www.bovada.lv/services/sports/event/coupon/events/A/description/basketball/nba?marketFilterId=def&preMatchOnly=true&lang=en',
 'prizepicks': 'https://api.prizepicks.com/projections?league_id=7&per_page=250',
 'underdog': 'https://api.underdogfantasy.com/beta/v5/over_under_lines',
}
R = {}
for k, u in U.items():
    try: r = requests.get(u, headers=H, timeout=20); R[k] = dict(status=r.status_code, bytes=len(r.content), json=r.headers.get('content-type', '').startswith('application/json'))
    except Exception as e: R[k] = dict(error=repr(e)[:120])
os.makedirs('data/live/probe', exist_ok=True); json.dump(dict(at=dt.datetime.now(dt.timezone.utc).isoformat(), results=R), open('data/live/probe/book_probe.json', 'w'), indent=1); print(json.dumps(R, indent=1))
