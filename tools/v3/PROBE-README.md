# AWV / TN-ITS evidence probe (research only)

Run: `python tools/v3/probe_official_evidence.py --config tools/v3/probe-cases-20261012.json --out probe-output`

This does NOT change the map, resolver, APK or release. It writes raw GeoJSON and summary.json; exit 2 means at least one source query failed.

**Critical:** The four bounding boxes are approximate windows centered on GPS fixes from the 12 October 2026 rides, NOT verified sign boundaries. They are not complete route geometries. The WFS type name in the example is a hypothesis requiring GetCapabilities verification; adjust to actual advertised QName. The script intentionally does not guess zone layer names. Discover them from the server's WFS GetCapabilities before adding them to the config. Verify EPSG:4326 axis order with a known feature and/or query in EPSG:31370 if necessary. Inspect output for exceptions, counts at cap, geometry and direction before using evidence.

TN-ITS is optional and requires an actual documented machine-readable URL with compatible JSON; do not assume the transportdata.be catalog page is itself the data feed. TN-ITS is change-only; absence is not negative evidence.

**Still to implement before any go/no-go decision:** complete GPS log import, point-to-directed-edge spatial join, provenance and temporal validity, feature paging, canonical Wegenregister identity, zone entry/exit boundary checks, TN-ITS OpenLR/GML decoding, and independent verification of source freshness. No production decisions may be based on the current output alone.

Case anchors (UTC+2, 12 Oct 2026):
- Dendermonde: first selected 30 near 51.0318247,4.0917542 at 15:45:30; physical sign pin not resolved.
- Wieze: ambiguous 30/0/50 on Nieuwstraat around 20:14:39–20:14:45 near 50.9807,4.083.
- Steven: incorrect OSM 90 near 50.9707056,4.1076901 at 20:10:05.
- Gijzegem: 30 selected near 50.9845405,4.0505517 at 20:19:11.

Keep raw evidence separate from inference. This probe is deliberately limited; the results must not be presented as verified speed limits.
