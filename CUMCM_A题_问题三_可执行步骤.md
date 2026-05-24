# CUMCM A题 问题三可执行步骤

> 题目：浙师大校园“微交通”系统的综合治理与优化设计  
> 问题三：校园微公交（接驳车）路线规划、站点选址与潮汐调度模型

---

## 0. 问题三的定位

问题三不是孤立设计一条公交线，而是承接问题一、问题二的结果，进一步解决校园私人电动车依赖过高的问题。

前两问已经得到：

1. 校园路网为 60 个节点、152 条有向边；
2. 问题一综合优化方案 C 可使总行程时间 TTT 改善 15.3%，人车冲突风险 S 改善 50.5%；
3. 问题二得到校园电动车最大容量：

\[
N_{\max}=2127
\]

4. 早高峰电动车需求约为：

\[
D_{bike}=3087
\]

5. 校园整体电动车饱和度：

\[
\theta=1.452>1
\]

说明校园电动车已经明显超载。因此问题三的核心目标是：

> 通过设计校园接驳车系统，替代一部分私人电动车出行需求，缓解宿舍区、教学区、食堂区之间的潮汐交通压力。

---

## 1. 总体执行流程

问题三建议按以下流程执行：

```text
Step 12  提取第三问基础数据
Step 13  构造候选站点集合
Step 14  计算站点覆盖关系与适宜性
Step 15  建立最大覆盖站点选址模型
Step 16  构造候选接驳线路
Step 17  计算线路广义成本并选线
Step 18  识别接驳车替代需求
Step 19  建立潮汐客流调度模型
Step 20  计算车辆投放量与发车间隔
Step 21  反馈评价接驳车对路网和电动车压力的改善效果
```

为了与前两问代码衔接，建议从 `step12` 开始编号。

---

# Step 12：提取第三问基础数据

## 12.1 输入文件

第三问需要复用前两问的输出数据。

| 来源 | 文件 | 用途 |
|---|---|---|
| step1 | `output_step1/campus_graph.gml` | 读取校园路网拓扑 |
| step1 | `output_step1/distance_matrix.csv` | 计算站点覆盖距离 |
| step2 | `output_step2/od_morning_total.csv` | 早高峰总 OD |
| step2 | `output_step2/od_noon_total.csv` | 午高峰总 OD |
| step2 | `output_step2/od_evening_total.csv` | 晚高峰总 OD |
| step2 | `output_step2/od_morning_ebike.csv` | 早高峰电动车 OD |
| step2 | `output_step2/od_noon_ebike.csv` | 午高峰电动车 OD |
| step2 | `output_step2/od_evening_ebike.csv` | 晚高峰电动车 OD |
| step3 | `output_step3/link_flow_morning.csv` | 早高峰路段 V/C 与风险 |
| step3 | `output_step3/link_flow_noon.csv` | 午高峰路段 V/C 与风险 |
| step3 | `output_step3/link_flow_evening.csv` | 晚高峰路段 V/C 与风险 |
| step8 | `output_step8/zones.csv` | 功能区信息 |
| step11 | `output_step11/final_capacity.csv` | 各区域电动车容量与压力 |

## 12.2 需要整理出的数据表

建议生成：

```text
output_step12/base_data_summary.csv
```

字段包括：

| 字段 | 含义 |
|---|---|
| node_id | 节点编号 |
| node_name | 节点名称 |
| zone_id | 所属区域 |
| zone_type | 区域类型，教学区/宿舍区/食堂区/商业区 |
| demand_morning | 早高峰相关需求 |
| demand_noon | 午高峰相关需求 |
| demand_evening | 晚高峰相关需求 |
| ebike_pressure | 电动车停车压力系数 |
| nearest_vc | 周边道路最大 V/C |
| nearest_risk | 周边道路冲突风险 |

---

# Step 13：构造候选站点集合

## 13.1 候选站点原则

接驳车站点不应随意设置，需要满足：

1. 靠近主要需求点；
2. 与建筑入口保持适当步行距离；
3. 附近道路宽度较大；
4. 不设置在 V/C 过高的瓶颈路段；
5. 不占用消防通道；
6. 停靠时不显著阻碍主干道交通。

