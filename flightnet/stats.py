"""Every number quoted in the README and on the website, computed from the data.

    python -m flightnet.stats            # print them
    python -m flightnet.stats --json     # as JSON
"""

import argparse
import hashlib
import json
import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import data, network

K_CLOSED = 10  # airports closed in the robustness comparison


def _pct(x, digits=0):
    return round(100 * float(x), digits)


def _and(items):
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def _alaska(ap):
    return (ap['country'] == 'United States') & (ap['lat'] > 51) & (ap['lon'] < -129)


CACHE = Path(__file__).resolve().parent.parent / '.cache'


def _data_key():
    """Changes whenever a data file or this module changes."""
    h = hashlib.sha1()
    for path in sorted(data.DATA.glob('*.csv')) + [Path(__file__), Path(data.__file__).with_name('network.py')]:
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


@lru_cache(maxsize=None)
def compute():
    """All statistics. Takes ~30 s the first time, then loads from .cache/ until the data changes."""
    path = CACHE / f'stats-{_data_key()}.pkl'
    if path.exists():
        with open(path, 'rb') as f:
            return pickle.load(f)
    s = _compute()
    CACHE.mkdir(exist_ok=True)
    for old in CACHE.glob('stats-*.pkl'):
        old.unlink()
    with open(path, 'wb') as f:
        pickle.dump(s, f)
    return s


