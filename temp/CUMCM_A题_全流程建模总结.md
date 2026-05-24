# CUMCM A题 全流程建模总结

> 浙师大校园微交通系统综合治理与优化设计  
> 覆盖问题一（高峰期人车混行与分流优化）+ 问题二（电动车环境承载力评估）

---

## 项目结构

```
workdir/
├── campus_network.txt          # 校园路网原始数据（60节点，77条无向边）
├── step1_build_graph.py        # ─┐
├── step2_od_matrix.py          #  │
├── step3_ue_fw.py              #  │ 问题一：交通流建模
├── step4_scenarios.py          #  │
├── step5_k_shortest.py         #  │
├── step6_evaluate.py           #  │
├── step7_heatmap.py            # ─┘ 问题一：可视化
├── step8_zones.py              # ─┐
├── step9_static.py             #  │ 问题二：承载力评估
├── step10_dynamic.py           #  │
├── step11_solve.py             # ─┘
├── output_step1/ ~ output_step11/   # 各步骤输出
└── CUMCM_A题_问题一_建模流程与文件说明.md
```

---

## 问题一：高峰期人车混行与分流优化

### step1 — 路网构建

**做了什么**：解析 `campus_network.txt`，构建浙师大金华校区有向加权路网图。

**算法/公式**：
- `networkx.DiGraph()` 有向图，节点=建筑+交叉口，边=道路段
- 道路宽度 → 通行能力：`width≥7→1200, 4-7→600, <4→300 pcu/h`
- 自由流时间：`t₀ = length / 5.56`（按机动车 20km/h）
- 邻接矩阵 + Floyd/Dijkstra 最短距离矩阵

**输出**：`output_step1/`
| 文件 | 含义 |
|---|---|
| `adjacency_matrix.csv` | 60×60 邻接矩阵 |
| `distance_matrix.csv` | 60×60 最短路径距离矩阵 |
| `node_order.txt` | 矩阵行列对应的节点顺序 |
| `campus_graph.gml` | NetworkX 图对象（后续步骤直接读取） |

**路网规模**：60 节点（11 建筑 + 49 交叉口），152 条有向边

---

### step2 — OD 需求生成

**做了什么**：基于引力模型生成早/午/晚三时段、步行/电动车/机动车/接驳车四方式的出行需求矩阵。

**算法/公式**：

引力模型：
\[
T_{ij} = O_i \times \frac{D_j \cdot d_{ij}^{-\gamma}}{\sum_k D_k \cdot d_{ik}^{-\gamma}}
\]

其中 \(O_i\) 为出发建筑产生量（building capacity × 时段满载率），\(D_j\) 为到达建筑吸引力，\(\gamma = 1.5\) 为距离衰减系数。

距离阶梯方式划分：
| 距离 | 步行 p | 电动车 b | 机动车 c |
|---|---|---|---|
| <500m | 70% | 25% | 5% |
| 500-1000m | 35% | 55% | 10% |
| 1000-1500m | 15% | 70% | 15% |
| >1500m | 5% | 75% | 20% |

时段满载率：早高峰 0.90, 午高峰 1.00, 晚高峰 0.50

**输出**：`output_step2/`（15 个 CSV）
| 文件模式 | 含义 |
|---|---|
| `od_{period}_{mode}.csv` | 分时段分方式 OD 矩阵 |
| `od_{period}_total.csv` | 分时段总 OD 矩阵 |

---

### step3 — 多类用户均衡交通分配

**做了什么**：用 Frank-Wolfe 算法求解多类用户均衡（UE），得到现状各路段流量、V/C、服务水平。

**算法/公式**：

BPR 阻抗函数：
\[
t_e(x) = t_0^e \cdot \left[1 + \alpha \cdot \left(\frac{x}{c}\right)^\beta\right],\quad \alpha = 0.15,\;\beta = 4.0
\]

PCU 等效换算（多方式统一）：
\[
x_e = 0.10 \cdot f_p + 0.30 \cdot f_b + 1.00 \cdot f_c
\]

Frank-Wolfe 迭代：
1. 用当前阻抗做 Dijkstra 最短路
2. AON（全有全无）分配得到辅助流
3. 二分线搜索求最优步长
4. 更新流量，检查收敛

评价指标：
- **TTT**（总行程时间）：\(TTT = \sum_{e,m} f_e^m \cdot t_e^m(x_e)\)
- **S**（人车冲突风险）：\(S = \sum_e (\omega_{pb} x_p x_b + \omega_{pc} x_p x_c + \omega_{bc} x_b x_c)\)
- **V/C**（饱和度）、**LOS**（服务水平 A-F）

**输出**：`output_step3/`
| 文件 | 含义 |
|---|---|
| `link_flow_{period}.csv` | 路段流量、V/C、LOS、风险 |
| `baseline.txt` | 三时段 TTT + S 汇总 |
| `baseline_summary.txt` | 补充摘要指标 |

