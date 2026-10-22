# MotoLimiet ride findings 2026-10-22

Research only. No production map publication and no street/coordinate hardcodes.

## Ride evidence

Two MotoLimiet 0.3.11 ride exports from 2026-10-22 were reviewed.

- Spoken uncertain-limit events: 34 total.
- Ride 1 UNKNOWN events: missing 387, ambiguous 41, variable 11, conflict 16.
- Ride 2 UNKNOWN events: missing 2311, ambiguous 71, variable 26, conflict 22.

The recurring complaint is primarily the `ambiguous` class, not a real speed-change event.

## Ooiebrug / Gentsesteenweg

Exact ride anchor:
- 2026-10-22 10:56:24Z
- 51.0315854, 4.0796830
- bearing 253.9 degrees
- app selected 70 km/h, quality=agreement

Current production-map trace:
- nearest segment id 4245563, OSM way 1468428806, Gentsesteenweg, 70/70, about 1.9 m
- adjacent continuation 4245564, same OSM way, 70/70
- a 50/50 Gentsesteenweg segment exists about 22.5 m away, but is not the driven geometry

Independent evidence:
AWV temporary Ooiebrug measure specifies 50 km/h Dendermonde -> Aalst and 70 km/h Aalst -> Dendermonde while the measure remains active.

Conclusion:
This is a map/evidence problem, not GPS noise. Direction-specific temporary evidence must be attached to the correct driven corridor; proximity to another 50 segment is not sufficient.

## Wichelen / Bohemen

Exact ride anchor:
- 2026-10-22 11:05:50Z
- 51.0021383, 3.9965807
- bearing 266.7 degrees
- app selected 70 km/h, quality=osm

Current production-map trace:
- nearest Bohemen segment is 70/70 in the shipped map
- later in the same driven corridor, at 51.0018765, 3.9924685, the map changes to 50/50

Independent evidence:
Police speed-control statistics list Bohemen in Wichelen at 50 km/h.

Conclusion:
The current map places or retains a 70 corridor too far into Bohemen. The transition boundary must be derived from source topology/evidence, not from a coordinate exception.

## Wichelse steenweg repeated ambiguity

Examples from the ride:
- 50.9814230, 3.9735839: runtime candidates 70,70,0 on the same named corridor -> spoken unknown
- 50.9805811, 3.9739206: candidates include 50,50,70 -> unknown; this is a real transition ambiguity and must not be suppressed without proof
- 50.9794162, 3.9746132: candidates predominantly 50 plus one 0 -> spoken unknown
- 50.9778581, 3.9749801: repeated 50 plus 0 ambiguity -> spoken unknown

Production-map inspection near the 50 corridor also shows valid 50/50 Wichelse steenweg segments together with nearby unnamed 0/0 non-comparable OSM segments.

Conclusion:
There are two different cases and they must stay separate:
1. numeric-vs-numeric (50 vs 70): retain uncertainty until topology proves the boundary;
2. stable known corridor vs nearby missing/non-comparable segment: candidate for continuity-aware filtering, provided tests prove no unsafe suppression.

## Safety rules for the next prototype

- Never choose the lowest candidate merely to avoid unknown.
- Never infer a speed solely from nearest AWV/sign geometry.
- Numeric-vs-numeric conflicts remain unknown unless independent direction/topology evidence resolves them.
- A missing/non-comparable side segment may only be prevented from causing ambiguity when the driven road corridor is independently stable and the missing segment cannot plausibly be the driven carriageway.
- No street-name or coordinate-specific production exceptions.
