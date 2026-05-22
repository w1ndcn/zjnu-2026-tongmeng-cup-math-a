"""
步骤三：多类用户均衡交通分配（Frank-Wolfe）
==========================================
BPR 阻抗 + FW 求解 → 路段流量、TTT、V/C、人车冲突风险 S
"""

import networkx as nx
import numpy as np
import pandas as pd
import os
import heapq
import math
from collections import defaultdict

# ========== 配置 ==========
STEP1_DIR = "output_step1"
STEP2_DIR = "output_step2"
OUTPUT_DIR = "output_step3"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# BPR
ALPHA = 0.15
BETA = 4.0

# PCU 等效系数
XI = {'p': 0.10, 'b': 0.30, 'c': 1.00, 'bus': 0.50}

# 各方式自由流速度 (m/s)
V_FREE = {'p': 1.39, 'b': 4.17, 'c': 5.56, 'bus': 4.17}

# 冲突风险权重 (pb, pc, bc)
OMEGA = {'pb': 0.5, 'pc': 1.5, 'bc': 0.8}

MODES = ['p', 'b', 'c', 'bus']
PERIODS = ['morning', 'noon', 'evening']
PERIOD_HOURS = {'morning': 0.75, 'noon': 0.83, 'evening': 0.67}

# FW 控制
FW_MAX_ITER = 50
FW_TOL = 1e-4

# ═══════════════════ 1. 加载图 ═══════════════════
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
nodes_list = list(G.nodes())
print(f"图加载: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")

# 构建邻接表 + 边属性（高效 Dijkstra）
adj = defaultdict(list)       # adj[u] = [(v, eid), ...]
edge_id = {}                  # (u,v) → eid
edge_attr = {}                # eid → {u, v, length, width, capacity, t0_m}
for eid, (u, v, data) in enumerate(G.edges(data=True)):
    length = float(data.get('length', 100))
    width = float(data.get('width', 6))
    cap = float(data.get('capacity', 600))
    t0_m = {m: length / V_FREE[m] for m in MODES}
    edge_id[(u, v)] = eid
    edge_attr[eid] = {'u': u, 'v': v, 'length': length, 'width': width,
                       'capacity': cap, 't0': t0_m}
    adj[u].append((v, eid))

# ═══════════════════ 2. BPR 函数 ═══════════════════
def bpr_cost(t0, capacity, flow):
    if capacity <= 0:
        return t0 * 10
    return t0 * (1 + ALPHA * (flow / capacity) ** BETA)

def bpr_integral(t0, capacity, flow):
    """∫₀ˣ t(w)dw = t0·[x + α·C/(β+1)·(x/C)^(β+1)]"""
    if capacity <= 0 or flow <= 0:
        return 0.0
    r = flow / capacity
    return t0 * (flow + ALPHA * capacity / (BETA + 1) * r ** (BETA + 1))

# ═══════════════════ 3. Dijkstra ═══════════════════
def dijkstra(source, cost_func):
    dist = {source: 0.0}
    prev = {}
    prev_edge = {}
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        for v, eid in adj.get(u, []):
            nd = d + cost_func(eid)
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                prev_edge[v] = eid
                heapq.heappush(heap, (nd, v))
    return dist, prev, prev_edge

def get_path_nodes(prev, source, target):
    """回溯路径节点序列"""
    if target not in prev:
        return None
    path = [target]
    cur = target
    while cur != source:
        cur = prev[cur]
        path.append(cur)
    return path[::-1]

# ═══════════════════ 4. AON 分配 ═══════════════════
def assign_aon(od, x_eq):
    """
    全有全无分配：每条 OD 全部流量走当前最短路径
    返回 aon_eq[eid], aon_mode[(eid,mode)]
    """
    aon_mode = defaultdict(float)

    for (origin, dest, mode), demand in od.items():
        if demand <= 0 or origin not in adj or dest not in adj:
            continue

        def cost_func(eid):
            attr = edge_attr[eid]
            xe = x_eq.get(eid, 0.0)
            return bpr_cost(attr['t0'][mode], attr['capacity'], xe)

        dist, prev, _ = dijkstra(origin, cost_func)
        path = get_path_nodes(prev, origin, dest)
        if path is None:
            continue

        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            eid = edge_id.get((u, v))
            if eid is not None:
                aon_mode[(eid, mode)] += demand

    aon_eq = defaultdict(float)
    for (eid, mode), flow in aon_mode.items():
        aon_eq[eid] += XI[mode] * flow

    return dict(aon_eq), dict(aon_mode)

