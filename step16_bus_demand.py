"""
步骤十六+十七：接驳车需求识别 + 潮汐调度模型
===========================================
基于问题二的超载需求，估算接驳车替代量；
按早/午/晚三时段计算所需车辆数、发车间隔、运能。

输入:
  - output_step3/baseline.txt（获取各时段 e-bike 需求）
  - output_step11/final_capacity.csv
  - output_step15/candidate_routes.csv

输出:
  - output_step16/bus_demand_scenarios.csv
  - output_step16/bus_schedule.csv
"""

import pandas as pd
import numpy as np
import os
import math

STEP3_DIR  = "output_step3"
STEP11_DIR = "output_step11"
STEP15_DIR = "output_step15"
OUTPUT_DIR = "output_step16"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════ 参数 ═══════════════════
K = 25              # 单车载客量 (人/车) — 中型接驳巴士
HOURS = {           # 各时段持续时间 (min)
    'morning': 45,   # 7:30-8:15
    'noon':    50,   # 11:40-12:30
    'evening': 40,   # 17:20-18:00
}
DELTA = 0.5         # 单站停靠时间 (min)
H_MAX = 10          # 最大可接受发车间隔 (min) — 高峰可放宽至连续运营
M_MAX = 30          # 单时段最大可投放车辆数

# 调度成本参数
C_V = 8.0           # 单车单位分钟运营成本
C_W = 0.6           # 乘客等待单位分钟成本
C_O = 0.2           # 单位闲置运能浪费成本

PERIOD_LABEL = {'morning': '早高峰', 'noon': '午高峰', 'evening': '晚高峰'}

# ═══════════════════ 1. 接驳需求模型 ═══════════════════
# 问题二结果
capacity_df = pd.read_csv(os.path.join(STEP11_DIR, "final_capacity.csv"))
N_max = sum(int(r['N_opt']) for _, r in capacity_df.iterrows())
print(f"校园最大容量 N_max = {N_max} 辆")

# 各时段 e-bike 需求（从 step2 OD 读取）
STEP2_DIR = "output_step2"
D_bike = {}
for p in ['morning', 'noon', 'evening']:
    df = pd.read_csv(os.path.join(STEP2_DIR, f'od_{p}_b.csv'), index_col=0)
    D_bike[p] = df.values.sum()
print(f"D_bike: {D_bike}")

# 两部分需求: 基础替代(绿色出行) + 超载治理
ETA_BASE = 0.10   # 基础替代率: 主动吸引10%电动车用户转移
ETA_OVER = 0.50   # 超载替代率: 超载部分承担50%

D_over_raw = {p: max(0, D_bike[p] - N_max) for p in D_bike}
D_base = {p: ETA_BASE * D_bike[p] for p in D_bike}
D_over_bus = {p: ETA_OVER * D_over_raw[p] for p in D_bike}

print("\n各时段电动车需求与接驳需求:")
for p in ['morning', 'noon', 'evening']:
    D_total = D_base[p] + D_over_bus[p]
    print(f"  {PERIOD_LABEL[p]:4s}: D_bike={D_bike[p]:.0f}, "
          f"基础替代={D_base[p]:.0f}, 超载转移={D_over_bus[p]:.0f}, "
          f"总接驳需求={D_total:.0f} 人次")

# ═══════════════════ 2. 情景法估算接驳需求 ═══════════════════
scenarios = {
    '保守': 0.05,
    '基准': 0.10,
    '积极': 0.15,
}

demand_rows = []
for name, eta_base_sc in scenarios.items():
    row = {'scenario': name, 'eta': f"{eta_base_sc:.0%}"}
    for p in ['morning', 'noon', 'evening']:
        d_bus = eta_base_sc * D_bike[p] + ETA_OVER * D_over_raw[p]
        row[f'{p}_demand'] = f"{d_bus:.0f}"
    demand_rows.append(row)

df_demand = pd.DataFrame(demand_rows)
df_demand.to_csv(os.path.join(OUTPUT_DIR, "bus_demand_scenarios.csv"),
                 index=False, encoding="utf-8-sig")

print("\n接驳车需求（三情景 × 三时段）:")
for _, r in df_demand.iterrows():
    print(f"  {r['scenario']:4s} (η={r['eta']}): "
          f"早={r['morning_demand']}  午={r['noon_demand']}  晚={r['evening_demand']} 人次")

# ═══════════════════ 3. 加载线路数据 ═══════════════════
route_df = pd.read_csv(os.path.join(STEP15_DIR, "candidate_routes.csv"))
# 取最优线路 R1
best_route = route_df[route_df['route_id'] == 'R1'].iloc[0]
tau_r = float(best_route['travel_time_min'])   # 单程时间 (min)
print(f"\n最优线路: {best_route['route_name']}")
print(f"  单程时间 τ_r = {tau_r:.1f} min")

# ═══════════════════ 4. 调度优化计算 ═══════════════════
def evaluate_dispatch(D_s, H_t, tau_r, n):
    """计算给定车辆数 n 下的运能、发车间隔和总成本"""
    headway = tau_r / n
    capacity = n * K * (H_t / tau_r)
    load_factor = D_s / max(capacity, 1)
    avg_wait = headway / 2

    operation_cost = C_V * n * H_t
    waiting_cost = C_W * D_s * avg_wait
    waste_cost = C_O * max(0, capacity - D_s)
    total_cost = operation_cost + waiting_cost + waste_cost

    feasible = (capacity >= D_s) and (headway <= H_MAX)
    return {
        'n': n,
        'headway': headway,
        'capacity': capacity,
        'load_factor': load_factor,
        'avg_wait': avg_wait,
        'operation_cost': operation_cost,
        'waiting_cost': waiting_cost,
        'waste_cost': waste_cost,
        'total_cost': total_cost,
        'feasible': feasible,
    }

