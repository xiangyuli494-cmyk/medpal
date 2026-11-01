# 模块：pytest CI流水线
## 一句话说清它干什么
新增pytest CI工作流，PR和push时自动执行单元测试，失败会阻断合并。

## 数据流
PR提交 / 代码push → 触发GitHub Actions → 拉取代码 → 安装依赖 → 执行make test → 回传测试结果，失败标记CI不通过。

## 我改了什么（人工修改点）
1. 在 .github/workflows 新增 pytest.yml，配置pull_request、push触发
2. 编写本交接单，用于handoff校验

## 怎么验证的
1. 检查yml语法无报错
2. 提交分支后可以正常触发CI任务
3. 等待CI自动运行pytest测试
