"""
步骤七：V/C 热力图（v2 — 新路网 N1-N64）
=========================================
独立运行基准和方案 C 的 UE 分配，生成三时段对比热力图。
"""

import networkx as nx, numpy as np, pandas as pd, os, math, heapq
from collections import defaultdict
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.lines import Line2D

fm._load_fontmanager(try_read_cache=False)
_cjk = [f.name for f in fm.fontManager.ttflist if f.name in ('STHeiti','Heiti TC','PingFang HK')]
if _cjk:
    plt.rcParams['font.sans-serif'] = [_cjk[0]] + plt.rcParams['font.sans-serif']
    plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

STEP1_DIR="output_step1"; STEP2_DIR="output_step2"
OUTPUT_DIR="output_step7"; os.makedirs(OUTPUT_DIR, exist_ok=True)

ALPHA,BETA=0.15,4.0; XI={'p':0.10,'b':0.30,'c':1.00}
V_FREE={'p':1.39,'b':4.17,'c':5.56}
MODES=['p','b','c']; PERIODS=['morning','noon','evening']
FW_MAX=20

# 建筑中文标签
BUILDING_LABEL = {
    'T_16':'16幢','T_25':'25幢',
    'T_1':'T1','T_2':'T2','T_3':'T3','T_4':'T4','T_5':'T5',
    'T_6':'T6','T_7':'T7','T_8':'T8','T_9':'T9','T_10':'T10',
    'TYGY':'桃园\n公寓','TYST':'桃园\n食堂',
    'XYGY':'杏园\n公寓','XYST':'杏园\n食堂',
    'GYGY':'桂苑\n公寓','GYST':'桂苑\n食堂','CYGY':'初阳\n公寓',
    'SYJ':'商业街',
}

# ════════════ 核心函数 ════════════
def bpr_cost(t0,cap,flow):
    if cap<=0: return t0*10
    return t0*(1+ALPHA*(flow/cap)**BETA)

def dijkstra(source,adj,eattr,cost_func):
    dist={source:0.0}; prev={}; heap=[(0.0,source)]
    while heap:
        d,u=heapq.heappop(heap)
        if d>dist.get(u,math.inf): continue
        for v,eid in adj.get(u,[]):
            nd=d+cost_func(eid)
            if nd<dist.get(v,math.inf):
                dist[v]=nd;prev[v]=u;heapq.heappush(heap,(nd,v))
    return dist,prev

def get_path(prev,src,dst):
    if dst not in prev: return None
    path=[dst];cur=dst
    while cur!=src: cur=prev[cur];path.append(cur)
    return path[::-1]

def assign_aon(od,adj,eattr,eid_map,x_eq):
    aon_mode=defaultdict(float)
    for (src,dst,mode),demand in od.items():
        if demand<=0 or src not in adj or dst not in adj: continue
        def cf(eid):
            a=eattr[eid];return bpr_cost(a['t0'][mode],a['capacity'],x_eq.get(eid,0))
        dist,prev=dijkstra(src,adj,eattr,cf)
        path=get_path(prev,src,dst)
        if path is None: continue
        for i in range(len(path)-1):
            eid=eid_map.get((path[i],path[i+1]))
            if eid is not None: aon_mode[(eid,mode)]+=demand
    aon_eq=defaultdict(float)
    for (eid,mode),flow in aon_mode.items(): aon_eq[eid]+=XI[mode]*flow
    return dict(aon_eq),dict(aon_mode)

