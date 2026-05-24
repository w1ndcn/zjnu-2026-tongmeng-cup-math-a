"""
步骤四：情景方案设计（v2 — 适配新路网 N1-N64）
===============================================
基于 step3 早高峰拥堵结果设计三类治理方案，重跑 UE 对比效果。

方案 A：关键路段单行线（针对早晚高峰不对称流向）
方案 B：午高峰食堂区限行（capacity 降低）
方案 C：综合优化（A+B+人车隔离 14 条路段）
"""

import networkx as nx
import numpy as np
import pandas as pd
import os, math, heapq
from collections import defaultdict

STEP1_DIR = "output_step1"
STEP2_DIR = "output_step2"
STEP3_DIR = "output_step3"
OUTPUT_DIR = "output_step4"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALPHA, BETA = 0.15, 4.0
XI = {'p': 0.10, 'b': 0.30, 'c': 1.00}
V_FREE = {'p': 1.39, 'b': 4.17, 'c': 5.56}
OMEGA = {'pb': 0.5, 'pc': 1.5, 'bc': 0.8}
MODES = ['p', 'b', 'c']
PERIODS = ['morning', 'noon', 'evening']

# ═══════════════ 核心函数（同 step3） ═══════════════
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
    path = [dst]; cur = dst
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
                  for e in edge_attr) * 100
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
    fb = defaultdict(lambda: defaultdict(float))
    for (eid, mode), flow in x_mode.items():
        fb[eid][mode] += flow
    total = 0.0
    for eid in edge_attr:
        f = fb[eid]; xp, xb, xc = f.get('p',0), f.get('b',0), f.get('c',0)
        s = OMEGA['pb']*xp*xb + OMEGA['pc']*xp*xc + OMEGA['bc']*xb*xc
        if isolation_edges and eid in isolation_edges:
            s *= 0.4
        total += s
    return total

# ═══════════════ 建图 ═══════════════
G0 = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))

def build_adj(G):
    adj = defaultdict(list); eid_map = {}; eattr = {}
    for eid, (u, v, data) in enumerate(G.edges(data=True)):
        l = float(data.get('length',100))
        cap = float(data.get('capacity',600))
        virt = data.get('virtual', False)
        eattr[eid] = {'u':u,'v':v,'length':l,'capacity':cap,
                       't0':{m: l/V_FREE[m] for m in MODES}, 'virtual':virt}
        adj[u].append((v, eid))
        eid_map[(u,v)] = eid
    return adj, eid_map, eattr

# ═══════════════════ 情景方案（新路网版） ═══════════════════

# 方案A: 早高峰单行线 — 基于v3实测V/C瓶颈重选
SCENARIO_A = {
    'name': '方案A：早高峰关键路段单行线',
    'one_way_morning': [
        # 杏园→16幢主通道 (V/C=1.710, 最严重瓶颈)
        ('N30', 'N16'),
        # 桃园→中心区主通道 (V/C=1.259, 早高峰北→南主导)
        ('N4', 'N14'),
        # 西区→教学区通道 (V/C=0.725, risk=1.8M)
        ('N49', 'N48'),
    ],
}

# 方案B: 午高峰关键路段限行（数据驱动，基于v3实际V/C瓶颈）
SCENARIO_B = {
    'name': '方案B：午高峰关键路段限行',
    'car_demand_noon': 0.3,  # 午高峰机动车需求降至30%（方案专属）
    'car_restrict_noon': [
        # 瓶颈路段（午高峰 V/C 数据驱动）
        ('N16', 'N30'),    # V/C=1.315 最严重瓶颈
        ('N48', 'N49'),    # V/C=0.857 第二
        ('N25', 'N26'),    # V/C=0.310
        ('N26', 'N27'),    # V/C=0.310
        # 食堂核心区（车辆限行，降低通行能力）
        ('N14', 'N15'), ('N14', 'N4'), ('N14', 'N6'),
        ('N30', 'N12'), ('N28', 'N12'),
        ('N28', 'N29'), ('N29', 'N31'), ('N31', 'N32'),
        # 商业街周边
        ('N12', 'N13'),
    ],
}

