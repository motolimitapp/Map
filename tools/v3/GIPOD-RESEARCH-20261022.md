# GIPOD temporary restriction research - 2026-10-22

Research only. No production integration.

## Why investigated
The static OSM/AWV speed evidence around Ooiebrug reports 70 km/h while current official AWV works information states a temporary direction-specific 50 km/h restriction Dendermonde -> Aalst. A generic temporary-restrictions source is required; a street/coordinate exception is not acceptable.

## Public GIPOD findings
- Digitaal Vlaanderen publishes a public OGC API Features service for GIPOD planned/active mobility hindrance.
- Public HINDER/HINDERGEVOLG records can contain the consequence "Snelheidsbeperking".
- The public fields expose the existence and geometry/time window of a speed restriction consequence, but not a numeric km/h value.
- Detailed signaling-permit API endpoints exist separately and require authenticated GIPOD read permissions.
- Public indexed GIPOD results around Gentsesteenweg/Ooiebrug did not establish the long-running 2025 Ooiebrug 50 km/h direction-specific measure with a machine-readable numeric value.

## Safety conclusion
GIPOD is a promising generic source for detecting that temporary traffic rules may override static map data, but public data is not currently sufficient to write a numeric 50 km/h limit for Ooiebrug.

Possible future safe use:
1. retrieve public active hindrance geometries;
2. prove the hindrance corridor/direction against Wegenregister/OSM topology;
3. if only "Snelheidsbeperking" is known without a numeric value, degrade a conflicting static numeric value to unknown rather than invent a speed;
4. only write a numeric temporary speed when an authoritative machine-readable source supplies that exact value and direction.

No production change is authorized by this research.
