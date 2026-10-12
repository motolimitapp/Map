# MotoLimiet official-evidence findings — 12 October 2026

Research checkpoint only. No production resolver, map or APK change is implied by this document.

## Sources checked
- AWV WFS: speed regimes, Zone 30, Zone 50, built-up area, woonerf, fietsstraten, motorway zones.
- Direct legacy traffic-sign layer: `awv:Verkeersborden.Vlaanderen_Borden`.
- Flemish TN-ITS dataset catalogue and sampled change datasets.
- MotoLimiet diagnostic anchors from the 12 October 2026 rides.

## Dendermonde
Official AWV data contains both speed=30 and Zone30 evidence near the ride anchors (about 18–21 m). The exact physical sign coordinate is still unresolved, so no claim is made about the exact legal zone-entry boundary.

Interpretation: AWV contains useful information that the current pipeline/runtime does not yet exploit optimally.

## Wieze
Near the zone transition, official AWV data contains nearby 50/F1a and Zone30 evidence, followed by 30/F4a farther along the driven path. This mirrors the runtime 30/0/50 ambiguity.

Interpretation: nearest-line matching is unsafe. AWV layers should first be combined on a canonical directed Wegenregister edge/topology before one match to OSM.

## Gijzegem
At the return anchor, AWV has specific 30/F4a + Zone30 evidence about 5.5 m from the fix while built-up 50 context is also present. The app selected 30 correctly; the missing spoken notification remains a separate app/TTS state issue.

Interpretation: specific local/zone evidence must outrank generic context within the AWV family. Layer agreement is internal consistency, not independent voting.

## Steven
At the erroneous OSM-90 announcement anchor:
- current AWV speed evidence supports 70 nearby, not 50;
- no Zone50 feature was found in the investigated window;
- built-up 50 context is substantially farther away and is not valid numeric evidence for the driven edge;
- the nearest direct legacy traffic signs do not include a C43-50 or F1/F3 sign relevant enough to establish 50;
- historical sampled TN-ITS data from 27 March 2024 contained a 70 speedLimit feature roughly 41 m from the anchor; nearest sampled 50 was over 500 m away;
- the newest sampled TN-ITS datasets have creation times 10 Oct 2026, 11 Oct 2026 and 12 Oct 2026. No speedLimit feature within 3 km of the Steven anchor was found in those three newest change datasets.

Interpretation: the official AWV/TN-ITS evidence checked so far does **not** reproduce the user's physical observation of 50 at Steven. Do not force AWV=truth or infer 50 from built-up context.

## Architecture decision retained
1. OSM and MOW/AWV remain separate evidence families.
2. AWV layers are first canonicalised on directed Wegenregister topology.
3. Specific regime evidence (Zone30/Zone50/etc.) is distinct from generic context.
4. One canonical AWV edge is then matched to OSM, not every AWV layer independently.
5. Explicit credible source conflicts remain uncertain until a defensible rule is empirically validated.
6. TN-ITS is a freshness/change source; missing change data is not negative evidence.
7. Direct traffic signs are provenance/audit evidence and cannot be treated as complete coverage.
8. Built-up area never directly generates a numeric speed.
9. Steven requires independent real-world validation (exact sign position/direction and, if useful, an independent visual/map audit) before changing production resolver rules.

## Next research action
Capture or resolve the exact physical 50 sign/zone-entry location and travel direction for Steven, then compare that point against Signalisatie Vlaanderen/direct official data and an independent audit source. Do not implement a Steven-specific exception.
