# 模块：agent 骨架入库与规范整改

| 项 | 内容 |
| --- | --- |
| 交接人 | T1 |
| 日期 | 2026-10-24 |
| 周次 | W1 |
| 分支 | `feat/agent-scaffold`（入库）、`fix/agent-ruff`（规范整改） |
| 关联 Issue | PR #18、PR #19 |

## 一句话说清它干什么

把 MCP 工具链、三个 Skill 包和评测集搬进仓库，让「clone 下来就能跑」。

## 数据流

~~~mermaid
flowchart LR
  A[agent/data/samples/*.md] --> B[parsers 解析 + 实体识别]
  B --> C[store 写 SQLite 资产台账]
  C --> D[seed 灌种子本体 v0.9]
  D --> E[server.py 10 个 MCP 工具]
  E --> F[eval/run_eval.py 14 条评测]
  E --> G[trace.json + reports/TR-*.md]
~~~

一句话：原始文件进来 → 解析成资产卡 → 落 SQLite → 工具查 → 出 trace 与评测报告。

## 我改了什么（人工修改点）

1. **搬目录**：本地 `scaffold/` 整套移到 `agent/`，按方案附录 A 的树逐行对齐；`scaffold` 里的 `.gitignore` 不复用，新写一份 `agent/.gitignore`。
2. **只排 `*.db`，不排整个 `data/`**：原 `.gitignore` 排的是 `mcp-server/data/`，那样种子本体 `ontology_v0.9.jsonl` 会一起被挡在门外，clone 下来跑不起来。改成 `mcp-server/data/*.db`。
3. **不搬运行期产物**：`medpal.db`（128 KB）、`tmp/`、`__pycache__`、59 份 `reports/` 都没进库，靠 `seed.py --reset` 重建。
4. **方案同步**：附录 A 补 `README.md` / `requirements.txt` / `skeleton.py` 三行，`data/` 一行写清「谁进库、谁可重建」；§2 / §6.2 / §10.2 三处 `scaffold/` 路径改 `agent/`。
5. **规范整改（PR #19）**：`seed.py` 的 5 个 lambda 赋值改成 `def`，歧义变量名 `l` 改 `label`；`store.py` / `server.py` 的超长 SQL 与 docstring 按语义断开（隐式字符串拼接，字面量不变）；`run_eval.py` 删无用变量 `tail`、`for l` 改 `for line`；`tests/test_mcp_client.py` 的延后导入加 `# noqa: E402` 并写清为什么不能挪到顶部。

## 怎么验证的

| 验证方式 | 具体内容 |
| --- | --- |
| 单元测试 | `pytest backend/tests -q` 12 passed（未受影响）；`agent/tests/*` 需装 `mcp` 包，本机未跑 |
| 手工验证 | `ruff check .` 全绿；8 个 py 文件 `py_compile` 全过；用真实 sqlite 跑通 store 全链路——建表 6 张、`upsert_asset`、`add_triple`、`neighbors`、`kg_query`(1 条 path)、`snapshot`、`current_version`、`resolve_entity`、`write_trace`、`get_trace`、`list_assets`、`diff_versions` |
| 边界情况 | 空 seeds 调 `kg_query` 返回 `resolved/unresolved` 而非抛错；重复三元组走 `UPDATE confidence` 分支；`align` 在 alias 表为空时返回 `unmapped` 而不是崩溃 |

## 已知风险与留待后续

- **`server.py` 与 `run_eval.py` 端到端未验**：本机 Python 没有 `mcp` 包，`pip install mcp==1.27.2` 超时。需要 T1 在装好依赖的机器上跑 `seed.py --reset` → `tests/test_smoke.py` → `eval/run_eval.py` 三连，并把输出贴进 PR。
- **`store.snapshot()` 会回写种子文件**：它把当前三元组写回 `mcp-server/data/ontology_v0.9.jsonl`，跑测试会覆盖种子。我验证时踩到一次，已从 git 恢复。建议 W1 给它加 `--out` 参数，默认不覆盖种子。
- **schema 冻结**：`SCHEMA_VERSION` 现在是 `walking-skeleton/1`，`store.py` 的表结构尚未冻结成 v0。按协作规则，改 schema 前要先走 T1 裁决。
- `agent/.gitignore` 排了 `eval/reports/*.json|md`，意味着评测报告不进库；如果 W3 需要「可复查的评测证据」，得改成只排大文件、保留 JSON。
