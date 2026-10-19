# 怎么在这个仓库里干活

> 五条规矩，看完就能开工。冲突时以 12 号开发规范与 00 号基线为准。

---

## 一、先把环境跑起来

~~~powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -r backend/requirements.txt

# 起两个假服务（不需要网络、不需要 Key）
powershell -ExecutionPolicy Bypass -File tools/dev.ps1

# 另开一个窗口跑测试
python -m pytest backend/tests -q
~~~

接口在 http://127.0.0.1:8000/api/v1/health，会话在 ws://127.0.0.1:8090。

---

## 二、一周怎么走

| 时点 | 做什么 |
| --- | --- |
| 周一 20:00 | 计划会认领任务，说清依赖谁 |
| 周一到周四 | 在自己的分支上做，小步提交，随做随推 |
| 周三 | 把 main 合进来一次：git pull --rebase origin main |
| 周五到周六 | 提 PR，写交接单，等 CI |
| 周日 20:00-22:00 | 合并窗口，T6 值守 |
| 周日 24:00 | 截止，附证据 |

## 三、分支

| 类型 | 格式 | 例子 |
| --- | --- | --- |
| 功能 | feat/F-{功能号}-{简述} | feat/F-012-check-plan |
| 修复 | fix/issue-{编号}-{简述} | fix/issue-38-asr-timeout |
| 测试 | test/T-{编号}-{简述} | test/T-007-recall-check |
| 文档 | docs/{简述} | docs/w1-protocol |

~~~powershell
git switch main
git pull --rebase origin main
git switch -c feat/F-001-device-shell
~~~

分支活不过一周。一周没合，要么拆小，要么先合一个能跑的版本，用开关关掉没做完的部分。

## 四、提交

格式：{type}({scope}): {中文动宾}，句末不加标点。

~~~text
feat(device): 增加长按 2 秒进入语音模式
fix(api): 修复扫描单据超时
docs(adr): ADR-015 访问控制模型
~~~

type 只能是：feat fix docs style refactor perf test build ci chore revert
scope 只能用：domain api device user family console firmware hardware test docs

一次提交只做一件事。混进无关的格式化改动，评审直接退回。

## 五、PR 与合并

完整规则见 [docs/合并规则.md](合并规则.md)：机器查什么、人要做什么、被拦了怎么查。下面是摘要。

一个 PR 只做一件事，并且**必须交一份模块交接单**：

~~~powershell
python tools/new_handoff.py --module 设备端空壳 --owner T2 --week 1
# 打开 docs/handoff/W1-T2-设备端空壳.md，把四节写满
python tools/check_handoff.py
~~~

合并前四个条件，缺一不可：

- [ ] CI 绿（ruff + 红线 + 测试）
- [ ] Handoff 绿（交接单齐、内容够）
- [ ] 至少 1 人 approve
- [ ] 分支已 rebase 到最新 main

合并方式用 Squash and merge，一个 PR 在 main 上留一个提交。

**禁止直接 push main，禁止 force push。**

## 六、交接单到底写什么

看 docs/handoff/README.md，里面有模板和一份填好的示例。

四句话概括：

1. 一句话说清它干什么；
2. 输入从哪来、经过哪几步、输出到哪去；
3. AI 生成后你亲手改了哪里；
4. 你用什么证明它能跑。

写不出第一条，说明这个模块还没想清楚，先别提交。

## 七、卡住了找谁

| 症状 | 找谁 |
| --- | --- |
| PR 提不上去、CI 报错看不懂 | T6 |
| 字段名不确定 | T1 |
| 前端请求被浏览器拦 | T6（CORS） |
| 接口与页面字段对不上 | T1 |
| 第三方接口调不通 | T5 |
| 不知道自己该交什么 | T1 |

卡超过 3 天在群里点名，不要自己扛。