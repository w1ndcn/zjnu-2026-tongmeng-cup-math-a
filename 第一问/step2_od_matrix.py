"""
步骤二：生成 OD 需求矩阵（v2 — 引力模型 + 距离阶梯方式划分 + 题目满载率）
输入: step1 的 distance_matrix.csv, node_order.txt
输出: 3时段 × 4方式(p/b/c/bus) 的 60×60 OD 矩阵
"""

import numpy as np
import pandas as pd
import os

STEP1_DIR = "output_step1"
OUTPUT_DIR = "output_step2"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════ 1. 建筑属性 ═══════════════════
# capacity: 该建筑能容纳的最大人数（用于引力模型的吸引力 D_j）
# 宿舍=床位数, 教学楼=教室容量, 食堂=座位数
building_capacity = {
    'T_16_E': 2000, 'T_16_W': 2000, 'T_25': 1500,   # 教学楼
    'D_T': 1500,    'D_X': 2200,    'D_C': 1800, 'D_G': 2000,  # 宿舍
    'C_T': 800,     'C_X': 800,     'C_G': 500,  'C_S': 1200,  # 食堂+商业街
}

# ═══════════════════ 2. 满载率（题目数据说明第2条） ═══════════════════
# 平峰30%  次高峰50%  绝对高峰80%-100%
peak_load = {
    'morning': 0.90,   # 7:30-8:15 绝对高峰
    'noon':    1.00,   # 11:40-12:30 绝对高峰
    'evening': 0.50,   # 17:20-18:00 次高峰
}

# ═══════════════════ 3. 引力模型参数 ═══════════════════
GAMMA = 1.5   # 距离衰减系数（校园尺度，1.0~2.0 合理）

# ═══════════════════ 4. 距离阶梯方式划分 ═══════════════════
# 根据 OD 距离 d(米) 确定各方式占比
# bus（接驳车）暂为 0%，为步骤三/四预留接口
def mode_split(distance_m):
    """返回 {p, b, c, bus} 占比，总和=1"""
    if distance_m < 500:
        return {'p': 0.70, 'b': 0.25, 'c': 0.05, 'bus': 0.00}
    elif distance_m < 1000:
        return {'p': 0.35, 'b': 0.55, 'c': 0.10, 'bus': 0.00}
    elif distance_m < 1500:
        return {'p': 0.15, 'b': 0.70, 'c': 0.15, 'bus': 0.00}
    else:
        return {'p': 0.05, 'b': 0.75, 'c': 0.20, 'bus': 0.00}

MODES = ['p', 'b', 'c', 'bus']

# ═══════════════════ 5. 加载节点顺序和距离矩阵 ═══════════════════
node_order_file = os.path.join(STEP1_DIR, "node_order.txt")
with open(node_order_file, "r") as f:
    all_nodes = [line.strip() for line in f if line.strip()]
n = len(all_nodes)
idx = {name: i for i, name in enumerate(all_nodes)}

# 距离矩阵（纯数值，无表头）
D_full = np.loadtxt(os.path.join(STEP1_DIR, "distance_matrix.csv"), delimiter=",")

# 提取建筑节点间的距离子矩阵
building_nodes = [n for n in all_nodes if not n.startswith("J_")]
b_idx = {name: i for i, name in enumerate(building_nodes)}
b_dist = np.zeros((len(building_nodes), len(building_nodes)))
for i, bi in enumerate(building_nodes):
    for j, bj in enumerate(building_nodes):
        b_dist[i][j] = D_full[idx[bi]][idx[bj]]

print(f"全路网: {n} 节点  |  建筑: {len(building_nodes)} 个")
print(f"引力模型 γ={GAMMA}  |  满载率: {peak_load}")

