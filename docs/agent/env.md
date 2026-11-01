# 环境踩坑与环境清单（WSL2 + Docker Desktop）

## 0 环境清单（实测值）

采集机器：T1 演示主机（Windows 11 + WSL2 + Docker Desktop），采集时间 2026-10-28 21:00–21:15。

| 项 | 值 | 采集命令 | 采集人 |
| ---- | ---- | ---- | ---- |
| WSL版本 | 3.0.3.0 | `wsl --version` | T1 |
| 内核版本 | 6.18.54.1-microsoft-standard-WSL2 | `uname -r` | T1 |
| Windows版本 | Windows 11 家庭版 26200.9711 | `winver` | T1 |
| Docker版本 | 29.9.2 (build a82e528)；Docker Desktop 4.96.3 | `docker --version` | T1 |
| docker compose版本 | v5.6.1 | `docker compose version` | T1 |
| Storage Driver | overlayfs | `docker info` | T1 |
| Docker Root Dir | /var/lib/docker | `docker info` | T1 |
| 可用磁盘 | E: 14 GB 可用 / 161 GB（已用 92%） | `df -h` | T1 |

> 第 11、12 行的意义：`Storage Driver=overlayfs` + `Docker Root Dir=/var/lib/docker` 说明数据落在 WSL 发行版自己的 ext4 上，**不在**跨 VHDX 的 9p/virtiofs 挂载点上。这两个值只要变成 `9p` 或 `/mnt/wsl/...`，就会命中 §1.3 的故障。判定命令：
>
> ```bash
> docker run --rm --privileged --pid=host --entrypoint /bin/sh \
>   ccr.ccs.tencentyun.com/nexent-hub/nexent-ubuntu-terminal:v2.7.0 \
>   -c 'nsenter -t 1 -m -u -n -i stat -f -c "fstype=%T" /var/lib/docker/volumes'
> # 期望 ext2/ext3/ext4；出现 9p 或 virtiofs 即命中 §1.3
> # 直接 wsl -d docker-desktop 进去 stat 会报 No such file or directory，原因见 §1.3
> ```

## 1 失败路径：装不起来时踩的坑

### 1.1 代理拦截回环地址

**现象**
WSL2 开启全局代理后，访问 localhost、127.0.0.1 超时失败；只设置 NO_PROXY 环境变量依然超时。

**根因**
仅环境变量 NO_PROXY 只能控制主动读取这个变量的程序；DNS 解析、socket 直连不受它控制，必须在代理软件分流规则里添加豁免。

**解决方案**
1. 在代理软件分流规则添加豁免：`127.0.0.1/8`、`::1`（不能只靠环境变量）
2. WSL2 内配置环境变量：
```bash
export NO_PROXY="localhost,127.0.0.1,::1,host.docker.internal"
```
3. Windows 主机侧（CMD 里执行）也要配置：

```
setx NO_PROXY "localhost,127.0.0.1,::1"
```

4. 验证命令：

```
curl -I http://127.0.0.1:3000
curl -I http://host.docker.internal:8090
```

> 配置失败现象：超时、DNS 解析失败、502

5. 修改完成后重启 WSL 生效：

```
wsl --shutdown
```

**复现环境**
WSL2 + Docker Desktop，配置全局代理，代理软件没有添加回环地址豁免

### 1.2 控制台 UTF-8 乱码

**现象**
WSL 终端中文显示问号、方块乱码

**根因**
系统默认字符集不是 UTF-8

**解决方案**

```
echo "export LANG=C.UTF-8" >> ~/.bashrc
source ~/.bashrc
```

> 验证：`echo $LANG`

**复现环境**
全新安装的 Ubuntu WSL，未配置 locale

### 1.3 Docker daemon 起不来：volume 元数据库超时

**现象**

Docker Desktop 启动失败，`docker version` 只能打到客户端，daemon 那一半报：

```
failed to start daemon
error while opening volume store metadata database (/var/lib/docker/volumes/metadata.db): timeout
```

同时伴随一条容易被忽略的 WARN：

```
WARN failed check for fsverity support: operation not supported  path=/var/lib/docker/plugins/storage
```

**根因（不是内存不足）**

Docker 的 volume 元数据库是 bbolt，打开时给的锁等待只有 **1 秒**：

```go
// volume/local/local.go
db, err := bolt.Open(dbPath, 0600, &bolt.Options{Timeout: 1 * time.Second})
```

