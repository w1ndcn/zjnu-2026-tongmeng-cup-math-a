import networkx as nx
import pandas as pd
import numpy as np
import os
STEP1_DIR  = "output_step1"
STEP2_DIR  = "output_step2"
STEP3_DIR  = "output_step3"
STEP8_DIR  = "output_step8"
STEP11_DIR = "output_step11"
OUTPUT_DIR = "output_step12"
os.makedirs(OUTPUT_DIR, exist_ok=True)
PERIODS = ['morning', 'noon', 'evening']
PERIOD_LABEL = {'morning': '早高峰', 'noon': '午高峰', 'evening': '晚高峰'}
print("1. 加载路网...")
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
print(f"   节点: {G.number_of_nodes()}, 边: {G.number_of_edges()}")
print("2. 加载区域数据...")
zone_map = pd.read_csv(os.path.join(STEP8_DIR, "building_zone_map.csv"))
zones_df = pd.read_csv(os.path.join(STEP8_DIR, "zones.csv"))
b2z = dict(zip(zone_map['building'], zone_map['zone_id']))
z2name = dict(zip(zones_df['zone_id'], zones_df['zone_name']))
z2type = dict(zip(zones_df['zone_id'], zones_df['zone_type']))
building_nodes = [n for n in G.nodes() if str(G.nodes[n].get('type', '')) != '交叉口']
print(f"   建筑节点: {len(building_nodes)}")
print("3. 加载 OD 数据...")
od_total = {}
od_ebike = {}
for period in PERIODS:
    fp_t = os.path.join(STEP2_DIR, f"od_{period}_total.csv")
    fp_b = os.path.join(STEP2_DIR, f"od_{period}_b.csv")
    if os.path.exists(fp_t):
        od_total[period] = pd.read_csv(fp_t, index_col=0)
    if os.path.exists(fp_b):
        od_ebike[period] = pd.read_csv(fp_b, index_col=0)
    print(f"   {period}: total={od_total[period].shape if period in od_total else 'N/A'}, "
          f"ebike={od_ebike[period].shape if period in od_ebike else 'N/A'}")
print("4. 加载路段流量数据...")
link_flows = {}
for period in PERIODS:
    fp = os.path.join(STEP3_DIR, f"link_flow_{period}.csv")
    if os.path.exists(fp):
        link_flows[period] = pd.read_csv(fp)
        print(f"   {period}: {len(link_flows[period])} 条路段")
print("5. 加载问题二结果...")
capacity_df = pd.read_csv(os.path.join(STEP11_DIR, "final_capacity.csv"))
print("\n6. 构建节点级基础数据表...")
rows = []
for node in G.nodes():
    ntype = str(G.nodes[node].get('type', ''))
    zid = b2z.get(node, '')
    zname = z2name.get(zid, '')
    ztype = z2type.get(zid, '')
    row = {
        'node_id': node,
        'node_type': ntype,
        'zone_id': zid,
        'zone_name': zname,
        'zone_type': ztype,
    }
    for period in PERIODS:
        ot = od_total.get(period)
        ob = od_ebike.get(period)
        if ot is not None and node in ot.index:
            row[f'demand_{period}_total'] = ot.loc[node].sum()
        else:
            row[f'demand_{period}_total'] = 0
        if ob is not None and node in ob.index:
            row[f'demand_{period}_ebike'] = ob.loc[node].sum()
        else:
            row[f'demand_{period}_ebike'] = 0
    for period in PERIODS:
        lf = link_flows.get(period)
        if lf is not None:
            mask = (lf['from'] == node) | (lf['to'] == node)
            nearby = lf[mask]
            if len(nearby) > 0:
                row[f'vc_max_{period}'] = nearby['saturation'].astype(float).max()
                row[f'risk_max_{period}'] = nearby['risk'].astype(float).max()
            else:
                row[f'vc_max_{period}'] = 0
                row[f'risk_max_{period}'] = 0
        else:
            row[f'vc_max_{period}'] = 0
            row[f'risk_max_{period}'] = 0
    if node in building_nodes:
        cap_row = capacity_df[capacity_df['zone_id'] == zid]
        if len(cap_row) > 0:
            row['N_opt'] = int(cap_row.iloc[0]['N_opt'])
            row['rho'] = float(cap_row.iloc[0]['rho'])
            row['status'] = cap_row.iloc[0]['status']
        else:
            row['N_opt'] = 0
            row['rho'] = 0
            row['status'] = ''
    else:
        row['N_opt'] = 0
        row['rho'] = 0
        row['status'] = ''
    rows.append(row)
df_nodes = pd.DataFrame(rows)
df_nodes.to_csv(os.path.join(OUTPUT_DIR, "base_data_summary.csv"),
                index=False, encoding="utf-8-sig")
building_rows = df_nodes[df_nodes['node_type'] != '交叉口']
print(f"\n   建筑节点: {len(building_rows)} 个")
print(f"   各区域需求与压力:")
for _, r in building_rows.iterrows():
    dem = sum(float(r[f'demand_{p}_total']) for p in PERIODS)
    ebk = sum(float(r[f'demand_{p}_ebike']) for p in PERIODS)
    print(f"     {r['node_id']:8s} [{r['zone_name']:6s}] "
          f"总需求={dem:6.0f}  ebike={ebk:5.0f}  "
          f"V/C早={r['vc_max_morning']:.3f}  "
          f"ρ={r['rho']:.3f}")
print("\n7. 构建区域级 e-bike OD 聚合表...")
zone_list = sorted(zones_df['zone_id'].tolist())
od_zone_rows = []
for period in PERIODS:
    ob = od_ebike.get(period)
    if ob is None:
        continue
    for zi in zone_list:
        bi = [b for b, z in b2z.items() if z == zi and b in ob.index]
        for zj in zone_list:
            bj = [b for b, z in b2z.items() if z == zj and b in ob.columns]
            flow_sum = 0
            for bi_node in bi:
                for bj_node in bj:
                    if bi_node in ob.index and bj_node in ob.columns:
                        flow_sum += ob.loc[bi_node, bj_node]
            if flow_sum > 0.1:
                od_zone_rows.append({
                    'period': period,
                    'from_zone': zi,
                    'to_zone': zj,
                    'from_name': z2name.get(zi, ''),
                    'to_name': z2name.get(zj, ''),
                    'ebike_flow': flow_sum,
                })
df_od = pd.DataFrame(od_zone_rows)
df_od.to_csv(os.path.join(OUTPUT_DIR, "od_ebike_summary.csv"),
             index=False, encoding="utf-8-sig")
for period in PERIODS:
    pdf = df_od[df_od['period'] == period].sort_values('ebike_flow', ascending=False)
    if len(pdf) == 0:
        continue
    print(f"\n   {PERIOD_LABEL[period]} e-bike 主要流向 (Top 5):")
    for _, r in pdf.head(5).iterrows():
        print(f"     {r['from_name']:8s} → {r['to_name']:8s}  {r['ebike_flow']:6.0f}")
print(f"\n{'='*60}")
print(f"完成！输出:")
print(f"  {OUTPUT_DIR}/base_data_summary.csv  ({len(df_nodes)} 行, 节点级)")
print(f"  {OUTPUT_DIR}/od_ebike_summary.csv   ({len(df_od)} 行, 区域级)")
print(f"\n关键数据供后续步骤使用:")
print(f"  建筑节点数: {len(building_rows)}")
print(f"  区域数: {len(zone_list)}")
print(f"  时段数: {len(PERIODS)}")