## 13.2 推荐候选站点

结合前两问结果，候选站点建议包括：

| 候选站点 | 服务对象 | 设置理由 |
|---|---|---|
| 桂苑生活区站 | 桂苑宿舍、桂苑食堂 | 早高峰出发需求大 |
| 桃园生活区站 | 桃园宿舍、桃园食堂 | 宿舍和食堂复合需求 |
| 杏园生活区站 | 杏园宿舍、杏园食堂 | 电动车容量相对充足，可分担停车压力 |
| 16幢教学区站 | 16幢东/西入口 | 早高峰瓶颈，停车压力高 |
| 25幢教学区站 | 25幢 | 最大停车瓶颈 |
| 商业街站 | 商业街、周边餐饮 | 午晚高峰目的地集中 |
| 校门站 | 校门及外部出行 | 可选，用于连接校外交通 |

## 13.3 输出文件

建议生成：

```text
output_step13/candidate_stops.csv
```

字段：

| 字段 | 含义 |
|---|---|
| stop_id | 候选站点编号 |
| stop_name | 站点名称 |
| nearest_node | 对应路网节点 |
| zone_id | 所属区域 |
| width | 附近道路宽度 |
| vc_morning | 早高峰附近 V/C |
| risk_morning | 早高峰附近风险 |
| can_stop | 是否允许停靠 |

---

# Step 14：计算站点覆盖关系与适宜性

## 14.1 覆盖关系

设：

- \(I\)：需求点集合；
- \(J\)：候选站点集合；
- \(d_{ij}\)：需求点 \(i\) 到候选站点 \(j\) 的最短步行距离；
- \(R_0\)：最大可接受步行距离。

建议取：

\[
R_0=200\text{m}
\]

定义覆盖矩阵：

\[
a_{ij}=\begin{cases}
1, & d_{ij}\leq R_0 \\
0, & d_{ij}>R_0
\end{cases}
\]

## 14.2 站点适宜性

站点不能只看距离，还要考虑是否安全、是否会加重拥堵。

定义候选站点 \(j\) 的适宜性系数：

\[
\phi_j=
\omega_1\frac{w_j}{w_{\max}}
+\omega_2\left(1-\frac{v_j}{v_{\max}}\right)
+\omega_3\left(1-\frac{S_j}{S_{\max}}\right)
\]

其中：

| 符号 | 含义 |
|---|---|
| \(w_j\) | 站点附近道路宽度 |
| \(v_j\) | 站点附近道路饱和度 V/C |
| \(S_j\) | 站点附近人车冲突风险 |
| \(\omega_1,\omega_2,\omega_3\) | 权重 |

建议权重：

\[
\omega_1=0.4,\quad \omega_2=0.3,\quad \omega_3=0.3
\]

若：

\[
\phi_j<\phi_{\min}
\]

则该站点不适合作为接驳车站点。

建议取：

\[
\phi_{\min}=0.5
\]

## 14.3 输出文件

建议生成：

```text
output_step14/stop_coverage.csv
output_step14/stop_suitability.csv
```

---

# Step 15：建立最大覆盖站点选址模型

## 15.1 决策变量

\[
y_j=\begin{cases}
1, & \text{选择候选站点 }j \\
0, & \text{不选择候选站点 }j
\end{cases}
\]

\[
z_i=\begin{cases}
1, & \text{需求点 }i\text{ 被至少一个站点覆盖} \\
0, & \text{否则}
\end{cases}
\]

## 15.2 目标函数

最大化覆盖需求：

\[
\max Z_1=\sum_{i\in I}D_i z_i
\]

其中 \(D_i\) 为需求点 \(i\) 的潜在接驳需求。

## 15.3 约束条件

### 覆盖约束

\[
z_i\leq \sum_{j\in J}a_{ij}y_j,\quad \forall i\in I
\]

### 站点数量约束

\[
\sum_{j\in J}y_j\leq B_{\max}
\]

建议：

\[
B_{\max}=5\sim 7
\]

