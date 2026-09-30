#!/usr/bin/env python3
"""Create the small HTTPS manifest for a published Belgium map gzip.

Usage: python tools/create_update_manifest.py belgium-limits.db.gz https://example.org/maps/belgium-limits.db.gz manifest.json
Publish the gzip and manifest on the same HTTPS host.
"""
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gzip_map")
    parser.add_argument("https_url")
    parser.add_argument("output")
    args = parser.parse_args()
    if not args.https_url.startswith("https://"):
        parser.error("The map URL must use HTTPS")
    digest = hashlib.sha256()
    with open(args.gzip_map, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    fd, temp = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(fd, "wb") as output, gzip.open(args.gzip_map, "rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                output.write(block)
        connection = sqlite3.connect(f"file:{temp}?mode=ro", uri=True)
        try:
            values = dict(connection.execute("SELECT key,value FROM metadata WHERE key IN ('format','built_utc')"))
            if values.get("format") != "motolimiet-2" or not values.get("built_utc"):
                raise ValueError("Expected motolimiet-2 and built_utc metadata")
        finally:
            connection.close()
        manifest = {"format": values["format"], "built_utc": values["built_utc"], "url": args.https_url, "sha256": digest.hexdigest()}
        with open(args.output, "w", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2, ensure_ascii=False)
            output.write("\n")
    finally:
        os.unlink(temp)


if __name__ == "__main__":
    main()
