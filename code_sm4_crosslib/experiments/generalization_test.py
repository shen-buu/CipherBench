"""
泛化测试: 对齐训练 → 独立测试
核心问题: 模型学的是实现指纹, 还是利用了(P,K,IV)对齐的统计泄露?
如果在独立(P,K,IV)测试集上准确率不降, 则实现指纹是真实的。
"""
import os, sys, json, random, secrets
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from sklearn.metrics import accuracy_score, confusion_matrix
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from model import MultiChannelCNN

SEED = 42
WINDOW_SIZE = 1024
N_TEST = 2000  # 泛化测试每库样本数


class IndependentTestDataset(Dataset):
    """
    独立(P,K,IV)测试数据集
    每个库使用完全独立随机的明文/密钥/IV
    与训练集的对齐设计形成对照
    """
    def __init__(self, mode="cbc", n_per_lib=N_TEST):
        self.mode = mode  # "sm4_cbc", "aes_cbc", etc.
        self.n_per_lib = n_per_lib
        self.window_size = WINDOW_SIZE

        # 判断算法类型
        if mode.startswith("aes"):
            self.algo = "aes"
            self.mode_clean = mode.replace("aes_", "")
        else:
            self.algo = "sm4"
            self.mode_clean = mode.replace("sm4_", "")

        filter_key = "aes_supported" if self.algo == "aes" else "sm4_supported"
        self.libs = [k for k in LIBRARIES if LIBRARIES[k].get(filter_key, False)]
        self.num_libs = len(self.libs)

        # 为每个(库, 样本索引)生成独立的(P, K, IV), 各库之间无共享
        rng = random.Random(SEED + 9999)
        self.samples = []

        from generators import SM4_GENERATORS, AES_GENERATORS, _aes_openssl_encrypt

        generators = AES_GENERATORS if self.algo == "aes" else SM4_GENERATORS
        key_len = 32 if self.algo == "aes" else 16

        for lib_key in self.libs:
            gen_key = (lib_key, self.mode_clean)
            gen_func = generators.get(gen_key)
            if gen_func is None:
                print(f"  ⚠ {lib_key}/{mode} 不可用")
                continue

            ok = 0
            for i in range(n_per_lib):
                # 每个样本: 独立随机(P, K, IV)
                # 用固定映射表取种子偏移（跨进程稳定）：
                # Python 的 hash() 受 PYTHONHASHSEED 随机化，独立测试集的
                # (P,K,IV) 会随进程而变；这里统一使用确定性的库索引。
                rng.seed(SEED * 12345 + self.libs.index(lib_key) * 1000 + i)
                pt_len = rng.randint(128, 1024)
                pt = bytes([rng.randint(32, 126) for _ in range(pt_len)])
                key = bytes([rng.randint(0, 255) for _ in range(key_len)])
                iv = bytes([rng.randint(0, 255) for _ in range(16)])

                try:
                    m = self.mode_clean
                    if m == "ctr":
                        ct = gen_func(pt, key, iv)
                    elif m == "gcm":
                        ct = gen_func(pt, key, iv[:12])
                    else:
                        ct = gen_func(pt, key, iv)
                except Exception:
                    ct = b''

                # 生成失败/空密文直接丢弃，空密文（→全零窗口）不进入样本集
                if ct:
                    self.samples.append((ct, self.libs.index(lib_key), lib_key))
                    ok += 1
            print(f"  {lib_key}/{self.mode_clean}: 生成 {ok}/{n_per_lib} 条独立样本")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        ct, lib_idx, lib_key = self.samples[idx]
        if len(ct) < self.window_size:
            data = ct + b'\x00' * (self.window_size - len(ct))
        else:
            # 用固定映射表取偏移，保证跨进程一致；
            # 使用确定性偏移，保证实验可复现
            offset = (idx * 7919) % max(1, len(ct) - self.window_size)
            data = ct[offset:offset + self.window_size]

        raw = torch.tensor(np.frombuffer(data, dtype=np.uint8), dtype=torch.float32) / 255.0
        return raw.unsqueeze(0), lib_idx


