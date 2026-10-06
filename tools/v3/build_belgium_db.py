#!/usr/bin/env python3
"""Build a compact local speed-limit database from a Belgium OSM PBF extract.

Dependency on the build computer: pip install osmium
Usage: python tools/build_belgium_db.py belgium-latest.osm.pbf belgium-limits.db
"""
import argparse
import datetime
import math
import os
import re
import sqlite3

try:
    import osmium
except ImportError as exc:
    raise SystemExit("Install pyosmium first: python -m pip install osmium") from exc

ROAD_TYPES = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road",
}


def awv_eligible(tags):
    """Missing is not the same as unparseable, conditional or implicitly regulated."""
    if tags.get("highway") not in {"primary", "secondary", "tertiary", "unclassified", "residential"}:
        return False
    if any("maxspeed" in tag.k or "conditional" in tag.k or "variable" in tag.k for tag in tags):
        return False
    if any(tags.get(k, "no") not in ("no", "0", "") for k in ("bridge", "tunnel", "covered", "cyclestreet", "bicycle_road")):
        return False
    return tags.get("layer", "0") == "0" and not tags.get("junction") and not tags.get("zone:traffic")


def speed(text):
    if not text:
        return 0
    match = re.fullmatch(r"\s*(\d{1,3})(?:\s*(?:km/h|kmh|kph))?\s*", text, re.I)
    if match:
        value = int(match.group(1))
        return value if 5 <= value <= 130 else 0
    mph = re.fullmatch(r"\s*(\d{1,3})\s*mph\s*", text, re.I)
    return round(int(mph.group(1)) * 1.609344) if mph else 0


class Builder(osmium.SimpleHandler):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.count = 0
        self.last_id = 0

    def way(self, way):
        tags = way.tags
        if tags.get("highway") not in ROAD_TYPES or tags.get("access") in ("no", "private"):
            return
        if tags.get("motor_vehicle") in ("no", "private") or tags.get("motorcycle") in ("no", "private"):
            return
        dynamic = any("conditional" in tag.k or "variable" in tag.k for tag in tags)
        general = speed(tags.get("maxspeed:motorcycle")) or speed(tags.get("maxspeed"))
        forward = speed(tags.get("maxspeed:motorcycle:forward")) or speed(tags.get("maxspeed:forward")) or general
        backward = speed(tags.get("maxspeed:motorcycle:backward")) or speed(tags.get("maxspeed:backward")) or general
        direction = tags.get("oneway", "")
        one_way = direction in ("yes", "true", "1", "-1") or tags.get("junction") == "roundabout"
        reverse = direction == "-1"
        fallback_eligible = int(awv_eligible(tags))
        comparable = tags.get("highway") in {"primary","secondary","tertiary","unclassified","residential"} and tags.get("layer","0")=="0" and not tags.get("junction") and all(tags.get(k,"no") in ("no","0","") for k in ("bridge","tunnel","covered"))
        if dynamic:forward=backward=0
        fs=11 if dynamic else (1 if forward else 0)
        bs=11 if dynamic else (1 if backward else 0)
        nodes = list(way.nodes)
        if reverse:
            nodes.reverse()
            forward, backward = backward, forward
            fs,bs=bs,fs
        for a, b in zip(nodes, nodes[1:]):
            if not (a.location.valid() and b.location.valid()):
                continue
            a_lat, a_lon = a.location.lat, a.location.lon
            b_lat, b_lon = b.location.lat, b.location.lon
            if a_lat == b_lat and a_lon == b_lon:
                continue
            metres = math.hypot((a_lat - b_lat) * 111195, (a_lon - b_lon) * 111195 * math.cos(math.radians(a_lat)))
            if metres > 500:
                continue
            self.last_id += 1
            self.db.execute("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?)", (
                self.last_id, a_lat, a_lon, b_lat, b_lon, forward, backward, int(one_way), tags.get("name", "")[:100]))
            tile_id = math.floor((a_lat + b_lat) * 100) * 100000 + math.floor((a_lon + b_lon) * 100) + 36000
            self.db.execute("INSERT INTO tiles VALUES (?,?)", (self.last_id, tile_id))
            self.db.execute("INSERT INTO osm_provenance VALUES (?,?,?,?)", (self.last_id, way.id, fallback_eligible,int(comparable)))
            self.db.execute("INSERT INTO segment_quality VALUES (?,?,?,?,?,?,?)",(self.last_id,fs,bs,forward,backward,"",""))
            self.count += 1
            if self.count % 100_000 == 0:
                self.db.commit()
                print(f"{self.count:,} segments", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Belgium .osm.pbf extract")
    parser.add_argument("output", help="Output .db; must not exist")
    args = parser.parse_args()
    if os.path.exists(args.output):
        parser.error("Output already exists; choose a new file or remove the old version")
    db = sqlite3.connect(args.output)
    try:
        db.executescript("""
            PRAGMA journal_mode=DELETE;
            PRAGMA page_size=4096;
            CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE segments (id INTEGER PRIMARY KEY,lat1 REAL,lon1 REAL,lat2 REAL,lon2 REAL,forward_kmh INTEGER,backward_kmh INTEGER,oneway INTEGER,name TEXT);
            CREATE TABLE tiles (id INTEGER PRIMARY KEY,tile_id INTEGER NOT NULL);
            CREATE TABLE osm_provenance (segment_id INTEGER PRIMARY KEY,osm_way_id INTEGER NOT NULL,awv_eligible INTEGER NOT NULL,comparable INTEGER NOT NULL);
            CREATE TABLE segment_quality(segment_id INTEGER PRIMARY KEY,forward_state INTEGER NOT NULL,backward_state INTEGER NOT NULL,osm_forward INTEGER NOT NULL,osm_backward INTEGER NOT NULL,forward_evidence TEXT NOT NULL,backward_evidence TEXT NOT NULL);
        """)
        builder = Builder(db)
        builder.apply_file(args.input, locations=True, idx="flex_mem")
        db.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("format", "motolimiet-3"),
            ("quality_schema","1"),("conflict_check","osm-only"),
            ("awv_eligibility_version", "2"),
            ("built_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()),
            ("source", "© OpenStreetMap contributors; ODbL"),
        ])
        db.execute("CREATE INDEX tile_lookup ON tiles(tile_id)")
        db.commit()
        db.execute("VACUUM")
        print(f"Wrote {builder.count:,} segments to {args.output}")
    except BaseException:
        db.close()
        os.unlink(args.output)
        raise
    db.close()


if __name__ == "__main__":
    main()
