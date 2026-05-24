"""
步骤二：生成 OD 需求矩阵（v3 — 扩校版 28,000人）
===============================================
输入: step1 的 distance_matrix.csv, node_order.txt
输出: 3时段 × 4方式 OD 矩阵

变更 v3:
  - 校园总人口 28,000（宿舍总容量）
  - 新增教学楼 T_1~T_10（各1,000人） + 商业街 SYJ
  - 教学楼总容量 15,000（T_16=3,000, T_25=2,000, T_1~T_10=10,000）
  - 食堂容量统一 1,100人
"""

import numpy as np
import pandas as pd
import os

STEP1_DIR = "output_step1"
OUTPUT_DIR = "output_step2"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════ 1. 建筑属性（v3 扩校版） ═══════════════════
building_capacity = {
    # 教学楼 (总计 15,000)
    'T_16': 3000,   # 16幢（精业楼）
    'T_25': 2000,   # 25幢（人文大楼）
    'T_1':  1000, 'T_2': 1000, 'T_3': 1000, 'T_4': 1000, 'T_5': 1000,
    'T_6':  1000, 'T_7': 1000, 'T_8': 1000, 'T_9': 1000, 'T_10': 1000,
    # 宿舍 (总计 28,000)
    'TYGY': 13000,  # 桃园公寓
    'XYGY': 7000,   # 杏园公寓
    'CYGY': 3000,   # 初阳公寓
    'GYGY': 5000,   # 桂苑公寓
    # 食堂 (各 1,100)
    'TYST': 1100,   # 桃园食堂
    'XYST': 1100,   # 杏园食堂
    'GYST': 1100,   # 桂苑食堂
    # 商业街
    'SYJ':  5000,   # 商业街（午高峰目的地，容量较大）
}

# 满载率（v3 更新）
peak_load = {
    'morning': 0.90,   # 早高峰宿舍出行比例
    'noon':    0.80,   # 午高峰教室出行比例
    'evening': 0.90,   # 晚高峰教室出行比例
}

GAMMA = 1.5        # 距离衰减系数
ATTENDANCE = 0.45    # 上课率（早高峰实际去上课的比例）
DEST_CAP = True      # 是否启用目的地容量约束

# ═══════════════════ 2. 方式划分（不变） ═══════════════════
def mode_split(distance_m):
    if distance_m < 500:
        return {'p': 0.70, 'b': 0.25, 'c': 0.05, 'bus': 0.00}
    elif distance_m < 1000:
        return {'p': 0.35, 'b': 0.55, 'c': 0.10, 'bus': 0.00}
    elif distance_m < 1500:
        return {'p': 0.15, 'b': 0.70, 'c': 0.15, 'bus': 0.00}
    else:
        return {'p': 0.05, 'b': 0.75, 'c': 0.20, 'bus': 0.00}

MODES = ['p', 'b', 'c', 'bus']

# ═══════════════════ 3. 加载数据 ═══════════════════
node_order_file = os.path.join(STEP1_DIR, "node_order.txt")
with open(node_order_file, "r") as f:
    all_nodes = [line.strip() for line in f if line.strip()]
n = len(all_nodes)
idx = {name: i for i, name in enumerate(all_nodes)}

D_full = np.loadtxt(os.path.join(STEP1_DIR, "distance_matrix.csv"), delimiter=",")

# 建筑节点
building_nodes = [n for n in all_nodes if not n.startswith("N")]
b_idx = {name: i for i, name in enumerate(building_nodes)}
b_dist = np.zeros((len(building_nodes), len(building_nodes)))
for i, bi in enumerate(building_nodes):
    for j, bj in enumerate(building_nodes):
        b_dist[i][j] = D_full[idx[bi]][idx[bj]]

print(f"全路网: {n} 节点  |  建筑: {len(building_nodes)} 个")
print(f"建筑: {', '.join(sorted(building_nodes))}")

