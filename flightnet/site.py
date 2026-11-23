"""Build the website in docs/ (served by GitHub Pages).

    python -m flightnet.site

docs/index.html    the data story; every number comes from flightnet.stats, filled into
                   [[dotted.keys]] in web/story.html, so the text always matches the data
docs/explore.html  the interactive explorer (web/explore.html)
docs/assets/       network.js (the data, as a script so pages also open straight from disk),
                   common.js (shared map/graph code), the Matplotlib figures
"""

import json
import re
import shutil
from pathlib import Path

from . import data, stats, style

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).with_name('web')
DOCS = ROOT / 'docs'
FIGURES = ['route_map.png', 'hubs.png', 'reach.png', 'gateways.png', 'fragility.png', 'airline-maps.png',
           'airline-strategy.png', 'regions.png', 'compare.png']


def payload():
    """Columnar arrays: compact, and quick to turn into typed arrays in the browser."""
    ap = data.airports()
    codes = list(ap.index)
    index = {c: i for i, c in enumerate(codes)}
    al = data.airlines()
    al_index = {c: i for i, c in enumerate(al.index)}
    pairs = data.pairs()
    continents = data.CONTINENTS
    labels = stats.compute()['regions']['labels']
    with open(data.WORLD, encoding='utf-8') as f:
        world = json.load(f)
    world['features'] = [x for x in world['features'] if x['properties']['name'] != 'Antarctica']

    def clean(values):
        return [v if isinstance(v, str) else '' for v in values]

    return {
        'airports': {
            'code': codes, 'name': clean(ap['name']), 'city': clean(ap['city']), 'country': clean(ap['country']),
            'cont': [continents.index(c) if c in continents else -1 for c in ap['continent']],
            'lon': [round(v, 3) for v in ap['lon']], 'lat': [round(v, 3) for v in ap['lat']],
            'deg': ap['degree'].tolist(), 'nal': ap['airlines'].tolist(),
            'ncountries': ap['countries_served'].tolist(),
            'btw': [float(f'{v:.3g}') for v in ap['betweenness']],
            'region': [int(labels.get(c, -1)) for c in codes],
        },
        'pairs': {
            'a': [index[c] for c in pairs['a']], 'b': [index[c] for c in pairs['b']],
            'n': pairs['n_airlines'].tolist(), 'km': pairs['distance_km'].tolist(),
            'al': [[al_index[c] for c in cs] for cs in pairs['airlines']],
        },
        'airlines': {'code': list(al.index), 'name': clean(al['name']), 'country': clean(al['country'])},
        'continents': continents,
        'continentColors': [style.CONTINENT_COLORS[c] for c in continents],
        'world': world,
        'source': style.SOURCE_NOTE,
    }


def fmt(value):
    if isinstance(value, float):
        return f'{value:,.1f}'.rstrip('0').rstrip('.') if value % 1 else f'{value:,.0f}'
    if isinstance(value, int):
        return f'{value:,}'
    return str(value)


def lookup(tree, dotted):
    node = tree
    for part in dotted.split('.'):
        node = node[int(part)] if isinstance(node, list) else (node[part] if part in node else node[int(part)])
    return node


def fill(template, values):
    missing = []

    def sub(match):
        try:
            return fmt(lookup(values, match.group(1)))
        except (KeyError, TypeError, ValueError, IndexError):
            missing.append(match.group(1))
            return match.group(0)

    html = re.sub(r'\[\[([\w.]+)\]\]', sub, template)
    if missing:
        raise SystemExit(f'template placeholders without a value: {sorted(set(missing))}')
    return html


def main():
    assets = DOCS / 'assets'
    (assets / 'img').mkdir(parents=True, exist_ok=True)
    s = stats.compute()
    values = stats.printable(s)

    js = 'window.NETWORK = ' + json.dumps(payload(), separators=(',', ':'), ensure_ascii=False) + ';\n'
    (assets / 'network.js').write_text(js, encoding='utf-8')
    shutil.copy(WEB / 'common.js', assets / 'common.js')
    shutil.copy(WEB / 'site.css', assets / 'site.css')
    for name in FIGURES:
        src = ROOT / 'figures' / name
        if src.exists():
            shutil.copy(src, assets / 'img' / name)
        else:
            print(f'warning: {src} missing; run python -m flightnet.figures')

    (DOCS / 'index.html').write_text(fill((WEB / 'story.html').read_text(encoding='utf-8'), values), encoding='utf-8')
    (DOCS / 'explore.html').write_text(fill((WEB / 'explore.html').read_text(encoding='utf-8'), values),
                                       encoding='utf-8')
    (DOCS / '.nojekyll').write_text('')
    print(f"wrote docs/index.html, docs/explore.html, docs/assets/ (network.js {len(js) / 1e6:.1f} MB)")


if __name__ == '__main__':
    main()
