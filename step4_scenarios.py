"""
步骤四：情景方案设计与对比
========================
设计三类治理方案（单行线/限行/综合优化），重跑UE分配，
对比各方案的TTT、冲突风险S、V/C等指标改善率。
"""

import networkx as nx
import pandas as pd
import numpy as np
import os, math, heapq
from collections import defaultdict
import copy

# ========== 路径配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STEP1_DIR = os.path.join(BASE_DIR, 'output_step1')
STEP2_DIR = os.path.join(BASE_DIR, 'output_step2')
STEP3_DIR = os.path.join(BASE_DIR, 'output_step3')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_step4')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== 模型参数（与step3一致） ==========
ALPHA, BETA = 0.15, 4.0
XI = {'p': 0.10, 'b': 0.30, 'c': 1.00}
V_FREE = {'p': 1.39, 'b': 4.17, 'c': 5.56}
OMEGA = {'pb': 0.5, 'pc': 1.5, 'bc': 0.8}
MODES = ['p', 'b', 'c']
PERIODS = ['morning', 'noon', 'evening']
FW_MAX = 20

# ========== 方案定义 ==========
# 方案A：早高峰单行线
ONEWAY_A = {
    'morning': [('N4', 'N14'), ('N30', 'N16'), ('N46', 'N49')],
}

# 方案B：午高峰关键路段限行 + 机动车需求削减
RESTRICT_B = {
    'noon': [
        # 午高峰瓶颈路段（capacity降至60%）
        ('N16', 'N30'),    # V/C=1.315 最严重
        ('N48', 'N49'),    # V/C=0.857
        ('N25', 'N26'),    # 东区教学群
        ('N26', 'N27'),
        # 食堂-商业街核心区
        ('N14', 'N15'), ('N14', 'N4'),
        ('N30', 'N12'), ('N28', 'N12'),
        ('N28', 'N29'), ('N29', 'N31'),
        ('N12', 'N13'),    # 商业街入口
    ],
}

# 方案C：人车隔离路段（冲突风险×0.4）
ISOLATE_C = [
    ('N4', 'N14'), ('N14', 'N15'), ('N15', 'N16'), ('N30', 'N16'),
    ('N28', 'N29'), ('N28', 'N31'), ('N33', 'N34'), ('N33', 'N46'),
    ('N46', 'N49'), ('N49', 'N48'), ('N37', 'N47'), ('N48', 'N38'),
    ('N33', 'N61'), ('N61', 'N62'),
]

ISO_SET = set()
for u, v in ISOLATE_C:
    ISO_SET.add((u, v))
    ISO_SET.add((v, u))

# ========== 核心函数（与step3一致） ==========
def bpr_cost(t0, cap, flow):
    if cap <= 0: return t0 * 10
    return t0 * (1 + ALPHA * (flow / cap) ** BETA)

def dijkstra(source, adj, cost_func):
    dist = {source: 0.0}; prev = {}; heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf): continue
        for v, eid in adj.get(u, []):
            nd = d + cost_func(eid)
            if nd < dist.get(v, math.inf):
                dist[v] = nd; prev[v] = u; heapq.heappush(heap, (nd, v))
    return dist, prev

def get_path(prev, src, dst):
    if dst not in prev: return None
    path = [dst]; cur = dst
    while cur != src: cur = prev[cur]; path.append(cur)
    return path[::-1]

def assign_aon(od, adj, eattr, eid_map, x_eq):
    aon_mode = defaultdict(float)
    for (src, dst, mode), demand in od.items():
        if demand <= 0 or src not in adj or dst not in adj: continue
        def cf(eid, _mode=mode):
            a = eattr[eid]; return bpr_cost(a['t0'][_mode], a['capacity'], x_eq.get(eid, 0))
        dist, prev = dijkstra(src, adj, cf)
        path = get_path(prev, src, dst)
        if path is None: continue
        for i in range(len(path) - 1):
            eid = eid_map.get((path[i], path[i + 1]))
            if eid is not None: aon_mode[(eid, mode)] += demand
    aon_eq = defaultdict(float)
    for (eid, mode), flow in aon_mode.items(): aon_eq[eid] += XI[mode] * flow
    return dict(aon_eq), dict(aon_mode)

