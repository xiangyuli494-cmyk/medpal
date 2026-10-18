# backend/apps —— Django 应用

会话链路、HTTP 接口、WebSocket consumer。

## 边界

- 这里可以有 Django、可以有 ORM；
- 但判断逻辑（能不能跃迁、话术怎么选、剂量要不要追问）必须调 domain，不许在视图里写 if；
- 任何查询都要带 episode 过滤（见 docs/specs/access-control.md）。

## 计划中的 app

| app | 负责 | 起始周 |
| --- | --- | --- |
| session | 会话编排、WS consumer | W3 |
| api | 用户端 / 家属端 / 工作台的 HTTP 接口 | W3 |
| admin-config | 运营配置（先用 Django Admin） | W4 |
