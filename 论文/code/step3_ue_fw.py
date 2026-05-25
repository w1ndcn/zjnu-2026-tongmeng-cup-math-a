import networkx as nx
import pandas as pd
import numpy as np
import os, math, heapq
from collections import defaultdict
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STEP1_DIR = os.path.join(BASE_DIR, 'output_step1')
STEP2_DIR = os.path.join(BASE_DIR, 'output_step2')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_step3')
os.makedirs(OUTPUT_DIR, exist_ok=True)
ALPHA, BETA = 0.15, 4.0
XI = {'p': 0.10, 'b': 0.30, 'c': 1.00}
V_FREE = {'p': 1.39, 'b': 4.17, 'c': 5.56}
OMEGA = {'pb': 0.5, 'pc': 1.5, 'bc': 0.8}
MODES = ['p', 'b', 'c']
PERIODS = ['morning', 'noon', 'evening']
FW_MAX = 20
LOS_LEVELS = [(0.35, 'A'), (0.55, 'B'), (0.75, 'C'), (0.90, 'D'), (1.00, 'E')]
def bpr_cost(t0, cap, flow):
    if cap <= 0:
        return t0 * 10
    return t0 * (1 + ALPHA * (flow / cap) ** BETA)
def dijkstra(source, adj, cost_func):
    dist = {source: 0.0}
    prev = {}
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
                heapq.heappush(heap, (nd, v))
    return dist, prev
def get_path(prev, src, dst):
    if dst not in prev:
        return None
    path = [dst]
    cur = dst
    while cur != src:
        cur = prev[cur]
        path.append(cur)
    return path[::-1]
def assign_aon(od, adj, eattr, eid_map, x_eq):
    aon_mode = defaultdict(float)
    for (src, dst, mode), demand in od.items():
        if demand <= 0 or src not in adj or dst not in adj:
            continue
        def cf(eid, _mode=mode):
            a = eattr[eid]
            return bpr_cost(a['t0'][_mode], a['capacity'], x_eq.get(eid, 0))
        dist, prev = dijkstra(src, adj, cf)
        path = get_path(prev, src, dst)
        if path is None:
            continue
        for i in range(len(path) - 1):
            eid = eid_map.get((path[i], path[i + 1]))
            if eid is not None:
                aon_mode[(eid, mode)] += demand
    aon_eq = defaultdict(float)
    for (eid, mode), flow in aon_mode.items():
        aon_eq[eid] += XI[mode] * flow
    return dict(aon_eq), dict(aon_mode)
def frank_wolfe(od, adj, eattr, eid_map):
    x_eq_zero = {eid: 0.0 for eid in eattr}
    aux_eq0, aux_mode0 = assign_aon(od, adj, eattr, eid_map, x_eq_zero)
    x_mode = defaultdict(float, aux_mode0)
    x_eq = defaultdict(float, aux_eq0)
    prev_obj = math.inf
    for it in range(FW_MAX):
        obj = 0.0
        for eid in eattr:
            a = eattr[eid]
            obj += bpr_cost(a['t0']['p'], a['capacity'], x_eq.get(eid, 0))
        y_eq, y_mode = assign_aon(od, adj, eattr, eid_map, x_eq)
        lo, hi = 0.0, 1.0
        for _ in range(20):
            lam = (lo + hi) / 2
            grad = 0.0
            for eid in eattr:
                xe, ye = x_eq.get(eid, 0), y_eq.get(eid, 0)
                if abs(ye - xe) < 1e-10:
                    continue
                xnew = max(xe + lam * (ye - xe), 0)
                a = eattr[eid]
                grad += bpr_cost(a['t0']['p'], a['capacity'], xnew) * (ye - xe)
            if grad > 0:
                hi = lam
            else:
                lo = lam
        lam_opt = (lo + hi) / 2
        new_x_mode = defaultdict(float)
        for k in set(x_mode) | set(y_mode):
            v = x_mode.get(k, 0) + lam_opt * (y_mode.get(k, 0) - x_mode.get(k, 0))
            if v > 0:
                new_x_mode[k] = v
        new_x_eq = defaultdict(float)
        for eid in eattr:
            v = x_eq.get(eid, 0) + lam_opt * (y_eq.get(eid, 0) - x_eq.get(eid, 0))
            if v > 0:
                new_x_eq[eid] = v
        x_mode, x_eq = new_x_mode, new_x_eq
        rel = abs(obj - prev_obj) / (abs(prev_obj) + 1e-10)
        if rel < 1e-4 and it > 5:
            break
        prev_obj = obj
    return dict(x_mode), dict(x_eq)
def build_adj_eattr(G):
    adj = defaultdict(list)
    eid_map = {}
    eattr = {}
    for eid, (u, v, data) in enumerate(G.edges(data=True)):
        L = float(data['length'])
        cap = float(data['capacity'])
        eattr[eid] = {
            'u': u, 'v': v, 'length': L, 'capacity': cap,
            'width': float(data.get('width', 6)),
            't0': {m: L / V_FREE[m] for m in MODES}
        }
        adj[u].append((v, eid))
        eid_map[(u, v)] = eid
    return adj, eid_map, eattr
