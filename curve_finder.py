from sage.all import *
import argparse
import os
from pathlib import Path
import csv
from ctypes import c_bool
from multiprocessing import Value, Process, cpu_count
from multiprocessing.managers import SyncManager, DictProxy
from dataclasses import dataclass, field, asdict

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

def sample_curve(q):
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


class CurveManager(SyncManager): pass

def __worker__(args):
    def work(targets, messages, pindex):
        def get_task():
            return max(targets.values())

        try:
            while True:
                task = get_task()
                print(f"P{pindex}, Job: {task.name}, current best: {task.current_best}, Samples: {task.samples}")

                if task.current_best < args.threshold:
                    print("Worst curve below threshold")
                    print("No work to be done, terminating...")
                    break

                for i in range(50):
                    (a, b), smoothness = sample_curve(task.q)
                    if smoothness < targets[task.name].current_best:
                        targets[task.name].current_best = smoothness
                        targets[task.name].aux_a = a
                        targets[task.name].aux_b = b
                        targets[task.name].samples += (i + 1)

                        # Communicate result
                        messages["changed"] = True

                        print(f"New best for {task.name}: smoothness of {smoothness}, with a={a}, b={b}")

                        # Go to next curve
                        break
                else:
                    targets[task.name].samples += 50

        except KeyboardInterrupt:
            print("Terminating...")

    CurveManager.register('get_targets')
    CurveManager.register('get_messages')
    m = CurveManager(address=(args.host, args.port), authkey=args.key)
    m.connect()

    targets = m.get_targets()
    messages = m.get_messages()

    procs = []
    for i in range(args.ncpu):
        p = Process(target=work, args=(targets, messages, i))
        p.start()
        procs.append(p)

    for p in procs:
        p.join()



def __coordinator__(args):
    print(f"Reading {args.csv}")

    targets = {}
    with open(args.csv, "r", newline="") as csvfile:
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
        while True:
            if messages["changed"]:
                messages["changed"] = False

                with open(args.csv, "w", newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, **csvConfig)
                    for E in targets.values():
                        writer.writerow(asdict(E))


    except KeyboardInterrupt:
        print("Terminating...")
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

    parser.add_argument('-j', '--ncpu', type=int, default=os.getenv("ACF_NCPU", cpu_count()),
                        help=f"Number of processes to run in parallel (Default: $ACF_NCPU or all CPUs (Detected: {cpu_count()}))")

    parser.add_argument('-t', '--threshold', type=float, default=os.getenv("ACF_THRESHOLD", 20.0),
                        help="Threshold for the order of the auxiliary curve in bits to consider finished")

    args = parser.parse_args()
    if args.coordinator:
        __coordinator__(args)
    else:
        __worker__(args)
