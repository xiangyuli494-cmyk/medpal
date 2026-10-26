# 冻结声明

**冻结日期**：2026-10-22
**锚点 tag**：`w1-freeze-20261022`
**冻结范围**：院内智慧陪诊终端（八周计划 W1–W8）

---

## 一句话

陪诊终端线自 `w1-freeze-20261022` 起**暂停推进**，全组资源转向赛题3（华为 ModelEngine Nexent 可进化决策智能体），周期 2026-10-23 → 2026-11-22。11-22 之后视情况恢复。

## 冻结的是计划，不是代码

| 保留 | 说明 |
| --- | --- |
| 全部分支 | 12 个纯落后分支照旧保留，不删除、不 rebase |
| 全部文档 | `docs/plan/`、`docs/specs/`、`docs/adr/`、`docs/handoff/` 原样冻结 |
| 工具链 | CI、交接单检查、分支规范继续生效，赛题3 线同样适用 |
| 演示件 | `demo/device-prototype.html`、`demo/v4.html` 保留可访问 |

## 冻结期间不做什么

- 不向陪诊线相关分支推送新提交
- 不修改 `docs/plan/`、`docs/specs/` 下的既有文档
- 不清理分支、不关闭已有 Issue

## 这一个月移植走的东西（不是白干）

| 复用物 | 去向 |
| --- | --- |
| 术语表 39 条 | `agent/ontology/` 别名词典种子 |
| KG 分诊 1912 行（PR #5） | `agent/ontology/` 多跳推理内核 |
| CI 九步门禁 | `.github/workflows/` 直接沿用 |
| OCR 实测数据（`docs/specs/ai-selection.md`） | `agent/docs/` 选型依据 |
| 合规三件套 + `docs/legal/` | 赛题3 数据合规基线 |
| 无障碍验收标准 | 演示可读性要求 |

## 恢复方式

```bash
git checkout w1-freeze-20261022
```

相关工作在新分支上继续，不改动本 tag 指向的提交。
