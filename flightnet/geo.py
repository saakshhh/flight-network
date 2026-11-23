"""Geography: great-circle paths, the date line, and the Equal Earth map projection.

Matplotlib's default lon/lat plot (plate carrée) stretches everything near the poles, so
Greenland looks as big as Africa. Equal Earth (Šavrič, Patterson & Jenny, 2018) keeps areas
true and is a few lines of math, so no cartopy/GDAL install is needed.
"""

import json
import math

import numpy as np
from geographiclib.geodesic import Geodesic

from .data import WORLD

# ---- Equal Earth -------------------------------------------------------------------
_A1, _A2, _A3, _A4 = 1.340264, -0.081106, 0.000893, 0.003796
_M = math.sqrt(3) / 2


def project(lon, lat):
    """Equal Earth projection. Takes degrees (scalars or arrays), returns x, y (unit sphere)."""
    lam = np.radians(np.asarray(lon, dtype=float))
    theta = np.arcsin(_M * np.sin(np.radians(np.asarray(lat, dtype=float))))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = 2 * math.sqrt(3) * lam * np.cos(theta) / (3 * (9 * _A4 * t6 * t2 + 7 * _A3 * t6 + 3 * _A2 * t2 + _A1))
    y = theta * (_A4 * t6 * t2 + _A3 * t6 + _A2 * t2 + _A1)
    return x, y


def outline(n=181):
    """The edge of the world map (the ±180° meridians), projected, as one closed ring."""
    lat = np.linspace(-90, 90, n)
    lon = np.concatenate([np.full(n, 180.0), np.full(n, -180.0)])
    x, y = project(lon, np.concatenate([lat, lat[::-1]]))
    return np.column_stack([x, y])


def plate_carree(lon, lat):
    """The plain lon/lat 'projection' the homework used, for comparison."""
    return np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)


PROJECTIONS = {'equal-earth': project, 'lonlat': plate_carree}


def countries(path=WORLD):
    """Natural Earth country outlines: a list of (name, continent, [ring, ...]) in lon/lat."""
    with open(path, encoding='utf-8') as file:
        world = json.load(file)
    out = []
    for feature in world['features']:
        geometry = feature['geometry']
        # polygons and multipolygons store their coordinates a little differently
        polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
        rings = [np.asarray(ring) for polygon in polygons for ring in polygon[:1]]  # outer rings only
        out.append((feature['properties']['name'], feature['properties']['continent'], rings))
    return out


# ---- great circles -----------------------------------------------------------------
def split_dateline(points):
    """Split a path whose longitudes run past ±180° into pieces that stay on the map.

    `points` may use "unrolled" longitudes (e.g. 200° instead of -160°), which is what makes
    the crossing easy to spot: each time the path moves into the next 360° band it crosses
    the date line, and we cut it there, interpolating the latitude at the crossing.
    """
    def zone(lon):
        return math.floor((lon + 180) / 360)

    def wrap(lon):
        return lon - 360 * zone(lon)

    parts = []
    current = [(wrap(points[0][0]), points[0][1])]
    for (lon1, lat1), (lon2, lat2) in zip(points, points[1:]):
        z1, z2 = zone(lon1), zone(lon2)
        if z1 == z2:
            current.append((wrap(lon2), lat2))
            continue
        if z2 > z1:
            boundary, edge1, edge2 = 180 + 360 * z1, 180, -180
        else:
            boundary, edge1, edge2 = -180 + 360 * z1, -180, 180
        lat_cross = lat1 + (boundary - lon1) / (lon2 - lon1) * (lat2 - lat1)
        current.append((edge1, lat_cross))
        parts.append(current)
        current = [(edge2, lat_cross), (wrap(lon2), lat2)]
    parts.append(current)
    return parts


_MASK = Geodesic.LATITUDE | Geodesic.LONGITUDE | Geodesic.LONG_UNROLL


def great_circle(start, end, max_step_km=250):
    """Shortest path over the WGS84 ellipsoid between two (lon, lat) points.

    Returns a list of pieces (more than one when the route crosses the date line), each a
    list of (lon, lat). Long routes get more points so they stay smooth.
    """
    (lon1, lat1), (lon2, lat2) = start, end
    line = Geodesic.WGS84.InverseLine(lat1, lon1, lat2, lon2)
    steps = max(2, int(math.ceil(line.s13 / 1000 / max_step_km)))
    points = []
    for i in range(steps + 1):
        position = line.Position(line.s13 * i / steps, _MASK)
        points.append((position['lon2'], position['lat2']))
    return split_dateline(points)


def straight(start, end):
    """The homework's straight lon/lat segment (one piece, no date-line handling)."""
    return [[tuple(start), tuple(end)]]