**现状诊断结果**：
- 早高峰最严重：TTT=1.93M, S=24.2M, 5条路段 V/C>0.75（3条 LOS=F）
- 主要瓶颈：桂苑宿舍出口（V/C=1.45）、16幢东西入口（V/C=1.27/1.07）

---

### step4 — 情景方案设计与对比

**做了什么**：设计三类治理方案，重跑 UE，对比效果。

**方案定义**：

| 方案 | 措施 | 技术实现 |
|---|---|---|
| **A** 关键桥梁单行线 | 南北主桥 + 东侧桥早高峰单向化 | 删除反向边 |
| **B** 午高峰食堂限行 | 食堂周边禁机动车 | capacity × 0.6，机动车需求 × 0.3 |
| **C** 综合优化 | A+B+人车隔离 | 单行线 + 限行 + 隔离路段冲突风险 × 0.4 |

**输出**：`output_step4/scenario_comparison.csv`

**结果**：
| 方案 | TTT 改善 | S 改善 |
|---|---|---|
| A 单行线 | +15.3% | +37.3% |
| B 限行 | ∼0% | ∼0% |
| **C 综合** | **+15.3%** | **+50.5%** ★ |

---

### step5 — K 短路径分流

**做了什么**：对 24 对重点 OD（3 教学楼 × 8 食堂/宿舍）用 Yen's Algorithm 构造 K=3 条备选路径，按广义费用分流。

**算法**：Yen's blocked-edge K-最短路径算法

广义费用：
\[
g = \theta_t \cdot T + \theta_d \cdot \frac{D}{1000} + \theta_r \cdot R
\]
其中 \(\theta = (0.40, 0.20, 0.30, 0.10)\)，\(R = 1/\text{width}\)

分流比例（Logit 型）：
\[
p_k = \frac{(1/g_k)^{\rho}}{\sum_j (1/g_j)^{\rho}},\quad \rho = 2.0
\]

**输出**：`output_step5/`
| 文件 | 含义 |
|---|---|
| `k_shortest_paths.csv` | 72 条路径记录（24OD × 3路径） |
| `path_report.txt` | 可读报告 |

---

### step6 — 效果评价

**做了什么**：汇总方案对比表，生成最终评价报告，选出最优方案。

**逻辑**：以 S（冲突风险）改善最大为标准选取最优方案。

**输出**：`output_step6/evaluation_report.txt`

**结论**：方案 C（综合优化）最优，TTT 改善 15.3%，S 改善 50.5%

---

### step7 — V/C 热力图可视化

**做了什么**：独立运行基准和方案 C 的 UE 分配，生成三时段的左右对比热力图。

**技术**：`matplotlib` + `kamada_kawai` 布局，边颜色按 V/C 从绿(A)→黄(C)→红(E)→深红(F) 映射，线宽与 V/C 成正比。

**节点标注**：所有建筑标注中文名称（16幢东/西入口、桃园宿舍、杏园食堂等），关键交叉口标注路口名（北桥、桃园路口等）。

**输出**：`output_step7/`
| 文件 | 内容 |
|---|---|
| `heatmap_morning.png` | 早高峰基准 vs 方案C |
| `heatmap_noon.png` | 午高峰基准 vs 方案C |
| `heatmap_evening.png` | 晚高峰基准 vs 方案C |

---

## 问题二：校园电动车环境承载力评估

### 数学模型

\[
\max N_{\max} = \sum_{i=1}^{n} N_i
\]

约束条件：

1. **静态面积约束**：\(N_i \leq \left\lfloor \frac{A_i^{eff}}{\beta \cdot a_e} \right\rfloor\)
2. **消防/路宽约束**：\(w_i - w_{park} \geq W_{left}^{\min}\)（消防≥4m / 主干道≥6m / 支路≥3m，消防一票否决）
3. **动态通行能力约束**：\(\alpha_i(t) \cdot N_i \leq C_i^{road},\;\forall i,\forall t\)

参数：\(a_e = 1.08\text{m}^2,\;\beta = 1.35,\;w_{park} = 0.8\text{m}\)

供需评价：
\[
\rho_i = \frac{D_i}{N_i^*},\quad \theta = \frac{\max_t \sum_i D_i(t)}{N_{\max}^*}
\]

---

### step8 — 功能区域划分

**做了什么**：将校园路网的 11 个建筑节点按功能归入 6 个区域，关联周边道路和交叉口。

**区域定义**：
| ID | 名称 | 建筑 | A_eff (m²) |
|---|---|---|---|
| Z1 | 16幢教学区 | T_16_E, T_16_W | 600 |
| Z2 | 25幢教学区 | T_25 | 300 |
| Z3 | 桃园生活区 | D_T, C_T | 800 |
| Z4 | 杏园生活区 | D_X, C_X | 900 |
| Z5 | 桂苑生活区 | D_C, D_G, C_G | 1200 |
| Z6 | 商业街 | C_S | 200 |

