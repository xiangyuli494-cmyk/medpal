# 院内智慧陪诊终端

> 医院采购的院内智慧陪诊系统 · 六人团队 · 八周工期

一台放在门诊大厅的终端，替不会用手机的老人走完院内全流程：刷证建档、语音说病、口述预分诊、语音挂号、点位讲解、院内导航、医嘱回放、一键求助。家属在手机上远程看见进度与医嘱。**设备是本体，用户端与家属端是它的两个远程延伸。**

---

## 现在是什么状态

| 项 | 状态 |
| --- | --- |
| 规划文档 | 齐（18 份，v3.0 八周版） |
| 前置规范 | 齐（访问控制、数据留存、NFR、毕设复用、知情同意书） |
| 工程骨架 | 在（目录、接口定义、工具链、CI、12 条测试） |
| 业务代码 | **还没开始**（W1 只定契约，W2 起写领域层） |
| 能演示的东西 | 在线：https://xiangyuli494-cmyk.github.io/medpal/ ｜本地：demo/device-prototype.html（设备端权威原型）、demo/v4.html（全链路演示），纯前端单文件，双击可跑 |

**还没到能跑起整个系统的阶段**：后端服务、三端页面都还没有，这是 W1 – W2 的活。现在评审的是**文档与骨架**。

---

## 快速开始

**方式一：直接在浏览器打开（不用下载任何东西）**

https://xiangyuli494-cmyk.github.io/medpal/

**方式二：本地打开（零依赖，双击即可）**

```bash
# 入口页，两个 demo 都能从这儿进
start index.html

# 设备端权威原型
start demo/device-prototype.html

# 全链路演示（含架构与故障视角）
start demo/v4.html
```

## 评审看什么（按时间选）

| 时间 | 看什么 |
| --- | --- |
| 5 分钟 | docs/plan/文档评审包.html（一页看全） |
| 10 分钟 | https://xiangyuli494-cmyk.github.io/medpal/demo/device-prototype.html（设备端长什么样） |
| 30 分钟 | docs/plan/00-项目工期与范围基线.md → 11-技术方案与接口契约.md §4 → docs/specs/device-ia.md |
| 按角色 | T6 看 12 号规范；T1 看 11 号；T3 看 02 号 §3；T4 看 02 号 §3 与 docs/specs/device-ia.md；T5 看 02 号 §4、§5 |

新增的规范值得单独看：

| 文件 | 内容 |
| --- | --- |
| docs/specs/access-control.md | 三类入口三套令牌、可见性矩阵、WS 鉴权 |
| docs/specs/device-ia.md | 设备端 11 节点逐屏、触摸控件体系、点位讲解词 |
| docs/specs/data-retention.md | 留多久、谁能删、删除怎么留痕 |
| docs/specs/nfr.md | 15 条指标，每条都带测法 |
| docs/specs/legacy-reuse.md | 毕设哪些能用、哪些不碰 |

---

## 怎么提意见

1. **直接开 Issue**：仓库已带三个模板（功能 / 缺陷 / 评审）。评审意见用「评审」模板，一条一个。
2. **口径冲突**：docs/plan 里有 12 处说法不一致（节点数 9 还是 11、术语表放哪、冻结时点等），集中列在 docs/plan/04 号口径裁决表里，逐条回「同意 / 改成什么」即可。
3. **别用微信口头说**：口头结论不进仓库，一周后没人记得。

截止：**周一 20:00 计划会前**，会上只处理有分歧的条目。

---

## 三条不能越的线

| 编号 | 约束 |
| --- | --- |
| R-1 | 医学相关表述须以医生原话为来源，不得表述为系统判断 |
| R-2 | 识别不确定时须标记并当场求证，不得推断，剂量字段尤须遵守 |
| R-3 | 重要医疗材料须电子化留存，交接有留痕、可追溯 |

---

## 目录

~~~
medpal/
├── .github/          CI、交接单检查、PR / Issue 模板
├── docs/
│   ├── plan/         规划文档集（18 份，含评审包）
│   ├── specs/        前置规范：访问控制、设备端信息架构、留存、NFR、毕设复用
│   ├── adr/          ADR-000 模板、ADR-016 毕设复用、ADR-017 触摸屏形态
│   ├── api/          会话协议 v0.1
│   ├── legal/        知情同意书
│   ├── handoff/      模块交接单：改了代码必须交
│   ├── accessibility/ 无障碍验收标准（W1 产出）
│   └── test/         测试计划与周报
├── backend/
│   ├── domain/       纯逻辑层，零框架依赖，覆盖率 100%
│   ├── adapters/     ASR/TTS/OCR/Push 接口与假实现；legacy 只读客户端
│   ├── apps/         Django 应用（W2 起）
│   └── tests/        12 条测试
├── fixtures/legacy/  从毕设导出的检查项、科室、排班样例
├── tools/            mock 服务、红线检查、交接单检查、毕设导出
├── index.html        演示入口页（在线打开时的首页）
├── demo/             device-prototype.html 设备端原型、v4.html 全链路
├── device/           设备端（浏览器形态，10.1 寸触摸屏 Kiosk，产品本体）
├── frontend/
│   ├── user-app/     用户端（老人版 / 标准版）
│   └── family/       家属端 H5
└── firmware/ hardware/  条件交付 C3/C4
~~~

---

## 本地能跑什么

~~~powershell
pip install -r requirements-dev.txt
python -m pytest backend/tests -q          # 12 条测试
powershell -ExecutionPolicy Bypass -File tools/dev.ps1   # 起 mock 接口(8000)与 mock 会话(8090)
python tools/check_guard_words.py          # 红线扫描
python tools/check_handoff.py              # 交接单检查
~~~

后端服务与前端页面还没有，W1 末补齐空壳。

---

## 协作规矩（摘要）

- 不直接 push main，一律走 PR；main 已开分支保护，两个检查必须绿；
- 改了代码必须交 docs/handoff/W{周}-T{工号}-{模块}.md，写清数据流与人工修改点，否则合并按钮是灰的；
- 提交格式为 type(scope): 中文动宾，scope 用白名单；
- 详见 CONTRIBUTING.md。

## 团队

| 代号 | 角色 |
| --- | --- |
| T1 | 项目经理 / 架构师 / 领域工程 |
| T2 | 设备端技术形态与嵌入式 |
| T3 | 用户端与家属端前端 |
| T4 | 毕设底座接入与设备端交互 |
| T5 | AI 集成与无障碍 |
| T6 | 质量保证 |

## 文档效力与合规

文档之间口径冲突时，以 `docs/plan/00-项目工期与范围基线.md` 为准。

本项目为教学项目，不收费、不用于商业用途。仓库内不得存放任何真实患者数据、真实身份证号、真实手机号或真实医疗单据原图。所有测试数据须为脱敏或自建样例。素材来源与许可见 `docs/specs/legacy-reuse.md` §5。
