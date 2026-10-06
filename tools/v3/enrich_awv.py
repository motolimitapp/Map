#!/usr/bin/env python3
"""Conservative, offline AWV fallback. Input is immutable; output is atomic.

Only explicitly eligible OSM gaps are enriched. Existing numeric and semantic
limits are never overwritten. No geographic exceptions or street-name patches.
"""
import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform
from shapely.strtree import STRtree

TO_LOCAL = Transformer.from_crs(4326, 31370, always_xy=True).transform
FROM_LOCAL = Transformer.from_crs(31370, 4326, always_xy=True).transform
AWV_TO_LOCAL = Transformer.from_crs(3857, 31370, always_xy=True).transform
MAX_DISTANCE = 7.0
MAX_ANGLE = 20.0
SAMPLE_STEP = 3.0


class AwvIndex:
    def __init__(self, collection):
        if "3857" not in str(collection.get("crs")):
            raise ValueError("AWV snapshot must use EPSG:3857")
        if int(collection["numberMatched"]) != len(collection["features"]):
            raise ValueError("Incomplete snapshot")
        self.stats = Counter()
        ways = defaultdict(list)
        records = []
        for feature_number,feature in enumerate(collection["features"],1):
            if feature_number%100000==0:print("AWV geometries",feature_number,flush=True)
            geometry = feature["geometry"]
            if not geometry or geometry["type"] not in ("LineString", "MultiLineString"):
                self.stats["unsupported_geometry"] += 1
                continue
            parts = geometry["coordinates"] if geometry["type"] == "MultiLineString" else [geometry["coordinates"]]
            coordinates = list(parts[0])
            continuous = True
            for part in parts[1:]:
                if coordinates[-1] != part[0]:
                    continuous = False
                    break
                coordinates.extend(part[1:])
            props = feature["properties"]
            for coords in [coordinates] if continuous else parts:
                line = transform(AWV_TO_LOCAL, LineString(coords))
                if not line.is_valid or line.length < 2:
                    continue
                ways[props["Wegsegment_ID"]].append(line)
                records.append((line, props, feature["id"], continuous))
        groups=defaultdict(list)
        for record in records:groups[(record[1]["Wegsegment_ID"],record[1]["Vorige_wegsegment_ID"])].append(record)
        proven=set()
        for (_,previous_id),group in groups.items():
            previous=ways.get(previous_id,[])
            for line,props,fid,continuous in group:
                start,end=Point(line.coords[0]),Point(line.coords[-1])
                if continuous and any(p.distance(start)<2 for p in previous) and not any(p.distance(end)<2 for p in previous):proven.add(id(line))
            changed=True
            while changed:
                changed=False
                for line,props,fid,continuous in group:
                    if continuous and id(line) not in proven and any(id(r[0]) in proven and Point(r[0].coords[-1]).distance(Point(line.coords[0]))<2 for r in group):
                        proven.add(id(line));changed=True
        self.lines, self.entries, self.evidence = [], [], {}
        for line, props, feature_id, continuous in records:
            direction_ok = id(line) in proven
            value = props.get("Snelheid")
            sign = props.get("Bepalend_bord")
            supported = type(value) is int and value in (20, 30, 40, 50, 60, 70, 90, 120) and sign in ("F1a", "F1b", "C43", "ZC43")
            if sign in ("F1a", "F1b") and value != 50:
                supported = False
            usable = supported and direction_ok and continuous
            kind="fixed" if usable else "unproven"
            if direction_ok and continuous and "IVMS" in str(sign).upper():kind="variable"
            self.evidence[feature_id]=(kind,value or 0,sign or "",feature_id)
            self.stats["usable_features" if usable else "blocking_features"] += 1
            pairs = list(zip(line.coords, list(line.coords)[1:]))
            for edge_number, (a, b) in enumerate(pairs):
                edge = LineString((a, b))
                if edge.length < 0.1:
                    continue
                self.lines.append(edge)
                self.entries.append((value if usable else 0, feature_id, props["Wegsegment_ID"], edge_number == 0, edge_number == len(pairs)-1))
        if not self.lines:
            raise ValueError("No usable AWV geometry")
        self.tree = STRtree(self.lines)

    def match(self, point, dx, dy):
        candidates = []
        for raw_index in self.tree.query(point.buffer(MAX_DISTANCE)):
            index = int(raw_index)
            line = self.lines[index]
            a, b = line.coords
            ex, ey = b[0]-a[0], b[1]-a[1]
            projection = ((point.x-a[0])*ex+(point.y-a[1])*ey)/(ex*ex+ey*ey)
            value, feature_id, road_id, first, last = self.entries[index]
            if (projection < -1e-7 and first) or (projection > 1+1e-7 and last):
                continue
            cosine = (dx*ex+dy*ey)/(math.hypot(dx,dy)*line.length)
            if cosine < math.cos(math.radians(MAX_ANGLE)):
                continue
            distance = line.distance(point)
            if distance <= MAX_DISTANCE:
                candidates.append((distance, value, feature_id, road_id, index))
        if not candidates:
            return 0, ""
        candidates.sort()
        best = candidates[0]
        close = [c for c in candidates if c[0] <= best[0]+4]
        for candidate in close:
            if candidate[1] != best[1]:
                return 0, ""
            if candidate[3] != best[3]:
                first_line, second_line = self.lines[best[4]], self.lines[candidate[4]]
                touching = min(Point(first_line.coords[-1]).distance(Point(second_line.coords[0])), Point(second_line.coords[-1]).distance(Point(first_line.coords[0]))) < .1
                if not touching:
                    return 0, ""
        return best[1], best[2] if best[1] else ""

    def pieces(self, row):
        _, lat1, lon1, lat2, lon2, forward, backward, oneway, name = row
        a, b = TO_LOCAL(lon1, lat1), TO_LOCAL(lon2, lat2)
        line = LineString((a,b))
        if line.length < 1:
            return [(0.,1.,forward,backward,"","")]
        dx, dy = b[0]-a[0], b[1]-a[1]
        cuts = {0., 1.}
        for raw_index in self.tree.query(line.buffer(MAX_DISTANCE)):
            for xy in self.lines[int(raw_index)].coords:
                t = line.project(Point(xy), normalized=True)
                if 0 < t < 1:
                    cuts.add(t)
        count = math.ceil(line.length/SAMPLE_STEP)
        cuts.update(i/count for i in range(1,count))
        cuts = sorted(cuts)
        pieces = []
        for lo, hi in zip(cuts, cuts[1:]):
            values = []
            for direction, original in ((1,forward),(-1,backward)):
                if original or (oneway and direction == -1):
                    values.append((original,""))
                    continue
                samples = [self.match(line.interpolate(lo+(hi-lo)*fraction, normalized=True), dx*direction,dy*direction) for fraction in (.1,.5,.9)]
                values.append(samples[1] if samples[0] == samples[1] == samples[2] else (0,""))
            state = (values[0][0],values[1][0],values[0][1],values[1][1])
            if pieces and pieces[-1][2:] == state:
                pieces[-1] = (pieces[-1][0],hi,*state)
            else:
                pieces.append((lo,hi,*state))
        if any((p[1]-p[0])*line.length < 1 for p in pieces):
            return [(0.,1.,forward,backward,"","")]
        return pieces


