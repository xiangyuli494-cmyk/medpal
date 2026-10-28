# 环境踩坑与环境清单（WSL2 + Docker Desktop）
> 面向全组。分两部分：失败过的坑（T6 记录）与已验证的成功路径（T1 在演示主机实测）。
## 0 环境清单（实测值）
| 项 | 值 | 采集命令 | 采集人 |
| ---- | ---- | ---- | ---- |
| WSL版本 |  | wsl --version |  |
| 内核版本 |  | uname -r |  |
| Windows版本 |  | winver |  |
| Docker版本 |  | docker --version |  |
| docker compose版本 |  | docker compose version |  |
| Storage Driver | TODO | docker info |  |
| Docker Root Dir | TODO | docker info |  |
| 可用磁盘 |  | df -h |  |

## 1 失败路径：装不起来时踩的坑
### 1.1 代理拦截回环地址
**现象**
WSL2开启全局代理后，访问 localhost、127.0.0.1 超时失败；只设置 NO_PROXY 环境变量依然超时。

**根因**
仅环境变量 NO_PROXY 只能控制主动读取这个变量的程序；DNS解析、socket直连不受它控制，必须在代理软件分流规则里添加豁免。

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

> 
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

> 
> 验证：`echo $LANG`

**复现环境**
全新安装的 Ubuntu WSL，未配置 locale

### 1.3 Docker daemon 起不来：metadata.db flock 超时

**现象**
Docker Desktop 启动报错，WSL 后端无法拉起，报错原文：metadata.db flock 超时

**根因**
交由 T1 补充

**解决方案**
交由 T1 补充

**复现环境**
Windows 内存紧张，WSL 分配内存过小

### 1.4 镜像源拉取失败

**现象**
`docker pull` 长时间卡住，超时失败，清华、中科大镜像源访问报错，报错原文：

```
Error response from daemon: Get "https://docker.mirrors.ustc.edu.cn/v2/": context deadline exceeded
```

**根因**
国内网络下镜像源连通不稳定，源本身不可达

**解决方案**

```
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn"
  ]
}
```

**复现环境**
国内网络，未配置镜像加速，尝试中科大 / 清华镜像源，连通超时

## 2 成功路径 / 演示主机的实际配置

交由 T1 补充整节

## 3 判定「环境好了」的四条指标

1. WSL 版本、内核、docker 版本信息采集正常
2. 代理豁免配置完成，本地端口连通正常
3. 中文不乱码，docker 服务正常启动
4. 镜像拉取加速配置生效，pull 镜像不超时

## 4 排障对照表（症状 → 命令 → 结论）


| 症状 | 排查命令 | 结论 |
| --- | --- | --- |
| 访问 127.0.0.1 超时 | curl -I http://127.0.0.1:3000 | 代理未添加回环豁免 / NO_PROXY 缺少 host.docker.internal |
| 中文问号方块乱码 | echo $LANG | 字符集不是 C.UTF-8 |
| Docker WSL 后端启动失败 | wsl --shutdown | WSL 内存不足或者镜像损坏，交由 T1 确认根因 |
| docker pull 卡住超时 | docker pull hello-world | 镜像源不可达，需要更换镜像源 |

## 5 交接单

docs/handoff/W1-T6 - 环境部署质量交接单.md

PR 描述：

需要 T1 补的部分：

1. 第 2 节（成功路径 —— 整节）
2. 1.3 的根因、解决方案
3. 环境清单里的【值】、采集人
