"""
PyTorch Dataset — SM4多库实现指纹数据集
"""
import os
import pickle
import numpy as np
import torch
from torch.utils.data import Dataset
from tqdm import tqdm
from config import *
from generators import generate_sm4_samples, generate_aes_samples


class SM4LibraryDataset(Dataset):
    """SM4实现指纹数据集

    每个样本 = 某库×某模式产生的密文
    标签 = 库的索引 (0-4)

    关键设计: 所有库使用相同的(明文,密钥,IV)序列
    确保任何可检测的差异来自实现而非输入
    """

    def __init__(self, task="sm4_cbc", split="train", modes=None):
        """
        Args:
            task: "sm4_cbc" | "sm4_ctr" | "sm4_gcm" | "sm4_all" | "aes_cbc"
            split: "train" | "val" | "test"
            modes: 可选，显式指定该任务包含的模式列表（如 ['cbc','ctr']），
                   用于跨模式联合任务；None 时按任务名解析
        """
        self.task = task
        self.split = split
        self.window_size = WINDOW_SIZE

        # 解析任务
        if task.startswith("sm4"):
            self.algorithm = "sm4"
            if modes is not None:
                self.modes = list(modes)
            elif task == "sm4_all":
                self.modes = SM4_MODES
            else:
                self.modes = [task.split("_")[1]]
            self.libs = [k for k in LIBRARIES if LIBRARIES[k]["sm4_supported"]]
        elif task.startswith("aes"):
            self.algorithm = "aes"
            self.modes = list(modes) if modes is not None else [task.split("_")[1]]
            self.libs = [k for k in LIBRARIES if LIBRARIES[k]["aes_supported"]]
        else:
            raise ValueError(f"Unknown task: {task}")

        self.num_libs = len(self.libs)
        self.total_per_config = SAMPLES_PER_CONFIG
        self.samples_per_lib_mode = SAMPLES_PER_CONFIG

        # 划分索引
        rng = np.random.RandomState(SEED)
        n_total = self.total_per_config
        indices = rng.permutation(n_total)
        n_test = int(n_total * TEST_RATIO)
        n_val = int(n_total * VAL_RATIO)
        n_train = n_total - n_test - n_val

        if split == "train":
            self.indices = indices[:n_train]
        elif split == "val":
            self.indices = indices[n_train:n_train + n_val]
        else:
            self.indices = indices[n_train + n_val:]

        # 数据缓存
        self._cache = {}
        self._load_data()

    def _load_data(self):
        """加载或生成数据，并按实际可用性过滤库。

        实现说明：
        未生成出数据的 (库, 模式) 组合不进入样本集（缺失数据显式报错）。
        b'\\x00'*1024 全零样本会让分类器仅凭识别全零类获得虚高准确率，
        因此数据集遵循以下两条约束：
        - 生成失败/不支持的组合直接过滤掉，不进入数据集；
        - 缺失数据即报错（不产生静默回退的伪影）。
        """
        cache_file = os.path.join(DATA_DIR, f"{self.task}_{self.split}.pkl")
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                self._cache = pickle.load(f)
        else:
            print(f"  [{self.task}/{self.split}] 生成数据...")
            for lib_key in tqdm(self.libs, desc=f"  {self.split}"):
                for mode in self.modes:
                    config_name = f"{lib_key}_{mode}"
                    if self.algorithm == "sm4":
                        samples = generate_sm4_samples(lib_key, mode, self.total_per_config)
                    else:
                        samples = generate_aes_samples(lib_key, mode, self.total_per_config)
                    self._cache[config_name] = samples

            with open(cache_file, 'wb') as f:
                pickle.dump(self._cache, f)

        # ── 按实际数据可用性过滤库：只保留在该任务所有模式上都有数据的库 ──
        libs_with_data = []
        for lib_key in self.libs:
            if all(len(self._cache.get(f"{lib_key}_{mode}", [])) > 0
                   for mode in self.modes):
                libs_with_data.append(lib_key)
        dropped = [k for k in self.libs if k not in libs_with_data]
        if dropped:
            print(f"  [{self.task}] 过滤掉无数据/不支持的库: {dropped}")
        self.libs = libs_with_data
        self.num_libs = len(self.libs)

        if self.num_libs < 2:
            raise ValueError(
                f"任务 {self.task} 可用库 < 2（只有 {self.libs}），"
                f"跨库分类不可行，跳过该任务")

    def __len__(self):
        return len(self.indices) * self.num_libs * len(self.modes)

    def __getitem__(self, idx):
        # 展开: (sample_idx, lib_idx, mode_idx)
        n_per_mode_lib = len(self.indices)
        lib_idx = idx // (n_per_mode_lib * len(self.modes))
        remainder = idx % (n_per_mode_lib * len(self.modes))
        mode_idx = remainder // n_per_mode_lib
        sample_local_idx = remainder % n_per_mode_lib
        sample_global_idx = self.indices[sample_local_idx]

        lib_key = self.libs[lib_idx]
        mode = self.modes[mode_idx]
        config_name = f"{lib_key}_{mode}"

        cache_samples = self._cache.get(config_name, [])
        n_available = len(cache_samples)
        if n_available == 0:
            # 缺失数据显式报错，不用兜底样本
            raise RuntimeError(
                f"config {config_name} 无数据——数据集构建逻辑错误，请检查生成器")

        safe_idx = sample_global_idx % n_available
        ct, iv, key, pt = cache_samples[safe_idx]
        if len(ct) < self.window_size:
            data = ct + b'\x00' * (self.window_size - len(ct))
        else:
            offset = safe_idx % max(1, len(ct) - self.window_size)
            data = ct[offset:offset + self.window_size]

        raw = torch.tensor(np.frombuffer(data, dtype=np.uint8), dtype=torch.float32) / 255.0
        raw = raw.unsqueeze(0)  # [1, 1024]
        label = lib_idx  # 只预测库, 不预测模式
        return {'raw': raw, 'label': label,
                'lib': lib_key, 'mode': mode, 'lib_idx': lib_idx}


# ══════════════════════════════════════════════════════
# 多任务变体: 预测(库, 模式)联合标签
# ══════════════════════════════════════════════════════

class SM4LibraryModeDataset(SM4LibraryDataset):
    """同时预测库和模式 (n_libs × n_modes 分类)。

    实现说明：联合任务只包含所有库都支持的模式
    （SM4 为 cbc/ctr；gcm 仅 cryptography 支持，不进入联合网格），
    通过 __init__ 的 modes 参数传入，避免 (库,模式) 网格出现空洞。
    """

    def __getitem__(self, idx):
        item = super().__getitem__(idx)
        mode_idx = self.modes.index(item['mode'])
        item['label'] = item['lib_idx'] * len(self.modes) + mode_idx
        return item
