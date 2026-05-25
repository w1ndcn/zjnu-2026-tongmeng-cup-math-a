"""
步骤五：MinMax V/C 系统优化分配
================================
替代旧的 K 短路径 Logit 分流。

核心思想：
- 将 OD 需求按小批次增量分配；
- 每一批根据当前路段 V/C 动态提高拥堵路段权重；
- 后续流量会主动避开高饱和路段，近似实现“最大 V/C 最小化”。
"""

import os
import math
import heapq
from collections import defaultdict

import networkx as nx
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STEP1_DIR = os.path.join(BASE_DIR, 'output_step1')
STEP2_DIR = os.path.join(BASE_DIR, 'output_step2')
STEP3_DIR = os.path.join(BASE_DIR, 'output_step3')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_step5_minmax')
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODES = ['p', 'b', 'c']
PERIODS = ['morning', 'noon', 'evening']
PERIOD_NAMES = {'morning': '早高峰', 'noon': '午高峰', 'evening': '晚高峰'}
XI = {'p': 0.10, 'b': 0.30, 'c': 1.00}
V_FREE = {'p': 1.39, 'b': 4.17, 'c': 5.56}

# 参数越大，越主动避开高 V/C 路段
BATCHES = 60
LAMBDA_CONGESTION = 65.0
POWER_CONGESTION = 4.0
OVER_CAP_PENALTY = 140.0
NARROW_PENALTY = 0.40


def build_edge_data(G):
    adj = defaultdict(list)
    edge_data = {}
    for eid, (u, v, data) in enumerate(G.edges(data=True)):
        length = float(data.get('length', 100))
        width = float(data.get('width', 6))
        capacity = float(data.get('capacity', 600))
        edge_data[eid] = {
            'u': u,
            'v': v,
            'length': length,
            'width': width,
            'capacity': capacity,
            'is_virtual': width >= 99,
        }
        adj[u].append((v, eid))
    return adj, edge_data


def edge_cost(eid, mode, edge_data, flow_eq):
    e = edge_data[eid]
    cap = max(e['capacity'], 1.0)
    vc = flow_eq.get(eid, 0.0) / cap
    base_time = e['length'] / V_FREE[mode]

    congestion = LAMBDA_CONGESTION * (vc ** POWER_CONGESTION)
    over_cap = OVER_CAP_PENALTY * (max(0.0, vc - 0.75) ** 2)
    narrow = 0.0
    if not e['is_virtual']:
        narrow = NARROW_PENALTY * max(0.0, (8.0 - e['width']) / 8.0)

    return base_time * (1.0 + congestion + over_cap + narrow)


def dijkstra_path(src, dst, adj, edge_data, flow_eq, mode):
    dist = {src: 0.0}
    prev = {}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        if u == dst:
            break
        for v, eid in adj.get(u, []):
            nd = d + edge_cost(eid, mode, edge_data, flow_eq)
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = (u, eid)
                heapq.heappush(heap, (nd, v))
    if dst not in prev:
        return None, math.inf

    nodes = [dst]
    eids = []
    cur = dst
    while cur != src:
        p, eid = prev[cur]
        eids.append(eid)
        cur = p
        nodes.append(cur)
    nodes.reverse()
    eids.reverse()
    return (nodes, eids), dist[dst]


def load_od(period):
    od = []
    for mode in MODES:
        fp = os.path.join(STEP2_DIR, f'od_{period}_{mode}.csv')
        if not os.path.exists(fp):
            continue
        df = pd.read_csv(fp, index_col=0)
        for src in df.index:
            for dst in df.columns:
                demand = float(df.loc[src, dst])
                if demand > 0.01:
                    od.append({'source': src, 'target': dst, 'mode': mode, 'demand': demand})
    od.sort(key=lambda x: x['demand'], reverse=True)
    return od


def get_los(vc):
    if vc <= 0.35:
        return 'A'
    if vc <= 0.55:
        return 'B'
    if vc <= 0.75:
        return 'C'
    if vc <= 0.90:
        return 'D'
    if vc <= 1.00:
        return 'E'
    return 'F'


def load_baseline(period):
    fp = os.path.join(STEP3_DIR, f'link_flow_{period}.csv')
    if not os.path.exists(fp):
        return {}
    df = pd.read_csv(fp)
    return {(r['from'], r['to']): float(r['saturation']) for _, r in df.iterrows()}


