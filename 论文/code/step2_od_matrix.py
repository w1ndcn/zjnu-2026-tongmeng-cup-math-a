import pandas as pd
import numpy as np
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STEP1_DIR = os.path.join(BASE_DIR, 'output_step1')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_step2')
os.makedirs(OUTPUT_DIR, exist_ok=True)
GAMMA = 1.5
LOAD_FACTOR = {'morning': 0.90, 'noon': 0.93, 'evening': 0.86}
ATTENDANCE = 0.45
PERIOD_FLOW = {
    'morning': {
        'sources': ['TYGY', 'XYGY', 'CYGY', 'GYGY'],
        'targets': ['T_16', 'T_25', 'T_1', 'T_2', 'T_3', 'T_4', 'T_5',
                     'T_6', 'T_7', 'T_8', 'T_9', 'T_10'],
    },
    'noon': {
        'sources': ['T_16', 'T_25', 'T_1', 'T_2', 'T_3', 'T_4', 'T_5',
                     'T_6', 'T_7', 'T_8', 'T_9', 'T_10'],
        'targets': ['TYST', 'XYST', 'GYST', 'SYJ'],
        'overflow': ['TYGY', 'XYGY', 'CYGY', 'GYGY'],
    },
    'evening': {
        'sources': ['T_16', 'T_25', 'T_1', 'T_2', 'T_3', 'T_4', 'T_5',
                     'T_6', 'T_7', 'T_8', 'T_9', 'T_10'],
        'targets': ['TYGY', 'XYGY', 'CYGY', 'GYGY'],
    },
}
CAPACITY = {
    'T_16': 3000, 'T_25': 2000,
    'T_1': 1000, 'T_2': 1000, 'T_3': 1000, 'T_4': 1000, 'T_5': 1000,
    'T_6': 1000, 'T_7': 1000, 'T_8': 1000, 'T_9': 1000, 'T_10': 1000,
    'TYGY': 13000, 'XYGY': 7000, 'CYGY': 3000, 'GYGY': 5000,
    'TYST': 1100, 'XYST': 1100, 'GYST': 1100,
    'SYJ': 5000,
}
MODE_SPLIT = {
    'short':  {'p': 0.70, 'b': 0.25, 'c': 0.05},
    'medium': {'p': 0.35, 'b': 0.55, 'c': 0.10},
    'long':   {'p': 0.15, 'b': 0.70, 'c': 0.15},
    'far':    {'p': 0.05, 'b': 0.75, 'c': 0.20},
}
MODES = ['p', 'b', 'c']
PERIODS = ['morning', 'noon', 'evening']
def get_mode_split(dist):
    if dist < 500:
        return MODE_SPLIT['short']
    elif dist < 1000:
        return MODE_SPLIT['medium']
    elif dist < 1500:
        return MODE_SPLIT['long']
    else:
        return MODE_SPLIT['far']
def gravity_model(sources, targets, dist_matrix, node_idx, lam, all_nodes):
    od = pd.DataFrame(0.0, index=all_nodes, columns=all_nodes)
    for src in sources:
        if src not in node_idx:
            continue
        i = node_idx[src]
        O_i = CAPACITY.get(src, 1000) * lam
        denom = 0.0
        weights = {}
        for dst in targets:
            if dst not in node_idx:
                continue
            j = node_idx[dst]
            d_ij = dist_matrix[i][j]
            if d_ij <= 0 or d_ij == np.inf or np.isnan(d_ij):
                d_ij = 10000
            D_j = CAPACITY.get(dst, 1000)
            w = D_j * (d_ij ** (-GAMMA))
            weights[dst] = w
            denom += w
        if denom > 0:
            for dst, w in weights.items():
                od.loc[src, dst] = O_i * w / denom
    return od
