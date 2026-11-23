"""Build the tidy flight-network dataset from the raw OpenFlights and OurAirports files.

    python scripts/build_dataset.py --openflights /tmp/openflights/data --ourairports /tmp/ourairports

Inputs (download links in data/README.md):
    OpenFlights: routes.dat, airports.dat, airlines.dat
    OurAirports: airports.csv, countries.csv

Outputs (in data/):
    routes.csv        one row per airline per directed nonstop route
    pairs.csv         one row per airport pair (both directions merged), the network's edges
    airports.csv      every airport that has at least one route, with location and network metrics
    airlines.csv      every airline that has at least one route
    build_report.json what the build removed, recovered or fixed
"""

import argparse
import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NULL = r'\N'
EARTH_RADIUS_KM = 6371.0088

# The routes are a 2014 snapshot but airports.dat has been updated since. Istanbul's IATA code IST
# moved to the new Istanbul Airport in 2019; in 2014 it meant Atatürk Airport.
CORRECTIONS = {
    'IST': {'name': 'Istanbul Atatürk Airport', 'lat': 40.976898, 'lon': 28.814600},
}

# The largest codes the automatic matching can't name (airlines.dat lists other airlines for
# them), identified from where their routes fly in 2014.
KNOWN_AIRLINES = {
    'GS': ('Tianjin Airlines', 'China'), '8L': ('Lucky Air', 'China'), 'KY': ('Kunming Airlines', 'China'),
    'TOM': ('Thomson Airways', 'United Kingdom'), 'TCX': ('Thomas Cook Airlines', 'United Kingdom'),
    'HQ': ('Thomas Cook Airlines Belgium', 'Belgium'), 'V7': ('Volotea', 'Spain'),
    'GL': ('Air Greenland', 'Greenland'), 'VB': ('VivaAerobús', 'Mexico'), 'VJ': ('VietJet Air', 'Vietnam'),
    'GK': ('Jetstar Japan', 'Japan'), 'BM': ('bmi regional', 'United Kingdom'),
    'JD': ('Beijing Capital Airlines', 'China'),
}
# codes whose single airlines.dat entry clearly doesn't match the routes (TO: listed as
# Transavia France, but most of its routes are UK holiday flights): leave them unnamed
AMBIGUOUS = {'TO'}

# airlines.dat and airports.dat spell some countries differently
COUNTRY_FIXES = {
    'ALASKA': 'United States', 'UNited Kingdom': 'United Kingdom', 'Netherland': 'Netherlands',
    'Republic of Korea': 'South Korea', "Democratic People's Republic of Korea": 'North Korea',
    'Russian Federation': 'Russia', 'Russia]]': 'Russia', 'Hong Kong SAR of China': 'Hong Kong',
    'Macao': 'Macau', 'Lao Peoples Democratic Republic': 'Laos', 'Syrian Arab Republic': 'Syria',
    'Somali Republic': 'Somalia', 'Ivory Coast': "Cote d'Ivoire",
    'Democratic Republic of Congo': 'Congo (Kinshasa)', 'Democratic Republic of the Congo': 'Congo (Kinshasa)',
    'Republic of the Congo': 'Congo (Brazzaville)', 'Myanmar': 'Burma',
}

CONTINENTS = {'AF': 'Africa', 'AN': 'Antarctica', 'AS': 'Asia', 'EU': 'Europe',
              'NA': 'North America', 'OC': 'Oceania', 'SA': 'South America'}


