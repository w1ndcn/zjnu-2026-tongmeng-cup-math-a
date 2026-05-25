import networkx as nx
import pandas as pd
import numpy as np
import os
from itertools import combinations
STEP1_DIR  = "output_step1"
STEP3_DIR  = "output_step3"
STEP12_DIR = "output_step12"
STEP13_DIR = "output_step13"
OUTPUT_DIR = "output_step14"
os.makedirs(OUTPUT_DIR, exist_ok=True)
R0 = 400
PHI_MIN = 0.35
W_WIDTH = 0.3
W_VC    = 0.4
W_RISK  = 0.3
B_MAX = 8
P_MIN = 0.55
MIN_STOPS = 5
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
stops_df = pd.read_csv(os.path.join(STEP13_DIR, "candidate_stops.csv"))
base_df = pd.read_csv(os.path.join(STEP12_DIR, "base_data_summary.csv"))
lf_morning = pd.read_csv(os.path.join(STEP3_DIR, "link_flow_morning.csv"))
building_df = base_df[base_df['node_type'] != '交叉口'].copy()
building_nodes = building_df['node_id'].tolist()
stop_nodes = [stops_df.iloc[i] for i in range(len(stops_df))]
print(f"需求点(建筑): {len(building_nodes)}")
print(f"候选站点: {len(stop_nodes)}")
print(f"覆盖半径 R0 = {R0}m, 最低适宜性 φ_min = {PHI_MIN}\n")
print("2. 计算覆盖矩阵...")
coverage_matrix = {}
coverage_records = []
for _, bld_row in building_df.iterrows():
    bi = bld_row['node_id']
    if bi not in G:
        continue
    for _, st_row in stops_df.iterrows():
        sj_node = st_row['nearest_node']
        if sj_node not in G:
            continue
        try:
            dist = nx.shortest_path_length(G, bi, sj_node, weight='length')
        except nx.NetworkXNoPath:
            dist = float('inf')
        covered = 1 if dist <= R0 else 0
        coverage_matrix[(bi, st_row['stop_id'])] = dist
        coverage_records.append({
            'building': bi,
            'stop_id': st_row['stop_id'],
            'stop_name': st_row['stop_name'],
            'distance_m': f"{dist:.0f}" if dist < float('inf') else '∞',
            'covered': covered,
        })
df_cov = pd.DataFrame(coverage_records)
df_cov.to_csv(os.path.join(OUTPUT_DIR, "stop_coverage.csv"), index=False, encoding="utf-8-sig")
print("   覆盖矩阵 (建筑 → 站点, 距离):")
print(f"   {'建筑':<8}", end="")
for s in stops_df['stop_id']:
    print(f"  {s:>6}", end="")
print(f"  {'覆盖范围':>6}")
for bi in building_nodes:
    print(f"   {bi:<8}", end="")
    for _, st in stops_df.iterrows():
        d = coverage_matrix.get((bi, st['stop_id']), float('inf'))
        mark = '✓' if d <= R0 else ' '
        print(f"  {d:3.0f}{mark} ", end="")
    nc = sum(1 for _, st in stops_df.iterrows()
             if coverage_matrix.get((bi, st['stop_id']), float('inf')) <= R0)
    print(f"   {nc}/{len(stop_nodes)}")
print("\n3. 计算站点适宜性...")
V_MAX = lf_morning['saturation'].astype(float).max()
S_MAX = lf_morning['risk'].astype(float).max()
W_MAX = 8.0
suit_rows = []
for _, st in stops_df.iterrows():
    node = st['nearest_node']
    mask = (lf_morning['from'] == node) | (lf_morning['to'] == node)
    nearby = lf_morning[mask]
    if len(nearby) > 0:
        w_j = float(nearby['width_m'].max()) if 'width_m' in nearby.columns else 8.0
        v_j = float(nearby['saturation'].max())
        s_j = float(nearby['risk'].max())
    else:
        w_j, v_j, s_j = 8.0, 0.0, 0.0
    phi = (W_WIDTH * (w_j / max(W_MAX, 1e-9))
           + W_VC * (1 - v_j / max(V_MAX, 1e-9))
           + W_RISK * (1 - s_j / max(S_MAX, 1e-9)))
    suitable = 1 if phi >= PHI_MIN else 0
    suit_rows.append({
        'stop_id': st['stop_id'],
        'stop_name': st['stop_name'],
        'road_width': w_j,
        'vc_morning': v_j,
        'risk_morning': s_j,
        'phi_width': W_WIDTH * w_j / max(W_MAX, 1e-9),
        'phi_vc': W_VC * (1 - v_j / max(V_MAX, 1e-9)),
        'phi_risk': W_RISK * (1 - s_j / max(S_MAX, 1e-9)),
        'phi': f"{phi:.4f}",
        'suitable': suitable,
    })
    print(f"   {st['stop_id']} {st['stop_name']:10s}: φ={phi:.4f} "
          f"(路宽={w_j:.0f}m V/C={v_j:.3f} 风险={s_j:.0f}) "
          f"{'✓' if suitable else '✗ 不适宜'}")
