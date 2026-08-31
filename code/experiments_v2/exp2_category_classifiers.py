#!/usr/bin/env python3
"""R1M4 三层任务报告 — 专用模型版：
(1) 7类"类别识别"模型（50类数据标签折叠为大类）
(2) 18类"对称加密类内算法识别"模型（只含对称样本）
(3) 8类"压缩类内格式识别"模型
(4) 6类"非对称类内算法识别"模型
配合已有 50 类主模型（表3）构成三层报告：大类/类内/全50类。
全部复用现有缓存（1024窗口），不重新生成数据。
"""
import os, sys, json
sys.path.insert(0, '/root/cipherbench')
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
import warnings
warnings.filterwarnings('ignore')

from config import *
from data.dataset import CachedCipherDataset
from models.cnn import MultiChannelCNN
from train import set_seed, train_cnn, get_predictions


class RemapDataset(Dataset):
    """按 label_map 重映射标签（cid_list 决定保留哪些类）。"""
    def __init__(self, base, cid_list, label_map):
        self.base = base
        self.label_map = label_map
        self.idx = [i for i in range(len(base))
                    if int(base[i]['label']) in set(label_map)]

    def __len__(self):
        return len(self.idx)

    def __getitem__(self, i):
        item = dict(self.base[self.idx[i]])
        item['label'] = torch.tensor(
            self.label_map[int(item['label'])], dtype=torch.long)
        return item


def run(task_key, cid_list, num_classes, label_map=None):
    set_seed(42)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'\n===== {task_key}: {num_classes}类 =====')
    train_base = CachedCipherDataset('train', dual_view=True)
    val_base = CachedCipherDataset('val', dual_view=True)
    test_base = CachedCipherDataset('test', dual_view=True)
    train_base.preload_all(); val_base.preload_all(); test_base.preload_all()
    if label_map is None:
        label_map = {c: i for i, c in enumerate(cid_list)}
    tr = RemapDataset(train_base, cid_list, label_map)
    va = RemapDataset(val_base, cid_list, label_map)
    te = RemapDataset(test_base, cid_list, label_map)
    print('样本数 train/val/test:', len(tr), len(va), len(te))
    tl = DataLoader(tr, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    vl = DataLoader(va, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)
    el = DataLoader(te, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)
    model = MultiChannelCNN(num_classes=num_classes)
    model, hist = train_cnn(model, tl, vl, f'round2_{task_key}',
                            epochs=EPOCHS, patience=EARLY_STOP_PATIENCE, save=False)
    preds, labels, _ = get_predictions(model, el, 'cnn')
    acc = float(accuracy_score(labels, preds))
    f1 = float(f1_score(labels, preds, average='macro', zero_division=0))
    cm = confusion_matrix(labels, preds, labels=list(range(num_classes))).tolist()
    best_ep = int(np.argmin(hist['val_loss'])) + 1
    out = {'task': task_key, 'num_classes': num_classes,
           'accuracy': round(acc, 4), 'macro_f1': round(f1, 4),
           'cm': cm, 'random_baseline': round(1 / num_classes, 4),
           'best_epoch': best_ep, 'n_test': len(te)}
    print(json.dumps({k: v for k, v in out.items() if k != 'cm'}, indent=1))
    return out


if __name__ == '__main__':
    # 类→大类映射
    cat_of_class = {}
    for cat, ids in CATEGORY_GROUPS.items():
        for c in ids:
            cat_of_class[c] = cat
    all_ids = list(range(50))
    cat_order = ['明文文本', '编码', '哈希', '压缩', '对称加密', '非对称加密', '真随机/对照']
    results = {}

    # (1) 7类大类任务（标签=大类索引）
    cat_map = {c: cat_order.index(cat_of_class[c]) for c in all_ids}
    results['cat7'] = run('cat7', all_ids, 7, label_map=cat_map)

    # (2) 类内任务
    results['symmetric18'] = run('symmetric18', sorted(CATEGORY_GROUPS['对称加密']), 18)
    results['compression8'] = run('compression8', sorted(CATEGORY_GROUPS['压缩']), 8)
    results['asymmetric6'] = run('asymmetric6', sorted(CATEGORY_GROUPS['非对称加密']), 6)

    os.makedirs('/root/cipherbench/results2', exist_ok=True)
    with open('/root/cipherbench/results2/category_classifiers.json', 'w') as f:
        json.dump(results, f, indent=2, default=float)
    print('saved results2/category_classifiers.json')
