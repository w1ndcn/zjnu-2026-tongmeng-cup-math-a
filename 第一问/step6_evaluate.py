"""
步骤六：效果评价
输入: step3 的 baseline + step4 的 scenario_comparison
输出: evaluation_report.txt（综合评价报告）
"""

import pandas as pd
import numpy as np
import os

STEP3_DIR = "output_step3"
STEP4_DIR = "output_step4"
STEP5_DIR = "output_step5"
OUTPUT_DIR = "output_step6"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════ 1. 加载数据 ═══════════════════

# 步骤四的情景对比
df = pd.read_csv(os.path.join(STEP4_DIR, "scenario_comparison.csv"))

# 解析数值列
for col in ['TTT合计', 'S合计']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

df['η_TTT_num'] = df['η_TTT'].str.replace('%','').str.replace('+','').astype(float)
df['η_S_num'] = df['η_S'].str.replace('%','').str.replace('+','').astype(float)
df['η_VC_num'] = df['η_VC'].str.replace('%','').str.replace('+','').astype(float)

baseline = df[df['方案'] == '基准（现状）'].iloc[0]
optimal  = df[df['η_S_num'] == df['η_S_num'].max()].iloc[0]

# 步骤三：各时段详细数据
los_dist = {}
for period in ['morning', 'noon', 'evening']:
    fp = os.path.join(STEP3_DIR, f"link_flow_{period}.csv")
    if os.path.exists(fp):
        lf = pd.read_csv(fp)
        los_dist[period] = lf['LOS'].value_counts().to_dict()

# ═══════════════════ 2. LOS 服务水平对比 ═══════════════════

print("=" * 60)
print("步骤六：方案效果评价")
print("=" * 60)

print(f"\n基准 TTT: {baseline['TTT合计']:.0f}  |  最优 TTT: {optimal['TTT合计']:.0f}  "
      f"|  提升 {optimal['η_TTT']}")
print(f"基准 S:   {baseline['S合计']:.0f}  |  最优 S:   {optimal['S合计']:.0f}  "
      f"|  提升 {optimal['η_S']}")

print(f"\n最优方案: {optimal['方案']}")

# LOS分布
print("\n各时段服务水平分布（基准）:")
for period, dist in los_dist.items():
    total = sum(dist.values())
    items = []
    for level in ['A','B','C','D','E','F']:
        c = dist.get(level, 0)
        if c > 0:
            items.append(f"{level}:{c}")
    print(f"  {period:8s}  {' '.join(items)}")

# ═══════════════════ 3. 写评价报告 ═══════════════════
report = os.path.join(OUTPUT_DIR, "evaluation_report.txt")
with open(report, "w", encoding="utf-8") as f:
    f.write("=" * 70 + "\n")
    f.write("浙师大校园微交通优化方案 — 效果评价报告\n")
    f.write("=" * 70 + "\n\n")

    f.write("一、核心指标对比\n")
    f.write("-" * 40 + "\n")
    f.write(f"  {'指标':<22} {'基准':>10} {'最优':>10} {'改善':>10}\n")
    f.write(f"  {'总行程时间 TTT':<22} {baseline['TTT合计']:>10.0f} {optimal['TTT合计']:>10.0f} {optimal['η_TTT']:>10}\n")
    f.write(f"  {'人车冲突风险 S':<22} {baseline['S合计']:>10.0f} {optimal['S合计']:>10.0f} {optimal['η_S']:>10}\n")
    f.write(f"  {'平均饱和度 V/C':<22} {baseline['avgV/C']:>10} {optimal['avgV/C']:>10} {optimal['η_VC']:>10}\n")

    f.write(f"\n最优方案: {optimal['方案']}\n")

    f.write("\n二、方案对比\n")
    f.write("-" * 40 + "\n")
    f.write(f"  {'方案':<22} {'TTT':>10} {'η_TTT':>8} {'S':>12} {'η_S':>8}\n")
    for _, row in df.iterrows():
        f.write(f"  {row['方案']:<22} {row['TTT合计']:>10.0f} {row['η_TTT']:>8} {row['S合计']:>12.0f} {row['η_S']:>8}\n")

    f.write("\n三、时段 LOS 分布\n")
    f.write("-" * 40 + "\n")
    for period, dist in los_dist.items():
        f.write(f"  {period}: " + " ".join(f"{k}:{v}" for k, v in sorted(dist.items())) + "\n")

    f.write("\n四、综合评价结论\n")
    f.write("-" * 40 + "\n")
    ttt_imp = optimal['η_TTT_num']
    s_imp = optimal['η_S_num']
    if ttt_imp > 0 and s_imp > 0:
        f.write(f"  综合方案使校园通行效率提升 {ttt_imp:.1f}%，\n")
        f.write(f"  人车冲突风险降低 {s_imp:.1f}%，\n")
        f.write(f"  实现了安全与效率的双重优化目标。\n")

print(f"\n报告已保存: {report}")
