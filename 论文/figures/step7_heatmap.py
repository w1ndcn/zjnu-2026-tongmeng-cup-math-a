"""
步骤七：校园路网 V/C 热力图可视化
================================
左图：step3 UE 基准 V/C。
右图：step5_minmax_vc.py 的 MinMax V/C 系统优化结果。
"""

import os
import math

import networkx as nx
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.lines import Line2D

# ========== 中文字体配置 ==========
fm._load_fontmanager(try_read_cache=False)
_cjk_fonts = [
    'SimHei', 'Microsoft YaHei', 'SimSun', 'FangSong', 'KaiTi',
    'STHeiti', 'STSong', 'STFangsong', 'STKaiti',
    'Heiti TC', 'PingFang HK', 'PingFang SC',
    'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'Droid Sans Fallback',
]
_available = [f.name for f in fm.fontManager.ttflist]
_cjk = None
for font in _cjk_fonts:
    if font in _available:
        _cjk = font
        break
if _cjk is None:
    for font in _cjk_fonts:
        for af in _available:
            if font.lower() in af.lower() or af.lower() in font.lower():
                _cjk = af
                break
        if _cjk:
            break
if _cjk:
    plt.rcParams['font.sans-serif'] = [_cjk] + plt.rcParams['font.sans-serif']
    plt.rcParams['font.family'] = 'sans-serif'
    print(f"[OK] 中文字体: {_cjk}")
else:
    print("[WARN] 未找到中文字体")
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STEP1_DIR = os.path.join(BASE_DIR, 'output_step1')
STEP3_DIR = os.path.join(BASE_DIR, 'output_step3')
STEP5_OPT_DIR = os.path.join(BASE_DIR, 'output_step5_minmax')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_step7')
os.makedirs(OUTPUT_DIR, exist_ok=True)

PERIODS = ['morning', 'noon', 'evening']
PERIOD_NAMES = {'morning': '早高峰', 'noon': '午高峰', 'evening': '晚高峰'}

BUILDING_LABEL = {
    'T_16': '16幢', 'T_25': '25幢',
    'T 1': 'T1', 'T 2': 'T2', 'T 3': 'T3', 'T 4': 'T4', 'T 5': 'T5',
    'T 6': 'T6', 'T 7': 'T7', 'T 8': 'T8', 'T 9': 'T9', 'T 10': 'T10',
    'T_1': 'T1', 'T_2': 'T2', 'T_3': 'T3', 'T_4': 'T4', 'T_5': 'T5',
    'T_6': 'T6', 'T_7': 'T7', 'T_8': 'T8', 'T_9': 'T9', 'T_10': 'T10',
    'TYGY': '桃园\n公寓', 'TYST': '桃园\n食堂',
    'XYGY': '杏园\n公寓', 'XYST': '杏园\n食堂',
    'GYGY': '桂苑\n公寓', 'GYST': '桂苑\n食堂', 'CYGY': '初阳\n公寓',
    'SYJ': '商业街',
}


def load_vc_csv(path):
    df = pd.read_csv(path)
    vc = {}
    # 兼容新旧列名
    cols = df.columns.tolist()
    if 'from' in cols and 'to' in cols:
        ucol, vcol = 'from', 'to'
    else:
        ucol, vcol = 'u', 'v'
    if 'saturation' in cols:
        vccol = 'saturation'
    elif 'V/C' in cols:
        vccol = 'V/C'
    elif 'optimized_vc' in cols:
        vccol = 'optimized_vc'
    else:
        return vc
    for _, r in df.iterrows():
        key = (str(r[ucol]), str(r[vcol]))
        vc[key] = float(r[vccol])
    return vc


def compute_layout(G):
    geo_pos = {}
    for n, data in G.nodes(data=True):
        try:
            lon = float(data.get('lon', ''))
            lat = float(data.get('lat', ''))
            if lon != 0 and lat != 0:
                geo_pos[n] = (lon, lat)
        except (TypeError, ValueError):
            pass

    if len(geo_pos) >= max(5, int(0.6 * G.number_of_nodes())):
        xs = np.array([p[0] for p in geo_pos.values()])
        ys = np.array([p[1] for p in geo_pos.values()])
        x_mid, y_mid = xs.mean(), ys.mean()
        x_span = max(xs.max() - xs.min(), 1e-9)
        y_span = max(ys.max() - ys.min(), 1e-9)
        scale = 6.0 / max(x_span, y_span)
        pos = {}
        for n in G.nodes():
            if n in geo_pos:
                x, y = geo_pos[n]
                pos[n] = ((x - x_mid) * scale, (y - y_mid) * scale)
        missing = [n for n in G.nodes() if n not in pos]
        if missing:
            fallback = nx.spring_layout(G.to_undirected(), seed=42, k=2.0, iterations=300)
            for n in missing:
                pos[n] = (fallback[n][0] * 2.5, fallback[n][1] * 2.5)
        return pos

    return nx.kamada_kawai_layout(G.to_undirected())


