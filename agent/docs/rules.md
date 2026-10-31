# agent/ 线工程规则（赛题3）

> 版本 v1.0 · 2026-10-22 · 适用范围：`agent/`、`fixtures/golden_trace.json`、`tools/diff_json.py`、`.github/workflows/skeleton.yml`
> 陪诊线（`backend/`、`frontend/`、`docs/plan/`）已冻结，规则另见 `docs/plan/12-*`、`13-*`。

---

## 1. 分支

| 类型 | 命名 | 例 |
| --- | --- | --- |
| 功能 | `feat/agent-{T编号}-{简述}` | `feat/agent-T2-ontology-extract` |
| 修复 | `fix/agent-{T编号}-{简述}` | `fix/agent-T6-ci-cache` |
| 文档 | `docs/agent-{简述}` | `docs/agent-charter` |

- 从 `main` 切出，存活 ≤ 7 天
- 每周至少 `git pull --rebase origin main` 一次
- 一个 PR 只做一件事、只动一层（见 §5）

## 2. 提交信息

```
<type>(agent): <描述>
```

- type ∈ `feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert`
- scope 固定 `agent`
- 描述用中文，不超过 50 字，不加句号

## 3. PR

必须满足四项才可合并：

1. `skeleton` workflow 绿（骨架通不通电）
2. `lint-and-test` workflow 绿
3. 至少 1 人 approve（CODEOWNERS 指定的 owner）
4. 带交接单 `docs/handoff/W{周}-T{编号}-{模块}.md`

PR 描述模板：

```markdown
## 改了什么
## 为什么改
## 怎么验的（贴命令和输出）
## 动了哪根骨头（解析 / 本体 / 推理 / 溯源 / 存储 / 平台 / 前端）
## 有没有让别人跑不通
```

## 4. 交接单

文件名：`W{周}-T{编号}-{模块}.md`，例 `W1-T2-ontology-extract.md`。
模板沿用 `docs/handoff/模板.md`，「工号」一栏填 T 编号。

## 5. 骨架纪律（红线）

1. **一次只加粗一根骨头。** 一个 PR 只改一层，跨层拆 PR。
2. **先红再绿。** 动骨架前先写一个会失败的测试或评测条目，PR 里贴红灯截图。
3. **骨架命令坏了，全组停手。** `python -B -m agent.skeleton` 不绿期间，只允许修它。

> 为什么加 `-B`：改一个数字但文件长度不变时，`__pycache__` 会让门禁**假绿**。已实测过 0.80→0.81 未触发变红。

## 6. Definition of Done

一个任务算做完，同时满足：

- [ ] 代码在 `agent/` 下，没有新增第三方依赖（除已在 `requirements.txt`）
- [ ] 有单元测试，且 `pytest` 本地全绿
- [ ] 骨架命令仍绿
- [ ] 交接单已提交
- [ ] 验收标准逐条自测过，附输出
- [ ] 没有 committed 的 Key、数据库、PDF、音视频

## 7. 不许做

- 直接向 `main` 推送（含强推）
- 修改别人的模块文件（`agent/ontology/`、`agent/parsers/` 等按人划分，见 `CODEOWNERS`）
- 在 PR 里顺手重构无关代码
- 用 AI 生成后直接提交且不说明（交接单「人工修改点」必填）
