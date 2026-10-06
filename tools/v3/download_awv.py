#!/usr/bin/env python3
"""Download a complete, paginated AWV snapshot; never accept partial results."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://opendata.apps.mow.vlaanderen.be/opendata-geoserver/awv/ows"
LAYER = "awv:Afgeleide_snelheidsregimes"


def download(output, bbox=None):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists")
    features, ids, expected = [], set(), None
    while expected is None or len(features) < expected:
        params = dict(service="WFS", version="2.0.0", request="GetFeature", typeNames=LAYER,
                      outputFormat="application/json", srsName="EPSG:3857", count=10000,
                      startIndex=len(features), sortBy="Wegsegment_ID,Vorige_wegsegment_ID")
        if bbox:
            params["bbox"] = bbox + ",urn:ogc:def:crs:OGC:1.3:CRS84"
        url = ENDPOINT + "?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=180) as response:
                    page = json.load(response)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        count = int(page["numberMatched"])
        if expected is not None and count != expected:
            raise ValueError("AWV changed during download; retry the entire snapshot")
        expected = count
        batch = page["features"]
        if not batch or len(batch) != int(page["numberReturned"]):
            raise ValueError("Empty/truncated AWV page")
        if "3857" not in str(page.get("crs")):
            raise ValueError("Unexpected AWV coordinate system")
        for feature in batch:
            if feature["id"] in ids:
                raise ValueError("Duplicate feature across pages; snapshot is not stable")
            ids.add(feature["id"])
        features.extend(batch)
        print(f"AWV {len(features):,}/{expected:,}", flush=True)
    if not expected or len(features) != expected:
        raise ValueError("Incomplete AWV snapshot")
    result = dict(type="FeatureCollection", crs=page["crs"], features=features,
                  numberMatched=expected, numberReturned=expected,
                  motolimiet_snapshot=dict(endpoint=ENDPOINT, layer=LAYER, bbox=bbox,
                      retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      note="Retrieval time, not the update date of individual road records"))
    data = json.dumps(result, separators=(",", ":"), ensure_ascii=False).encode()
    temporary = output.with_suffix(output.suffix + ".part")
    try:
        temporary.write_bytes(data)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print("SHA256", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--bbox", help="Optional test area: west,south,east,north")
    args = parser.parse_args()
    download(args.output, args.bbox)
