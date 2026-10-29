# W1-T6-PYTEST-CI 交接单
## 任务简述
新增 GitHub Actions pytest CI 流水线，发起PR或者推代码到feat分支时自动运行pytest单元测试。

## 修改内容
1. 新增文件：.github/workflows/pytest.yml
2. 配置：触发后自动拉取代码、安装依赖、执行 make test

## 验证方式
手工核对yml语法正确；提交分支后，触发CI，观察pytest任务正常拉起。

## 风险
仅新增CI配置，不改动业务代码；CI测试失败会阻断PR合并。
