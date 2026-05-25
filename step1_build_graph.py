"""
步骤一：路网构建
==============
从 campus_network_with_coords.txt 读取校园路网数据（含经纬度坐标），
构建有向加权图 G=(V,E)，输出 GraphML、邻接矩阵、距离矩阵等。

数据格式（8列）：起点, 终点, 长度m, 宽度m, 起点经度, 起点纬度, 终点经度, 终点纬度
"""

import networkx as nx
import pandas as pd
import numpy as np
import os, re

# ========== 路径配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, 'campus_network_with_coords.txt')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output_step1')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== 建筑类型映射 ==========
BUILDING_TYPE = {
    'T_16': '教学楼', 'T_25': '教学楼',
    'T_1': '教学楼', 'T_2': '教学楼', 'T_3': '教学楼',
    'T_4': '教学楼', 'T_5': '教学楼', 'T_6': '教学楼',
    'T_7': '教学楼', 'T_8': '教学楼', 'T_9': '教学楼', 'T_10': '教学楼',
    'TYGY': '宿舍', 'XYGY': '宿舍', 'CYGY': '宿舍', 'GYGY': '宿舍',
    'TYST': '食堂', 'XYST': '食堂', 'GYST': '食堂',
    'SYJ': '商业街',
}

# ========== 建筑容量（人） ==========
CAPACITY = {
    'T_16': 3000, 'T_25': 2000,
    'T_1': 1000, 'T_2': 1000, 'T_3': 1000, 'T_4': 1000, 'T_5': 1000,
    'T_6': 1000, 'T_7': 1000, 'T_8': 1000, 'T_9': 1000, 'T_10': 1000,
    'TYGY': 13000, 'XYGY': 7000, 'CYGY': 3000, 'GYGY': 5000,
    'TYST': 1100, 'XYST': 1100, 'GYST': 1100,
    'SYJ': 5000,
}

# ========== 道路等级分类 ==========
def classify_road(width):
    """根据道路宽度估计通行能力和自由流速度"""
    if width >= 99:
        return 9999, 5.56   # 虚拟路段
    elif width >= 12:
        return 1200, 8.33   # 交通性主干道 (30km/h)
    elif width >= 8:
        return 800, 6.94    # 生活性次干道 (25km/h)
    elif width >= 6:
        return 600, 5.56    # 支路 (20km/h)
    else:
        return 300, 4.17    # 狭窄路段 (15km/h)

# ========== 解析数据文件 ==========
def parse_network(filepath):
    """解析 campus_network_with_coords.txt"""
    nodes = {}    # {name: {'type': str, 'lon': float, 'lat': float}}
    edges = []    # [(u, v, length, width, lon1, lat1, lon2, lat2)]

    current_section = None
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                # 检测段落标题
                if '节点清单' in line:
                    current_section = 'nodes'
                elif '边清单' in line:
                    current_section = 'edges'
                continue

            if current_section == 'nodes':
                parts = line.split(',')
                name = parts[0].strip()
                ntype = parts[1].strip()
                nodes[name] = {'type': ntype}
                # 尝试读取坐标（如果有的话）
                if len(parts) >= 4:
                    try:
                        nodes[name]['lon'] = float(parts[2].strip())
                        nodes[name]['lat'] = float(parts[3].strip())
                    except:
                        pass

            elif current_section == 'edges':
                parts = line.split(',')
                u = parts[0].strip()
                v = parts[1].strip()
                length = float(parts[2].strip())
                width = float(parts[3].strip())
                lon1 = float(parts[4].strip()) if len(parts) >= 5 else 0
                lat1 = float(parts[5].strip()) if len(parts) >= 6 else 0
                lon2 = float(parts[6].strip()) if len(parts) >= 7 else 0
                lat2 = float(parts[7].strip()) if len(parts) >= 8 else 0
                edges.append((u, v, length, width, lon1, lat1, lon2, lat2))

                # 将起终点坐标补充到节点（如果节点还没有坐标）
                if u not in nodes:
                    nodes[u] = {'type': '交叉口'}
                if v not in nodes:
                    nodes[v] = {'type': '交叉口'}
                if 'lon' not in nodes[u] or (nodes[u].get('lon', 0) == 0 and lon1 != 0):
                    if lon1 != 0:
                        nodes[u]['lon'] = lon1
                        nodes[u]['lat'] = lat1
                if 'lon' not in nodes[v] or (nodes[v].get('lon', 0) == 0 and lon2 != 0):
                    if lon2 != 0:
                        nodes[v]['lon'] = lon2
                        nodes[v]['lat'] = lat2

    return nodes, edges