def _compute():
    ap, pairs, routes, al = data.airports(), data.pairs(), data.routes(), data.airlines()
    H = data.main_network()
    main = ap.loc[list(H.nodes)]
    s = {}

    s['overview'] = {
        'airports': len(ap),
        'pairs': len(pairs),
        'routes': len(routes),
        'airlines': int((~al['name'].str.endswith('(unidentified)')).sum()),
        'airline_codes': len(al),
        'countries': int(ap['country'].nunique()),
        'main_airports': H.number_of_nodes(),
        'main_share': _pct(H.number_of_nodes() / len(ap), 1),
        'outside_main': len(ap) - H.number_of_nodes(),
        'domestic_share': _pct((pairs['a'].map(ap['country']) == pairs['b'].map(ap['country'])).mean()),
        'intercontinental_share': _pct((pairs['a'].map(ap['continent']) != pairs['b'].map(ap['continent'])).mean()),
        'median_distance_km': int(pairs['distance_km'].median()),
        'single_airline_share': _pct((pairs['n_airlines'] == 1).mean()),
    }

    # --- 1. hubs ---------------------------------------------------------------------
    deg = ap['degree'].sort_values(ascending=False, kind='stable')
    top5 = set(deg.index[:int(round(len(deg) * 0.05))])
    touching = (pairs['a'].isin(top5) | pairs['b'].isin(top5)).mean()
    s['hubs'] = {
        'median_degree': int(ap['degree'].median()),
        'small_share': _pct((ap['degree'] <= 2).mean()),
        'top5_count': len(top5),
        'top5_pair_share': _pct(touching),
        'top': [{'iata': c, 'city': ap.at[c, 'city'], 'degree': int(deg[c])} for c in deg.index[:5]],
        'max_degree': int(deg.iloc[0]),
    }

    # --- 2. small world -------------------------------------------------------------
    hist, ecc = network.hop_distribution(H)
    total = sum(hist.values())
    cum = np.cumsum([hist[k] for k in sorted(hist)]) / total
    within = {k: _pct(c, 0) for k, c in zip(sorted(hist), cum)}
    far = ecc[ecc == ecc.max()].index
    # the farthest pair: two airports at the maximum distance from each other
    import networkx as nx
    a_far = far[0]
    lengths = nx.single_source_shortest_path_length(H, a_far)
    b_far = max(lengths, key=lambda x: (lengths[x], x))
    # same rule as the explorer's route finder: fewest flights, then fewest kilometres
    km = {(a, b): d for a, b, d in zip(pairs['a'], pairs['b'], pairs['distance_km'])}
    weight = lambda u, v, _: 1e6 + km.get((u, v), km.get((v, u)))
    path = nx.dijkstra_path(H, a_far, b_far, weight=weight)
    best = ecc.sort_values(kind='stable')
    s['reach'] = {
        'mean_flights': round(sum(k * c for k, c in hist.items()) / total, 1),
        'within': within,
        'distribution': {k: _pct(hist[k] / total, 1) for k in sorted(hist)},
        'diameter': int(ecc.max()),
        'far_a': {'iata': a_far, 'name': ap.at[a_far, 'name'], 'city': ap.at[a_far, 'city'],
                  'country': ap.at[a_far, 'country']},
        'far_b': {'iata': b_far, 'name': ap.at[b_far, 'name'], 'city': ap.at[b_far, 'city'],
                  'country': ap.at[b_far, 'country']},
        'far_path': path,
        'far_route': ' → '.join(path),
        'far_via': _and([ap.at[c, 'city'] for c in path if ap.at[c, 'degree'] >= 50]),
        'min_eccentricity': int(best.iloc[0]),
        'most_central': list(best[best == best.iloc[0]].index),
        'from_ord': network.reach('ORD', H, 3),
    }

    # --- 3. gateways ----------------------------------------------------------------
    btw = main['betweenness'].sort_values(ascending=False, kind='stable')
    deg_rank = main['degree'].rank(ascending=False, method='min')
    top20 = btw.index[:20]
    s['gateways'] = {
        'top': [{'iata': c, 'city': ap.at[c, 'city'], 'degree': int(ap.at[c, 'degree']),
                 'degree_rank': int(deg_rank[c]), 'betweenness': round(float(btw[c]), 3)}
                for c in btw.index[:10]],
        'anc_degree': int(ap.at['ANC', 'degree']),
        'anc_degree_rank': int(deg_rank['ANC']),
        'anc_rank': int(list(btw.index).index('ANC')) + 1,
        'anc_vs_ams': round(float(btw['ANC'] / btw['AMS']), 1),
        'sfj_rank': int(list(btw.index).index('SFJ')) + 1,
        'sfj_degree': int(ap.at['SFJ', 'degree']),
        'top20_outside_top50_degree': int((deg_rank[top20] > 50).sum()),
        'correlation': round(float(np.corrcoef(np.log(main['degree']), np.log(main['betweenness'] + 1e-7))[0, 1]), 2),
    }

    # --- 4. fragility ---------------------------------------------------------------
    curves = network.removal_curves(H=H)
    order_btw = list(btw.index)
    order_deg = list(main['degree'].sort_values(ascending=False, kind='stable').index)
    cut_btw = network.cut_off_by(order_btw, K_CLOSED, H)
    cut_deg = network.cut_off_by(order_deg, K_CLOSED, H)
    cut = ap.loc[cut_btw]
    s['fragility'] = {
        'k': K_CLOSED,
        'closed_btw': order_btw[:K_CLOSED],
        'closed_deg': order_deg[:K_CLOSED],
        'cut_btw': len(cut_btw),
        'cut_deg': len(cut_deg),
        'cut_random': round(float((1 - curves.at[K_CLOSED, 'random']) * H.number_of_nodes()), 0),
        'cut_btw_alaska': int(_alaska(cut).sum()),
        'cut_btw_share': _pct(len(cut_btw) / H.number_of_nodes(), 1),
        'ratio_btw_deg': round(len(cut_btw) / max(len(cut_deg), 1), 0),
        'remaining_100': {k: _pct(v, 0) for k, v in curves.loc[100].items()},
        'curves': curves,
    }

    # --- 5. airline strategy --------------------------------------------------------
    strat = network.airline_strategy()
    share = strat['hub_share']
    pick = lambda code: {'name': strat.at[code, 'name'], 'hub': strat.at[code, 'hub'],
                         'share': _pct(share[code]), 'routes': int(strat.at[code, 'routes'])}
    s['airlines'] = {
        'n': len(strat),
        'min_pairs': 75,
        'QR': pick('QR'), 'EK': pick('EK'), 'FR': pick('FR'), 'WN': pick('WN'), 'DL': pick('DL'),
        'U2': pick('U2'), 'LH': pick('LH'), 'TK': pick('TK'),
        'over_half': int((share > 0.5).sum()),
        'under_quarter': int((share < 0.25).sum()),
        'table': strat,
    }

    # --- regions --------------------------------------------------------------------
    labels = network.regions(H)
    desc = network.describe_regions(labels)
    s['regions'] = {'n': int(labels.nunique()), 'big': int((desc['airports'] >= 100).sum()),
                    'labels': labels, 'table': desc}
    return s


def printable(s):
    """The stats without the DataFrames/Series (for printing and the website)."""
    def clean(v):
        if isinstance(v, dict):
            return {str(k): clean(x) for k, x in v.items() if not hasattr(x, 'to_dict') or isinstance(x, dict)}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        return v
    return clean(s)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    s = compute()
    if args.json:
        print(json.dumps(printable(s), indent=2, ensure_ascii=False))
        return
    for section, values in printable(s).items():
        print(f'\n== {section}')
        for k, v in values.items():
            print(f'  {k}: {v}')
    print('\n== airline strategy (share of an airline\'s own routes touching its busiest airport)')
    print(s['airlines']['table'][['name', 'routes', 'hub', 'hub_share']].round(2).to_string())
    print('\n== regions')
    print(s['regions']['table'].to_string())


if __name__ == '__main__':
    main()
