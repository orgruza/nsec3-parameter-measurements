#!/usr/bin/env python3
"""
Measure DNSSEC signed-domain deployment for a domain list.

For each domain, query DS and DNSKEY records via a recursive resolver.
A domain is labeled signed=1 if both DS and DNSKEY records are observed.

Note: This is a scalable deployment proxy. The script does not perform
full DNSSEC chain-of-trust validation.
"""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed

import dns.message
import dns.query
import dns.flags
import dns.rdatatype
import dns.rcode
from tqdm import tqdm


def norm_domain(s):
    s = s.strip().rstrip("\r")
    if not s or s.startswith("#"):
        return ""
    return s if s.endswith(".") else s + "."


def query_rr(domain, rdtype, resolver, timeout=1.5, edns_payload=1232):
    q = dns.message.make_query(domain, rdtype, want_dnssec=True)
    q.use_edns(edns=0, payload=edns_payload, ednsflags=dns.flags.DO)

    try:
        r = dns.query.udp(q, resolver, timeout=timeout)
        if r.flags & dns.flags.TC:
            r = dns.query.tcp(q, resolver, timeout=timeout)

        if r.rcode() != dns.rcode.NOERROR:
            return dns.rcode.to_text(r.rcode()), False

        present = any(rrset.rdtype == rdtype for rrset in r.answer)
        return "NOERROR", present

    except Exception as e:
        return type(e).__name__, False


def main():
    ap = argparse.ArgumentParser(
        description="Measure DS/DNSKEY presence for DNSSEC signed-domain labeling."
    )
    ap.add_argument("domains", help="Input file with one domain per line")
    ap.add_argument("--resolver", default="1.1.1.1", help="Recursive resolver IP")
    ap.add_argument("--out", default="signed_domains.csv", help="Output CSV")
    ap.add_argument("--workers", type=int, default=50, help="Parallel workers")
    ap.add_argument("--timeout", type=float, default=1.5, help="DNS timeout in seconds")
    ap.add_argument("--edns-payload", type=int, default=1232, help="EDNS UDP payload size")
    args = ap.parse_args()

    with open(args.domains, encoding="utf-8", errors="ignore") as f:
        domains = [d for d in (norm_domain(line) for line in f) if d]

    def work(d):
        ds_rcode, ds_present = query_rr(
            d, dns.rdatatype.DS, args.resolver, args.timeout, args.edns_payload
        )
        dnskey_rcode, dnskey_present = query_rr(
            d, dns.rdatatype.DNSKEY, args.resolver, args.timeout, args.edns_payload
        )
        signed = int(ds_present and dnskey_present)
        return [d, ds_rcode, int(ds_present), dnskey_rcode, int(dnskey_present), signed]

    with open(args.out, "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo, lineterminator="\n")
        w.writerow(["domain", "ds_rcode", "ds_present", "dnskey_rcode", "dnskey_present", "signed"])

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(work, d) for d in domains]
            for fut in tqdm(as_completed(futures), total=len(futures), unit="domain"):
                w.writerow(fut.result())


if __name__ == "__main__":
    main()