def optimize_period(period, G, adj, edge_data):
    od = load_od(period)
    flow_eq = defaultdict(float)
    flow_mode = defaultdict(float)
    path_counter = defaultdict(float)

    print(f"\n--- {PERIOD_NAMES[period]} ---")
    print(f"  OD记录: {len(od)} 条, 总需求: {sum(x['demand'] for x in od):.0f} 人")

    for batch in range(BATCHES):
        for item in od:
            src, dst, mode = item['source'], item['target'], item['mode']
            if src not in G.nodes or dst not in G.nodes:
                continue
            batch_flow = item['demand'] / BATCHES
            result, _ = dijkstra_path(src, dst, adj, edge_data, flow_eq, mode)
            if result is None:
                continue
            nodes, eids = result
            eq_flow = batch_flow * XI[mode]
            for eid in eids:
                flow_eq[eid] += eq_flow
                flow_mode[(eid, mode)] += batch_flow
            path_counter[(period, src, dst, mode, ' -> '.join(nodes))] += batch_flow

    link_records = []
    opt_vc = {}
    for eid, e in edge_data.items():
        flow = flow_eq.get(eid, 0.0)
        cap = e['capacity']
        vc = flow / cap if cap > 0 else 0.0
        opt_vc[(e['u'], e['v'])] = vc
        link_records.append({
            'u': e['u'],
            'v': e['v'],
            'length': e['length'],
            'width': e['width'],
            'capacity': cap,
            'flow_pcu': round(flow, 2),
            'flow_p': round(flow_mode.get((eid, 'p'), 0.0), 2),
            'flow_b': round(flow_mode.get((eid, 'b'), 0.0), 2),
            'flow_c': round(flow_mode.get((eid, 'c'), 0.0), 2),
            'V/C': round(vc, 4),
            'LOS': get_los(vc),
        })

    link_df = pd.DataFrame(link_records)
    link_df.to_csv(os.path.join(OUTPUT_DIR, f'link_flow_optimized_{period}.csv'), index=False, encoding='utf-8-sig')

    base_vc = load_baseline(period)
    compare_records = []
    for eid, e in edge_data.items():
        edge = (e['u'], e['v'])
        b = base_vc.get(edge, 0.0)
        o = opt_vc.get(edge, 0.0)
        compare_records.append({
            'u': e['u'],
            'v': e['v'],
            'width': e['width'],
            'capacity': e['capacity'],
            'baseline_vc': round(b, 4),
            'optimized_vc': round(o, 4),
            'delta_vc': round(o - b, 4),
            'reduction_pct': round((b - o) / b * 100, 2) if b > 1e-9 else 0.0,
        })
    compare_df = pd.DataFrame(compare_records)
    compare_df.to_csv(os.path.join(OUTPUT_DIR, f'vc_compare_{period}.csv'), index=False, encoding='utf-8-sig')

    path_rows = []
    for (p, src, dst, mode, route), flow in path_counter.items():
        path_rows.append({
            'period': PERIOD_NAMES[p],
            'source': src,
            'target': dst,
            'mode': mode,
            'route': route,
            'flow_persons': round(flow, 2),
        })

    real_links = link_df[link_df['width'] < 99]
    high = int((real_links['V/C'] > 0.75).sum())
    max_vc = float(real_links['V/C'].max()) if len(real_links) else 0.0
    mean_pos = float(real_links[real_links['V/C'] > 0]['V/C'].mean()) if (real_links['V/C'] > 0).any() else 0.0
    base_real = compare_df[compare_df['width'] < 99]
    base_max = float(base_real['baseline_vc'].max()) if len(base_real) else 0.0
    base_high = int((base_real['baseline_vc'] > 0.75).sum())

    print(f"  基准: max V/C={base_max:.3f}, V/C>0.75={base_high} 条")
    print(f"  优化: max V/C={max_vc:.3f}, V/C>0.75={high} 条, 正流均值={mean_pos:.3f}")

    return {
        'period': period,
        'base_max': base_max,
        'opt_max': max_vc,
        'base_high': base_high,
        'opt_high': high,
        'mean_pos': mean_pos,
        'path_rows': path_rows,
    }


def main():
    print("=" * 60)
    print("步骤五：MinMax V/C 系统优化分配")
    print("=" * 60)

    G = nx.read_gml(os.path.join(STEP1_DIR, 'campus_graph.gml'))
    adj, edge_data = build_edge_data(G)
    print(f"图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 有向边")

    summaries = []
    all_path_rows = []
    for period in PERIODS:
        res = optimize_period(period, G, adj, edge_data)
        summaries.append({k: v for k, v in res.items() if k != 'path_rows'})
        all_path_rows.extend(res['path_rows'])

    pd.DataFrame(all_path_rows).to_csv(os.path.join(OUTPUT_DIR, 'path_flow_optimized.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(summaries).to_csv(os.path.join(OUTPUT_DIR, 'summary.csv'), index=False, encoding='utf-8-sig')

    print(f"\n步骤五完成！输出目录: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
