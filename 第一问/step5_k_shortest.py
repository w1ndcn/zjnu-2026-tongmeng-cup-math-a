"""
步骤五：K 短路径分流（Yen's Algorithm — blocked-edge 版本）
输入: step1 图 + step2 OD + step3 现状流量
输出: k_shortest_paths.csv + path_report.txt
"""

import networkx as nx
import numpy as np
import pandas as pd
import os
import math
import heapq
from collections import defaultdict

STEP1_DIR = "output_step1"
STEP2_DIR = "output_step2"
STEP3_DIR = "output_step3"
OUTPUT_DIR = "output_step5"
os.makedirs(OUTPUT_DIR, exist_ok=True)

K_PATHS = 3
RHO = 2.0
THETA = {'time': 0.40, 'dist': 0.20, 'risk': 0.30, 'penalty': 0.10}

SOURCES = ['T_16_E', 'T_16_W', 'T_25']
TARGETS = ['C_T', 'C_X', 'C_G', 'C_S', 'D_T', 'D_X', 'D_C', 'D_G']
PERIODS = ['morning', 'noon', 'evening']

# ═══════════════════ 1. 加载数据 ═══════════════════
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
print(f"图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")

# 邻接表 + 边属性
adj = defaultdict(list)
edge_attr = {}
edge_by_nodes = {}
for eid, (u, v, data) in enumerate(G.edges(data=True)):
    length = float(data.get('length', 100))
    width = float(data.get('width', 6))
    edge_attr[eid] = {'u': u, 'v': v, 'length': length, 'width': width}
    adj[u].append((v, eid))
    edge_by_nodes[(u, v)] = eid

# ═══════════════════ 2. Dijkstra（支持 blocked） ═══════════════════
def dijkstra_blocked(source, cost_map, blocked_nodes=None, blocked_edges=None):
    blocked_nodes = blocked_nodes or set()
    blocked_edges = blocked_edges or set()
    dist = {source: 0.0}
    prev = {}
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        for v, eid in adj[u]:
            if v in blocked_nodes or eid in blocked_edges:
                continue
            c = cost_map.get(eid, math.inf)
            nd = d + c
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    return dist, prev

def path_from_prev(prev, source, target):
    if target not in prev and target != source:
        return None
    path = [target]
    cur = target
    while cur != source:
        cur = prev[cur]
        path.append(cur)
    return list(reversed(path))

def path_to_edges(path_nodes):
    edges = []
    for i in range(len(path_nodes) - 1):
        eid = edge_by_nodes.get((path_nodes[i], path_nodes[i+1]), -1)
        edges.append(eid)
    return edges

# ═══════════════════ 3. Yen's Algorithm ═══════════════════
def yen_k_shortest(source, target, cost_map, K=3):
    dist, prev = dijkstra_blocked(source, cost_map)
    if math.isinf(dist.get(target, math.inf)):
        return []

    p1_nodes = path_from_prev(prev, source, target)
    if p1_nodes is None:
        return []
    p1_edges = path_to_edges(p1_nodes)
    p1_cost = sum(cost_map.get(e, 0) for e in p1_edges if e >= 0)

    A = [(p1_cost, p1_nodes, p1_edges)]
    B = []

    for ki in range(1, K):
        prev_nodes, prev_edges = A[-1][1], A[-1][2]
        for spur_idx in range(len(prev_nodes) - 1):
            spur_node = prev_nodes[spur_idx]
            root_path = prev_nodes[:spur_idx + 1]

            # 屏蔽所有已知路径在 spur_idx 处的下一条边
            blocked_e = set()
            for _, pn, pe in A:
                if pn[:spur_idx + 1] == root_path and spur_idx < len(pe):
                    blocked_e.add(pe[spur_idx])
            blocked_n = set(root_path[:-1])

            d_spur, prev_s = dijkstra_blocked(spur_node, cost_map, blocked_n, blocked_e)
            if math.isinf(d_spur.get(target, math.inf)):
                continue

            spur_nodes = path_from_prev(prev_s, spur_node, target)
            if spur_nodes is None:
                continue

            full_path = root_path + spur_nodes[1:]
            full_cost = d_spur[target] + sum(
                cost_map.get(path_to_edges(root_path)[j], 0)
                for j in range(len(root_path) - 1))

            if any(n == full_path for _, n, _ in A):
                continue
            if any(n == full_path for _, n, _ in B):
                continue

            full_edges = path_to_edges(full_path)
            heapq.heappush(B, (full_cost, full_path, full_edges))

        if not B:
            break
        A.append(heapq.heappop(B))

    return A[:K]

# ═══════════════════ 4. 广义费用 + 分流 ═══════════════════
def edge_risk(width):
    return 1.0 / max(float(width), 1.0)

