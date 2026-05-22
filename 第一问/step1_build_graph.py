"""
步骤一：建图
输入: campus_network.txt（节点清单 + 边清单）
输出: 邻接矩阵 A, 距离矩阵 D, 路网拓扑
"""

import networkx as nx
import numpy as np
import os

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

DATA_FILE = "campus_network.txt"
OUTPUT_DIR = "output_step1"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def parse_txt(filepath):
    nodes = {}
    edges = []
    with open(filepath, "r", encoding="utf-8") as f:
        mode = None
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
    return nodes, edges


def build_graph(nodes, edges):
    G = nx.DiGraph()
    for name, ntype in nodes.items():
        G.add_node(name, type=ntype)
    for u, v, length, width in edges:
        # 宽度 → 通行能力 (pcu/h)
        if width >= 7.0:
            capacity = 1200
        elif width >= 4.0:
            capacity = 600
        else:
            capacity = 300
        free_time = length / 5.56
        G.add_edge(u, v, length=length, width=width, capacity=capacity, free_time=free_time)
        G.add_edge(v, u, length=length, width=width, capacity=capacity, free_time=free_time)
    print(f"节点数: {G.number_of_nodes()}")
    print(f"边数(有向): {G.number_of_edges()}")
    return G


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


def print_summary(node_list, A, D, G):
    building_nodes = [n for n in G.nodes() if G.nodes[n].get("type") not in ("交叉口", None)]
    junction_nodes = [n for n in G.nodes() if G.nodes[n].get("type") == "交叉口"]

    print(f"\n建筑节点 ({len(building_nodes)}个):", ", ".join(sorted(building_nodes)))
    print(f"交叉口节点 ({len(junction_nodes)}个)", end="")
    isolated = [n for n in G.nodes() if G.degree(n) == 0]
    if isolated:
        print(f"  [警告: {len(isolated)} 个孤立节点: {isolated}]")
    else:
        print("  [全部连通]")

    # 检查重点 OD 可达性
    print("\n=== 重点 OD 距离检查 ===")
    pairs = [
        ("T_16_W", "C_T"), ("T_16_W", "D_T"), ("T_16_E", "C_T"), ("T_16_E", "D_T"),
        ("T_25", "C_T"), ("T_25", "D_T"), ("T_25", "C_S"),
        ("T_25", "C_X"), ("T_25", "C_G"), ("T_25", "D_X"), ("T_25", "D_C"), ("T_25", "D_G"),
        ("T_16_W", "C_X"), ("T_16_E", "C_X"), ("T_16_W", "D_X"), ("T_16_E", "D_X"),
    ]
    idx = {name: i for i, name in enumerate(node_list)}
    for u, v in pairs:
        if u in idx and v in idx:
            d = D[idx[u]][idx[v]]
            status = f"{d:.0f}m" if d < np.inf else "不通!"
            print(f"  {u:8s} -> {v:5s} : {status}")

    print(f"\n=== 枢纽节点（度排序 Top 10）===")
    for name, deg in sorted(G.degree(), key=lambda x: -x[1])[:10]:
        print(f"  {name:6s}: 度 = {deg}")


def main():
    if not os.path.exists(DATA_FILE):
        print(f"错误: 找不到 {DATA_FILE}")
        return
    print(f"读取: {DATA_FILE}")
    nodes, edges = parse_txt(DATA_FILE)
    print(f"解析: {len(nodes)} 节点, {len(edges)} 条边(无向)")
    G = build_graph(nodes, edges)
    node_list, A, D = compute_matrices(G)
    print_summary(node_list, A, D, G)

    np.savetxt(os.path.join(OUTPUT_DIR, "adjacency_matrix.csv"), A, fmt="%d", delimiter=",")
    np.savetxt(os.path.join(OUTPUT_DIR, "distance_matrix.csv"), D, fmt="%.2f", delimiter=",")
    with open(os.path.join(OUTPUT_DIR, "node_order.txt"), "w") as f:
        for name in node_list:
            f.write(name + "\n")
    nx.write_gml(G, os.path.join(OUTPUT_DIR, "campus_graph.gml"))

    print(f"\n输出已保存到 {OUTPUT_DIR}/")
    print(f"  邻接矩阵 ({len(node_list)}x{len(node_list)}): adjacency_matrix.csv")
    print(f"  距离矩阵 ({len(node_list)}x{len(node_list)}): distance_matrix.csv")
    print(f"  节点顺序: node_order.txt")
    print(f"  图对象:   campus_graph.gml")


if __name__ == "__main__":
    main()
