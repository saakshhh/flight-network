# Data

Everything in this folder is built by [`scripts/build_dataset.py`](../scripts/build_dataset.py) from three open
sources:

| Source | What it gives | License |
|---|---|---|
| [OpenFlights](https://openflights.org/data) `routes.dat`, `airports.dat`, `airlines.dat` | 67,663 airline routes (June 2014 snapshot), airport names and coordinates, airline names | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| [OurAirports](https://ourairports.com/data/) `airports.csv`, `countries.csv` | continents, airport size, and the airports that OpenFlights' routes use but its airport list lacks | Public domain |
| [Natural Earth](https://www.naturalearthdata.com/) 1:110m countries | country outlines (`world_110m.geojson`, coordinates rounded to 0.01°) | Public domain |

The tables here are a derived database of OpenFlights, so they are shared under the same ODbL license.

## Files

**`routes.csv`**: one row per airline per directed nonstop route (67,618 rows)

| column | meaning |
|---|---|
| `airline`, `airline_name`, `airline_country` | two-letter IATA code (some three-letter ICAO codes), name, home country |
| `src`, `dst` | IATA codes of the origin and destination airports |
| `codeshare` | `True` when the airline only sells seats on a flight another airline operates |
| `equipment` | aircraft types (IATA codes, space-separated) |
| `distance_km` | great-circle distance |

**`pairs.csv`**: one row per airport pair, both directions merged: the network's edges (19,239 rows)

| column | meaning |
|---|---|
| `a`, `b` | the two airports (alphabetical order) |
| `airlines`, `n_airlines` | every airline that sells the route in either direction, and how many |
| `n_operating` | airlines that fly it themselves (not codeshare) |
| `listings` | raw route rows merged into this pair (airline × direction). The course version of this data called this number "number of flights", but it isn't a flight count. |
| `distance_km`, `both_directions` | great-circle distance; whether the route appears in both directions |

**`airports.csv`**: every airport with at least one route (3,419 rows)

| column | meaning |
|---|---|
| `iata`, `name`, `city`, `country`, `icao`, `lat`, `lon`, `tz` | from OpenFlights (OurAirports for the recovered ones) |
| `iso_country`, `continent`, `size` | from OurAirports (`size`: large / medium / small / seaplane_base / heliport) |
| `degree` | nonstop destinations (airports it shares a pair with) |
| `betweenness` | share of all shortest paths in the network that pass through the airport (exact, NetworkX) |
| `in_main_network` | in the largest connected component (3,391 airports; the rest are island networks) |
| `departing_routes`, `airlines`, `countries_served` | airline routes departing, distinct airlines, distinct countries among its destinations |

**`airlines.csv`**: every airline code in the routes, with name, country, number of routes and airports.

**`build_report.json`**: everything the build removed, recovered or fixed, with counts.

## Cleaning and fixes

- Dropped 11 routes with stops (not nonstop) and 1 route from an airport to itself.
- **Recovered 158 airports** that routes use but `airports.dat` lacks, from OurAirports. Only 33 routes are lost,
  to 5 airport codes neither source knows.
- **Airline names.** `routes.dat` links each route to an airline id, but those ids were assigned by looking the code
  up in `airlines.dat`, which reuses codes: Vueling's routes are labelled *Formosa Airlines*, Gol's *City
  Connexion Airlines*. The build names each code by:
  1. the only airline with that code, if there is one;
  2. otherwise the candidate whose home country makes up the most of its routes' endpoints (at least 10%), after
     reconciling country spellings (*Republic of Korea* ↔ *South Korea* …);
  3. a short hand-checked list for the largest codes neither rule resolves (`KNOWN_AIRLINES` in the script);
  4. otherwise `XX (unidentified)` instead of a wrong guess (67 codes, 2.5% of routes, including TO, whose
     only `airlines.dat` entry clearly doesn't match its routes).
- **Time mismatch.** The routes are from 2014 but `airports.dat` has been updated since, so a few airport records
  changed meaning. Istanbul's code IST moved to the new Istanbul Airport in 2019; the build restores Atatürk Airport.
- Continents for closed airports (Berlin Tegel …) come from their ICAO code in OurAirports, or else from the
  continent most airports in the same country are on.

## Rebuild

```bash
git clone --depth 1 https://github.com/jpatokal/openflights.git /tmp/openflights
git clone --depth 1 https://github.com/davidmegginson/ourairports-data.git /tmp/ourairports
python scripts/build_dataset.py --openflights /tmp/openflights/data --ourairports /tmp/ourairports
```

OurAirports is updated nightly, so a rebuild can differ slightly from the committed files in the recovered airports.