### 最低覆盖率约束

\[
\frac{\sum_{i\in I}D_i z_i}{\sum_{i\in I}D_i}\geq P_{\min}
\]

建议：

\[
P_{\min}=0.85
\]

### 站点适宜性约束

\[
y_j=0,\quad \text{if }\phi_j<\phi_{\min}
\]

## 15.4 求解方法

由于候选站点数量较少，可以采用：

1. 枚举法；
2. 整数规划；
3. 贪心算法。

比赛论文中推荐使用整数规划表达，代码中可用枚举或贪心实现。

## 15.5 输出文件

```text
output_step15/selected_stops.csv
```

字段：

| 字段 | 含义 |
|---|---|
| stop_id | 站点编号 |
| stop_name | 站点名称 |
| covered_demand | 覆盖需求 |
| suitability | 适宜性系数 |
| selected | 是否选中 |

---

# Step 16：构造候选接驳线路

## 16.1 推荐线路类型

建议构造三类候选线路：

### 线路 A：单环线

适合覆盖全校主要区域。

```text
桂苑生活区 → 桃园生活区 → 16幢 → 25幢 → 商业街/食堂 → 杏园生活区 → 桂苑生活区
```

### 线路 B：教学生活潮汐线

适合早高峰和晚高峰。

早高峰方向：

```text
桂苑/桃园/杏园生活区 → 16幢 → 25幢
```

午晚高峰方向：

```text
25幢 → 16幢 → 食堂/商业街 → 宿舍区
```

### 线路 C：教学—食堂短驳线

适合午高峰。

```text
25幢 → 16幢 → 商业街/食堂区 → 桃园/杏园食堂
```

## 16.2 线路构造方法

对每条候选线路，根据选中站点序列，在路网中逐段求最短时间路径。

对于相邻站点 \((s_k,s_{k+1})\)，计算：

\[
P_{k,k+1}=\operatorname{ShortestPath}(s_k,s_{k+1})
\]

整条线路为：

\[
P_r=\bigcup_k P_{k,k+1}
\]

其中最短路权重不建议只用距离，而应使用问题一中的 BPR 通行时间：

\[
t_e(x_e)=t_e^0\left[1+0.15\left(\frac{x_e}{C_e}\right)^4\right]
\]

## 16.3 输出文件

```text
output_step16/candidate_routes.csv
output_step16/route_paths.csv
```

字段：

| 字段 | 含义 |
|---|---|
| route_id | 线路编号 |
| route_type | 环线/往返线/短驳线 |
| stop_sequence | 站点序列 |
| path_nodes | 实际经过路网节点 |
| length_m | 线路长度 |
| travel_time_min | 运行时间 |

---

# Step 17：计算线路广义成本并选线

## 17.1 线路运行时间

线路 \(r\) 的单圈运行时间为：

\[
\tau_r=\sum_{e\in r}t_e(x_e)+\sum_{j\in S_r}\delta_j
\]

其中：

| 符号 | 含义 |
|---|---|
| \(t_e(x_e)\) | 路段拥堵通行时间 |
| \(S_r\) | 线路经过的站点集合 |
| \(\delta_j\) | 单站停靠时间 |

建议取：

\[
\delta_j=0.5\text{min}
\]

## 17.2 线路广义成本

定义线路广义成本：

\[
G_r=
\alpha_1\frac{L_r}{L_{\max}}
+\alpha_2\frac{\tau_r}{\tau_{\max}}
+\alpha_3\frac{\overline{v}_r}{v_{\max}}
+\alpha_4\frac{\overline{S}_r}{S_{\max}}
-\alpha_5\frac{P_r}{P_{\max}}
\]

其中：

| 符号 | 含义 |
|---|---|
| \(L_r\) | 线路长度 |
| \(\tau_r\) | 线路单圈时间 |
| \(\overline{v}_r\) | 线路平均 V/C |
| \(\overline{S}_r\) | 线路平均冲突风险 |
| \(P_r\) | 线路覆盖客流 |

建议权重：

