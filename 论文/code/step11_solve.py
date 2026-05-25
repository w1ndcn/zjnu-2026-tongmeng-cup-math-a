import pandas as pd, numpy as np, os
STEP2_DIR="output_step2"; STEP8_DIR="output_step8"
STEP9_DIR="output_step9"; STEP10_DIR="output_step10"
OUTPUT_DIR="output_step11"; os.makedirs(OUTPUT_DIR,exist_ok=True)
PERIODS=['morning','noon','evening']
static_df=pd.read_csv(os.path.join(STEP9_DIR,"static_capacity.csv"))
dyn_df=pd.read_csv(os.path.join(STEP10_DIR,"dynamic_capacity.csv"))
zone_map=pd.read_csv(os.path.join(STEP8_DIR,"building_zone_map.csv"))
b2z=dict(zip(zone_map['building'],zone_map['zone_id']))
od_bike={}
for p in PERIODS:
    fp=os.path.join(STEP2_DIR,f"od_{p}_b.csv")
    if os.path.exists(fp):od_bike[p]=pd.read_csv(fp,index_col=0)
zone_demand={}
for p in PERIODS:
    ob=od_bike.get(p)
    if ob is None:continue
    for bld in ob.columns:
        zid=b2z.get(bld,''); arr=ob.loc[:,bld].sum() if bld in ob.columns else 0
        if zid:zone_demand[zid]=max(zone_demand.get(zid,0),arr)
rows=[]
for _,sr in static_df.iterrows():
    zid=sr['zone_id'];zname=sr['zone_name'];N_static=int(sr['N_static'])
    dr=dyn_df[dyn_df['zone_id']==zid]
    N_dynamic=int(dr.iloc[0]['N_dynamic']) if len(dr)>0 else N_static
    binding=dr.iloc[0]['binding_period'] if len(dr)>0 else'-'
    N_opt=min(N_static,N_dynamic)
    limiting='静态面积' if N_static<=N_dynamic else f'动态({binding})'
    D_i=zone_demand.get(zid,0);rho=D_i/N_opt if N_opt>0 else float('inf')
    if rho<0.85:status='容量充足'
    elif rho<=1.00:status='接近饱和'
    else:status='超载'
    rows.append({'zone_id':zid,'zone_name':zname,'N_static':N_static,'N_dynamic':N_dynamic,
                 'N_opt':N_opt,'limiting':limiting,'D_i':f"{D_i:.0f}",'rho':f"{rho:.3f}",'status':status})
    m=' ★' if N_static!=N_dynamic else''
    print(f"{zid} {zname:8s}: N_static={N_static:4d} N_dynamic={N_dynamic:4d} N*={N_opt:4d} D={D_i:5.0f} ρ={rho:.3f} [{status}]{m}")
N_max=sum(r['N_opt'] for r in rows)
period_demand={p:0.0 for p in PERIODS}
for p in PERIODS:
    ob=od_bike.get(p)
    if ob is None:continue
    for bld in ob.columns:
        if bld in b2z:period_demand[p]+=ob.loc[:,bld].sum()
worst_p=max(period_demand,key=period_demand.get)
theta=period_demand[worst_p]/N_max if N_max>0 else 0
print(f"\nN_max = {N_max} 辆 | θ = {theta:.3f} (最差:{worst_p})")
bottleneck=[r for r in rows if r['N_dynamic']<r['N_static']]
if bottleneck:
    for r in bottleneck:
        pct=(1-r['N_opt']/max(r['N_static'],1))*100
        print(f"  瓶颈: {r['zone_name']} {r['N_static']}→{r['N_opt']} (-{pct:.0f}%)")
df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR,"final_capacity.csv"),index=False,encoding="utf-8-sig")
with open(os.path.join(OUTPUT_DIR,"capacity_report.txt"),"w",encoding="utf-8") as f:
    f.write(f"校园电动车环境承载力评估 (v2)\n")
    f.write(f"N_max = {N_max} 辆 | θ = {theta:.3f}\n\n")
    for r in rows:
        f.write(f"{r['zone_name']}: N*={r['N_opt']} ρ={r['rho']} [{r['status']}]\n")
print(f"输出: {OUTPUT_DIR}/")
