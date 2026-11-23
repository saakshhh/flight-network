"""Regenerate every figure in figures/ and the website in docs/.

    python -m flightnet.figures
"""

import subprocess
import sys

COMMANDS = [
    ['flightnet.routemap', '-o', 'figures/route_map.png'],
    ['flightnet.routemap', '--top', '200', '--straight', '--projection', 'lonlat', '--color-by', 'airlines',
     '-o', 'figures/homework_style.png'],
    *[['flightnet.charts', name, '-o', f'figures/{name}.png']
      for name in ['hubs', 'reach', 'gateways', 'fragility', 'airline-maps', 'airline-strategy', 'regions',
                   'compare']],
    ['flightnet.site'],  # docs/index.html + docs/explore.html (+ copies the PNGs to docs/img/)
]

if __name__ == '__main__':
    for module, *args in COMMANDS:
        print('→', module, *args, flush=True)
        subprocess.run([sys.executable, '-m', module, *args], check=True)