def read_dat(path, names):
    return pd.read_csv(path, header=None, names=names, na_values=NULL, keep_default_na=False,
                       dtype=str, encoding='utf-8')


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def load_airports(of_dir, oa_dir, report):
    of = read_dat(of_dir / 'airports.dat',
                  ['of_id', 'name', 'city', 'country', 'iata', 'icao', 'lat', 'lon', 'alt_ft',
                   'utc_offset', 'dst', 'tz', 'kind', 'source'])
    of = of[of['iata'].notna() & (of['iata'].str.len() == 3)].copy()
    of['lat'] = of['lat'].astype(float)
    of['lon'] = of['lon'].astype(float)

    oa_all = pd.read_csv(oa_dir / 'airports.csv', dtype=str, keep_default_na=False, na_values=[''])
    oa = oa_all[oa_all['iata_code'].notna() & (oa_all['iata_code'].str.len() == 3)]
    # several OurAirports rows can share an IATA code (closed airports keep theirs);
    # prefer the one with scheduled service, then the biggest type
    size_rank = {'large_airport': 0, 'medium_airport': 1, 'small_airport': 2, 'seaplane_base': 3,
                 'heliport': 4, 'balloonport': 5, 'closed': 6}
    oa = oa.assign(_svc=(oa['scheduled_service'] != 'yes').astype(int),
                   _size=oa['type'].map(size_rank).fillna(9))
    oa = oa.sort_values(['_svc', '_size']).drop_duplicates('iata_code')
    countries = pd.read_csv(oa_dir / 'countries.csv', dtype=str, keep_default_na=False)
    country_name = dict(zip(countries['code'], countries['name']))
    oa = oa.set_index('iata_code')

    # OpenFlights has a few duplicate IATA codes; keep the first (lowest id = oldest record)
    report['openflights_duplicate_iata_dropped'] = int(of['iata'].duplicated().sum())
    of = of.drop_duplicates('iata').set_index('iata')

    airports = of[['name', 'city', 'country', 'icao', 'lat', 'lon', 'tz']].copy()
    airports['iso_country'] = oa['iso_country'].reindex(airports.index)
    airports['continent'] = oa['continent'].reindex(airports.index).map(CONTINENTS)
    airports['size'] = oa['type'].reindex(airports.index).str.replace('_airport', '')

    # closed airports (Berlin Tegel, ...) lost their IATA code in OurAirports: match on ICAO instead
    by_icao = oa_all.drop_duplicates('ident').set_index('ident')
    gap = airports['continent'].isna() & airports['icao'].notna()
    airports.loc[gap, 'iso_country'] = airports.loc[gap, 'icao'].map(by_icao['iso_country'])
    airports.loc[gap, 'continent'] = airports.loc[gap, 'icao'].map(by_icao['continent']).map(CONTINENTS)
    airports.loc[gap, 'size'] = airports.loc[gap, 'icao'].map(by_icao['type']).str.replace('_airport', '')
    # last resort: the continent most airports of the same country are on
    country_continent = airports.dropna(subset=['continent']).groupby('country')['continent'].agg(
        lambda x: x.mode().iat[0])
    gap = airports['continent'].isna()
    airports.loc[gap, 'continent'] = airports.loc[gap, 'country'].map(country_continent)
    report['continent_from_country'] = sorted(airports.index[gap])

    for code, fix in CORRECTIONS.items():
        for column, value in fix.items():
            airports.loc[code, column] = value
    report['manual_corrections'] = CORRECTIONS

    # airports that routes use but OpenFlights has no record for: take them from OurAirports
    extra = oa.drop(index=airports.index, errors='ignore')
    extra = pd.DataFrame({
        'name': extra['name'], 'city': extra['municipality'],
        'country': extra['iso_country'].map(country_name), 'icao': extra['icao_code'],
        'lat': extra['latitude_deg'].astype(float), 'lon': extra['longitude_deg'].astype(float),
        'tz': np.nan, 'iso_country': extra['iso_country'],
        'continent': extra['continent'].map(CONTINENTS),
        'size': extra['type'].str.replace('_airport', ''),
    })
    return airports, extra


