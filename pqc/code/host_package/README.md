# CipherBench-PQC 主机运行包（波次 3.2 基线）

## 一、主机准备（一次性）

```bash
# 1. 把本目录整体拷贝到主机（含 statistical.py）
# 2. 安装依赖（仅需这些：torch/numpy/scipy/sklearn——主机不需要 liboqs/openssl/oqs-provider！）
pip install -r requirements.txt
# 3. 拷贝数据集：解包 data_formal.tar.gz 到任意路径（本机已生成 34 类 × 300 = 10,200 对象，
#    主机只跑训练、不生成数据，因此无需任何密码学库与编译器）
tar xzf data_formal.tar.gz
```

**关键澄清**：主机任务（3.2 基线）是**纯训练**——数据集在本机（Linux + liboqs + oqs-provider）已生成完毕，
主机只需要 torch/sklearn 读数据跑模型。MinGW openssl / 无 gcc / 无 liboqs 都不影响训练。

## 二、运行方式

```bash
# 冒烟（每类 20 样本，CPU，~1 分钟）
python3 train_baselines.py --data ./data --arch rf --scene len --device cpu --smoke

# 单组（示例：CNN + P1 窗口协议，GPU）
python3 train_baselines.py --data ./data --arch cnn --scene p1 --device cuda

# 全矩阵（4 架构 × 3 场景 × 5 种子 = 60 组；预计 30-60 GPU 时）
python3 train_baselines.py --data ./data --arch all --scene all --device cuda
```

断点制：`results/{arch}_{scene}_seed{seed}.json` 存在即跳过，中断后重跑同一命令自动续。
**组级跑**（--groups 子集）文件名带组后缀：`results/{arch}_{scene}_seed{seed}_g_prim.json`（prim/pk8/crt），与混合跑互不覆盖。

## 三、协议与口径（v2.2 冻结，与论文一致）

- **P1**：1024B 随机偏移等长裁剪；**短对象（<1024B）置于窗口内均匀随机位置，其余随机填充（禁零填充）**——防止位置锚定泄漏，保持『碎片来自任意位置』语义——C_bytes 信道；
- **P2**：头部 1024B 定长窗口；短对象锚定位置 0 + 随机填充——C_struct 信道（S1 擦除实验另用 exp_s1.py）；
- **LEN**：对象级长度单特征（1-NN）——C_len 信道；
- 架构：RF/HistGB（stats 特征）、CNN/BiLSTM（raw 字节）；
- **E8**：每种子独立窗口 rng（种子列表 [42,123,2024,7,99]）；
- **E14**：汇报 macro-F1 ± 种子 std（括号 SE）；对照类实验另报实现间 std；
- 输出字段：macro_f1 / per_class_f1 / confusion / n_classes / sec。

## 四、后续实验（本机已跑通，随数据集交付）

- `exp_s1.py`：S1 擦除/截断 11 条件梯度（P2 协议，RF）；
- `exp_s2s3.py`：S2 外层加密保真度 + S3 粗粒度化 β(G) 阶梯（条件基线三列，E6）；
- `exp_b4_pqclean.py`：PQClean 直证腿（必做，3.5）。

## 五、预期结果核对锚（本机波次 2 已测）

- LEN 场景组级折叠精度 ≈ 1.0；P1 场景宏 F1 ≈ 随机（置换零带内）；S1 intact ≈ 1.0、head48 ≈ 0.87。
- 若主机结果与锚偏离 >2σ：先查代码（准则 0），再回传对比。