\[
\alpha_1=0.2,\quad
\alpha_2=0.3,\quad
\alpha_3=0.2,\quad
\alpha_4=0.2,\quad
\alpha_5=0.1
\]

注意：覆盖客流越大越好，所以最后一项为负号。

## 17.3 选线目标

若选一条主线：

\[
\min G_r
\]

若选多条线路：

\[
\min \sum_{r\in R}G_ru_r
\]

约束：

\[
\sum_{r\in R}u_r=m
\]

其中 \(m\) 为线路数量。

## 17.4 输出文件

```text
output_step17/route_evaluation.csv
output_step17/selected_routes.csv
```

---

# Step 18：识别接驳车替代需求

## 18.1 基于电动车超载量估算

问题二中：

\[
N_{\max}=2127
\]

早高峰电动车需求为：

\[
D_{bike}=3087
\]

因此超载需求为：

\[
D_{over}=D_{bike}-N_{\max}=960
\]

若设微公交承担其中比例 \(\eta\)，则：

\[
D_{bus}=\eta D_{over}
\]

建议设置三种情景：

| 情景 | 微公交承担比例 | 早高峰接驳需求 |
|---|---:|---:|
| 保守情景 | 40% | 384 人次 |
| 基准情景 | 50% | 480 人次 |
| 积极情景 | 60% | 576 人次 |

## 18.2 基于 Logit 的方式转移模型

为增强模型严谨性，可进一步用 Logit 模型计算电动车转移到接驳车的比例。

电动车广义成本：

\[
C_{od}^{b}=T_{od}^{b}+\mu_1\rho_d+\mu_2R_{od}
\]

接驳车广义成本：

\[
C_{od}^{s}=T_{walk,o}+W_t+T_{ride,od}+T_{walk,d}+F
\]

转移到接驳车的概率：

\[
P_{od}^{s,t}=\frac{\exp(-\theta C_{od}^{s,t})}
{\exp(-\theta C_{od}^{s,t})+\exp(-\theta C_{od}^{b,t})}
\]

接驳车客流：

\[
Q_{od}^{s,t}=P_{od}^{s,t}Q_{od}^{t}
\]

全时段接驳需求：

\[
D_s^t=\sum_{od}Q_{od}^{s,t}
\]

如果时间紧，可以先用 40%/50%/60% 情景估算；如果要增强论文质量，再加入 Logit 模型。

## 18.3 输出文件

```text
output_step18/bus_demand_scenarios.csv
output_step18/mode_shift_result.csv
```

---

# Step 19：建立潮汐客流调度模型

## 19.1 潮汐方向设定

| 时段 | 主方向 | 说明 |
|---|---|---|
| 早高峰 | 宿舍区 → 教学区 | 桂苑、桃园、杏园到 16幢、25幢 |
| 午高峰 | 教学区 → 食堂区/宿舍区 | 16幢、25幢到食堂、商业街、宿舍 |
| 晚高峰 | 教学区 → 食堂区/宿舍区/校门 | 目的地更加分散 |

## 19.2 运能约束

设：

| 符号 | 含义 |
|---|---|
| \(D_s^t\) | 时段 \(t\) 的接驳需求 |
| \(K\) | 单车载客量 |
| \(n_t\) | 时段 \(t\) 投放车辆数 |
| \(H_t\) | 时段 \(t\) 持续时间 |
| \(\tau_r\) | 线路单圈时间 |

则接驳车在时段 \(t\) 的总运能为：

\[
Q_{cap}^t=n_tK\frac{H_t}{\tau_r}
\]

必须满足：

\[
n_tK\frac{H_t}{\tau_r}\geq D_s^t
\]

因此最小车辆数为：

\[
n_t^{\min}=\left\lceil\frac{D_s^t\tau_r}{KH_t}\right\rceil
\]

## 19.3 发车间隔

发车间隔为：

\[
h_t=\frac{\tau_r}{n_t}
\]

平均等待时间：

\[
W_t=\frac{h_t}{2}
\]

服务质量约束：

\[
h_t\leq h_{\max}
\]

建议：

\[
h_{\max}=10\text{min}
\]

## 19.4 成本目标函数

