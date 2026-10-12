#!/usr/bin/env python3
"""Bounded TN-ITS sample inspection. No speed inference, no map changes."""
import argparse
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

XLINK = "{http://www.w3.org/1999/xlink}href"

def download(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "MotoLimiet-TNITS-research/1.0",
        "Accept": "application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("response exceeds 2 MB")
        return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tnits-research")
    parser.add_argument("--sample", type=int, default=12)
    args = parser.parse_args()
    output = pathlib.Path(args.out)
    output.mkdir(exist_ok=True, parents=True)

    root = ET.fromstring(download("https://opendata.apps.mow.vlaanderen.be/tn-its/rest/dataset"))
    urls = [element.attrib[XLINK] for element in root if XLINK in element.attrib]
    results = {
        "dataset_refs": len(urls),
        "sampled": [],
        "errors": [],
        "warning": "First N catalog references only. This does not test whether Steven is present in TN-ITS.",
    }

    for index, url in enumerate(urls[:max(0, min(args.sample, 30))]):
        try:
            data = download(url)
            filename = f"dataset-{index:03d}.xml"
            (output / filename).write_bytes(data)
            document = ET.fromstring(data)
            counts = Counter(element.tag.rsplit("}", 1)[-1] for element in document.iter())
            results["sampled"].append({
                "index": index,
                "url": url,
                "file": filename,
                "root": document.tag,
                "bytes": len(data),
                "element_counts": counts.most_common(35),
            })
        except Exception as exc:
            results["errors"].append({"index": index, "url": url, "error": str(exc)})

    (output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
