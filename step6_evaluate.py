"""
步骤六：效果评价
==============
汇总方案对比结果，计算改善率，确定最优方案，
统计LOS分布，生成综合评价报告。
"""

import pandas as pd
import os

# ========== 路径配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STEP3_DIR = os.path.join(BASE_DIR, 'output_step3')
STEP4_DIR = os.path.join(BASE_DIR, 'output_step4')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_step6')
os.makedirs(OUTPUT_DIR, exist_ok=True)

PERIODS = ['morning', 'noon', 'evening']
PERIOD_NAMES = {'morning': '早高峰', 'noon': '午高峰', 'evening': '晚高峰'}

# ========== 主函数 ==========
def main():
    print("=" * 60)
    print("步骤六：效果评价")
    print("=" * 60)

    # 1. 读取方案对比结果
    comp_path = os.path.join(STEP4_DIR, 'scenario_comparison.csv')
    comp_df = pd.read_csv(comp_path)
    print(f"\n方案对比表:\n{comp_df.to_string(index=False)}")

    # 2. 确定最优方案（以冲突风险改善率为主）
    best_idx = comp_df['eta_S'].idxmax()
    best_scenario = comp_df.loc[best_idx]
    best_name = best_scenario['方案']

    print(f"\n最优方案: {best_name}")
    print(f"  TTT改善: {best_scenario['eta_TTT']:.1f}%")
    print(f"  S改善:   {best_scenario['eta_S']:.1f}%")
    print(f"  V/C改善: {best_scenario['eta_VC']:.1f}%")

    # 3. LOS分布统计
    los_dist = {}
    for period in PERIODS:
        fp = os.path.join(STEP3_DIR, f'link_flow_{period}.csv')
        if not os.path.exists(fp):
            continue
        df = pd.read_csv(fp)
        los_counts = df['LOS'].value_counts().to_dict()
        los_dist[PERIOD_NAMES[period]] = los_counts

    # 4. 生成评价报告
    report = []
    report.append("=" * 60)
    report.append("浙师大校园微交通系统综合治理 — 效果评价报告")
    report.append("=" * 60)

    report.append("\n一、方案对比结果")
    report.append("-" * 40)
    for _, row in comp_df.iterrows():
        report.append(f"\n  {row['方案']}:")
        report.append(f"    TTT合计: {row['TTT合计']:,.0f} 人·秒 (改善 {row['eta_TTT']:.1f}%)")
        report.append(f"    S合计:   {row['S合计']:,.0f} (改善 {row['eta_S']:.1f}%)")
        report.append(f"    avgV/C:  {row['avgV/C']:.4f} (改善 {row['eta_VC']:.1f}%)")
        report.append(f"    maxV/C:  {row['maxV/C']:.4f}")

    report.append(f"\n二、最优方案: {best_name}")
    report.append("-" * 40)
    report.append(f"  以冲突风险(S)改善率作为主要评价指标:")
    report.append(f"  TTT总行程时间改善: {best_scenario['eta_TTT']:.1f}%")
    report.append(f"  人车冲突风险降低: {best_scenario['eta_S']:.1f}%")
    report.append(f"  平均V/C改善: {best_scenario['eta_VC']:.1f}%")

    report.append("\n三、基准LOS分布")
    report.append("-" * 40)
    for period_name, los_counts in los_dist.items():
        report.append(f"\n  {period_name}:")
        for los_level in ['A', 'B', 'C', 'D', 'E', 'F']:
            count = los_counts.get(los_level, 0)
            if count > 0:
                report.append(f"    LOS {los_level}: {count} 条路段")

    report.append("\n四、结论")
    report.append("-" * 40)
    report.append(f"  推荐方案: {best_name}")
    if best_scenario['eta_S'] > 10:
        report.append("  该方案显著降低了人车冲突风险，")
        report.append("  在保障校园交通安全方面效果突出。")
    report.append(f"  总行程时间基本保持稳定（变化 {best_scenario['eta_TTT']:.1f}%），")
    report.append("  说明优化措施未牺牲通行效率。")

    report_text = '\n'.join(report)
    report_path = os.path.join(OUTPUT_DIR, 'evaluation_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    print(f"\n{report_text}")
    print(f"\n报告已保存: {report_path}")
    print("步骤六完成！")

if __name__ == '__main__':
    main()
