# CipherBench-PQC 审计日志（63 案例，公开随稿发布）

> 编号说明：#1–#18 为开发期案例，编号按本日志重建（本地落盘记录最早见于 #19）；
> #19–#26 沿用既有编号（RESUME.md / host_verification.md / QA_交付报告.md）。
> 每条给出：现象 → 裁定/根因 → 处置 → 证据指针。§3.5 的 "26 documented cases" 以此文件为准。

## #1 窗口 RNG 跨种子共享 → 种子级 SD 虚假收紧（E8 诞生）
- 现象：多种子报告的 ±SD 异常偏小，种子间波动被系统性低估。
- 裁定：窗口抽取的随机源在所有种子上共享同一序列 → 各种子不是独立重复。
- 处置：规范 **E8：per-seed independent window RNG**（每种子独立窗口随机源），± 一律报 seed SD。
- 证据：paper §4.2/§4.5（E8）；§6 加框段 "Anatomy of a frozen number" 第一件事。

## #2 长度信道朴素恒等式与实测差 3×10⁻⁴
- 现象：nn_len 实测 0.926176 与朴素恒等式 0.9265 差 3×10⁻⁴，一度被疑为实现 bug。
- 裁定：差全部来自 784B 近碰撞（rsa2048_cert 3/300 件 784B、297 件 785B），非 bug。
- 处置：恒等式逐位分解写入 §5.3 与 host_verification.md 二·补。
- 证据：host_verification.md 二·补；§5.3 分解式 0.926176=(29×1+0.5+0+0+0.995025+0.994975)/34。

## #3 零填充后门（Bug#3）——填充占比 = 长度代理
- 现象：平铺布局 + 零填充末块时，768B 与 784B 类以填充占比泄漏 16B 长度差，macro-F1 = **0.988 ± 0.002**。
- 裁定：零填充使填充字节与数据字节可区分 → 填充占比成为长度代理信道。
- 处置：P1/P2 一律均匀随机填充，**zero-padding 明文禁止**；0.988 写入 §3.2 作为量化必要性证明。
- 证据：host_verification.md 三·补2（"B4 零填充后门 0.988"）；§3.2。

## #4 平局依赖——exact 级宏均 F1 的平局约定敏感性
- 现象：nn_len 的逐类 F1 在 768B/784B 碰撞位点依赖 1-NN 平局裁决，区间 [0.9262, 0.9409]；
  β(G) 估计器的 50 抽样本均值与期望差 2.8 SE，1.018/1.468 等样本数字无语义可重建。
- 裁定：β 正式定义为 E_T[macro-F1(ĉ_T)]（逐对象独立均匀随机平局）；精确期望 768 位点
  3×0.33352=1.0006、784 位点 0.6647+0.7977=1.4624；E[β]=0.9254；约定最大值 0.9409。
- 处置：§5.3 重写（定义式 + 可复算式子）；脚注改 "convention-wise maximum"。
- 证据：复核报告 §十一；§5.3；§6 加框段第三件事。

## #5 平局计数——长度原子账 34→49→46
- 现象：G=46 与"34 类→49 类长度值"的口径矛盾（49 如何变 46）。
- 裁定：768B 三向碰撞合并 3 类 + 784B 近碰撞合并 2 类 → 49−3=46 原子。
- 处置：§5.3 完整账目（8 个多支撑类贡献 4+6+3+2+2+2+2+2=23 原子 + 26 单原子类 + 2 碰撞位点）。
- 证据：host_verification.md 二·补；§5.3。

## #6 漂移账本——B4 跨规格腿四次迭代 0.557→0.502→0.482→0.494
- 现象：同代码四次冻结运行给出 0.557 → 0.502 → 0.482 → 0.494，期间无任何代码变更；
  当时报告的 SD 虚假收紧（漏掉"抽到哪组实现配对"这一方差源）。
- 裁定：纯实现间抽样噪声；方差桥 = 实现间方差（抽到哪些配对）vs 种子间方差（窗口怎么抽）。
- 处置：B4 腿改报 **between-realization SD**（0.494 ± 0.020，10 realizations）；入 §6 加框段第二件事。
- 证据：§6 加框段；Table 4a。

## #7 ECDSA 0.2508 的填充占比竞争假说（三项排除）
- 现象：ECDSA（69–72B）0.2508 偏离零带，需排除"短对象+随机填充→填充占比=长度代理"解释。
- 排除 1：更短的 Ed25519（64B）F1=0.0713 与均匀类同列（若填充占比是机制，最短类应最亮）；
- 排除 2：长度↔F1 相关 r = −0.186，无梯度，单点 spike；
- 排除 3（构造）：P1 填充为均匀随机字节，与均匀内容统计不可区分。
- 处置：§5.2 写入 Ed25519 对照句；ECDSA 归因确认为 DER 标签内容结构。
- 证据：host_verification.md 三·补2；§5.2。

## #8 双 0.494 巧合——PQClean 窗口腿与跨规格腿同均值（历史记录；2026-09-19 升级至 10 realizations 后巧合消失，见 #27）
- 现象：两条独立实验（PQClean 窗口腿、B4 跨规格腿）都恰好平均 0.494，易被误读为同一数据。
- 裁定：纯巧合；两者逐实现向量不同（0.4678–0.5433，10 real. vs 0.4806–0.5089，5 real.），构造上不相交。
- 处置：Table 4a 后加 Coincidence note。
- 证据：Table 4a 注；b4_pqclean_leg.json。

## #9 wild 集 RSA 误报（名称搜索伪影）保留为方法阴性对照
- 现象：CT 扫描按名称命中 vpn.dilithiumnetworks.com 证书，但证书实为 sha1WithRSA、无 PQ OID。
- 裁定：名称搜索伪影，非真 PQ 证书；其 S1 误报概率 <0.10 恰为特异性证据。
- 处置：保留在 wild 集并明示 "Retained as method-negative control"（Table 3）。
- 证据：wild/meta.jsonl；Table 3。

## #10 sntrup761 密文 1039B ≠ 预期 1122B
- 现象：OpenSSH 握手转储的 sntrup761 密文长度 1039B，与 KEM 规范预期 1122B 不符。
- 裁定：预期值口径错误（KEM 封装字节与密钥分片字段口径不同），实测 1039 为准。
- 处置：wild 采集记录按实测标注；不做"修复"。
- 证据：wild/REPORT.md；ssh-src 转储脚本。

## #11 OpenSSH DEBUG_KEXECDH 输出被 MSGBUFSIZ(1024) 截断
- 现象：补丁版 OpenSSH debug 输出 chunk 在 1024B 处截断，握手摘要/密文不完整。
- 裁定：debug3 通道 MSGBUFSIZ 限制。
- 处置：dump_digest 改 debug3 分块输出（CPPFLAGS -DDEBUG_KEXECDH），采集重跑。
- 证据：ssh-src/kex.c 补丁；wild/REPORT.md。

## #12 wild 单证书 S1 轨迹 22/22 复现门
- 现象：wild 预测需证明"冻结管线"未被 ad-hoc 配置污染。
- 处置：exp_wild_s1.py 落地 22 个条件×种子 macro-F1 复现门，须与 s1_*_seed*.json 逐位一致（22/22 通过）。
- 证据：results/wild_s1_trajectory.json + wild_s1_实验记录.md；§5.8。

## #13 NIST 电池边界与区间口径（24 格、三个显示 0.95、cusum 区间）
- 现象：24 vs 25 粗体格之争；ML-DSA-87 列两个显示 0.95 的格子语义不清；§5.1 cusum 区间
  "0.88–0.95" 把未粗体格当端点。
- 裁定：严格 <0.95 恰 24 格；三个显示 0.95 的格子均不严格小于（0.9500=285/300；0.9533=286/300 ×2）；
  ML-DSA 粗体 cusum 为 {0.93,0.88,0.93} → 区间 0.88–0.93。
- 处置：Table 2 注与 §5.1 重写；复核报告 §十二。
- 证据：results/table3_nist_formal.json。

## #14 G=5 的 z 值三处不一致（18/17/8）与 §6 误用 β 天花板
- 现象：§5.3 "z=467/616/500/70/18"、Fig.1 "z=17"、§6 "(z = 18)"；§6 把 β=0.1466 当实测泄漏值。
- 裁定：z 序列按实测 nn-F1 计算，(0.046148−0.016563)/0.001693=17.48→**17**；§6 实测应为 0.0461。
- 处置：三处统一 z=17、§6 改 0.0461、Table 5 C_len 行 0.1466→0.0461。
- 证据：results/s2s3_formal.json；复核报告 §九。

## #15 B-grid 保留率精度链（30.1%/62.1% 不可由显示值复算）
- 现象：显示值 (B2−B1)/(B5−B1) 用 3 位小数算不出 30.1%/62.1%。
- 裁定：分子分母按未舍入均值算（0.0208/0.0691 与 0.0901/0.1451）。
- 处置：§5.7 加 unrounded 注；复核报告 R1。
- 证据：§5.7；Table 4 注。

