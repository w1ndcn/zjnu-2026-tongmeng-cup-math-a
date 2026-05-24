# CUMCM A题问题一建模流程与文件说明

> 说明：本文档基于当前工作区内全部核心脚本、输入文件与输出结果整理，重点覆盖 `step1_build_graph.py` 到 `step6_evaluate.py` 的完整数据流、模型逻辑、文件作用与结果含义。

## 1. 项目总览

本项目围绕 CUMCM A题“浙师大校园微交通系统综合治理与优化设计”展开，当前问题一的实现主线已经打通：

`campus_network.txt` → `step1_build_graph.py` → `output_step1/`
→ `step2_od_matrix.py` → `output_step2/`
→ `step3_ue_fw.py` → `output_step3/`
→ `step4_scenarios.py` → `output_step4/`
→ `step5_k_shortest.py` → `output_step5/`
→ `step6_evaluate.py` → `output_step6/`

整体建模思路可概括为：

1. 将校园路网抽象为有向加权图；
2. 基于建筑容量与距离衰减构造分时段、分方式 OD 需求；
3. 用多类用户均衡模型计算现状流量、旅行时间、饱和度与冲突风险；
4. 设计单行线、限行与隔离等情景方案并重跑分配；
5. 对重点 OD 执行 K 短路径分流分析；
6. 汇总形成综合评价报告，选出最优方案。

---

## 2. 论文版建模流程

### 2.1 路网抽象与图构建

首先读取 `campus_network.txt` 中的节点清单与边清单，将校园道路系统建模为有向图 `G=(V,E)`。节点包括教学楼、宿舍、食堂/商业节点与交叉口节点；边包含起点、终点、长度与宽度等属性。

在 `step1_build_graph.py` 中：

- 使用 `networkx.DiGraph()` 构建有向图；
- 根据道路宽度估计通行能力：
  - `width >= 7.0` → `capacity = 1200`
  - `4.0 <= width < 7.0` → `capacity = 600`
  - `width < 4.0` → `capacity = 300`
- 以 `free_time = length / 5.56` 作为机动车自由流时间近似；
- 计算邻接矩阵与最短距离矩阵；
- 输出 `adjacency_matrix.csv`、`distance_matrix.csv`、`node_order.txt` 与 `campus_graph.gml`。

这一阶段的作用是把非结构化校园地图转为后续可计算的网络模型。

### 2.2 OD 需求生成

`step2_od_matrix.py` 基于步骤一的节点顺序与距离矩阵，采用引力模型生成三时段、四方式的 OD 需求。

核心公式为：

```text
T_ij = O_i × (D_j × d_ij^(-γ)) / Σ_k(D_k × d_ik^(-γ))
```

其中：

- `O_i`：出发建筑的人群产生量；
- `D_j`：到达建筑的吸引力；
- `d_ij`：建筑间最短距离；
- `γ = 1.5`：距离衰减系数。

时段设置：

- 早高峰：宿舍 → 教学楼，满载率 `0.90`
- 午高峰：教学楼 → 食堂/商业街，满载率 `1.00`
- 晚高峰：教学楼 → 宿舍，满载率 `0.50`

方式划分采用距离阶梯：

- `<500m`：步行占比高
- `500-1000m`：电动车占比提高
- `1000-1500m`：电动车与机动车混合增加
- `>1500m`：机动车比例继续上升

输出为 `od_{period}_{mode}.csv` 和 `od_{period}_total.csv`。

### 2.3 多类用户均衡分配

`step3_ue_fw.py` 是整套模型的核心。它将 OD 需求映射到路网中，使用多类用户均衡（UE）+ BPR 阻抗函数 + Frank-Wolfe 算法求解现状流量。

#### 2.3.1 阻抗函数

```text
t_e(x) = t0_e · [1 + α · (x/c)^β]
```

其中：

- `α = 0.15`
- `β = 4.0`
- `t0_e` 为自由流时间
- `c` 为通行能力
- `x` 为等效流量

#### 2.3.2 多方式等效换算

使用 PCU 等效系数：

```python
XI = {'p': 0.10, 'b': 0.30, 'c': 1.00, 'bus': 0.50}
```

即把步行、电动车、机动车和接驳车统一折算到等效流量上。

#### 2.3.3 Frank-Wolfe 求解

实现流程：

1. 自由流初始化；
2. 用当前阻抗做最短路；
3. AON（全有全无）分配得到辅助流；
4. 用二分线搜索求最优步长；
5. 更新流量并检查收敛。