# ═══════════════════ 5. Frank-Wolfe ═══════════════════
def frank_wolfe(od):
    """FW 求解多类 UE，返回 x_mode, x_eq"""
    n_edges = len(edge_attr)

    # 初始化 AON（自由流）
    x_eq_zero = {eid: 0.0 for eid in edge_attr}
    aux_eq0, aux_mode0 = assign_aon(od, x_eq_zero)
    x_mode = defaultdict(float, aux_mode0)
    x_eq = defaultdict(float, aux_eq0)

    prev_obj = math.inf
    for it in range(FW_MAX_ITER):
        # 目标函数
        obj = 0.0
        for eid in edge_attr:
            attr = edge_attr[eid]
            obj += bpr_integral(attr['t0']['p'], attr['capacity'], x_eq.get(eid, 0.0))

        # AON 辅助方向
        y_eq, y_mode = assign_aon(od, x_eq)

        # ── 线搜索：一阶条件二分法（正确做法）──
        # dZ/dλ = Σ_e t_e(x_e+λ(y_e-x_e))·(y_e-x_e)
        lo, hi = 0.0, 1.0
        for _ in range(25):
            lam = (lo + hi) / 2
            grad = 0.0
            for eid in edge_attr:
                xe = x_eq.get(eid, 0.0)
                ye = y_eq.get(eid, 0.0)
                if abs(ye - xe) < 1e-10:
                    continue
                xnew = xe + lam * (ye - xe)
                if xnew < 0:
                    xnew = 0
                attr = edge_attr[eid]
                t_val = bpr_cost(attr['t0']['p'], attr['capacity'], xnew)
                grad += t_val * (ye - xe)
            if grad > 0:
                hi = lam
            else:
                lo = lam
        lam_opt = (lo + hi) / 2

        # 更新流量
        new_x_mode = defaultdict(float)
        for key in set(x_mode) | set(y_mode):
            new_x_mode[key] = x_mode.get(key, 0.0) + lam_opt * (y_mode.get(key, 0.0) - x_mode.get(key, 0.0))
            if new_x_mode[key] < 0:
                new_x_mode[key] = 0

        new_x_eq = defaultdict(float)
        for eid in edge_attr:
            xe = x_eq.get(eid, 0.0)
            ye = y_eq.get(eid, 0.0)
            new_x_eq[eid] = max(xe + lam_opt * (ye - xe), 0)

        x_mode = new_x_mode
        x_eq = new_x_eq

        # 收敛判断
        rel_change = abs(obj - prev_obj) / (abs(prev_obj) + 1e-10)
        if it % 10 == 0 or it < 3:
            print(f"    FW iter {it:3d}: obj={obj:.2f}, λ={lam_opt:.4f}, Δ={rel_change:.2e}")
        if rel_change < FW_TOL and it > 5:
            print(f"    FW 收敛于 iter {it}")
            break
        prev_obj = obj

    return dict(x_mode), dict(x_eq)

# ═══════════════════ 6. 评价指标 ═══════════════════
def calc_ttt(x_mode, x_eq):
    """TTT = Σ_e,m x_e^m · t_e^m(X_e)"""
    ttt = 0.0
    for (eid, mode), flow in x_mode.items():
        if flow <= 0:
            continue
        attr = edge_attr[eid]
        t_val = bpr_cost(attr['t0'][mode], attr['capacity'], x_eq.get(eid, 0.0))
        ttt += flow * t_val
    return ttt

