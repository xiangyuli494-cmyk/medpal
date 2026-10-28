# env.md 环境踩坑文档（WSL2 + Docker Desktop）
> 适用：T6 W1 任务，WSL2 + Docker Desktop 部署 Nexent 环境踩坑记录

## 1. 代理拦截回环地址问题
### 现象
WSL2 内部配置全局代理后，访问 `127.0.0.1` / `localhost` 回环地址被代理转发，请求超时、连接失败，Docker 容器本地互通、本地控制台访问异常。

### 根因
代理软件默认接管全部流量，没有豁免回环网段。WSL2 的 localhost 转发机制 + 系统代理叠加后，本地流量被向外转发。

### 解决方案
1. 在代理软件的分流规则中添加豁免：`127.0.0.1/8`、`::1`
2. WSL2 内环境变量 NO_PROXY 追加回环：
```bash
export NO_PROXY="localhost,127.0.0.1,::1"
