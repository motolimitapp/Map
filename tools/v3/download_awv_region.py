#!/usr/bin/env python3
"""Research-only bounded regional AWV snapshot; no production publication."""
import argparse
from download_awv import download
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("output")
    p.add_argument("--bbox",required=True)
    a=p.parse_args()
    download(a.output,a.bbox)
