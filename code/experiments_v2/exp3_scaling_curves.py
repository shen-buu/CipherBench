#!/usr/bin/env python3
"""R2S1 规模曲线：准确率 vs 每类训练样本数 (100/250/500/700)。
模型：Multi-Channel CNN + GBT（170维统计特征），同协议（早停、seed42）。
数据：现有 1024 窗口缓存，按类分层抽取前 n 个样本索引。
"""
import os, sys, json
sys.path.insert(0, '/root/cipherbench')
import numpy as np
import torch
from torch.utils.data import Subset, DataLoader
from sklearn.metrics import accuracy_score, f1_score
import warnings
warnings.filterwarnings('ignore')

from config import *
from data.dataset import CachedCipherDataset
from models.cnn import MultiChannelCNN
from train import set_seed, train_cnn, train_gbt, get_predictions


def stratified_indices(ds, n_per_class, n_classes=50):
    """每类取前 n_per_class 个样本的全局下标（缓存索引按类连续排列）。"""
    idx = []
    for c in range(n_classes):
        pos = [i for i in range(len(ds)) if int(ds[i]['label']) == c]
        idx.extend(pos[:n_per_class])
    return idx


def main():
    set_seed(42)
    train_base = CachedCipherDataset('train', dual_view=True)
    val_base = CachedCipherDataset('val', dual_view=True)
    test_base = CachedCipherDataset('test', dual_view=True)
    train_base.preload_all(); val_base.preload_all(); test_base.preload_all()
    val_loader = DataLoader(val_base, batch_size=BATCH_SIZE, shuffle=False,
                            num_workers=2)
    test_loader = DataLoader(test_base, batch_size=BATCH_SIZE, shuffle=False,
                             num_workers=2)
    results = {}
    for n_per in [100, 250, 500, 700]:
        print(f'\n===== n_per_class = {n_per} =====')
        idx = stratified_indices(train_base, n_per)
        sub = Subset(train_base, idx)
        tl = DataLoader(sub, batch_size=BATCH_SIZE, shuffle=True,
                        num_workers=2)

        # GBT（170维特征，CPU 快）
        gbt_model, gbt_res = train_gbt(tl, val_loader)
        gbt_preds, gbt_labels, _ = get_predictions(gbt_model, test_loader, 'xgboost')
        gbt_acc = float(accuracy_score(gbt_labels, gbt_preds))
        gbt_f1 = float(f1_score(gbt_labels, gbt_preds, average='macro', zero_division=0))
        print(f'GBT acc={gbt_acc:.4f} f1={gbt_f1:.4f}')

        # MC-CNN
        model = MultiChannelCNN(num_classes=NUM_CLASSES)
        model, hist = train_cnn(model, tl, val_loader, f'round2_scale{n_per}',
                                epochs=EPOCHS, patience=EARLY_STOP_PATIENCE, save=False)
        preds, labels, _ = get_predictions(model, test_loader, 'cnn')
        mc_acc = float(accuracy_score(labels, preds))
        mc_f1 = float(f1_score(labels, preds, average='macro', zero_division=0))
        best_ep = int(np.argmin(hist['val_loss'])) + 1
        print(f'MC-CNN acc={mc_acc:.4f} f1={mc_f1:.4f} best_ep={best_ep}')
        results[str(n_per)] = {
            'n_train': len(idx), 'gbt_acc': round(gbt_acc, 4),
            'gbt_f1': round(gbt_f1, 4), 'mc_acc': round(mc_acc, 4),
            'mc_f1': round(mc_f1, 4), 'mc_best_epoch': best_ep}
    os.makedirs('/root/cipherbench/results2', exist_ok=True)
    with open('/root/cipherbench/results2/scaling_curves.json', 'w') as f:
        json.dump(results, f, indent=2, default=float)
    print('saved results2/scaling_curves.json')
    print(json.dumps(results, indent=1))


if __name__ == '__main__':
    main()