def vc_color(vc):
    if vc <= 0.35:
        return (0.18, 0.72, 0.18, 0.9)
    if vc <= 0.55:
        return (0.50, 0.85, 0.18, 0.9)
    if vc <= 0.75:
        return (0.92, 0.78, 0.10, 0.9)
    if vc <= 0.90:
        return (0.95, 0.45, 0.08, 0.9)
    if vc <= 1.00:
        return (0.88, 0.12, 0.05, 0.95)
    return (0.65, 0.0, 0.0, 1.0)


def draw_heatmap(ax, G, pos, vc_by_edge, title, is_left=True):
    ax.set_title(title, fontsize=13, fontweight='bold', pad=8)
    ax.axis('off')
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    pad_x = max((max(xs) - min(xs)) * 0.08, 0.2)
    pad_y = max((max(ys) - min(ys)) * 0.08, 0.2)
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)
    ax.set_aspect('equal', adjustable='box')

    for u, v, data in G.edges(data=True):
        vc = vc_by_edge.get((u, v), 0.0)
        ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                color=vc_color(vc), linewidth=0.8 + 5.0 * min(vc, 1.5), alpha=0.82, zorder=1)

    # 标注真实道路高 V/C 数值
    for u, v, data in G.edges(data=True):
        vc = vc_by_edge.get((u, v), 0.0)
        width = float(data.get('width', 0))
        if vc < 0.75 or width >= 99:
            continue
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        nx_dir, ny_dir = (-dy / length, dx / length) if length > 0 else (0, 0)
        tx, ty = mx + nx_dir * 0.08, my + ny_dir * 0.08
        color = '#900' if vc >= 1.0 else '#C0392B'
        ax.annotate(f'{vc:.2f}', (tx, ty), fontsize=6.5, color=color, fontweight='bold',
                    ha='center', va='center', zorder=7,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                              edgecolor=color, alpha=0.92, linewidth=0.8))

    buildings = {n for n in G.nodes() if G.nodes[n].get('type', '') != '交叉口'}
    for n in G.nodes():
        if n in buildings:
            x, y = pos[n]
            nm = G.nodes[n].get('type', '')
            c = {'教学楼': '#E74C3C', '宿舍': '#3498DB', '食堂': '#27AE60', '商业街': '#27AE60'}.get(nm, '#888')
            ax.scatter(x, y, s=160, c=c, edgecolors='white', linewidth=1.5, zorder=5)
            label = BUILDING_LABEL.get(n, n)
            ax.annotate(label, (x, y), textcoords='offset points', xytext=(0, -16),
                        fontsize=7.5, ha='center', color='#222', fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.85), zorder=6)
        else:
            ax.scatter(pos[n][0], pos[n][1], s=8, c='#CCCCCC', zorder=2)

    legend_vc = [Line2D([0], [0], color=vc_color(x), lw=3, label=l)
                 for x, l in [(0.2, 'A ≤0.35'), (0.45, 'B'), (0.65, 'C'),
                              (0.85, 'D'), (0.95, 'E'), (1.3, 'F >1.00')]]
    if is_left:
        ax.legend(handles=legend_vc, loc='lower left', fontsize=6.5, framealpha=0.85, title='V/C')


def summarize(period, base_vc, opt_vc, G):
    real_edges = [(u, v) for u, v, d in G.edges(data=True) if float(d.get('width', 0)) < 99]
    b_vals = [base_vc.get(e, 0.0) for e in real_edges]
    o_vals = [opt_vc.get(e, 0.0) for e in real_edges]
    b_max = max(b_vals) if b_vals else 0.0
    o_max = max(o_vals) if o_vals else 0.0
    b_high = sum(x > 0.75 for x in b_vals)
    o_high = sum(x > 0.75 for x in o_vals)
    return f"基准max={b_max:.2f}, 优化max={o_max:.2f}; 高负荷边 {b_high}→{o_high}"


def main():
    G = nx.read_gml(os.path.join(STEP1_DIR, 'campus_graph.gml'))
    pos = compute_layout(G)

    for period in PERIODS:
        print(f"{period} ...")
        base_path = os.path.join(STEP3_DIR, f'link_flow_{period}.csv')
        opt_path = os.path.join(STEP5_OPT_DIR, f'link_flow_optimized_{period}.csv')
        if not os.path.exists(base_path):
            raise FileNotFoundError(base_path)
        if not os.path.exists(opt_path):
            raise FileNotFoundError(opt_path)

        base_vc = load_vc_csv(base_path)
        opt_vc = load_vc_csv(opt_path)
        summary = summarize(period, base_vc, opt_vc, G)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(24, 11), facecolor='white')
        draw_heatmap(ax1, G, pos, base_vc, f'UE基准 — {PERIOD_NAMES[period]}', True)
        draw_heatmap(ax2, G, pos, opt_vc, f'MinMax V/C优化 — {PERIOD_NAMES[period]}', False)
        plt.suptitle(f'校园路网 V/C 热力图 | {PERIOD_NAMES[period]} | {summary}', fontsize=15, fontweight='bold', y=0.99)
        plt.tight_layout(rect=[0, 0.02, 1, 0.93])
        out = os.path.join(OUTPUT_DIR, f'heatmap_{period}.png')
        plt.savefig(out, dpi=220, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  {summary}")
        print(f"  -> {out}")

    print(f"\n全部完成: {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()