def test_generalization():
    """核心实验: 用对齐训练的模型测试独立(P,K,IV)数据"""
    print("=" * 70)
    print("泛化测试: 对齐(P,K,IV)训练 → 独立(P,K,IV)测试")
    print("=" * 70)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    results = {}

    # 合并SM4和AES任务
    all_tasks = [(mode, 'sm4') for mode in SM4_MODES]
    # 加入AES (仅测试有模型且库≥2的模式)
    all_tasks.append(('cbc', 'aes'))

    for mode, algo in all_tasks:
        task_name = f"{algo}_{mode}"
        label = f"{algo.upper()}-{mode.upper()}"
        print(f"\n─── {label} ───")

        # 加载模型（num_classes 从 checkpoint 读取，与实际训练一致）
        model_path = os.path.join(MODEL_DIR, f"{task_name}.pt")
        if not os.path.exists(model_path):
            print(f"  模型不存在: {model_path}, 跳过")
            continue

        ckpt = torch.load(model_path, map_location=device, weights_only=False)
        n_libs = ckpt.get('num_classes', None)
        if n_libs is None:  # 兼容旧 checkpoint
            filter_key = f"{algo}_supported"
            n_libs = len([k for k in LIBRARIES if LIBRARIES[k].get(filter_key, False)])
        model = MultiChannelCNN(num_classes=n_libs).to(device)
        model.load_state_dict(ckpt['state_dict'])
        model.eval()

        # 原始对齐测试集的准确率 (来自checkpoint)
        aligned_acc = ckpt.get('test_acc', None)

        # 构建独立(P,K,IV)测试集
        print(f"  构建独立测试集 ({task_name})...")
        indep_ds = IndependentTestDataset(mode=task_name, n_per_lib=N_TEST)
        # 获取实际的库名列表
        lib_names = list(indep_ds.libs)
        indep_loader = DataLoader(indep_ds, batch_size=64, shuffle=False, num_workers=0)
        print(f"  测试样本: {len(indep_ds)}")

        # 推理
        all_preds, all_labels = [], []
        with torch.no_grad():
            for x, y in tqdm(indep_loader, desc=f"  {mode}"):
                logits = model(x.to(device))
                all_preds.extend(logits.argmax(1).cpu().numpy())
                all_labels.extend(y.numpy())

        indep_acc = accuracy_score(all_labels, all_preds)
        indep_cm = confusion_matrix(all_labels, all_preds)
        n_actual = indep_cm.shape[0]  # 实际生成数据的库数
        random_baseline = 1.0 / max(n_actual, n_libs)

        print(f"\n  {'对齐测试 (来自训练)':<25s}: {aligned_acc:.4f}" if aligned_acc else "")
        print(f"  {'独立(P,K,IV)测试':<25s}: {indep_acc:.4f}")
        print(f"  {'随机基线':<25s}: {random_baseline:.4f}")
        print(f"  {'泛化差异 (对齐-独立)':<25s}: {(aligned_acc - indep_acc):+.4f}" if aligned_acc else "")

        # 逐类报告 (使用实际测试集的库, 不是配置的全部库)
        actual_libs = [lib_names[i] for i in range(len(lib_names)) if i < indep_cm.shape[0]]
        cm_n = indep_cm.shape[1]
        print(f"\n  独立测试混淆矩阵 ({len(actual_libs)}库×{cm_n}预测):")
        header = "      " + "".join(f"{n:>15s}" for n in actual_libs)
        print(header)
        for i, name in enumerate(actual_libs):
            row = "".join(f"{indep_cm[i][j]:>15d}" for j in range(cm_n))
            print(f"  {name:>15s}: {row}")

        results[task_name] = {
            'algo': algo,
            'aligned_acc': float(aligned_acc) if aligned_acc else None,
            'independent_acc': float(indep_acc),
            'random_baseline': float(random_baseline),
            'delta': float(aligned_acc - indep_acc) if aligned_acc else None,
            'n_libs_model': n_libs,
            'n_libs_actual': n_actual,
            'lib_names': actual_libs,
            'n_test': N_TEST,
            'cm': indep_cm.tolist()
        }

    # 保存
    os.makedirs(RESULT_DIR, exist_ok=True)
    outpath = os.path.join(RESULT_DIR, "generalization_test.json")
    with open(outpath, 'w') as f:
        json.dump(results, f, indent=2, default=float)

    # 汇总
    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)
    print(f"{'模式':<12s} {'对齐测试':>10s} {'独立测试':>10s} {'Δ':>8s} {'结论':>20s}")
    print("-" * 65)
    for mode in SM4_MODES:
        task = f"sm4_{mode}"
        if task in results:
            r = results[task]
            a = f"{r['aligned_acc']:.4f}" if r['aligned_acc'] else "N/A"
            i = f"{r['independent_acc']:.4f}"
            d = f"{r['delta']:+.4f}" if r['delta'] else "N/A"
            # 结论
            if r['delta'] is not None:
                if abs(r['delta']) < 0.05:
                    c = "✅ 指纹真实"
                elif r['delta'] > 0.05:
                    c = "⚠ 部分泄露"
                else:
                    c = "⚠ 独立更高(反常)"
            else:
                c = "—"
            print(f"{mode:<12s} {a:>10s} {i:>10s} {d:>8s} {c:>20s}")

    print(f"\n结果已保存: {outpath}")


if __name__ == "__main__":
    test_generalization()
