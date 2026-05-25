import networkx as nx, pandas as pd, os
STEP1_DIR = "output_step1"
OUTPUT_DIR = "output_step8"
os.makedirs(OUTPUT_DIR, exist_ok=True)
ZONES = {
    'Z1': {'name':'16幢教学区','buildings':['T_16'],'A_eff':450,'type':'教学区'},
    'Z2': {'name':'25幢教学区','buildings':['T_25'],'A_eff':550,'type':'教学区'},
    'Z3': {'name':'桃园生活区','buildings':['TYGY','TYST'],'A_eff':8160,'type':'生活区'},
    'Z4': {'name':'杏园生活区','buildings':['XYGY','XYST'],'A_eff':5100,'type':'生活区'},
    'Z5': {'name':'桂苑生活区','buildings':['GYGY','CYGY','GYST'],'A_eff':7700,'type':'生活区'},
    'Z6': {'name':'东区新教学楼','buildings':['T_1','T_2','T_3','T_4','T_5'],'A_eff':2200,'type':'教学区'},
    'Z7': {'name':'西区新教学楼','buildings':['T_6','T_7','T_8','T_9','T_10'],'A_eff':4000,'type':'教学区'},
    'Z8': {'name':'商业街','buildings':['SYJ'],'A_eff':1200,'type':'商业区'},
}
G_di = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
G = G_di.to_undirected()
print(f"图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边(无向)")
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
rows = []; building_to_zone = {}
for zid, zinfo in ZONES.items():
    blds = zinfo['buildings']
    junctions, edge_list = find_zone_roads(G, blds, max_distance=2)
    for b in blds: building_to_zone[b] = zid
    widths = [e['width'] for e in edge_list if e['width']>0 and e['width']<99]
    min_w = min(widths) if widths else 0; max_w = max(widths) if widths else 0
    avg_w = sum(widths)/len(widths) if widths else 0
    rows.append({
        'zone_id':zid,'zone_name':zinfo['name'],'zone_type':zinfo['type'],
        'buildings':'|'.join(blds),'num_buildings':len(blds),'A_eff_m2':zinfo['A_eff'],
        'junctions':'|'.join(junctions[:15]),'num_junctions':len(junctions),
        'num_edges':len(edge_list),
        'min_road_width':f"{min_w:.1f}",'max_road_width':f"{max_w:.1f}",'avg_road_width':f"{avg_w:.1f}",
    })
    print(f"{zid} {zinfo['name']}: {', '.join(blds)} | "
          f"路口={len(junctions)} 路段={len(edge_list)} 路宽={min_w:.0f}~{max_w:.0f}m A_eff={zinfo['A_eff']}m²")
df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR,"zones.csv"),index=False,encoding="utf-8-sig")
pd.DataFrame([{'building':b,'zone_id':z} for b,z in building_to_zone.items()]).to_csv(
    os.path.join(OUTPUT_DIR,"building_zone_map.csv"),index=False,encoding="utf-8-sig")
print(f"\n共 {len(ZONES)} 个功能区 | 输出: {OUTPUT_DIR}/")