# ========== 构建有向图 ==========
def build_graph(nodes, edges):
    """构建 NetworkX 有向图"""
    G = nx.DiGraph()

    # 添加节点
    for name, attr in nodes.items():
        ntype = BUILDING_TYPE.get(name, attr.get('type', '交叉口'))
        G.add_node(name,
                   type=ntype,
                   capacity=CAPACITY.get(name, 0),
                   lon=str(attr.get('lon', '')),
                   lat=str(attr.get('lat', '')))

    # 添加边（双向）
    added_edges = set()
    for u, v, length, width, lon1, lat1, lon2, lat2 in edges:
        cap, vfree = classify_road(width)

        # 正向边
        edge_key_f = (u, v)
        if edge_key_f not in added_edges:
            G.add_edge(u, v,
                       length=length, width=width,
                       capacity=cap, free_speed=vfree,
                       free_time=length / vfree,
                       lon1=lon1, lat1=lat1,
                       lon2=lon2, lat2=lat2)
            added_edges.add(edge_key_f)

        # 反向边（虚拟路段也创建反向边，保证建筑与路口双向连通）
        edge_key_r = (v, u)
        if edge_key_r not in added_edges:
            G.add_edge(v, u,
                       length=length, width=width,
                       capacity=cap, free_speed=vfree,
                       free_time=length / vfree,
                       lon1=lon2, lat1=lat2,
                       lon2=lon1, lat2=lat1)
            added_edges.add(edge_key_r)

    return G

# ========== 计算矩阵 ==========
def compute_matrices(G, node_order):
    """计算邻接矩阵和最短距离矩阵"""
    n = len(node_order)
    idx = {name: i for i, name in enumerate(node_order)}

    # 邻接矩阵
    adj = np.zeros((n, n), dtype=int)
    # 最短距离矩阵
    dist = np.full((n, n), np.inf)
    np.fill_diagonal(dist, 0)

    for u, v, data in G.edges(data=True):
        i, j = idx[u], idx[v]
        adj[i][j] = 1
        d = data['length']
        if d < dist[i][j]:
            dist[i][j] = d

    # Floyd-Warshall 求全源最短路
    for k in range(n):
        for i in range(n):
            if dist[i][k] == np.inf:
                continue
            for j in range(n):
                if dist[k][j] == np.inf:
                    continue
                if dist[i][j] > dist[i][k] + dist[k][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]

    return adj, dist

# ========== 输出节点坐标 ==========
def output_node_coords(G, node_order, filepath):
    """输出节点坐标CSV"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('node,type,lon,lat\n')
        for name in node_order:
            ntype = G.nodes[name]['type']
            lon = G.nodes[name].get('lon', '')
            lat = G.nodes[name].get('lat', '')
            f.write(f'{name},{ntype},{lon},{lat}\n')

# ========== 主函数 ==========
def main():
    print("="*60)
    print("步骤一：校园路网建模")
    print("="*60)

    # 1. 解析数据
    print(f"\n读取数据: {INPUT_FILE}")
    nodes, edges = parse_network(INPUT_FILE)
    print(f"  节点数: {len(nodes)}")
    print(f"  边数（单向）: {len(edges)}")

    # 统计节点类型
    type_count = {}
    for name, attr in nodes.items():
        t = BUILDING_TYPE.get(name, attr.get('type', '交叉口'))
        type_count[t] = type_count.get(t, 0) + 1
    print(f"  节点类型分布: {type_count}")

    # 2. 构建图
    G = build_graph(nodes, edges)
    print(f"\n有向图构建完成:")
    print(f"  节点数: {G.number_of_nodes()}")
    print(f"  有向边数: {G.number_of_edges()}")

    # 统计路宽分布
    width_dist = {}
    for u, v, data in G.edges(data=True):
        w = data['width']
        width_dist[w] = width_dist.get(w, 0) + 1
    print(f"  路宽分布: {dict(sorted(width_dist.items()))}")

    # 3. 计算矩阵
    print("\n计算最短距离矩阵...")
    node_order = list(G.nodes())
    adj, dist = compute_matrices(G, node_order)

    # 4. 保存输出
    gml_path = os.path.join(OUTPUT_DIR, 'campus_graph.gml')
    nx.write_gml(G, gml_path)
    print(f"\n输出文件:")
    print(f"  campus_graph.gml")

    # 邻接矩阵
    adj_df = pd.DataFrame(adj, index=node_order, columns=node_order)
    adj_df.to_csv(os.path.join(OUTPUT_DIR, 'adjacency_matrix.csv'))
    print(f"  adjacency_matrix.csv")

    # 距离矩阵
    dist_df = pd.DataFrame(dist, index=node_order, columns=node_order)
    dist_df.to_csv(os.path.join(OUTPUT_DIR, 'distance_matrix.csv'))
    print(f"  distance_matrix.csv")

    # 节点顺序
    with open(os.path.join(OUTPUT_DIR, 'node_order.txt'), 'w', encoding='utf-8') as f:
        for name in node_order:
            f.write(f"{name}\n")
    print(f"  node_order.txt")

    # 节点坐标
    output_node_coords(G, node_order, os.path.join(OUTPUT_DIR, 'node_coords.csv'))
    print(f"  node_coords.csv")

    print(f"\n步骤一完成！输出目录: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