def frank_wolfe(od,adj,eattr,eid_map):
    x_eq_zero={eid:0.0 for eid in eattr}
    aux_eq0,aux_mode0=assign_aon(od,adj,eattr,eid_map,x_eq_zero)
    x_mode=defaultdict(float,aux_mode0);x_eq=defaultdict(float,aux_eq0)
    prev_obj=math.inf
    for it in range(FW_MAX):
        obj=0.0
        for eid in eattr:
            a=eattr[eid];obj+=bpr_cost(a['t0']['p'],a['capacity'],x_eq.get(eid,0))
        y_eq,y_mode=assign_aon(od,adj,eattr,eid_map,x_eq)
        lo,hi=0.0,1.0
        for _ in range(20):
            lam=(lo+hi)/2;grad=0.0
            for eid in eattr:
                xe,ye=x_eq.get(eid,0),y_eq.get(eid,0)
                if abs(ye-xe)<1e-10:continue
                xnew=max(xe+lam*(ye-xe),0);a=eattr[eid]
                grad+=bpr_cost(a['t0']['p'],a['capacity'],xnew)*(ye-xe)
            if grad>0:hi=lam
            else:lo=lam
        lam_opt=(lo+hi)/2
        new_x_mode=defaultdict(float)
        for k in set(x_mode)|set(y_mode):
            v=x_mode.get(k,0)+lam_opt*(y_mode.get(k,0)-x_mode.get(k,0))
            if v>0:new_x_mode[k]=v
        new_x_eq=defaultdict(float)
        for eid in eattr:
            v=x_eq.get(eid,0)+lam_opt*(y_eq.get(eid,0)-x_eq.get(eid,0))
            if v>0:new_x_eq[eid]=v
        x_mode,x_eq=new_x_mode,new_x_eq
        rel=abs(obj-prev_obj)/(abs(prev_obj)+1e-10)
        if rel<1e-4 and it>5:break
        prev_obj=obj
    return dict(x_mode),dict(x_eq)

# ════════════ 建图 ════════════
def build_adj_eattr(G):
    adj=defaultdict(list);eid_map={};eattr={}
    for eid,(u,v,data) in enumerate(G.edges(data=True)):
        L=float(data['length']);cap=float(data['capacity'])
        eattr[eid]={'u':u,'v':v,'length':L,'capacity':cap,'t0':{m:L/V_FREE[m] for m in MODES}}
        adj[u].append((v,eid));eid_map[(u,v)]=eid
    return adj,eid_map,eattr

def load_od(period):
    od={}
    for mode in MODES:
        fp=os.path.join(STEP2_DIR,f"od_{period}_{mode}.csv")
        if not os.path.exists(fp):continue
        df=pd.read_csv(fp,index_col=0)
        for src in df.index:
            for dst in df.columns:
                v=float(df.loc[src,dst])
                if v>0.01:od[(src,dst,mode)]=v
    return od

def apply_scenario_c(G,period):
    G_mod=G.copy()
    if period=='morning':
        for u,v in [('N4','N14'),('N30','N16'),('N46','N49')]:
            if G_mod.has_edge(v,u):G_mod.remove_edge(v,u)
    if period=='noon':
        for u,v in [('N14','N15'),('N14','N4'),('N14','N6'),
                    ('N30','N12'),('N28','N12'),('N28','N29'),
                    ('N29','N31'),('N31','N32')]:
            if G_mod.has_edge(u,v):
                G_mod[u][v]['capacity']=float(G_mod[u][v]['capacity'])*0.6
        # 降机动车需求在 load_od 时处理
    iso_pairs=SCENARIO_C_ISO
    iso=set()
    for u,v in iso_pairs:
        if G_mod.has_edge(u,v):iso.add((u,v))
        if G_mod.has_edge(v,u):iso.add((v,u))
    return G_mod,iso

SCENARIO_C_ISO = [
    ('N4','N14'),('N14','N15'),('N15','N16'),('N30','N16'),
    ('N28','N29'),('N28','N31'),('N33','N34'),('N33','N46'),
    ('N46','N49'),('N49','N48'),('N37','N47'),('N48','N38'),
    ('N33','N61'),('N61','N62'),
]

def run_assignment(period,scenario_c=False):
    G0=nx.read_gml(os.path.join(STEP1_DIR,"campus_graph.gml"))
    if scenario_c:
        G,iso=apply_scenario_c(G0,period)
    else:
        G=G0;iso=set()
    adj,eid_map,eattr=build_adj_eattr(G)
    od=load_od(period)
    if scenario_c and period=='noon':
        new_od={}
        for (s,d,m),v in od.items():
            new_od[(s,d,m)]=v*0.3 if m=='c' else v
        od=new_od
    x_mode,x_eq=frank_wolfe(od,adj,eattr,eid_map)
    vc={}
    for eid,a in eattr.items():
        vc[(a['u'],a['v'])]=x_eq.get(eid,0)/a['capacity'] if a['capacity']>0 else 0
    return G,vc

