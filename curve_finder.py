#!/bin/python3
from datetime import datetime
import argparse
import os
from time import sleep
from pathlib import Path
import csv
from ctypes import c_bool
from multiprocessing import Value, Process, cpu_count
from multiprocessing.managers import SyncManager, DictProxy
from dataclasses import dataclass, field, asdict

import socketserver
import threading

try:
    pari_mode = False
    from sage.all import *
except:
    pari_mode = True
    import cypari2
    from math import log



class tcphandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.data = self.request.recv(1024)
        self.request.send(self.data)

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass

@dataclass(order=True)
class EllipticCurveTask:
    name: str=field(compare=False)
    q: int=field(compare=False)

    samples: int=field(compare=False)
    current_best: float=field(compare=True)

    aux_a: int=field(compare=False)
    aux_b: int=field(compare=False)

    def __post_init__(self):
        self.q = int(self.q)
        self.samples = int(self.samples)
        self.current_best = float(self.current_best)
        self.aux_a = int(self.aux_a)
        self.aux_b = int(self.aux_b)

FIELDNAMES = ("name", "q", "samples", "current_best", "aux_a", "aux_b")
csvConfig = {"fieldnames": FIELDNAMES,
             "delimiter": ",",
             "quotechar": "|",
             "quoting": csv.QUOTE_ALL}



def smoothness(factors):
    return max([pi**ei for pi, ei in factors])

def sample_curve_sage(q):
    FFq = GF(q)
    def mkCurve():
        # Reject singular curves
        while 4 * (a := FFq.random_element())**3 + \
              27 * (b := FFq.random_element())**2 \
              == 0:
            pass
        return EllipticCurve(FFq, [a, b])

    # Reject Curves whose group structure splits
    while len((E := mkCurve()).gens()) != 1:
        pass

    a, b = E.a4(), E.a6()
    order = E.order()
    factors = factor(order)
    del(E)
    return (int(a), int(b)), float(log(smoothness(factors), 2))

def sample_curve_pari(q, pari):
    def mkCurve():
        # Reject singular curves
        while 4 * (a := pari.random(q))**3 + \
              27 * (b := pari.random(q))**2 \
              == 0:
            pass
        return pari.ellinit([a, b], q)

    # Reject Curves whose group structure splits
    while len(pari.ellgenerators(E := mkCurve())) != 1:
        pass

    a, b = E[3], E[4]
    order = pari.ellcard(E)
    factors = list(zip(*pari.factor(order)))
    return (int(a), int(b)), float(log(smoothness(factors), 2))

class CurveManager(SyncManager): pass

