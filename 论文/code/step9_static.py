import networkx as nx, pandas as pd, numpy as np, os
STEP1_DIR="output_step1"; STEP8_DIR="output_step8"
OUTPUT_DIR="output_step9"; os.makedirs(OUTPUT_DIR,exist_ok=True)
a_e=1.08; beta=1.35
SAFETY_LAMBDA = {
    'Z1': 0.72, 'Z2': 0.72,
    'Z3': 0.63, 'Z4': 0.65, 'Z5': 0.63,
    'Z6': 0.70, 'Z7': 0.70, 'Z8': 0.60,
}
G=nx.read_gml(os.path.join(STEP1_DIR,"campus_graph.gml"))
zones_df=pd.read_csv(os.path.join(STEP8_DIR,"zones.csv"))
print(f"{len(zones_df)} 区域")
print(f"{'区域':<12} {'A_raw':>7} ×{'λ':>5} = {'A_safe':>7} → {'N_static':>7}")
print("-" * 52)
rows=[]
for _,zrow in zones_df.iterrows():
    zid=zrow['zone_id'];zname=zrow['zone_name']
    A_safe=float(zrow['A_eff_m2'])
    lam = SAFETY_LAMBDA.get(zid, 0.70)
    A_raw = A_safe / lam
    N_static=int(np.floor(A_safe/(beta*a_e)))
    rows.append({
        'zone_id':zid,'zone_name':zname,
        'A_raw':round(A_raw,0),'lambda':lam,'A_eff_m2':A_safe,
        'N_static':N_static,'binding_constraint':'面积',
    })
    print(f"{zname:<12} {A_raw:7.0f} ×{lam:<5.2f} = {A_safe:7.0f} → {N_static:>7}")
df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR,"static_capacity.csv"),index=False,encoding="utf-8-sig")
total=sum(r['N_static'] for r in rows)
print(f"\nΣ N_static = {total} 辆 | 输出: {OUTPUT_DIR}/")
