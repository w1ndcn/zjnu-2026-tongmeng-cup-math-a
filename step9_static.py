"""
步骤九：静态容量（v4 — 显式消防安全折减）
========================================
电动车只允许停放在建筑周边广场、停车坪等候选空间中，消防通道、建筑出入口、
主通行人行道、绿化隔离带和必要疏散空间不得计入停车面积。

step8 输出的 A_eff_m2 已由 A_raw_m2 经安全折减系数 lambda_safe 得到：
    A_eff = A_raw * lambda_safe
因此 N_static 只基于满足消防与通行安全约束后的有效停车面积计算。
"""

import networkx as nx, pandas as pd, numpy as np, os

STEP1_DIR="output_step1"; STEP8_DIR="output_step8"
OUTPUT_DIR="output_step9"; os.makedirs(OUTPUT_DIR,exist_ok=True)

a_e=1.08; beta=1.35

G=nx.read_gml(os.path.join(STEP1_DIR,"campus_graph.gml"))
zones_df=pd.read_csv(os.path.join(STEP8_DIR,"zones.csv"))
print(f"{len(zones_df)} 区域")

rows=[]
for _,zrow in zones_df.iterrows():
    zid=zrow['zone_id'];zname=zrow['zone_name'];A_eff=float(zrow['A_eff_m2'])
    A_raw=float(zrow['A_raw_m2']) if 'A_raw_m2' in zrow else A_eff
    lambda_safe=float(zrow['lambda_safe']) if 'lambda_safe' in zrow else 1.0
    N_static=int(np.floor(A_eff/(beta*a_e)))
    rows.append({
        'zone_id':zid,'zone_name':zname,
        'A_raw_m2':A_raw,'lambda_safe':lambda_safe,'A_eff_m2':A_eff,
        'a_e_m2':a_e,'beta':beta,
        'N_static':N_static,'binding_constraint':'消防安全折减后面积',
    })
    print(f"{zid} {zname}: A_raw={A_raw:.0f}m² × λ={lambda_safe:.2f} → A_eff={A_eff:.0f}m² → N_static={N_static}")

df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR,"static_capacity.csv"),index=False,encoding="utf-8-sig")
total=sum(r['N_static'] for r in rows)
print(f"\nΣ N_static = {total} 辆 | 输出: {OUTPUT_DIR}/")