# ═══════════════════ 4. 分配模型（v3: 上课率 + 容量约束 + 双模式分配） ═══════════════════
def generate_od_gravity(sources, targets, load_factor, attendance_rate=1.0,
                         alloc_mode='gravity', target_weights=None,
                         secondary_targets=None, secondary_alloc='capacity'):
    """
    生成 OD 需求矩阵。
    secondary_targets: 主目标容量不够时的溢出目的地
    """
    od = {m: np.zeros((n, n)) for m in MODES}

    # ═══════ 第一步: 主目标分配 ═══════
    raw_demand = {}  # (s,t) → float
    all_targets = list(targets) + (secondary_targets or [])
    total_target_cap = sum(building_capacity.get(t, 0) for t in targets)

    for s in sources:
        if s not in idx: continue
        O_i = building_capacity.get(s, 0) * load_factor

        if alloc_mode == 'capacity':
            if target_weights:
                custom_sum = sum(target_weights.values())
                remain_ratio = 1.0 - custom_sum
                remain_targets = [t for t in targets if t not in target_weights]
                remain_cap = sum(building_capacity.get(t, 0) for t in remain_targets)
                for t in targets:
                    if t not in idx: continue
                    if t in target_weights:
                        raw_demand[(s, t)] = O_i * target_weights[t]
                    elif remain_cap > 0 and remain_targets:
                        cap_t = building_capacity.get(t, 0)
                        raw_demand[(s, t)] = O_i * remain_ratio * cap_t / remain_cap
            else:
                for t in targets:
                    if t not in idx: continue
                    cap_t = building_capacity.get(t, 0)
                    if total_target_cap > 0 and cap_t > 0:
                        raw_demand[(s, t)] = O_i * cap_t / total_target_cap
        else:
            # 引力模型
            weights, total_weight = {}, 0.0
            for t in targets:
                if t not in idx: continue
                d = b_dist[b_idx[s]][b_idx[t]]
                if d <= 0: d = 1
                D_j = building_capacity.get(t, 0)
                w = D_j * (d ** (-GAMMA))
                weights[t] = w
                total_weight += w
            if total_weight > 0:
                for t in targets:
                    if t not in weights: continue
                    raw_demand[(s, t)] = O_i * weights[t] / total_weight

    # ═══════ 第二步: 上课率削减 ═══════
    for (s, t) in list(raw_demand.keys()):
        if t in ALL_TEACHING:
            raw_demand[(s, t)] *= attendance_rate

    # ═══════ 第三步: 主目标容量约束 ═══════
    if DEST_CAP:
        for t in targets:
            cap_t = building_capacity.get(t, 0)
            if cap_t <= 0: continue
            total_to_t = sum(v for (s2, t2), v in raw_demand.items() if t2 == t)
            if total_to_t > cap_t * 1.01:
                scale = cap_t / total_to_t
                for (s2, t2) in list(raw_demand.keys()):
                    if t2 == t:
                        raw_demand[(s2, t2)] *= scale

    # ═══════ 第四步: 溢出 → 副目标分配 ═══════
    if secondary_targets and DEST_CAP:
        # 计算每个源在主目标上的实际分配量
        allocated = {}   # source → total allocated to primary
        for (s, t), v in raw_demand.items():
            allocated[s] = allocated.get(s, 0) + v

        # 剩余需求分流到副目标
        extra_targets = [t for t in secondary_targets if t not in targets]
        if extra_targets:
            extra_total_cap = sum(building_capacity.get(t, 0) for t in extra_targets)
            for s in sources:
                if s not in idx: continue
                O_i = building_capacity.get(s, 0) * load_factor
                used = allocated.get(s, 0)
                remaining = O_i - used
                if remaining <= 0.01:
                    continue
                # 按容量比例分给副目标
                for t in extra_targets:
                    if t not in idx: continue
                    cap_t = building_capacity.get(t, 0)
                    if extra_total_cap > 0 and cap_t > 0:
                        extra_demand = remaining * cap_t / extra_total_cap
                        if extra_demand > 0.01:
                            raw_demand[(s, t)] = extra_demand

        # 副目标容量约束
        for t in extra_targets:
            cap_t = building_capacity.get(t, 0)
            if cap_t <= 0: continue
            total_to_t = sum(v for (s2, t2), v in raw_demand.items() if t2 == t)
            if total_to_t > cap_t * 1.01:
                scale = cap_t / total_to_t
                for (s2, t2) in list(raw_demand.keys()):
                    if t2 == t:
                        raw_demand[(s2, t2)] *= scale

    # ═══════ 第五步: 方式划分 ═══════
    for (s, t), demand in raw_demand.items():
        if demand < 0.01: continue
        d_ij = b_dist[b_idx[s]][b_idx[t]]
        modes = mode_split(d_ij)
        for mode in MODES:
            od[mode][idx[s]][idx[t]] += demand * modes[mode]

    return od

