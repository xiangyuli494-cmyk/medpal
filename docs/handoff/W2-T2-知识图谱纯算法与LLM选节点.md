# 模块：知识图谱纯算法与LLM选节点

| 项 | 内容 |
| --- | --- |
| 交接人 | zincumyu（T2） |
| 日期 | 2026-10-19 |
| 周次 | W2 |
| 分支 | feat/zincumyu-kg-triage |
| 关联 Issue | 无（赛题三 R4 能力迁移；非旧陪诊项目的 C2 条件交付） |

## 一句话说清它干什么

把原 KG 的症状→疾病→科室遍历、儿科过滤和 LLM 选节点迁入 medpal，默认不依赖 MySQL。

## 数据流

文本 → NodeSelector 规则层（别名/名称精确）→ 未命中时 LLM 调 search_nodes/select_nodes → GraphRepository 校验 node_key → traverse() 投票出科室。MemoryGraphRepository 从 fixtures/kg/demo_graph.json 读图；LLM 走 OpenAI-compatible /chat/completions。

~~~mermaid
flowchart LR
  A[患者文本] --> B[规则层 别名/名称精确]
  B -->|命中| E[节点列表]
  B -->|未命中| C[LLM tool calling]
  C --> D[search_nodes / select_nodes]
  D --> F[GraphRepository 校验]
  F --> E
  E --> G[traverse 投票]
  G --> H[候选科室 + 置信度 + 依据]
~~~

## 我改了什么（人工修改点）

1. 把原 recommend.py 里的 SQL 查询抽成 GraphRepository 协议，domain 只保留纯遍历、投票、儿科过滤和置信度计算。
2. 新增 MemoryGraphRepository 与 fixtures/kg/demo_graph.json，用 21 个节点/16 条边的小图覆盖规则层、LLM 选节点和遍历测试。
3. 新增规则层 + LLM 工具调用两层选择器；LLM 提交的每个 node_key 必须过 node_exists，编造的 key 直接丢弃。
4. 新增 OpenAI-compatible LLM 适配器、.env 配置加载、FakeLlm 和 httpx.MockTransport 测试；修复 LLM_MODEL_MAIN 回退，避免网关因模型名不对返回 403。
5. 403 时把上游响应体带进错误信息，并加 tools/kg/demo.py --probe 用于区分鉴权/额度/模型问题。

## 怎么验证的

| 验证方式 | 具体内容 |
| --- | --- |
| 单元测试 | python -m pytest backend/tests -q：65 passed；test_triage.py 22 条、test_kg_selector.py 17 条、test_llm_config.py 14 条、原有 12 条 |
| 覆盖率 | python -m pytest backend/tests -q --cov=backend/domain：100%（114 statements，0 miss） |
| 静态检查 | ruff check .：All checks passed；python tools/check_guard_words.py：禁用词 0 次 |
| 手工验证 | python tools/kg/demo.py 腿疼 → 规则层命中，骨科专科/风湿免疫科；python tools/kg/demo.py "我腿疼" --llm --trace → source=llm，节点 symptom:腿疼，遍历到骨科专科 |
| 上游探测 | python tools/kg/demo.py --probe → 探测成功（MaaS qwen3.8-flash） |
| 边界情况 | 空输入、未知节点、无疾病症状、儿科过滤（成人/儿童/年龄未知）、试管婴儿反例、重复疾病去重、邻居上限、缺失科室名回退 |

## 已知风险与留待后续

- 目前只有内存小图，没有 MySQL 的 kg_node/kg_edge/kg_alias，也没有 2 万节点/13 万边/1 万别名的全量数据；
- 旧 store.search_nodes 的剥口语填充词、长句切词、alias_stripped 尚未迁入，规则层目前只认别名/名称精确匹配；
- LLM 真实调用依赖外部 MaaS 网关，CI 只用 FakeLlm；.env 与 Key 不入库；
- OpenCMKG 数据仅限学术研究，后续接全量数据时需补署名与许可说明；
- 迁移前，该能力在旧陪诊项目里按 ADR-011 属 C2 条件交付、不进陪诊主状态机；迁入赛题三后它是 R4 的核心得分点（方案 §2 R4），定位已变；
- 本模块是知识图谱协作；T2 的 W1/W2 主任务是迁移现有 KG 代码，并在其上做两跳查询与实体消歧。
