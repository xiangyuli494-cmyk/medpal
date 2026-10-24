# 评测集 v0（10 条）

格式：每行一个 JSON 对象。

| 字段 | 含义 |
| --- | --- |
| id | 题号，稳定不变 |
| question | 自然语言问题 |
| gold.dept | 金标准建议科室；空字符串表示本应拒答 |
| gold.exams | 金标准检查项列表 |
| gold.conflicts | 应被识别出的冲突实体 |
| gold.out_of_scope | true 表示正确答案是「超出覆盖范围」 |
| gold_evidence | 金标准证据锚点（三元组 id 或 asset anchor） |
| hops | 需要的最少跳数 |
| difficulty | easy / medium / hard / negative |

规模规划：赛前扩到 50 条 = 本文件 10 条 + 原有 125 个测试用例改写 30 条 + 新写多跳 15 条 + 反例 5 条（本文件已含 2 条反例，作为写法样板）。

反例题的判定：只要智能体输出「超出覆盖范围」或「证据不足 + 缺口清单」，即算正确；给出具体科室算错误。