综合车辆运营成本、乘客等待成本和运能浪费成本：

\[
\min Z_2=\sum_{t\in T}\left[c_vn_tH_t+c_wD_s^t\frac{h_t}{2}+c_o\max(0,Q_{cap}^t-D_s^t)\right]
\]

约束：

\[
n_tK\frac{H_t}{\tau_r}\geq D_s^t,\quad \forall t
\]

\[
h_t=\frac{\tau_r}{n_t},\quad \forall t
\]

\[
h_t\leq h_{\max},\quad \forall t
\]

\[
1\leq n_t\leq M_t,\quad n_t\in\mathbb{Z}_+
\]

---

# Step 20：计算车辆投放量与发车间隔

## 20.1 推荐参数

| 参数 | 建议值 | 说明 |
|---|---:|---|
| \(K\) | 12 人/车 | 小型接驳车容量 |
| \(H_{morning}\) | 45 min | 7:30-8:15 |
| \(H_{noon}\) | 50 min | 11:40-12:30 |
| \(H_{evening}\) | 40 min | 17:20-18:00 |
| \(\tau_r\) | 12-18 min | 根据线路计算得到 |
| \(h_{max}\) | 10 min | 最大可接受发车间隔 |
| \(\delta_j\) | 0.5 min | 单站停靠时间 |

## 20.2 示例计算

以基准情景为例，早高峰微公交承担 50% 超载需求：

\[
D_s^{morning}=480
\]

若：

\[
K=12,\quad H=45\text{min},\quad \tau_r=15\text{min}
\]

则：

\[
n_{morning}^{\min}=\left\lceil\frac{480\times15}{12\times45}\right\rceil=14
\]

如果采用两条线路分担，则每条线路约需 7 辆。

发车间隔：

\[
h=\frac{15}{7}\approx2.14\text{min}
\]

说明早高峰需要高频短驳。

## 20.3 输出文件

```text
output_step20/bus_schedule.csv
```

字段：

| 字段 | 含义 |
|---|---|
| period | 时段 |
| route_id | 线路编号 |
| direction | 主方向 |
| demand | 接驳需求 |
| vehicles | 投放车辆数 |
| headway_min | 发车间隔 |
| capacity | 时段运能 |
| load_factor | 满载率 |

---

# Step 21：反馈评价改善效果

## 21.1 电动车需求削减

接驳车替代后，电动车需求变为：

\[
D_{bike}^{new,t}=D_{bike}^{old,t}-D_s^t
\]

新的电动车饱和度为：

\[
\theta^{new}=\frac{D_{bike}^{new,t}}{N_{\max}}
\]

以早高峰基准情景为例：

\[
D_{bike}^{new}=3087-480=2607
\]

\[
\theta^{new}=\frac{2607}{2127}=1.226
\]

相比原始饱和度：

\[
\theta=1.452
\]

改善率为：

\[
\Delta \theta=\frac{1.452-1.226}{1.452}\times100\%\approx15.6\%
\]

## 21.2 路网流量反馈

设接驳车替代了部分原电动车 OD，则路段电动车流量更新为：

\[
f_{e,b}^{new,t}=f_{e,b}^{old,t}-\sum_{od}Q_{od}^{s,t}\delta_{e,od}^{b}
\]

等效流量更新为：

\[
x_e^{new,t}=0.10f_{e,p}^{t}+0.30f_{e,b}^{new,t}+1.00f_{e,c}^{t}+\kappa_sf_{e,s}^{t}
\]

其中 \(\kappa_s\) 为接驳车 PCU 系数，建议取：

\[
\kappa_s=1.5\sim2.0
\]

## 21.3 重新计算 TTT 与冲突风险

新的总行程时间：

\[
TTT^{new}=\sum_e x_e^{new,t}t_e(x_e^{new,t})
\]

新的冲突风险：

\[
S^{new}=\sum_e
\left(
\omega_{pb}x_p x_b^{new}
+
\omega_{pc}x_p x_c
+
\omega_{bc}x_b^{new}x_c
\right)
\]

改善率：