def frank_wolfe(od, adj, eattr, eid_map):
    x_eq_zero = {eid: 0.0 for eid in eattr}
    aux_eq0, aux_mode0 = assign_aon(od, adj, eattr, eid_map, x_eq_zero)
    x_mode = defaultdict(float, aux_mode0); x_eq = defaultdict(float, aux_eq0)
    prev_obj = math.inf
    for it in range(FW_MAX):
        obj = sum(bpr_cost(eattr[eid]['t0']['p'], eattr[eid]['capacity'], x_eq.get(eid, 0)) for eid in eattr)
        y_eq, y_mode = assign_aon(od, adj, eattr, eid_map, x_eq)
        lo, hi = 0.0, 1.0
        for _ in range(20):
            lam = (lo + hi) / 2; grad = 0.0
            for eid in eattr:
                xe, ye = x_eq.get(eid, 0), y_eq.get(eid, 0)
                if abs(ye - xe) < 1e-10: continue
                xnew = max(xe + lam * (ye - xe), 0); a = eattr[eid]
                grad += bpr_cost(a['t0']['p'], a['capacity'], xnew) * (ye - xe)
            if grad > 0: hi = lam
            else: lo = lam
        lam_opt = (lo + hi) / 2
        new_x_mode = defaultdict(float)
        for k in set(x_mode) | set(y_mode):
            v = x_mode.get(k, 0) + lam_opt * (y_mode.get(k, 0) - x_mode.get(k, 0))
            if v > 0: new_x_mode[k] = v
        new_x_eq = defaultdict(float)
        for eid in eattr:
            v = x_eq.get(eid, 0) + lam_opt * (y_eq.get(eid, 0) - x_eq.get(eid, 0))
            if v > 0: new_x_eq[eid] = v
        x_mode, x_eq = new_x_mode, new_x_eq
        rel = abs(obj - prev_obj) / (abs(prev_obj) + 1e-10)
        if rel < 1e-4 and it > 5: break
        prev_obj = obj
    return dict(x_mode), dict(x_eq)

def build_adj_eattr(G):
    adj = defaultdict(list); eid_map = {}; eattr = {}
    for eid, (u, v, data) in enumerate(G.edges(data=True)):
        L = float(data['length']); cap = float(data['capacity'])
        eattr[eid] = {'u': u, 'v': v, 'length': L, 'capacity': cap,
                       'width': float(data.get('width', 6)),
                       't0': {m: L / V_FREE[m] for m in MODES}}
        adj[u].append((v, eid)); eid_map[(u, v)] = eid
    return adj, eid_map, eattr

def load_od(period):
    od = {}
    for mode in MODES:
        fp = os.path.join(STEP2_DIR, f'od_{period}_{mode}.csv')
        if not os.path.exists(fp): continue
        df = pd.read_csv(fp, index_col=0)
        for src in df.index:
            for dst in df.columns:
                v = float(df.loc[src, dst])
                if v > 0.01: od[(src, dst, mode)] = v
    return od

# ========== 应用方案修改图 ==========
def apply_scenario(G, scenario, period):
    """根据方案修改图结构"""
    G_mod = G.copy()

    # 方案A：删除反向边实现单行线
    if scenario in ('A', 'C'):
        oneway_edges = ONEWAY_A.get(period, [])
        for u, v in oneway_edges:
            if G_mod.has_edge(v, u):
                G_mod.remove_edge(v, u)

    # 方案B：限行路段降容
    if scenario in ('B', 'C'):
        restrict_edges = RESTRICT_B.get(period, [])
        for u, v in restrict_edges:
            if G_mod.has_edge(u, v):
                G_mod[u][v]['capacity'] = float(G_mod[u][v]['capacity']) * 0.6

    # 方案C：午高峰机动车需求降低
    return G_mod

def compute_metrics(x_mode, x_eq, eattr):
    ttt = 0.0
    for (eid, mode), flow in x_mode.items():
        a = eattr[eid]
        travel_time = bpr_cost(a['t0'][mode], a['capacity'], x_eq.get(eid, 0))
        ttt += flow * travel_time

    flow_by_mode = defaultdict(lambda: {'p': 0, 'b': 0, 'c': 0})
    for (eid, mode), flow in x_mode.items():
        flow_by_mode[eid][mode] = flow

    S = 0.0
    for eid, flows in flow_by_mode.items():
        a = eattr[eid]
        width = a['width'] if a['width'] < 99 else 6.0
        fp, fb, fc = flows['p'], flows['b'], flows['c']
        risk = (fp * fb * OMEGA['pb'] + fp * fc * OMEGA['pc'] + fb * fc * OMEGA['bc']) / width
        # 方案C隔离路段风险折扣
        u, v = a['u'], a['v']
        if scenario_is_isolated(u, v, current_scenario):
            risk *= 0.4
        S += risk

    return ttt, S

