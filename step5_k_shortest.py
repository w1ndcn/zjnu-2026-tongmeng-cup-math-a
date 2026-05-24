"""
步骤五：K 短路径分流（v2 — 适配新路网）
========================================
输入: step1 GML + step2 OD + step3 流量
输出: k_shortest_paths.csv + path_report.txt
"""

import networkx as nx
import numpy as np
import pandas as pd
import os, math, heapq
from collections import defaultdict

STEP1_DIR = "output_step1"
STEP2_DIR = "output_step2"
STEP3_DIR = "output_step3"
OUTPUT_DIR = "output_step5"
os.makedirs(OUTPUT_DIR, exist_ok=True)

K_PATHS = 3; RHO = 2.0
THETA = {'time': 0.40, 'dist': 0.20, 'risk': 0.30, 'penalty': 0.10}
SOURCES = ['T_16', 'T_25']
TARGETS = ['TYST', 'XYST', 'GYST',           # 食堂
           'TYGY', 'XYGY', 'CYGY', 'GYGY']   # 宿舍

PERIODS = ['morning', 'noon', 'evening']

# ═══════════════ 加载 ═══════════════
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
print(f"图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")

adj = defaultdict(list)
edge_attr = {}
edge_by_nodes = {}
for eid, (u, v, data) in enumerate(G.edges(data=True)):
    length = float(data.get('length', 100))
    width = float(data.get('width', 6))
    edge_attr[eid] = {'u': u, 'v': v, 'length': length, 'width': width}
    adj[u].append((v, eid))
    edge_by_nodes[(u, v)] = eid

# ═══════════════ Yen's ═══════════════
def dijkstra_blocked(source, cost_map, blocked_nodes=None, blocked_edges=None):
    blocked_nodes = blocked_nodes or set(); blocked_edges = blocked_edges or set()
    dist = {source: 0.0}; prev = {}
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf): continue
        for v, eid in adj[u]:
            if v in blocked_nodes or eid in blocked_edges: continue
            nd = d + cost_map.get(eid, math.inf)
            if nd < dist.get(v, math.inf):
                dist[v] = nd; prev[v] = u; heapq.heappush(heap, (nd, v))
    return dist, prev

def path_from_prev(prev, source, target):
    if target not in prev and target != source: return None
    path = [target]; cur = target
    while cur != source:
        cur = prev[cur]; path.append(cur)
    return list(reversed(path))

def path_to_edges(path_nodes):
    return [edge_by_nodes.get((path_nodes[i], path_nodes[i+1]), -1)
            for i in range(len(path_nodes)-1)]

def yen_k_shortest(source, target, cost_map, K=3):
    dist, prev = dijkstra_blocked(source, cost_map)
    if math.isinf(dist.get(target, math.inf)): return []
    p1_nodes = path_from_prev(prev, source, target)
    if p1_nodes is None: return []
    p1_edges = path_to_edges(p1_nodes)
    A = [(sum(cost_map.get(e,0) for e in p1_edges if e>=0), p1_nodes, p1_edges)]
    B = []
    for ki in range(1, K):
        prev_nodes, prev_edges = A[-1][1], A[-1][2]
        for spur_idx in range(len(prev_nodes)-1):
            spur_node = prev_nodes[spur_idx]
            root_path = prev_nodes[:spur_idx+1]
            blocked_e = set()
            for _, pn, pe in A:
                if pn[:spur_idx+1]==root_path and spur_idx<len(pe): blocked_e.add(pe[spur_idx])
            d_spur, prev_s = dijkstra_blocked(spur_node, cost_map, set(root_path[:-1]), blocked_e)
            if math.isinf(d_spur.get(target, math.inf)): continue
            spur_nodes = path_from_prev(prev_s, spur_node, target)
            if spur_nodes is None: continue
            full_path = root_path + spur_nodes[1:]
            if any(n==full_path for _,n,_ in A): continue
            if any(n==full_path for _,n,_ in B): continue
            full_edges = path_to_edges(full_path)
            full_cost = d_spur[target]+sum(cost_map.get(path_to_edges(root_path)[j],0) for j in range(len(root_path)-1))
            heapq.heappush(B, (full_cost, full_path, full_edges))
        if not B: break
        A.append(heapq.heappop(B))
    return A[:K]

