"""One visual system for every figure: colors and Matplotlib defaults."""

import matplotlib as mpl
from matplotlib.colors import LinearSegmentedColormap

SURFACE = '#fcfcfb'
LAND = '#ecebe7'
COASTLINE = '#c9c7c0'
TEXT_PRIMARY = '#0b0b0b'
TEXT_SECONDARY = '#52514e'
TEXT_MUTED = '#77766f'
GRID = '#e4e3df'
ACCENT = '#2a78d6'
HIGHLIGHT = '#eb6834'

# Okabe–Ito colors: distinguishable with the common color-vision deficiencies.
CONTINENT_COLORS = {
    'North America': '#0072B2',
    'South America': '#009E73',
    'Europe':        '#56B4E9',
    'Africa':        '#E69F00',
    'Asia':          '#D55E00',
    'Oceania':       '#CC79A7',
}

# Single-hue sequential ramp (light -> dark blue) for routes and other continuous values.
SEQUENTIAL = LinearSegmentedColormap.from_list(
    'flight_blue', ['#cde2fb', '#86b6ef', '#3987e5', '#256abf', '#184f95', '#0d366b'])

SOURCE_NOTE = 'Data: OpenFlights route database (2014 snapshot, ODbL) · airports: OurAirports · map: Natural Earth'


def apply():
    mpl.rcParams.update({
        'figure.facecolor': SURFACE,
        'axes.facecolor': SURFACE,
        'savefig.facecolor': SURFACE,
        'font.family': 'DejaVu Sans',
        'font.size': 10,
        'text.color': TEXT_PRIMARY,
        'axes.labelcolor': TEXT_SECONDARY,
        'axes.edgecolor': GRID,
        'axes.linewidth': 0.8,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.grid': True,
        'axes.axisbelow': True,
        'grid.color': GRID,
        'grid.linewidth': 0.6,
        'xtick.color': TEXT_SECONDARY,
        'ytick.color': TEXT_SECONDARY,
        'xtick.major.size': 0,
        'ytick.major.size': 0,
        'legend.frameon': False,
        'axes.titleweight': 'bold',
        'axes.titlesize': 11,
        'axes.titlelocation': 'left',
        'figure.titleweight': 'bold',
        'figure.titlesize': 14,
        'savefig.dpi': 200,
        'savefig.bbox': 'tight',
    })


def footnote(fig, text=SOURCE_NOTE, y=0.005):
    fig.text(0.01, y, text, fontsize=7.5, color=TEXT_MUTED, ha='left', va='bottom')