# ════════════ 布局 ════════════
def compute_layout(G):
    try:
        pos=nx.kamada_kawai_layout(G.to_undirected())
    except: pos=nx.spring_layout(G,seed=42,k=2.0,iterations=300)
    scale=2.5
    for n in pos:pos[n]=(pos[n][0]*scale,pos[n][1]*scale)
    for n in G.nodes():
        if G.nodes[n].get('type','')!='交叉口':
            x,y=pos[n];pos[n]=(x*1.08,y*1.08)
    return pos

# ════════════ 画图 ════════════
def vc_color(vc):
    if vc<=0.35:return(0.18,0.72,0.18,0.9)
    elif vc<=0.55:return(0.50,0.85,0.18,0.9)
    elif vc<=0.75:return(0.92,0.78,0.10,0.9)
    elif vc<=0.90:return(0.95,0.45,0.08,0.9)
    elif vc<=1.00:return(0.88,0.12,0.05,0.95)
    else:return(0.65,0.0,0.0,1.0)

def draw_heatmap(ax,G,pos,vc_by_edge,title,is_left=True):
    ax.set_title(title,fontsize=13,fontweight='bold',pad=8)
    ax.axis('off');ax.set_xlim(-3.5,3.5);ax.set_ylim(-3.5,3.5)
    for u,v in G.edges():
        if (u,v) not in vc_by_edge:continue
        vc=vc_by_edge[(u,v)]
        ax.plot([pos[u][0],pos[v][0]],[pos[u][1],pos[v][1]],
                color=vc_color(vc),linewidth=0.8+5.0*min(vc,1.5),alpha=0.8,zorder=1)
    buildings={n for n in G.nodes() if G.nodes[n].get('type','')!='交叉口'}
    for n in G.nodes():
        if n in buildings:
            x,y=pos[n];nm=G.nodes[n].get('type','')
            c={'教学楼':'#E74C3C','宿舍':'#3498DB','食堂':'#27AE60','建筑':'#27AE60'}.get(nm,'#888')
            ax.scatter(x,y,s=160,c=c,edgecolors='white',linewidth=1.5,zorder=5)
            label=BUILDING_LABEL.get(n,n)
            ax.annotate(label,(x,y),textcoords="offset points",xytext=(0,-16),
                fontsize=7.5,ha='center',color='#222',fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3',facecolor='white',alpha=0.85),zorder=6)
        else:
            ax.scatter(pos[n][0],pos[n][1],s=8,c='#CCCCCC',zorder=2)
    legend_vc=[Line2D([0],[0],color=vc_color(x),lw=3,label=l)
               for x,l in [(0.2,'A ≤0.35'),(0.45,'B'),(0.65,'C'),(0.85,'D'),(0.95,'E'),(1.3,'F >1.00')]]
    if is_left:ax.legend(handles=legend_vc,loc='lower left',fontsize=6.5,framealpha=0.85,title='V/C')

# ════════════ 主流程 ════════════
period_names={'morning':'早高峰','noon':'午高峰','evening':'晚高峰'}
G_base=nx.read_gml(os.path.join(STEP1_DIR,"campus_graph.gml"))
pos=compute_layout(G_base)

for period in PERIODS:
    print(f"{period} ...")
    G_b,vc_b=run_assignment(period,False)
    G_s,vc_s=run_assignment(period,True)
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(24,11),facecolor='white')
    draw_heatmap(ax1,G_b,pos,vc_b,f'基准 — {period_names[period]}',True)
    draw_heatmap(ax2,G_s,pos,vc_s,f'方案C — {period_names[period]}',False)
    plt.suptitle(f'校园路网 V/C 热力图 | {period_names[period]}',fontsize=16,fontweight='bold',y=0.99)
    plt.tight_layout(rect=[0,0.02,1,0.93])
    out=os.path.join(OUTPUT_DIR,f"heatmap_{period}.png")
    plt.savefig(out,dpi=200,bbox_inches='tight',facecolor='white');plt.close()
    print(f"  → {out}")

print(f"\n全部完成: {OUTPUT_DIR}/")
