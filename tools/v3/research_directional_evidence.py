"""Directional AWV evidence for research crosswalk annotations only.

Never returns a legally certified speed and never writes production limits.
An AWV geometry's coordinate order alone DOES NOT establish travel direction.
A predecessor Wegsegment_ID must geometrically touch exactly one endpoint;
otherwise both directions remain unresolved.
"""
import math
from collections import defaultdict

from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform

PROJECT = Transformer.from_crs("EPSG:4326", "EPSG:31370", always_xy=True)
SNAP_METRES = 2.0
HEADING_TOLERANCE_DEG = 25.0
SUPPORTED_SPEEDS = {20, 30, 40, 50, 60, 70, 90, 120}


def angle_error(ax, ay, bx, by):
    la, lb = math.hypot(ax,ay), math.hypot(bx,by)
    if la < 0.1 or lb < 0.1:
        return 180.0
    cosine = max(-1.0,min(1.0,(ax*bx+ay*by)/(la*lb)))
    return math.degrees(math.acos(cosine))


def line_geometry(feature):
    geometry = feature.get("geometry")
    if not geometry:
        return None
    try:
        metric = transform(PROJECT.transform,shape(geometry))
        if isinstance(metric,LineString):
            return metric if metric.length > 2.0 else None
        # MultiLineString may contain disconnected parts: never infer direction
        # by joining unrelated polylines.
        if metric.geom_type == "MultiLineString" and len(metric.geoms) == 1:
            return metric.geoms[0] if metric.geoms[0].length > 2.0 else None
    except (ValueError,TypeError):
        pass
    return None


def _endpoints(line):
    return (line.coords[0],line.coords[-1])


def _dist(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def _incoming_end(line,previous_lines):
    """Return 0/1 for the entrance endpoint, or None without unique proof."""
    start,end = _endpoints(line)
    touches = []
    for previous in previous_lines:
        points = _endpoints(previous)
        touches.append((
            min(_dist(start,p) for p in points) <= SNAP_METRES,
            min(_dist(end,p) for p in points) <= SNAP_METRES,
        ))
    starts = any(a for a,b in touches)
    ends = any(b for a,b in touches)
    if starts == ends:
        return None
    return 0 if starts else 1


def evidence_kind(props):
    speed = props.get("Snelheid")
    sign = str(props.get("Bepalend_bord") or "")
    zone = str(props.get("Zone") or "")
    if type(speed) is not int or speed not in SUPPORTED_SPEEDS:
        return "unproven_speed",None
    if speed == 30 and sign == "F4a" and "SnelheidsZone" in zone:
        return "zone30_candidate",30
    if sign in ("C43","ZC43"):
        return "signed_speed_candidate",speed
    if sign in ("F1a","F1b"):
        return "builtup_context_only",None
    return "other_unproven_sign",None


def build_road_evidence(collection):
    """Group feature evidence by Wegsegment_ID and uniquely proven direction."""
    entries=[]
    lines_by_road=defaultdict(list)
    for feature in collection.get("features",[]):
        props=feature.get("properties") or {}
        rid=props.get("Wegsegment_ID")
        if rid is None:
            continue
        line=line_geometry(feature)
        if line is None:
            continue
        try:
            rid=int(rid)
        except (TypeError,ValueError):
            continue
        lines_by_road[rid].append(line)
        entries.append((rid,feature,props,line))

    by_road=defaultdict(list)
    for rid,feature,props,line in entries:
        previous=props.get("Vorige_wegsegment_ID")
        incoming=None
        try:
            previous_id=int(previous)
        except (TypeError,ValueError):
            previous_id=None
        if previous_id is not None and previous_id != rid:
            incoming=_incoming_end(line,lines_by_road.get(previous_id,[]))
        a,b=_endpoints(line)
        dx,dy=(b[0]-a[0],b[1]-a[1])
        if incoming == 1:
            dx,dy=-dx,-dy
        kind,kmh=evidence_kind(props)
        by_road[rid].append({
            "feature_id":str(feature.get("id") or ""),
            "direction_proven":incoming is not None,
            "travel_dx":dx if incoming is not None else None,
            "travel_dy":dy if incoming is not None else None,
            "kind":kind,
            "kmh":kmh,
            "sign":str(props.get("Bepalend_bord") or ""),
            "previous_road_id":previous_id,
        })
    return by_road


def directional_summary(evidence,osm_dx,osm_dy):
    """Return research annotations for OSM forward and backward direction.

    A missing predecessor or unrelated/sidelined feature cannot fill a speed.
    Conflicting candidate numbers remain unresolved.
    """
    result={}
    for direction,multiplier in (("forward",1),("backward",-1)):
        relevant=[]
        unknown=[]
        for item in evidence:
            if not item["direction_proven"]:
                unknown.append(item)
                continue
            err=angle_error(osm_dx*multiplier,osm_dy*multiplier,
                            item["travel_dx"],item["travel_dy"])
            if err<=HEADING_TOLERANCE_DEG:
                relevant.append(item)
        refs=sorted({i["feature_id"] for i in relevant})
        numeric={i["kmh"] for i in relevant if i["kmh"] is not None}
        if unknown:
            state,kmh="unresolved_direction_provenance",None
        elif len(numeric)>1:
            state,kmh="conflicting_official_numeric",None
        elif len(numeric)==1:
            state,kmh=("zone30_candidate" if any(i["kind"]=="zone30_candidate" for i in relevant)
                       else "signed_speed_candidate"),next(iter(numeric))
        elif relevant:
            state,kmh="context_only_no_numeric",None
        else:
            state,kmh="no_directed_evidence",None
        result[direction]={
            "state":state,"candidate_kmh":kmh,
            "feature_ids":refs,
            "matched_features":len(relevant),
            "unresolved_features":len(unknown),
            "guardrail":"research_only_not_production",
        }
    return result