def __worker__(args):
    TRY_SAMPLES = 100
    def work(targets, messages, pindex):
        def get_task():
            return max(targets.values())

        pari = cypari2.Pari()
        pari.allocatemem(args.memory * 1000000)
        try:
            while True:
                task = get_task()
                print(f"P{pindex:03}, Job {task.name}: current best: {task.current_best}, Samples: {task.samples}", flush=True)

                if task.current_best < args.threshold:
                    print("Worst curve below threshold")
                    print("No work to be done, terminating...")
                    break

                for i in range(TRY_SAMPLES):
                    if pari_mode:
                        (a, b), smoothness = sample_curve_pari(task.q, pari)
                    else:
                        (a, b), smoothness = sample_curve_sage(task.q)

                    if smoothness >= task.current_best:
                        # We know that we did not improve, so we don't need
                        # to check the coordinator
                        continue

                    if smoothness < targets[task.name].current_best:
                        task.current_best = smoothness
                        task.aux_a = a
                        task.aux_b = b
                        task.samples += targets[task.name].samples + i + 1

                        # Communicate result
                        targets[task.name] = task
                        messages["changed"] = True

                        print(f"P{pindex:03}, Job {task.name}:     New best: {smoothness}, with a={a}, b={b}")

                        # Go to next curve
                        break
                else:
                    task = targets[task.name]
                    task.samples += TRY_SAMPLES
                    targets[task.name] = task
                    messages["changed"] = True


        except KeyboardInterrupt:
            print("Terminating...")

    CurveManager.register('get_targets')
    CurveManager.register('get_messages')
    print(f"Trying to connect to {args.host}:{args.port}...")
    m = CurveManager(address=(args.host, args.port), authkey=args.key)
    m.connect()
    print("Connected")



    targets = m.get_targets()
    messages = m.get_messages()

    print(f"Starting {args.ncpu} processes")
    procs = []
    for i in range(args.ncpu):
        p = Process(target=work, args=(targets, messages, i))
        p.start()
        procs.append(p)

    print("Starting health check port")

    server = ThreadedTCPServer(("0.0.0.0", args.port + 1), tcphandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon  = True
    server_thread.start()

    for p in procs:
        p.join()

    server.shutdown()



def __coordinator__(args):
    print(f"Reading {args.csv}")

    targets = {}

    initialFile = \
        args.csv \
        if os.path.isfile(args.csv) else \
        os.path.join("/basedata", os.path.basename(args.csv))
    with open(initialFile, "r", newline="") as csvfile:
        reader = csv.DictReader(csvfile, **csvConfig)
        for csvE in reader:
            E = EllipticCurveTask(**csvE)
            targets[E.name] = E

    print(f"Read {len(targets.keys())} curves")

    messages = { "changed": False }

    def get_targets():
        return targets

    def get_messages():
        return messages

    CurveManager.register('get_targets', get_targets, DictProxy)
    CurveManager.register('get_messages', get_messages, DictProxy)
    m = CurveManager(address=(args.host, args.port), authkey=args.key)
    m.start()
    print(f"Coordinator started on {args.host}:{args.port}")

    targets = m.get_targets()
    messages = m.get_messages()

    try:
        last_write = datetime.now()
        while True:
            if messages["changed"] and (datetime.now() - last_write).seconds >= 5:
                messages["changed"] = False

                with open(args.csv, "w", newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, **csvConfig)
                    for E in targets.values():
                        writer.writerow(asdict(E))

                last_write = datetime.now()
                print(f"\rLast write: {last_write}",  end="", flush=True)
            sleep(0.25)
    except KeyboardInterrupt:
        print("Terminating...")

        with open(args.csv, "w", newline='') as csvfile:
            writer = csv.DictWriter(csvfile, **csvConfig)
            for E in targets.values():
                print(asdict(E))
                writer.writerow(asdict(E))
        m.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="curve_finder.py",
                                     description="Auxiliary Curve Finder",
                                     )
    parser.add_argument('--coordinator', action='store_true',
                        help='Run in coordinator mode')

    parser.add_argument('-H', '--host', type=str, default=os.getenv("ACF_HOST", "localhost"), \
                        help='The hostname of the coordinator (Default: $ACF_HOST or localhost)')
    parser.add_argument('-p', '--port', type=int, default=os.getenv("ACF_PORT", 46173), \
                        help='The port of the coordinator (Default: $ACF_PORT or 46173)')
    parser.add_argument('-k', '--key', type=str, default=os.getenv("ACF_SECRET", b"qp5zys77biz7imbk6yy85q5pdv7qk84j"),
                        help='Auth key for the remote connection (Default: $ACF_SECRET or fixed value)')

    parser.add_argument('-c', '--csv', type=Path, default=os.getenv("ACF_CSV", "curves.csv"),
                        help="CSV file (r/w) of target elliptic curves (Default: $ACF_CSV or curves.csv)")

    parser.add_argument('-j', '--ncpu', type=int, default=os.getenv("ACF_NCPU", cpu_count() - 1),
                        help=f"Number of processes to run in parallel (Default: $ACF_NCPU or all but one CPUs, detected: {cpu_count() - 1})")

    parser.add_argument('-t', '--threshold', type=float, default=os.getenv("ACF_THRESHOLD", 30.0),
                        help="Threshold for the order of the auxiliary curve in bits to consider finished (Default: 30.0)")


    parser.add_argument('-m', '--memory', type=int, default=50,
                        help="Memory (in MB) to allocate per CPU for PARI (Default: 50)")

    args = parser.parse_args()



    try:
        pari = cypari2.Pari()
        pari.ellmodulareqn(11)
        print("SEA dataset available")
        del(pari)
    except:
        print("No SEA dataset available")

    if args.coordinator:
        __coordinator__(args)
    else:
        __worker__(args)
