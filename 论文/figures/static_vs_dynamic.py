"""
静态 vs 动态容量对比图（双柱状图）
=================================
横轴：8个功能区  纵轴：车辆数
每个区域两根柱子：静态停车容量（左）、动态道路容量（右）
瓶颈柱用橙色高亮，上方标注控制类型。
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os

# ── 字体 ──
fm._load_fontmanager(try_read_cache=False)
_cjk = [f.name for f in fm.fontManager.ttflist
        if f.name in ('STHeiti', 'Heiti TC', 'PingFang HK', 'Arial Unicode MS')]
if _cjk:
    plt.rcParams['font.sans-serif'] = [_cjk[0]] + plt.rcParams['font.sans-serif']
    plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(BASE_DIR)

# ── 数据 ──
static = pd.read_csv(os.path.join(PARENT, 'output_step9', 'static_capacity.csv'))
dynamic = pd.read_csv(os.path.join(PARENT, 'output_step10', 'dynamic_capacity.csv'))
final = pd.read_csv(os.path.join(PARENT, 'output_step11', 'final_capacity.csv'))

zones = ['Z1','Z2','Z3','Z4','Z5','Z6','Z7','Z8']
labels = ['16幢\n教学区','25幢\n教学区','桃园\n生活区','杏园\n生活区',
          '桂苑\n生活区','东区新\n教学楼','西区新\n教学楼','商业街']

s_map = dict(zip(static['zone_id'], static['N_static']))
d_map = dict(zip(dynamic['zone_id'], dynamic['N_dynamic']))
f_map = dict(zip(final['zone_id'], zip(final['N_opt'], final['limiting'])))

N_static = [s_map[z] for z in zones]
N_dynamic = [d_map[z] for z in zones]
N_opt    = [f_map[z][0] for z in zones]
limiting = [f_map[z][1] for z in zones]

# ── 绘图 ──
fig, ax = plt.subplots(figsize=(14, 7))
fig.patch.set_facecolor('white')
ax.set_facecolor('#FAFAFA')

x = np.arange(len(zones))
bar_width = 0.32

# 静态柱
bars_s = ax.bar(x - bar_width/2, N_static, bar_width,
                color='#3498DB', edgecolor='#2980B9', linewidth=1.2,
                label='静态停车容量 $N_i^{static}$', zorder=3)

# 动态柱
bars_d = ax.bar(x + bar_width/2, N_dynamic, bar_width,
                color='#2ECC71', edgecolor='#27AE60', linewidth=1.2,
                label='动态道路容量 $N_i^{dynamic}$', zorder=3)

# 在瓶颈柱顶上标红色尖角箭头
for i, z in enumerate(zones):
    if '静态' in limiting[i]:
        idx, bar, val = i, bars_s, N_static[i]
        color = '#E74C3C'
    elif '动态' in limiting[i]:
        idx, bar, val = i, bars_d, N_dynamic[i]
        color = '#E74C3C'
    else:
        continue
    # 瓶颈柱加粗边框
    bar[i].set_edgecolor(color)
    bar[i].set_linewidth(3)
    bar[i].set_zorder(5)
    # 上方标注
    ax.annotate('瓶颈',
                xy=(x[i] + (-bar_width/2 if '静态' in limiting[i] else bar_width/2), val),
                xytext=(x[i], val + max(N_static[i], N_dynamic[i]) * 0.25),
                fontsize=9, fontweight='bold', color=color, ha='center',
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5))

# N_opt 标注（用横线标出最终取值）
for i, z in enumerate(zones):
    opt = N_opt[i]
    ax.plot([x[i] - 0.42, x[i] + 0.42], [opt, opt],
            color='#E67E22', lw=2.5, linestyle='--', zorder=4)
    ax.text(x[i], opt - max(N_static[i], N_dynamic[i]) * 0.06,
            f'$N^*$={opt}',
            fontsize=7.5, ha='center', va='top',
            color='#E67E22', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.85))

# 坐标轴
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylabel('车辆数', fontsize=12, fontweight='bold')
ax.set_ylim(0, max(max(N_static), max(N_dynamic)) * 1.25)

# 网格
ax.yaxis.grid(True, linestyle='--', alpha=0.35)
ax.set_axisbelow(True)

# 图例
legend = ax.legend(loc='upper right', fontsize=10, framealpha=0.9)
# 手动在图例末尾加一行 orange 虚线说明
from matplotlib.lines import Line2D
custom_line = Line2D([0],[0], color='#E67E22', lw=2.5, linestyle='--',
                     label=r'最终承载力 $N^*=\min(N^{static},N^{dynamic})$')
handles, labels = ax.get_legend_handles_labels()
handles.append(custom_line)
labels.append(r'最终承载力 $N^*=\min(N^{static},N^{dynamic})$')
ax.legend(handles=handles, loc='upper right', fontsize=9, framealpha=0.9)

ax.set_title('校园各功能区静态停车容量 vs 动态道路容量对比',
             fontsize=14, fontweight='bold', pad=14)

# 顶部说明文字
fig.text(0.5, 0.97,
         '红色箭头标注的区域为容量瓶颈所在侧  |  橙色虚线为最终安全承载力 $N^*$',
         ha='center', fontsize=9, color='#666')

plt.tight_layout(rect=[0, 0, 1, 0.94])

out = os.path.join(BASE_DIR, 'static_vs_dynamic.png')
plt.savefig(out, dpi=200, bbox_inches='tight', facecolor='white')
plt.close()

print(f"已生成: {out}")