def optimize_dispatch(D_s, H_t, tau_r):
    """枚举车辆数，在满足需求和发车间隔约束下选择总成本最小方案"""
    candidates = [evaluate_dispatch(D_s, H_t, tau_r, n) for n in range(1, M_MAX + 1)]
    feasible = [c for c in candidates if c['feasible']]

    if feasible:
        best = min(feasible, key=lambda c: c['total_cost'])
        best['constraint_note'] = '满足运能和发车间隔约束'
    else:
        # 若 H_MAX 约束无法满足，则退化为满足运能且总成本最低；仍给出警告
        capacity_feasible = [c for c in candidates if c['capacity'] >= D_s]
        if capacity_feasible:
            best = min(capacity_feasible, key=lambda c: c['total_cost'])
            best['constraint_note'] = '满足运能，但发车间隔超过约束'
        else:
            best = max(candidates, key=lambda c: c['capacity'])
            best['constraint_note'] = '最大车辆数下仍运能不足'
    return best, candidates

# 潮汐方向
TIDAL_DIR = {
    'morning': '宿舍区 → 教学区',
    'noon':    '教学区 → 食堂/商业街',
    'evening': '教学区 → 宿舍/食堂',
}

# 对基准情景做完整调度计算
BASE_ETA = 0.10   # 基准情景基础替代率

schedule_rows = []
cost_rows = []
for period in ['morning', 'noon', 'evening']:
    D_s = BASE_ETA * D_bike[period] + ETA_OVER * D_over_raw[period]
    H_t = HOURS[period]

    best_dispatch, candidates = optimize_dispatch(D_s, H_t, tau_r)
    n_t = best_dispatch['n']
    h_t = best_dispatch['headway']
    Q_cap = best_dispatch['capacity']
    load_factor = best_dispatch['load_factor']

    for c in candidates:
        cost_rows.append({
            'period': period,
            'period_name': PERIOD_LABEL[period],
            'n_vehicles': c['n'],
            'headway_min': f"{c['headway']:.2f}",
            'Q_cap': f"{c['capacity']:.1f}",
            'load_factor': f"{c['load_factor']:.3f}",
            'operation_cost': f"{c['operation_cost']:.2f}",
            'waiting_cost': f"{c['waiting_cost']:.2f}",
            'waste_cost': f"{c['waste_cost']:.2f}",
            'total_cost': f"{c['total_cost']:.2f}",
            'feasible': c['feasible'],
        })

    schedule_rows.append({
        'period': period,
        'period_name': PERIOD_LABEL[period],
        'direction': TIDAL_DIR[period],
        'D_s': f"{D_s:.0f}",
        'H_t_min': H_t,
        'tau_r_min': f"{tau_r:.1f}",
        'n_vehicles': n_t,
        'headway_min': f"{h_t:.1f}",
        'avg_wait_min': f"{best_dispatch['avg_wait']:.1f}",
        'Q_cap': f"{Q_cap:.0f}",
        'load_factor': f"{load_factor:.2f}",
        'operation_cost': f"{best_dispatch['operation_cost']:.2f}",
        'waiting_cost': f"{best_dispatch['waiting_cost']:.2f}",
        'waste_cost': f"{best_dispatch['waste_cost']:.2f}",
        'total_cost': f"{best_dispatch['total_cost']:.2f}",
        'meets_constraint': '✓' if best_dispatch['feasible'] else '✗',
        'constraint_note': best_dispatch['constraint_note'],
    })

    print(f"\n  {PERIOD_LABEL[period]}:")
    print(f"    接驳需求 D_s = {D_s:.0f} 人次")
    print(f"    最优车辆数 n = {n_t} 辆")
    print(f"    发车间隔 h = {tau_r:.1f}/{n_t} = {h_t:.1f} min")
    print(f"    平均等待 W = {best_dispatch['avg_wait']:.1f} min")
    print(f"    运能 Q_cap = {n_t}×{K}×({H_t}/{tau_r:.1f}) = {Q_cap:.0f} 人次")
    print(f"    满载率 = {D_s:.0f}/{Q_cap:.0f} = {load_factor:.2f}")
    print(f"    成本 = 运营 {best_dispatch['operation_cost']:.1f} + 等待 {best_dispatch['waiting_cost']:.1f} + 浪费 {best_dispatch['waste_cost']:.1f} = {best_dispatch['total_cost']:.1f}")
    print(f"    {best_dispatch['constraint_note']}")

df_sched = pd.DataFrame(schedule_rows)
df_sched.to_csv(os.path.join(OUTPUT_DIR, "bus_schedule.csv"), index=False, encoding="utf-8-sig")

df_cost = pd.DataFrame(cost_rows)
df_cost.to_csv(os.path.join(OUTPUT_DIR, "dispatch_cost_candidates.csv"), index=False, encoding="utf-8-sig")

# ═══════════════════ 5. 汇总 ═══════════════════
print(f"\n{'='*60}")
print(f"接驳车系统设计汇总（基准情景 η={BASE_ETA:.0%}）:")

total_vehicles = sum(int(r['n_vehicles']) for r in schedule_rows)
max_vehicles = max(int(r['n_vehicles']) for r in schedule_rows)
print(f"  线路: {best_route['route_name']} (单程 {tau_r:.1f} min)")
print(f"  三时段合计需要 {total_vehicles} 车次")
print(f"  最大同时投放: {max_vehicles} 辆（{PERIOD_LABEL[max(schedule_rows, key=lambda r: int(r['n_vehicles']))['period']]}）")

print(f"\n输出: {OUTPUT_DIR}/")
print(f"  bus_demand_scenarios.csv")
print(f"  bus_schedule.csv")
print(f"  dispatch_cost_candidates.csv")
