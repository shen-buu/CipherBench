# v2 实验结果清单（修正数据上的全部实验）

- `A_main_{model}_{seed}.json` / `B_main_transformer_{seed}.json`：5 模型 × 5 种子主结果（表3 与图1 数据源）；
- `A_headless_ab_fixed.json`：无头增广 A/B（表5/表7/图4/图5 数据源）；
- `A_performat_confusion.json`：逐格式混淆矩阵（补充材料表 S1）；
- `A_non_fragmented_baseline_fixed.json`：校准实验（表2）；
- `A_ablation_fixed.json` + `B_ablate_{no_fft,no_diff}_{42,123,456}.json`：消融（表6）；
- `A_random_padding_eval.json` + `B_random_padding_train.json`：随机填充评估侧与训练侧（§4.4）；
- `A_nist_analysis_fixed.json`：NIST 重标注（§4.5/图3）；
- `A_r1m7_distance_analysis.json`：无头机制距离与 t-SNE 坐标（§4.8/图 S1）；
- `B_category_classifiers.json`：专用 7/18/8/6 类分类器（§4.3）；
- `B_scaling_curves.json`：规模曲线（§4.11/图6）；
- `{A,B}_corpus_split_{1..10}.json`：语料 10 分区（表8）；
- `checkpoints_A_v2.tar.gz` / `checkpoints_B_v2.tar.gz`：训练权重（复现评估用）。

数据缓存（修正后压缩类）见 `../04_Data/cache_corrected_v2.tar.gz`。
