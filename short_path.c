#include <stdio.h>
#include <string.h>
#include <limits.h>

#define MAXN 3005

int g[MAXN][MAXN];
int dist[MAXN], vis[MAXN];
int n, m, s, t;

// dist[i]: 从起点s到顶点i的当前最短距离，初始为INT_MAX表示无穷大
// vis[i]:  标记顶点i是否已确定最短距离，0表示未确定，1表示已确定

void dijkstra()
{
    for (int i = 1; i <= n; i++)
    { // 初始化距离数组和访问标记
        dist[i] = INT_MAX;
        vis[i] = 0;
    }
    dist[s] = 0;

    for (int i = 1; i <= n; i++)
    { // 控制算法的轮次，确保每个节点都被加入
        int a = -1;
        int minDis = INT_MAX;
        for (int j = 1; j <= n; j++)
        { // 在剩余未处理节点中，寻找当前距离源点最近的那个点
            if (!vis[j] && dist[j] < minDis)
            {
                minDis = dist[j];
                a = j;
            }
        }

        if (a == -1)
            break;
        vis[a] = 1;

        for (int i = 1; i <= n; i++)
        { // 更新邻居的距离
            if (!vis[i] && g[a][i] != 0 && dist[a] != INT_MAX && dist[a] + g[a][i] < dist[i])
            {
                dist[i] = dist[a] + g[a][i];
            }
        }
    }
}

int main()
{
    scanf("%d %d %d %d", &n, &m, &s, &t);
    // n: 顶点数量（点数）
    // m: 边的数量
    // s: 起点编号
    // t: 终点编号

    memset(g, 0, sizeof(g));

    for (int i = 0; i < m; i++)
    {
        int u, v, w;
        scanf("%d %d %d", &u, &v, &w);
        g[u][v] = w;
        g[v][u] = w;
    }

    dijkstra();

    printf("%d\n", dist[t]);

    return 0;
}
