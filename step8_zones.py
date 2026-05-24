"""
步骤八：校园功能区域划分（v3 — 扩校版 8 个功能区）
==================================================
输入: output_step1/campus_graph.gml
输出: output_step8/zones.csv, building_zone_map.csv
"""

import networkx as nx, pandas as pd, os

STEP1_DIR = "output_step1"
OUTPUT_DIR = "output_step8"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════ 区域定义 ═══════════════
# ZONES = {
#     'Z1': {'name':'16幢教学区','buildings':['T_16'],'A_eff':600,'type':'教学区'},
#     'Z2': {'name':'25幢教学区','buildings':['T_25'],'A_eff':400,'type':'教学区'},
#     'Z3': {'name':'桃园生活区','buildings':['TYGY','TYST'],'A_eff':1200,'type':'生活区'},
#     'Z4': {'name':'杏园生活区','buildings':['XYGY','XYST'],'A_eff':900,'type':'生活区'},
#     'Z5': {'name':'桂苑生活区','buildings':['GYGY','CYGY','GYST'],'A_eff':1500,'type':'生活区'},
#     'Z6': {'name':'东区新教学楼','buildings':['T_1','T_2','T_3','T_4','T_5'],'A_eff':800,'type':'教学区'},
#     'Z7': {'name':'西区新教学楼','buildings':['T_6','T_7','T_8','T_9','T_10'],'A_eff':800,'type':'教学区'},
#     'Z8': {'name':'商业街','buildings':['SYJ'],'A_eff':300,'type':'商业区'},
# }

ZONES = {
    # A_raw_m2 为地图估计的候选停车空间；lambda_safe 为消防/人行/出入口/绿化等安全折减系数；
    # A_eff_m2 = A_raw_m2 * lambda_safe，表示真正可用于停车的有效面积。
    'Z1': {'name':'16幢教学区','buildings':['T_16'],'A_raw':450,'lambda_safe':0.65,'type':'教学区'},
    'Z2': {'name':'25幢教学区','buildings':['T_25'],'A_raw':550,'lambda_safe':0.65,'type':'教学区'},
    'Z3': {'name':'桃园生活区','buildings':['TYGY','TYST'],'A_raw':8160,'lambda_safe':0.50,'type':'生活区'},
    'Z4': {'name':'杏园生活区','buildings':['XYGY','XYST'],'A_raw':5100,'lambda_safe':0.55,'type':'生活区'},
    'Z5': {'name':'桂苑生活区','buildings':['GYGY','CYGY','GYST'],'A_raw':7700,'lambda_safe':0.50,'type':'生活区'},
    'Z6': {'name':'东区新教学楼','buildings':['T_1','T_2','T_3','T_4','T_5'],'A_raw':2200,'lambda_safe':0.60,'type':'教学区'},
    'Z7': {'name':'西区新教学楼','buildings':['T_6','T_7','T_8','T_9','T_10'],'A_raw':4000,'lambda_safe':0.60,'type':'教学区'},
    'Z8': {'name':'商业街','buildings':['SYJ'],'A_raw':300,'lambda_safe':0.50,'type':'商业区'},
}

# ═══════════════ 加载 ═══════════════
G_di = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
G = G_di.to_undirected()
print(f"图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边(无向)")

# ═══════════════ 找区域周边道路 ═══════════════
def find_zone_roads(G, building_list, max_distance=2):
    junctions = set(); edges_in_zone = []
    for bld in building_list:
        if bld not in G: continue
        visited = {bld: 0}; queue = [bld]
        while queue:
            u = queue.pop(0); dist = visited[u]
            if dist >= max_distance: continue
            for v in G.neighbors(u):
                if v not in visited:
                    visited[v] = dist+1; queue.append(v)
                    ntype = str(G.nodes[v].get('type',''))
                    if ntype == '交叉口': junctions.add(v)
    seen = set()
    for u in junctions:
        for v in G.neighbors(u):
            if v in junctions:
                key = tuple(sorted([u,v]))
                if key in seen: continue
                seen.add(key)
                w = float(G[u][v].get('width',0))
                l = float(G[u][v].get('length',0))
                edges_in_zone.append({'from':u,'to':v,'width':w,'length':l})
    return sorted(junctions), edges_in_zone

# ═══════════════ 主流程 ═══════════════
rows = []; building_to_zone = {}
for zid, zinfo in ZONES.items():
    blds = zinfo['buildings']
    A_raw = float(zinfo['A_raw'])
    lambda_safe = float(zinfo['lambda_safe'])
    A_eff = A_raw * lambda_safe
    junctions, edge_list = find_zone_roads(G, blds, max_distance=2)
    for b in blds: building_to_zone[b] = zid
    widths = [e['width'] for e in edge_list if e['width']>0 and e['width']<99]
    min_w = min(widths) if widths else 0; max_w = max(widths) if widths else 0
    avg_w = sum(widths)/len(widths) if widths else 0
    rows.append({
        'zone_id':zid,'zone_name':zinfo['name'],'zone_type':zinfo['type'],
        'buildings':'|'.join(blds),'num_buildings':len(blds),
        'A_raw_m2':f"{A_raw:.0f}",'lambda_safe':f"{lambda_safe:.2f}",'A_eff_m2':f"{A_eff:.0f}",
        'junctions':'|'.join(junctions[:15]),'num_junctions':len(junctions),
        'num_edges':len(edge_list),
        'min_road_width':f"{min_w:.1f}",'max_road_width':f"{max_w:.1f}",'avg_road_width':f"{avg_w:.1f}",
    })
    print(f"{zid} {zinfo['name']}: {', '.join(blds)} | "
          f"路口={len(junctions)} 路段={len(edge_list)} 路宽={min_w:.0f}~{max_w:.0f}m "
          f"A_raw={A_raw:.0f}m² λ={lambda_safe:.2f} A_eff={A_eff:.0f}m²")

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR,"zones.csv"),index=False,encoding="utf-8-sig")
pd.DataFrame([{'building':b,'zone_id':z} for b,z in building_to_zone.items()]).to_csv(
    os.path.join(OUTPUT_DIR,"building_zone_map.csv"),index=False,encoding="utf-8-sig")

print(f"\n共 {len(ZONES)} 个功能区 | 输出: {OUTPUT_DIR}/")