#### 2.3.4 评价输出

本步骤同时输出：

- `link_flow_{period}.csv`：路段流量、V/C、LOS、风险；
- `baseline.txt`：三个时段的 TTT 与 S；
- `baseline_summary.txt`：补充摘要指标。

其中：

- `TTT` 表示总行程时间；
- `S` 表示人车冲突风险；
- `LOS` 按 V/C 划分 A-F 级服务水平。

### 2.4 情景方案设计

`step4_scenarios.py` 用于设计治理措施并重跑 UE，比较不同方案效果。

当前设置了三类方案：

- 方案A：关键桥梁单行线
- 方案B：午高峰食堂区限行
- 方案C：综合优化（A+B+人车隔离）

实现方式包括：

- 删除反向边实现单行线；
- 午高峰对机动车敏感路段降容；
- 对指定隔离路段的冲突风险乘以折扣系数 `0.4`。

最终输出 `scenario_comparison.csv`，对比各方案的：

- `TTT合计`
- `η_TTT`
- `S合计`
- `η_S`
- `avgV/C`
- `η_VC`
- `maxV/C`

### 2.5 重点 OD 的 K 短路径分流

`step5_k_shortest.py` 使用 Yen's Algorithm 的 blocked-edge 版本，为重点 OD 构造 3 条候选路径，并按广义费用进行分流。

广义费用由以下因素构成：

- 时间成本
- 距离成本
- 风险成本
- 额外惩罚项

权重配置：

```python
THETA = {'time': 0.40, 'dist': 0.20, 'risk': 0.30, 'penalty': 0.10}
```

再通过：

```python
split_ratio(costs)
```

将流量按“费用越小、分配越高”的原则分给候选路径。

输出：

- `k_shortest_paths.csv`
- `path_report.txt`

### 2.6 效果评价

`step6_evaluate.py` 是最终评价脚本，读取 `scenario_comparison.csv` 与 `link_flow_{period}.csv`，生成综合报告 `evaluation_report.txt`。

当前逻辑：

- 将 `η_TTT`、`η_S`、`η_VC` 转为数值；
- 以 `η_S_num` 最大作为最优方案；
- 统计各时段 LOS 分布；
- 写出正式评价结论。

当前结果显示：

- 最优方案：`方案C：综合优化`
- 总行程时间改善：`+15.3%`
- 人车冲突风险降低：`+50.5%`
- 平均 V/C 改善：`+15.8%`

---

## 3. `.py` 文件作用表

| 文件名 | 作用 | 主要输入 | 主要输出 |
|---|---|---|---|
| `step1_build_graph.py` | 解析校园路网文本并构建有向图 | `campus_network.txt` | `adjacency_matrix.csv`、`distance_matrix.csv`、`node_order.txt`、`campus_graph.gml` |
| `step2_od_matrix.py` | 基于引力模型生成分时段、分方式 OD 矩阵 | `output_step1/distance_matrix.csv`、`output_step1/node_order.txt` | `od_{period}_{mode}.csv`、`od_{period}_total.csv` |
| `step3_ue_fw.py` | 多类用户均衡分配，计算路段流量与拥堵指标 | `output_step1/campus_graph.gml`、`output_step2/od_*.csv` | `link_flow_{period}.csv`、`baseline.txt` |
| `step4_scenarios.py` | 构建治理方案并重跑 UE 进行对比 | `output_step1/campus_graph.gml`、`output_step2/od_*.csv`、`output_step3/link_flow_*.csv` | `scenario_comparison.csv` |
| `step5_k_shortest.py` | 对重点 OD 做 K 短路径分流 | `output_step1/campus_graph.gml`、`output_step2/od_*.csv`、`output_step3/link_flow_*.csv` | `k_shortest_paths.csv`、`path_report.txt` |
| `step6_evaluate.py` | 汇总方案效果并生成最终评价报告 | `output_step4/scenario_comparison.csv`、`output_step3/link_flow_*.csv` | `evaluation_report.txt` |

---

## 4. 输出文件及含义表

### 4.1 `output_step1/`

| 文件名 | 含义 |
|---|---|
| `adjacency_matrix.csv` | 路网邻接矩阵，表示节点间有向连接关系 |
| `distance_matrix.csv` | 全节点最短路径距离矩阵，是 OD 生成的基础 |
| `node_order.txt` | 矩阵行列对应的节点顺序 |
| `campus_graph.gml` | NetworkX 图对象文件，后续步骤直接读取 |