\[
\Delta TTT=\frac{TTT^{old}-TTT^{new}}{TTT^{old}}\times100\%
\]

\[
\Delta S=\frac{S^{old}-S^{new}}{S^{old}}\times100\%
\]

## 21.4 输出文件

```text
output_step21/bus_effect_evaluation.csv
output_step21/bus_effect_report.txt
```

---

# 最终应输出的结果表

## 1. 站点选址结果表

| 站点 | 覆盖建筑 | 覆盖需求 | 适宜性 | 是否选中 |
|---|---|---:|---:|---|
| 桂苑生活区站 | 桂苑宿舍、桂苑食堂 | — | — | 是 |
| 桃园生活区站 | 桃园宿舍、桃园食堂 | — | — | 是 |
| 16幢教学区站 | 16幢东西入口 | — | — | 是 |
| 25幢教学区站 | 25幢 | — | — | 是 |
| 商业街站 | 商业街、食堂区 | — | — | 是 |

## 2. 线路规划结果表

| 线路 | 类型 | 站点序列 | 长度/m | 单圈时间/min | 覆盖率 |
|---|---|---|---:|---:|---:|
| R1 | 教学生活潮汐线 | 桂苑-桃园-16幢-25幢 | — | — | — |
| R2 | 教学食堂短驳线 | 25幢-16幢-商业街/食堂 | — | — | — |

## 3. 调度结果表

| 时段 | 主方向 | 接驳需求 | 投放车辆 | 发车间隔 | 运能 | 满载率 |
|---|---|---:|---:|---:|---:|---:|
| 早高峰 | 宿舍 → 教学区 | — | — | — | — | — |
| 午高峰 | 教学区 → 食堂/宿舍 | — | — | — | — | — |
| 晚高峰 | 教学区 → 食堂/宿舍/校门 | — | — | — | — | — |

## 4. 改善效果表

| 指标 | 接驳前 | 接驳后 | 改善率 |
|---|---:|---:|---:|
| 电动车峰值需求 | 3087 | 2607 | 15.5% |
| 电动车饱和度 | 1.452 | 1.226 | 15.6% |
| TTT | — | — | — |
| 冲突风险 S | — | — | — |
| 16幢停车压力 | 3.79 | — | — |
| 25幢停车压力 | 30.79 | — | — |

---

# 建议代码文件安排

建议在原项目后继续添加以下脚本：

```text
step12_prepare_bus_data.py       # 整理第三问基础数据
step13_candidate_stops.py        # 构造候选站点
step14_stop_coverage.py          # 计算覆盖矩阵和适宜性
step15_select_stops.py           # 站点选址
step16_candidate_routes.py       # 构造候选线路
step17_route_evaluation.py       # 线路评价与选线
step18_bus_demand.py             # 接驳需求识别与方式转移
step19_dispatch_model.py         # 潮汐调度模型
step20_schedule.py               # 车辆数和发车间隔计算
step21_bus_effect.py             # 效果反馈评价
```

---

# 论文写作建议

第三问论文正文可以按以下结构写：

```text
3.1 问题分析
3.2 接驳需求识别
3.3 站点选址模型
3.4 线路规划模型
3.5 潮汐客流调度模型
3.6 结果分析与方案评价
```

其中重点写清楚三件事：

1. 微公交需求来自哪里；
2. 站点和线路为什么这样选；
3. 投放多少车、多久一班、改善多少。

---

# 推荐结论表达

可以在问题三结尾这样总结：

> 基于电动车承载力评估结果，校园早高峰电动车需求超过环境承载上限约 960 人次。本文设计校园微公交系统，通过设置教学生活潮汐线与教学食堂短驳线，覆盖 16幢、25幢、桂苑、桃园、杏园和商业街等主要出行节点。在基准情景下，微公交承担 50% 的电动车超载转移需求，可将早高峰电动车需求由 3087 降至 2607，校园电动车饱和度由 1.452 降至 1.226，改善约 15.6%。进一步结合路网流量反馈，微公交可有效降低教学区周边电动车流量与人车冲突风险，是问题一综合路网优化方案和问题二总量控制政策的重要补充。