def capacity_allocate(sources, targets, lam, all_nodes, attendance=1.0):
    od = pd.DataFrame(0.0, index=all_nodes, columns=all_nodes)
    target_caps = {t: CAPACITY.get(t, 1000) for t in targets if t in all_nodes}
    total_cap = sum(target_caps.values())
    for src in sources:
        if src not in all_nodes:
            continue
        O_i = CAPACITY.get(src, 1000) * lam * attendance
        for dst, cap in target_caps.items():
            if total_cap > 0 and cap > 0:
                od.loc[src, dst] = O_i * cap / total_cap
    for dst in targets:
        cap = target_caps.get(dst, 0)
        if cap <= 0:
            continue
        total_to_dst = od.loc[:, dst].sum()
        if total_to_dst > cap:
            od.loc[:, dst] *= cap / total_to_dst
    return od
def split_by_mode(od_total, dist_matrix, node_idx):
    od_modes = {}
    for mode in MODES:
        od_modes[mode] = pd.DataFrame(0.0, index=od_total.index, columns=od_total.columns)
    for src in od_total.index:
        for dst in od_total.columns:
            total = od_total.loc[src, dst]
            if total < 0.01:
                continue
            i = node_idx.get(src, 0)
            j = node_idx.get(dst, 0)
            d = 1000
            if i < dist_matrix.shape[0] and j < dist_matrix.shape[1]:
                d = dist_matrix[i][j]
            if d == np.inf or np.isnan(d):
                d = 1000
            split = get_mode_split(d)
            for mode in MODES:
                od_modes[mode].loc[src, dst] = total * split[mode]
    return od_modes
def main():
    print("="*60)
    print("步骤二：OD需求矩阵生成")
    print("="*60)
    dist_df = pd.read_csv(os.path.join(STEP1_DIR, 'distance_matrix.csv'), index_col=0)
    with open(os.path.join(STEP1_DIR, 'node_order.txt'), 'r', encoding='utf-8') as f:
        node_order = [line.strip() for line in f if line.strip()]
    node_idx = {name: i for i, name in enumerate(node_order)}
    dist_matrix = dist_df.values
    for period in PERIODS:
        print(f"\n--- {period} ---")
        flow = PERIOD_FLOW[period]
        sources = flow['sources']
        targets = flow['targets']
        lam = LOAD_FACTOR[period]
        if period == 'morning':
            od_total = capacity_allocate(sources, targets, lam, node_order, ATTENDANCE)
        elif period == 'evening':
            od_total = gravity_model(sources, targets, dist_matrix, node_idx, lam, node_order)
        else:
            od_total = gravity_model(sources, targets, dist_matrix, node_idx, lam, node_order)
            overflow_targets = flow.get('overflow', [])
            if overflow_targets:
                for dst in targets:
                    cap = CAPACITY.get(dst, 0)
                    if cap <= 0:
                        continue
                    total_to = od_total.loc[:, dst].sum()
                    if total_to > cap:
                        od_total.loc[:, dst] *= cap / total_to
                for src in sources:
                    if src not in od_total.index:
                        continue
                    used = od_total.loc[src, targets].sum()
                    O_i = CAPACITY.get(src, 1000) * lam
                    remaining = max(0, O_i - used)
                    if remaining <= 0.01:
                        continue
                    dorm_caps = {d: CAPACITY.get(d, 1000) for d in overflow_targets if d in node_order}
                    dorm_total_cap = sum(dorm_caps.values())
                    for dst, dc in dorm_caps.items():
                        if dorm_total_cap > 0 and dc > 0:
                            od_total.loc[src, dst] += remaining * dc / dorm_total_cap
        od_modes = split_by_mode(od_total, dist_matrix, node_idx)
        od_bus = pd.DataFrame(0.0, index=node_order, columns=node_order)
        od_bus.to_csv(os.path.join(OUTPUT_DIR, f'od_{period}_bus.csv'))
        total_demand = 0
        for mode in MODES:
            od_modes[mode].to_csv(os.path.join(OUTPUT_DIR, f'od_{period}_{mode}.csv'))
            mode_demand = od_modes[mode].values.sum()
            total_demand += mode_demand
            print(f"  {mode}: {mode_demand:.0f} 人")
        od_total.to_csv(os.path.join(OUTPUT_DIR, f'od_{period}_total.csv'))
        print(f"  总计: {total_demand:.0f} 人")
    print(f"\n步骤二完成！输出目录: {OUTPUT_DIR}")
if __name__ == '__main__':
    main()