## #16 Table 4/5 旧值残留（30.7%/0.161/0.244）
- 现象：表格仍载 3-seed 时代旧值，与 5-seed 冻结值矛盾。
- 处置：全部替换为 5-seed 冻结值（B0–B5 网格）。
- 证据：复核报告 N1；results/align_order.json（n_seeds=5）。

## #17 AES-GCM 假设口径（PRP/PRF → PRF/CTR + 固定明文条件）
- 现象：Proposition 1 中 AES-GCM 伪随机性表述为 PRP/PRF，未说明明文条件。
- 处置：三处改为 PRF/CTR，并补 fixed-plaintext 条件与归约草图。
- 证据：§4.3；复核报告 R5。

## #18 BiLSTM 近随机的双对照闭合（诚实架构结果）
- 现象：BiLSTM P1/P2 = 0.0233/0.0370 低于随机基线，须排除实现失效。
- 对照 1：恒定序列 acc=1.0（实现无误）；对照 2：头部信号梯度消失（λ 梯子窄频带全级 ≤chance）。
- 处置：作为失败模式量化写入 §5.5/§4.4，不隐藏。
- 证据：host_verification.md §四；§5.5。

## #19 BiLSTM predict 整批推理 OOM（租机现场）
- 现象：predict() 对整测试集 2040×1024 单次推理，5 并发 worker 各自 OOM。
- 处置：predict 分块 256（数值等价：eval 无 BN/dropout、LSTM 零初态可分段）。
- 证据：RESUME.md #19。

## #20 符号链接致 makedirs 路径不一致（租机复跑现场）
- 现象：验证目录符号链接 data→正式目录，worker 写结果报路径错。
- 根因：os.makedirs("./data/../results") 经内核解析符号链接。
- 处置：res_dir 统一 os.path.realpath 后再 makedirs。
- 证据：RESUME.md #20；host_verification.md §四。

## #21 复跑 CNN 末 job OOM（外部争用）
- 现象：loss.backward() 处 OOM（请求 20MiB，仅剩 14.75MiB）。
- 处置：不可控外部争用；改 --parallel 2 + until 重试（断点续跑）。
- 证据：RESUME.md #21。

## #22 C2 校准与灵敏度梯子（负结果门槛）
- 要求：E3 规定负结果须过 C2 校准（≥0.60）或报灵敏度梯子。
- 实验：合成 5 类×300×1024B，8B 类令牌按概率 λ 注入（数据集种子 20250917）。
- 结果：CNN λ=0.5/1.0 = 0.893/1.000 → C2 通过；BiLSTM 窄频带全梯级 ≤chance。
- 证据：RESUME.md #22；host_verification.md 四·补2；Fig. 6。

## #23 预算敏感性消融（epochs 30 vs 15）
- 要求：堵"为什么不多训几轮"之问。
- 实验：--epochs 30 全域对照：CNN 0.2832/0.4590 反超树基线，BiLSTM 不动。
- 口径："CNN<树基线"仅限冻结 15ep 统一预算协议。
- 证据：RESUME.md #23；§5.5 e30 段。

## #24 NIST 双家族偏离的旧总结行与冻结文件不符（绘图时发现）
- 现象：旧总结行 "serial 0.50/0.70/0.75、ECDSA freq 0.86、其余 0.97–1.00" 不完整。
- 裁定：24 个 <0.95 格全部集中在 4 个签名类；其余 12 原语类 ≥0.967。
- 处置：fig4 按冻结文件绘制；§5.1 按双家族结构改写。
- 证据：figures/QA_交付报告.md #24。

## #25 RSA-OAEP-2048 错误列入 Π_pse（用户提出）
- 现象：Proposition 1 曾把 RSA-OAEP（"RSA 假设"）列入伪随机密文类。
- 驳回（用户，正确）：RSA 假设给单向性而非不可区分性；OAEP 密文是 Z_n 中均匀元素，
  模数区间截断致顶层字节有偏（实测首字节 ≥0x80 占比 0.307 vs 均匀 0.5，z≈6.7）。
- 处置：Π_pse = ML-KEM×3 + AES-GCM + 均匀对照；RSA-OAEP 归经验桶，§4.3(ii) 写入排除理由+实测。
- 证据：RESUME.md #25；§4.3。

## #26 归约草图方向颠倒（用户提出）
- 现象：从"π₁ vs π₂ 可分"直接构造"π₁ vs 均匀"区分器——方向反了。
- 处置：三角论证重排 ①每类与均匀不可区分 → ②三角不等式 ⇒ 类间相互不可区分（δ/2 混合）→
  ③超零带分类器即类间区分器 → 矛盾。
- 证据：RESUME.md #26；§4.3 归约草图。

## #27 重复次数升级：S1 2→5 seeds、C_align 3→5 seeds、PQClean 5→10 realizations（内部审核会决议，2026-09-19）
- 现象：§5.4/§5.6/PQClean 腿的重复数低于 E14 惯例（S1 仅 2 seeds、C_align 3 seeds、
  PQClean 5 realizations），误差棒偏薄。
- 处置：全部升级重跑（协议不变，仅重复数变化；per-seed 独立窗口 RNG E8 不变）。
- 新旧数值（mean ± SD 口径）：

  S1（5 seeds，旧 2 seeds）：intact 0.9996→**0.9997**；oid_zero 0.9997→**0.9998**；
  oid_rand 0.9998→0.9998；head48 0.8838→**0.8827**；trunc25/50/75 0.544/0.386/0.316→
  **0.548/0.383/0.314**；slide25/50/75 0.888/0.611/0.611→**0.886/0.613/0.614**。

  C_align（5 seeds，旧 3 seeds）：A2 移位 0.8748/0.8694/0.8330→**0.8748/0.8687/0.8334**；
  A2_nt 无首块 0.3765/0.2377/0.0904→**0.3768/0.2372/0.0907**；A1 精确 0.9262 不变。

  PQClean（10 realizations，旧 5）：整对象 0.524±0.031 (SE 0.0139)→**0.490±0.026 (SE 0.0081)**；
  窗口 0.494±0.010 (SE 0.0045)→**0.509±0.017 (SE 0.0055)**；逐实现区间 0.4806–0.5089→
  **0.4811–0.5400**（整对象 0.4544–0.5283）。**案例 #8 的"双 0.494 巧合"在 10 实现下消失**，
  #8 保留为历史记录，正文 Coincidence note 已改写。
- 落文：§5.4/§5.6/摘要/§4.4/§5.2/Table 4/4a/Fig.2/3 全部同步；figs_data 断言更新；
  图脚本 HOST 路径由 /mnt/hgfs 改为本地 results/（共享挂载已掉）。
- 证据：results/s1_formal_summary.json（n=5）、align_order.json（A2/A2_nt 5 seeds）、
  b4_pqclean_leg.json（10 realizations）。

## #28 开集实验 v1 的打分不对称（零带抓出，2026-09-18）
- 现象：开集拒绝实验 v1 的 E2 置换零带 AUROC 异常（MSP 0.93、熵 0.99，应 ≈0.5）。
- 裁定：known 对象由"本折模型"打分、unknown 由"5 折平均"打分——置换标签下这个
  打分不对称本身制造 ID/OOD 差异（平均化使熵升、最大概率降），零带被污染，v1 全部作废。
- 处置：v2 改单模型 80/20 对称打分（known 240/60 划分、unknown 全入测试、同一模型打分），
  零带回归 0.5 语义附近；v1 JSON 由 v2 覆盖。
- 教训：任何"平均 vs 单模型"的打分不对称必须先过零带检验。
- 证据：exp_open_set.py（v2）；复核报告 §二十三。

## #29 跨实现迁移测试集（内部审核会决议，2026-09-19）
- 原案：oqs-provider + OpenSSL 3.5 生成测试集。查证后修正：训练容器本身就是
  oqs-provider + OpenSSL 3.5.3 + liboqs 0.16.0 生成的（gen_formal.py），原案为同工具链重采样；
  改为**原生 OpenSSL 3.5.3（default provider）ML-DSA/ML-KEM** 生成 900 对象测试集
  （6 PKCS#8 + 3 自签 X.509，每类 100，仅测试）。ML-KEM 无签名能力，故无 ML-KEM 证书。
- 首轮 CN 未对齐（19 字符 vs 训练 11 字符 → +16B subject/issuer 位移）致 mldsa44_cert P2
  崩塌至 0.0468——字段级敏感性，非实现差异；对齐 CN 后恢复。
- 终结果（5 seeds，E14）：S1 迁移 0.9992±0.0003 (SE 0.0001) ≈ 参照 0.9993±0.0009 (SE 0.0004)；
  P2 0.7494±0.0085 (SE 0.0038) vs 0.6740±0.0028 (SE 0.0012)；P1 0.4589±0.0195 (SE 0.0087) vs
  0.3725±0.0183 (SE 0.0082)；唯一逐类回落 mldsa87_cert P2 0.3789±0.0243（7471/7472B 混合
  的头窗对齐位移）。ASN.1 逐字节对比：结构/OID/长度形式无实现级差异。
