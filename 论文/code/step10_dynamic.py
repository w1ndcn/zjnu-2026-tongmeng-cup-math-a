import pandas as pd, numpy as np, os
STEP3_DIR="output_step3"; STEP8_DIR="output_step8"
OUTPUT_DIR="output_step10"; os.makedirs(OUTPUT_DIR,exist_ok=True)
SAT_LIMIT=0.85; PCU_BIKE=0.30; PERIODS=['morning','noon','evening']
ALPHA_DEFAULT={'morning':0.90,'noon':0.80,'evening':0.90}
zones_df=pd.read_csv(os.path.join(STEP8_DIR,"zones.csv"))
link_flows={}
for p in PERIODS:
    fp=os.path.join(STEP3_DIR,f"link_flow_{p}.csv")
    if os.path.exists(fp):link_flows[p]=pd.read_csv(fp)
    print(f"加载 {p}: {len(link_flows.get(p,[]))} 条")
rows=[]
for _,zrow in zones_df.iterrows():
    zid=zrow['zone_id'];zname=zrow['zone_name']
    junctions=set(j.strip() for j in str(zrow['junctions']).split('|') if j.strip())
    period_results={}
    for period in PERIODS:
        lf=link_flows.get(period)
        if lf is None:continue
        mask=lf['from'].isin(junctions)|lf['to'].isin(junctions)
        zone_edges=lf[mask]
        if len(zone_edges)==0:
            period_results[period]={'C_road':0,'N_dyn':0}
            continue
        remaining_bike=[]
        for _,edge in zone_edges.iterrows():
            cap=float(edge['capacity']);flow_eq=float(edge['flow_eq'])
            remaining=max(0.0,cap*SAT_LIMIT-flow_eq)/PCU_BIKE
            remaining_bike.append({'remaining_ebike':remaining,'edge':f"{edge['from']}→{edge['to']}"})
        rv=sorted([r['remaining_ebike'] for r in remaining_bike])
        bi=max(0,min(len(rv)-1,int(len(rv)*0.05)))
        C_road=rv[bi] if rv else 0
        bneck=min(remaining_bike,key=lambda r:r['remaining_ebike']) if remaining_bike else None
        alpha=ALPHA_DEFAULT[period]
        N_dyn=C_road/alpha if alpha>0 else float('inf')
        period_results[period]={'C_road':C_road,'N_dyn':N_dyn,'num_edges':len(zone_edges),'bottleneck':bneck['edge'] if bneck else'-'}
    dyn_vals=[v['N_dyn'] for v in period_results.values() if v['N_dyn']>0]
    N_dynamic=int(np.floor(min(dyn_vals))) if dyn_vals else 0
    binding=min(period_results,key=lambda p:period_results[p]['N_dyn']) if period_results else'-'
    row={'zone_id':zid,'zone_name':zname,'N_dynamic':N_dynamic,'binding_period':binding}
    for period in PERIODS:
        pr=period_results.get(period,{})
        row[f'{period}_C_road']=f"{pr.get('C_road',0):.0f}"
        row[f'{period}_N_dyn']=f"{pr.get('N_dyn',0):.0f}"
        row[f'{period}_bottleneck']=pr.get('bottleneck','-')
    rows.append(row)
    print(f"{zid} {zname}: N_dynamic={N_dynamic} (卡在{binding}) "
          f"[早={period_results.get('morning',{}).get('N_dyn',0):.0f} "
          f"午={period_results.get('noon',{}).get('N_dyn',0):.0f} "
          f"晚={period_results.get('evening',{}).get('N_dyn',0):.0f}]")
df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR,"dynamic_capacity.csv"),index=False,encoding="utf-8-sig")
print(f"\nΣ N_dynamic = {sum(r['N_dynamic'] for r in rows)} | 输出: {OUTPUT_DIR}/")
