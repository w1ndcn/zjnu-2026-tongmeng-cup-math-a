"""
步骤十五+十六：候选接驳线路构造 + 广义成本评价选线
=================================================
输入:
  - output_step1/campus_graph.gml
  - output_step3/link_flow_morning.csv
  - output_step13/candidate_stops.csv
  - output_step14/selected_stops.csv
  - output_step14/stop_coverage.csv
输出:
  - output_step15/candidate_routes.csv
  - output_step15/route_evaluation.csv
"""

import networkx as nx
import pandas as pd
import numpy as np
import os
import math
from collections import defaultdict

STEP1_DIR  = "output_step1"
STEP3_DIR  = "output_step3"
STEP13_DIR = "output_step13"
STEP14_DIR = "output_step14"
OUTPUT_DIR = "output_step15"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== 参数 =====
DELTA = 0.5       # 单站停靠时间 (min)
BUS_SPEED = 20    # 接驳车自由流速度 (km/h) ≈ 5.56 m/s

# 广义成本权重（文档 §17.2）
ALPHA_L = 0.2     # 长度
ALPHA_T = 0.3     # 时间
ALPHA_V = 0.2     # 平均 V/C
ALPHA_S = 0.2     # 平均风险
ALPHA_P = 0.1     # 覆盖客流（越大越好，负号）

# ═══════════════ 1. 加载数据 ═══════════════
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
stops_df = pd.read_csv(os.path.join(STEP13_DIR, "candidate_stops.csv"))
sel_df = pd.read_csv(os.path.join(STEP14_DIR, "selected_stops.csv"))
lf = pd.read_csv(os.path.join(STEP3_DIR, "link_flow_morning.csv"))

# 选中的站点
selected = sel_df[sel_df['selected'] == True]
print(f"选中站点: {len(selected)} 个")
for _, s in selected.iterrows():
    print(f"  {s['stop_id']} {s['stop_name']} @ {s['nearest_node']}")

# 站点到路网节点的映射
stop_to_node = dict(zip(stops_df['stop_id'], stops_df['nearest_node']))
stop_name = dict(zip(stops_df['stop_id'], stops_df['stop_name']))

# ═══════════════ 2. 定义候选线路（v3 2条线路） ═══════════════
CANDIDATE_ROUTES = [
    {
        'route_id': 'R1',
        'route_name': '教学潮汐线',
        'route_type': '潮汐线 桃园→16幢→25幢→杏园→桂苑',
        'stop_sequence': ['S2', 'S4', 'S5', 'S3', 'S1'],
        'direction_morning': 'forward',   # 早: 宿舍→教学
        'direction_noon': 'reverse',      # 午: 教学→食堂/商业街
    },
    {
        'route_id': 'R2',
        'route_name': '校园环线',
        'route_type': '环线 桂苑→桃园→16幢→25幢→杏园→桂苑',
        'stop_sequence': ['S1', 'S2', 'S4', 'S5', 'S3', 'S1'],
        'direction_morning': 'forward',
        'direction_noon': 'forward',
    },
]

# ═══════════════ 3. 路段属性查找 + BPR 拥堵阻抗 ═══════════════
# 构建边 (u,v) → V/C, risk 的快速查询
edge_vc = {}
edge_risk = {}
for _, row in lf.iterrows():
    u, v = row['from'], row['to']
    edge_vc[(u, v)] = float(row['saturation'])
    edge_risk[(u, v)] = float(row['risk'])

BPR_ALPHA = 0.15
BPR_BETA = 4.0
BUS_SPEED_MPS = 5.56

def bpr_time_sec(length, vc):
    """基于 BPR 函数的接驳车路段通行时间 (s)"""
    t0 = length / BUS_SPEED_MPS
    vc = max(float(vc), 0.0)
    return t0 * (1 + BPR_ALPHA * (vc ** BPR_BETA))

