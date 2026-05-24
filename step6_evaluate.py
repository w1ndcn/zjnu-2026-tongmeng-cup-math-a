"""
步骤六：效果评价（v2 — 新路网）
===============================
"""

import pandas as pd, numpy as np, os

STEP3_DIR = "output_step3"; STEP4_DIR = "output_step4"
OUTPUT_DIR = "output_step6"
os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_csv(os.path.join(STEP4_DIR, "scenario_comparison.csv"))
for col in ['TTT合计', 'S合计']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['η_TTT_num'] = df['η_TTT'].str.replace('%','').str.replace('+','').astype(float)
df['η_S_num'] = df['η_S'].str.replace('%','').str.replace('+','').astype(float)

baseline = df[df['方案']=='基准（现状）'].iloc[0]
optimal  = df[df['η_S_num']==df['η_S_num'].max()].iloc[0]

los_dist = {}
for period in ['morning','noon','evening']:
    fp = os.path.join(STEP3_DIR, f"link_flow_{period}.csv")
    if os.path.exists(fp):
        lf = pd.read_csv(fp)
        los_dist[period] = lf['LOS'].value_counts().to_dict()

print("步骤六：方案效果评价（v2 新路网）")
print(f"\n基准 TTT: {baseline['TTT合计']:.0f}  |  最优 TTT: {optimal['TTT合计']:.0f}  "
      f"|  提升 {optimal['η_TTT']}")
print(f"基准 S:   {baseline['S合计']:.0f}  |  最优 S:   {optimal['S合计']:.0f}  "
      f"|  提升 {optimal['η_S']}")
print(f"\n最优方案: {optimal['方案']}")

report = os.path.join(OUTPUT_DIR, "evaluation_report.txt")
with open(report, "w", encoding="utf-8") as f:
    f.write("="*70+"\n")
    f.write("浙师大校园微交通优化方案 — 效果评价报告 (v2 新路网)\n")
    f.write("="*70+"\n\n")
    f.write("一、核心指标对比\n")
    f.write(f"  指标          基准        最优        改善\n")
    f.write(f"  TTT    {baseline['TTT合计']:>10.0f}  {optimal['TTT合计']:>10.0f}  {optimal['η_TTT']:>10}\n")
    f.write(f"  S      {baseline['S合计']:>10.0f}  {optimal['S合计']:>10.0f}  {optimal['η_S']:>10}\n")
    f.write(f"\n最优方案: {optimal['方案']}\n\n")
    f.write("二、方案对比\n")
    for _,r in df.iterrows():
        f.write(f"  {r['方案']:<22} TTT={r['TTT合计']:>8} {r['η_TTT']:>8} S={r['S合计']:>10} {r['η_S']:>8}\n")
    f.write(f"\n三、结论\n")
    f.write(f"  综合方案使校园人车冲突风险降低 {optimal['η_S_num']:.1f}%，\n")
    f.write(f"  实现了安全优化目标。\n")

print(f"\n报告: {report}")
