# CUMCM A题 问题二 — PY 文件说明

> 校园电动车环境承载力评估  
> 4 个脚本，从区域划分到最终求解

---

## 数学模型

\[
\max N_{\max} = \sum_{i=1}^{n} N_i
\]

约束：
1. 静态面积：\(N_i \leq \lfloor A_i^{eff} / (\beta \cdot a_e) \rfloor\)
2. 消防/路宽：\(w_i - w_{park} \geq W_{left}^{\min}\)（消防≥4m/主干道≥6m/支路≥3m）
3. 动态通行能力：\(\alpha_i(t) \cdot N_i \leq C_i^{road},\;\forall i,\forall t\)

参数：\(a_e=1.08\text{m}^2,\;\beta=1.35,\;w_{park}=0.8\text{m}\)

---

## 文件清单

| 文件名 | 作用 | 核心算法 | 输入 | 输出 |
|---|---|---|---|---|
| **step8_zones.py** | 划分 6 个功能区域，建立建筑→区域→路段映射 | BFS 从建筑出发收集 2 跳内交叉口 | `output_step1/campus_graph.gml` | `output_step8/zones.csv`, `building_zone_map.csv` |
| **step9_static.py** | 计算各区域静态容量（面积 + 消防/路宽约束） | \(N_i^{area} = \lfloor A_i^{eff} / 1.458 \rfloor\) + 路宽分级检查 | `output_step1/` + `output_step8/` | `output_step9/static_capacity.csv` |
| **step10_dynamic.py** | 从 step3 UE 流量反推各区域动态通行能力约束 | \(C_i^{road} = \max(0, c\cdot0.85 - x_{eq})/0.30\) | `output_step3/` + `output_step8/` | `output_step10/dynamic_capacity.csv` |
| **step11_solve.py** | 求解 \(N_i^*\)、\(N_{\max}\)，计算供需压力系数 | \(N_i^* = \min(N_{static}, N_{dynamic})\) | `output_step9/` + `output_step10/` + `output_step2/` | `output_step11/final_capacity.csv`, `capacity_report.txt` |

---

## 各文件详细信息

### step8_zones.py

**做什么**：将 11 个建筑节点按功能归入 6 个区域，关联周边道路。

**区域定义**：

| ID | 名称 | 建筑 | A_eff (m²) |
|---|---|---|---|
| Z1 | 16幢教学区 | T_16_E, T_16_W | 600 |
| Z2 | 25幢教学区 | T_25 | 300 |
| Z3 | 桃园生活区 | D_T, C_T | 800 |
| Z4 | 杏园生活区 | D_X, C_X | 900 |
| Z5 | 桂苑生活区 | D_C, D_G, C_G | 1200 |
| Z6 | 商业街 | C_S | 200 |

**算法**：从每个建筑出发 BFS（最大 2 跳），收集相邻交叉口节点和路段。

> ⚠ A_eff 为暂估值，可根据实测地图在 `ZONES` 字典中修改。

---

### step9_static.py

**做什么**：计算纯面积上限 + 消防/路宽约束检查。

**公式**：
\[
N_i^{area} = \left\lfloor \frac{A_i^{eff}}{1.35 \times 1.08} \right\rfloor = \left\lfloor \frac{A_i^{eff}}{1.458} \right\rfloor
\]

**路宽检查**：对每个区域的周边路段，验证：
\[
w_i - 0.8 \geq W_{left}^{\min}
\]
其中消防通道≥4m、主干道≥6m、支路≥3m。若任何消防通道不满足 → \(N_i = 0\)（一票否决）。

**结果**：所有区域均通过约束（停车后剩余 4.2~7.2m > 4m），N_static = N_area = 2,741 辆。

---

### step10_dynamic.py

**做什么**：用 step3 的 UE 流量数据反推每个区域的潮汐通行能力约束。

**公式**：
\[
C_i^{road} = \frac{\max(0,\;\text{capacity} \times 0.85 - \text{flow\_eq})}{0.30}
\]
\[
N_i^{dynamic}(t) = \frac{C_i^{road}}{\alpha_i(t)},\quad N_i^{dynamic} = \min_t N_i^{dynamic}(t)
\]

其中 \(\alpha_i(t)\) 为潮汐出行比例（早 0.90 / 午 1.00 / 晚 0.50）。

**计算过程**：
1. 对每个区域，找出所有相邻路段
2. 逐路段计算剩余 e-bike 通行能力（取瓶颈路段的最小值）
3. 除以各时段潮汐比例，取三时段中最紧的约束

**关键发现**：
- Z2（25幢）：N_dynamic = 25（瓶颈：午高峰 T_25→J_47, V/C=0.837）
- Z5（桂苑）：N_dynamic = 461（瓶颈：早高峰 D_C→J_29, V/C=1.452，已过饱和）
- Z1（16幢）：N_dynamic = 339（瓶颈：早高峰 J_01→T_16_W, V/C=1.270）

---

### step11_solve.py

**做什么**：取静态和动态容量的较小值求最优解，计算供需压力系数。

**求解**：
\[
N_i^* = \min(N_i^{static},\;N_i^{dynamic}),\quad N_{\max} = \sum N_i^* = 2,127\;\text{辆}
\]

**需求估算**：
\(D_i\) = 三时段中到达区域 i 的 e-bike 最大流量（反映峰值停车数）

**最终结果**：

| 区域 | N_static | N_dynamic | **N\*** | D_i | ρ | 状态 |
|---|---|---|---|---|---|---|
| 16幢教学区 | 411 | 339 | **339** | 1284 | 3.79 | 超载 |
| 25幢教学区 | 205 | 25 | **25** | 770 | 30.79 | 超载 |
| 桃园生活区 | 548 | 635 | **548** | 726 | 1.33 | 超载 |
| 杏园生活区 | 617 | 987 | **617** | 412 | 0.67 | 充足 |
| 桂苑生活区 | 823 | 461 | **461** | 402 | 0.87 | 接近饱和 |
| 商业街 | 137 | 575 | **137** | 573 | 4.19 | 超载 |

**校园总体**：N_max = 2,127 辆，θ = 1.452（早高峰最差），建议实施总量控制。

**输出**：`final_capacity.csv` + `capacity_report.txt`
