"""
源明文级划分数据集 — 回应审稿人 R1M2 / R1M8（数据泄漏问题）

核心思想（区别于原 sample-level 划分）：
- 原划分按「样本」切分：同一源明文可同时出现在 train 与 test，只是换了变换方式/窗口，
  模型可能背下源明文本身而非算法特征 → 数据泄漏。
- 本划分按「源明文(corpus)」切分：将 13,077 条源明文按 split_seed 打散后
  切分为 train/val/test（70/15/15，互不重叠），每个 split 只使用自己的子集作为语料池。
- 每个 split 的样本数与原协议完全一致（每类 train 700 / val 150 / test 150），
  因此与原协议唯一区别 = 源明文在 split 间不重叠，用于隔离并量化泄漏影响。

实现方式：继承 CachedCipherDataset，仅覆盖「语料池」与「缓存目录」，
复用原数据生成、索引构建、缓存、preload 的全部逻辑（风险最小）。
"""
import os
import numpy as np

from config import *
from data.corpus import get_corpus
from data.dataset import CachedCipherDataset


class CorpusSplitCachedCipherDataset(CachedCipherDataset):
    """源明文级划分数据集：语料池为 disjoint 子集，样本数与原协议一致"""

    def __init__(self, split='train', dual_view=True, split_seed=42):
        self.split_seed = split_seed

        # 读取全部语料并按 split_seed 打散、切分
        all_corpus = get_corpus()
        n_total = len(all_corpus)
        rng = np.random.RandomState(split_seed)
        ids = np.arange(n_total)
        rng.shuffle(ids)

        n_train = int(n_total * 0.70)
        n_val = int(n_total * 0.15)
        if split == 'train':
            my_ids = ids[:n_train]
        elif split == 'val':
            my_ids = ids[n_train:n_train + n_val]
        else:  # test
            my_ids = ids[n_train + n_val:]

        self.corpus_ids = my_ids
        self._split_pool = [all_corpus[i] for i in my_ids]

        # 父类初始化：构建索引（每类样本数与原协议一致）、设置默认语料池
        super().__init__(split=split, dual_view=dual_view)

        # 用 disjoint 子集覆盖语料池 + 独立的缓存目录（按 split_seed 区分）
        self.corpus_pool = self._split_pool
        self.cache_dir = os.path.join(
            DATA_DIR, f"cache_corpus_split_{split_seed}", split
        )
        os.makedirs(self.cache_dir, exist_ok=True)

        print(f"[{split}|split_seed={split_seed}] 源明文子集: {len(self._split_pool)} 条")


def verify_corpus_split_integrity(split_seed=42):
    """验证三个 split 的源明文互不重叠，且并集覆盖全部语料"""
    n_total = len(get_corpus())
    train_ids = set(CorpusSplitCachedCipherDataset('train', split_seed=split_seed).corpus_ids)
    val_ids = set(CorpusSplitCachedCipherDataset('val', split_seed=split_seed).corpus_ids)
    test_ids = set(CorpusSplitCachedCipherDataset('test', split_seed=split_seed).corpus_ids)

    assert not (train_ids & val_ids), "train/val 语料重叠！"
    assert not (train_ids & test_ids), "train/test 语料重叠！"
    assert not (val_ids & test_ids), "val/test 语料重叠！"

    union = train_ids | val_ids | test_ids
    assert union == set(range(n_total)), "并集未覆盖全部语料！"

    print(f"[verify] 总语料 {n_total}: train={len(train_ids)} val={len(val_ids)} "
          f"test={len(test_ids)}, 无重叠 ✓")
    return True


if __name__ == "__main__":
    for s in [42, 1, 2, 3]:
        verify_corpus_split_integrity(s)
    print("所有划分完整性验证通过 ✓")
