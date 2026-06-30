#!/usr/bin/env python3
#!/usr/bin/env python3
"""
Measure NSEC3 parameters for a list of domains.

For each domain, this script queries the NSEC3PARAM resource record at the
zone apex through a recursive resolver using EDNS(0) and the DNSSEC OK (DO)
bit. If NSEC3PARAM records are present, the script extracts the published
NSEC3 parameters (algorithm, flags, iteration count, and salt).

From the observed parameters, the script additionally derives:

  - Knot Resolver's NSEC3 price
  - Whether the parameter set exceeds Knot Resolver's default price limit
    (price > 51)
  - Whether the iteration count exceeds the default limit (iterations > 50)
    used by several validating resolvers

The script measures published NSEC3 parameters only. It does not execute,
instrument, or evaluate any resolver implementation. It also does not query
DNSKEY records; therefore, the dnskey_observed column is intentionally left
empty.

Output CSV columns:
  domain,status,rcode,dnskey_observed,nsec3param_count,
  algo,flags,iterations,salt_len,salt_hex,
  knot_price,knot_limited,iter_limit_exceeded
"""

import argparse
import csv
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Empty, Queue

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rdatatype
import dns.rcode
from tqdm import tqdm


HEADER = [
    "domain",
    "status",
    "rcode",
    "dnskey_observed",
    "nsec3param_count",
    "algo",
    "flags",
    "iterations",
    "salt_len",
    "salt_hex",
    "knot_price",
    "knot_limited",
    "iter_limit_exceeded",
]


def knot_price(iterations: int, salt_len: int) -> int:
    """Compute Knot Resolver's NSEC3 price from the observed parameters."""
    return (iterations + 1) * math.ceil((20 + salt_len) / 64)


def knot_limited(iterations: int, salt_len: int) -> bool:
    """Return whether the computed price exceeds Knot Resolver's default limit."""
    return knot_price(iterations, salt_len) > 51


def iter_limit_exceeded(iterations: int) -> bool:
    """Return whether the iteration count exceeds the default limit of 50."""
    return iterations > 50


def norm_domain(line: str) -> str:
    """Normalize one input line to an FQDN with a trailing dot."""
    domain = line.strip().rstrip("\r")
    if not domain or domain.startswith("#"):
        return ""
    return domain if domain.endswith(".") else domain + "."


def dns_udp_tcp(
    query: dns.message.Message,
    server: str,
    timeout: float,
    retries: int,
) -> dns.message.Message:
    """
    Send DNS query over UDP and fall back to TCP if truncated.
    Retries are applied to timeout/blocking/OS-level transient errors.
    """
    last_error = None

    for attempt in range(retries + 1):
        try:
            response = dns.query.udp(query, server, timeout=timeout)
            if response.flags & dns.flags.TC:
                response = dns.query.tcp(query, server, timeout=timeout)
            return response

        except (dns.exception.Timeout, BlockingIOError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.02 * (attempt + 1))
                continue
            raise

    raise last_error  # pragma: no cover


def query_nsec3param(
    domain: str,
    server: str,
    timeout: float,
    edns_payload: int,
    retries: int,
):
    """Query NSEC3PARAM at the zone apex and return (rcode, params)."""
    query = dns.message.make_query(domain, dns.rdatatype.NSEC3PARAM, want_dnssec=True)
    query.flags |= dns.flags.RD
    query.use_edns(edns=0, payload=edns_payload, ednsflags=dns.flags.DO)

    response = dns_udp_tcp(query, server, timeout=timeout, retries=retries)
    rcode_txt = dns.rcode.to_text(response.rcode())

    params = []
    if response.rcode() == dns.rcode.NOERROR:
        for rrset in response.answer:
            if rrset.rdtype != dns.rdatatype.NSEC3PARAM:
                continue
            for rr in rrset:
                params.append(
                    {
                        "algo": int(rr.algorithm),
                        "flags": int(rr.flags),
                        "iterations": int(rr.iterations),
                        "salt_bytes": rr.salt or b"",
                    }
                )

    return rcode_txt, params


def writer_thread_fn(out_path: str, queue: Queue, stop: threading.Event) -> None:
    """Write CSV rows from a queue to disk."""
    write_header = (not os.path.exists(out_path)) or (os.path.getsize(out_path) == 0)

    with open(out_path, "a", newline="", encoding="utf-8") as outfile:
        writer = csv.writer(outfile, lineterminator="\n")

        if write_header:
            writer.writerow(HEADER)

        while not (stop.is_set() and queue.empty()):
            try:
                row = queue.get(timeout=0.2)
            except Empty:
                continue

            writer.writerow(row)
            queue.task_done()


