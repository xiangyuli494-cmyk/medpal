# 毕设复用与旧系统边界（v0.1）

> 状态：W1 冻结。上游依据：旧版 06 号《现有代码体检与复用策略》（仍有效），本文件是 8 周口径下的执行版。
> 一句话：**毕设不是包袱，是数据底座。搬数据、借结构、参考交互，不搬业务，不碰旧代码。**

---

## 1 旧系统是什么

| 项 | 事实 |
| --- | --- |
| 位置 | E:\3 源码\1 源代码\Django_project_stream_medical |
| 后端 | Django + DRF + SimpleJWT，跑在 **8001**，库 ai250301（32 张表） |
| 前端 | 两套 uni-app：患者端 html_ye/medical（9 页）、医生端 html_ye/doctor（5 页） |
| AI | DashScope（qwen / qwen3-asr / qwen3-tts）+ LangGraph 症状问答 |
| 检索 | Milvus + Neo4j + Chroma（Docker，装不起来就 500） |
| 数据 | database/medical.sql（49MB）、data/*.xlsx（科室、排班、检查项目、发药、检验） |
| 测试 | 无自动化测试 |

**它在业务上不是陪诊**：所谓「陪诊」只是 prompt 里的一句自我称呼。所以这是「在医疗信息底座上新建陪诊域」，不是改造。

---

## 2 三条纪律

1. **不改旧系统一行代码**。要数据就导出，要实时就只读调用。
2. **业务逻辑一律新写**，不在 aichat 里加陪诊功能，也不复用它的状态流转。
3. **只读调用集中在 backend/adapters/legacy/**，将来下线只删一个目录。

---

## 3 复用什么（按价值排序）

| # | 资产 | 旧位置 | 新用途 | 方式 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | 检查项 + 院内方位（743 条） | aichat_departmentcheckitem（wzsm） | 检查规划引擎的位置数据、导航话术 | **已导出** fixtures/legacy/check_items.json | 完成 |
| 2 | 科室字典（33 个） | aichat_hospitalschedule.yjksmc | 科室选择、需求分类 | **已导出** departments.json | 完成 |
| 3 | 排班结构（rs 总号源 / fybz 余号源 / dateindex 唯一索引） | aichat_hospitalschedule | 号源中心：按此结构建新表，承载「科室-医生-日期-时段-余号」与扣减事务，**不复用旧表** | 借结构 | W2 |
| 4 | 排班样例（40 条，姓名已脱敏） | 同上 | 演示数据、W2 骨架联调 | **已导出** schedule_samples.json | 完成 |
| 5 | 短信验证码登录 | user/views.py send_code / sms_login | 用户端与家属端登录 | 抄逻辑，重写接口 | W3 |
| 6 | Excel 批量导入范式 | myfile/views.py upload | 后台上传科室/检查项 | 参考 | W4 |
| 7 | 审核后台单页 | static/audit/index.html | 开发期数据查看（不入交付范围） | 参考 | — |
| 8 | 两套 uni-app 页面（9 + 4 页） | html_ye/medical、html_ye/doctor | 用户端适老页面交互参考 | 参考交互，重写代码 | W2 |
| 9 | Celery + Redis 基座 | aiserver/celery.py | 推送、生成小结 | 直接沿用配置 | W4 |
| 10 | DashScope 调用封装 | aichat/ 里的调用代码 | W5 选型对比的参考实现 | 参考 | W5 |

**最值钱的是第 1 和第 3 项**：743 条检查项连院内位置都带着，这是从零做不出来的；号源扣减结构（`rs` 总号 / `fybz` 余号 / 事务内 UPDATE ... WHERE fybz > 0）可以直接套成「号源中心」，是设备端完成「确认挂号」这一步的真实底座。

---

## 4 明确不搬

| 资产 | 为什么不搬 |
| --- | --- |
| aichat/medical_agent.py（843 行 LangGraph） | 它的目标是「症状 → 科室 → 挂号」，陪诊要的是「状态机 → 任务 → 留痕」，几乎零重叠 |
| Milvus / Neo4j / Chroma / Reranker | 对陪诊主流程不是刚需，装不起来反而拖垮部署；知识图谱留作条件交付 C2 |
| AllowAny + csrf_exempt + 从 body 取 user_id | 任何人可冒充任意用户查病历，这是法律风险，不是代码风格问题 |
| 明文密码（passwd 字段） | 陪诊涉老人隐私，必须用 set_password |
| SECRET_KEY 派生 Fernet 落库 | 换密钥或改字段，历史数据全部解不开 |
| 外键全是裸 IntegerField | 挂号记录、医生、患者会出现孤儿数据 |
| 症状问答 / DiagnosisReport / checkpoints 三表 | 与陪诊域无关，且强绑 topic_id |

---

## 5 已导出的数据

| 文件 | 条数 | 字段 |
| --- | --- | --- |
| fixtures/legacy/check_items.json | 743 | id、category、item_code、item_name、body_part、location |
| fixtures/legacy/departments.json | 33 | name、schedule_rows |
| fixtures/legacy/schedule_samples.json | 40 | dept、doctor（脱敏）、title、date、total、remaining |
| fixtures/legacy/doctors.json | 60 | alias（医生-哈希4位）、title |

**脱敏规则**：医生姓名替换为「医生-<sha1 前 4 位>」，同一人前后一致；手机号、姓名、病史、诊断、就诊记录**一条都没导**。

**不导的四张表**：user_user、user_doctor、aichat_registrationrecord、chat / topic / checkpoints。

重新导出（换机器或数据更新时）：

~~~powershell
python tools/legacy/extract_seed.py --sql "E:/3 源码/1 源代码/Django_project_stream_medical/database/medical.sql"
~~~

脚本只读 .sql 文件，不连数据库，不需要旧系统跑起来。

---

## 6 只读适配器

位置：backend/adapters/legacy/client.py

| 项 | 规定 |
| --- | --- |
| 协议 | POST /ai/mixed/find_location/，body 为 {"check_query": "..."}（W1 读旧代码确认，不是 GET） |
| 返回 | {"code": 200, "data": [...]}；code 非 200 一律当不可用处理 |
| 超时 | 2 秒 |
| 重试 | 只对网络错误重试 1 次，业务错误不重试 |
| 失败 | 抛 LegacyUnavailable，调用方降级读 fixtures |
| 已知限制 | 该接口依赖 Milvus/Neo4j 混合检索，干净机器上必然返回 code 500「Retriever not initialized」 |

**降级必须可演示**：现场旧系统没开，流程也要能走完，所以降级路径有测试（见 backend/tests/test_legacy_client.py）。

### 6.1 旧系统可用路由（W1 读 urls.py 确认）

| 路由 | 方法 | 用途 | 能不能直接复用 |
| --- | --- | --- | --- |
| /ai/mixed/find_location/ | POST | 检查项查位置 | 依赖 Milvus，大概率 500，只作增强 |
| /ai/gh/schedules/ | GET | 排班查询 | 可参考，W2 决定是否接 |
| /ai/mixed/recommend_schedule/ | POST | 按科室推荐排班 | 依赖检索栈，不用 |
| /user/send_code/ | POST | 短信验证码 | 逻辑可抄，接口重写 |
| /user/sms_login/ | POST | 验证码登录 | 逻辑可抄，接口重写 |
| /myfile/uploads/ | POST | Excel 批量导入 | 范式可参考 |
| /ai/doctor/patients/ 等 | GET | 医生端接口 | 不接，本项目不做院内人员界面 |

---

## 7 风险与处置

| 风险 | 触发条件 | 处置 |
| --- | --- | --- |
| 旧系统端口或接口变了 | 换了机器、改了配置 | 适配器只认 LEGACY_BASE_URL 环境变量，改配置不改代码 |
| 旧库导不出来 | MySQL 没装、dump 损坏 | fixtures 已经进仓库，不依赖旧库 |
| 数据里混入真实患者信息 | 误导 registrationrecord 或 user 表 | 导出脚本写死表白名单，只认三张表 |
| 旧密钥已泄露 | .env 里曾有 AccessKey | W1 内全部轮换，旧 key 作废（06 号 S3） |
| 有人想「顺手改一下旧代码」 | 赶工期 | 违反纪律，评审直接退回 |

---

## 8 验收（W1 – W4）

| 周 | 验收项 | 判定 |
| --- | --- | --- |
| W1 | fixtures 进仓库，测试通过 | pytest 里 3 条 fixtures 用例全绿 |
| W1 | 旧密钥轮换完成 | 旧 key 调用返回鉴权失败 |
| W2 | 与旧系统联调一次 find_location | 真实返回能解析出房间号 |
| W3 | 排期表按 rs/fybz 结构建好 | 扣减有事务，并发测试不超卖 |
| W4 | 检查规划用到方位数据 | 规划结果里每条检查都带楼层与房间 |

---

## 9 与旧文档的关系

| 旧文档 | 处置 |
| --- | --- |
| medpal-plan/06-现有代码体检与复用策略 | 继续有效，作为背景与安全债清单 |
| 本文件 | 8 周口径下的执行版，冲突时以本文件为准 |
| 11 号 ADR-001（沿用既有底座） | 由 ADR-016 细化：底座只用数据与结构，不用其鉴权与业务 |