# ═══════════════════ 6. 引力模型 OD 生成 ═══════════════════
def generate_od_gravity(sources, targets, load_factor, period_name):
    """
    引力模型:
      T_ij = O_i × (D_j × d_ij^(-γ)) / Σ_k(D_k × d_ik^(-γ))
      O_i = building_capacity[source] × load_factor  (产生量)
      D_j = building_capacity[target]                (吸引力)
    """
    od = {m: np.zeros((n, n)) for m in MODES}

    for s in sources:
        if s not in idx:
            continue
        O_i = building_capacity.get(s, 0) * load_factor

        # 计算 s 到所有 targets 的引力权重
        weights = {}
        total_weight = 0.0
        for t in targets:
            if t not in idx:
                continue
            d = b_dist[b_idx[s]][b_idx[t]]
            if d <= 0:
                d = 1  # 防止除零（自身）
            D_j = building_capacity.get(t, 0)
            w = D_j * (d ** (-GAMMA))
            weights[t] = w
            total_weight += w

        if total_weight == 0:
            continue

        # 分配流量
        for t in targets:
            if t not in weights:
                continue
            frac = weights[t] / total_weight
            demand = O_i * frac  # 从 s 到 t 的总人数

            d_ij = b_dist[b_idx[s]][b_idx[t]]
            modes = mode_split(d_ij)
            for mode in MODES:
                od[mode][idx[s]][idx[t]] = demand * modes[mode]

    return od

# ═══════════════════ 7. 三个时段生成 ═══════════════════
periods = {
    'morning': {
        'sources': ['D_T', 'D_X', 'D_C', 'D_G'],
        'targets': ['T_16_E', 'T_16_W', 'T_25'],
        'load': peak_load['morning'],
        'desc': '宿舍 → 教学楼',
    },
    'noon': {
        'sources': ['T_16_E', 'T_16_W', 'T_25'],
        'targets': ['C_T', 'C_X', 'C_G', 'C_S'],
        'load': peak_load['noon'],
        'desc': '教学楼 → 食堂/商业街',
    },
    'evening': {
        'sources': ['T_16_E', 'T_16_W', 'T_25'],
        'targets': ['D_T', 'D_X', 'D_C', 'D_G'],
        'load': peak_load['evening'],
        'desc': '教学楼 → 宿舍',
    },
}

for period_name, cfg in periods.items():
    od = generate_od_gravity(cfg['sources'], cfg['targets'], cfg['load'], period_name)

    # 保存各方式矩阵
    for mode in MODES:
        df = pd.DataFrame(od[mode], index=all_nodes, columns=all_nodes)
        df.to_csv(os.path.join(OUTPUT_DIR, f"od_{period_name}_{mode}.csv"))

    # 汇总
    total = sum(od.values())
    df_total = pd.DataFrame(total, index=all_nodes, columns=all_nodes)
    df_total.to_csv(os.path.join(OUTPUT_DIR, f"od_{period_name}_total.csv"))

    # 打印摘要
    print(f"\n{'─'*50}")
    print(f"{period_name:8s}  {cfg['desc']}")
    print(f"  满载率: {cfg['load']:.0%}  |  总需求: {total.sum():.0f} 人次")
    print(f"  各方式: p={od['p'].sum():.0f}  b={od['b'].sum():.0f}  c={od['c'].sum():.0f}  bus={od['bus'].sum():.0f}")

    # 打印引力分配详情
    print(f"  引力分配矩阵 (前5个OD):")
    printed = 0
    for s in cfg['sources']:
        for t in cfg['targets']:
            if s in idx and t in idx:
                val = total[idx[s]][idx[t]]
                if val > 0.1:
                    d = b_dist[b_idx[s]][b_idx[t]]
                    pct = val / total.sum() * 100
                    print(f"    {s:8s} → {t:8s}  d={d:5.0f}m  q={val:6.0f}人 ({pct:5.1f}%)")
                    printed += 1
                    if printed >= 12:
                        break
        if printed >= 12:
            break

print(f"\n{'='*50}")
print(f"输出: {OUTPUT_DIR}/  (3时段 × 5文件 = 15个)")
print(f"方式: p=步行 b=电动车 c=机动车 bus=接驳车(预留)")
