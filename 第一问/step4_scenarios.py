"""
步骤四+六：情景方案设计 + 重跑UE + 效果评价
===========================================
方案A: 单行线（早高峰瓶颈路段改单向）
方案B: 分时限行（午高峰教学区周边禁机动车）
方案C: 综合方案（A+B+人车隔离）
→ 对比 TTT/S/V/C/重点OD通行时间
"""

import networkx as nx
import numpy as np
import pandas as pd
import os
import heapq
import math
import copy
from collections import defaultdict

STEP1_DIR = "output_step1"
STEP2_DIR = "output_step2"
STEP3_DIR = "output_step3"
OUTPUT_DIR = "output_step4"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# BPR / PCU 参数（同步 step3）
ALPHA, BETA = 0.15, 4.0
XI = {'p': 0.10, 'b': 0.30, 'c': 1.00, 'bus': 0.50}
V_FREE = {'p': 1.39, 'b': 4.17, 'c': 5.56, 'bus': 4.17}
OMEGA = {'pb': 0.5, 'pc': 1.5, 'bc': 0.8}
MODES = ['p', 'b', 'c']
PERIODS = ['morning', 'noon', 'evening']

# ═══════════════════ 1. 核心函数（从 step3 移植，参数化） ═══════════════════
def bpr_cost(t0, cap, flow):
    if cap <= 0: return t0 * 10
    return t0 * (1 + ALPHA * (flow / cap) ** BETA)

def dijkstra(source, adj, edge_attr, cost_func):
    dist = {source: 0.0}
    prev = {}
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf): continue
        for v, eid in adj.get(u, []):
            nd = d + cost_func(eid)
            if nd < dist.get(v, math.inf):
                dist[v] = nd; prev[v] = u
                heapq.heappush(heap, (nd, v))
    return dist, prev

def get_path(prev, src, dst):
    if dst not in prev: return None
    path = [dst]
    cur = dst
    while cur != src:
        cur = prev[cur]; path.append(cur)
    return path[::-1]

def assign_aon(od, adj, edge_attr, edge_id, x_eq):
    aon_mode = defaultdict(float)
    for (src, dst, mode), demand in od.items():
        if demand <= 0 or src not in adj or dst not in adj: continue
        def cf(eid):
            a = edge_attr[eid]
            return bpr_cost(a['t0'][mode], a['capacity'], x_eq.get(eid, 0))
        dist, prev = dijkstra(src, adj, edge_attr, cf)
        path = get_path(prev, src, dst)
        if path is None: continue
        for i in range(len(path)-1):
            eid = edge_id.get((path[i], path[i+1]))
            if eid is not None: aon_mode[(eid, mode)] += demand
    aon_eq = defaultdict(float)
    for (eid, mode), flow in aon_mode.items():
        aon_eq[eid] += XI[mode] * flow
    return dict(aon_eq), dict(aon_mode)

def frank_wolfe(od, adj, edge_attr, edge_id, max_iter=30):
    x_eq_zero = {eid: 0.0 for eid in edge_attr}
    aux_eq0, aux_mode0 = assign_aon(od, adj, edge_attr, edge_id, x_eq_zero)
    x_mode = defaultdict(float, aux_mode0)
    x_eq = defaultdict(float, aux_eq0)
    prev_obj = math.inf
    for it in range(max_iter):
        obj = sum(bpr_cost(edge_attr[e]['t0']['p'], edge_attr[e]['capacity'], x_eq.get(e, 0))
                  for e in edge_attr) * 100  # proxy
        y_eq, y_mode = assign_aon(od, adj, edge_attr, edge_id, x_eq)
        lo, hi = 0.0, 1.0
        for _ in range(20):
            lam = (lo+hi)/2; grad = 0.0
            for eid in edge_attr:
                xe, ye = x_eq.get(eid,0), y_eq.get(eid,0)
                if abs(ye-xe) < 1e-10: continue
                xnew = max(xe + lam*(ye-xe), 0)
                a = edge_attr[eid]
                grad += bpr_cost(a['t0']['p'], a['capacity'], xnew) * (ye-xe)
            if grad > 0: hi = lam
            else: lo = lam
        lam_opt = (lo+hi)/2
        new_x_mode = defaultdict(float)
        for k in set(x_mode)|set(y_mode):
            v = x_mode.get(k,0) + lam_opt*(y_mode.get(k,0)-x_mode.get(k,0))
            if v > 0: new_x_mode[k] = v
        new_x_eq = defaultdict(float)
        for eid in edge_attr:
            v = x_eq.get(eid,0) + lam_opt*(y_eq.get(eid,0)-x_eq.get(eid,0))
            if v > 0: new_x_eq[eid] = v
        x_mode, x_eq = new_x_mode, new_x_eq
        rel = abs(obj-prev_obj)/(abs(prev_obj)+1e-10)
        if rel < 1e-4 and it > 5: break
        prev_obj = obj
    return dict(x_mode), dict(x_eq)

