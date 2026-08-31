# Dataset cache

The 50,000-sample dataset cache (`cache_corrected_v2.tar.gz`, ~80 MB) is distributed as a
**GitHub Release asset** rather than in git history.

## Obtain

1. Go to the Releases page of this repository and download `cache_corrected_v2.tar.gz`.
2. Extract it so that the caches sit under `code/data/cache/`:

   ```
   code/data/cache/
   ├── cache_train/      # 35,000 samples (700 per class)
   ├── cache_val/        # 7,500 samples (150 per class)
   ├── cache_test/       # 7,500 samples (150 per class)
   └── corpus_pool.txt   # plaintext corpus pool (hashes only)
   ```

3. Train / evaluate as usual (`python train.py` from `code/`).

## Regenerate from scratch

The dataset is fully reproducible from its recorded seeds: `code/data/generators.py` implements
every class, and `CachedCipherDataset.preload_all()` builds the caches deterministically. Note
that ciphertext classes draw per-sample keys from the system CSPRNG as required by
NIST SP 800-131A, so regenerated caches reproduce the same *distribution* but not the same
bytes; the released cache is therefore the canonical dataset behind the paper's numbers.

The plaintext corpus (13,077 fragments) is excluded by design; only its SHA-256 pool
(`corpus_pool.txt`) is shipped.
