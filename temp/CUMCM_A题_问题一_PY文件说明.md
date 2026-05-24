# CUMCM A题 问题一 — PY 文件说明

> 高峰期主干道人车混行与分流优化  
> 7 个脚本，从路网构建到可视化

---

## 文件清单

| 文件名 | 作用 | 核心算法 | 输入 | 输出 |
|---|---|---|---|---|
| **step1_build_graph.py** | 解析校园路网文本，构建有向加权图 | DiGraph 建图、Dijkstra 最短距离矩阵 | `campus_network.txt` | `output_step1/`（邻接矩阵、距离矩阵、节点顺序、GML 图） |
| **step2_od_matrix.py** | 基于引力模型生成三时段×四方式的 OD 需求矩阵 | 引力模型 \(T_{ij}=O_i \cdot D_j d_{ij}^{-\gamma}/\sum\)，距离阶梯方式划分 | `output_step1/` | `output_step2/`（15 个 CSV：3时段×5文件） |
| **step3_ue_fw.py** | 多类用户均衡分配，计算现状路段流量/饱和度/风险 | BPR 阻抗 + Frank-Wolfe 求解多类 UE | `output_step1/` + `output_step2/` | `output_step3/`（路段流量表、baseline TTT/S） |
| **step4_scenarios.py** | 设计 A/B/C 三类治理方案，重跑 UE 对比效果 | 方案应用（删边/降容/隔离折扣）+ FW 重分配 | `output_step1/` + `output_step2/` | `output_step4/scenario_comparison.csv` |
| **step5_k_shortest.py** | 对 24 对重点 OD 做 K=3 短路径分流 | Yen's blocked-edge K-最短路径 + 广义费用 logit 分流 | `output_step1/` + `output_step2/` + `output_step3/` | `output_step5/`（72 条路径记录 + 报告） |
| **step6_evaluate.py** | 汇总方案对比，生成最终评价报告 | 以 S 改善最大选最优方案 | `output_step4/` + `output_step3/` | `output_step6/evaluation_report.txt` |
| **step7_heatmap.py** | 生成三时段 V/C 热力图（基准 vs 方案C 左右对比） | kamada_kawai 布局 + matplotlib 颜色映射 | `campus_network.txt` + `output_step2/` | `output_step7/`（3 张 PNG） |

---

## 各文件详细信息

### step1_build_graph.py

**做什么**：把 `campus_network.txt` 转成 NetworkX 有向图。

**算法**：
- 道路宽度 → 通行能力：≥7m→1200, 4~7m→600, <4m→300 pcu/h
- 自由流时间：\(t_0 = \text{length} / 5.56\)（20 km/h）
- 计算全节点最短距离矩阵（Dijkstra）

**输出关键数据**：
- 60 节点（11 建筑 + 49 交叉口）、152 条有向边
- 邻接矩阵 `adjacency_matrix.csv`、距离矩阵 `distance_matrix.csv`

---

### step2_od_matrix.py

**做什么**：生成早/午/晚三个时段，步行/电动车/机动车/接驳车四种方式的出行需求矩阵。

**算法**：
- 引力模型：\(T_{ij} = O_i \times \frac{D_j \cdot d_{ij}^{-\gamma}}{\sum D_k \cdot d_{ik}^{-\gamma}}\)，\(\gamma=1.5\)
- 方式划分：按距离阶梯（<500m 步行 70%，500-1000m 电动车 55%，>1500m 电车 75%）
- 满载率：早 0.90 / 午 1.00 / 晚 0.50

**时段流向**：
- 早高峰：宿舍 → 教学楼
- 午高峰：教学楼 → 食堂/商业街
- 晚高峰：教学楼 → 宿舍

---

### step3_ue_fw.py

**做什么**：用 Frank-Wolfe 算法求解多类用户均衡，得到各路段流量。

**算法**：
- BPR 阻抗：\(t_e(x) = t_0 \cdot [1 + 0.15 \cdot (x/c)^4]\)
- PCU 换算：\(x_e = 0.10f_p + 0.30f_b + 1.00f_c\)
- FW 迭代：Dijkstra 最短路 → AON 分配 → 二分线搜索 → 收敛判断（最多 50 次）

**评价指标**：
- TTT（总行程时间）：\(\sum f_e^m \cdot t_e^m(x_e)\)
- S（人车冲突风险）：\(\sum (\omega_{pb}x_px_b + \omega_{pc}x_px_c + \omega_{bc}x_bx_c)\)
- V/C（饱和度）、LOS（服务水平 A-F）

**输出**：各时段路段流量 CSV（含 flow_p/b/c、saturation、LOS、risk）

---

### step4_scenarios.py

**做什么**：设计并对比三类治理方案。

**方案定义**：

| 方案 | 措施 | 实现方式 |
|---|---|---|
| A 桥梁单行线 | J_04↔J_19、J_02↔J_16 早高峰单向 | 删除反向边 |
| B 食堂限行 | 午高峰食堂周边禁机动车 | capacity×0.6 + 机动车需求×0.3 |
| C 综合 | A+B+14 条路段人车隔离 | 方案叠加 + 隔离路段风险×0.4 |

**结果**：方案 C 最优 → **TTT -15.3%, S -50.5%**

---

### step5_k_shortest.py

**做什么**：对 3 教学楼 × 8 食堂/宿舍 = 24 对重点 OD，各找 3 条备选路径并分流。

**算法**：
- Yen's blocked-edge K-最短路径
- 广义费用：\(g = 0.40T + 0.20(D/1000) + 0.30R\)
- 分流比例：\(p_k = (1/g_k)^2 / \sum (1/g_j)^2\)

**输出**：72 条路径记录（含距离、时间、分流比例、路径节点序列）

---

### step6_evaluate.py

**做什么**：读取 step3 现状 + step4 方案对比，生成最终评价报告。

**逻辑**：以冲突风险 S 改善率最大选最优 → 方案 C。

**输出**：`evaluation_report.txt`（含核心指标对比、LOS 分布、结论）

---

### step7_heatmap.py

**做什么**：生成早/午/晚三时段的 V/C 热力图，左半=基准，右半=方案 C。

**技术**：
- 布局：`kamada_kawai_layout`（比 spring 更规整）
- 颜色：V/C 映射 绿(A)→黄(C)→橙(D)→红(E)→深红(F)
- 节点标注：所有建筑中文名 + 关键交叉口

**输出**：`output_step7/heatmap_{period}.png`（3 张）