def calc_ttt(x_mode, x_eq, edge_attr):
    ttt = 0.0
    for (eid, mode), flow in x_mode.items():
        if flow <= 0: continue
        a = edge_attr[eid]
        ttt += flow * bpr_cost(a['t0'][mode], a['capacity'], x_eq.get(eid,0))
    return ttt

def calc_conflict(x_mode, edge_attr, isolation_edges=None):
    """人车冲突风险，isolation_edges 享受折扣"""
    fb = defaultdict(lambda: defaultdict(float))
    for (eid, mode), flow in x_mode.items():
        fb[eid][mode] += flow
    total = 0.0
    for eid in edge_attr:
        f = fb[eid]; xp, xb, xc = f.get('p',0), f.get('b',0), f.get('c',0)
        s = OMEGA['pb']*xp*xb + OMEGA['pc']*xp*xc + OMEGA['bc']*xb*xc
        if isolation_edges and eid in isolation_edges:
            s *= 0.4  # 隔离降低60%风险
        total += s
    return total

# ═══════════════════ 2. 加载基础图 ═══════════════════
G0 = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))

def build_adj(G):
    adj = defaultdict(list); eid_map = {}; eattr = {}
    for eid, (u, v, data) in enumerate(G.edges(data=True)):
        l = float(data.get('length',100)); w = float(data.get('width',6))
        cap = float(data.get('capacity',600))
        eattr[eid] = {'u':u,'v':v,'length':l,'width':w,'capacity':cap,
                       't0':{m: l/V_FREE[m] for m in MODES}}
        adj[u].append((v, eid))
        eid_map[(u,v)] = eid
    return adj, eid_map, eattr

# ═══════════════════ 3. 情景方案定义 ═══════════════════
# 基于 step3 早高峰拥堵热力图设计

# 方案A: 单行线 — 仅对关键桥梁路段（南北连接），高峰期单向化避免对向冲突
SCENARIO_A = {
    'name': '方案A：关键桥梁单行线',
    'one_way_morning': [
        # 南北主桥 J_04↔J_19(140m)：早高峰北→南主导，设为单行
        ('J_04','J_19'),
        # 东侧桥 J_02↔J_16(60m)：设为单行
        ('J_02','J_16'),
    ],
}

# 方案B: 分时限行 — 午高峰食堂周边禁机动车
SCENARIO_B = {
    'name': '方案B：午高峰食堂区限行',
    'car_restrict_noon': [
        # 桃园食堂通道
        ('J_04','J_05'), ('J_05','J_06'),
        # 杏园食堂通道
        ('J_20','J_23'), ('J_23','J_24'),
        # 桂苑食堂通道
        ('J_29','J_30'),
    ],
}

# 方案C: 综合（A+B+人车隔离）
SCENARIO_C = {
    'name': '方案C：综合优化',
    'one_way_morning': SCENARIO_A['one_way_morning'],
    'car_restrict_noon': SCENARIO_B['car_restrict_noon'],
    'isolation': [
        # 建筑出入口隔离（行人/非机动车与机动车物理分隔）
        ('J_01','T_16_W'), ('J_15','T_16_E'), ('J_47','T_25'),
        ('J_05','C_T'), ('J_23','C_X'), ('J_30','C_G'),
        ('J_13','D_T'), ('J_24','D_X'), ('J_34','D_G'),
        # 主干道高风险段
        ('J_04','J_05'), ('J_05','J_07'), ('J_19','J_20'),
        ('J_20','J_21'), ('J_24','J_25'),
    ],
}

# ═══════════════════ 4. 方案应用 ═══════════════════
def apply_scenario(G, scenario, period):
    """返回修改后的 G 和 adj/edge_attr"""
    G_mod = G.copy()

    # 单行线：删反向边
    # 单行线（仅指定时段）
    one_way = []
    if period == 'morning':
        one_way = scenario.get('one_way_morning', [])
    elif period == 'noon':
        one_way = scenario.get('one_way_noon', [])
    elif period == 'evening':
        one_way = scenario.get('one_way_evening', [])
    one_way = one_way or scenario.get('one_way', [])  # fallback to non-period-specific

    for u, v in one_way:
        rev = (v, u)
        if G_mod.has_edge(*rev):
            # 也检查正向是否存在
            if G_mod.has_edge(u, v):
                G_mod.remove_edge(*rev)

    # 分时限行（仅午高峰）：降低禁行路段的 capacity
    if period == 'noon':
        for u, v in scenario.get('car_restrict_noon', []):
            if G_mod.has_edge(u, v):
                # 减少 capacity（模拟禁机动车后流量下降）
                old_cap = float(G_mod[u][v].get('capacity', 600))
                G_mod[u][v]['capacity'] = old_cap * 0.6  # 保留60%（步行+电动车仍需通行）

    adj, eid_map, eattr = build_adj(G_mod)

    # 隔离：将 (u,v) 对转为 eid 集合
    isolation_edges = set()
    for u, v in scenario.get('isolation', []):
        if (u, v) in eid_map:
            isolation_edges.add(eid_map[(u, v)])
        if (v, u) in eid_map:
            isolation_edges.add(eid_map[(v, u)])

    return G_mod, adj, eid_map, eattr, isolation_edges

