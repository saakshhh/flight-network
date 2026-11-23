"""The analysis charts behind each finding.

    python -m flightnet.charts hubs -o figures/hubs.png
    python -m flightnet.charts NAME --show

NAME is one of: hubs, reach, gateways, fragility, airline-maps, airline-strategy, regions, compare
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, PercentFormatter

from . import data, geo, maps, network, stats, style


def _title(fig, title, subtitle, y=0.985):
    fig.suptitle(title, x=0.01, ha='left', y=y)
    fig.text(0.01, y - 0.06, subtitle, color=style.TEXT_SECONDARY, fontsize=9.5, va='top')


def _continent_colors(codes):
    return data.airports().loc[codes, 'continent'].map(style.CONTINENT_COLORS).fillna(style.TEXT_MUTED)


# ---- 1. hubs -------------------------------------------------------------------------
def hubs():
    s = stats.compute()['hubs']
    ap, pairs = data.airports(), data.pairs()
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={'width_ratios': [1.1, 1]})
    fig.subplots_adjust(top=0.8, bottom=0.12, wspace=0.35, left=0.07, right=0.98)

    order = ap['degree'].sort_values(ascending=False, kind='stable').index
    rank = {c: i for i, c in enumerate(order)}
    first = np.minimum(pairs['a'].map(rank), pairs['b'].map(rank)).to_numpy()  # best-ranked end
    counts = np.bincount(first, minlength=len(order))
    x = np.arange(1, len(order) + 1) / len(order) * 100
    y = np.cumsum(counts) / len(pairs) * 100
    left.plot([0, 100], [0, 100], color=style.GRID, linewidth=1, linestyle='--')
    left.text(62, 55, 'if every airport\nhad equal share', color=style.TEXT_MUTED, fontsize=8.5, rotation=0)
    left.plot(x, y, color=style.ACCENT, linewidth=2.2)
    i5 = s['top5_count'] - 1
    left.scatter([x[i5]], [y[i5]], color=style.ACCENT, zorder=3, s=30)
    left.annotate(f"the top 5% of airports ({s['top5_count']})\ntouch {s['top5_pair_share']:.0f}% of all routes",
                  (x[i5], y[i5]), xytext=(14, 30), textcoords='offset points', fontsize=9.5,
                  arrowprops=dict(arrowstyle='-', color=style.TEXT_MUTED, linewidth=0.8))
    left.set_xlim(0, 100)
    left.set_ylim(0, 102)
    left.xaxis.set_major_formatter(PercentFormatter())
    left.yaxis.set_major_formatter(PercentFormatter())
    left.set_xlabel('Airports, from most to fewest destinations')
    left.set_ylabel('Routes that touch them')
    left.set_title('A few airports carry most of the network')

    top = order[:12][::-1]
    right.barh(range(len(top)), ap.loc[top, 'degree'], color=_continent_colors(top), height=0.7)
    right.set_yticks(range(len(top)), [f"{ap.at[c, 'city']} ({c})" for c in top], fontsize=9)
    for i, c in enumerate(top):
        right.text(ap.at[c, 'degree'] + 3, i, str(ap.at[c, 'degree']), va='center', fontsize=8.5,
                   color=style.TEXT_SECONDARY)
    right.grid(axis='y', visible=False)
    right.set_xlabel('Nonstop destinations')
    right.set_title(f"Busiest hubs (the median airport has {s['median_degree']})")
    right.set_xlim(0, 370)
    right.legend(handles=maps.continent_handles(5), fontsize=7.5, loc='lower right', ncol=2)
    _title(fig, 'Hubs: a handful of airports hold the network together',
           f"{s['small_share']:.0f}% of airports have 2 or fewer nonstop destinations; "
           f"Amsterdam has {s['max_degree']}")
    style.footnote(fig)
    return fig


# ---- 2. reach ------------------------------------------------------------------------
def reach():
    s = stats.compute()['reach']
    dist = {int(k): v for k, v in s['distribution'].items()}
    within = {int(k): v for k, v in s['within'].items()}
    cap = 9
    ks = list(range(1, cap + 1))
    vals = [dist[k] for k in ks[:-1]] + [sum(v for k, v in dist.items() if k >= cap)]
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.subplots_adjust(top=0.8, bottom=0.18, left=0.08, right=0.98)
    colors = [style.ACCENT if k <= 4 else '#86b6ef' for k in ks]
    ax.bar(ks, vals, color=colors, width=0.72)
    for k, v in zip(ks, vals):
        label = f'{v:.1f}%' if v >= 0.1 else '<0.1%'
        ax.text(k, v + 0.6, label, ha='center', fontsize=9, color=style.TEXT_PRIMARY)
        if 2 <= k <= 7:
            ax.text(k, -3.2, f'{within[k]:.0f}% within', ha='center', fontsize=8, color=style.TEXT_MUTED)
    ax.set_xticks(ks, [str(k) for k in ks[:-1]] + [f'{cap}–{s["diameter"]}'])
    ax.set_xlabel('Flights needed on the fastest connection', labelpad=18)
    ax.set_ylabel('Share of airport pairs')
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylim(0, max(vals) * 1.15)
    ax.grid(axis='x', visible=False)
    ax.annotate(f"average: {s['mean_flights']} flights", (4, dist[4]), xytext=(60, -10),
                textcoords='offset points', fontsize=10, color=style.TEXT_PRIMARY,
                arrowprops=dict(arrowstyle='-', color=style.TEXT_MUTED, linewidth=0.8))
    a, b = s['far_a'], s['far_b']
    _title(fig, f"A small world: {within[4]:.0f}% of airport pairs are 4 flights or fewer apart",
           f"Over all {stats.compute()['overview']['main_airports']:,} airports in the connected network. "
           f"The worst case is {s['diameter']} flights: {a['city']}, {a['country']} → {b['city']}, {b['country']}.")
    style.footnote(fig)
    return fig


# ---- 3. gateways ---------------------------------------------------------------------
GATEWAY_LABELS = {  # code: (dx, dy) label offset in points
    'ANC': (8, 4), 'LAX': (-10, 8), 'CDG': (-34, 6), 'DXB': (6, -10), 'FRA': (8, -2), 'AMS': (6, 4),
    'SEA': (-36, 2), 'IST': (6, -9), 'ATL': (8, -10), 'GRU': (-36, -2), 'BNE': (-36, -2), 'SFJ': (8, -12),
    'BET': (8, -2), 'DME': (-32, -10), 'PEK': (-34, -4), 'SYD': (6, -6),
}


def gateways():
    s = stats.compute()['gateways']
    ap = data.airports()
    floor = 1e-6  # fewer than 1 in a million fastest connections: not shown
    main = ap[ap['in_main_network'] & (ap['betweenness'] >= floor)]
    fig, ax = plt.subplots(figsize=(10, 6.4))
    fig.subplots_adjust(top=0.82, bottom=0.11, left=0.09, right=0.98)
    ax.scatter(main['degree'], main['betweenness'], s=12, c=_continent_colors(main.index), alpha=0.65,
               linewidths=0)
    for code, (dx, dy) in GATEWAY_LABELS.items():
        x, y = ap.at[code, 'degree'], ap.at[code, 'betweenness']
        bold = code in ('ANC', 'SFJ')
        ax.scatter([x], [y], s=34 if bold else 18, facecolor='none', edgecolor=style.TEXT_PRIMARY, linewidth=0.8)
        name = {'SFJ': 'Kangerlussuaq'}.get(code, ap.at[code, 'city'])
        ax.annotate(name if bold else code, (x, y), xytext=(dx, dy), textcoords='offset points',
                    fontsize=9.5 if bold else 8.5, fontweight='bold' if bold else 'normal')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('Nonstop destinations (log scale)')
    ax.set_ylabel('Betweenness: share of fastest connections\nthat pass through the airport (log scale)')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v * 100:.4f}'.rstrip('0').rstrip('.') + '%'))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.set_ylim(floor * 0.8, 0.15)
    ax.legend(handles=maps.continent_handles(5), fontsize=8, loc='lower right', ncol=2)
    _title(fig, 'Gateways: the most important airport isn\'t the busiest',
           f"Anchorage has only {s['anc_degree']} destinations (#{s['anc_degree_rank']} in the world), but more "
           f"fastest connections pass through it than through any other airport: it links Alaska's bush airports "
           f"to everywhere else.\nOther gateways to remote regions (Greenland, Northern Australia) also rank far "
           f"higher by betweenness than by size. Airports below 0.0001% not shown.")
    style.footnote(fig)
    return fig


# ---- 4. fragility --------------------------------------------------------------------
def fragility():
    s = stats.compute()['fragility']
    curves = s['curves'] * 100
    fig = plt.figure(figsize=(13, 5.6))
    left = fig.add_axes([0.06, 0.12, 0.3, 0.64])
    right = fig.add_axes([0.39, 0.06, 0.6, 0.74])
    labels = {'random': ('random airports', '#9a998f'), 'degree': ('busiest first (most destinations)', style.ACCENT),
              'betweenness': ('gateways first (highest betweenness)', style.HIGHLIGHT)}
    for key, (label, color) in labels.items():
        left.plot(curves.index, curves[key], color=color, linewidth=2.2)
        left.text(101, curves[key].iloc[-1], label.split(' (')[0], color=color, fontsize=8.5, va='center')
    left.axvline(s['k'], color=style.GRID, linewidth=1)
    left.set_xlim(0, 100)
    left.set_ylim(60, 101)
    left.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    left.set_xlabel('Airports closed')
    left.set_ylabel('Airports still connected to each other')
    left.set_title('Close airports one by one…')

    maps.draw_basemap(right)
    ap = data.airports()
    cut = network.cut_off_by(s['closed_btw'], s['k'])
    rest = ap.index[ap['in_main_network']].difference(cut).difference(s['closed_btw'])
    maps.draw_airports(right, rest, color_by='#c9c7c0', size_scale=0.15, linewidths=0)
    maps.draw_airports(right, cut, color_by=style.HIGHLIGHT, size_scale=0, s=10, linewidths=0, zorder=4)
    x, y = geo.project(ap.loc[s['closed_btw'], 'lon'], ap.loc[s['closed_btw'], 'lat'])
    right.scatter(x, y, marker='X', s=60, color=style.TEXT_PRIMARY, edgecolor='white', linewidth=0.6, zorder=5)
    right.set_title(f"…close just the top {s['k']} gateways and {s['cut_btw']} airports are cut off "
                    f"({s['cut_btw_alaska']} of them in Alaska)", loc='left')
    right.legend(handles=[Line2D([], [], marker='X', linestyle='', color=style.TEXT_PRIMARY, label='closed'),
                          Line2D([], [], marker='o', linestyle='', color=style.HIGHLIGHT, label='cut off'),
                          Line2D([], [], marker='o', linestyle='', color='#c9c7c0', label='still connected')],
                 loc='lower left', fontsize=8.5, ncol=3)
    _title(fig, 'Fragility: losing the gateways hurts far more than losing the biggest hubs',
           f"Closing the {s['k']} highest-betweenness airports cuts off {s['cut_btw']} airports; closing the "
           f"{s['k']} with the most destinations cuts off {s['cut_deg']}; {s['k']} random airports, about "
           f"{s['cut_random']:.0f}.")
    style.footnote(fig)
    return fig


# ---- 5. airlines ---------------------------------------------------------------------
STRATEGY_AIRLINES = ['QR', 'TK', 'LH', 'DL', 'WN', 'FR']


def _operated(code):
    r = data.routes()
    g = r[(r['airline'] == code) & ~r['codeshare']]
    p = data.pairs().set_index(['a', 'b'])
    keys = set(map(tuple, np.sort(g[['src', 'dst']].to_numpy(), axis=1)))
    return p.loc[sorted(keys)].reset_index()


def airline_maps():
    s = stats.compute()['airlines']
    table = s['table']
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.4))
    fig.subplots_adjust(top=0.86, bottom=0.04, left=0.01, right=0.99, wspace=0.04, hspace=0.18)
    for ax, code in zip(axes.flat, STRATEGY_AIRLINES):
        pairs = _operated(code)
        hub = table.at[code, 'hub']
        maps.draw_basemap(ax, coast='#dcdad4')
        touches = (pairs['a'] == hub) | (pairs['b'] == hub)
        maps.draw_routes(ax, pairs[~touches], color='#86b6ef', alpha=0.6, width_scale=0.9)
        maps.draw_routes(ax, pairs[touches], color=style.ACCENT, alpha=0.8, width_scale=0.9, zorder=2)
        codes = sorted(set(pairs['a']) | set(pairs['b']))
        maps.draw_airports(ax, codes, color_by=style.TEXT_SECONDARY, size_scale=0, s=4, linewidths=0)
        hx, hy = geo.project(data.airports().at[hub, 'lon'], data.airports().at[hub, 'lat'])
        ax.scatter([hx], [hy], s=40, color=style.HIGHLIGHT, edgecolor='white', linewidth=0.8, zorder=5)
        # zoom to the network
        ap = data.airports().loc[codes]
        x, y = geo.project(ap['lon'], ap['lat'])
        pad_x, pad_y = (x.max() - x.min()) * 0.08 + 0.05, (y.max() - y.min()) * 0.08 + 0.05
        cx, cy, half_w = (x.max() + x.min()) / 2, (y.max() + y.min()) / 2, max((x.max() - x.min()) / 2 + pad_x,
                                                                              ((y.max() - y.min()) / 2 + pad_y) * 1.5)
        ax.set_xlim(cx - half_w, cx + half_w)
        ax.set_ylim(cy - half_w / 1.5, cy + half_w / 1.5)
        ax.set_title(f"{table.at[code, 'name']}: {table.at[code, 'hub_share'] * 100:.0f}% of routes touch "
                     f"{data.airports().at[hub, 'city']}", fontsize=10, loc='left')
    _title(fig, 'Strategy on a map: hub-and-spoke vs point-to-point',
           'Each airline\'s own routes (codeshares excluded). Dark blue: routes to or from its busiest airport '
           '(orange); light blue: everything else. Left to right, top to bottom: from pure hub to no hub.',
           y=0.99)
    style.footnote(fig)
    return fig


STRATEGY_LABELS = ['US', 'QR', 'EK', 'TK', 'KL', 'BA', 'AF', 'LH', 'AC', 'DL', 'UA', 'AA', 'CA', 'U2', 'WN', 'FR',
                   'W6', 'DY', 'B6', 'SQ', 'NH', 'CZ', 'VY']


def airline_strategy():
    s = stats.compute()['airlines']
    t = s['table']
    fig, ax = plt.subplots(figsize=(11, 5.6))
    fig.subplots_adjust(top=0.82, bottom=0.11, left=0.08, right=0.98)
    lowcost = {'FR', 'WN', 'U2', 'W6', 'DY', 'B6', 'VY', 'G4', 'NK', 'TO', 'HV', '4U', 'LS', 'ZB', 'JQ', 'AK', '5J',
               'PC', 'F9', 'Y4', '6E', 'SG', 'JT', 'AD', 'G3', 'FL', 'WS', '9C', 'X3', 'TOM', 'DE', 'AB'}
    colors = [style.HIGHLIGHT if c in lowcost else style.ACCENT for c in t.index]
    ax.scatter(t['hub_share'] * 100, t['routes'], s=28, c=colors, alpha=0.8, linewidths=0)
    for code in STRATEGY_LABELS:
        if code in t.index:
            ax.annotate(t.at[code, 'name'].replace(' Airlines', '').replace(' Air Lines', '').replace(' Airways', ''),
                        (t.at[code, 'hub_share'] * 100, t.at[code, 'routes']), xytext=(5, 2),
                        textcoords='offset points', fontsize=8)
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_xlabel('Share of the airline\'s routes that start or end at its busiest airport')
    ax.set_ylabel('Routes the airline operates (log scale)')
    ax.text(2, ax.get_ylim()[1] * 0.85, '← point-to-point', fontsize=9, color=style.TEXT_MUTED, va='top')
    ax.text(98, ax.get_ylim()[1] * 0.85, 'hub-and-spoke →', fontsize=9, color=style.TEXT_MUTED, va='top', ha='right')
    ax.legend(handles=[Line2D([], [], marker='o', linestyle='', color=style.HIGHLIGHT, label='low-cost / leisure'),
                       Line2D([], [], marker='o', linestyle='', color=style.ACCENT, label='other airlines')],
              loc='lower left', fontsize=8.5)
    _title(fig, f"{s['n']} airlines, two business models",
           f"Every airline operating at least {s['min_pairs']} routes. Gulf carriers route nearly everything "
           f"through home ({s['QR']['name']} {s['QR']['share']:.0f}%, {s['EK']['name']} {s['EK']['share']:.0f}%); "
           f"{s['FR']['name']} ({s['FR']['share']:.0f}%) and {s['WN']['name']} ({s['WN']['share']:.0f}%) have no real hub.")
    style.footnote(fig)
    return fig


# ---- regions -------------------------------------------------------------------------
REGION_NAMES = {'ATL': 'North America', 'AMS': 'Europe & North Africa', 'PEK': 'East & Southeast Asia',
                'GRU': 'South America', 'DXB': 'Gulf & South Asia', 'SYD': 'Oceania', 'CMN': 'Sub-Saharan Africa',
                'JNB': 'Sub-Saharan Africa', 'ANC': 'Alaska', 'DME': 'Russia & Central Asia', 'SVO': 'Russia & Central Asia',
                'YZF': 'Northern Canada', 'YUL': 'Northern Canada', 'GOH': 'Greenland & Iceland'}
REGION_COLORS = ['#0072B2', '#56B4E9', '#D55E00', '#009E73', '#E69F00', '#CC79A7', '#8c564b', '#17becf',
                 '#7f3c8d', '#bcbd22', '#525252']


def regions():
    st = stats.compute()['regions']
    labels, table = st['labels'], st['table']
    big = table.index[table['airports'] >= 50][:len(REGION_COLORS)]
    color_of = {r: REGION_COLORS[i] for i, r in enumerate(big)}
    fig, ax = plt.subplots(figsize=(13, 6.6))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.12)
    maps.draw_basemap(ax)
    pairs = data.pairs()
    ra, rb = pairs['a'].map(labels), pairs['b'].map(labels)
    inside = pairs[(ra == rb) & ra.isin(big)]
    maps.draw_routes(ax, inside, color=[color_of[r] for r in inside['a'].map(labels).sort_index()],
                     alpha=0.12, width_scale=0.6)
    codes = labels.index
    region_color = labels.map(lambda r: color_of.get(r, '#b5b3ab'))
    for r in list(big) + ['other']:
        members = codes[labels.isin(big) == False] if r == 'other' else codes[labels == r]  # noqa: E712
        maps.draw_airports(ax, members, color_by=region_color[members].iat[0] if len(members) else 'grey',
                           size_scale=0.4, zorder=3)
    handles = []
    for r in big:
        hub = table.at[r, 'hub']
        name = REGION_NAMES.get(hub, data.airports().at[hub, 'city'])
        handles.append(Line2D([], [], marker='o', linestyle='', markersize=7, color=color_of[r],
                              label=f"{name} ({table.at[r, 'airports']})"))
    handles.append(Line2D([], [], marker='o', linestyle='', markersize=7, color='#b5b3ab', label='smaller groups'))
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.0), ncol=4, fontsize=8.5, frameon=False)
    _title(fig, 'The network\'s own regions mostly follow geography, with telling exceptions',
           f"Community detection (Louvain) splits the network into {st['n']} groups of airports that connect mainly "
           "to each other. India joins the Gulf, not Asia; Alaska and Northern Canada are worlds of their own.", y=0.975)
    style.footnote(fig)
    return fig


# ---- the homework vs now ---------------------------------------------------------------
def compare():
    """Side by side: the homework's straight lines on a lon/lat grid vs great circles on Equal Earth."""
    p = data.filter_pairs(top=300)
    p = p[(p['distance_km'] > 7000)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 3.9))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.78, bottom=0.04, wspace=0.03)
    for ax, (proj, geodesic, title) in zip(axes, [('lonlat', False, 'Homework: straight lines on a lon/lat grid'),
                                                  ('equal-earth', True, 'Now: great circles on an equal-area map')]):
        maps.draw_basemap(ax, proj)
        maps.draw_routes(ax, p, proj, geodesic=geodesic, color=style.ACCENT, alpha=0.7)
        codes = sorted(set(p['a']) | set(p['b']))
        maps.draw_airports(ax, codes, proj, color_by=style.TEXT_PRIMARY, size_scale=0, s=8, linewidths=0)
        ax.set_title(title, fontsize=10.5)
    _title(fig, 'Why the projection and the path matter',
           f'The {len(p)} longest of the 300 busiest routes. Straight lon/lat lines miss the polar routes planes '
           'really fly, and the grid makes Greenland look as big as Africa.', y=0.99)
    return fig


CHARTS = {'hubs': hubs, 'reach': reach, 'gateways': gateways, 'fragility': fragility,
          'airline-maps': airline_maps, 'airline-strategy': airline_strategy, 'regions': regions, 'compare': compare}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('chart', choices=list(CHARTS))
    p.add_argument('-o', '--output', type=Path, help='save to this file (PNG, SVG, PDF...)')
    p.add_argument('--show', action='store_true')
    args = p.parse_args()
    style.apply()
    fig = CHARTS[args.chart]()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output)
        print(f'saved {args.output}')
    if args.show or not args.output:
        plt.show()


if __name__ == '__main__':
    main()