def generalized_cost(path_nodes, path_edges):
    T = D = R = 0.0
    for eid in path_edges:
        if eid < 0 or eid not in edge_attr:
            continue
        a = edge_attr[eid]
        T += a['length'] / 4.17   # 电动车自由流 (m/s)
        D += a['length']
        R += edge_risk(a['width'])
    g = THETA['time'] * T + THETA['dist'] * D / 1000 + THETA['risk'] * R + THETA['penalty'] * 0
    return g, T, D, R

def split_ratio(costs):
    w = [(1.0 / max(c, 1e-9)) ** RHO for c in costs]
    s = sum(w)
    return [x / s for x in w]

# ═══════════════════ 5. 加载 step3 拥堵数据（按方式分流量 + V/C） ═══════════════════
def load_step3_flow(period):
    fpath = os.path.join(STEP3_DIR, f"link_flow_{period}.csv")
    if not os.path.exists(fpath):
        return {}
    df = pd.read_csv(fpath)
    flow = {}
    for _, row in df.iterrows():
        u, v = row['from'], row['to']
        flow[(u, v)] = {
            'flow_p': float(row.get('flow_p', 0)),
            'flow_b': float(row.get('flow_b', 0)),
            'V/C': float(row.get('saturation', 0)),
        }
    return flow

# ═══════════════════ 6. 主流程 ═══════════════════
cost_map = {eid: a['length'] / 4.17 for eid, a in edge_attr.items()}  # 电动车自由流
all_records = []

for period in PERIODS:
    # 加载该时段总需求 OD
    od_path = os.path.join(STEP2_DIR, f"od_{period}_total.csv")
    if not os.path.exists(od_path):
        continue
    od_df = pd.read_csv(od_path, index_col=0)
    step3_flow = load_step3_flow('morning')  # 用早高峰拥堵数据做风险参考

    for src in SOURCES:
        if src not in G:
            continue
        for tgt in TARGETS:
            if tgt not in G or src == tgt:
                continue
            q_total = float(od_df.loc[src, tgt]) if src in od_df.index and tgt in od_df.columns else 0
            if q_total < 0.01:
                continue

            k_paths = yen_k_shortest(src, tgt, cost_map, K=K_PATHS)
            if not k_paths:
                continue

            g_list = []
            for cost_y, pn, pe in k_paths:
                g, T, D, R = generalized_cost(pn, pe)
                g_list.append((g, T, D, R, pn, pe))

            ratios = split_ratio([g for g, _, _, _, _, _ in g_list])

            for ki, ((g, T, D, R, pn, pe), ratio) in enumerate(zip(g_list, ratios)):
                flow = q_total * ratio
                all_records.append({
                    'period': period, 'source': src, 'target': tgt,
                    'rank': ki + 1, 'distance_m': f"{D:.0f}",
                    'time_s': f"{T:.1f}", 'generalized_cost': f"{g:.3f}",
                    'allocation_pct': f"{ratio*100:.1f}",
                    'flow_person': f"{flow:.0f}",
                    'path': " → ".join(pn),
                })

# ═══════════════════ 7. 保存 ═══════════════════
df = pd.DataFrame(all_records)
df.to_csv(os.path.join(OUTPUT_DIR, "k_shortest_paths.csv"), index=False, encoding="utf-8-sig")

# 可读报告
with open(os.path.join(OUTPUT_DIR, "path_report.txt"), "w", encoding="utf-8") as f:
    f.write("=" * 70 + "\n")
    f.write("重点 OD K 短路径分流报告\n")
    f.write(f"K={K_PATHS}  ρ={RHO}  θ=({THETA['time']},{THETA['dist']},{THETA['risk']},{THETA['penalty']})\n")
    f.write("=" * 70 + "\n\n")
    for period in PERIODS:
        recs = [r for r in all_records if r['period'] == period]
        if not recs:
            continue
        f.write(f"\n▶ {period}\n")
        seen = set()
        for r in recs:
            key = (r['source'], r['target'])
            if key not in seen:
                seen.add(key)
                subset = [x for x in recs if x['source'] == r['source'] and x['target'] == r['target']]
                for x in subset:
                    nodes = x['path'].split(" → ")
                    preview = " → ".join(nodes[:6]) + (" → ..." if len(nodes) > 6 else "")
                    f.write(f"  {x['source']}→{x['target']}  P{x['rank']}: "
                            f"{x['distance_m']}m  {x['allocation_pct']}%  "
                            f"g={x['generalized_cost']}  flow={x['flow_person']}\n"
                            f"    {preview}\n")

print(f"\n输出: {OUTPUT_DIR}/k_shortest_paths.csv  ({len(all_records)} 条)")
print(f"      {OUTPUT_DIR}/path_report.txt")