# 全局变量标记当前方案
current_scenario = 'baseline'

def scenario_is_isolated(u, v, scenario):
    if scenario != 'C':
        return False
    return (u, v) in ISO_SET

def run_scenario(scenario_name, G_base):
    """运行指定方案的UE分配"""
    global current_scenario
    current_scenario = scenario_name

    results = {}
    for period in PERIODS:
        # 应用方案
        G_mod = apply_scenario(G_base, scenario_name, period)
        adj, eid_map, eattr = build_adj_eattr(G_mod)
        od = load_od(period)

        # 方案B/C午高峰机动车需求削减
        if scenario_name in ('B', 'C') and period == 'noon':
            new_od = {}
            for (s, d, m), val in od.items():
                new_od[(s, d, m)] = val * 0.3 if m == 'c' else val
            od = new_od

        x_mode, x_eq = frank_wolfe(od, adj, eattr, eid_map)
        ttt, S = compute_metrics(x_mode, x_eq, eattr)

        # V/C统计
        vc_values = []
        for eid, a in eattr.items():
            eq_flow = x_eq.get(eid, 0)
            vc = eq_flow / a['capacity'] if a['capacity'] > 0 else 0
            vc_values.append(vc)

        results[period] = {
            'TTT': ttt, 'S': S,
            'avg_vc': np.mean(vc_values) if vc_values else 0,
            'max_vc': max(vc_values) if vc_values else 0,
        }
    return results

# ========== 主函数 ==========
def main():
    print("=" * 60)
    print("步骤四：情景方案设计与对比")
    print("=" * 60)

    G_base = nx.read_gml(os.path.join(STEP1_DIR, 'campus_graph.gml'))

    scenarios = [
        ('baseline', '基准（现状）'),
        ('A', '方案A：关键路段单行线'),
        ('B', '方案B：午高峰食堂区限行'),
        ('C', '方案C：综合优化'),
    ]

    all_results = {}
    for sname, sdesc in scenarios:
        print(f"\n--- {sdesc} ---")
        res = run_scenario(sname, G_base)
        all_results[sname] = res
        for period, r in res.items():
            print(f"  {period}: TTT={r['TTT']:,.0f}, S={r['S']:,.0f}, avgVC={r['avg_vc']:.4f}")

    # 汇总对比
    base = all_results['baseline']
    comparison = []
    period_names = {'morning': '早高峰', 'noon': '午高峰', 'evening': '晚高峰'}

    for sname, sdesc in scenarios:
        row = {'方案': sdesc}
        total_ttt = sum(all_results[sname][p]['TTT'] for p in PERIODS)
        total_s = sum(all_results[sname][p]['S'] for p in PERIODS)
        avg_vc = np.mean([all_results[sname][p]['avg_vc'] for p in PERIODS])
        max_vc = max(all_results[sname][p]['max_vc'] for p in PERIODS)

        row['TTT合计'] = round(total_ttt, 0)
        row['S合计'] = round(total_s, 0)
        row['avgV/C'] = round(avg_vc, 4)
        row['maxV/C'] = round(max_vc, 4)

        base_ttt = sum(base[p]['TTT'] for p in PERIODS)
        base_s = sum(base[p]['S'] for p in PERIODS)
        base_avg_vc = np.mean([base[p]['avg_vc'] for p in PERIODS])
        base_max_vc = max(base[p]['max_vc'] for p in PERIODS)

        row['eta_TTT'] = round((base_ttt - total_ttt) / base_ttt * 100, 1) if base_ttt > 0 else 0
        row['eta_S'] = round((base_s - total_s) / base_s * 100, 1) if base_s > 0 else 0
        row['eta_VC'] = round((base_avg_vc - avg_vc) / base_avg_vc * 100, 1) if base_avg_vc > 0 else 0

        comparison.append(row)

    comp_df = pd.DataFrame(comparison)
    comp_df.to_csv(os.path.join(OUTPUT_DIR, 'scenario_comparison.csv'), index=False, encoding='utf-8-sig')

    print("\n" + "=" * 60)
    print("方案对比汇总:")
    print(comp_df.to_string(index=False))
    print(f"\n输出: {OUTPUT_DIR}/scenario_comparison.csv")
    print("步骤四完成！")

if __name__ == '__main__':
    main()
