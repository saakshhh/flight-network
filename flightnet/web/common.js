// Shared by index.html and explore.html: the network as a graph, path finding, map drawing helpers.
(function () {
  const N = window.NETWORK;
  const A = N.airports, P = N.pairs;
  const n = A.code.length, m = P.a.length;

  const indexOf = new Map(A.code.map((c, i) => [c, i]));

  // adjacency lists in CSR form: neighbors of i are nbr[start[i]..start[i+1]), edge ids in eid[]
  const degree = new Int32Array(n);
  for (let e = 0; e < m; e++) { degree[P.a[e]]++; degree[P.b[e]]++; }
  const start = new Int32Array(n + 1);
  for (let i = 0; i < n; i++) start[i + 1] = start[i] + degree[i];
  const fill = start.slice(0, n), nbr = new Int32Array(2 * m), eid = new Int32Array(2 * m);
  for (let e = 0; e < m; e++) {
    const a = P.a[e], b = P.b[e];
    nbr[fill[a]] = b; eid[fill[a]++] = e;
    nbr[fill[b]] = a; eid[fill[b]++] = e;
  }

  // fewest flights from src to every airport (-1 = unreachable)
  function bfs(src) {
    const dist = new Int16Array(n).fill(-1);
    const queue = new Int32Array(n);
    let head = 0, tail = 0;
    dist[src] = 0; queue[tail++] = src;
    while (head < tail) {
      const u = queue[head++];
      for (let k = start[u]; k < start[u + 1]; k++) {
        const v = nbr[k];
        if (dist[v] < 0) { dist[v] = dist[u] + 1; queue[tail++] = v; }
      }
    }
    return dist;
  }

  // the fewest-flights itinerary; among equally short ones, the fewest kilometres
  function bestPath(src, dst) {
    const dist = bfs(src);
    if (dist[dst] < 0) return null;
    const km = new Float64Array(n).fill(Infinity), prev = new Int32Array(n).fill(-1), via = new Int32Array(n).fill(-1);
    km[src] = 0;
    const order = Array.from({ length: n }, (_, i) => i).filter(i => dist[i] >= 0 && dist[i] <= dist[dst])
      .sort((x, y) => dist[x] - dist[y]);
    for (const u of order) {
      if (km[u] === Infinity) continue;
      for (let k = start[u]; k < start[u + 1]; k++) {
        const v = nbr[k];
        if (dist[v] !== dist[u] + 1) continue;
        const d = km[u] + P.km[eid[k]];
        if (d < km[v]) { km[v] = d; prev[v] = u; via[v] = eid[k]; }
      }
    }
    const nodes = [dst], edges = [];
    for (let v = dst; v !== src; v = prev[v]) { edges.push(via[v]); nodes.push(prev[v]); }
    return { nodes: nodes.reverse(), edges: edges.reverse(), km: km[dst], dist };
  }

  function edgesOf(i) {
    const out = [];
    for (let k = start[i]; k < start[i + 1]; k++) out.push(eid[k]);
    return out;
  }

  const radius = deg => Math.sqrt(2 + 0.6 * deg) * 0.62;  // same area rule as the Matplotlib maps
  const fmt = new Intl.NumberFormat('en-US');
  const place = i => [A.city[i], A.country[i]].filter(Boolean).join(', ');
  const label = i => `${A.city[i] || A.name[i]} (${A.code[i]})`;
  const airlineNames = e => P.al[e].map(j => N.airlines.name[j]);

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  // a <datalist> of every airport, busiest first, for search inputs
  function airportOptions(datalist) {
    const order = Array.from({ length: n }, (_, i) => i).sort((x, y) => A.deg[y] - A.deg[x]);
    datalist.innerHTML = order.map(i => `<option value="${A.code[i]} · ${A.city[i]}, ${A.country[i]}">`).join('');
  }
  function parseAirport(text) {
    if (!text) return -1;
    const code = text.split(' · ')[0].trim().toUpperCase();
    if (indexOf.has(code)) return indexOf.get(code);
    const t = text.trim().toLowerCase();
    let best = -1;
    for (let i = 0; i < n; i++) {
      if ((A.city[i] || '').toLowerCase() === t && (best < 0 || A.deg[i] > A.deg[best])) best = i;
    }
    return best;
  }

  // colors for "flights needed" (1, 2, 3, 4, 5+): one sequential hue, darker = closer
  const HOP_COLORS = ['#0d366b', '#256abf', '#3987e5', '#86b6ef', '#cde2fb'];
  const hopColor = d => d < 0 ? '#d6d4ce' : d === 0 ? '#eb6834' : HOP_COLORS[Math.min(d, 5) - 1];

  // the map area every flat map is fitted to: the whole world from 58°S (below the southernmost airport) to 84°N
  const frame = { type: 'MultiPoint', coordinates: [] };
  for (let lat = -58; lat <= 84; lat += 2) frame.coordinates.push([-180, lat], [180, lat]);
  for (let lon = -180; lon <= 180; lon += 5) frame.coordinates.push([lon, 84], [lon, -58]);

  window.Flight = { frame, N, A, P, n, m, indexOf, bfs, bestPath, edgesOf, radius, fmt, place, label, airlineNames,
                    css, airportOptions, parseAirport, HOP_COLORS, hopColor };
})();
