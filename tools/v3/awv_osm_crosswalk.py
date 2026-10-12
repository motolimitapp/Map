#!/usr/bin/env python3
"""Research-only AWV/Wegenregister to OSM geometry crosswalk prototype.

This module is intentionally conservative. It does not assign a speed limit.
It only asks whether an OSM road segment can be associated with one AWV
Wegsegment_ID despite a systematic lateral geometry offset.

Acceptance requires:
- persistent proximity at 3 samples along the OSM segment;
- road-axis agreement within MAX_AXIS_ANGLE;
- stable lateral distance across the samples;
- a clear margin over competing AWV Wegsegment_ID candidates.

Ambiguous or weak matches return no crosswalk.
"""
from collections import defaultdict
import math

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

MAX_DISTANCE = 40.0
MAX_AXIS_ANGLE = 15.0
MAX_DISTANCE_VARIATION = 8.0
COMPETITOR_MARGIN = 5.0
SAMPLES = (0.1, 0.5, 0.9)


def _axis_error(ax, ay, bx, by):
    la = math.hypot(ax, ay)
    lb = math.hypot(bx, by)
    if la < 1e-9 or lb < 1e-9:
        return 180.0
    cosine = abs((ax * bx + ay * by) / (la * lb))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


class CrosswalkIndex:
    def __init__(self, awv_lines):
        """awv_lines: iterable of (LineString, wegsegment_id, feature_id)."""
        self.lines = []
        self.meta = []
        for line, road_id, feature_id in awv_lines:
            if not isinstance(line, LineString) or len(line.coords) < 2 or line.length < 1.0:
                continue
            self.lines.append(line)
            self.meta.append((road_id, feature_id))
        if not self.lines:
            raise ValueError("No AWV lines")
        self.tree = STRtree(self.lines)

    def _sample_candidates(self, point, odx, ody):
        by_road = {}
        for raw_index in self.tree.query(point.buffer(MAX_DISTANCE)):
            index = int(raw_index)
            line = self.lines[index]
            road_id, feature_id = self.meta[index]
            coords = list(line.coords)
            best = None
            for a, b in zip(coords, coords[1:]):
                ex, ey = b[0] - a[0], b[1] - a[1]
                if _axis_error(odx, ody, ex, ey) > MAX_AXIS_ANGLE:
                    continue
                edge = LineString((a, b))
                distance = float(point.distance(edge))
                if distance > MAX_DISTANCE:
                    continue
                if best is None or distance < best[0]:
                    best = (distance, feature_id)
            if best is not None and (road_id not in by_road or best[0] < by_road[road_id][0]):
                by_road[road_id] = best
        return by_road

    def match(self, osm_line):
        if not isinstance(osm_line, LineString) or len(osm_line.coords) < 2 or osm_line.length < 3.0:
            return None, {"reason": "invalid_osm_geometry"}

        a, b = osm_line.coords[0], osm_line.coords[-1]
        odx, ody = b[0] - a[0], b[1] - a[1]
        sample_sets = [self._sample_candidates(osm_line.interpolate(f, normalized=True), odx, ody) for f in SAMPLES]
        common = set(sample_sets[0])
        for candidates in sample_sets[1:]:
            common &= set(candidates)
        if not common:
            return None, {"reason": "no_persistent_candidate"}

        scores = []
        for road_id in common:
            distances = [c[road_id][0] for c in sample_sets]
            variation = max(distances) - min(distances)
            if variation > MAX_DISTANCE_VARIATION:
                continue
            scores.append((sum(distances) / len(distances), variation, road_id, distances))

        if not scores:
            return None, {"reason": "offset_not_stable"}

        scores.sort()
        best = scores[0]
        if len(scores) > 1 and scores[1][0] - best[0] < COMPETITOR_MARGIN:
            return None, {
                "reason": "competing_road_ids",
                "best_road_id": best[2],
                "best_mean_distance_m": round(best[0], 2),
                "competitor_road_id": scores[1][2],
                "competitor_mean_distance_m": round(scores[1][0], 2),
            }

        return best[2], {
            "reason": "matched",
            "road_id": best[2],
            "mean_distance_m": round(best[0], 2),
            "distance_variation_m": round(best[1], 2),
            "sample_distances_m": [round(v, 2) for v in best[3]],
        }
