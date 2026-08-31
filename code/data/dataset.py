"""
PyTorch Dataset — 动态数据生成管线
"""
import os
import random
import pickle
import numpy as np
import torch
from torch.utils.data import Dataset
from tqdm import tqdm

from config import *
from data.corpus import get_corpus
from data.generators import GENERATORS
from features.statistical import extract_full_features, get_feature_dim


class CipherDataset(Dataset):
    """50类动态生成数据集"""

    def __init__(self, split='train', dual_view=True):
        """
        Args:
            split: 'train' | 'val' | 'test'
            dual_view: 是否启用双视图处理
        """
        self.split = split
        self.dual_view = dual_view
        self.window_size = WINDOW_SIZE
        self.num_classes = NUM_CLASSES
        self.feature_dim = get_feature_dim()

        # 语料池(单例)
        self.corpus_pool = get_corpus()
        print(f"[{split}] 语料池: {len(self.corpus_pool)}条")

        # 样本索引: [(class_id, sample_idx), ...]
        self._build_index()

        # 缓存路径
        self.cache_dir = os.path.join(DATA_DIR, f"cache_{split}")
        os.makedirs(self.cache_dir, exist_ok=True)

    def _build_index(self):
        """构建样本索引"""
        rng = np.random.RandomState(SEED)

        # 确定每个split的样本范围
        n_test = int(SAMPLES_PER_CLASS * TEST_RATIO)
        n_val = int(SAMPLES_PER_CLASS * VAL_RATIO)
        n_train = SAMPLES_PER_CLASS - n_test - n_val

        if self.split == 'train':
            self.per_class = n_train
        elif self.split == 'val':
            self.per_class = n_val
        else:
            self.per_class = n_test

        self.index = []
        for cid in range(NUM_CLASSES):
            # 每个split使用不同的seed偏移以保证数据独立
            offset = {'train': 0, 'val': n_train, 'test': n_train + n_val}[self.split]
            for sid in range(self.per_class):
                self.index.append((cid, offset + sid))

        self.total_samples = len(self.index)

    def __len__(self):
        return self.total_samples

    def _generate_sample(self, class_id: int, sample_id: int):
        """生成单个样本 + 元数据"""
        import hashlib
        class_name = CLASS_NAMES[class_id]

        # 为每个样本设置确定性随机状态(确保可复现)
        gen_seed = SEED * 10000 + class_id * 1000 + sample_id
        random.seed(gen_seed)
        np.random.seed(gen_seed)

        generator = GENERATORS.get(class_name)
        if generator is None:
            raise ValueError(f"Unknown generator: {class_name}")

        # 无头增广仅在训练集生效：验证/测试集保留完整文件头（协议见论文 §3.2）。
        import data.generators as gen_mod
        saved_headless = getattr(gen_mod, 'HEADLESS_PROB', None)
        gen_mod.HEADLESS_PROB = HEADLESS_PROB if self.split == 'train' else 0.0

        # 按生成器签名判断是否传入语料池；生成失败显式报错，
        # 保证每个样本都来自其声明的算法实现。
        try:
            gen_sig = generator.__code__.co_varnames[:generator.__code__.co_argcount]
            if 'pool' in gen_sig or 'corpus_pool' in gen_sig:
                raw = generator(self.corpus_pool)
            else:
                raw = generator()
        except Exception as e:
            raise RuntimeError(
                f"样本生成失败 class={class_name} class_id={class_id} "
                f"sample_id={sample_id}: {e}") from e
        finally:
            if saved_headless is not None:
                gen_mod.HEADLESS_PROB = saved_headless

        # 元数据
        raw_length = len(raw)
        raw_sha256 = hashlib.sha256(raw).hexdigest()

        # 统一截取/填充到窗口大小
        if raw_length < self.window_size:
            data = raw + b'\x00' * (self.window_size - raw_length)
            zero_padding = self.window_size - raw_length
            window_offset = 0
        else:
            # 从随机位置截取(使用确定性seed)
            rng = random.Random(gen_seed)
            start = rng.randint(0, len(raw) - self.window_size)
            data = raw[start:start + self.window_size]
            zero_padding = 0
            window_offset = start

        # 元数据
        metadata = {
            'class_id': class_id,
            'class_name': class_name,
            'sample_id': sample_id,
            'gen_seed': gen_seed,
            'raw_length': raw_length,
            'raw_sha256': raw_sha256,
            'window_size': self.window_size,
            'window_offset': window_offset,
            'zero_padding_bytes': zero_padding,
            'data_sha256': hashlib.sha256(data).hexdigest()
        }

        # 字节数组
        data_arr = np.frombuffer(data, dtype=np.uint8).astype(np.float32) / 255.0

        return data_arr, class_id, metadata

    def _get_cached_path(self, class_id: int, sample_id: int):
        return os.path.join(self.cache_dir, f"{class_id}_{sample_id}.pkl")

    def __getitem__(self, idx):
        class_id, sample_id = self.index[idx]
        cache_path = self._get_cached_path(class_id, sample_id)

        # 读缓存
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                cached = pickle.load(f)
            if isinstance(cached, dict):
                if 'metadata' not in cached:
                    cached['metadata'] = {}
                if 'features' not in cached:
                    raw_bytes = (cached['raw'].squeeze(0).numpy() * 255).astype(np.uint8).tobytes()
                    cached['features'] = torch.from_numpy(
                        extract_full_features(raw_bytes, dual_view=self.dual_view)).float()
                return cached

        # 未命中缓存 → 生成
        data_arr, label, metadata = self._generate_sample(class_id, sample_id)
        feature_vec = extract_full_features(
            (data_arr * 255).astype(np.uint8).tobytes(), dual_view=self.dual_view)

        result = {
            'raw': torch.from_numpy(data_arr).float().unsqueeze(0),
            'features': torch.from_numpy(feature_vec).float(),
            'label': torch.tensor(label, dtype=torch.long),
            'class_name': CLASS_NAMES[label],
            'metadata': metadata,
        }

        # 写缓存（含特征，避免每个epoch重复计算170维统计特征）
        cache_data = {'raw': result['raw'], 'label': result['label'],
                      'class_name': result['class_name'], 'metadata': metadata,
                      'features': result['features']}
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            # 缓存写失败仅告警：样本仍返回，后续 epoch 重新生成
            print(f"[warn] 缓存写入失败 {cache_path}: {e}")

        return result

    def get_class_weights(self) -> torch.Tensor:
        """返回类别权重(平衡数据集，所有类权重均为1)"""
        return torch.ones(NUM_CLASSES)

    def get_category_group(self, class_id: int) -> str:
        """返回类所属的大类组名"""
        for group_name, ids in CATEGORY_GROUPS.items():
            if class_id in ids:
                return group_name
        return "unknown"


class CachedCipherDataset(CipherDataset):
    """
    预缓存的Dataset — 首次遍历后全部缓存到磁盘
    避免每个epoch重新生成加密/压缩数据
    """

    def preload_all(self):
        """预加载所有样本到磁盘缓存。

        全部样本逐一生成并缓存；训练开始后只读缓存，
        避免 DataLoader 多 worker 并发生成同一样本的写竞争。
        """
        print(f"[{self.split}] 预加载 {self.total_samples} 个样本...")
        for idx in tqdm(range(self.total_samples)):
            self.__getitem__(idx)
        print(f"[{self.split}] 预加载完成")


if __name__ == "__main__":
    # 快速测试
    ds = CipherDataset(split='train')
    print(f"数据集大小: {len(ds)}")
    sample = ds[0]
    print(f"Raw shape: {sample['raw'].shape}")
    print(f"Features shape: {sample['features'].shape}")
    print(f"Label: {sample['label']} ({sample['class_name']})")