# 为路网边写入 bus_time 权重，使线路搜索能主动避开拥堵路段
for u, v, data in G.edges(data=True):
    length = float(data.get('length', 50))
    vc = edge_vc.get((u, v), 0.0)
    data['bus_time'] = bpr_time_sec(length, vc)

def compute_route_path(G, stop_seq, forward=True):
    """
    计算一条线路的实际路网路径。
    返回: (node_path, total_length_m, total_time_min, vc_list, risk_list)
    """
    seq = stop_seq if forward else list(reversed(stop_seq))
    full_path = []
    total_length = 0
    total_time = 0
    vc_list = []
    risk_list = []

    for k in range(len(seq) - 1):
        s_from = seq[k]
        s_to = seq[k + 1]
        u = stop_to_node.get(s_from, '')
        v = stop_to_node.get(s_to, '')

        if u not in G or v not in G:
            continue

        try:
            path = nx.shortest_path(G, u, v, weight='bus_time')
        except nx.NetworkXNoPath:
            continue

        # 跳过第一个节点（起点已经在上一个段）
        start_idx = 1 if full_path else 0
        full_path.extend(path[start_idx:])

        # 计算该段的长度和时间
        seg_length = 0
        seg_time = 0
        for i in range(len(path) - 1):
            a, b = path[i], path[i+1]
            if G.has_edge(a, b):
                L = float(G[a][b].get('length', 50))
                vc = edge_vc.get((a, b), 0)
                seg_length += L
                seg_time += bpr_time_sec(L, vc)
                vc_list.append(vc)
                risk_list.append(edge_risk.get((a, b), 0))

        total_length += seg_length
        total_time += seg_time

    # + 停站时间
    total_time_sec = total_time + DELTA * 60 * (len(seq) - 1)
    total_time_min = total_time_sec / 60

    return full_path, total_length, total_time_min, vc_list, risk_list


# ═══════════════ 4. 计算每条线路 ═══════════════
rows = []
eval_rows = []

for route in CANDIDATE_ROUTES:
    rid = route['route_id']
    rname = route['route_name']
    rtype = route['route_type']
    stop_seq = route['stop_sequence']

    # 前向（早高峰方向）
    path, length, t_min, vcs, risks = compute_route_path(G, stop_seq, forward=True)

    avg_vc = np.mean(vcs) if vcs else 0
    avg_risk = np.mean(risks) if risks else 0
    max_vc = max(vcs) if vcs else 0

    # 路径节点字符串
    path_str = ' → '.join(path[:12]) + ('...' if len(path) > 12 else '')
    stop_str = ' → '.join([f"{stop_name.get(s,s)}" for s in stop_seq])

    rows.append({
        'route_id': rid,
        'route_name': rname,
        'route_type': rtype,
        'stop_sequence': stop_str,
        'path_nodes': path_str,
        'num_nodes': len(path),
        'length_m': f"{length:.0f}",
        'travel_time_min': f"{t_min:.1f}",
        'avg_vc': f"{avg_vc:.3f}",
        'max_vc': f"{max_vc:.3f}",
        'avg_risk': f"{avg_risk:.0f}",
    })

    print(f"\n{rid} {rname} ({rtype}):")
    print(f"  站点: {stop_str}")
    print(f"  长度: {length:.0f}m, 用时: {t_min:.1f}min (含停站)")
    print(f"  经过节点: {len(path)} 个")
    print(f"  平均 V/C: {avg_vc:.3f}, 最大 V/C: {max_vc:.3f}, 平均风险: {avg_risk:.0f}")

# ═══════════════ 5. 广义成本评价 ═══════════════
print(f"\n{'='*60}")
print("5. 广义成本评价:")

# 归一化参照值
lengths = [float(r['length_m']) for r in rows]
times = [float(r['travel_time_min']) for r in rows]
vcs_avg = [float(r['avg_vc']) for r in rows]
risks_avg = [float(r['avg_risk']) for r in rows]

