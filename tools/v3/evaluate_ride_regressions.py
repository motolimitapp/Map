#!/usr/bin/env python3
"""Read-only road/speed candidate audit of reproducible GPS anchors.

Research tool, NOT Android's matcher, a legal-speed oracle, or a map publisher.
Both driving direction and quality state are checked; ambiguous neighbours
remain inconclusive. Only independently verified evidence can fail a gate.
"""
import argparse
import datetime
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

from pyproj import Transformer

PROJECT = Transformer.from_crs("EPSG:4326", "EPSG:31370", always_xy=True)
CERTAIN_QUALITY = {1, 2, 3, 4}


def angular_error(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def distance_to_segment(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 0.01:
        return float("inf")
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def candidates(db, anchor, radius_m=25.0, heading_tolerance_deg=35.0):
    x, y = PROJECT.transform(anchor["lon"], anchor["lat"])
    lat_pad = radius_m / 110000.0
    lon_pad = radius_m / (110000.0 * math.cos(math.radians(anchor["lat"])))
    query = """
      SELECT s.id,s.name,s.lat1,s.lon1,s.lat2,s.lon2,s.forward_kmh,
             s.backward_kmh,s.oneway,q.forward_state,q.backward_state
      FROM segments s JOIN segment_quality q ON s.id=q.segment_id
      WHERE max(s.lat1,s.lat2)>=? AND min(s.lat1,s.lat2)<=?
        AND max(s.lon1,s.lon2)>=? AND min(s.lon1,s.lon2)<=?
    """
    rows = db.execute(query, (
        anchor["lat"]-lat_pad, anchor["lat"]+lat_pad,
        anchor["lon"]-lon_pad, anchor["lon"]+lon_pad,
    ))
    ranked = []
    for sid, road, lat1, lon1, lat2, lon2, fw, bw, oneway, fs, bs in rows:
        if anchor.get("road") and (road or "").casefold() != anchor["road"].casefold():
            continue
        ax, ay = PROJECT.transform(lon1, lat1)
        bx, by = PROJECT.transform(lon2, lat2)
        distance = distance_to_segment(x, y, ax, ay, bx, by)
        if distance > radius_m:
            continue
        bearing = math.degrees(math.atan2(bx-ax, by-ay)) % 360.0
        options = [("forward", bearing, fw, fs)]
        if not oneway:
            options.append(("backward", (bearing+180.0)%360.0, bw, bs))
        for direction, segment_bearing, kmh, quality in options:
            heading_error = angular_error(anchor["bearing_deg"], segment_bearing)
            if heading_error > heading_tolerance_deg:
                continue
            ranked.append({
                "segment_id":sid, "road":road, "direction":direction,
                "distance_m":round(distance,2), "heading_error_deg":round(heading_error,2),
                "limit_kmh":kmh, "quality_state":quality,
                "score":round(distance + 0.2 * heading_error,2),
            })
    return sorted(ranked, key=lambda row:(row["score"],row["segment_id"]))


def evaluate(db, anchor):
    result = {
        "id":anchor["id"], "date":anchor["date"], "lat":anchor["lat"],
        "lon":anchor["lon"], "bearing_deg":anchor["bearing_deg"],
        "evidence_level":anchor["evidence_level"],
        "expected_kmh":anchor.get("expected_kmh"),
        "app_reported_kmh":anchor.get("app_reported_kmh"),
    }
    if anchor.get("reference_url"):
        result["reference_url"] = anchor["reference_url"]
    if anchor.get("valid_from") and anchor["date"] < anchor["valid_from"]:
        result["status"]="evidence_not_yet_valid"
        return result
    if anchor.get("valid_until") and anchor["date"] > anchor["valid_until"]:
        result["status"]="evidence_expired"
        return result
    ranked = candidates(db,anchor)
    result["candidates"] = ranked[:5]
    if not ranked:
        result["status"]="not_covered_or_no_directional_match"
        return result
    best = ranked[0]
    close = [c for c in ranked if c["score"] <= best["score"] + 3.0]
    values = {(c["limit_kmh"],c["quality_state"]) for c in close}
    if len(values) > 1:
        result["status"]="ambiguous_candidates_unresolved"
        return result
    result["candidate_kmh"]=best["limit_kmh"]
    result["candidate_quality_state"]=best["quality_state"]
    if not best["limit_kmh"] or best["quality_state"] not in CERTAIN_QUALITY:
        result["status"]="uncertain_safe"
    elif anchor["evidence_level"] in ("official_directional","official_location"):
        result["status"] = ("matches_verified_reference" if best["limit_kmh"] == anchor["expected_kmh"]
                            else "verified_regression")
    elif anchor["evidence_level"] == "rider_observation" and anchor.get("expected_kmh") is not None:
        result["status"] = ("matches_rider_observation" if best["limit_kmh"] == anchor["expected_kmh"]
                            else "rider_discrepancy_unverified")
    else:
        result["status"]="mapping_only_no_ground_truth"
    return result


def audit(db, fixture):
    records=[evaluate(db,anchor) for anchor in fixture["anchors"]]
    counts=Counter(r["status"] for r in records)
    return {"status":"research_only_not_android_runtime", "statistics":dict(counts),
            "verified_regressions":counts["verified_regression"], "anchors":records}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("fixture")
    parser.add_argument("report")
    parser.add_argument("--strict",action="store_true",help="Fail only on an independently verified mismatch")
    parser.add_argument("--ids",default="",help="Comma-separated anchor ids to evaluate")
    args=parser.parse_args()
    fixture=json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    if args.ids:
        wanted={value.strip() for value in args.ids.split(",") if value.strip()}
        fixture=dict(fixture)
        fixture["anchors"]=[row for row in fixture["anchors"] if row["id"] in wanted]
        missing=wanted-{row["id"] for row in fixture["anchors"]}
        if missing:
            raise SystemExit("Unknown anchor ids: "+",".join(sorted(missing)))
    with sqlite3.connect(Path(args.database).resolve().as_uri()+"?mode=ro",uri=True) as db:
        report=audit(db,fixture)
    Path(args.report).write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report["statistics"],indent=2))
    if args.strict and report["verified_regressions"]:
        raise SystemExit(2)


if __name__=="__main__":
    main()