bbolt 在 Linux 上靠 `flock(2)` 加锁。当 `/var/lib/docker` 落在**跨 VHDX 的 bind mount**（旧版是独立的 `docker-desktop-data` 发行版，4.30+ 在 `/mnt/wsl/docker-desktop-data`）上时，`flock` 要经 9p/virtiofs 往返 Windows 宿主，1 秒预算烧完就 timeout。

上面那条 fsverity WARN 是同一根因的旁证：`FS_IOC_MEASURE_VERITY` 只有 ext4/F2FS 这类本地块设备文件系统才支持，9p 上必然返回 `operation not supported`。

一句话：**问题在「数据目录放在了不支持 flock 的跨系统挂载上」，与内存大小无关。**

**判定命令**

```bash
# ✗ 不这样查：`wsl -d docker-desktop` 的 shell 与 dockerd 不在同一 mount namespace，
#   那里 /var/lib 下只有 misc，读 /var/lib/docker/volumes 会报 No such file or directory。
# ✓ 从容器里 nsenter 进 1 号进程（dockerd）的 namespace 再查：
docker run --rm --privileged --pid=host --entrypoint /bin/sh \
  ccr.ccs.tencentyun.com/nexent-hub/nexent-ubuntu-terminal:v2.7.0 \
  -c 'nsenter -t 1 -m -u -n -i sh -c "findmnt -T /var/lib/docker -o TARGET,SOURCE,FSTYPE; stat -f -c \"fstype=%T\" /var/lib/docker/volumes"'
```

输出里 FSTYPE 出现 `9p` 或 `virtiofs` 即坐实。本机实测为 `/var/lib /dev/sdd[/data] ext4`，未命中本故障。

> 两个读法上的坑：`stat -f` 对 ext4 报 `ext2/ext3` 是 coreutils 的既定行为，一律以 `findmnt` 的 FSTYPE 列为准；Git Bash 下路径会被 MSYS 改写，命令前加 `MSYS_NO_PATHCONV=1`。

**解决方案（按代价从低到高）**

1. **先救元数据**（volume 里的数据不丢，只丢元数据条目）：

   ```bash
   wsl -d docker-desktop -e sh -c "mv /var/lib/docker/volumes/metadata.db /var/lib/docker/volumes/metadata.db.bak"
   ```

2. **回退 WSL 版本**（治症状，1 分钟）：`wsl --update --rollback`。数据仍在 9p 上，只是往返变快。

3. **换正统 Ubuntu 发行版跑 docker-ce**（治根因，推荐）：`wsl --install -d Ubuntu-22.04`，`/etc/wsl.conf` 开 `systemd` 并设 `appendWindowsPath=false`，apt 装 `docker-ce` + `docker-compose-plugin`。这样 `/var/lib/docker` 回到发行版自己的 ext4，flock 在 guest 内核内完成、不出虚拟机。Nexent 只需要 engine + compose，不需要 Docker Desktop。

4. **云主机兜底**：4 核 / 8 GiB / 40 GiB 起步。

**复现环境**

WSL 3.0.3.0 + Windows 10.0.26300 及以上 Insider 构建 + Docker Desktop，`/var/lib/docker` 落在 `/mnt/wsl/docker-desktop-data`（9p/virtiofs）。与内存大小无关；内存充足照样复现。

### 1.4 镜像源拉取失败

**现象**

`docker pull` 长时间卡住，超时失败。报错原文：

```
Error response from daemon: Get "https://docker.mirrors.ustc.edu.cn/v2/": context deadline exceeded
```

**根因**

国内网络下部分老牌公共镜像源已经不可达。**源本身挂了**，不是网络慢、也不是配置写错。

**解决方案**

不要照抄报错里那个源——它正是失败原因。2026-10-28 实测连通性（`curl -o /dev/null -w '%{http_code}' https://<源>/v2/`，4 秒超时）：

| 镜像源 | 实测 |
| --- | --- |
| `https://docker.m.daocloud.io` | 401（通，401 是未认证的正常响应） |
| `https://docker.1ms.run` | 401（通） |
| `https://hub.rat.dev` | 通（本机在用） |
| `https://dockerproxy.cn` | timeout（不可用） |
| `https://hub-mirror.c.163.com` | timeout（不可用） |
| `https://docker.mirrors.ustc.edu.cn` | timeout（不可用，即报错里那个） |

可用配置（Docker Desktop → Settings → Docker Engine，或 `~/.docker/daemon.json`）：

