"""Static world route map (homework parts 1, 2 and 5 in one command).

    python -m flightnet.routemap                          # every route, great circles, Equal Earth
    python -m flightnet.routemap --top 200 --straight --projection lonlat --color-by airlines
                                                          # the homework version: 200 busiest, straight lines
    python -m flightnet.routemap --airline EK -o figures/emirates.png
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from . import data, maps, style


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--top', type=int, help='only the N routes sold by the most airlines')
    p.add_argument('--min-airlines', type=int, default=1, help='hide routes with fewer airlines')
    p.add_argument('--min-degree', type=int, default=0,
                   help='hide airports (and their routes) with fewer nonstop destinations')
    p.add_argument('--airline', help='two-letter airline code, e.g. EK, FR, DL')
    p.add_argument('--straight', action='store_true', help='straight lon/lat lines instead of great circles')
    p.add_argument('--projection', choices=['equal-earth', 'lonlat'], default='equal-earth')
    p.add_argument('--color-by', choices=['continent', 'airlines'], default='continent',
                   help='airport color: continent, or number of airlines serving it')
    p.add_argument('-o', '--output', type=Path, help='save to this file (PNG, SVG, PDF...)')
    p.add_argument('--show', action='store_true', help='open a window')
    return p


def draw(args, fig=None, ax=None):
    pairs = data.filter_pairs(args.min_airlines, args.min_degree, args.airline, args.top)
    if fig is None:
        fig, ax = plt.subplots(figsize=(13, 6.4))
        fig.subplots_adjust(left=0.01, right=0.99, top=0.89, bottom=0.15)
    maps.draw_basemap(ax, args.projection)
    many = len(pairs) > 3000
    maps.draw_routes(ax, pairs, args.projection, geodesic=not args.straight,
                     alpha=0.35 if many else 0.75, width_scale=0.6 if many else 1.0)
    codes = sorted(set(pairs['a']) | set(pairs['b']))
    maps.draw_airports(ax, codes, args.projection, color_by=args.color_by)
    maps.map_legends(ax, args.color_by, loc_y=-0.01)

    what = f'{len(pairs):,} routes between {len(codes):,} airports'
    if args.airline:
        name = data.airlines()['name'].get(args.airline, args.airline)
        title = f'{name}: {what}'
    elif args.top:
        title = f'The {args.top} routes sold by the most airlines'
    else:
        title = f'The world\'s nonstop air routes: {what}'
    fig.suptitle(title, x=0.01, ha='left', y=0.975)
    lines = 'straight lon/lat lines' if args.straight else 'great-circle paths (the way planes actually fly)'
    fig.text(0.01, 0.91, f'{lines} · darker, thicker = more airlines sell the route · '
             f'circle area = nonstop destinations', color=style.TEXT_SECONDARY, fontsize=9.5)
    style.footnote(fig)
    return fig, ax


def main():
    args = parser().parse_args()
    style.apply()
    fig, _ = draw(args)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output)
        print(f'saved {args.output}')
    if args.show or not args.output:
        plt.show()


if __name__ == '__main__':
    main()
