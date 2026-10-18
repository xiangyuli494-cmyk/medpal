# backend/tests —— 测试

| 目录 | 内容 |
| --- | --- |
| tests/ | 领域层与接口的单元测试 |
| tests/eval/ | AI 评测集（W5 起） |

## 跑法

~~~powershell
make test          # Windows 没有 make 时：
python -m pytest backend/tests -q --cov=backend/domain --cov-report=term-missing
~~~

## 约定

- 测试默认不联网、不用真 Key、不读数据库；
- 每个缺陷先写一条会失败的用例，再修；
- 领域层覆盖率 100%，新增代码覆盖率 80%。
