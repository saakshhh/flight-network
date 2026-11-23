"""Drawing blocks shared by every map: basemap, routes, airports and their legends."""

from functools import lru_cache

import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

from . import data, geo, style

ROUTE_NORM = Normalize(1, 10, clip=True)
SOUTH = -58  # southern edge of every map (the southernmost airport with routes is at 54.8°S)  # 10+ airlines all get the darkest blue


def airport_size(degree, scale=0.6):
    """Marker *area* grows linearly with the number of destinations, so it reads honestly."""
    return 2 + scale * np.asarray(degree, dtype=float)


def route_style(n_airlines):
    v = ROUTE_NORM(np.asarray(n_airlines, dtype=float))
    return style.SEQUENTIAL(0.25 + 0.75 * v), 0.25 + 1.6 * v


def draw_basemap(ax, projection='equal-earth', land=style.LAND, coast=style.COASTLINE):
    """Countries as filled shapes plus the map's outer edge; turns the axes off."""
    project = geo.PROJECTIONS[projection]
    polygons = []
    for name, _, rings in _countries():
        if name == 'Antarctica':  # no airports with routes; cropping it gives the map 30% more room
            continue
        for ring in rings:
            x, y = project(ring[:, 0], ring[:, 1])
            polygons.append(np.column_stack([x, y]))
    ax.add_collection(PolyCollection(polygons, facecolors=land, edgecolors=coast, linewidths=0.35, zorder=0))
    if projection == 'equal-earth':
        edge = geo.outline()
        ax.plot(edge[:, 0], edge[:, 1], color=coast, linewidth=0.8, zorder=0)
        ax.set_xlim(edge[:, 0].min() * 1.01, edge[:, 0].max() * 1.01)
        ax.set_ylim(geo.project(0, SOUTH)[1], edge[:, 1].max() * 1.02)
    else:
        ax.set_xlim(-180, 180)
        ax.set_ylim(SOUTH, 85)
    ax.set_aspect('equal')
    ax.set_axis_off()


@lru_cache(maxsize=1)
def _countries():
    return geo.countries()


@lru_cache(maxsize=None)
def _path(a, b, geodesic):
    pos = data.airports()[['lon', 'lat']]
    start, end = tuple(pos.loc[a]), tuple(pos.loc[b])
    return geo.great_circle(start, end) if geodesic else geo.straight(start, end)


def route_segments(pair_table, projection='equal-earth', geodesic=True):
    """Projected line pieces for every route, and for each piece the row it belongs to.

    One route can become two pieces when its great circle crosses the date line.
    """
    project = geo.PROJECTIONS[projection]
    segments, owner = [], []
    for i, (a, b) in enumerate(zip(pair_table['a'], pair_table['b'])):
        for piece in _path(a, b, geodesic):
            piece = np.asarray(piece)
            x, y = project(piece[:, 0], piece[:, 1])
            segments.append(np.column_stack([x, y]))
            owner.append(i)
    return segments, np.asarray(owner, dtype=int)


def draw_routes(ax, pair_table, projection='equal-earth', geodesic=True, color=None, alpha=0.7,
                width_scale=1.0, zorder=1):
    """Routes as one LineCollection (fast enough for all 19k routes).

    Color and width encode how many airlines sell the route, unless `color` is given.
    Busier routes are drawn last so they sit on top. Returns (collection, rows), where rows[i]
    is the position in `pair_table` of the route drawn as segment i (for tooltips).
    """
    ordered = pair_table.reset_index(drop=True)
    order = np.argsort(ordered['n_airlines'].to_numpy(), kind='stable')
    ordered = ordered.iloc[order].reset_index(drop=True)
    segments, owner = route_segments(ordered, projection, geodesic)
    colors, widths = route_style(ordered['n_airlines'].to_numpy()[owner]) if len(owner) else ([], [])
    if color is not None:
        colors = color
    lines = LineCollection(segments, colors=colors, linewidths=np.asarray(widths) * width_scale,
                           alpha=alpha, zorder=zorder, capstyle='round')
    ax.add_collection(lines)
    return lines, order[owner] if len(owner) else owner


def draw_airports(ax, codes, projection='equal-earth', color_by='continent', size_scale=0.6,
                  zorder=3, **kwargs):
    """Airports sized by destinations; colored by continent, by number of airlines, or one color."""
    ap = data.airports().loc[list(codes)]
    x, y = geo.PROJECTIONS[projection](ap['lon'].to_numpy(), ap['lat'].to_numpy())
    fixed = kwargs.pop('s', None)
    sizes = airport_size(ap['degree'], size_scale) if fixed is None else np.full(len(ap), float(fixed))
    order = np.argsort(-sizes, kind='stable')  # big circles first so small ones stay visible
    if color_by == 'continent':
        colors = ap['continent'].map(style.CONTINENT_COLORS).fillna(style.TEXT_MUTED).to_numpy()
        extra = dict(c=colors[order])
    elif color_by == 'airlines':
        extra = dict(c=ap['airlines'].to_numpy()[order], cmap='viridis', norm=Normalize(1, 100, clip=True))
    else:
        extra = dict(color=color_by)
    defaults = dict(edgecolors='white', linewidths=0.3)
    defaults.update(kwargs)
    points = ax.scatter(x[order], y[order], s=sizes[order], zorder=zorder, **extra, **defaults)
    return points, ap.index.to_numpy()[order]


# ---- legends ------------------------------------------------------------------------
def continent_handles(marker_size=6):
    return [Line2D([], [], marker='o', linestyle='', markersize=marker_size, markerfacecolor=c,
                   markeredgecolor='white', label=name) for name, c in style.CONTINENT_COLORS.items()]


def size_handles(values=(10, 50, 100, 200), scale=0.6, color='#9a998f'):
    return [Line2D([], [], marker='o', linestyle='', markersize=np.sqrt(airport_size(v, scale)),
                   markerfacecolor='none', markeredgecolor=color, label=f'{v}') for v in values]


def route_handles(values=(1, 3, 6, 10)):
    handles = []
    for v in values:
        color, width = route_style(v)
        handles.append(Line2D([], [], color=color, linewidth=width * 1.5,
                              label=f'{v}+' if v == ROUTE_NORM.vmax else str(v)))
    return handles


def map_legends(ax, color_by='continent', loc_y=0.0):
    """Three compact legends under the map: route airlines, airport destinations, color."""
    fig = ax.figure
    common = dict(frameon=False, fontsize=8, title_fontsize=8.5, handletextpad=0.4, columnspacing=1.0,
                  borderaxespad=0)
    leg1 = ax.legend(handles=route_handles(), title='Airlines on the route', ncol=4,
                     loc='upper left', bbox_to_anchor=(0.0, loc_y), **common)
    ax.add_artist(leg1)
    leg2 = ax.legend(handles=size_handles(), title='Nonstop destinations', ncol=4,
                     loc='upper center', bbox_to_anchor=(0.47, loc_y), **common)
    ax.add_artist(leg2)
    if color_by == 'continent':
        ax.legend(handles=continent_handles(), title='Continent', ncol=3, loc='upper right',
                  bbox_to_anchor=(1.0, loc_y), **common)
    elif color_by == 'airlines':
        from matplotlib.cm import ScalarMappable
        cax = fig.add_axes([0.78, 0.07, 0.17, 0.018])
        cb = fig.colorbar(ScalarMappable(Normalize(1, 100), 'viridis'), cax=cax, orientation='horizontal')
        cb.set_label('Airlines serving the airport (100+)', fontsize=8)
        cb.ax.tick_params(labelsize=7)
    return fig
