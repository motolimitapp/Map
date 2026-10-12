#!/usr/bin/env python3
"""Read-only official-evidence probe for MotoLimiet research.

Queries AWV WFS layers around known 12 Oct 2026 ride anchors and stores raw
GeoJSON plus nearest-feature diagnostics. It deliberately does NOT infer a
legal speed or modify any production map.
"""
import argparse
import json
import math
import pathlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform

UA = "MotoLimiet-evidence-probe/2.0"
MAX_BYTES = 50_000_000

def fetch(url, accept="*/*", timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("response exceeds 50 MB safety limit")
        return data, response.headers.get("Content-Type", "")

def fetch_json(url):
    data, _ = fetch(url, "application/json, application/geo+json;q=0.9, */*;q=0.1")
    return json.loads(data)

def wfs_url(endpoint, typename, bbox31370, count, start):
    args = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": typename,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": ",".join(f"{value:.3f}" for value in bbox31370) + ",EPSG:31370",
        "count": count,
        "startIndex": start,
    }
    return endpoint + "?" + urllib.parse.urlencode(args)

def bbox_to_31370(bbox4326, margin_m=50):
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:31370", always_xy=True)
    x1, y1 = transformer.transform(bbox4326[0], bbox4326[1])
    x2, y2 = transformer.transform(bbox4326[2], bbox4326[3])
    return [
        min(x1, x2) - margin_m,
        min(y1, y2) - margin_m,
        max(x1, x2) + margin_m,
        max(y1, y2) + margin_m,
    ]

def get_layer(endpoint, typename, bbox31370, page_size, max_features):
    features = []
    start = 0
    urls = []
    while start < max_features:
        count = min(page_size, max_features - start)
        url = wfs_url(endpoint, typename, bbox31370, count, start)
        urls.append(url)
        data = fetch_json(url)
        if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
            raise ValueError("WFS response is not a GeoJSON FeatureCollection")
        batch = data["features"]
        features.extend(batch)
        if not batch or len(batch) < count:
            break
        start += len(batch)
    return {"type": "FeatureCollection", "features": features}, urls, len(features) >= max_features

def _angle_error(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)

