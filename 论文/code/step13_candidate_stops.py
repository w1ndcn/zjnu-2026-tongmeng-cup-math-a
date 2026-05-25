import networkx as nx
import pandas as pd
import numpy as np
import os
STEP1_DIR  = "output_step1"
STEP3_DIR  = "output_step3"
STEP8_DIR  = "output_step8"
STEP12_DIR = "output_step12"
OUTPUT_DIR = "output_step13"
os.makedirs(OUTPUT_DIR, exist_ok=True)
PERIODS = ['morning', 'noon', 'evening']
G = nx.read_gml(os.path.join(STEP1_DIR, "campus_graph.gml"))
zones_df = pd.read_csv(os.path.join(STEP8_DIR, "zones.csv"))
base_df = pd.read_csv(os.path.join(STEP12_DIR, "base_data_summary.csv"))
link_flows = {}
for period in PERIODS:
    fp = os.path.join(STEP3_DIR, f"link_flow_{period}.csv")
    if os.path.exists(fp):
        link_flows[period] = pd.read_csv(fp)
print(f"路网: {G.number_of_nodes()} 节点")
print(f"区域: {len(zones_df)} 个")
CANDIDATE_STOPS = [
    {
        'stop_id': 'S1', 'stop_name': '桂苑站',
        'nearest_node': 'N28', 'zone_id': 'Z5',
        'reason': '桂苑生活区核心，GYST+GYGY+CYGY复合需求',
    },
    {
        'stop_id': 'S2', 'stop_name': '桃园站',
        'nearest_node': 'N4', 'zone_id': 'Z3',
        'reason': '桃园生活区核心，TYGY+TYST+近T_3/T_4',
    },
    {
        'stop_id': 'S3', 'stop_name': '杏园站',
        'nearest_node': 'N12', 'zone_id': 'Z4',
        'reason': '杏园生活区核心，XYGY+XYST+商业街方向',
    },
    {
        'stop_id': 'S4', 'stop_name': '16幢站',
        'nearest_node': 'N15', 'zone_id': 'Z1',
        'reason': '16幢教学区核心，近T_2/T_5',
    },
    {
        'stop_id': 'S5', 'stop_name': '25幢站',
        'nearest_node': 'N48', 'zone_id': 'Z2',
        'reason': '25幢教学区核心，近T_9/T_10',
    },
    {
        'stop_id': 'S6', 'stop_name': '商业街站',
        'nearest_node': 'N13', 'zone_id': 'Z8',
        'reason': 'SYJ商业街，午晚高峰最大目的地',
    },
    {
        'stop_id': 'S7', 'stop_name': '东区教学楼站',
        'nearest_node': 'N20', 'zone_id': 'Z6',
        'reason': '东区新教学楼核心(T_1~T_3)，早高峰主要目的地',
    },
    {
        'stop_id': 'S8', 'stop_name': '西区教学楼站',
        'nearest_node': 'N42', 'zone_id': 'Z7',
        'reason': '西区新教学楼核心(T_6~T_8)，早高峰主要目的地',
    },
]
def get_edge_conditions(link_df, node):
    mask = (link_df['from'] == node) | (link_df['to'] == node)
    nearby = link_df[mask]
    if len(nearby) == 0:
        return {'vc': 0, 'risk': 0, 'width': 8}
    return {
        'vc': float(nearby['saturation'].max()),
        'risk': float(nearby['risk'].max()),
        'width': float(nearby['width_m'].max()) if 'width_m' in nearby.columns else 8.0,
    }
rows = []
for stop in CANDIDATE_STOPS:
    node = stop['nearest_node']
    zone = zones_df[zones_df['zone_id'] == stop['zone_id']]
    zname = zone.iloc[0]['zone_name'] if len(zone) > 0 else ''
    cond_m = get_edge_conditions(link_flows.get('morning', pd.DataFrame()), node)
    cond_n = get_edge_conditions(link_flows.get('noon', pd.DataFrame()), node)
    cond_e = get_edge_conditions(link_flows.get('evening', pd.DataFrame()), node)
    vc_max = max(cond_m['vc'], cond_n['vc'], cond_e['vc'])
    risk_max = max(cond_m['risk'], cond_n['risk'], cond_e['risk'])
    can_stop = (cond_m['width'] >= 5.0) and (vc_max <= 0.90)
    if not can_stop:
        fail_reason = []
        if cond_m['width'] < 5.0:
            fail_reason.append(f"路宽不足({cond_m['width']:.1f}m)")
        if vc_max > 0.90:
            fail_reason.append(f"拥堵(V/C={vc_max:.3f})")
        reason_str = '; '.join(fail_reason)
    else:
        reason_str = '符合条件'
    rows.append({
        'stop_id': stop['stop_id'],
        'stop_name': stop['stop_name'],
        'nearest_node': node,
        'zone_id': stop['zone_id'],
        'zone_name': zname,
        'road_width_m': cond_m['width'],
        'vc_morning': f"{cond_m['vc']:.3f}",
        'vc_noon': f"{cond_n['vc']:.3f}",
        'vc_evening': f"{cond_e['vc']:.3f}",
        'risk_morning': f"{cond_m['risk']:.0f}",
        'risk_noon': f"{cond_n['risk']:.0f}",
        'risk_evening': f"{cond_e['risk']:.0f}",
        'vc_max': f"{vc_max:.3f}",
        'can_stop': can_stop,
        'stop_reason': reason_str if not can_stop else stop['reason'],
    })
    print(f"{stop['stop_id']} {stop['stop_name']:10s} @ {node:6s}  "
          f"路宽={cond_m['width']:.0f}m  V/C={vc_max:.3f}  "
          f"{'✓' if can_stop else '✗ ' + reason_str}")
df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR, "candidate_stops.csv"), index=False, encoding="utf-8-sig")
valid = [r for r in rows if r['can_stop']]
print(f"\n{'='*60}")
print(f"候选站点: {len(rows)} 个, 符合条件: {len(valid)} 个")
print(f"输出: {OUTPUT_DIR}/candidate_stops.csv")