def load_processed_domains(csv_path: str) -> set[str]:
    """Load domains already present in an output CSV for resume support."""
    processed: set[str] = set()

    if not csv_path or not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return processed

    with open(csv_path, "r", encoding="utf-8", errors="ignore") as infile:
        infile.readline()  # header
        for line in infile:
            domain = line.split(",", 1)[0].strip()
            if domain:
                processed.add(norm_domain(domain))

    return processed


def load_domains(path: str) -> list[str]:
    """Load and normalize domains from a text file."""
    domains: list[str] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as infile:
        for line in infile:
            domain = norm_domain(line)
            if domain:
                domains.append(domain)

    return domains


def rows_for_domain(domain: str, args: argparse.Namespace) -> list[list[object]]:
    """Measure one domain and return one or more CSV rows."""
    try:
        rcode_txt, params = query_nsec3param(
            domain,
            args.resolver,
            args.timeout,
            args.edns_payload,
            args.retries,
        )

        if rcode_txt != "NOERROR":
            return [[domain, "error_rcode", rcode_txt, "", 0, "", "", "", "", "", "", "", ""]]

        if not params:
            return [[domain, "nodata", rcode_txt, "", 0, "", "", "", "", "", "", "", ""]]

        rows = []
        for param in params:
            iterations = param["iterations"]
            salt_bytes = param["salt_bytes"]
            salt_len = len(salt_bytes)
            salt_hex = salt_bytes.hex().upper()

            price = knot_price(iterations, salt_len)
            limited = knot_limited(iterations, salt_len)
            pdns_reject = iter_limit_exceeded(iterations)

            rows.append(
                [
                    domain,
                    "ok",
                    rcode_txt,
                    "",
                    len(params),
                    param["algo"],
                    param["flags"],
                    iterations,
                    salt_len,
                    salt_hex,
                    price,
                    int(limited),
                    int(pdns_reject),
                ]
            )

        return rows

    except (dns.exception.Timeout, BlockingIOError, OSError):
        return [[domain, "timeout_or_blocking", "TIMEOUT_OR_BLOCKING", "", 0, "", "", "", "", "", "", "", ""]]

    except Exception as exc:
        return [[domain, "exception", type(exc).__name__, "", 0, "", "", "", "", "", "", "", ""]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast NSEC3PARAM measurement.")
    parser.add_argument("domains", help="Input file with one domain per line")
    parser.add_argument("--resolver", default="1.1.1.1", help="Recursive resolver IP")
    parser.add_argument("--out", default="results_fast.csv", help="Output CSV file")
    parser.add_argument(
        "--resume-from",
        default="",
        help="Optional CSV file whose domains should be skipped",
    )
    parser.add_argument("--workers", type=int, default=80, help="Parallel worker threads")
    parser.add_argument("--timeout", type=float, default=1.2, help="DNS timeout in seconds")
    parser.add_argument("--retries", type=int, default=1, help="Retries per DNS query")
    parser.add_argument("--edns-payload", type=int, default=1232, help="EDNS UDP payload size")
    args = parser.parse_args()

    domains = load_domains(args.domains)

    processed = set()
    if args.resume_from:
        processed |= load_processed_domains(args.resume_from)
    processed |= load_processed_domains(args.out)

    to_do = [domain for domain in domains if domain not in processed]

    print(f"[i] Input domains: {len(domains)}")
    print(f"[i] Skip already processed: {len(processed)}")
    print(f"[i] Remaining: {len(to_do)}")
    sys.stdout.flush()

    queue: Queue = Queue(maxsize=50000)
    stop = threading.Event()

    writer_thread = threading.Thread(
        target=writer_thread_fn,
        args=(args.out, queue, stop),
        daemon=True,
    )
    writer_thread.start()

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(rows_for_domain, domain, args) for domain in to_do]

            for future in tqdm(as_completed(futures), total=len(futures), unit="domain"):
                for row in future.result():
                    queue.put(row)

    except KeyboardInterrupt:
        print("\n[i] Interrupted. Output is consistent up to the last written row.")

    finally:
        queue.join()
        stop.set()
        writer_thread.join(timeout=2.0)

    print(f"[i] Done. Output: {args.out}")


if __name__ == "__main__":
    main()
