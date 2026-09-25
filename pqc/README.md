# CipherBench-PQC (pqc/)

**License:** code under this directory is **MIT** (see [`../LICENSE`](../LICENSE));
the dataset and the frozen results are **CC BY 4.0** (see [`../DATA_LICENSE.md`](../DATA_LICENSE.md)).

CipherBench-PQC measures how much algorithm identity leaks from post-quantum
cryptographic objects through representation-level observable channels (length,
structure, byte statistics, alignment): 34 algorithm classes (16 primitives,
18 containers; 10,200 objects) from FIPS 203/204/205 implementations and OpenSSL.
This directory holds the code, the frozen results and the public audit log;
the dataset itself is distributed as a **GitHub Release asset**.

## Obtain the dataset

1. Go to the [Releases](../../releases) page of this repository and download
   `pqc_dataset_v1.0.tar.gz` (44.5 MB, tag `pqc-dataset-v1.0`).
2. Verify the checksum:

   ```
   # Linux/macOS
   sha256sum pqc_dataset_v1.0.tar.gz
   # Windows
   certutil -hashfile pqc_dataset_v1.0.tar.gz SHA256
   ```

   Expected SHA-256: `69fde5a58fb2a93b93661b4653bdc2e81b3d7458a73f2ffccb0bb02c452e6f7a`
3. Extract: the archive unpacks to `cipherbench-pqc/` containing
   `data/` (34 classes × 300 objects = 10,200 objects, 16 primitives + 18 containers),
   `data_oqs_native/` (the 900-object cross-implementation transfer set, test-only),
   plus the same code, frozen results and audit logs as this directory.

## Regenerate from scratch

- Generator: `code/gen_formal.py` (liboqs + oqs-provider + OpenSSL 3.5).
  The generator seed is fixed (`20250912`, recorded in `data/meta.json`), and the
  pipeline is checkpointed per class. Cryptographic objects draw fresh per-object
  keys from the system entropy source (NIST SP 800-131A), so a regenerated dataset
  reproduces the same *distribution*, not the same bytes; the released archive is
  therefore the canonical dataset behind the paper's numbers.
- Evaluation protocol (frozen, norm E8/E14): 5-fold stratified CV × 5 seeds
  `[7, 42, 99, 123, 2024]` with per-seed independent window RNG; the β(G) ladder uses
  50 Monte-Carlo draws with symmetric randomized tie-breaking, seed `2025`.
  Per-seed result JSONs record `env` fields (library versions, device) and seeds.

## Reproduce the frozen numbers

- Environment: Python ≥ 3.9; `pip install numpy scikit-learn matplotlib`.
  GPU tiers were frozen on torch 2.9.1+cu128 / Tesla V100 (recorded per file).
- From `pqc/`, run e.g.:

  ```bash
  python code/exp_prim60_analysis.py     # re-derives the 60-epoch tier summary
  python code/exp_data_audit.py          # read-only audit of results/*.json
  python code/exp_padding_design.py      # replay-gated: bit-exact vs. frozen ladder
  python code/exp_prior_skew.py          # replay-gated: vs. frozen per-seed F1s
  ```

  Scripts with a replay gate assert equality with the frozen files before producing
  new numbers, so the reported values are checkable rather than re-claimed.

## Layout

```
pqc/
├── code/            # generator, training, evaluation and audit scripts
│   ├── host_package/      # shared pipeline (baselines, features, NIST battery)
│   ├── exp_*.py           # one script per experiment
│   ├── pqclean/           # vendored ML-DSA-65 reference build (PQClean license)
│   └── wild/              # public CT-log scan: scripts, metadata, certificates
├── results/         # all frozen per-seed / summary JSONs (env fields, seeds)
├── audit_log/       # the public audit log (51 numbered cases, zh + en)
└── README.md
```

See `audit_log/audit_log_en.md` for the numbered audit cases behind the frozen
numbers.
