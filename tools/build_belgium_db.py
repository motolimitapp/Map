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
        # Conditional and variable limits need live context (hours, weather, signs).
        # No unconditional number is shown on roads carrying such tags.
        if any("conditional" in tag.k or "variable" in tag.k for tag in tags):
            return
        general = speed(tags.get("maxspeed:motorcycle")) or speed(tags.get("maxspeed"))
        forward = speed(tags.get("maxspeed:motorcycle:forward")) or speed(tags.get("maxspeed:forward")) or general
        backward = speed(tags.get("maxspeed:motorcycle:backward")) or speed(tags.get("maxspeed:backward")) or general
        # Keep roads without a numeric limit as candidates too: they must not be
        # mistaken for an adjacent road with a known speed limit.
        direction = tags.get("oneway", "")
        one_way = direction in ("yes", "true", "1", "-1") or tags.get("junction") == "roundabout"
        reverse = direction == "-1"
        nodes = list(way.nodes)
        if reverse:
            nodes.reverse()
            forward, backward = backward, forward
        for a, b in zip(nodes, nodes[1:]):
            if not (a.location.valid() and b.location.valid()):
                continue
            a_lat, a_lon = a.location.lat, a.location.lon
            b_lat, b_lon = b.location.lat, b.location.lon
            if a_lat == b_lat and a_lon == b_lon:
                continue
            # Very long edges in incomplete extracts are not reliable matches.
            metres = math.hypot((a_lat - b_lat) * 111195, (a_lon - b_lon) * 111195 * math.cos(math.radians(a_lat)))
            if metres > 500:
                continue
            self.last_id += 1
            self.db.execute("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?)", (
                self.last_id, a_lat, a_lon, b_lat, b_lon, forward, backward, int(one_way), tags.get("name", "")[:100]))
            tile_id = math.floor((a_lat + b_lat) * 100) * 100000 + math.floor((a_lon + b_lon) * 100) + 36000
            self.db.execute("INSERT INTO tiles VALUES (?,?)", (self.last_id, tile_id))
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
        """)
        builder = Builder(db)
        builder.apply_file(args.input, locations=True, idx="flex_mem")
        db.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("format", "motolimiet-2"),
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
