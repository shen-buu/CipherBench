#!/usr/bin/env python3
"""Read-only four-layer audit over results/*.json (hygiene / structure / headline cross-check / outliers). Output: results/data_audit_report.json."""
import os, json, glob, math, platform, datetime
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
RES = os.path.join(BASE, "results")
RENT = os.path.join(BASE, "rental_snapshot", "pqc", "results")
SEEDS5 = [7, 42, 99, 123, 2024]
FLAGS = []


def flag(layer, cid, msg, detail=None):
    FLAGS.append({"layer": layer, "id": cid, "msg": msg, "detail": detail})
    print(f"[FLAG {layer} {cid}] {msg}", flush=True)


def load(p):
    return json.load(open(p))


def walk_nums(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk_nums(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk_nums(v, f"{path}[{i}]")
    elif isinstance(o, (int, float)):
        yield path, o


# ================= L1：JSON 卫生 =================
print("== L1 JSON hygiene ==", flush=True)
files = sorted(glob.glob(os.path.join(RES, "*.json")))
print(f"results/*.json: {len(files)} files", flush=True)
for f in files:
    name = os.path.basename(f)
    try:
        d = load(f)
    except Exception as e:
        flag("L1", "parse", f"unparseable {name}: {e}")
        continue
    for path, v in walk_nums(d):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            flag("L1", "nan", f"{name}{path} = {v}")
        if "f1" in path.lower() and isinstance(v, float) and not (0.0 <= v <= 1.0 + 1e-9):
            flag("L1", "range", f"{name}{path} = {v} out of [0,1]")

# ================= L2：结构一致性 =================
print("== L2 structural consistency ==", flush=True)
for f in files:
    name = os.path.basename(f)
    d = load(f)
    if isinstance(d, dict) and "macro_f1" in d and isinstance(d.get("per_class_f1"), dict) and d["per_class_f1"]:
        pcm = float(np.mean(list(d["per_class_f1"].values())))
        if abs(d["macro_f1"] - pcm) > 1e-9:
            flag("L2", "macro_perclass", f"{name}: macro {d['macro_f1']:.6f} != mean(per_class) {pcm:.6f}")
    if isinstance(d, dict) and "seeds" in d:
        n = len(d["seeds"]) if isinstance(d["seeds"], list) else None
        if n and n != 5:
            flag("L2", "seedcount", f"{name}: seeds={d['seeds']}")
    # SE = SD/sqrt(n) 一致性（凡同时含 mean/sd/se/n 的块）
    def check_se(o, path=""):
        if isinstance(o, dict):
            if "mean" in o and "sd" in o and "se" in o and isinstance(o["n"] if "n" in o else None, int):
                expect = o["sd"] / math.sqrt(o["n"])
                if abs(o["se"] - expect) > 1e-9:
                    flag("L2", "se_consistency", f"{name}{path}: se {o['se']} != sd/sqrt(n) {expect}")
            for k, v in o.items():
                check_se(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                check_se(v, f"{path}[{i}]")
    check_se(d)

# per-seed 5 文件完整性（per-seed JSON 组）
groups = {}
for f in files:
    name = os.path.basename(f)
    import re as _re
    m = _re.match(r"(.+)_seed(\d+)(.*)\.json", name)
    if m:
        groups.setdefault(m.group(1) + m.group(3), set()).add(int(m.group(2)))
for g, seeds in sorted(groups.items()):
    if seeds == set(SEEDS5):
        continue
    if seeds and seeds <= set(SEEDS5):
        missing = sorted(set(SEEDS5) - seeds)
        if not g.endswith("_smoke"):
            flag("L2", "seed_complete", f"group '{g}': missing seeds {missing}")

# ================= L3：论文口径核对 =================
print("== L3 headline cross-check ==", flush=True)

def ck(cid, got, want, tol=5e-5, note=""):
    ok = abs(got - want) <= tol
    if not ok:
        flag("L3", cid, f"{note or cid}: got {got:.6f} want {want:.6f} (Δ={got-want:+.6f})")
    return ok


def seeds_stat(prefix, suffix=""):
    vals = []
    for s in SEEDS5:
        p = os.path.join(RES, f"{prefix}_seed{s}{suffix}.json")
        if not os.path.exists(p):
            p = os.path.join(RENT, f"{prefix}_seed{s}{suffix}.json")
        vals.append(load(p)["macro_f1"])
    return float(np.mean(vals)), float(np.std(vals))


d_s2s3 = load(os.path.join(RES, "s2s3_formal.json"))
s2 = d_s2s3["s2"]
ck("S2-inner", s2["inner"]["f1"], 0.9262, note="S2 inner 0.9262")
ck("S2-none", s2["none"]["f1"], 0.9262, note="S2 outer none (ct=len+16) 0.9262")
ck("S2-rand255", s2["rand255"]["f1"], 0.5766, note="S2 rand255 0.5766")
ck("S2-rand1024", s2["rand1024"]["f1"], 0.3173, note="S2 rand1024 0.3173")
s3 = d_s2s3["s3"]
LADDER = {"exact": (0.9260, 0.9262, 46, 0.0261, 0.0019, 467),
          "round16": (0.8824, 0.8480, 31, 0.0261, 0.0013, 616),
          "round64": (0.7647, 0.7176, 26, 0.0256, 0.0014, 500),
          "log2bin": (0.2938, 0.1716, 10, 0.0216, 0.0021, 70),
          "size_class": (0.1466, 0.0461, 5, 0.0166, 0.0017, 17)}
for lv, (b, n, g, nm, ns, z) in LADDER.items():
    v = s3[lv]
    ck(f"S3-{lv}-beta", v["beta"], b, 5e-4, note=f"β({lv})")
    ck(f"S3-{lv}-nn", v["nn_f1"], n, 5e-4, note=f"1-NN({lv})")
    if v["G"] != g:
        flag("L3", f"S3-{lv}-G", f"G={v['G']} want {g}")
    ck(f"S3-{lv}-null", v["nn_null_mean"], nm, 5e-4, note=f"null({lv})")
    ck(f"S3-{lv}-nullsd", v["nn_null_std"], ns, 5e-4, note=f"null SD({lv})")
    zcalc = round((v["nn_f1"] - v["nn_null_mean"]) / v["nn_null_std"])
    if zcalc != z:
        flag("L3", f"S3-{lv}-z", f"z trunc = {zcalc} want {z}")

d_s1 = load(os.path.join(RES, "s1_formal_summary.json"))
S1Q = {"intact": 0.9997, "oid_zero": 0.9998, "oid_rand": 0.9998, "head48": 0.8827,
       "head24": 0.8861, "trunc25": 0.5478, "trunc50": 0.3831, "trunc75": 0.3139,
       "slide25": 0.8859, "slide50": 0.6126, "slide75": 0.6137}
for k, w in S1Q.items():
    ck(f"S1-{k}", d_s1[k]["mean"], w, 5e-4, note=f"S1 {k}")
    if d_s1[k]["n"] != 5:
        flag("L3", f"S1-{k}-n", f"n={d_s1[k]['n']} want 5")

d_pp = load(os.path.join(RES, "prim_perclass_formal.json"))
ck("prim-P1-macro", d_pp["p1"]["macro_mean"], 0.0744, 5e-4, note="prim P1 0.0744")
ck("prim-P2-macro", d_pp["p2"]["macro_mean"], 0.0756, 5e-4, note="prim P2 0.0756")
ck("prim-P1-ecdsa", d_pp["p1"]["per_class_mean"]["ecdsa_p256_sig"], 0.2508, 5e-4, note="ECDSA P1 0.2508")
ck("prim-P1-ed25519", d_pp["p1"]["per_class_mean"]["ed25519_sig"], 0.0713, 5e-4, note="Ed25519 0.0713")
mx_p2 = max((v, k) for k, v in d_pp["p2"]["per_class_mean"].items() if k != "ecdsa_p256_sig")
ck("prim-P2-maxnonecdsa", mx_p2[0], 0.0813, 5e-4, note=f"max non-ECDSA P2 ({mx_p2[1]})")
# 15 类均值（去 ECDSA）
m15 = float(np.mean([v for k, v in d_pp["p1"]["per_class_mean"].items() if k != "ecdsa_p256_sig"]))
ck("prim-P1-non15", m15, 0.0626, 5e-4, note="P1 15-class 0.0626 = null center")

d_b4 = load(os.path.join(RES, "b4_pqclean_leg.json"))
if "pqclean" in d_b4:
    pq = d_b4["pqclean"]
    ck("pqclean-whole", pq["whole"]["mean"], 0.490, 5e-3, note="PQClean whole 0.490")
    ck("pqclean-win", pq["window"]["mean"], 0.509, 5e-3, note="PQClean window 0.509")

# mixed-34 基线（15ep 冻结）
m34 = {}
for arch, sc in [("rf", "p1"), ("hgb", "p1"), ("cnn", "p1"), ("bilstm", "p1"), ("cnn", "p2"), ("bilstm", "p2")]:
    m, s = seeds_stat(f"{arch}_{sc}", "")
    m34[f"{arch}_{sc}"] = (m, s)
M34Q = {"rf_p1": 0.2808, "hgb_p1": 0.2903, "cnn_p1": 0.2075, "bilstm_p1": 0.0233,
        "cnn_p2": 0.3415, "bilstm_p2": 0.0370}
for k, w in M34Q.items():
    ck(f"m34-{k}", m34[k][0], w, 5e-3, note=f"mixed-34 {k} mean")
SD34Q = {"cnn_p1": 0.0083, "cnn_p2": 0.0237, "bilstm_p1": 0.0061, "bilstm_p2": 0.0080}
for k, w in SD34Q.items():
    ck(f"m34-{k}-sd", m34[k][1], w, 5e-3, note=f"mixed-34 {k} seed SD")

# budget grid e30/e60（mixed-34）
for tag, Q in [("_e30", {"cnn_p1": 0.2832, "cnn_p2": 0.4590}),
               ("_e60", {"cnn_p1": 0.3181, "cnn_p2": 0.4999})]:
    for k, w in Q.items():
        arch, sc = k.split("_")
        m, s = seeds_stat(f"{arch}_{sc}", tag)
        ck(f"grid-{tag[1:]}-{k}", m, w, 5e-3, note=f"budget grid {tag} {k}")

# prim 60ep（#42 新冻结）
d60 = load(os.path.join(RES, "prim60_summary_formal.json"))
for sc, (m, sd) in [("p1", (0.0547, 0.0054)), ("p2", (0.1056, 0.0040))]:
    ck(f"prim60-{sc}-macro", d60["scenes"][sc]["macro"]["mean"], m, 5e-4, note=f"prim60 {sc}")
    ck(f"prim60-{sc}-ecdsa", d60["scenes"][sc]["ecdsa_f1"]["mean"], {"p1": 0.1468, "p2": 0.9715}[sc], 5e-4, note=f"prim60 ECDSA {sc}")

# padding / prior-skew / slide50（#39/#40/#41 新冻结）
d_pad = load(os.path.join(RES, "padding_design_formal.json"))
ck("pad-overall", d_pad["aggregate"]["overall_ratio"], 1.671, 1e-3, note="padding 1.671×")
ck("pad-uniform", d_pad["aggregate_uniform_max"]["overall_ratio"], 8.263, 1e-3, note="uniform 8.263×")
for lv, b in [("exact", 0.1469), ("log2bin", 0.1176), ("size_class", 0.0593)]:
    ck(f"pad-{lv}", d_pad["ladder_padded"][lv]["beta"], b, 5e-4, note=f"padded β'({lv})")
ck("pad-uni-beta", d_pad["ladder_uniform_max"]["exact"]["beta"], 0.0296, 5e-4, note="uniform β'=1/34")

d_sk = load(os.path.join(RES, "prior_skew_formal.json"))
for ch, pr, w in [("C_len", "skew80_20", 0.9744), ("C_len", "skew95_5", 0.9924),
                  ("C_bytes", "skew80_20", 0.4586), ("C_bytes", "skew95_5", 0.5214)]:
    vals = [d_sk["channels"][ch][str(s)][pr]["weighted_f1"] for s in SEEDS5]
    ck(f"skew-{ch}-{pr}", float(np.mean(vals)), w, 5e-3, note=f"prior skew {ch} {pr} W")

d_att = load(os.path.join(RES, "slide50_perclass_attribution.json"))
rf_m15 = d_att["summary"]["rf"]["macro_without_ecdsa_mean"]
ck("att-rf-15", rf_m15, 0.0754, 5e-3, note="slide50 rf 15-class")
ck("att-hgb-15", d_att["summary"]["hgb"]["macro_without_ecdsa_mean"], 0.0782, 5e-3, note="slide50 hgb 15-class")
ck("att-rf-mldsa44", d_att["summary"]["rf"]["per_class_mean"]["mldsa44_sig"], 0.1872, 5e-3, note="slide50 rf ML-DSA-44")

# ---- §5.6-5.11 冻结档 ----
d_al = load(os.path.join(RES, "align_order.json"))["c_align"]
for k, w in [("A2_B512", 0.8748), ("A2_B1024", 0.8687), ("A2_B4096", 0.8334),
             ("A2_nt_B512", 0.3768), ("A2_nt_B1024", 0.2372), ("A2_nt_B4096", 0.0907)]:
    ck(f"align-{k}", d_al[k]["mean"], w, 5e-4, note=f"C_align {k}")

d_os = load(os.path.join(RES, "open_set_formal.json"))
for mname, w in [("msp", 0.8307), ("entropy", 0.8064)]:
    vals = [d_os["splits"][str(s)]["p2"]["baselines"][mname]["auroc"] for s in SEEDS5]
    ck(f"openset-p2-{mname}", float(np.mean(vals)), w, 5e-4, note=f"open-set P2 {mname} AUROC")

d_tls = load(os.path.join(RES, "tls_records_formal.json"))
ck("tls-macro", d_tls["macro_f1"], 0.9262, note="TLS record 0.9262")
if d_tls["std"] != 0.0:
    flag("L3", "tls-std", f"TLS std={d_tls['std']} want 0.0")

d_tools = load(os.path.join(RES, "tools_baseline_formal.json"))["conditions"]
ck("tools-libmagic", d_tools["intact"]["libmagic"]["macro_f1"], 0.0555, 1e-4, note="libmagic 0.0555")
ck("tools-oid-intact", d_tools["intact"]["oid"]["macro_f1"], 1.0000, 1e-4, note="OID intact 1.0000")
ck("tools-oid-zero", d_tools["oid_zero"]["oid"]["macro_f1"], 0.5000, 1e-4, note="OID oid_zero 0.5000")
for cond in ["head48", "trunc50"]:
    for tool in ["libmagic", "oid"]:
        ck(f"tools-{cond}-{tool}", d_tools[cond][tool]["macro_f1"], 0.0, 1e-9, note=f"{cond} {tool} 0")

d_b4 = load(os.path.join(RES, "b4_pqclean_leg.json"))
ck("b4-whole", d_b4["whole_object_bytes"]["grand_mean"], 0.490, 5e-3, note="B4 whole 0.490")
ck("b4-whole-sd", d_b4["whole_object_bytes"]["between_realization_std"], 0.026, 3e-3, note="B4 whole SD 0.026")
ck("b4-whole-se", d_b4["whole_object_bytes"]["SE"], 0.0081, 3e-3, note="B4 whole SE 0.0081")
ck("b4-win", d_b4["window_bytes"]["grand_mean"], 0.509, 5e-3, note="B4 window 0.509")
ck("b4-win-se", d_b4["window_bytes"]["SE"], 0.0055, 3e-3, note="B4 window SE 0.0055")
if not (d_b4["cross_verify"]["pqclean_sign_liboqs_verify"] and d_b4["cross_verify"]["liboqs_sign_pqclean_verify"]):
    flag("L3", "b4-crossverify", "cross_verify flags false")

d_tr = load(os.path.join(RES, "oqs_transfer_formal.json"))["scenes"]
def tr_macro(scene, side):
    per = d_tr[scene]["per_seed"]
    vals = [float(np.mean(list(per[str(s)][side].values()))) for s in SEEDS5]
    return float(np.mean(vals)), float(np.std(vals))
for sc, side, wm, wsd in [("s1", "test_pc", 0.9992, 0.0003), ("p2", "test_pc", 0.7494, 0.0085),
                          ("p1", "test_pc", 0.4589, 0.0195), ("s1", "ref_pc", 0.9993, 0.0009),
                          ("p2", "ref_pc", 0.6740, 0.0028), ("p1", "ref_pc", 0.3725, 0.0183)]:
    m, sd = tr_macro(sc, side)
    ck(f"tr-{sc}-{side}", m, wm, 5e-3, note=f"transfer {sc} {side}")
    ck(f"tr-{sc}-{side}-sd", sd, wsd, 5e-3, note=f"transfer {sc} {side} SD")
ck("tr-mldsa87-p2", d_tr["p2"]["test_agg"]["mldsa87_cert"]["mean"], 0.3789, 5e-3, note="mldsa87_cert P2 0.3789")

# ================= L4：异常检测 =================
print("== L4 anomaly scan ==", flush=True)
# 逐种子离群（>3×SD of others；全部 5-seed 组，排除 smoke）
import re as _re
_allgroups = {}
for _f in files:
    _m = _re.match(r"(.+)_seed(\d+)(.*)\.json", os.path.basename(_f))
    if _m and not _m.group(3).endswith("_smoke"):
        _allgroups.setdefault(_m.group(1) + _m.group(3), {})[int(_m.group(2))] = load(_f)["macro_f1"]
for g, vals in _allgroups.items():
    if len(vals) != 5:
        continue
    for s, v in vals.items():
        others = [x for k, x in vals.items() if k != s]
        m, sd = np.mean(others), np.std(others)
        if sd > 0 and abs(v - m) > 3 * sd:
            flag("L4", "seed_outlier", f"{g} seed{s}: {v:.4f} vs others {m:.4f}±{sd:.4f} ({abs(v-m)/sd:.1f}σ)")
# prim60 逐种子离群
for sc in ["p1", "p2"]:
    vals = [load(os.path.join(RES, f"cnn_{sc}_seed{s}_g_prim_e60.json"))["macro_f1"] for s in SEEDS5]
    for s, v in zip(SEEDS5, vals):
        others = [x for i, x in enumerate(vals) if i != SEEDS5.index(s)]
        m, sd = np.mean(others), np.std(others)
        if sd > 0 and abs(v - m) > 3 * sd:
            flag("L4", "prim60_outlier", f"cnn_{sc} seed{s}: {v:.4f} vs others {m:.4f}±{sd:.4f}")

out = {"protocol": "data_audit v1", "n_flags": len(FLAGS), "flags": FLAGS,
       "n_files_scanned": len(files),
       "env": {"script": os.path.basename(__file__), "python": platform.python_version(),
               "numpy": np.__version__, "date": datetime.date.today().isoformat(),
               "read_only": True, "frozen_files_modified": False}}
json.dump(out, open(os.path.join(RES, "data_audit_report.json"), "w"), indent=1)
print(f"\n== 审计完成：扫描 {len(files)} 文件，FLAG {len(FLAGS)} 项 ==", flush=True)
for f_ in FLAGS:
    print("  ", f_["layer"], f_["id"], "|", f_["msg"], flush=True)
print("→ results/data_audit_report.json", flush=True)