def generalized_cost(path_nodes, path_edges):
    T = D = R = 0.0
    for eid in path_edges:
        if eid<0 or eid not in edge_attr: continue
        a = edge_attr[eid]; T += a['length']/4.17; D += a['length']
        R += 1.0/max(float(a['width']),1.0)
    g = THETA['time']*T + THETA['dist']*D/1000 + THETA['risk']*R
    return g, T, D, R

def split_ratio(costs):
    w = [(1.0/max(c,1e-9))**RHO for c in costs]
    s = sum(w); return [x/s for x in w]

# ═══════════════ 主流程 ═══════════════
cost_map = {eid: a['length']/4.17 for eid, a in edge_attr.items()}
all_records = []

for period in PERIODS:
    od_path = os.path.join(STEP2_DIR, f"od_{period}_total.csv")
    if not os.path.exists(od_path): continue
    od_df = pd.read_csv(od_path, index_col=0)

    for src in SOURCES:
        if src not in G: continue
        for tgt in TARGETS:
            if tgt not in G or src == tgt: continue
            q = float(od_df.loc[src, tgt]) if src in od_df.index and tgt in od_df.columns else 0
            if q < 0.01: continue
            k_paths = yen_k_shortest(src, tgt, cost_map, K=K_PATHS)
            if not k_paths: continue
            g_list = []
            for cost_y, pn, pe in k_paths:
                g, T_, D_, R_ = generalized_cost(pn, pe)
                g_list.append((g, T_, D_, R_, pn, pe))
            ratios = split_ratio([g for g,_,_,_,_,_ in g_list])
            for ki, ((g, T_, D_, R_, pn, pe), ratio) in enumerate(zip(g_list, ratios)):
                flow = q * ratio
                all_records.append({
                    'period': period, 'source': src, 'target': tgt,
                    'rank': ki+1, 'distance_m': f"{D_:.0f}",
                    'time_s': f"{T_:.1f}", 'generalized_cost': f"{g:.3f}",
                    'allocation_pct': f"{ratio*100:.1f}",
                    'flow_person': f"{flow:.0f}",
                    'path': " → ".join(pn),
                })

df = pd.DataFrame(all_records)
df.to_csv(os.path.join(OUTPUT_DIR, "k_shortest_paths.csv"), index=False, encoding="utf-8-sig")

with open(os.path.join(OUTPUT_DIR, "path_report.txt"), "w", encoding="utf-8") as f:
    f.write("="*70+"\n")
    f.write("重点 OD K 短路径分流报告 (v2 新路网)\n")
    f.write(f"K={K_PATHS}  ρ={RHO}\n")
    f.write("="*70+"\n\n")
    for period in PERIODS:
        recs = [r for r in all_records if r['period']==period]
        if not recs: continue
        f.write(f"\n▶ {period}\n")
        seen = set()
        for r in recs:
            key = (r['source'], r['target'])
            if key not in seen:
                seen.add(key)
                subset = [x for x in recs if x['source']==r['source'] and x['target']==r['target']]
                for x in subset:
                    nodes = x['path'].split(" → ")
                    preview = " → ".join(nodes[:6])+(" → ..." if len(nodes)>6 else "")
                    f.write(f"  {x['source']}→{x['target']}  P{x['rank']}: "
                            f"{x['distance_m']}m  {x['allocation_pct']}%  "
                            f"g={x['generalized_cost']}  flow={x['flow_person']}\n    {preview}\n")

print(f"\nK短路径: {len(all_records)} 条 (2源×7目标×3路径={2*7*3})")
print(f"输出: {OUTPUT_DIR}/")
