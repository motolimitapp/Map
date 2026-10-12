# Findings — 12 October 2026 ride evidence

Research checkpoint only. No production map, resolver or APK behavior is changed by this note.

## Steven

Ride anchor: approximately 50.9707056, 4.1076901 (20:10:05 Belgian local time).

Observed by rider: actual 50 km/h built-up context. MotoLimiet 0.3.10 announced 90 km/h from OSM.

Official-source probe findings:

- AWV `Afgeleide_snelheidsregimes`: nearest directed geometry is 70 km/h, about 7–22 m from the two ride anchors, Wegsegment_ID 728485. No determining sign is attached in that feature.
- AWV Zone 50: no feature in the local test window.
- AWV built-up-area layer: nearest 50-context geometry is roughly 65–81 m from the ride anchors; this is context, not sufficient on its own to assert the legal speed at the GPS point.
- Direct `Verkeersborden.Vlaanderen_Borden` snapshot: 30 signs in the local window, but no C43-50 or F1/F3 sign that directly explains the rider-observed 50 at the anchor. Nearest signs are route/direction signs (e.g. FtsRt, F34b1) and warning/direction signage.
- TN-ITS: the newest 30 datasets were downloaded and inspected. Their creation times span 2026-10-06 through 2026-10-12. No road feature with a GML point within 2 km of the Steven anchor was found in those updates.

Interpretation:
- OSM 90 is not supported by the current AWV speed snapshot, which says 70 near the anchor.
- The official sources tested so far do not yet explain the rider-observed 50.
- Therefore Steven must remain an unresolved source conflict / field-observation case. Do not automatically replace OSM 90 with AWV 70 or built-up 50 solely from these results.
- A newer Signalisatie Vlaanderen/VKS export may exist organizationally, but no separately documented public machine-readable feed newer than the current AWV WFS/TN-ITS chain has yet been verified for this case.

## Architecture implication

Keep OSM and AWV as separate evidence families. Inside AWV, canonicalize speed, zones, context and signs by Wegenregister/direction before matching to OSM. Direct sign proximity and nearest-line distance are diagnostic evidence only, not runtime authority.

Steven remains the strongest negative test: any future resolver rule must avoid confidently returning 90, 70 or 50 unless additional directional/topological/sign evidence resolves the discrepancy.
