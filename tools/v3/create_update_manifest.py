#!/usr/bin/env python3
"""Create the small HTTPS manifest for a validated Belgium v3 map gzip.

Usage:
  python tools/v3/create_update_manifest.py MAP_GZIP HTTPS_MAP_URL OUTPUT_JSON

The Android 0.3.10 client requires the manifest and map URL to be on the
same HTTPS host, port and directory. Extra manifest fields are diagnostic;
format, built_utc, url and sha256 remain the compatibility contract.
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
    size_bytes = 0
    with open(args.gzip_map, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size_bytes += len(block)

    fd, temp = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(fd, "wb") as output, gzip.open(args.gzip_map, "rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                output.write(block)

        connection = sqlite3.connect(f"file:{temp}?mode=ro", uri=True)
        try:
            values = dict(
                connection.execute(
                    "SELECT key,value FROM metadata WHERE key IN "
                    "('format','built_utc','quality_schema','conflict_check','osm_built_utc','awv_snapshot_sha256')"
                )
            )
            if (
                values.get("format") != "motolimiet-3"
                or not values.get("built_utc")
                or values.get("quality_schema") != "1"
                or values.get("conflict_check") != "osm-awv-1"
            ):
                raise ValueError("Expected validated motolimiet-3 metadata")
        finally:
            connection.close()

        manifest = {
            "format": values["format"],
            "built_utc": values["built_utc"],
            "url": args.https_url,
            "sha256": digest.hexdigest(),
            "size_bytes": size_bytes,
            "quality_schema": values["quality_schema"],
            "conflict_check": values["conflict_check"],
        }
        if values.get("osm_built_utc"):
            manifest["osm_built_utc"] = values["osm_built_utc"]
        if values.get("awv_snapshot_sha256"):
            manifest["awv_snapshot_sha256"] = values["awv_snapshot_sha256"]

        with open(args.output, "w", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2, ensure_ascii=False)
            output.write("\n")
    finally:
        os.unlink(temp)


if __name__ == "__main__":
    main()
