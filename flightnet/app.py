"""Interactive desktop explorer (homework parts 3, 4 and 5 in one window).

    python -m flightnet.app

- Hover an airport or route for details (tooltip flips sides near the edges so it stays visible)
- Click an airport to highlight its routes; click empty sea or press Esc to clear
- Filter by minimum destinations, minimum airlines per route, and airline
- Search an airport by code or city
- Switch between great circles and straight lines, Equal Earth and plain lon/lat

Works with PyQt5, PyQt6 or PySide6 (whichever is installed).
"""

import logging
import sys

import matplotlib
matplotlib.use('QtAgg')

import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.backends.qt_compat import QtCore, QtWidgets  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from . import data, geo, maps, style  # noqa: E402

Qt = QtCore.Qt
# zooming with an equal aspect makes Matplotlib widen one axis and log a note each time; it's expected
logging.getLogger('matplotlib.axes._base').setLevel(logging.ERROR)
HORIZONTAL = getattr(Qt, 'Horizontal', None) or Qt.Orientation.Horizontal


class FlightExplorer(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        style.apply()
        self.airports = data.airports()
        self.max_degree = int(self.airports['degree'].max())
        self.selected = None          # IATA code of the clicked airport
        self.routes_artist = self.highlight_artist = self.nodes_artist = None
        self.visible_pairs = data.pairs().iloc[0:0]
        self.segment_rows = np.array([], dtype=int)
        self.node_codes = np.array([])

        self.figure = Figure(figsize=(12, 6.5))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_axes([0.005, 0.01, 0.99, 0.93])
        self.tooltip = self.ax.annotate(
            '', xy=(0, 0), xytext=(15, 15), textcoords='offset points', fontsize=9, zorder=10,
            bbox=dict(boxstyle='round,pad=0.5', fc='white', ec=style.COASTLINE, alpha=0.96),
            arrowprops=dict(arrowstyle='-', color=style.TEXT_MUTED))
        self.tooltip.set_visible(False)

        self._build_controls()
        self.redraw_basemap()
        self.canvas.mpl_connect('motion_notify_event', self.on_hover)
        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.canvas.mpl_connect('key_press_event', lambda e: e.key == 'escape' and self.select(None))
        self.canvas.setFocusPolicy(getattr(Qt, 'StrongFocus', None) or Qt.FocusPolicy.StrongFocus)

    # ---- controls -------------------------------------------------------------------
    def _slider(self, low, high, value):
        slider = QtWidgets.QSlider(HORIZONTAL)
        slider.setRange(low, high)
        slider.setValue(value)
        slider.setTracking(False)  # redraw on release, not on every pixel of a drag
        label = QtWidgets.QLabel(str(value))
        label.setMinimumWidth(28)
        slider.sliderMoved.connect(lambda v: label.setText(str(v)))
        slider.valueChanged.connect(lambda v: label.setText(str(v)))
        slider.valueChanged.connect(self.update_plot)
        return slider, label

    def _build_controls(self):
        self.degree_slider, degree_label = self._slider(0, self.max_degree, 10)
        self.airlines_slider, airlines_label = self._slider(1, 10, 1)

        self.airline_box = QtWidgets.QComboBox()
        self.airline_box.addItem('All airlines', None)
        table = data.airlines()
        for code, row in table.iterrows():
            self.airline_box.addItem(f"{row['name']} ({code}) · {row['airports']} airports", code)
        self.airline_box.currentIndexChanged.connect(self.update_plot)

        self.geodesic_box = QtWidgets.QCheckBox('Great circles')
        self.geodesic_box.setChecked(True)
        self.geodesic_box.toggled.connect(self.update_plot)
        self.projection_box = QtWidgets.QComboBox()
        self.projection_box.addItem('Equal Earth', 'equal-earth')
        self.projection_box.addItem('Lon/lat grid', 'lonlat')
        self.projection_box.currentIndexChanged.connect(self.redraw_basemap)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Find airport: code or city…')
        labels = [f"{c} · {r['city']}, {r['country']}" for c, r in self.airports.iterrows()]
        completer = QtWidgets.QCompleter(labels)
        completer.setCaseSensitivity(getattr(Qt, 'CaseInsensitive', None) or Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(getattr(Qt, 'MatchContains', None) or Qt.MatchFlag.MatchContains)
        completer.activated.connect(lambda text: self.select(text.split(' · ')[0]))
        self.search.setCompleter(completer)
        self.search.returnPressed.connect(self.search_airport)

        self.status = QtWidgets.QLabel()
        self.status.setStyleSheet(f'color: {style.TEXT_SECONDARY}')

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel('Min. destinations'))
        row1.addWidget(degree_label)
        row1.addWidget(self.degree_slider, 2)
        row1.addSpacing(16)
        row1.addWidget(QtWidgets.QLabel('Min. airlines per route'))
        row1.addWidget(airlines_label)
        row1.addWidget(self.airlines_slider, 1)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(self.airline_box, 2)
        row2.addWidget(self.search, 2)
        row2.addWidget(self.geodesic_box)
        row2.addWidget(self.projection_box)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.status)
        self.setWindowTitle('Flight network explorer')

    @property
    def projection(self):
        return self.projection_box.currentData()

    # ---- drawing --------------------------------------------------------------------
    def redraw_basemap(self, *_):
        for artist in list(self.ax.collections) + list(self.ax.lines):
            artist.remove()
        self.routes_artist = self.highlight_artist = self.nodes_artist = None
        maps.draw_basemap(self.ax, self.projection)
        self.ax.set_adjustable('datalim')
        self.full_view = (self.ax.get_xlim(), self.ax.get_ylim())
        self.update_plot()

    def update_plot(self, *_):
        self.tooltip.set_visible(False)
        for artist in (self.routes_artist, self.highlight_artist, self.nodes_artist):
            if artist is not None:
                artist.remove()
        self.highlight_artist = None

        airline = self.airline_box.currentData()
        # a selected airport shows all its routes: the destinations filter would hide its small neighbors
        min_degree = 0 if self.selected else self.degree_slider.value()
        pairs = data.filter_pairs(self.airlines_slider.value(), min_degree, airline)
        if self.selected is not None:
            pairs = pairs[(pairs['a'] == self.selected) | (pairs['b'] == self.selected)]
        self.visible_pairs = pairs.reset_index(drop=True)
        many = len(pairs) > 3000
        self.routes_artist, self.segment_rows = maps.draw_routes(
            self.ax, self.visible_pairs, self.projection, geodesic=self.geodesic_box.isChecked(),
            color=style.HIGHLIGHT if self.selected else None,
            alpha=0.35 if many else 0.75, width_scale=0.6 if many else 1.0)
        self.routes_artist.set_pickradius(4)

        codes = sorted(set(pairs['a']) | set(pairs['b']) | ({self.selected} if self.selected else set()))
        self.nodes_artist, self.node_codes = maps.draw_airports(self.ax, codes, self.projection)

        self.zoom(codes if (airline or self.selected) else None)

        name = data.airlines()['name'].get(airline, 'All airlines') if airline else 'All airlines'
        title = f'{name}: {len(pairs):,} routes, {len(codes):,} airports'
        if self.selected:
            title = f"{self.airports.at[self.selected, 'city']} ({self.selected}) · " + title
        self.ax.set_title(title, loc='left', fontsize=12)
        hint = 'Click an airport to focus on it' if not self.selected else 'Click empty space or press Esc to clear'
        self.status.setText(f'{hint} · color/width = airlines on the route · circle area = nonstop destinations · '
                            f'{style.SOURCE_NOTE}')
        self.canvas.draw_idle()

    def zoom(self, codes):
        """Fit the view to these airports (or the whole world for None)."""
        if not codes:
            self.ax.set_xlim(*self.full_view[0])
            self.ax.set_ylim(*self.full_view[1])
            return
        ap = self.airports.loc[list(codes)]
        x, y = geo.PROJECTIONS[self.projection](ap['lon'].to_numpy(), ap['lat'].to_numpy())
        (fx0, fx1), (fy0, fy1) = self.full_view
        pad_x = max((x.max() - x.min()) * 0.1, (fx1 - fx0) * 0.03)
        pad_y = max((y.max() - y.min()) * 0.1, (fy1 - fy0) * 0.03)
        self.ax.set_xlim(max(fx0, x.min() - pad_x), min(fx1, x.max() + pad_x))
        self.ax.set_ylim(max(fy0, y.min() - pad_y), min(fy1, y.max() + pad_y))

    def select(self, code):
        if code is not None and code not in self.airports.index:
            return
        self.selected = code
        self.update_plot()

    def search_airport(self):
        text = self.search.text().strip()
        code = text.split(' · ')[0].upper()
        if code not in self.airports.index:
            matches = self.airports[self.airports['city'].str.lower() == text.lower()]
            code = matches['degree'].idxmax() if len(matches) else None
        self.select(code)

    # ---- interaction ----------------------------------------------------------------
    def _airport_at(self, event):
        if self.nodes_artist is None:
            return None
        hit, info = self.nodes_artist.contains(event)
        if not hit or not len(info['ind']):
            return None
        # several circles can overlap: take the biggest (they're drawn biggest first)
        return self.node_codes[min(info['ind'])]

    def show_tooltip(self, xy, text, event):
        self.tooltip.xy = xy
        self.tooltip.set_text(text)
        right = event.x > self.ax.bbox.x0 + self.ax.bbox.width * 0.6
        top = event.y > self.ax.bbox.y0 + self.ax.bbox.height * 0.75
        self.tooltip.set_position((-15 if right else 15, -15 if top else 15))
        self.tooltip.set_horizontalalignment('right' if right else 'left')
        self.tooltip.set_verticalalignment('top' if top else 'bottom')
        self.tooltip.set_visible(True)
        self.canvas.draw_idle()

    def on_hover(self, event):
        if event.inaxes == self.ax:
            code = self._airport_at(event)
            if code is not None:
                a = self.airports.loc[code]
                xy = geo.PROJECTIONS[self.projection](a['lon'], a['lat'])
                return self.show_tooltip(xy, data.describe_airport(code), event)
            if self.routes_artist is not None and len(self.segment_rows):
                hit, info = self.routes_artist.contains(event)
                if hit and len(info['ind']):
                    # prefer the busiest route under the cursor (drawn last = highest index)
                    row = self.visible_pairs.iloc[self.segment_rows[max(info['ind'])]]
                    return self.show_tooltip((event.xdata, event.ydata), data.describe_pair(row), event)
        if self.tooltip.get_visible():
            self.tooltip.set_visible(False)
            self.canvas.draw_idle()

    def on_click(self, event):
        if event.inaxes != self.ax:
            return
        self.select(self._airport_at(event))


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = FlightExplorer()
    window.resize(1300, 850)
    window.show()
    sys.exit(app.exec() if hasattr(app, 'exec') else app.exec_())


if __name__ == '__main__':
    main()