def enrich(source, snapshot, destination, report):
    source, snapshot, destination, report = map(Path,(source,snapshot,destination,report))
    if destination.exists() or report.exists() or source.resolve() == destination.resolve():
        raise ValueError("Choose new output and report paths")
    collection = json.loads(snapshot.read_text())
    index = AwvIndex(collection)
    snapshot_metadata = collection.get("motolimiet_snapshot", {})
    del collection
    temporary = destination.with_suffix(destination.suffix+".part")
    if temporary.exists():
        raise ValueError("Temporary output exists; inspect/remove it before retrying")
    original = sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)
    output = None
    stats = Counter()
    try:
        metadata = dict(original.execute("SELECT key,value FROM metadata"))
        if metadata.get("format") != "motolimiet-2" or metadata.get("awv_eligibility_version") != "1":
            raise ValueError("Rebuild from OSM with the updated builder; old maps lack exclusion evidence")
        if "awv_snapshot_sha256" in metadata:
            raise ValueError("Always enrich a fresh OSM build, never an already enriched map")
        output = sqlite3.connect(temporary)
        original.backup(output)
        output.execute("CREATE TABLE awv_provenance (segment_id INTEGER PRIMARY KEY,original_segment_id INTEGER,forward_feature TEXT,backward_feature TEXT)")
        maximum = output.execute("SELECT coalesce(max(id),0) FROM segments").fetchone()[0]
        query = "SELECT s.*,p.osm_way_id FROM segments s JOIN osm_provenance p ON p.segment_id=s.id WHERE p.awv_eligible=1 AND (forward_kmh=0 OR (oneway=0 AND backward_kmh=0))"
        for extended in original.execute(query):
            row, osm_way = extended[:9], extended[9]
            if not (50.65 <= row[1] <= 51.55 and 2.5 <= row[2] <= 5.95):
                continue
            stats["eligible_edges"] += 1
            pieces = index.pieces(row)
            if not any(p[4] or p[5] for p in pieces):
                continue
            stats["enriched_original_edges"] += 1
            original_id = row[0]
            output.execute("DELETE FROM segments WHERE id=?",(original_id,))
            output.execute("DELETE FROM tiles WHERE id=?",(original_id,))
            output.execute("DELETE FROM osm_provenance WHERE segment_id=?",(original_id,))
            for n,(lo,hi,fw,bw,fw_id,bw_id) in enumerate(pieces):
                if n == 0:
                    segment_id = original_id
                else:
                    maximum += 1
                    segment_id = maximum
                lat1=row[1]+(row[3]-row[1])*lo; lon1=row[2]+(row[4]-row[2])*lo
                lat2=row[1]+(row[3]-row[1])*hi; lon2=row[2]+(row[4]-row[2])*hi
                output.execute("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?)",(segment_id,lat1,lon1,lat2,lon2,fw,bw,row[7],row[8]))
                tile=math.floor((lat1+lat2)*100)*100000+math.floor((lon1+lon2)*100)+36000
                output.execute("INSERT INTO tiles VALUES (?,?)",(segment_id,tile))
                output.execute("INSERT INTO osm_provenance VALUES (?,?,?)",(segment_id,osm_way,1))
                output.execute("INSERT INTO awv_provenance VALUES (?,?,?,?)",(segment_id,original_id,fw_id,bw_id))
                stats["supplemented_directions"] += bool(fw_id)+bool(bw_id)
            if stats["enriched_original_edges"] % 1000 == 0:
                print(dict(stats),flush=True)
        if not stats["supplemented_directions"]:
            raise ValueError("No AWV matches accepted; output was not created")
        with snapshot.open("rb") as stream:
            hasher=hashlib.sha256()
            for block in iter(lambda:stream.read(1024*1024),b""):
                hasher.update(block)
        digest=hasher.hexdigest()
        evidence=dict(policy="conservative-1",snapshot_sha256=digest,snapshot=snapshot_metadata,statistics=dict(stats),index_statistics=dict(index.stats),max_distance_m=MAX_DISTANCE,max_angle_degrees=MAX_ANGLE)
        output.executemany("INSERT OR REPLACE INTO metadata VALUES (?,?)",[
            ("source",metadata["source"]+"; Bron: MOW - AWV"),
            ("built_utc",datetime.datetime.now(datetime.timezone.utc).isoformat()),
            ("osm_built_utc",metadata["built_utc"]),
            ("awv_snapshot_sha256",digest),("awv_policy","conservative-1"),
            ("awv_snapshot",json.dumps(evidence["snapshot"]))])
        output.commit()
        if output.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Output database validation failed")
        if output.execute("SELECT count(*) FROM segments").fetchone() != output.execute("SELECT count(*) FROM tiles").fetchone():
            raise ValueError("Tile count mismatch")
        output.close();output=None
        report.write_text(json.dumps(evidence,indent=2)+"\n")
        temporary.replace(destination)
        print(json.dumps(evidence,indent=2))
    finally:
        original.close()
        if output is not None:
            output.close()
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source");p.add_argument("snapshot");p.add_argument("output");p.add_argument("report")
    args=p.parse_args()
    enrich(args.source,args.snapshot,args.output,args.report)