# 方案C: 综合（A+B+人车隔离）
SCENARIO_C = {
    'name': '方案C：综合优化',
    'one_way_morning': SCENARIO_A['one_way_morning'],
    'car_demand_noon': SCENARIO_B['car_demand_noon'],
    'car_restrict_noon': SCENARIO_B['car_restrict_noon'],
    'isolation': [
        # 早高峰高风险段 (风险 > 1.1M)
        ('N30', 'N16'),    # risk=6.3M morning, V/C=1.710
        ('N4', 'N14'),     # risk=2.1M morning, V/C=1.259
        ('N49', 'N48'),    # risk=1.8M morning, V/C=0.725
        ('N33', 'N31'),    # risk=1.3M morning, V/C=0.637
        ('N60', 'N33'),    # risk=1.1M morning, V/C=0.858
        ('N61', 'N60'),    # risk=1.1M morning, V/C=0.858
        # 午高峰高风险段
        ('N16', 'N30'),    # risk=4.0M noon, V/C=1.315
        ('N48', 'N49'),    # risk=3.1M noon, V/C=0.857
        # 晚高峰高风险段
        ('N14', 'N4'),     # risk=1.4M evening, V/C=1.068
        # 教学楼核心区 (16幢/25幢周边)
        ('N14', 'N15'), ('N15', 'N16'),
        ('N47', 'N48'), ('N48', 'N38'),
        # 食堂-商业街核心区
        ('N28', 'N29'), ('N29', 'N31'),
        # 西区教学群高风险段
        ('N42', 'N43'), ('N46', 'N49'),
    ],
}

# ═══════════════ 方案应用 ═══════════════
def apply_scenario(G, scenario, period):
    G_mod = G.copy()

    # 单行线
    one_way = []
    if period == 'morning':
        one_way = scenario.get('one_way_morning', [])
    elif period == 'noon':
        one_way = scenario.get('one_way_noon', [])
    elif period == 'evening':
        one_way = scenario.get('one_way_evening', [])
    one_way = one_way or scenario.get('one_way', [])

    for u, v in one_way:
        if G_mod.has_edge(v, u) and G_mod.has_edge(u, v):
            G_mod.remove_edge(v, u)

    # 午高峰限行
    if period == 'noon':
        for u, v in scenario.get('car_restrict_noon', []):
            if G_mod.has_edge(u, v):
                old = float(G_mod[u][v].get('capacity', 600))
                G_mod[u][v]['capacity'] = old * 0.6

    adj, eid_map, eattr = build_adj(G_mod)

    # 隔离
    isolation_edges = set()
    for u, v in scenario.get('isolation', []):
        if (u, v) in eid_map: isolation_edges.add(eid_map[(u, v)])
        if (v, u) in eid_map: isolation_edges.add(eid_map[(v, u)])

    return G_mod, adj, eid_map, eattr, isolation_edges


# ═══════════════ 跑情景 ═══════════════
def run_scenario(scenario):
    results = {}
    for period in PERIODS:
        G_mod, adj, eid_map, eattr, iso = apply_scenario(G0, scenario, period)

        od = {}
        for mode in MODES:
            fp = os.path.join(STEP2_DIR, f"od_{period}_{mode}.csv")
            if os.path.exists(fp):
                df = pd.read_csv(fp, index_col=0)
                for src in df.index:
                    for dst in df.columns:
                        v = df.loc[src, dst]
                        if v > 0.01:
                            # 午高峰机动车需求削减（仅方案专属，非全局）
                            car_reduction = scenario.get('car_demand_noon', 1.0)
                            if period == 'noon' and mode == 'c':
                                v *= car_reduction
                            od[(src, dst, mode)] = float(v)

        x_mode, x_eq = frank_wolfe(od, adj, eattr, eid_map, max_iter=20)
        ttt = calc_ttt(x_mode, x_eq, eattr)
        s = calc_conflict(x_mode, eattr, iso if scenario.get('isolation') else None)

        vc_list = []
        for eid, a in eattr.items():
            vc = x_eq.get(eid, 0) / a['capacity'] if a['capacity'] > 0 else 0
            vc_list.append(vc)

        results[period] = {'TTT': ttt, 'S': s, 'avg_VC': np.mean(vc_list),
                           'max_VC': max(vc_list)}
        print(f"  {period:8s}: TTT={ttt:.0f}  S={s:.0f}  "
              f"avgV/C={np.mean(vc_list):.3f}  maxV/C={max(vc_list):.3f}")
    return results


# ═══════════════ 跑对比 ═══════════════
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

# ═══════════════ 汇总 ═══════════════
print("\n" + "=" * 60)
print("方案效果对比")
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
    print(f"  {name:20s} TTT={ttt_sum:.0f}({eta_t:+.1f}%)  S={s_sum:.0f}({eta_s:+.1f}%)  "
          f"V/C={vc_avg:.3f}{marker}")

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR, "scenario_comparison.csv"),
          index=False, encoding="utf-8-sig")
print(f"\n输出: {OUTPUT_DIR}/scenario_comparison.csv")
