#!/usr/bin/env python3
"""Research release-readiness summary. Does not publish or modify map data."""
import argparse,json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument("output")
p.add_argument("--ride-report",action="append",default=[])
p.add_argument("--full-candidate-validated",action="store_true")
a=p.parse_args()

blockers=[]
warnings=[]
for path in a.ride_report:
    report=json.loads(Path(path).read_text(encoding="utf-8"))
    for row in report.get("anchors",[]):
        if row.get("status")=="verified_regression" and row.get("evidence_level")=="official_directional":
            blockers.append({"type":"verified_directional_regression","id":row.get("id"),"candidate_kmh":row.get("candidate_kmh"),"expected_kmh":row.get("expected_kmh")})
        elif row.get("status") in ("rider_discrepancy_unverified","ambiguous_candidates_unresolved"):
            warnings.append({"type":row.get("status"),"id":row.get("id")})
if not a.full_candidate_validated:
    blockers.append({"type":"full_belgium_candidate_not_validated"})

out={
    "status":"release_blocked" if blockers else "release_candidate",
    "production_publish_allowed":False if blockers else True,
    "blockers":blockers,
    "warnings":warnings,
    "note":"Research gate only. A separate explicit production approval is still required even when blockers are empty."
}
Path(a.output).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
print(json.dumps(out,indent=2))