def resolve_airlines(routes, airlines, airports):
    """Name every airline code in the routes.

    routes.dat links each route to an airline id, but those ids were assigned by looking the
    two-letter code up in airlines.dat, which reuses codes (VY is both Vueling and Formosa
    Airlines). So: when a code belongs to one airline, use it; when several share it, pick the one
    whose home country the routes actually touch most; when none fits, call it unidentified
    instead of guessing.
    """
    airlines = airlines.assign(country=airlines['country'].replace(COUNTRY_FIXES))
    by_code = airlines[airlines['iata'].notna()].groupby('iata')
    endpoint_country = pd.concat([routes[['airline', 'src']].rename(columns={'src': 'iata'}),
                                  routes[['airline', 'dst']].rename(columns={'dst': 'iata'})])
    endpoint_country['country'] = endpoint_country['iata'].map(airports['country'])
    touched = endpoint_country.groupby('airline')['country'].value_counts()

    names, countries, how = {}, {}, {}
    for code in routes['airline'].unique():
        cands = by_code.get_group(code) if code in by_code.groups else airlines.iloc[0:0]
        pick, method = None, 'unidentified'
        if code in KNOWN_AIRLINES:
            names[code], countries[code] = KNOWN_AIRLINES[code]
            how[code] = 'manual'
            continue
        if code in AMBIGUOUS:
            cands = cands.iloc[0:0]
        if len(cands) == 1:
            pick, method = cands.iloc[0], 'unique code'
        elif len(cands) > 1:
            counts = touched.get(code, pd.Series(dtype=int))
            share = cands['country'].map(lambda c: counts.get(c, 0)) / max(counts.sum(), 1)
            score = share + 0.001 * cands['active'].eq('Y')  # break ties toward active airlines
            if share.max() >= 0.1:  # a real airline's home country is at least 10% of its endpoints
                pick, method = cands.loc[score.idxmax()], 'matched home country'
        names[code] = pick['name'] if pick is not None else f'{code} (unidentified)'
        countries[code] = pick['country'] if pick is not None else np.nan
        how[code] = method
    return names, countries, how


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--openflights', type=Path, required=True, help='folder with routes.dat etc.')
    parser.add_argument('--ourairports', type=Path, required=True, help='folder with airports.csv, countries.csv')
    parser.add_argument('--out', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {}

    # ---- routes -----------------------------------------------------------------
    routes = read_dat(args.openflights / 'routes.dat',
                      ['airline', 'airline_id', 'src', 'src_id', 'dst', 'dst_id', 'codeshare', 'stops',
                       'equipment'])
    report['raw_route_rows'] = len(routes)
    routes['codeshare'] = routes['codeshare'].eq('Y')
    routes['stops'] = routes['stops'].astype(int)

    report['dropped_not_nonstop'] = int((routes['stops'] > 0).sum())
    routes = routes[routes['stops'] == 0]
    report['dropped_self_loops'] = int((routes['src'] == routes['dst']).sum())
    routes = routes[routes['src'] != routes['dst']]
    # a few routes use 4-letter ICAO codes instead of IATA codes
    bad_code = ~(routes['src'].str.len().eq(3) & routes['dst'].str.len().eq(3))
    report['dropped_non_iata_codes'] = int(bad_code.sum())
    routes = routes[~bad_code]
    report['dropped_duplicate_rows'] = int(routes.duplicated(['airline', 'src', 'dst']).sum())
    routes = routes.drop_duplicates(['airline', 'src', 'dst'])

    # ---- airports ---------------------------------------------------------------
    airports, extra = load_airports(args.openflights, args.ourairports, report)
    used = pd.Index(pd.unique(routes[['src', 'dst']].values.ravel()))
    missing = used.difference(airports.index)
    recovered = extra.reindex(missing).dropna(subset=['lat'])
    report['airports_recovered_from_ourairports'] = sorted(recovered.index)
    airports = pd.concat([airports, recovered])
    unknown = used.difference(airports.index)
    report['airports_without_coordinates'] = sorted(unknown)
    lost = routes['src'].isin(unknown) | routes['dst'].isin(unknown)
    report['dropped_routes_unknown_airport'] = int(lost.sum())
    routes = routes[~lost]

    # ---- airlines ---------------------------------------------------------------
    airlines = read_dat(args.openflights / 'airlines.dat',
                        ['airline_id', 'name', 'alias', 'iata', 'icao', 'callsign', 'country', 'active'])
    names, countries, how = resolve_airlines(routes, airlines, airports)
    routes['airline_name'] = routes['airline'].map(names)
    routes['airline_country'] = routes['airline'].map(countries)
    report['airline_resolution'] = pd.Series(how).value_counts().to_dict()
    report['airlines_unidentified'] = sorted(c for c, h in how.items() if h == 'unidentified')

    # ---- distances --------------------------------------------------------------
    s, d = airports.loc[routes['src']], airports.loc[routes['dst']]
    routes['distance_km'] = haversine_km(s['lat'].values, s['lon'].values,
                                         d['lat'].values, d['lon'].values).round(0).astype(int)
    routes = routes[['airline', 'airline_name', 'airline_country', 'src', 'dst', 'codeshare',
                     'equipment', 'distance_km']].sort_values(['src', 'dst', 'airline'])

    # ---- airport pairs (network edges) -----------------------------------------
    a, b = np.minimum(routes['src'], routes['dst']), np.maximum(routes['src'], routes['dst'])
    keyed = routes.assign(a=a, b=b)
    pairs = keyed.groupby(['a', 'b']).agg(
        airlines=('airline', lambda x: ' '.join(sorted(set(x)))),
        n_airlines=('airline', 'nunique'),
        n_operating=('codeshare', lambda x: int((~x).sum())),
        listings=('airline', 'size'),
        distance_km=('distance_km', 'first'),
    ).reset_index()
    directed = set(zip(routes['src'], routes['dst']))
    pairs['both_directions'] = [(x, y) in directed and (y, x) in directed for x, y in zip(pairs['a'], pairs['b'])]
    # n_operating counts route rows that aren't codeshares; turn it into distinct operating airlines
    op = keyed[~keyed['codeshare']].groupby(['a', 'b'])['airline'].nunique()
    pairs['n_operating'] = pairs.set_index(['a', 'b']).index.map(op).fillna(0).astype(int)

    # ---- network metrics --------------------------------------------------------
    G = nx.Graph()
    G.add_edges_from(zip(pairs['a'], pairs['b']))
    giant = G.subgraph(max(nx.connected_components(G), key=len))
    print(f'network: {G.number_of_nodes()} airports, {G.number_of_edges()} pairs; '
          f'giant component {giant.number_of_nodes()} — computing betweenness (≈1 min)…')
    betweenness = nx.betweenness_centrality(G, normalized=True)
    airports = airports.loc[sorted(G.nodes)].copy()
    airports.index.name = 'iata'
    airports['degree'] = pd.Series(dict(G.degree()))
    airports['betweenness'] = pd.Series(betweenness).round(9)
    airports['in_main_network'] = airports.index.isin(giant.nodes)
    out_routes = routes.groupby('src').size()
    airports['departing_routes'] = out_routes.reindex(airports.index).fillna(0).astype(int)
    airports['airlines'] = (pd.concat([routes[['src', 'airline']].rename(columns={'src': 'iata'}),
                                       routes[['dst', 'airline']].rename(columns={'dst': 'iata'})])
                            .groupby('iata')['airline'].nunique())
    airports['countries_served'] = (pd.concat([
        pd.DataFrame({'iata': pairs['a'], 'other': pairs['b']}),
        pd.DataFrame({'iata': pairs['b'], 'other': pairs['a']})])
        .assign(c=lambda x: x['other'].map(airports['country']))
        .groupby('iata')['c'].nunique())
    airports[['degree', 'airlines', 'countries_served']] = airports[['degree', 'airlines', 'countries_served']].astype(int)
    airports['lat'] = airports['lat'].round(5)
    airports['lon'] = airports['lon'].round(5)

    airline_table = (routes.groupby('airline')
                     .agg(name=('airline_name', 'first'), country=('airline_country', 'first'),
                          routes=('src', 'size'),
                          airports=('src', lambda x: len(set(x) | set(routes.loc[x.index, 'dst']))))
                     .sort_values('routes', ascending=False))

    # ---- write ------------------------------------------------------------------
    routes.to_csv(args.out / 'routes.csv', index=False)
    pairs.to_csv(args.out / 'pairs.csv', index=False)
    airports.to_csv(args.out / 'airports.csv')
    airline_table.to_csv(args.out / 'airlines.csv')
    report['continent_from_country'] = [c for c in report['continent_from_country'] if c in airports.index]
    report.update(routes=len(routes), pairs=len(pairs), airports=len(airports),
                  airlines=len(airline_table),
                  airports_outside_main_network=int((~airports['in_main_network']).sum()))
    (args.out / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if not isinstance(v, list)}, indent=2))


if __name__ == '__main__':
    main()