def load_od(period):
    od = {}
    for mode in MODES:
        fp = os.path.join(STEP2_DIR, f'od_{period}_{mode}.csv')
        if not os.path.exists(fp):
            continue
        df = pd.read_csv(fp, index_col=0)
        for src in df.index:
            for dst in df.columns:
                v = float(df.loc[src, dst])
                if v > 0.01:
                    od[(src, dst, mode)] = v
    return od
def get_los(vc):
    if vc <= 0.35: return 'A'
    if vc <= 0.55: return 'B'
    if vc <= 0.75: return 'C'
    if vc <= 0.90: return 'D'
    if vc <= 1.00: return 'E'
    return 'F'
def compute_metrics(x_mode, x_eq, eattr, eid_map):
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
        S += risk
    return ttt, S
def main():
    print("=" * 60)
    print("步骤三：多类用户均衡交通分配")
    print("=" * 60)
    G = nx.read_gml(os.path.join(STEP1_DIR, 'campus_graph.gml'))
    adj, eid_map, eattr = build_adj_eattr(G)
    print(f"图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 有向边, {len(eattr)} 路段")
    baseline_results = {}
    for period in PERIODS:
        print(f"\n--- {period} ---")
        od = load_od(period)
        print(f"  OD需求: {len(od)} 条")
        x_mode, x_eq = frank_wolfe(od, adj, eattr, eid_map)
        ttt, S = compute_metrics(x_mode, x_eq, eattr, eid_map)
        flow_by_mode_link = defaultdict(lambda: {'p': 0, 'b': 0, 'c': 0})
        for (eid, mode), flow in x_mode.items():
            flow_by_mode_link[eid][mode] = flow
        link_records = []
        high_vc_count = 0
        max_vc = 0
        for eid, a in eattr.items():
            eq_flow = x_eq.get(eid, 0)
            vc = eq_flow / a['capacity'] if a['capacity'] > 0 else 0
            if vc > max_vc:
                max_vc = vc
            if vc > 0.75:
                high_vc_count += 1
            fm = flow_by_mode_link.get(eid, {'p':0,'b':0,'c':0})
            width_r = a['width'] if a['width'] < 99 else 6.0
            risk = (fm['p']*fm['b']*OMEGA['pb'] + fm['p']*fm['c']*OMEGA['pc'] + fm['b']*fm['c']*OMEGA['bc']) / width_r
            link_records.append({
                'edge_id': eid,
                'from': a['u'], 'to': a['v'],
                'length_m': f'{a["length"]:.0f}', 'width_m': f'{a["width"]:.1f}',
                'capacity': f'{a["capacity"]:.1f}',
                'flow_p': f'{fm["p"]:.1f}', 'flow_b': f'{fm["b"]:.1f}', 'flow_c': f'{fm["c"]:.1f}',
                'flow_eq': f'{eq_flow:.1f}',
                'saturation': f'{vc:.4f}', 'LOS': get_los(vc),
                'risk': f'{risk:.1f}',
            })
        link_df = pd.DataFrame(link_records)
        link_df.to_csv(os.path.join(OUTPUT_DIR, f'link_flow_{period}.csv'), index=False)
        print(f"  TTT: {ttt:,.0f} 人·秒")
        print(f"  S:   {S:,.0f}")
        print(f"  V/C>0.75: {high_vc_count} 条")
        print(f"  max V/C:  {max_vc:.3f}")
        baseline_results[period] = {'TTT': ttt, 'S': S, 'high_vc': high_vc_count, 'max_vc': max_vc}
    with open(os.path.join(OUTPUT_DIR, 'baseline.txt'), 'w', encoding='utf-8') as f:
        f.write("period,TTT,S\n")
        for period in ['morning', 'noon', 'evening']:
            if period in baseline_results:
                f.write(f"{period},{baseline_results[period]['TTT']:.1f},{baseline_results[period]['S']:.1f}\n")
    with open(os.path.join(OUTPUT_DIR, 'baseline_readable.txt'), 'w', encoding='utf-8') as f:
        f.write("基准现状评价结果\n")
        f.write("=" * 50 + "\n\n")
        period_names = {'morning': '早高峰', 'noon': '午高峰', 'evening': '晚高峰'}
        for period, res in baseline_results.items():
            f.write(f"{period_names[period]} ({period}):\n")
            f.write(f"  TTT (总行程时间): {res['TTT']:,.0f} 人·秒\n")
            f.write(f"  S   (冲突风险):   {res['S']:,.0f}\n")
            f.write(f"  V/C>0.75路段:    {res['high_vc']} 条\n")
            f.write(f"  max V/C:         {res['max_vc']:.3f}\n\n")
        total_ttt = sum(r['TTT'] for r in baseline_results.values())
        total_s = sum(r['S'] for r in baseline_results.values())
        f.write(f"三时段合计:\n")
        f.write(f"  TTT合计: {total_ttt:,.0f} 人·秒\n")
        f.write(f"  S合计:   {total_s:,.0f}\n")
    print(f"\n步骤三完成！输出目录: {OUTPUT_DIR}")
if __name__ == '__main__':
    main()
