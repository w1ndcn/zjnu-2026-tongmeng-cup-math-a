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
DELTA = 0.5
BUS_SPEED = 20
ALPHA_L = 0.2
ALPHA_T = 0.3
ALPHA_V = 0.2
ALPHA_S = 0.2
ALPHA_P = 0.1
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
stops_df = pd.read_csv(os.path.join(STEP13_DIR, "candidate_stops.csv"))
sel_df = pd.read_csv(os.path.join(STEP14_DIR, "selected_stops.csv"))
lf = pd.read_csv(os.path.join(STEP3_DIR, "link_flow_morning.csv"))
selected = sel_df[sel_df['selected'] == True]
print(f"选中站点: {len(selected)} 个")
for _, s in selected.iterrows():
    print(f"  {s['stop_id']} {s['stop_name']} @ {s['nearest_node']}")
stop_to_node = dict(zip(stops_df['stop_id'], stops_df['nearest_node']))
stop_name = dict(zip(stops_df['stop_id'], stops_df['stop_name']))
CANDIDATE_ROUTES = [
    {
        'route_id': 'R1',
        'route_name': '教学潮汐线',
        'route_type': '潮汐线 桃园→16幢→25幢→杏园→桂苑',
        'stop_sequence': ['S2', 'S4', 'S5', 'S3', 'S1'],
        'direction_morning': 'forward',
        'direction_noon': 'reverse',
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
    t0 = length / BUS_SPEED_MPS
    vc = max(float(vc), 0.0)
    return t0 * (1 + BPR_ALPHA * (vc ** BPR_BETA))
for u, v, data in G.edges(data=True):
    length = float(data.get('length', 50))
    vc = edge_vc.get((u, v), 0.0)
    data['bus_time'] = bpr_time_sec(length, vc)
def compute_route_path(G, stop_seq, forward=True):
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
        start_idx = 1 if full_path else 0
        full_path.extend(path[start_idx:])
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
    total_time_sec = total_time + DELTA * 60 * (len(seq) - 1)
    total_time_min = total_time_sec / 60
    return full_path, total_length, total_time_min, vc_list, risk_list
rows = []
eval_rows = []
for route in CANDIDATE_ROUTES:
    rid = route['route_id']
    rname = route['route_name']
    rtype = route['route_type']
    stop_seq = route['stop_sequence']
    path, length, t_min, vcs, risks = compute_route_path(G, stop_seq, forward=True)
    avg_vc = np.mean(vcs) if vcs else 0
    avg_risk = np.mean(risks) if risks else 0
    max_vc = max(vcs) if vcs else 0
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
print(f"\n{'='*60}")
print("5. 广义成本评价:")
lengths = [float(r['length_m']) for r in rows]
times = [float(r['travel_time_min']) for r in rows]
vcs_avg = [float(r['avg_vc']) for r in rows]
risks_avg = [float(r['avg_risk']) for r in rows]
L_max = max(lengths) if max(lengths) > 0 else 1
T_max = max(times) if max(times) > 0 else 1
V_max = max(vcs_avg) if max(vcs_avg) > 0 else 1
S_max = max(risks_avg) if max(risks_avg) > 0 else 1
BUILDING_CAPACITY = {
    'T_16': 3000, 'T_25': 2000,
    'T_1': 1000, 'T_2': 1000, 'T_3': 1000, 'T_4': 1000, 'T_5': 1000,
    'T_6': 1000, 'T_7': 1000, 'T_8': 1000, 'T_9': 1000, 'T_10': 1000,
    'TYGY': 13000, 'XYGY': 7000, 'CYGY': 3000, 'GYGY': 5000,
    'TYST': 1100, 'XYST': 1100, 'GYST': 1100, 'SYJ': 5000,
}
sel_stops_info = dict(zip(sel_df['stop_id'], sel_df['covered_demand']))
for i, route in enumerate(CANDIDATE_ROUTES):
    unique_stops = set(route['stop_sequence'])
    covered = sum(float(sel_stops_info.get(s, '0')) for s in unique_stops)
    L = float(rows[i]['length_m'])
    T = float(rows[i]['travel_time_min'])
    V = float(rows[i]['avg_vc'])
    S = float(rows[i]['avg_risk'])
    P = covered
    P_max = sum(BUILDING_CAPACITY.values())
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
        'G_cost': f"{G_cost:.4f}",
    })
    print(f"  {route['route_id']} {route['route_name']:10s}: "
          f"L={L:.0f}m T={T:.1f}min V/C={V:.3f} S={S:.0f} "
          f"覆盖={P:.0f} G={G_cost:.4f}")
best = min(eval_rows, key=lambda r: float(r['G_cost']))
print(f"\n  最优线路: {best['route_id']} {best['route_name']} (G={best['G_cost']})")
df_routes = pd.DataFrame(rows)
df_routes.to_csv(os.path.join(OUTPUT_DIR, "candidate_routes.csv"), index=False, encoding="utf-8-sig")
df_eval = pd.DataFrame(eval_rows)
df_eval.to_csv(os.path.join(OUTPUT_DIR, "route_evaluation.csv"), index=False, encoding="utf-8-sig")
print(f"\n输出: {OUTPUT_DIR}/")
print(f"  candidate_routes.csv  ({len(rows)} 条候选线路)")
print(f"  route_evaluation.csv  (线路评价)")