df_suit = pd.DataFrame(suit_rows)
df_suit.to_csv(os.path.join(OUTPUT_DIR, "stop_suitability.csv"), index=False, encoding="utf-8-sig")
print("\n4. MCLP 最大覆盖选址...")
BUILDING_CAPACITY = {
    'T_16': 3000, 'T_25': 2000,
    'T_1': 1000, 'T_2': 1000, 'T_3': 1000, 'T_4': 1000, 'T_5': 1000,
    'T_6': 1000, 'T_7': 1000, 'T_8': 1000, 'T_9': 1000, 'T_10': 1000,
    'TYGY': 13000, 'XYGY': 7000, 'CYGY': 3000, 'GYGY': 5000,
    'TYST': 1100, 'XYST': 1100, 'GYST': 1100, 'SYJ': 5000,
}
demands = {}
for _, bld in building_df.iterrows():
    bi = bld['node_id']
    demands[bi] = BUILDING_CAPACITY.get(bi, 500)
total_demand = sum(demands.values())
print(f"   总接驳需求(早高峰): {total_demand:.0f} 人次")
stop_ids = [st['stop_id'] for _, st in stops_df.iterrows()]
a = {}
for _, st in stops_df.iterrows():
    sj_id = st['stop_id']
    suit_row = [r for r in suit_rows if r['stop_id'] == sj_id]
    suitable = suit_row[0]['suitable'] if suit_row else 0
    for bi in building_nodes:
        d = coverage_matrix.get((bi, sj_id), float('inf'))
        a[(bi, sj_id)] = 1 if (d <= R0 and suitable) else 0
best_cov_rate = 0
best_k = 0
best_selection = []
for k in range(MIN_STOPS, min(B_MAX + 1, len(stop_ids) + 1)):
    for combo in combinations(stop_ids, k):
        covered_demand = 0
        for bi in building_nodes:
            if any(a.get((bi, sj), 0) for sj in combo):
                covered_demand += demands.get(bi, 0)
        cov_rate = covered_demand / max(total_demand, 1)
        if cov_rate < P_MIN:
            continue
        better = (cov_rate > best_cov_rate + 1e-6 or
                  (abs(cov_rate - best_cov_rate) < 1e-6 and k < best_k))
        if better or not best_selection:
            best_cov_rate = cov_rate
            best_k = k
            best_selection = list(combo)
print(f"   枚举组合数: {sum(1 for k in range(MIN_STOPS, min(B_MAX+1, len(stop_ids)+1)) for _ in combinations(stop_ids, k))}")
print(f"   最优: 覆盖率={best_cov_rate:.1%}, 用 {best_k} 站: {best_selection}")
sel_rows = []
for _, st in stops_df.iterrows():
    selected = st['stop_id'] in best_selection
    cov_dem = sum(demands.get(bi, 0) for bi in building_nodes
                  if a.get((bi, st['stop_id']), 0))
    phi_val = float([r['phi'] for r in suit_rows if r['stop_id'] == st['stop_id']][0])
    sel_rows.append({
        'stop_id': st['stop_id'],
        'stop_name': st['stop_name'],
        'nearest_node': st['nearest_node'],
        'zone_name': st['zone_name'],
        'vc_max': st['vc_max'],
        'phi': f"{phi_val:.4f}",
        'covered_demand': f"{cov_dem:.0f}",
        'covered_pct': f"{cov_dem/max(total_demand,1)*100:.1f}%",
        'selected': selected,
    })
    print(f"   {st['stop_id']} {st['stop_name']:10s}: φ={phi_val:.4f}, "
          f"覆盖需求={cov_dem:.0f}({cov_dem/max(total_demand,1)*100:.1f}%), "
          f"{'★' if selected else ''}")
df_sel = pd.DataFrame(sel_rows)
df_sel.to_csv(os.path.join(OUTPUT_DIR, "selected_stops.csv"), index=False, encoding="utf-8-sig")
print(f"\n{'='*60}")
print(f"MCLP 结果: 从 {len(stop_ids)} 个候选站中选出 {len(best_selection)} 个")
print(f"  最优覆盖: {best_cov_rate:.1%}")
print(f"  选中: {', '.join(best_selection)}")
print(f"输出: {OUTPUT_DIR}/")