L_max = max(lengths) if max(lengths) > 0 else 1
T_max = max(times) if max(times) > 0 else 1
V_max = max(vcs_avg) if max(vcs_avg) > 0 else 1
S_max = max(risks_avg) if max(risks_avg) > 0 else 1

# 覆盖客流: 读取站点-建筑覆盖矩阵，对线路覆盖建筑去重后计算需求
BUILDING_CAPACITY = {
    'T_16': 3000, 'T_25': 2000,
    'T_1': 1000, 'T_2': 1000, 'T_3': 1000, 'T_4': 1000, 'T_5': 1000,
    'T_6': 1000, 'T_7': 1000, 'T_8': 1000, 'T_9': 1000, 'T_10': 1000,
    'TYGY': 13000, 'XYGY': 7000, 'CYGY': 3000, 'GYGY': 5000,
    'TYST': 1100, 'XYST': 1100, 'GYST': 1100, 'SYJ': 5000,
}
coverage_df = pd.read_csv(os.path.join(STEP14_DIR, "stop_coverage.csv"))
P_max = sum(BUILDING_CAPACITY.get(str(b), 500) for b in coverage_df['building'].drop_duplicates())
P_max = P_max if P_max > 0 else 1

def route_covered_demand(stop_seq):
    """计算线路经过站点覆盖的建筑需求，建筑去重，避免重复计数。"""
    covered_buildings = set()
    for sid in set(stop_seq):
        sub = coverage_df[(coverage_df['stop_id'] == sid) & (coverage_df['covered'] == 1)]
        covered_buildings.update(str(b) for b in sub['building'].tolist())
    demand = sum(BUILDING_CAPACITY.get(b, 500) for b in covered_buildings)
    return demand, covered_buildings

for i, route in enumerate(CANDIDATE_ROUTES):
    covered, covered_buildings = route_covered_demand(route['stop_sequence'])

    L = float(rows[i]['length_m'])
    T = float(rows[i]['travel_time_min'])
    V = float(rows[i]['avg_vc'])
    S = float(rows[i]['avg_risk'])
    P = covered

    G_cost = (ALPHA_L * L / L_max
              + ALPHA_T * T / T_max
              + ALPHA_V * V / V_max
              + ALPHA_S * S / S_max
              - ALPHA_P * P / P_max)

    eval_rows.append({
        'route_id': route['route_id'],
        'route_name': route['route_name'],
        'length_m': f"{L:.0f}",
        'time_min': f"{T:.1f}",
        'avg_vc': f"{V:.3f}",
        'avg_risk': f"{S:.0f}",
        'covered_demand': f"{P:.0f}",
        'covered_buildings': '|'.join(sorted(covered_buildings)),
        'G_cost': f"{G_cost:.4f}",
    })

    print(f"  {route['route_id']} {route['route_name']:10s}: "
          f"L={L:.0f}m T={T:.1f}min V/C={V:.3f} S={S:.0f} "
          f"覆盖={P:.0f} G={G_cost:.4f}")

# 选出最优线路
best = min(eval_rows, key=lambda r: float(r['G_cost']))
print(f"\n  最优线路: {best['route_id']} {best['route_name']} (G={best['G_cost']})")

# ═══════════════ 6. 保存 ═══════════════
df_routes = pd.DataFrame(rows)
df_routes.to_csv(os.path.join(OUTPUT_DIR, "candidate_routes.csv"), index=False, encoding="utf-8-sig")

df_eval = pd.DataFrame(eval_rows)
df_eval.to_csv(os.path.join(OUTPUT_DIR, "route_evaluation.csv"), index=False, encoding="utf-8-sig")

print(f"\n输出: {OUTPUT_DIR}/")
print(f"  candidate_routes.csv  ({len(rows)} 条候选线路)")
print(f"  route_evaluation.csv  (线路评价)")
