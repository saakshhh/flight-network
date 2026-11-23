"""Network analysis behind the findings: hubs, hop distances, robustness, airline strategy, regions."""

import random
from collections import Counter

import networkx as nx
import numpy as np
import pandas as pd

from . import data


def hop_distribution(H=None):
    """How many flights the fastest connection takes, over every pair of airports in the main network.

    Returns (Counter {flights: number of ordered airport pairs}, Series of each airport's
    eccentricity = flights to its farthest airport).
    """
    H = data.main_network() if H is None else H
    hist, ecc = Counter(), {}
    for source, lengths in nx.all_pairs_shortest_path_length(H):
        hist.update(lengths.values())
        ecc[source] = max(lengths.values())
    del hist[0]
    return hist, pd.Series(ecc)


def reach(code, H=None, max_flights=4):
    """Number of airports reachable from `code` within 1, 2, ... flights (cumulative)."""
    H = data.main_network() if H is None else H
    lengths = nx.single_source_shortest_path_length(H, code, cutoff=max_flights)
    counts = Counter(lengths.values())
    total, out = 0, {}
    for k in range(1, max_flights + 1):
        total += counts.get(k, 0)
        out[k] = total
    return out


def giant_fraction(G, n_total):
    if G.number_of_nodes() == 0:
        return 0.0
    return max(len(c) for c in nx.connected_components(G)) / n_total


def removal_curve(order, ks, H=None):
    """Share of airports still in one connected network after closing the first k of `order`."""
    H = data.main_network() if H is None else H
    n = H.number_of_nodes()
    out = {}
    for k in ks:
        G = H.copy()
        G.remove_nodes_from(order[:k])
        out[k] = giant_fraction(G, n)
    return out


def removal_curves(ks=range(0, 101, 5), seeds=20, H=None):
    """Close airports in order of betweenness, of destinations (degree), or at random."""
    H = data.main_network() if H is None else H
    ap = data.airports().loc[list(H.nodes)]
    curves = {
        'betweenness': removal_curve(list(ap['betweenness'].sort_values(ascending=False).index), ks, H),
        'degree': removal_curve(list(ap['degree'].sort_values(ascending=False, kind='stable').index), ks, H),
    }
    nodes = sorted(H.nodes)
    runs = [removal_curve(random.Random(seed).sample(nodes, max(ks)), ks, H) for seed in range(seeds)]
    curves['random'] = {k: float(np.mean([r[k] for r in runs])) for k in ks}
    return pd.DataFrame(curves)


def cut_off_by(order, k, H=None):
    """Airports that lose every connection to the main network when the first k of `order` close."""
    H = data.main_network() if H is None else H
    G = H.copy()
    G.remove_nodes_from(order[:k])
    giant = max(nx.connected_components(G), key=len)
    return sorted(set(G.nodes) - giant)


def airline_strategy(min_pairs=75):
    """For each airline with at least `min_pairs` routes it operates itself (codeshares excluded):
    its busiest airport and the share of its routes that touch that airport.

    Near 100% is pure hub-and-spoke (every flight starts or ends at home); near 0% is
    point-to-point (flights criss-cross between many bases).
    """
    r = data.routes()
    ops = r[~r['codeshare']]
    names = data.airlines()['name']
    rows = []
    for code, g in ops.groupby('airline'):
        pairs = set(map(tuple, np.sort(g[['src', 'dst']].to_numpy(), axis=1)))
        if len(pairs) < min_pairs or names.get(code, '').endswith('(unidentified)'):
            continue
        counts = Counter(a for p in pairs for a in p)
        hub, hub_pairs = counts.most_common(1)[0]
        rows.append({'airline': code, 'name': names.get(code, code), 'routes': len(pairs),
                     'airports': len(counts), 'hub': hub, 'hub_share': hub_pairs / len(pairs),
                     'country': data.airlines()['country'].get(code)})
    return pd.DataFrame(rows).set_index('airline').sort_values('hub_share')


def regions(H=None, seed=7, resolution=1.0):
    """Louvain communities: groups of airports more connected to each other than to the rest.

    Returns a Series airport -> region number (0 = largest region).
    """
    H = data.main_network() if H is None else H
    communities = sorted(nx.community.louvain_communities(H, seed=seed, resolution=resolution),
                         key=len, reverse=True)
    return pd.Series({a: i for i, c in enumerate(communities) for a in c}).sort_index()


def describe_regions(labels):
    """One row per region: size, biggest airport, top countries and continents."""
    ap = data.airports()
    rows = []
    for region, members in labels.groupby(labels):
        a = ap.loc[members.index]
        rows.append({'region': region, 'airports': len(a), 'hub': a['degree'].idxmax(),
                     'countries': ', '.join(a['country'].value_counts().head(3).index),
                     'continent_share': a['continent'].value_counts(normalize=True).round(2).to_dict()})
    return pd.DataFrame(rows).set_index('region')
