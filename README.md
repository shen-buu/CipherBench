# CipherBench

**A Fine-Grained Benchmark Dataset for Algorithm-Level Fragmented Payload Identification**

CipherBench is a benchmark dataset for identifying the *algorithm* that produced a raw, fragmented byte payload: 50 algorithm-level classes across 7 categories (plaintext, encoding, hash digests, compression, symmetric encryption, asymmetric encryption, and random/control), 50,000 samples in total, where every sample is a random-offset 1,024-byte window with zero padding that simulates TCP-style payload fragmentation.

> **Status:** this repository is kept **private during peer review** and will be made public upon paper acceptance. Review copies of the data and checkpoints are available from the authors on request.

## Highlights

- **50 classes · 7 categories · 50,000 samples** (1,000 per class), each a 1,024-byte random-offset window with zero padding.
- **First public benchmark with SM2 and SM4** (Chinese national cryptographic algorithms, GM/T 0002-2012 / GM/T 0003-2012, adopted as ISO/IEC 18033-3).
- **NIST SP 800-22 randomness annotations** (Frequency and Runs pass rates) and a **9-field per-sample metadata record**.
- **Layered difficulty gradient**: hash ≈100% → encoding ≈99.6% → compression 0–100% per format (header-dependent) → symmetric encryption at chance (4.81% vs. a 5.56% baseline), consistent with IND-CPA security.
- **Control suites**: cross-library classifiers (four independent SM4 implementations), random-padding probes (evaluation-side and training-side), corpus-level partitioning (10 partitions), headless-training ablation, scaling curves, and a 512-byte window variant.

## Repository layout

```
.
├── code/                  # Main code: data generation, training, evaluation
│   ├── config.py          # Global configuration (window size, splits, seeds, classes)
│   ├── data/              # Corpus, generators, dataset pipeline
│   ├── models/            # 1D-CNN / Multi-Channel CNN / GBT / Transformer / BiLSTM
│   ├── features/          # 170-dim statistical features
│   ├── train.py           # Training entry point (train_all_baselines)
│   ├── experiments_v2/    # Calibration, ablations, scaling, per-class, corpus partitions
│   └── requirements.txt
├── code_sm4_crosslib/     # Cross-library control suite (4 independent SM4 implementations)
├── results/               # All experimental result JSONs reported in the paper
├── data/                  # (README only) dataset cache: see GitHub Release assets
├── LICENSE                # MIT (code)
├── DATA_LICENSE.md        # CC BY 4.0 (dataset, results, checkpoints)
└── CITATION.cff           # Citation metadata
```

## Quick start

```bash
git clone https://github.com/shen-buu/CipherBench.git
cd CipherBench/code
pip install -r requirements.txt

# 1) Obtain the dataset cache: download `cache_corrected_v2.tar.gz` from the
#    GitHub Release assets and extract it into code/data/cache/ (see data/README.md).
#    The generators can also rebuild the dataset from scratch (deterministic seeds).

# 2) Train all five baselines (GBT, 1D-CNN, Multi-Channel CNN, Byte Transformer, BiLSTM-Attention)
python train.py

# 3) Run specific experiments (calibration, ablations, scaling, corpus partitions, ...)
python experiments_v2/<script>.py
```

## Reproduced results

The `results/` directory contains the JSON files behind every table and figure of the paper (seed-42 and five-seed runs). Headline numbers on the corrected dataset:

| Model (5 seeds, mean ± SD) | Accuracy |
|---|---|
| GBT | 49.19 ± 0.20% |
| 1D-CNN | 50.80 ± 0.12% |
| Multi-Channel CNN | 51.84 ± 0.19% (seed-42: 51.79%) |
| Byte Transformer | 50.73 ± 0.35% |
| BiLSTM-Attention | 51.36 ± 0.36% |

## Citation

```bibtex
@article{CipherBench,
  title = {CipherBench: A Fine-Grained Benchmark Dataset for Algorithm-Level Fragmented Payload Identification},
  author = {Shen, Jinhui and Liu, Kai and Zhao, Mengnan and Yue, Ziye and Mao, Jiaqi and Li, Xiaofeng},
  journal = {Applied Sciences},
  year = {2026},
  note = {(publication details to be added upon acceptance)}
}
```

## License

- **Code** (`code/`, `code_sm4_crosslib/`): [MIT License](LICENSE)
- **Dataset, results, and checkpoints** (`data/`, `results/`, Release assets): [CC BY 4.0](DATA_LICENSE.md) — attribution required; please cite the CipherBench paper.

## Data availability

The corrected dataset cache (~80 MB) and the trained model checkpoints are distributed as **GitHub Release assets** of this repository. During peer review the repository is private; access is granted to reviewers and editors on request (see the Data Availability statement of the manuscript).
