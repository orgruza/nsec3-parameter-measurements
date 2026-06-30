# NSEC3 Parameter Measurements

This repository contains the measurement scripts, datasets, and plotting utilities used for the Internet-scale analysis of NSEC3 deployments presented in the accompanying paper.

The measurements were performed from **February 3 to February 5, 2026 (CET)** on the Tranco Top-1M domain list using the public recursive resolver **1.1.1.1 (Cloudflare)**. For each domain, the scripts collect published NSEC3 parameters, derive the corresponding work limits used by current DNSSEC-validating resolvers, and reproduce the figures reported in the paper.

The repository includes the processed measurement datasets used to obtain the reported results.

---

# Repository Structure

```
.
├── data/
│   ├── results_all_merged.csv
│   └── signed_domains.csv
│
├── figures/
│   ├── knot_price_depth_model.pdf
│   └── nsec3_salt_iterations_ccdf.pdf
│
├── input/
│   └── test_domains.txt
│
├── scripts/
│   ├── measure_nsec3params_fast.py
│   ├── measure_signed_domains.py
│   ├── plot_knot_price_depth.py
│   └── plot_nsec3_ccdf.py
│
├── LICENSE
├── README.md
└── requirements.txt
```

---

# Requirements

The scripts were tested with **Python 3.12.3**.

Install the required Python packages using

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

---

# Reproducing the Measurements

## Measuring NSEC3 Parameters

The following command measures the NSEC3 parameters published by a list of domains.

```bash
python3 scripts/measure_nsec3params_fast.py \
    input/domains.txt \
    --resolver 1.1.1.1 \
    --out data/results_all_merged.csv
```

For each domain, the script

- queries the zone apex for the `NSEC3PARAM` resource record,
- enables EDNS(0) with a UDP payload size of 1232 bytes,
- sets the DNSSEC OK (DO) bit,
- extracts the published NSEC3 parameters (algorithm, flags, iteration count, and salt),
- computes Knot Resolver's NSEC3 price,
- determines whether the published parameter set exceeds Knot Resolver's default work limit (`price > 51`), and
- determines whether the iteration count exceeds the default limit (`iterations > 50`) used by several validating resolvers.

The script evaluates published NSEC3 parameters only. It does **not** execute, instrument, or benchmark any resolver implementation.

---

## Measuring DNSSEC Deployment

The DNSSEC deployment measurement is reproduced using

```bash
python3 scripts/measure_signed_domains.py \
    input/domains.txt \
    --resolver 1.1.1.1 \
    --out data/signed_domains.csv
```

For each domain, the script queries both `DS` and `DNSKEY`.

A domain is classified as DNSSEC-signed if both records are observed during measurement.

---

# Reproducing the Figures

The repository already contains the processed measurement datasets used in the paper.

Generate the NSEC3 parameter distribution:

```bash
python3 scripts/plot_nsec3_ccdf.py \
    data/results_all_merged.csv \
    --out figures/nsec3_salt_iterations_ccdf.pdf
```

Generate the Knot Resolver work-limit model:

```bash
python3 scripts/plot_knot_price_depth.py \
    --out figures/knot_price_depth_model.pdf
```

---

# Datasets

## `results_all_merged.csv`

Contains one row for every observed `NSEC3PARAM` resource record.

The dataset includes

- queried domain
- measurement status
- DNS response code
- number of observed `NSEC3PARAM` records
- NSEC3 hash algorithm
- NSEC3 flags
- iteration count
- salt length
- salt value (hexadecimal)
- computed Knot Resolver NSEC3 price
- whether the parameter set exceeds Knot Resolver's default work limit
- whether the iteration count exceeds the default iteration limit

## `signed_domains.csv`

Contains one row per queried domain including

- DS response code
- whether a DS record was observed
- DNSKEY response code
- whether a DNSKEY record was observed
- derived DNSSEC-signed classification

---

# Input Data

The repository includes `input/test_domains.txt` for functional testing.

The Internet-scale measurements reported in the paper were performed on the **Tranco Top-1M** domain list. Since the Tranco list is publicly available and regularly updated, it is intentionally **not** redistributed as part of this artifact.

To reproduce the full measurements, download the corresponding Tranco Top-1M list and place it as

```
input/domains.txt
```

before executing the measurement scripts.
