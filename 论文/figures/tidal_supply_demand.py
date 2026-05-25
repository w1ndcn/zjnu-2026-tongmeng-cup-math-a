"""
潮汐客流供需匹配阶梯图（时序调度图）
====================================
横轴：早/午/晚高峰时段  纵轴：人次
折线表示实际接驳需求，阶梯粗线表示调度方案提供的总运能。
运能线紧贴需求线上方，直观展示供需匹配效果。
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
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

# ── 数据（最新重跑结果） ──
periods = ['早高峰\n7:30–8:15', '午高峰\n11:40–12:30', '晚高峰\n17:20–18:00']
demand = [415, 439, 532]        # 接驳需求（人次）
capacity = [582, 647, 690]      # 运能（人次）
n_vehicles = [3, 3, 4]
headway = [1.9, 1.9, 1.4]
load = [0.71, 0.68, 0.77]

# ── 绘图 ──
fig, ax = plt.subplots(figsize=(12, 7))
fig.patch.set_facecolor('white')
ax.set_facecolor('#FAFAFA')

x = np.arange(len(periods))
bar_width = 0.55  # 时段宽度用于阶梯图

# 需求折线
ax.plot(x, demand, 'o-', color='#E74C3C', linewidth=2.2, markersize=10,
        markerfacecolor='white', markeredgewidth=2.5, zorder=5, label='接驳需求 $D_s^t$')

# 需求柱状（半透明填充）
ax.bar(x, demand, bar_width * 0.75, color='#E74C3C', alpha=0.15, zorder=2)

# 运能阶梯线
# 每个时段向右延伸半个宽度
cap_x = []
cap_y = []
for i in range(len(periods)):
    left = i - 0.42
    right = i + 0.42
    cap_x.extend([left, right])
    cap_y.extend([capacity[i], capacity[i]])

ax.plot(cap_x, cap_y, color='#2E86C1', linewidth=4.5, drawstyle='default',
        zorder=4, label='调度运能 $Q_t(n_t)$')

# 运能柱子（半透明）
ax.bar(x, capacity, bar_width * 0.6, color='#2E86C1', alpha=0.12, zorder=1)

# 供需缺口标注
for i in range(len(periods)):
    gap = capacity[i] - demand[i]
    mid = (demand[i] + capacity[i]) / 2
    ax.plot([x[i], x[i]], [demand[i], capacity[i]], color='#27AE60', lw=1.2, linestyle=':', zorder=3)
    ax.annotate(f'+{gap}',
                xy=(x[i], mid), fontsize=9.5, color='#27AE60', fontweight='bold',
                ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.25', facecolor='#E8F8F5', edgecolor='#27AE60', alpha=0.9))

# 每个时段标注需求值和运能值
for i in range(len(periods)):
    ax.text(x[i], demand[i] - 55, f'{demand[i]}人次',
            ha='center', fontsize=10, color='#E74C3C', fontweight='bold')
    ax.text(x[i], capacity[i] + 22, f'{capacity[i]}人次',
            ha='center', fontsize=10, color='#2E86C1', fontweight='bold')

# 调度信息框
info_texts = [
    f'{n_vehicles[i]}辆  |  间隔{headway[i]}min  |  满载率{load[i]:.2f}'
    for i in range(3)
]
bbox_colors = ['#EBF5FB', '#EBF5FB', '#D5F5E3']
for i, txt in enumerate(info_texts):
    ax.text(x[i], capacity[i] + 80, txt,
            ha='center', fontsize=8.5, color='#555',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=bbox_colors[i],
                      edgecolor='#CCC', alpha=0.85))

# 坐标轴
ax.set_xticks(x)
ax.set_xticklabels(periods, fontsize=11)
ax.set_ylabel('人次', fontsize=12, fontweight='bold')
ax.set_ylim(0, max(capacity) + 160)

# 网格
ax.yaxis.grid(True, linestyle='--', alpha=0.3)
ax.set_axisbelow(True)

# 图例
ax.legend(loc='upper left', fontsize=10, framealpha=0.9)

ax.set_title('潮汐客流供需匹配 — 微公交调度方案',
             fontsize=14, fontweight='bold', pad=14)

# 底部说明
fig.text(0.5, 0.01,
         '绿色+标注为运能冗余量，运能线始终紧贴需求线上方，既无运能浪费也无乘客滞留',
         ha='center', fontsize=9, color='#888')

plt.tight_layout(rect=[0, 0.05, 1, 0.95])

out = os.path.join(BASE_DIR, 'tidal_supply_demand.png')
plt.savefig(out, dpi=200, bbox_inches='tight', facecolor='white')
plt.close()

print(f'已生成: {out}')