```json
{
  "registry-mirrors": [
    "https://hub.rat.dev",
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io"
  ]
}
```

**复现环境**

国内网络，`registry-mirrors` 里配了已下线的源（中科大 / 网易 / dockerproxy.cn）。

> 判定口诀：401 是通的（镜像仓库要求先认证），timeout / 000 才是不通。看到 401 别去改配置。

## 2 成功路径 / 演示主机的实际配置

这一节是**能跑起来的那条路**，按顺序执行。所有数字都是 2026-10-28 在本机实测的，不是估计值。

### 2.1 前置

| 项 | 本机实测 | 官方要求 |
| --- | --- | --- |
| CPU | 6 核可见（宿主 i7-13650HX，14C/20T） | 最低 4 核，推荐 8 核 |
| 内存 | 14.66 GB 可见（宿主 23.8 GB） | 最低 8 GiB，推荐 16 GiB |
| 磁盘 | E: 14 GB 可用（**真实瓶颈**） | 最低 40 GiB，推荐 100 GiB |
| 虚拟化 | BIOS 里 VT-x 已开启 | 必需 |

> 磁盘这一行要正视：本机只剩 14 GB，而官方最低要 40 GiB。当前 13 个容器 + 13 个镜像共占 **17.37 GB**（`docker system df` 实测：镜像 17.37 GB，其中可回收 2.387 GB；容器 581.6 MB；卷 15.99 kB。`nexent-data-process` 单个 6.77 GB）。**再装东西之前先清盘**，否则 ES 会因磁盘水位触发只读（`ES_DISK_WATERMARK_FLOOD_STAGE=95%`）。

### 2.2 启动命令（唯一正确写法）

```bash
cd E:/deepseek-data/nexent/deploy/docker
bash deploy.sh --defaults
```

实测：**13 个容器全部 Up，冷启动 61 秒**，末尾输出 `🎉 Deployment completed successfully!` 与 `http://localhost:3000`。

`--defaults` 会读 `deploy.options`（本机：`imageSource: mainland`、`sandboxMode: disabled`、`portPolicy: development`），跳过交互式 TUI。

### 2.3 一个必须知道的坑：不能直接 `docker compose up`

想手动操作容器时，**不要**这样写：

```bash
# ❌ 会报 invalid compose project
docker compose -f deploy/docker/compose/docker-compose.yml ps
```

原因是 compose 文件里的镜像变量（`NEXENT_IMAGE`、`NEXENT_WEB_IMAGE` 等）**不在** `deploy/env/.env` 里，而是 `deploy.sh` 运行时渲染到 `deploy/docker/.env.generated` 的。少了这些变量，compose 会报：

```
service "nexent-northbound" has neither an image nor a build context specified: invalid compose project
```

正确写法是先 source 生成的变量文件：

```bash
cd E:/deepseek-data/nexent/deploy/docker
set -a; . ./.env.generated; set +a
docker compose --env-file ../env/.env -p nexent -f ./compose/docker-compose.yml ps
```

（`-p nexent` 不能省，项目名不猜。）

### 2.4 端口表（实测映射）

| 宿主端口 | 容器端口 | 服务 | 实测响应 |
| --- | --- | --- | --- |
| 3000 | 3000 | nexent-web（控制台） | 307 → 登录页 |
| 5010 | 5010 | nexent-config | 404（FastAPI 根路径，正常） |
| 5011 / 5015 | 5011 / 5015 | nexent-mcp | 404（正常） |
| 5012 / 5555 / 8265 | 同 | nexent-data-process | 404（正常） |
| 5013 | 5013 | nexent-northbound | 404（正常） |
| 5014 | 5014 | nexent-runtime | 404（正常） |
| 5434 | 5432 | nexent-postgresql | TCP |
| 5436 | 5436 | supabase-db-mini | TCP |
| 6379 | 6379 | nexent-redis | TCP |
| 9010 / 9011 | 9000 / 9001 | nexent-minio（API / 控制台） | 403 / 200 |
| 9210 / 9310 | 9200 / 9300 | nexent-elasticsearch | 401（要认证，正常） |
| 8000 / 8443 | 8000 / 8443 | supabase-kong-mini | TCP |

> **404 和 401 都是「活着」的证据**。这些是 FastAPI / ES 的正常响应，不代表服务坏了。真正判死的信号是连接被拒（curl 返回 `000`）。

### 2.5 怎么判定「环境真的好了」

四条，全部可机械执行：

