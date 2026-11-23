"""Load the tidy tables in data/ and turn them into a network."""

from functools import lru_cache
from pathlib import Path

import networkx as nx
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / 'data'
WORLD = DATA / 'world_110m.geojson'

CONTINENTS = ['North America', 'South America', 'Europe', 'Africa', 'Asia', 'Oceania']

# keep_default_na=False so that Namibia's ISO code "NA" isn't read as missing
_READ = dict(keep_default_na=False, na_values=[''])


@lru_cache(maxsize=None)
def airports(folder=DATA):
    """One row per airport (index: IATA code) with location and network metrics."""
    return pd.read_csv(Path(folder) / 'airports.csv', index_col='iata', **_READ)


@lru_cache(maxsize=None)
def pairs(folder=DATA):
    """One row per airport pair with nonstop service, both directions merged.

    `n_airlines` is the number of different airlines that sell the route (in either
    direction), the best measure of a route's importance OpenFlights offers:
    the database has no flight frequencies or seat counts.
    """
    df = pd.read_csv(Path(folder) / 'pairs.csv', **_READ)
    df['airlines'] = df['airlines'].str.split(' ')
    return df


@lru_cache(maxsize=None)
def routes(folder=DATA):
    """One row per airline per directed nonstop route."""
    return pd.read_csv(Path(folder) / 'routes.csv', **_READ)


@lru_cache(maxsize=None)
def airlines(folder=DATA):
    return pd.read_csv(Path(folder) / 'airlines.csv', index_col='airline', **_READ)


def graph(pair_table=None):
    """Undirected airport network: an edge wherever any airline flies nonstop."""
    pair_table = pairs() if pair_table is None else pair_table
    G = nx.Graph()
    G.add_edges_from(zip(pair_table['a'], pair_table['b']))
    return G


def main_network(G=None):
    """The largest connected component (99% of airports; the rest are isolated island networks)."""
    G = graph() if G is None else G
    return G.subgraph(max(nx.connected_components(G), key=len)).copy()


def airline_pairs(code):
    """The airport pairs one airline flies (as operator or codeshare seller)."""
    p = pairs()
    return p[p['airlines'].map(lambda codes: code in codes)]


def filter_pairs(min_airlines=1, min_degree=0, airline=None, top=None):
    """The routes shown on a map: optionally one airline's, between airports with at least
    `min_degree` destinations, flown by at least `min_airlines` airlines, the `top` busiest."""
    p = airline_pairs(airline) if airline else pairs()
    degree = airports()['degree']
    keep = (p['n_airlines'] >= min_airlines) & (p['a'].map(degree) >= min_degree) & (p['b'].map(degree) >= min_degree)
    p = p[keep]
    if top:
        p = p.sort_values(['n_airlines', 'distance_km'], ascending=[False, False]).head(top)
    return p


def describe_airport(code):
    """Multi-line text used by every tooltip."""
    a = airports().loc[code]
    place = ', '.join(str(x) for x in (a['city'], a['country']) if isinstance(x, str) and x)
    return (f"{a['name']} ({code})\n{place}\n"
            f"{a['degree']} nonstop destinations in {a['countries_served']} countries\n"
            f"{a['airlines']} airlines")


def describe_pair(row):
    ap = airports()
    names = airlines()['name']
    sellers = [names.get(c, c) for c in row['airlines']]
    shown = ', '.join(sellers[:6]) + (f' +{len(sellers) - 6} more' if len(sellers) > 6 else '')
    return (f"{ap.at[row['a'], 'city']} ({row['a']}) – {ap.at[row['b'], 'city']} ({row['b']})\n"
            f"{row['distance_km']:,} km\n"
            f"{row['n_airlines']} airline{'s' if row['n_airlines'] != 1 else ''}: {shown}")