# ═══════════════════ 5. 三时段 ═══════════════════
ALL_TEACHING = ['T_16','T_25','T_1','T_2','T_3','T_4','T_5','T_6','T_7','T_8','T_9','T_10']

periods = {
    'morning': {
        'sources': ['TYGY', 'XYGY', 'CYGY', 'GYGY'],
        'targets': ALL_TEACHING,
        'load': peak_load['morning'],
        'attendance': ATTENDANCE,     # 上课率 45%
        'alloc_mode': 'capacity',     # 按容量均分
        'target_weights': {'T_16': 0.25, 'T_25': 0.25},  # 16/25幢各25%, 其余50%按容量分
        'desc': '宿舍 → 教学楼',
    },
    'noon': {
        'sources': ALL_TEACHING,
        'targets': ['TYST', 'XYST', 'GYST', 'SYJ'],
        'secondary_targets': ['TYGY', 'XYGY', 'CYGY', 'GYGY'],
        'load': peak_load['noon'],
        'attendance': 1.0,
        'alloc_mode': 'gravity',
        'secondary_alloc': 'capacity',
        'desc': '教学楼 → 食堂/商业街 → 宿舍',
    },
    'evening': {
        'sources': ALL_TEACHING,
        'targets': ['TYGY', 'XYGY', 'CYGY', 'GYGY'],
        'load': peak_load['evening'],
        'attendance': 1.0,
        'alloc_mode': 'capacity',     # 按宿舍容量均分(回自己宿舍)
        'desc': '教学楼 → 宿舍',
    },
}

for period_name, cfg in periods.items():
    od = generate_od_gravity(cfg['sources'], cfg['targets'],
                              cfg['load'], attendance_rate=cfg.get('attendance', 1.0),
                              alloc_mode=cfg.get('alloc_mode', 'gravity'),
                              target_weights=cfg.get('target_weights'),
                              secondary_targets=cfg.get('secondary_targets'),
                              secondary_alloc=cfg.get('secondary_alloc', 'capacity'))

    for mode in MODES:
        df = pd.DataFrame(od[mode], index=all_nodes, columns=all_nodes)
        df.to_csv(os.path.join(OUTPUT_DIR, f"od_{period_name}_{mode}.csv"))

    total = sum(od.values())
    df_total = pd.DataFrame(total, index=all_nodes, columns=all_nodes)
    df_total.to_csv(os.path.join(OUTPUT_DIR, f"od_{period_name}_total.csv"))

    print(f"\n{period_name:8s}  {cfg['desc']}")
    print(f"  满载率: {cfg['load']:.0%}  |  总需求: {total.sum():.0f} 人次")
    print(f"  各方式: p={od['p'].sum():.0f}  b={od['b'].sum():.0f}  "
          f"c={od['c'].sum():.0f}  bus={od['bus'].sum():.0f}")

    # 打印引力分配详情
    printed = 0
    for s in cfg['sources']:
        for t in cfg['targets']:
            if s in idx and t in idx:
                val = total[idx[s]][idx[t]]
                if val > 0.1:
                    d = b_dist[b_idx[s]][b_idx[t]]
                    pct = val / total.sum() * 100
                    print(f"    {s:6s} → {t:6s}  d={d:6.0f}m  q={val:6.0f}人 ({pct:5.1f}%)")
                    printed += 1
                    if printed >= 12: break
        if printed >= 12: break

print(f"\n{'='*50}")
print(f"输出: {OUTPUT_DIR}/  (3时段 × 5文件 = 15个)")
