#!/usr/bin/env python3
"""v2 消融多种子补跑：no_fft / no_diff × seeds 42/123/456。
结果：results2/v2/ablate_{variant}_{seed}.json；full 引用新主结果。
"""
import os, sys, json, argparse, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import torch
from torch.utils.data import DataLoader
from sklearn.metrics import accuracy_score, f1_score
from config import *
from data.dataset import CachedCipherDataset
from train import set_seed, train_cnn, get_predictions
from ablation_fixed import NoFFT, NoDiff

MODELS = {'no_fft': NoFFT, 'no_diff': NoDiff}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', required=True, choices=['no_fft', 'no_diff'])
    ap.add_argument('--seed', type=int, required=True)
    args = ap.parse_args()

    set_seed(args.seed)
    train_ds = CachedCipherDataset('train', dual_view=True)
    val_ds = CachedCipherDataset('val', dual_view=True)
    test_ds = CachedCipherDataset('test', dual_view=True)
    train_ds.preload_all(); val_ds.preload_all(); test_ds.preload_all()
    tl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    vl = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)
    el = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)

    model = MODELS[args.variant](num_classes=NUM_CLASSES)
    model, hist = train_cnn(model, tl, vl, f'ablate_{args.variant}_{args.seed}',
                            epochs=EPOCHS, patience=EARLY_STOP_PATIENCE, save=False)
    preds, labels, _ = get_predictions(model, el, 'cnn')
    result = {
        'variant': args.variant, 'seed': args.seed,
        'test_acc': float(accuracy_score(labels, preds)),
        'test_macro_f1': float(f1_score(labels, preds, average='macro', zero_division=0)),
        'best_epoch': int(np.argmin(hist['val_loss'])) + 1,
    }
    out = f'results2/v2/ablate_{args.variant}_{args.seed}.json'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(result, f, indent=2, default=float)
    print(f"{args.variant} seed{args.seed} acc={result['test_acc']*100:.2f}% -> {out}", flush=True)


if __name__ == "__main__":
    main()
