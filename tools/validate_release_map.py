#!/usr/bin/env python3
"""Reject incomplete or incompatible Belgium map builds before publishing."""
import argparse
import datetime
import sqlite3


def validate(path, minimum=3_000_000):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        metadata = dict(db.execute("SELECT key,value FROM metadata"))
        if metadata.get("format") != "motolimiet-2":
            raise ValueError("Wrong map format")
        built = datetime.datetime.fromisoformat(metadata["built_utc"])
        if built.tzinfo is None or not datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2) <= built <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10):
            raise ValueError("Map build timestamp is missing, stale or in the future")
        segment_count = db.execute("SELECT count(*) FROM segments").fetchone()[0]
        tile_count = db.execute("SELECT count(*) FROM tiles").fetchone()[0]
        if segment_count < minimum or segment_count != tile_count:
            raise ValueError(f"Incomplete map: segments={segment_count}, tiles={tile_count}")
        if not any(row[1] == "tile_lookup" for row in db.execute("PRAGMA index_list(tiles)")):
            raise ValueError("Tile lookup index is missing")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite quick_check failed")
        print(f"Validated {segment_count:,} road segments; built {built.isoformat()}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    args = parser.parse_args()
    validate(args.database)
