#!/usr/bin/env python3
"""Read-only WFS/TN-ITS evidence probe. No speed inference or production map writes."""
import argparse
import csv
import json
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone

def get_json(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": "MotoLimiet-evidence-probe/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(25_000_001)
        if len(data) > 25_000_000:
            raise ValueError("Response exceeds 25 MB safety limit")
        return json.loads(data)

def wfs_url(endpoint, typename, bbox, count):
    args = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": typename,
            "outputFormat": "application/json", "srsName": "EPSG:4326", "bbox": ",".join(map(str, bbox)) + ",EPSG:4326",
            "count": count}
    return endpoint + ("&" if "?" in endpoint else "?") + urllib.parse.urlencode(args)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="JSON config with WFS endpoint, layer names and test bounding boxes")
    parser.add_argument("--out", default="probe-output")
    args = parser.parse_args()
    cfg = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    output = pathlib.Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    summary = {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "cases": [], "errors": [], "notes": [
        "Raw source evidence only; no speed inference or legal interpretation.",
        "A missing feature does not prove absence of a traffic sign or regulation.",
        "Feature counts reaching the request cap are incomplete and must not be used for decisions.",
        "WFS bbox axis order/CRS must be verified against server metadata before production use.",
        "TN-ITS deltas are not a complete snapshot; no delta is not proof of no change."
    ]}
    for case in cfg["cases"]:
        case_result = {"name": case["name"], "bbox": case["bbox"], "layers": {}}
        for label, typename in cfg["layers"].items():
            url = wfs_url(cfg["wfs_endpoint"], typename, case["bbox"], cfg.get("count", 1000))
            path = output / (case["name"] + "-" + label + ".geojson")
            try:
                data = get_json(url)
                if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
                    raise ValueError("Not a GeoJSON FeatureCollection")
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                n = len(data["features"])
                case_result["layers"][label] = {"count": n, "possibly_truncated": n >= cfg.get("count", 1000), "file": str(path)}
            except Exception as exc:
                case_result["layers"][label] = {"error": str(exc), "url": url}
                summary["errors"].append({"case": case["name"], "layer": label, "error": str(exc)})
        summary["cases"].append(case_result)
    if cfg.get("tnits_url"):
        try:
            data = get_json(cfg["tnits_url"])
            (output / "tnits-raw.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            summary["tnits"] = {"status": "retrieved", "note": "Not geographically joined or validated"}
        except Exception as exc:
            summary["tnits"] = {"status": "unavailable", "error": str(exc)}
            summary["errors"].append({"source": "tnits", "error": str(exc)})
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["errors"]:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