### 4.2 `output_step2/`

| 文件名模式 | 含义 |
|---|---|
| `od_morning_p.csv` | 早高峰步行 OD 矩阵 |
| `od_morning_b.csv` | 早高峰电动车 OD 矩阵 |
| `od_morning_c.csv` | 早高峰机动车 OD 矩阵 |
| `od_morning_bus.csv` | 早高峰接驳车预留矩阵 |
| `od_morning_total.csv` | 早高峰总 OD 矩阵 |
| `od_noon_*.csv` | 午高峰对应 OD 矩阵 |
| `od_evening_*.csv` | 晚高峰对应 OD 矩阵 |

### 4.3 `output_step3/`

| 文件名 | 含义 |
|---|---|
| `link_flow_morning.csv` | 早高峰路段流量、饱和度、LOS 与风险 |
| `link_flow_noon.csv` | 午高峰路段流量、饱和度、LOS 与风险 |
| `link_flow_evening.csv` | 晚高峰路段流量、饱和度、LOS 与风险 |
| `edge_flows_morning.csv` | 早高峰另一版边流量输出，包含 `flow_pcu`、`V/C`、`travel_time_s` 等字段 |
| `edge_flows_noon.csv` | 午高峰边流量输出 |
| `edge_flows_evening.csv` | 晚高峰边流量输出 |
| `baseline.txt` | 基准现状三个时段的 TTT 与 S 汇总 |
| `baseline_summary.txt` | 基准现状补充摘要，含 `TTT_s`、`TTT_h`、`edges_high_vc` |

### 4.4 `output_step4/`

| 文件名 | 含义 |
|---|---|
| `scenario_comparison.csv` | 各方案的 TTT、S、V/C 与改善率对比表 |

### 4.5 `output_step5/`

| 文件名 | 含义 |
|---|---|
| `k_shortest_paths.csv` | 重点 OD 的 K 短路径分流结果，含路径、广义费用、分配比例与人流量 |
| `path_report.txt` | 可读形式的重点 OD 路径分流报告 |

### 4.6 `output_step6/`

| 文件名 | 含义 |
|---|---|
| `evaluation_report.txt` | 最终综合评价报告，包含最优方案、指标对比和 LOS 分布 |

---

## 5. step6_evaluate.py 检查结论

### 5.1 结论

`step6_evaluate.py` 目前逻辑是正确的，能够：

- 正常读取 `output_step4/scenario_comparison.csv`；
- 正常读取 `output_step3/link_flow_{period}.csv`；
- 正常生成 `output_step6/evaluation_report.txt`；
- 正确选出当前最优方案 `方案C：综合优化`。

### 5.2 当前可保留的逻辑

- 通过 `η_S_num` 最大选择最优方案，这一点与当前评价目标一致；
- 报告输出结构清晰，适合直接作为论文结果部分的基础文本；
- LOS 分布统计保留了各时段的路段服务水平信息，便于写作。

### 5.3 可优化点

1. 文件注释写的是“步骤四+六”，但当前脚本定位已更像独立的步骤六；
2. 终端输出若出现乱码，多半是显示环境问题，不影响 UTF-8 报告文件本身；
3. 若论文更强调综合平衡，可考虑在最优方案判定中引入 `TTT`、`S`、`V/C` 的加权评分，而不是只看 `η_S_num`。

---

## 6. 论文写作可直接引用的简版表述

本研究首先根据校园道路与建筑分布构建有向加权图，并计算节点间最短路径距离矩阵。随后，结合建筑容量、时段满载率与距离衰减引力模型，生成分时段、分方式的 OD 需求。接着，在多类用户均衡框架下，采用 BPR 阻抗函数和 Frank-Wolfe 算法求解路段流量分布，并据此计算总行程时间、路段饱和度、服务水平及人车冲突风险。在此基础上，设计单行线、限行与人车隔离等治理情景，重跑均衡分配并比较方案效果；进一步针对重点 OD 使用 K 短路径分流模型优化出行组织。最后，依据综合评价指标对方案效果进行汇总，确定最优治理方案。

---

## 7. 当前最优结果

- 最优方案：`方案C：综合优化`
- `TTT` 改善：`+15.3%`
- `S` 改善：`+50.5%`
- 平均 `V/C` 改善：`+15.8%`

这说明当前综合方案在效率与安全之间取得了更好的平衡。
