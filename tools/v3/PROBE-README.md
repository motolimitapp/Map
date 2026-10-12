# AWV / TN-ITS evidence probe — 12 October 2026

Research-only. This branch/PR does **not** change MotoLimiet's production map, resolver, app or release.

## What the probe now does
- Queries the confirmed AWV WFS endpoint and advertised layers for speed regimes, Zone 30, Zone 50, built-up area, woonerf, fietsstraten and motorway zones.
- Converts WGS84 ride windows to **EPSG:31370 (Belgian Lambert 72)** before WFS BBOX filtering; requests returned GeoJSON in EPSG:4326.
- Paginates feature retrieval with hard caps.
- Stores raw GeoJSON per case/layer.
- Reports property keys and nearest raw geometries to named GPS anchors.
- Fetches the Flemish TN-ITS dataset-list endpoint as raw bytes; no semantic TN-ITS decoding yet.

## What it deliberately does NOT do
No legal speed inference, majority voting, OSM/AWV conflict resolution, directed-edge matching, zone entry/exit reconstruction, or production database writes.

Nearest feature distance is **diagnostic only**. Before any production decision we still need to validate road direction/topology, Wegenregister identity, feature temporal validity/freshness, zone continuity, and TN-ITS OpenLR/GML semantics.

## Run
`python tools/v3/probe_official_evidence.py --config tools/v3/probe-cases-20261012.json --out probe-output`

Dependencies are already in `requirements-v3.txt` (pyproj + shapely).

## Case anchors
All observations are from 12 Oct 2026; clock labels are Belgian local time (UTC+2).

- Dendermonde: nearby/selected/confirmed 30 around 15:45:28–15:45:32. The user's physical sign Google Maps pin still has not been resolved to coordinates, so these anchors are **not** the physical sign boundary.
- Wieze: ambiguity on Nieuwstraat around 20:14:39–20:14:45; announcement around 20:14:47.
- Gijzegem: first-pass and return-pass 30 anchors.

## Interpretation guardrails
1. All AWV layers are one evidence family; internal agreement is consistency, not independent voting.
2. Missing feature != proof of absence.
3. TN-ITS is change-oriented; missing delta != current state is correct.
4. Do not promote any resolver rule until raw evidence for the active cases has been inspected.