1. **容器齐**：`docker ps --format '{{.Names}}' | wc -l` → `13`
2. **Web 通**：`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/` → `307`
3. **ES 绿**（要带密码，`ELASTIC_PASSWORD` 在 `deploy/env/.env`）：

   ```bash
   PW=$(grep -E '^ELASTIC_PASSWORD=' deploy/env/.env | head -1 | cut -d= -f2- | tr -d '"')
   docker exec nexent-elasticsearch curl -s -u "elastic:$PW" localhost:9200/_cluster/health
   # 期望 "status":"green"
   ```

   本机实测：`{"cluster_name":"docker-cluster","status":"green","number_of_nodes":1,"active_primary_shards":3,...}`

4. **数据目录不在 9p 上**：容器内 `nsenter -t 1` 之后执行 `stat -f -c 'fstype=%T' /var/lib/docker/volumes`（完整命令见 §1.3）→ `ext2/ext3/ext4`

### 2.6 本机遗留问题（已知，不阻塞）

| 现象 | 影响 | 说明 |
| --- | --- | --- |
| `nexent-runtime` 日志刷 `otel-collector` 解析失败 | 无 | 未部署 monitoring 组件（`deploy.options` 里 `monitoringProvider: otlp` 但没选 monitoring），遥测上报失败只打 WARN/ERROR，不影响推理 |
| 磁盘只剩 14 GB | 有风险 | 见 §2.1 |
| 未装 WSL 的 Ubuntu 发行版 | 无 | 本机只有 `docker-desktop` 发行版，Docker Desktop 后端正常工作，说明未命中 §1.3 |
| 控制台页脚版本号 | 展示问题 | 未登录时页脚显示 `v1.0.0`，登录后才是 `v2.7.0`；本机部署版本为 v2.7.0 |

## 3 判定「环境好了」的四条指标

1. WSL 版本、内核、docker 版本信息采集正常
2. 代理豁免配置完成，本地端口连通正常
3. 中文不乱码，docker 服务正常启动
4. 镜像拉取加速配置生效，pull 镜像不超时

> 第 1 条的「正常」以 §0 表格填满为准；第 4 条以 §1.4 的 401/timeout 判据为准。

## 4 排障对照表（症状 → 命令 → 结论）

| 症状 | 排查命令 | 结论 |
| --- | --- | --- |
| 访问 127.0.0.1 超时 | `curl -I http://127.0.0.1:3000` | 代理未添加回环豁免 / NO_PROXY 缺少 host.docker.internal |
| 中文问号方块乱码 | `echo $LANG` | 字符集不是 C.UTF-8 |
| Docker daemon 起不来，报 volume metadata 超时 | 容器内 `nsenter -t 1` 后 `stat -f -c 'fstype=%T' /var/lib/docker/volumes`（见 §1.3） | 数据目录在 9p/virtiofs 上，flock 超 1 秒 → 见 §1.3 |
| `docker compose ps` 报 invalid compose project | `ls deploy/docker/.env.generated` | 没 source 生成的变量文件 → 见 §2.3 |
| docker pull 卡住超时 | `curl -o /dev/null -w '%{http_code}' https://<源>/v2/` | 401=通，timeout=源挂了 → 换源，见 §1.4 |
| 控制台 3000 返回 000 | `docker ps -a --format '{{.Names}}\t{{.Status}}'` | 容器没起；先 `bash deploy.sh --defaults` |
| 服务端口返回 404 / 401 | 无需处理 | FastAPI / ES 的正常响应，不是故障 |
| ES 健康检查 401 | 带上 `-u elastic:$ELASTIC_PASSWORD` | 安全插件默认开启，未带凭据 |

## 5 交接单

`docs/handoff/W1-T6-质量交接单.md`

### 本节（T1 补写）完成情况

| 项 | 状态 |
| --- | --- |
| §0 表格 8 行全部填实测值 | ✅ |
| §1.3 根因与解决方案 | ✅ 已重写，纠正「内存不足」的误判，给出 flock 1 秒超时的真实机制 |
| §1.3 报错原文 | ✅ 已替换为真实原文（`error while opening volume store metadata database ...: timeout`） |
| §1.4 换可用源 | ✅ 已给出实测可用源与 401/timeout 判据 |
| §2 成功路径整节 | ✅ 含冷启动实测 61 秒、端口表、compose 变量文件坑、四条判定指标 |
| §4 排障表 3 条结论纠正 | ✅ 已按实测改正 |