# ═══════════════════ 5. 跑情景 ═══════════════════
def run_scenario(scenario):
    results = {}
    for period in PERIODS:
        G_mod, adj, eid_map, eattr, iso = apply_scenario(G0, scenario, period)

        # 加载 OD
        od = {}
        for mode in MODES:
            fp = os.path.join(STEP2_DIR, f"od_{period}_{mode}.csv")
            if os.path.exists(fp):
                df = pd.read_csv(fp, index_col=0)
                for src in df.index:
                    for dst in df.columns:
                        v = df.loc[src, dst]
                        if v > 0.01:
                            # 分时限行：午高峰禁机动车的路段，机动车的 OD 需求也削减
                            if period == 'noon' and mode == 'c':
                                v *= 0.3  # 70% 的车改步行/电动车/放弃
                            od[(src, dst, mode)] = float(v)

        x_mode, x_eq = frank_wolfe(od, adj, eattr, eid_map, max_iter=20)
        ttt = calc_ttt(x_mode, x_eq, eattr)
        s = calc_conflict(x_mode, eattr, iso if scenario.get('isolation') else None)

        # V/C 统计
        vc_list = []
        for eid, a in eattr.items():
            vc = x_eq.get(eid, 0) / a['capacity'] if a['capacity'] > 0 else 0
            vc_list.append(vc)

        results[period] = {'TTT': ttt, 'S': s, 'avg_VC': np.mean(vc_list),
                           'max_VC': max(vc_list), 'vc_list': vc_list}
        print(f"  {period:8s}: TTT={ttt:.0f}  S={s:.0f}  avgV/C={np.mean(vc_list):.3f}  maxV/C={max(vc_list):.3f}")
    return results

# ═══════════════════ 6. 跑对比 ═══════════════════
scenarios = [
    ({}, '基准（现状）'),
    (SCENARIO_A, SCENARIO_A['name']),
    (SCENARIO_B, SCENARIO_B['name']),
    (SCENARIO_C, SCENARIO_C['name']),
]

all_results = {}
print("=" * 60)
for scenario, name in scenarios:
    print(f"\n▶ {name}")
    all_results[name] = run_scenario(scenario)

# ═══════════════════ 7. 汇总对比 ═══════════════════
print("\n" + "=" * 60)
print("方案效果对比")
print("=" * 60)
baseline = all_results['基准（现状）']
rows = []
for name, res in all_results.items():
    ttt_sum = sum(res[p]['TTT'] for p in PERIODS)
    s_sum = sum(res[p]['S'] for p in PERIODS)
    vc_avg = np.mean([res[p]['avg_VC'] for p in PERIODS])
    vc_max = max(res[p]['max_VC'] for p in PERIODS)

    ttt_b = sum(baseline[p]['TTT'] for p in PERIODS)
    s_b = sum(baseline[p]['S'] for p in PERIODS)
    vc_b = np.mean([baseline[p]['avg_VC'] for p in PERIODS])

    eta_t = (ttt_b - ttt_sum) / max(ttt_b, 1) * 100
    eta_s = (s_b - s_sum) / max(s_b, 1) * 100
    eta_v = (vc_b - vc_avg) / max(vc_b, 1e-9) * 100

    rows.append({'方案': name, 'TTT合计': f'{ttt_sum:.0f}', 'η_TTT': f'{eta_t:+.1f}%',
                 'S合计': f'{s_sum:.0f}', 'η_S': f'{eta_s:+.1f}%',
                 'avgV/C': f'{vc_avg:.3f}', 'η_VC': f'{eta_v:+.1f}%',
                 'maxV/C': f'{vc_max:.3f}'})
    marker = " ← 最优" if name != '基准（现状）' and eta_t > 0 and eta_s > 0 else ""
    print(f"  {name:20s} TTT={ttt_sum:.0f}({eta_t:+.1f}%)  S={s_sum:.0f}({eta_s:+.1f}%)  V/C={vc_avg:.3f}{marker}")

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR, "scenario_comparison.csv"), index=False, encoding="utf-8-sig")
print(f"\n输出: {OUTPUT_DIR}/scenario_comparison.csv")
