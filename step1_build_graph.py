"""
步骤一：建图（v2 — 质心法 + 虚拟路段）
=====================================
输入: campus_network.txt（N1-N64交叉口 + 建筑质心 + 虚拟路段width=99）
输出: output_step1/（邻接矩阵、距离矩阵、GML图）

变更:
  - 节点命名: N1~N64 交叉口, 建筑用名称(TYGY/T_16/T_1~T_10等)
  - 路宽分类: 12m→主干, 8m→次干, 6m→支路, 99→虚拟路段(不限流)
  - 建筑通过虚拟路段连接多个路口(质心法)
"""

import networkx as nx
import numpy as np
import os

DATA_FILE = "campus_network.txt"
OUTPUT_DIR = "output_step1"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════ 1. 解析 ═══════════════════
BUILDING_NAMES = {'TYGY','TYST','XYST','XYGY','GYST','CYGY','GYGY',
                  'T_16','T_25',
                  'T_1','T_2','T_3','T_4','T_5','T_6','T_7','T_8','T_9','T_10',
                  'SYJ'}

def parse_txt(filepath):
    nodes = {}   # name → type
    edges = []   # (u, v, length, width)
    mode = None
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                if "节点" in line:
                    mode = "node"
                elif "边" in line:
                    mode = "edge"
                continue
            parts = [p.strip() for p in line.split(",")]
            if mode == "node" and len(parts) >= 2:
                nodes[parts[0]] = parts[1]
            elif mode == "edge" and len(parts) >= 4:
                u, v, length, width = parts[0], parts[1], float(parts[2]), float(parts[3])
                edges.append((u, v, length, width))

    # 从边列表自动补全缺失节点（建筑质心 + N63/N64 等新路口）
    for u, v, _, _ in edges:
        for nd in (u, v):
            if nd not in nodes:
                if nd in BUILDING_NAMES:
                    nodes[nd] = '建筑'   # 先标为建筑，后面再细化
                else:
                    nodes[nd] = '交叉口'

    return nodes, edges

# ═══════════════════ 2. 建图 ═══════════════════
def build_graph(nodes, edges):
    G = nx.DiGraph()

    # 建筑类型映射
    BUILDING_TYPE_MAP = {
        'TYGY': '宿舍', 'TYST': '食堂', 'XYST': '食堂',
        'XYGY': '宿舍', 'GYST': '食堂', 'CYGY': '宿舍',
        'GYGY': '宿舍', 'T_16': '教学楼', 'T_25': '教学楼',
        'T_1': '教学楼', 'T_2': '教学楼', 'T_3': '教学楼',
        'T_4': '教学楼', 'T_5': '教学楼', 'T_6': '教学楼',
        'T_7': '教学楼', 'T_8': '教学楼', 'T_9': '教学楼',
        'T_10': '教学楼', 'SYJ': '商业街',
    }

    for name, ntype in nodes.items():
        mapped = BUILDING_TYPE_MAP.get(name, ntype)
        G.add_node(name, type=mapped)

    for u, v, length, width in edges:
        # 虚拟路段 (width=99): 极高通行能力、极短自由流时间
        if width >= 99.0:
            capacity = 9999      # 不限流
            free_speed = 5.56    # m/s (正常步行/骑行)
        elif width >= 12.0:
            capacity = 1200      # 交通性主干道 (12m)
            free_speed = 8.33    # 30km/h
        elif width >= 8.0:
            capacity = 800       # 生活性次干道 (8m)
            free_speed = 6.94    # 25km/h
        elif width >= 6.0:
            capacity = 600       # 支路 (6m)
            free_speed = 5.56    # 20km/h
        else:
            capacity = 300
            free_speed = 4.17    # 15km/h

        free_time = length / free_speed

        G.add_edge(u, v, length=length, width=width,
                   capacity=capacity, free_time=free_time, virtual=(width >= 99))
        G.add_edge(v, u, length=length, width=width,
                   capacity=capacity, free_time=free_time, virtual=(width >= 99))

    return G


# ═══════════════════ 3. 矩阵计算 ═══════════════════
def compute_matrices(G):
    node_list = sorted(G.nodes())
    n = len(node_list)
    idx = {name: i for i, name in enumerate(node_list)}

    A = np.zeros((n, n), dtype=int)
    for u, v in G.edges():
        A[idx[u]][idx[v]] = 1

    D = np.full((n, n), np.inf)
    for u in G.nodes():
        lengths = nx.single_source_dijkstra_path_length(G, u, weight="length")
        for v, dist in lengths.items():
            D[idx[u]][idx[v]] = dist
    return node_list, A, D


# ═══════════════════ 4. 摘要 ═══════════════════
def print_summary(node_list, G):
    building_nodes = [n for n in G.nodes()
                      if G.nodes[n].get("type") not in ("交叉口", None)]
    junction_nodes = [n for n in G.nodes()
                      if G.nodes[n].get("type") == "交叉口"]

    print(f"\n建筑节点 ({len(building_nodes)}个):")
    for b in sorted(building_nodes):
        deg = G.out_degree(b)
        print(f"  {b:6s} [{G.nodes[b].get('type','')}]  出度={deg}")

    print(f"\n交叉口节点 ({len(junction_nodes)}个)", end="")
    isolated = [n for n in G.nodes() if G.degree(n) == 0]
    if isolated:
        print(f"  [警告: {len(isolated)} 个孤立节点: {isolated}]")
    else:
        print("  [全部连通]")

    # 统计虚拟路段
    virtual_edges = [(u,v) for u,v,d in G.edges(data=True) if d.get('virtual')]
    print(f"\n虚拟路段 (width=99): {len(virtual_edges)//2} 条(无向)")

    # 道路等级分布
    from collections import Counter
    widths = [d['width'] for _,_,d in G.edges(data=True)]
    width_dist = Counter([int(w) if w < 20 else 99 for w in widths])
    print(f"路宽分布: {dict(sorted(width_dist.items()))}")


# ═══════════════════ 5. 主流程 ═══════════════════
def main():
    if not os.path.exists(DATA_FILE):
        print(f"错误: 找不到 {DATA_FILE}")
        return

    print(f"读取: {DATA_FILE}")
    nodes, edges = parse_txt(DATA_FILE)
    print(f"解析: {len(nodes)} 节点, {len(edges)} 条边(无向)")

    G = build_graph(nodes, edges)
    node_list, A, D = compute_matrices(G)
    print(f"建图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边(有向)")

    print_summary(node_list, G)

    # 保存
    np.savetxt(os.path.join(OUTPUT_DIR, "adjacency_matrix.csv"),
               A, fmt="%d", delimiter=",")
    np.savetxt(os.path.join(OUTPUT_DIR, "distance_matrix.csv"),
               D, fmt="%.2f", delimiter=",")
    with open(os.path.join(OUTPUT_DIR, "node_order.txt"), "w") as f:
        for name in node_list:
            f.write(name + "\n")
    nx.write_gml(G, os.path.join(OUTPUT_DIR, "campus_graph.gml"))

    print(f"\n输出已保存到 {OUTPUT_DIR}/")
    for fn in ["adjacency_matrix.csv", "distance_matrix.csv",
               "node_order.txt", "campus_graph.gml"]:
        print(f"  {fn}")


if __name__ == "__main__":
    main()
