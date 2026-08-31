#!/usr/bin/env python3
"""随机填充"训练变体"（与评估侧探针对照）。
训练时把训练与验证样本的尾部零填充区替换为随机字节（数据加载时变换，
元数据 zero_padding_bytes 精确定位）；测试保持原样，另加随机填充测试对照。
验证集与训练集同分布（随机填充机制一致）。
评估：
  (a) 零填充测试集（分布内）
  (b) 随机填充测试集（与主实验 random_padding_eval 相同的测试变换）
结果文件: results2/random_padding_train.json
"""
import os, sys, json
sys.path.insert(0, '/root/cipherbench')
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import accuracy_score, f1_score
import warnings
warnings.filterwarnings('ignore')

from config import *
from data.dataset import CachedCipherDataset
from models.cnn import MultiChannelCNN
from train import set_seed, train_cnn, get_predictions


class RandPadDataset(Dataset):
    """加载时把尾部零填充替换为随机字节（种子固定保证可复现）。"""
    def __init__(self, base, rand_pad=True, seed=1234):
        self.base = base
        self.rand_pad = rand_pad
        self.rng = np.random.RandomState(seed)

    def __len__(self):
        return len(self.base)

    def __getitem__(self, i):
        item = dict(self.base[i])
        if not self.rand_pad:
            return item
        zp = item['metadata'].get('zero_padding_bytes', 0)
        if zp > 0:
            raw = item['raw'].clone()
            pad = torch.from_numpy(
                self.rng.randint(0, 256, size=(zp,), dtype=np.uint8)
            ).float() / 255.0
            raw[0, -zp:] = pad
            item['raw'] = raw
        return item


def eval_model(model, loader):
    preds, labels, _ = get_predictions(model, loader, 'cnn')
    acc = float(accuracy_score(labels, preds))
    f1 = float(f1_score(labels, preds, average='macro', zero_division=0))
    return acc, f1


def main():
    set_seed(42)
    train_base = CachedCipherDataset('train', dual_view=True)
    val_base = CachedCipherDataset('val', dual_view=True)
    test_base = CachedCipherDataset('test', dual_view=True)
    train_base.preload_all(); val_base.preload_all(); test_base.preload_all()

    train_ds = RandPadDataset(train_base, rand_pad=True)
    val_ds = RandPadDataset(val_base, rand_pad=True, seed=999)
    tl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    vl = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)

    model = MultiChannelCNN(num_classes=NUM_CLASSES)
    model, hist = train_cnn(model, tl, vl, 'round2_randpad_train',
                            epochs=EPOCHS, patience=EARLY_STOP_PATIENCE, save=False)
    best_ep = int(np.argmin(hist['val_loss'])) + 1

    # 评估 (a) 零填充测试
    el0 = DataLoader(test_base, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)
    acc0, f10 = eval_model(model, el0)
    # 评估 (b) 随机填充测试（与主实验相同变换，固定种子）
    test_rand = RandPadDataset(test_base, rand_pad=True, seed=777)
    el1 = DataLoader(test_rand, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)
    acc1, f11 = eval_model(model, el1)

    # 逐大类
    preds0, labels0, _ = get_predictions(model, el0, 'cnn')
    preds1, labels1, _ = get_predictions(model, el1, 'cnn')
    per_cat = {}
    for cat, ids in CATEGORY_GROUPS.items():
        m0 = [p == l for p, l in zip(preds0, labels0) if l in ids]
        m1 = [p == l for p, l in zip(preds1, labels1) if l in ids]
        per_cat[cat] = {
            'zero_pad_test': round(float(np.mean(m0)) * 100, 2) if m0 else None,
            'rand_pad_test': round(float(np.mean(m1)) * 100, 2) if m1 else None}

    per_class_rand = {}
    for c in range(NUM_CLASSES):
        m1c = [p == l for p, l in zip(preds1, labels1) if l == c]
        per_class_rand[CLASS_NAMES[c]] = round(float(np.mean(m1c)) * 100, 2) if m1c else None
    out = {'train': 'random-padded zero regions (per-sample CSPRNG bytes)',
           'zero_pad_test_acc': round(acc0, 4), 'zero_pad_test_f1': round(f10, 4),
           'rand_pad_test_acc': round(acc1, 4), 'rand_pad_test_f1': round(f11, 4),
           'best_epoch': best_ep, 'per_category': per_cat,
           'per_class_rand_pad_test': per_class_rand,
           'note': '训练时零填充区替换为随机字节；与主实验评估侧探针对照；'}
    torch.save({'state_dict': model.state_dict(), 'history': hist},
               os.path.join(MODEL_DIR, 'randpad_train_seed42.pt'))
    os.makedirs('/root/cipherbench/results2', exist_ok=True)
    with open('/root/cipherbench/results2/random_padding_train.json', 'w') as f:
        json.dump(out, f, indent=2, default=float)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