def _nearest_segment_heading(point, geometry):
    lines = list(geometry.geoms) if geometry.geom_type == "MultiLineString" else [geometry]
    best = None
    for line in lines:
        coords = list(line.coords)
        for a, b in zip(coords, coords[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 0.01:
                continue
            segment = shape({"type": "LineString", "coordinates": [a, b]})
            distance = float(point.distance(segment))
            if best is None or distance < best[0]:
                heading = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
                best = (distance, heading)
    return best

def nearest(anchor, features, limit=5):
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:31370", always_xy=True)
    point = Point(*transformer.transform(anchor["lon"], anchor["lat"]))
    results = []
    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            geometry31370 = shp_transform(transformer.transform, shape(geometry))
            distance = float(point.distance(geometry31370))
            tangent = _nearest_segment_heading(point, geometry31370)
        except Exception:
            continue
        item = {
            "distance_m": round(distance, 2),
            "id": feature.get("id"),
            "geometry_type": geometry.get("type"),
            "properties": feature.get("properties") or {},
            "within_7m": distance <= 7.0,
        }
        if tangent is not None:
            item["local_geometry_heading_deg"] = round(tangent[1], 1)
        if "bearing_deg" in anchor and tangent is not None:
            directed = _angle_error(anchor["bearing_deg"], tangent[1])
            axis = min(directed, abs(180.0 - directed))
            item["ride_bearing_deg"] = anchor["bearing_deg"]
            item["directed_heading_error_deg"] = round(directed, 1)
            item["axis_heading_error_deg"] = round(axis, 1)
            item["within_20deg_axis"] = axis <= 20.0
            item["within_7m_and_20deg_axis"] = distance <= 7.0 and axis <= 20.0
        results.append(item)
    results.sort(key=lambda item: item["distance_m"])
    return results[:limit]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="probe-output")
    args = parser.parse_args()

    config = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    output = pathlib.Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    summary = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "cases": [],
        "errors": [],
        "notes": [
            "Raw evidence only; no legal-speed inference.",
            "AWV layers are one evidence family; layer agreement is not independent voting.",
            "Missing WFS/TN-ITS evidence is not proof that a rule or sign is absent.",
            "Nearest geometry is diagnostic only; direction/topology/validity still require validation.",
        ],
    }

    for case in config["cases"]:
        bbox31370 = bbox_to_31370(case["bbox"], config.get("bbox_margin_m", 50))
        case_result = {
            "name": case["name"],
            "bbox_wgs84": case["bbox"],
            "bbox_epsg31370": [round(value, 2) for value in bbox31370],
            "anchors": case.get("anchors", []),
            "layers": {},
        }

        for label, typename in config["layers"].items():
            try:
                feature_collection, urls, capped = get_layer(
                    config["wfs_endpoint"],
                    typename,
                    bbox31370,
                    config.get("page_size", 500),
                    config.get("max_features_per_layer", 5000),
                )
                filename = f"{case['name']}-{label}.geojson"
                (output / filename).write_text(json.dumps(feature_collection, ensure_ascii=False), encoding="utf-8")
                property_keys = sorted({
                    key
                    for feature in feature_collection["features"]
                    for key in (feature.get("properties") or {}).keys()
                })
                layer_result = {
                    "count": len(feature_collection["features"]),
                    "capped": capped,
                    "property_keys": property_keys,
                    "file": filename,
                    "request_pages": len(urls),
                    "nearest": {},
                }
                for anchor in case.get("anchors", []):
                    layer_result["nearest"][anchor["label"]] = nearest(
                        anchor, feature_collection["features"], config.get("nearest_count", 5)
                    )
                case_result["layers"][label] = layer_result
            except Exception as exc:
                case_result["layers"][label] = {"error": repr(exc)}
                summary["errors"].append({"case": case["name"], "layer": label, "error": repr(exc)})

        summary["cases"].append(case_result)

    tnits_url = config.get("tnits_url")
    if tnits_url:
        try:
            raw, content_type = fetch(tnits_url)
            if "json" in content_type.lower():
                suffix = ".json"
            elif "xml" in content_type.lower() or raw.lstrip().startswith(b"<"):
                suffix = ".xml"
            else:
                suffix = ".bin"
            filename = "tnits-dataset-list" + suffix
            (output / filename).write_bytes(raw)
            tnits_result = {
                "status": "retrieved",
                "content_type": content_type,
                "bytes": len(raw),
                "file": filename,
                "note": "Dataset list retrieved; limited change records sampled for schema inspection.",
            }
            sample_limit = int(config.get("tnits_sample_limit", 0))
            if sample_limit > 0 and suffix == ".xml":
                root = ET.fromstring(raw)
                hrefs = []
                for element in root.iter():
                    href = element.attrib.get("{http://www.w3.org/1999/xlink}href")
                    if href:
                        hrefs.append(href)
                tnits_result["dataset_ref_count"] = len(hrefs)
                sample_dir = output / "tnits-samples"
                sample_dir.mkdir(exist_ok=True)
                samples = []
                for index, href in enumerate(hrefs[-sample_limit:]):
                    try:
                        sample_raw, sample_type = fetch(href, timeout=15)
                        sample_name = f"dataset-{index:03d}.xml"
                        (sample_dir / sample_name).write_bytes(sample_raw)
                        samples.append({
                            "href": href,
                            "bytes": len(sample_raw),
                            "content_type": sample_type,
                            "file": str(pathlib.Path("tnits-samples") / sample_name),
                        })
                    except Exception as sample_exc:
                        samples.append({"href": href, "error": repr(sample_exc)})
                tnits_result["samples"] = samples
            summary["tnits"] = tnits_result
        except Exception as exc:
            summary["tnits"] = {"status": "unavailable", "error": repr(exc)}
            summary["errors"].append({"source": "tnits", "error": repr(exc)})

    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(2 if summary["errors"] else 0)

if __name__ == "__main__":
    main()
