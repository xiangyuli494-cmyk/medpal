# 模块：Trace推理链路可视化页面

## 一句话说清它干什么
trace.html 静态页面，实现trace推理链路可视化渲染，按schema契约做断链标红，支持gaps、detail字段展示，无需后端服务，浏览器直接打开使用。

## 数据流
前端读取本地选择的trace json，解析schema，循环渲染step卡片；依据unresolved、evidence等字段规则执行标红逻辑，gaps仅展示文本不参与颜色判断。

## 我改了什么（人工修改点）
1. 开发 trace.html，对齐 trace-schema v1 契约，支持三份官方fixture渲染；
2. 实现unresolved标红、gaps和detail字段渲染、XSS防护；
3. 本次调整：将交接单从 `agent/docs/handoff/W1-T3-trace.md` 迁移至 `docs/handoff/W1-T3-trace.md`，适配自动化检查器路径。

## 怎么验证的
1. 本地浏览器加载三份fixture样例，核对渲染、标红、警告行为；
2. 校验schema版本闸门、字段渲染规则；
3. 验证畸形JSON不会崩溃，页面无后端依赖；
4. 自测DoD清单全部通过。

---
# W1-T3 trace可视化模块交接单
任务编号: W1-T3
模块名称: Trace推理链路可视化页面
交付文件: agent/web/trace.html

## 1. 模块目标
实现T3任务3.1单页可视化、3.2断链标红能力，静态单HTML页面，**无需后端服务**，双击直接在浏览器打开。
遵循契约:
- trace-schema.md v1
- T3-可视化输入契约.md.txt

## 2. 文件路径
agent
└── web/
    └── trace.html

## 3. 核心功能规则
1. Schema版本闸门
- medpal-trace/1: 完整渲染全部字段，执行断链标红逻辑
- walking-skeleton/1: 旧方言兼容，弹出黄色迁移提示，**不做红标**
2. 断链标红判定
- 仅顶层 unresolved 数组做精确字符串匹配
- gaps 只做文本展示，**不参与颜色判断**
- 仅匹配到的单条证据下划线变红，不会整步骤染红
3. 字段渲染规则
顶层字段: schema、trace_id、question、agent_version、ontology_version、trace_completeness、sources、gaps、unresolved
step字段: 1/step、op、in、out、detail(可选)、confidence、evidence
- confidence缺失显示 --，不自动补
- evidence为空数组: 展示灰色【无引用】，不标红
4. 安全: 内置HTML转义escapeHtml，防御XSS
5. UI: 概要卡片 + Unresolved提示块，输入输出使用浅灰代码块

## 4. 验收测试（3份官方fixture）
fixture路径: agent/tests/fixtures/
1. trace_v1_example.json（全绿样例）：正常渲染，无红标
2. trace_v1_broken.json（断链样例）：仅匹配证据条目红下划线
3. trace_walking_skeleton_example.json（旧骨架）：黄色迁移警告，零红标

## 5. 使用方式
1. 本地双击 trace.html 打开
2. 页面里选择对应的json fixture文件加载
3. 浏览器推荐 Ctrl+Shift+R 硬刷新，避免缓存问题

## 6. 自测DoD清单
- [x] 红标逻辑符合契约，gaps不参与判断
- [x] 新旧schema闸门生效
- [x] 缺失字段渲染规则正确
- [x] 支持detail可选字段渲染
- [x] XSS防护，畸形JSON不会崩溃
- [x] 三份fixture渲染行为符合预期
- [x] 纯静态文件，零依赖

## 7. 已知限制 & 后续
- 仅本地浏览器加载文件，无后端接口
- 仅支持契约约定schema版本