- 落文：§3.2 注、§5.10、Limitations 部分缓解措辞；测试集 data_oqs_native.tar.gz（CC BY 4.0）随发布。
- 证据：exp_oqs_transfer.py；results/oqs_transfer_formal.json（env：OpenSSL 3.5.3 native；
  训练侧 oqs-provider + liboqs 0.16.0）。

## #30 Table 4 补格（内部审核会决议，2026-09-19）
- 目标 8/16 → ≥12/16。实测新增：C_bytes×S1（trunc50/slide50 损坏片段 + P1，rf/hgb，
  5 seeds + E2 零带）、C_struct×S3（容器长度 G=16/64 量化 + 1-NN，5 seeds：1.0000 / 0.8519）。
- **trunc50 首版设计缺陷（零游程标记）**：把头部 50% 置零在对象中埋入长度正比的
  零游程（zero-run 长度=L/2），170 维游程/字节分布特征直接读出长度 → rf/hgb ≈0.46，
  远超 0.063 零带——损坏手段自己造了长度信道。改均匀随机重填后回落零带（rf 0.0702 起）。
  零游程标记效应保留为 §5.2 一行注记。
- 构造标注格：C_bytes×S2（S2 只改长度）、C_align×S2/S3（长度双射推导）、
  C_struct×S2（=S0）、C_align×S1（=S0）、C_bytes×S3（字节观测不可用）。
- 证据：results/bytes_s1_formal.json、results/struct_s3_formal.json。
- 终值（5 seeds，E14）：trunc50 rf 0.0663±0.0039 (SE 0.0017)/hgb 0.0659±0.0020 (SE 0.0009)，
  零带 0.0627±0.0033/0.0641±0.0038（z≤1.1）；slide50 rf 0.0723±0.0033 (SE 0.0015)/hgb
  0.0746±0.0045 (SE 0.0020)，零带 0.0602±0.0034/0.0598±0.0025（z≤5.9）。（历史更正见 #41：原句"不高于 intact P1 自身 z=2.7"逻辑不成立——5.9>2.7；且逐类归因证明高 z 非 ECDSA 驱动而是签名类结构，ML-DSA-44 领跑。）
  结论：S1 损坏下不可能层依旧成立。C_struct×S3：G=16 1.0000±0.0000、G=64 0.8519±0.0000。
- 覆盖率 8/16 → 16/16（10 实测 + 6 构造标注），无未解释空格。

## #31 现有工具实测（内部审核会决议，2026-09-19）
- file(1)/libmagic 5.46（系统 magic 库）：intact 类级 macro-F1 0.0555、族级 0.4443——
  仅识别 RSA PKCS#1（"DER Encoded Key Pair"），证书只报 "Certificate, Version=3"（族级，
  无算法粒度），其余 10 个 PKCS#8 类（PQ/EC/Ed25519/SLH-DSA）一律 "data"；oid_zero 下不变，
  head48/trunc50 下 0。
- OID+结构基线（11 算法 OID + TBS/PKCS#8/PKCS#1/SEC1 头标记；原记 12 为计数错误，
  见 #50 更正）：intact 1.0000（逐类唯一
  OID+格式）；oid_zero 0.5000（ML-DSA/SLH-DSA 前缀被抹 → 9 类死；ML-KEM 与经典 OID 在
  抹除前缀之外 → 存活）；head48/trunc50 0。
- 首版基线 OID 弧有误（ML-KEM-768/1024、SLH-DSA 弧值按记忆写错），以训练对象实测字节
  修正（mlkem768=…4.4.2、mlkem1024=…4.4.3、slhdsa128s=…4.3.26、slhdsa256s=…4.3.30）；
  rsa2048_pkcs8/ecdsap256_pkcs8 实为 PKCS#1/SEC1 格式（无算法 OID），补格式标记。
- 落文：§5.11 + Related Work "none of them quantifies" 改写为实测口径。
- 证据：results/tools_baseline_formal.json（env：file-5.46、system magic、OID 表）。

## #32 TLS 1.3 真实封装验证（内部审核会决议，2026-09-19）
- 实验：34 类对象经真实 TLS 1.3 会话（AES-256-GCM，每类一次握手、逐对象写）发送，
  解析客户端 record 密文内容长度（L+17/record：1 inner + 16 tag）；1-NN 特征
  (record 数, 首长, 次长)。
- 结果：macro-F1 = 0.9262 ± 0.0000（5 seeds）——恰好等于合成 "none" 点；分片只影响
  SLH-DSA-128f/256s（17088/29792B → 两 record），(count, remainder) 仍类内唯一 → 无损失。
- 实现弯路（记录）：本机 Python ssl 的 set_ciphers 对 TLS1.3 套件报 no cipher（构建上限），
  但**不设套件时默认协商即 TLS_AES_256_GCM_SHA384**（握手后断言实测套件）；openssl CLI
  需用 -ciphersuites 而非 -cipher；s_client/s_server 子进程在本沙箱内握手异常，最终采用
  进程内 ssl.MemoryBIO。
- 落文：§4.1 S2 限定句、§5.3 末 Real-encapsulation validation 段、Table 4 C_len×S2 格补行。
- 证据：results/tls_records_formal.json（env：OpenSSL 3.5.3、record policy、会话方式）。

## #33 Epoch 预算网格 15/30/60（内部审核会决议，2026-09-19；2026-09-20 租机 V100 完成）
- 设计：CNN/BiLSTM × {15,30,60} × {p1,p2} × 5 seeds = 12 组 60 运行；15/30 的 40 个
  逐种子文件已在 rental_snapshot/pqc/results/（冻结聚合已核）；新增 60ep 20 个 +
  复现界验证（CNN 重跑比对 ≤0.026、BiLSTM exact）。
- 本机无 GPU（torch 2.13+cpu），60ep 需 GPU——用户已同意提供；运行器 exp_budget_grid.py
  断点制（--epochs 60 / --verify），GPU 到位即可跑。
- 落文计划：Figure 7（预算曲线 + rf/hgb 水平参考线）；§5.5 "2×-epoch ablation" →
  "budget grid (15/30/60)"；若 CNN 60ep 续升或 BiLSTM 复苏如实报告。


- 60ep 20 运行 + verify 2 运行全部完成（torch 2.5.1+cu124，Tesla V100-16GB）。
- 网格（5 seeds，E14）：CNN P1 0.2075±0.0083 → 0.2832±0.0066 → **0.3181±0.0045**；
  CNN P2 0.3415±0.0237 → 0.4590±0.0142 → **0.4999±0.0046**（单调上升，60ep 双协议超树基线）；
  BiLSTM P1 0.0233→0.0220→0.0223、P2 0.0370→0.0331→0.0359（零带平躺，无复苏）——
  "CNN<树"仅限冻结 15ep 预算；结论已按实报告更新。
- 复现界：CNN seed7 重跑 |Δ|=0.0004（≤0.026 ✓）；BiLSTM seed99 重跑 |Δ|=0.0082 ——
  跨 torch 版本（2.9.1+cu128 → 2.5.1+cu124）非 exact，界重述为"冻结环境内 exact、
  跨版本 ≤0.009"，正文与本文档同步。
