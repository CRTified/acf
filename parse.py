import csv
import json
import os
import sys
from collections import defaultdict
from sage.all import *


from dataclasses import dataclass, field, asdict

@dataclass(order=True)
class EllipticCurveTask:
    name: str=field(compare=False)
    q: int=field(compare=False)

    samples: int=field(compare=False)
    current_best: float=field(compare=True)

    aux_a: int=field(compare=False)
    aux_b: int=field(compare=False)

FIELDNAMES = ("name", "q", "samples", "current_best", "aux_a", "aux_b")


if __name__ == "__main__":
    curves = defaultdict(list)
    if len(sys.argv) != 2:
        print(f"# Usage: {sys.argv[0]} /path/to/git/checkout")
        print(f"# Expecting path to clone of https://github.com/J08nY/std-curves")
        print(f"git clone https://github.com/J08nY/std-curves.git")
        sys.exit(1)

    for root, _, files in os.walk(sys.argv[1]):
        for name in files:
            if "curves.json" not in name:
                continue
            fpath = os.path.join(root, name)
            with open(fpath, "r") as f:
                data = json.load(f)
                for curveData in data["curves"]:
                    if not is_prime(int(curveData["order"], 16)):
                        print(f"Skipping {curveData['name']}, order not prime")
                        continue

                    E = EllipticCurveTask(
                        name = f"{curveData['name']} ({data['name']})",
                        q = int(curveData["order"], 16),
                        samples = 0,
                        current_best = sys.float_info.max,
                        aux_a = 0,
                        aux_b = 0,
                    )
                    bitLevel = len(Integer(E.q).bits())
                    curves[bitLevel].append(asdict(E))

    combined = {b: [] for b in [164, 257, 384, 521, 1024]}

    for bitLevel, c in curves.items():
        bucket = min(filter(lambda x: x >= bitLevel, combined.keys()))
        combined[bucket] += c

    for bitLevel, curves in combined.items():
        with open(f"curves_{bitLevel}.csv", "w", newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES, delimiter=',', quotechar='|', quoting=csv.QUOTE_ALL)
            for E in curves:
                writer.writerow(E)

