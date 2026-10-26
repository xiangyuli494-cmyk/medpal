---
name: ontology-evolve
description: 从新入库资产中抽取候选三元组，做规则校验与 ICD-10 对齐，产出可审 diff，确认后发布新本体版本
allowed-tools: [onto_propose, std_align, onto_commit, get_asset_card]
tags: [medical, ontology, evolution, low-resource]
---

# 本体进化（S2）

## 何时用

新资产已入库、需要把里面的新知识并进本体时；或用户要求「看看本体能不能更新」「出一版 diff」时。
知识库变大不等于本体进化——本技能只处理三元组，不做向量入库。

## 输入

- 一批 asset_id（通常来自 S1 的台账）
- 可选的版本说明

## 步骤

1. 调 onto_propose，拿到 candidates 与 rejected。
2. **先报统计再看细节**：候选 n 条、拒收 m 条，并按 reason 分组计数（too_short / no_pattern_match / entity_unresolved / duplicate）。拒收不是错误，是规则在起作用，要讲清楚。
3. 对每条候选调 std_align 补标准编码；对齐失败的标 unmapped 并单独列出，不阻塞发布。
4. 以 diff 形式呈现给用户：+ 新增 / ~ 修改（同三元组置信度变化）/ - 废弃，每条都带 provenance 锚点。
5. **必须等用户确认**再调 onto_commit。用户未明确同意时不得自行发布。
6. 发布后输出：新版本号、三元组总数、与前版本的差分统计、对齐率。

## 输出格式

    候选 8 条 / 拒收 12 条（too_short 4、duplicate 6、entity_unresolved 2）
    + 消化性溃疡 -requires_exam-> 幽门螺杆菌呼气试验   [AST-...#p3.s5, 置信 0.72]
    对齐：6/8 命中 ICD-10，2 条 unmapped（列出）
    待确认后发布。已确认 -> v1.0（此前 v0.9，净增 8 条）

## 禁止

- 不在用户未确认时调 onto_commit
- 不把 rejected 条目悄悄丢掉，必须报数
- 不宣称「全自动更新」——人工确认是本技能的固定环节
