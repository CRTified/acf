# Auxiliary Curve Finder

This is a tool to find auxiliary elliptic curves by brute-force.
Please see [discrete-log](https://github.com/CRTified/discrete-log)
and the paper [Dlog is Practically as Hard (or Easy) as DH](https://eprint.iacr.org/2023/539)
for an in-detail explanation.

This Repo contains the code for a large-scale search of auxiliary curves.

## How to use

```
usage: curve_finder.py [-h] [--coordinator] [-H HOST] [-p PORT] [-k KEY] [-c CSV] [-j NCPU] [-t THRESHOLD]

Auxiliary Curve Finder

options:
  -h, --help            show this help message and exit
  --coordinator         Run in coordinator mode
  -H HOST, --host HOST  The hostname of the coordinator (Default: $ACF_HOST or localhost)
  -p PORT, --port PORT  The port of the coordinator (Default: $ACF_PORT or 46173)
  -k KEY, --key KEY     Auth key for the remote connection (Default: $ACF_SECRET or fixed value)
  -c CSV, --csv CSV     CSV file (r/w) of target elliptic curves (Default: $ACF_CSV or curves.csv)
  -j NCPU, --ncpu NCPU  Number of processes to run in parallel (Default: $ACF_NCPU or all CPUs (Detected: _))
  -t THRESHOLD, --threshold THRESHOLD
                        Threshold for the order of the auxiliary curve in bits to consider finished
```