def calc_conflict(x_mode):
    """人车冲突风险 S = Σ_e (ω_pb·xp·xb + ω_pc·xp·xc + ω_bc·xb·xc)"""
    flow_by_edge = defaultdict(lambda: defaultdict(float))
    for (eid, mode), flow in x_mode.items():
        flow_by_edge[eid][mode] += flow

    total = 0.0
    risk_by_edge = {}
    for eid in edge_attr:
        f = flow_by_edge[eid]
        xp, xb, xc = f.get('p', 0), f.get('b', 0), f.get('c', 0)
        s = OMEGA['pb'] * xp * xb + OMEGA['pc'] * xp * xc + OMEGA['bc'] * xb * xc
        risk_by_edge[eid] = s
        total += s
    return total, risk_by_edge

def los_label(vc):
    if vc <= 0.35: return 'A'
    if vc <= 0.55: return 'B'
    if vc <= 0.75: return 'C'
    if vc <= 0.90: return 'D'
    if vc <= 1.00: return 'E'
    return 'F'

# ═══════════════════ 7. 主流程 ═══════════════════
results = {}

for period in PERIODS:
    print(f"\n{'='*50}")
    print(f"时段: {period}")

    # 加载 OD（按方式展开为 (origin,dest,mode)→demand）
    od = {}
    for mode in MODES:
        if mode == 'bus':
            continue
        fpath = os.path.join(STEP2_DIR, f"od_{period}_{mode}.csv")
        if not os.path.exists(fpath):
            continue
        df = pd.read_csv(fpath, index_col=0)
        for src in df.index:
            for dst in df.columns:
                val = df.loc[src, dst]
                if val > 0.01:
                    # 人次 → 人次/时段 → 保留为原始人次（FW 内部不关心时间单位）
                    od[(src, dst, mode)] = float(val)

    print(f"  OD 数: {len(od)}")

    # FW
    x_mode, x_eq = frank_wolfe(od)

    # 评价
    ttt = calc_ttt(x_mode, x_eq)
    s_total, s_by_edge = calc_conflict(x_mode)

    results[period] = {'x_mode': x_mode, 'x_eq': x_eq, 'TTT': ttt, 'S': s_total}

    print(f"  TTT = {ttt:.0f} 人·秒")
    print(f"  冲突风险 S = {s_total:.0f}")

    # ── 保存路段流量 CSV ──
    flow_by_edge = defaultdict(lambda: defaultdict(float))
    for (eid, mode), flow in x_mode.items():
        flow_by_edge[eid][mode] += flow

    rows = []
    for eid, attr in edge_attr.items():
        f = flow_by_edge[eid]
        xeq = x_eq.get(eid, 0.0)
        cap = attr['capacity']
        sat = xeq / cap if cap > 0 else 0
        rows.append({
            'edge_id': eid, 'from': attr['u'], 'to': attr['v'],
            'length_m': f"{attr['length']:.0f}", 'width_m': f"{attr['width']:.1f}",
            'capacity': f"{cap:.1f}",
            'flow_p': f"{f.get('p',0):.1f}", 'flow_b': f"{f.get('b',0):.1f}",
            'flow_c': f"{f.get('c',0):.1f}", 'flow_eq': f"{xeq:.1f}",
            'saturation': f"{sat:.4f}", 'LOS': los_label(sat),
            'risk': f"{s_by_edge.get(eid, 0):.1f}",
        })
    pd.DataFrame(rows).to_csv(os.path.join(OUTPUT_DIR, f"link_flow_{period}.csv"), index=False)

    # 摘要
    high = [r for r in rows if float(r['saturation']) > 0.75]
    print(f"  V/C>0.75: {len(high)} 条")
    for r in sorted(high, key=lambda x: -float(x['saturation']))[:5]:
        print(f"    {r['from']:8s}→{r['to']:8s}  V/C={r['saturation']}  {r['LOS']}")

# ── 保存基准 ──
with open(os.path.join(OUTPUT_DIR, "baseline.txt"), "w") as f:
    f.write("period,TTT,S\n")
    for p in PERIODS:
        f.write(f"{p},{results[p]['TTT']:.1f},{results[p]['S']:.1f}\n")

print(f"\n输出已保存到 {OUTPUT_DIR}/")
print(f"  link_flow_morning.csv  link_flow_noon.csv  link_flow_evening.csv")
print(f"  baseline.txt")