> A_eff 为暂估值，根据地图实测后可修改。

**输出**：`output_step8/`
| 文件 | 含义 |
|---|---|
| `zones.csv` | 区域总表（建筑、路口、路宽、A_eff） |
| `building_zone_map.csv` | 建筑→区域映射 |

---

### step9 — 静态容量（面积 + 消防/路宽）

**做了什么**：计算各区域纯面积上限 + 消防/路宽约束检查。

**计算**：
\[
N_i^{area} = \left\lfloor \frac{A_i^{eff}}{1.35 \times 1.08} \right\rfloor
\]

消防检查：对每个区域的周边路段，验证 \(w_i - 0.8 \geq W_{left}^{\min}\)。若任何路段不满足消防（<4m），该区域 \(N_i = 0\)。

**结果**：所有路段均满足消防约束（停车后剩余宽度 4.2m~7.2m > 4m），N_static = N_area。

**输出**：`output_step9/static_capacity.csv`

---

### step10 — 动态容量（潮汐通行能力）

**做了什么**：从 step3 UE 流量反推各区域周边道路的 e-bike 剩余通行能力。

**计算**：
\[
C_i^{road} = \frac{\max(0,\;capacity \times 0.85 - flow\_eq)}{0.30}
\]
\[
N_i^{dynamic}(t) = \frac{C_i^{road}}{\alpha_i(t)},\quad N_i^{dynamic} = \min_t N_i^{dynamic}(t)
\]

其中 \(\alpha_i(t)\) 为潮汐出行比例（早 0.90 / 午 1.00 / 晚 0.50），\(C_i^{road}\) 取瓶颈路段的剩余 e-bike 通行能力。

**输出**：`output_step10/dynamic_capacity.csv`

---

### step11 — 最终求解 + 供需评价

**做了什么**：取静态和动态约束的较小值，求各区域最优容量和校园总量，计算供需压力系数。

**求解**：
\[
N_i^* = \min(N_i^{static},\;N_i^{dynamic}),\quad N_{\max} = \sum_i N_i^*
\]

**需求估算**：\(D_i\) = 三时段中到达区域 \(i\) 的 e-bike 流量最大值（反映峰值停车数）

**最终结果**：

| 区域 | N_static | N_dynamic | **N\*** | D_i | ρ | 状态 |
|---|---|---|---|---|---|---|
| 16幢教学区 | 411 | 339 | **339** | 1284 | 3.79 | 超载 |
| 25幢教学区 | 205 | 25 | **25** | 770 | 30.79 | 超载 |
| 桃园生活区 | 548 | 635 | **548** | 726 | 1.33 | 超载 |
| 杏园生活区 | 617 | 987 | **617** | 412 | 0.67 | 充足 |
| 桂苑生活区 | 823 | 461 | **461** | 402 | 0.87 | 接近饱和 |
| 商业街 | 137 | 575 | **137** | 573 | 4.19 | 超载 |

```
N_max = 2,127 辆
整体饱和度 θ = 1.452（早高峰）
```

**输出**：`output_step11/`
| 文件 | 含义 |
|---|---|
| `final_capacity.csv` | 完整容量表 |
| `capacity_report.txt` | 正式评估报告 |

---

## 关键结论

### 问题一

1. 早高峰是校园交通最紧张时段，3 条路段过饱和（LOS=F）
2. 方案 C（单行线+限行+人车隔离）为最优方案：**TTT -15.3%, S -50.5%**
3. 方案 B（午高峰限机动车）基本无效——机动车仅占总流量 6%
4. 24 对重点 OD 已建立 K=3 路径分流方案

### 问题二

1. 校园最大电动车容量 **N_max = 2,127 辆**
2. 早高峰是最紧张时段，实时需求 3,087 辆，**θ = 1.452 > 1**
3. **25幢是最大瓶颈**：静态容量 205 → 动态约束压至 25 辆（-88%）
4. 教学区停车严重不足（16幢 ρ=3.79, 25幢 ρ=30.79）
5. 杏园生活区尚有富余（ρ=0.67），可作需求转移方向

---

## 如何修改参数

| 参数 | 所在文件 | 位置 |
|---|---|---|
| A_eff（有效停车面积） | `step8_zones.py` | `ZONES` 字典 |
| β（停车通道系数） | `step9_static.py` | `beta = 1.35` |
| w_park（停车占用宽度） | `step9_static.py` | `w_park = 0.8` |
| α_i(t)（潮汐比例） | `step10_dynamic.py` | `ALPHA_DEFAULT` / `ALPHA_OVERRIDE` |
| SAT_LIMIT（饱和度上限） | `step10_dynamic.py` | `SAT_LIMIT = 0.85` |

修改后从对应步骤开始重跑即可，下游步骤会自动同步。