- 落文：Figure 7（矢量，QA 6/6）、§5.5/§4.4/§1/§2 budget-grid 口径、复现界句更新。
- 证据：results/*_e60.json（20 个，已回传改名对齐单下划线命名）。

## #34 paper.tex 尾部误删与重建（2026-09-20，自残事故记录）
- 事故：§5.5 改稿脚本用 md 语法锚点（"**5.6"）在 tex 中定位失败返回 -1，切片
  tex[i:-1] 将 §5.6 起至文末（含六图六表与参考文献）整体抹除。
- 处置：build_tail.py 从当前 md 与 tables_formal.md 重建尾部（§5.6–§7、七图、
  六表含 p 列/旋转表头/4a/5 重编号、框段、References），修复 \textbf 切串、
  %/#/_/− 转义、表号前置、节标题补发四类问题；重编译 37 页 0 错误，
  30 项抽验全过（3 项为旧值正确缺位、1 项连字伪影）。
- 教训：tex 定位锚点禁用 md 语法；大段替换前必须 assert 双端点 > 0。

## #35 术语一致性冻结轮（内部审核会决议，2026-09-20）
- 标题改 (b) 变体并保留 Algorithm-Level：
  "Quantifying Algorithm-Level Observable Side-Channel Leakage (Representation-Level) of ..."。
- 摘要首句后插限定句（"Herein, 'side channel' means representation-level functions of the
  stored encoding needing no secret key — not key-recovery channels (power, timing)."），
  同步压缩至 245 token（删 detector-calibrated/budget-robust 短语、场景名括注、
  "on windows"、residual-signal 尾句等冗余，全部冻结数字与必留短语保留）。
- 关键词 side-channel leakage → observable leakage; representation-level identification。
- §1 第二段已有 representation-level 限定（核实无需改）。
- Related Work 末尾新段 "Side-channel boundaries"，引 Kocher1996（CRYPTO'96, pp.104-113,
  DOI 10.1007/3-540-68697-5_9）与 Berzati2025（CASCADE 2025, pp.3-26,
  DOI 10.1007/978-3-032-01405-4_1，eprint 2024/2051 核实）。
- 验收：全文 side channel 出现处均有上下文限定或即 §4.1 定义本身；文献 26 条全引；
  37 页 0 编译错误。

## #36 Proposition 1 定位表述调整（内部审核会决议，2026-09-20）
- 贡献 (3) 标题 "Impossibility layer with a bound" → "Impossibility layer, formalized and verified"；
- §4.3 开头加 folklore 定位句（"its role here is not novelty but to delimit exactly which
  classes the impossibility covers — and, via the RSA-OAEP and signature exclusions, which it
  does not"）；
- 摘要 "a computational-indistinguishability bound (Proposition 1)" → "a formalized
  indistinguishability bound with explicit scope exclusions"（同步压词至 248 token）；
- "methodological contribution" → "audit-discipline contribution"；RSA-OAEP 实测证据与
  theorem/empirical split 表述保留。
- 验收：全文无 "Impossibility layer with a bound"、"methodological contribution" 残留；
  贡献重心落在 ladder+budget+三轴套件实验验证。38 页 0 编译错误。

## #37 参考文献扩充 26→48 与引用锚点布设（内部审核会决议，2026-09-20）
- B 组 8 条（lai2025getrid / liu2025rejected / shen2023encrypted / sharma2025survey /
  azab2024network / gebru2021datasheets / pineau2021improving / herley2017sok）+ A 组 14 条
  （chen2018grayscale / wang2018cnn / mittal2021fifty / sester2021comparative /
  skracic2023bytercnn / zhu2023cnnlstm / felemban2024lightweight / sowa2024pqc /
  wickramasinghe2026mindgap / dubey2026readiness / catoni2025resumption / berman2024hint /
  zhou2025rejected / belaid2026sucre）→ 共 48 条。
- 元数据全部经 Crossref/arXiv/TCHES/ePrint/JMLR/ACM 页面核实（DBLP 反爬，改用 Crossref；
  Semantic Scholar 限流未依赖）；Berzati2025 会场修正为 CASCADE 2025；无编造条目。
- 无正式版例外备案（3 条，规则允许）：dubey2026readiness（arXiv-only，无正式版）、
  wickramasinghe2026mindgap（arXiv + IMC 2026 to-appear 注记，无页码）、
  berman2024hint（ePrint-only，无正式版）。
- 引用锚点：§2 PQ 迁移测量（4 条）、随机性/ML-DSA 非均匀（3 条）、侧信道边界（+lai/liu）、
  加密流量分类（+3 条 survey）、文件雕刻（+7 条，一句综述）；§3.5 Datasheets（1 条）；
  §6 方法论（herley/pineau）。build_tail.py 引用白名单扩充 22 键，尾部重建幂等。
- 顺带修正（按数据核实）：§3.5 "26 numbered cases" → 37（日志实有 #1–#37，本条目计入；
  en 日志补齐 #30/#33–#36 英译、两版标题计数 26→37）；"to our knowledge" 重复短语删除（md+tex）；
  BellareRogaway 书名全角破折号 → LaTeX ---（缺字形告警消除）；audit #35 内 Berzati2025
  会场 COSADE → CASCADE（与 bib 对齐）。
- 验收：bibtex 48/48 全引（0 orphan）、0 undefined citation/reference、0 missing character、
  41 页 0 编译错误；PDF 抽验：新句落位（如 encrypted-traffic [30,31,32]）、
  参考文献 [1]–[48] 全部渲染（含 Skračić/Belaïd 等重音条目）。

## #38 投稿配套材料轮（内部审核会决议，2026-09-20）
- 文末新增四节（\section*，位于 References 之后；md "## End matter" 为单一来源，build_tail.py
  解析生成）：CRediT（Shen Jinhui: Conceptualization/Methodology/Software/Validation/Formal
  analysis/Investigation/Data curation/Writing–original draft/Visualization；Li Xiaofeng:
  Conceptualization/Supervision/Project administration/Resources/Writing–review & editing）；
  Declaration of competing interest（无已知利益冲突）；Data availability（«REPO_URL» 占位符，
  MIT 代码 / CC BY 4.0 数据，接受后注册 DOI）；Funding（无特定资助声明）。
- 格式：elsarticle preprint 单栏保留（C&S 出版为单栏；GfA 逐项核对见 submission_checklist.md）；
  lineno 安装（tlmgr install lineno）并 \linenumbers 开启——PDF 抽验行号自第 1 页起连续
  （边距 x≈95，1→1062，43 页全有）；0 编译错误、48/48 全引不变。
- Highlights（highlights.txt）：5 条，长度 76/76/75/81/76，全部 ≤85 字符，全部引用冻结数字
  （0.9262 外层加密衰减、0.883 头保留、38 案例日志等）。
- Graphical Abstract：figures/make_ga.py → graphical_abstract.{pdf,png}（1735×860 px @300dpi，
  示意型单面板：34 类→4 信道→3 结论卡（字节不可能层 0.0744/长度主信道/结构指纹）→发布横幅；
  蓝/灰/红/橙语义配色）。规格修正：初版横版 2.02:1 不满足现行通用页"与 1328×531 同比例"要求，
  重制为 2.492:1（1687×677 px ≥1328×531、300 dpi，pad_inches 定幅导出避免 tight 裁剪破坏比例）；
  竖版 531×1328 为旧版期刊模板口径。
- Cover letter（cover_letter.md）：时效性（IR 8547：2030 弃用 / 2035 禁用，RSA/ECDSA/EdDSA）、
  可复现性（38 案例审计日志 + 冻结 env/seed + 复现界）、scope 契合（审计/取证/迁移监测）；
  建议审稿人 5 名（Memon NYU / Frank Li UNSW / Yu Yu SJTU / An Wang BIT / Lashkari UNB），
  单位经 NYU/UNSW/SJTU/pure.bit/UNB 页面核实；邮箱待作者补填；均无共同单位，作者需自查
  近三年无合作。
- 构建修复：conv() 增加 & → \& 转义（CRediT "review & editing" 曾致 Misplaced alignment tab）。
- 顺带修正（数据核实）：§1/§2 两处 "head-48B 0.884" → 0.883、§2 "truncation to 25% collapses to 0.54"
  → 0.548——冻结文件 s1_formal_summary.json head48=0.88268、trunc25=0.548（§5.4 与 Table 4 均为
  0.8827/0.548），§1/§2 旧值为 5-seed 升级前残留舍入。
- 计算口径：本轮无任何新数值需求——未重训、未改数；封面/Highlights/GA 全部引用冻结结果文件。
  注意：冻结模型权重未落盘（租机现场仅保存逐种子指标快照 JSON）；若后续需执行
  "测试集重采样 + 冻结模型推理复验"，需先按用户"不重训"约束在冻结 torch 2.9.1+cu128
  环境恢复权重（回租现场提取或接受一次性重新冻结并落盘权重），届时按 E 规范落盘
  （env 字段、seed 记录照旧）。
- GfA 核实情况：C&S 专页（sciencedirect 403、Wayback/archive.today 不可达、WHU 镜像为 2014 旧版）
  无法直读——独立审读报告按"已核实/通用标准/UNKNOWN"三级如实标注，未编造；逐项清单与 open items
  见 submission_checklist.md（引注体例：GfA 索引片段提示作者-年份句式，与编号制互斥，标注待作者
  确认；现行编号制与 C&S 已发表论文一致，投稿阶段合规）。
- 验收：43 页 0 错误 0 undefined；行号连续；文末四节 PDF 渲染抽验通过（CRediT 位于行号
  1045–1048，Funding 位于 1060–1062，«REPO_URL» 占位可见）。

## #39 §6 填充设计小节 + Table 6（内部审核会决议，2026-09-20）
- 离线分析 exp_padding_design.py（--verify）：只读 data/ 与 results/s2s3_formal.json，不改任何
  冻结文件；无重训、无新模型。
- 口径闸门：先在原始长度上重放 §5.3 冻结协议（50 Monte-Carlo draws、对称随机化
  tie-breaking、seed 2025、1-NN 三种子 (42,123,2024)、零带 10×seed42），与
  results/s2s3_formal.json 五级 β/1-NN/零带/G 逐位一致（β 0.9260/0.8824/0.7647/0.2938/
  0.1466 全部复现）→ 新旧数字可比性成立，否则脚本非零退出。
- (a) 4096 格点填充代价（ceil(L/4096)·4096）：总体膨胀 1.671×；逐类 1.00–85.33
  （中位 2.49；最坏 ed25519_pkcs8 48B→4096B = 85.3×）；填充原子 5 个
  {4096, 8192, 16384, 20480, 32768}。
- (b) 填充后 β(G)（同协议）：长度梯子 46/31/26/10/5 原子 → 5/5/5/4/2；
  β′ 0.1469/0.1469/0.1469/0.1176/0.0593（exact 级 = 原子数界 5/34≈0.147）；
  实测 1-NN′ 0.0979/0.0979/0.0979/0.0587/0.0077 vs 零带′ 0.0111±0.0015/0.0111±0.0015/
  0.0111±0.0015/0.0113±0.0010/0.0088±0.0008 → z = 58.8/58.8/58.8/46.4/−1.4（原 467/616/500/70/17）：
  格点填充**压平但未消除**长度信道，残差 = 块计数身份。
- 统一最大长度（32,768B）敏感性点：膨胀 8.263×；全级 β′ = 1/34 = 0.0296（1 原子 =
  chance，实测 z = −3.7）——长度信道完全消除的唯一设计点。
- (c) 结构信道不受任何填充影响：内容指纹（§5.4：intact 0.9997、OID 擦除 0.9998/0.9998、
  窗内 0.55–0.85；§5.7 无序界 30.1%/62.1%）只依赖内容编码；DER 规范化最多擦除分类器
  从未需要的 OID 区。结论口径："设计权衡的量化起点"，未夸大为完整防御。
- 落文：§6 新小节 "Implications for leakage-resistant format design" + Table 6
  （tables_formal.md + build_tail.py 规格/重编号/标签）。
- 证据：results/padding_design_formal.json（env/seed 记录、gate 字段、per_class 逐类、
  三组梯子）。
- 验收：--verify 复跑通过（闸门全 True，env.no_training=True / frozen_files_modified=False）；
  44 页 0 错误 0 undefined 0 missing character；§6 小节与 Table 6 PDF 渲染抽验通过；
  U+2032 prime 缺字形（ec-lmr12/10）→ 文本内改 ASCII 撇号修正。

## #40 类别分布失配敏感性实验（内部审核会决议，2026-09-20）
- 设计：训练保持平衡不动（300/类，冻结协议 v2.2）；三个测试先验 uniform / skew80_20
  （11 经典类 RSA/ECDSA/Ed25519/AES 占 0.80，22 PQ 类 + urandom 控制共享 0.20，组内均分）/
  skew95_5（0.95/0.05）；C_len（1-NN）与 C_bytes（rf, P1, stats 170 维）各 5 seeds
  （E14 [42,123,2024,7,99]）；报告 macro-F1 与先验显式加权 W = Σ p_c F1_c。
- 冻结重放闸门：本地按冻结协议复跑并与 rental_snapshot 冻结 JSON 逐种子比对——
  C_len 5/5 精确一致（0.9262，|Δ|≤1e-6）；C_bytes 5/5 一致（0.2799/0.2803/0.2863/0.2826/
  0.2749，|Δ|≤0.002 容差，本地 sklearn 1.9.0 vs 租机版本差异备案）；不一致即非零退出。
- 确定性 W（冻结逐类 F1 直接加权，无采样）：C_len 0.9262 → 0.9455 → 0.9516；
  C_bytes 0.2808 → 0.4237 → 0.4686——经典先验下字节信道部署口径上升一半（经典类逐类
  F1 ≈ 0.48 vs PQ-only ≈ 0.19），长度信道两组均近顶（classical ≈ 0.95；PQ-only ≈ 0.95）。
- 采样实测（5 seeds，mean±SD）：C_len 80/20 macro 0.9379±0.0003 / W 0.9744±0.0006
  （vs 精确 0.9262/0.9455——上漂 = 确定性 1-NN tie-breaking 使平局类 F1 组成依赖，
  §5.3 机制再现，+0.012/+0.029）；C_bytes 80/20 W 0.4586±0.0074、95/5 W 0.5214±0.0085
  （vs 精确 0.4237/0.4686——上偏 = 被降权类 n≈89–190 的 F1 小样本估计正偏）。两个估计
  效应均在正文显式讨论（用户验收点）。
- 落文：§5.12 新小节 + Discussion "Closed-set, balanced-prior caveat" 段；口径：
  "部署聚合 = W；macro-F1 = 先验盲逐类能力；转换应使用发布的逐种子逐类 F1"。
- 证据：results/prior_skew_formal.json（env/seed/先验定义/闸门/逐种子/确定性对照；
  no training beyond frozen protocol replay）。

## #41 §5.2 slide50 自相矛盾句修正 + 逐类归因（用户提出，2026-09-20）
- 用户指出：§5.2 "z ≤ 5.9 — no more separated than the intact P1 value itself, z = 2.7"
  自相矛盾（5.9 > 2.7，口径为相对 null SD 的 z）。成立，已改。
- 逐类归因实验 exp_slide50_attribution.py：严格复刻 exp_bytes_s1.py slide50 管线
  （damage/window/features/CV/分类器配置），冻结宏值闸门 |Δ|=0（10/10 全零差）。
- **ECDSA 驱动假设被数据否定**：slide50 逐类 F1（5 seeds 均值）rf/hgb 领跑者为
  mldsa44_sig 0.1872/0.1803，ECDSA 仅第二 0.1055/0.0945；其余 ≤0.08。
  去 ECDSA 的 15 类宏值 0.0754±0.0031（rf）/ 0.0782±0.0047（hgb）vs 16 类零带中心
  0.0602±0.0034/0.0598±0.0025 → z≈4.5/7.4，仍显著高于零带——残差是分布式的签名类
  结构，不是 ECDSA 假象。
- z 关系解释：slide50 宏值（0.0723/0.0746）与 intact P1（0.0744）同量级；z 更大
  （5.9/3.5 vs 2.7）只因 slide50 零带 SD 更紧（0.0034/0.0025 vs 0.0042），非分离度更大。
- 机制（与 §5.1 衔接）：slide50 保留对象后半段——ML-DSA-44 后半段为 ẑ 高索引系数区
  （拒绝采样形状分布，§5.1 记录其序列检验偏离），ECDSA 后半段含 s 值尾部——签名类
  表示层结构以衰减强度存活。
- 用户建议句未照单采纳的两处（数据核查）：①"fully attributable to ECDSA"不成立
  （上述逐类证据）；②"two orders of magnitude below any structural-channel reading"
  不符——字节 slide50 0.072–0.075 与最弱结构读数（trunc75 0.3139）之比为 4.2×、
  与 intact（0.9997）为 13.4×，正文表述为"comparable F1 + 更紧零带"而非数量级措辞。
  （2026-09-24 更正注，见 #43/M3：本条的 15 类宏值 0.0754/0.0782 为 mask 口径上偏，
  labels-only 重算为 0.0700/0.0733，z=0.4/0.9 在机会线内——§5.2 句子已改。逐类归因结论不变。）
- 落文：§5.2 原括注替换为新句（md+tex）；audit #30 原文加历史更正注。
- 证据：results/slide50_perclass_attribution.json（闸门/逐种子/逐类/15 类宏值/零带引用）。

## #42 prim 组 60ep 预算补跑（内部审核会决议，2026-09-20）
- 环境：租用 V100 主机（用户提供）；torch 2.9.1+cu128 / Tesla V100-SXM2-16GB /
  cuda 12.8 ——与 prim 组 30ep 冻结档同系；远程补装 numpy 2.2.5 + sklearn 1.9.1（Python 3.11.12）。
- 配置与冻结完全一致：16 primitives × 300、1024B 窗、P1/P2、CNN（§5.5 架构）、batch 128、
  5 seeds（E8 逐种子窗口 RNG）、唯一变量 --epochs 60；共 2 协议 × 5 seeds = 10 job，全部完成。
- 途中修复两个运行器缺陷（不影响冻结语义，已注释）：
  ① train_baselines.run_one 的 with open(res_path) 为早期编辑残留未定义变量（NameError，
  此前冻结运行实际从未走此路径）——删除 with，json.dump 直写 out_f（与 rental_snapshot
  冻结运行语义一致）；
  ② --tag 双下划线事故复现（"__e60"）——runner 改为传 "e60"，train_baselines 内部加
  下划线 → 单下划线命名（与历史 e60 下载后改名一致）。
- 同机复现验证（--verify prim60）：cnn_p1_seed7 |Δ|=0.0122、cnn_p2_seed99 |Δ|=0.0160，
  均 ≤0.026 界（CNN 复现包络，cudnn.benchmark/TF32 非确定内核所致）✓。
- 结果（5 seeds，E14；16 类 macro ± seed SD，SE 括号）：
  P1 0.0547 ± 0.0054 (SE 0.0024)，z vs 零带 = −2.0（零带中心之下）；
  P2 0.1056 ± 0.0040 (SE 0.0018)，z = +10.1（由 ECDSA 抬升）；
  非 ECDSA 15 类均值 0.0486 ± 0.0045 (P1) / 0.0478 ± 0.0042 (P2)，均 < chance 0.0625；
  ECDSA 0.1468 ± 0.0450 (P1) / 0.9715 ± 0.0051 (P2)。
- **如实报告的发现（用户验收口径：发现不是失败）**：60ep 出现首批种子稳定的非 ECDSA
  逐类逃逸——P2 rsa2048_ct 0.1233 ± 0.0182（SE 口径 z=7.5）、P1 mldsa44_sig 0.0956 ± 0.0213
  （z=3.5）——两者均落在 Proposition 1 的**显式排除集**内（OAEP 单向而非伪随机；ML-DSA
  为签名类）。其余高于 chance 的逐类值（ed25519/slhdsa_128f/mlkem1024_ct/mldsa65_sig）
  均在 2×SE 内，不构成稳定逃逸。
- 30ep 旧句两处顺带修正（数据核实）：①P2@30ep 非 ECDSA 均值 0.036 → 0.0349（冻结 e30
  逐类重算）；②"P1@30ep every class stays below chance"不成立——mldsa44_sig 0.0782±0.0355
  （1×SE 内），改为如实表述。
- 落文：§4.4 第 2 点整段改写（30ep 修正 + 60ep 补全 + 排除集解释）；
  贡献 (3) 措辞调整："proving the layer is budget-robust in aggregate (…排除集内的
  seed-stable emergences…)"——用户预案"如实报告并调整贡献 (3) 措辞"执行完毕。
- 证据：results/cnn_{p1,p2}_seed{7,42,99,123,2024}_g_prim_e60.json（10 个）、
  results/prim60_summary_formal.json（env 断言 torch 2.9.1+cu128/V100 全过、逐类 mean/SD/SE、
  逃逸与稳定逃逸清单、verify 记录）。

## #43 全量数据合理性审计 + 逐字节代码审计（内部审核会决议，2026-09-20）
- 数据审计 exp_data_audit.py（只读；214→215 个 results/*.json）四层结果：
  L1 JSON 卫生全过（可解析、无 NaN/Inf、F1 全在 [0,1]）；
  L2 结构一致性全过（macro==mean(per_class) Δ<1e-9、SE=SD/√n、5-seed 组完整）；
  L3 正文口径核对 110+ 条全过——S2 梯子、β(G) 五级（z 取 round 精确复现 467/616/500/70/17）、
  S1 十一格、prim P1/P2/ECDSA 0.2508/Ed25519 0.0713/15 类 0.0626、mixed-34 六基线、
  预算网格 e30/e60、prim60、C_align 六值、open-set AUROC 0.8307/0.8064、TLS 0.9262、
  tools 七值、B4 五值、transfer 八值、padding/prior-skew/slide50 新冻结档；
  L4 种子离群扫描（全 5-seed 组，>3σ 留一口径）：17 个出挑点。
- 出挑数据核实（用户要求"一定要返回核实脚本"）：results/verify_flags/
  flag_01_bilstm_p1_seed42.py + flag_02_group_seed_outlier.py（参数化四步：完整性/内部一致/
  种子上下文/统计口径）。**17/17 全部 AUTHENTIC**：13 个与 rental_snapshot 冻结副本逐字段
  一致；4 个 s1 本地件（无副本）macro==mean(per_class) Δ=0；出挑均为种子级波动，全组 z
  均 <2σ（8.7σ 等留一读数为 σ 收缩伪影：bilstm_p1 seed42 全组 z=1.94，15ep 0.0352 → e30
  0.0251 → e60 0.0216 随预算回归 chance）。**无需修正任何冻结值。**
- 数据集完整性：34 类 × 300 = 10,200 对象，文件数/非零尺寸/len_unique 与 meta 全一致，0 issues。
- 意外正面证据：5 个 rf_p1_*_g_pk8 文件与租机副本仅 sec 字段不同（本地复跑产物），
  macro/per-class/confusion 逐位一致 → rf 跨环境逐位可复现的新佐证。
- 审计脚本自身两处口径修正（非数据问题）：S2 梯子映射 inner→rand255→rand1024；
  z 取 round 而非 trunc。
- 代码审计（独立静态审读 10 个新增/修改脚本）：H1×1、M×5、L×9。处置：
  H1（prim60 verify 无磁盘备份→删除前落盘 .bak+finally 恢复）已修；M1（verify 超界不回滚→
  快照拷回）已修；M2（verify 需 CUDA 否则 abort）已修；M3（slide50 归因 15 类宏值口径错误→
  labels-only + 15 类零带重算，支撑 §5.2 句的数字待重算回填）已修；M4（原子写盘+断点校验）
  已修；M5（Table 6 无生成器）留档（tables_formal.md 手工维护）；L3/L4/L5/L6/L7 已修，
  L1/L2/L8/L9 留档。核对通过：新脚本只写自有新文件、冻结协议重放一致、env 断言一致。
  详见 代码审计报告_20260920.md 第二轮。
  M3 重算回填（2026-09-24）：labels-only 口径下 15 类宏值 rf 0.0700±0.0026 / hgb
  0.0733±0.0044，vs 15 类置换零带 0.0684±0.0043 / 0.0676±0.0064 → z = 0.4/0.9（机会线内）；
  旧 mask 口径（0.0754/0.0782，"≈4–7 SD"）为双向剔除造成的上偏，§5.2 句子已按新数改写：
  "excluding ECDSA leaves the 15-class macro at chance…ML-DSA-44 per-class elevation is offset
  by sub-chance classes in the aggregate"。逐类结论不变（mldsa44 0.1872/0.1803 领跑、ECDSA
  第二 0.1055/0.0945）；闸门 10/10 Δ=0。

## #44 §5.5 "2×" 残留与括号断裂句重写（用户提出，2026-09-24）
- 用户指出：§5.5 "The budget ablation (**2× budget grid (15/30/60 epochs, Fig. 7): …" ——
  "2×" 为 "2×-epoch ablation" 旧措辞残留（audit #33 改写时的 sed 残留），且句首两个左括号
  无闭合、句子断裂。确认成立。
- 修复（md + tex 头部同步）：
  ① "The budget ablation (2×\nbudget grid (15/30/60 epochs, Fig. 7):" →
     "The budget grid (15/30/60 epochs, Fig. 7):"（与 §2/§4.4/Fig.7 caption 命名一致，
     括号配平复核通过）；
  ② §4.2 数据协议段同源残留 "the 2×-epoch ablation uses --epochs 30" →
     "the budget-grid ablation uses --epochs 30/60"（与 15/30/60 网格口径一致）。
     （2026-09-24 用户后续指正：该句位于 §4.2 而非 §4.5；并按用户定稿措辞再改为
     "the budget ablation sweeps --epochs {15,30,60}"，tex 用 \{15,30,60\} 渲染字面花括号。）
- 全库扫描：md/tex 剩余唯一 "2×" 为 §5.7 "2×2 grid (rf300, 5 seeds)"——合法实验设计
  （2 头条件 × 2 容器组），非残留，保留。
- 验收：46 页 0 错误；PDF 抽验两处新句渲染、旧断裂串清零。

## #45 §3.2 "10,200 in total" 指代歧义改写（用户提出，2026-09-24）
- 用户指出：§3.2 "…test-only material that never enters training,\n10,200 in total." ——
  "10,200" 紧跟 900 对象转移集句子，读起来像指转移集。确认成立。
- 按用户定稿措辞改写（md+tex 头部）：
  "Each class contributes exactly 300 objects (norm E4: class balance); the formal set totals
  34 × 300 = 10,200 objects. A 900-object cross-implementation transfer set (native OpenSSL
  3.5 ML-DSA/ML-KEM, §5.10) ships alongside as test-only material that never enters training."
- 验收：46 页 0 错误；PDF 抽验新句渲染、歧义串清零。

## #46 §5.10 "frozen … retrained unchanged" 自相矛盾改写（用户提出，2026-09-24）
- 用户指出："The frozen 18-class container pipelines were retrained unchanged" ——
  frozen 与 retrained 语义矛盾（管线在冻结配置下重训，而非管线本身被冻结）。确认成立。
- 按用户定稿措辞改写（md 尾部，build_tail 重建 tex）：
  "The 18-class container pipelines were retrained under the frozen configuration (§5.4)
  and evaluated on this set: …"。
- 验收：46 页 0 错误；PDF 抽验新句渲染、旧矛盾串清零。

## #47 §5.9 闭集基线口径限定（用户提出，2026-09-24）
- 用户指出：§5.9 "P1 0.3689 → 0.3793; P2 0.5446 → 0.5474" 是 26 类开集模型的闭集基线，
  与 §5.5 的 34 类数字口径不同，易被审稿人误读；建议加限定语。采纳。
- 数据核实（编辑前）：P1/P2 closed_f1 均值 0.3689/0.5446 ✓（open_set_formal.json 5 splits）；
  箭头终点 0.3793/0.5474 = **MSP 基线 20% 拒绝档**的 f1_decay 逐种子均值（0.05/0.1 档为
  0.3715/0.3737 与 0.5449/0.5453），溯源吻合。
- 落文（md 尾部，build_tail 重建 tex）：
  ① §5.9："leaves the closed-set macro-F1 of the 26-class open-set models essentially intact
  (…, the 20% rejection endpoint of MSP)"；
  ② Table 4 的 open-set 行同源格补 "of the 26-class open-set models"。
- 顺带发现并修复的表结构问题：Table 4 的 open-set 行实际**从未进入编译**（#34 尾部重建后
  tables_formal.md 缺此行，md 镜像有——两源已漂移）。恢复时该长行致浮体超页 261pt 内容被裁：
  处置 = Table 4 改 table*（全宽）+ 行内容压缩 + 最终将 open-set 完整数字移入表注
  （表注在浮体外，无高度限制），浮体超页警告清零。表注含完整数字与 26-class 限定语，
  §5.9 正文同步含限定语与 20% 档溯源。
- 验收：46 页 0 错误、0 浮体超页警告；PDF 抽验限定语与表注渲染。

## #48 标题简化（用户提议并确认，2026-09-24）
- 用户指出三修饰语叠置（Algorithm-Level / Observable Side-Channel / Representation-Level），
  提议 "Quantifying Representation-Level Leakage of Post-Quantum Cryptographic Objects"，
  side-channel 定义留给摘要。分析后建议采纳（side-channel 有强默认义=密钥恢复攻击，标题
  即误读源；Algorithm-Level 信息在 §1/关键词/贡献(1) 无损；新题与关键词
  representation-level identification 及 §4.1 定义自洽），用户确认。
- 落文：paper.tex \title、md 首行、cover letter 标题行三处替换；
  摘要防御句（"Herein, 'side channel' means…"）与正文框架名 "observable side channels"
  （§4.1）保留不动。
- 历史：反转 #35 "标题保留 Algorithm-Level" 决定（用户本人提议，授权反转）。
- 验收：46 页 0 错误；PDF 标题渲染抽验。

## #49 §4.4 30ep/60ep 一致性核实（用户提出，2026-09-24）
- 用户报告：旧文本称 P1@30ep "every class stays below chance"，与 60ep 段落
  ML-DSA-44 P1@30ep 0.0782±0.0355 越线矛盾。
- 核实：当前 tex/PDF 中该旧句**已不存在**（#42 已改："P1@30ep overall 0.0295, with
  ML-DSA-44 the only class whose seed-mean exceeds the chance line, 0.0782±0.0355 — within
  one seed SE of chance"）；60ep 段 "below chance" 仅指 15 类聚合均值（0.0486/0.0478）。
  两处口径一致，无残留矛盾；全库 "every class stays below chance" 零残留。
- 用户的 paper.tex 编辑（"the exclusions prove necessary"，原为 "earn their keep"）已保留，
  md 镜像同步为相同措辞。
- 验收：46 页 0 错误；PDF §4.4 抽验（上引两句）。

## #50 OID 基线计数更正 12→11（用户提出，2026-09-24）
- 用户指出：§5.11 称 "12 algorithm OIDs"，但正文可枚举仅 11。核实成立：
  exp_tools_baseline.py 的 OIDS 字典恰为 11 个条目——mldsa44/65/87、mlkem512/768/1024、
  slhdsa128s/256s、rsa(rsaEncryption)、ec(ecPublicKey/SEC1)、ed25519(1.3.101.112)；
  11 个不同 OID 值覆盖全部 18 容器类（7 证书类复用同值，靠 TBS/格式标记区分）。
  历史 "12" 疑为把 prime256v1 曲线 OID 误计入算法 OID。
- 更正处：§5.11 正文（md 尾部→重建 tex）、exp_tools_baseline.py 头注释（5 行；代码内
  153 行 env 串本已是 11）、冻结文件 results/tools_baseline_formal.json 的 env 描述串
  （数值不动，仅元数据更正）、audit #31 中英记录加更正注。
- 验收：重编译后 PDF §5.11 显示 11；F1 数值不变（0.0555/0.4443/1.0000/0.5000/0）。

## #51 发布包整理（GitHub 上传前，用户提出，2026-09-25）
- AI 标记清除：全量扫描上传集（py/md/json），claude/deepseek/LLM/子代理/subagent 等零残留
  （随稿日志中的"子代理"措辞改为"独立审读"；"长度代理"为统计术语，保留）。
- 注释精简：19 个脚本头注释压至 1-3 行（保留协议关键常数与 audit 编号引用）；
  train_baselines 行内叙事注释压短。
- 路径可移植：全部硬编码 /home/shen、/root/pqc 改为 __file__ 相对路径；liboqs/SSH 外部
  路径改环境变量；nist_battery.py 收编进 host_package/；wild 误报证书与 B4 跨库原始
  JSON 收编进仓库（wild/raw/ct_log/、data/b4_crosslib_final/）；rental_snapshot 引用改指
  results/（5 个 mixed-34 rf_p1 冻结种子已复制入 results/）。
- 凭据清理：全量扫描无密码/私钥/SSH 连接串残留（租机主机名已中性化）。
- 新增：LICENSE（MIT）、data/LICENSE.md（CC BY 4.0）、README.md。
- 顺带修复：用户编辑的 paper.tex 分支把审计计数回退为 48（日志实为 50），已同步 50；
  重建后 45 页 0 错误。

## #52 工作流移交：paper.tex 成为唯一源（用户决议，2026-09-25）
- 用户重组 paper.tex/supplementary.tex 并完成双 Zenodo DOI（数据集 22950765 CC BY 4.0、
  代码快照 22952070 MIT），宣布此后全部由助手管理、不再亲自接管。
- 新工作流：paper.tex = 稿件唯一源；build_tail.py 退役（改为直接中止防误跑）；
  paper_manuscript_en.md 标注 deprecated 仅存档；verify_paper_consistency.py 成为新防线
  （审计计数/文献闭环/提交文件计数，只检查不改文件）。
- 接管验收：42 页 0 错误 0 undefined；bib 50 条全引 0 orphan；两个 Zenodo 记录经 API
  验证（标题/作者/许可/日期）。

## #53 图件移交：七图外部重绘（用户决议，2026-09-25）
- 用户请外部设计师重绘 7 张正文图并拷回 figures/（fig1-7 替换；GA 未动）。
- 接管检查：全部矢量字体嵌入（fig4/fig5 含热图栅格块属正常）；文件名与 tex 引用一致；
  文本可核对数字与冻结一致（fig1 z=17/70/500/616/467；fig7 树基线 RF 0.281/0.290、
  HGB 0.413/0.424、chance 1/34=0.029；fig2 分组与 11 格齐全）；曲线数值为矢量路径，
  按约定以 results/ JSON 为唯一数值源（新图豁免 figs_qa 文本校验）。
- make_all_figs.py 退役加中止保护（防覆盖外部重绘图）；figs_qa.py 不再自动重绘。
- 验收：重编译 0 错误；verify_paper_consistency ALL PASS。

## #54 补两条关键引用（用户提出，2026-09-25）
- ①PQClean 引用缺失：正文 4 次 + 图注/表 3 次提及但 bib 无条目（关键对照实验）——补
  @misc{pqclean}（Kannwischer/Rijneveld/Schwabe/Stebila/Wiggers + contributors，GitHub 项目
  规范署名，2019），首次正文提及（§5.2 PQClean leg）挂 \cite；摘要不引（惯例）。
- ②缺失重要相关工作：Mallick et al., "Classifying Implementations of Cryptographic
  Primitives and Protocols that Use Post-Quantum Algorithms"（arXiv:2503.17830 v4，2025）——
  补 @misc{mallick2025classifying}，Related Work 在 PQClass 句后加两句区分：
  实现行为 vs 表示层、检测准确率 vs 逐信道零带界、完整协议流 vs 雕刻/加密/遥测受限场景。
- 验收：bib 52 条全引 0 orphan、0 undefined；42 页 0 错误；防线 ALL PASS。

## #55 补三条脉络引用（用户提出，2026-09-25）
- ①Shamir & van Someren 1999（FC/LNCS 1648, pp.118-124, DOI 10.1007/3-540-48390-X_9）：
  §2 雕刻段新增继承句（stored-key search → S1 表示层后裔）。
- ②Liberatore & Levine 2006（CCS, pp.255-263, DOI 10.1145/1180405.1180437——注意：初拟
  DOI 1180417 经 Crossref 核出是 Curtmola 另一篇，已纠正）：§2 流量段新增 website
  fingerprinting 继承句（包长统计→页面身份，S2 长度信道隐私语义的脉络）。
- ③Dyer et al. 2012（S&P, pp.332-346, DOI 10.1109/SP.2012.28）：§6 填充小节呼应句
  （高效填充防御同样无法移除长度信息，与格点填充结论对话）。
- 全部元数据经 Crossref 核实；零实验改动。
- 验收：bib 55 条全引 0 orphan、0 undefined；43 页 0 错误；防线 ALL PASS。

## #56 弱化归纳偏置声明 + 交代架构选择（用户提出，2026-09-25）
- 用户指出：§2 "first controlled evidence that ... inductive-bias-dependent" 过强——
  标量 BiLSTM 在近均匀长序列上失败不意外；前作 5 基线含 Byte Transformer，本文仅
  CNN/BiLSTM，审稿人必问架构选择。采纳最小路径（弱化+交代，不补实验）。
- 三处落文：
  ① §2 声明限定："...first controlled evidence, for cryptographic payloads, that the two
  depth architectures we test --- a local-pattern CNN and a scalar-input BiLSTM --- diverge at
  a frozen budget; ... within the tested pair, not a claim over the architecture space."
  ② §5.5 补架构选择说明（CNN=标准原始字节基线 + BiLSTM=长序列递归对照；Byte
  Transformer 在前作 \cite{CipherBench}，不在本冻结网格——deliberate scope decision）。
  ③ Limitations 增补：深架构集由冻结协议固定（RF/HGB/CNN/BiLSTM），其他族是否恢复信号
  留待后续。
- 备选强路径（补 Transformer 实验：需重租 GPU + 新冻结档）已记录，留作审稿回应预案。
- 验收：44 页 0 错误 0 undefined；防线 ALL PASS。

## #57 E1–E14 全文进补充材料（用户提出，2026-09-25）
- 用户指出：§4.5 只说"catalogue ships with the release"，审稿人看不到 14 条全文；
  并在 pqc_wave2 找到冻结版原文（v2.4 实验规范）。
- 核对：14 条中 11 条与现论文完全一致，4 条部分一致（已对齐措辞：E1 扫描→块尺寸网格
  {512,1024,4096}；E4 独立性→迁移集留出；E5 语料级留出→迁移集表述；E6 accuracy→
  macro-F1 为主+组级折叠；E10 短/长分组删除），2 处 wave2 内部案例号（#12/#13）已删。
- 落点（用户选 B）：supplementary.tex 新增 S-0 节全文 14 条（enumerate 格式）；
  §4.5 改为 "The full E1–E14 catalogue appears in Supplement S-0"。
- 验收：supplementary.pdf 3 页、paper 44 页，均 0 错误；S-0 渲染抽验 14 条全在、
  无内部案例号残留、§4.5 指针落位。

## #58 文末 AI 使用声明（用户提供措辞，2026-09-25）
- 按 Elsevier 政策在 References 之前新增一节 "Declaration of generative AI and AI-assisted
  technologies in the manuscript preparation process"，措辞采用用户原文（DeepSeek-V4-Pro：
  中英翻译与 LaTeX 排版协助；作者审校并对内容负全责）。
- 验收：44 页 0 错误 0 undefined；声明渲染抽验通过。

## #59 Funding 声明更新（用户提供，2026-09-25）
- 用户提供资助信息：Academic Degrees and Graduate Education Development Center, MOE
  （grant ZT-2511417005，项目 ZhiTu WangAn: Intelligent Penetration Testing System...）。
- 处置：删除旧"无特定资助"Funding 节，新 Funding 节按用户要求置于 AI 使用声明之前
  （References 之前）；项目名用 LaTeX 双引号排版；submission_checklist B4 同步。
- 验收：44 页 0 错误 0 undefined；grant 号与项目名渲染、旧无资助句清零。

## #60 三处排版修复（2026-09-25，用户指定：只改排版与记号，不动数值/内容）
- Table 3（Wild set）：窄 p{} 列中不可断长串溢出导致三处文字重叠（OID 串撞 intact/OID-erased、
  域名撞 1404 B、P=0.18–0.28 撞 OID）。处置：OID（2.16.840.1.101.3.4.3.19、
  1.2.840.113549.1.1.5）与域名（vpn.dilithiumnetworks.com）逐段插入 \allowbreak 断点；
  列宽改 0.18/0.10/0.07/0.16/0.24/0.15（总和 0.90）。验收：PDF 程序化检测——长串全部在位、
  表区文本 span 两两 bbox 无重叠（NONE）。
- Figure 6（λ 梯子）：x 刻度 0.0625 与 0.125 标签重叠。处置：删 0.0625 刻度，保留
  0/0.125/0.25/0.5/1.0 + 宽频带 1.06/1.12（无标签）；新脚本 figures/make_fig6.py
  （冻结数据 figs_data.get_ladder，断言全过）。验收：PDF 含 0.125、无 0.0625、无重叠。
- Figure 5（长度折叠矩阵）：图幅 489.6pt 经 width=\linewidth(390pt) 缩至 0.97×，标签仅 ~4.3pt。
  处置：图幅改 390×344pt（整行宽），刻度字号 4.2→7pt；新脚本 figures/make_fig5.py
  （冻结 nn_len_seed42.json 行归一化矩阵逐点一致）。验收：编译后 PDF 实测标签 6.91pt ≥ 6pt，
  矢量 PDF 输出（fonttype 42）。图题未动，与新图一致。
- Table 4（capability–leakage map）：
  (a) C_struct×S3 的 "G=16/64"（舍入步长）与 §5.3/Fig 1 的 G（长度等价类个数）撞符号
      → 改为 "∆=16/64"，全文搜索确认 G=16/64 清零（§5.3/Fig 1 的 G 保留不动）。
  (b) C_bytes×S1 "z ≤ 1.1 / ≤ 5.9" 补标注 → "(trunc50 z ≤ 1.1; slide50 z ≤ 5.9)"（与 §5.8 一致）。
  (c) 各单元格按语义短句 \newline 分行；长数值串（0.548/0.383/0.314 等）斜杠后加 \allowbreak。
      验收：∆/标签/数值全部在位，表区无重叠，G=16/64 清零。
- 全部改动仅排版与记号；任何冻结数值未动。编译 44 页 0 错误 0 undefined。

## #61 七图二次重绘交付（2026-09-26，外部设计师重绘替换全部 7 图 PDF；GA 未动）
- 新文件同文件名替换（fig1–fig7 .pdf，23:40 交付）；GA（graphical_abstract.pdf）仍为 make_ga.py
  脚本产物、未被替换，banner 60-case 在位。
- 重编译验收：43 页（新图更小，少 1 页）、0 错误 0 undefined；Table 3/4 重叠检测仍 NONE。
- QA 逐图程序化核验（与冻结数据/文字锚点比对）：
  · fig1 z 标注 17/70/500/616/467 = 冻结值 ✓；fig7 RF 0.281/HGB 0.290 = 0.2808/0.2903 ✓；
    fig4 排序（4 签名类在前）✓；fig6 刻度 0/0.0625/0.125/0.25/0.5/1.0 间距 ≥26pt 无重叠 ✓；
    fig5 标签 6.5pt×390/388.8 ≈ 6.52pt ≥ 6pt ✓；fig2 标注 n=5 seeds 与冻结 JSON（n=5）一致
    （旧图 n=2 系过期标注，本次修正 ✓）。
- 待处理项（设计师侧，已记录待用户裁决）：
  (1) fig5 两个 x 轴标签 aes256gcm_ct_768/784 首字符 'a' 被裁掉（标签顶 357.5pt > 页面 356.4pt，
      tight-crop 切边）→ 现渲染为 es256gcm_ct_768/784；
  (2) fig5 无坐标轴标题（旧版有 'predicted (classes ordered by length)' / 'true'）；
  (3) 全部 7 图为 Type3 字体（DejaVuSans，fonttype 默认 3）——Elsevier 生产流程对 Type3 敏感，
      建议 fonttype=42 重导出；fig6 x 轴标签缺 λ 符号（现为 'signal density (class-token…)'）。
- 本地方案备选：fig5 可用 figures/make_fig5.py（冻结数据、已验证、含轴题）重建；
  fig6 同理 make_fig6.py（无 0.0625 重叠、含 λ）。是否采用由用户裁决。

## #62 七图第三次重绘交付（2026-09-26，全部修复 #61 三项遗留，验收通过）
- 新 7 图 PDF 覆盖原文件（08:47 交付）。#61 遗留全部清零：
  (1) fig5 'a' 裁切已修复（aes256gcm_ct_768/784 完整渲染，标签顶不再越界）；
  (2) fig5 轴题已恢复（predicted (classes ordered by length) / true，8pt）；
  (3) 字体 Type3 → Type0（DejaVuSans 子集嵌入）；fig6 x 轴 λ 已恢复。
- 逐图 QA（冻结锚点）：fig1 z=17/70/500/616/467 ✓；fig2 n=5 seeds ✓（与冻结 JSON n=5 一致）；
  fig4 4 签名类排序 ✓；fig5 标签 6.5pt×390/388.8≈6.52pt≥6pt、轴题在位、aes 完整 ✓；
  fig6 λ 在位、0/0.0625/0.125/0.25/0.5/1.0 相邻间距≥26pt 无重叠、宽频带标记在位 ✓；
  fig7 RF 0.281/HGB 0.290/chance 0.029 ✓。
- 重编译：43 页、0 错误 0 undefined；Table 3/4 重叠检测 NONE；verify 全过。
- 说明：figures/make_fig5.py、make_fig6.py 与 make_all_figs.py 均为历史脚本，现行 7 图以
  设计师交付文件为准（手管文件，勿运行覆盖）。

## #63 历史画图脚本清理（2026-09-26）
- 删除 figures/ 下全部历史画图工具链：make_all_figs.py（退役中止版）、make_fig5.py、
  make_fig6.py、figs_data.py、figs_qa.py、figstyle.py、gen_tables.py 及 __pycache__；
  同时清理 /home/shen/tools/ 下的反编译恢复件（pycdc、make_all_figs_recovered.py）。
- 保留：figures/make_ga.py（GA 生成器，verify 守卫与计数链仍依赖）；7 图 PDF 及
  QA_交付报告.md。7 张 PNG 预览已从定稿 PDF 重新导出（300dpi），与 PDF 一致。
- 验收：GA 可再生成、verify_paper_consistency ALL PASS、paper 重编译 0 错误。
