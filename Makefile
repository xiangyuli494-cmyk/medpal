.PHONY: help dev test test-e2e test-ai lint check

help:
	@echo "小暖陪诊 · 可用命令"
	@echo "  make dev       启动本地开发环境（SQLite + 假适配器）"
	@echo "  make test      运行 L1-L4 测试（目标 < 60 秒）"
	@echo "  make test-e2e  运行 Playwright 端到端测试"
	@echo "  make test-ai   运行 AI 评测集（需 API Key）"
	@echo "  make lint      代码规范检查"
	@echo "  make check     lint + test + 契约校验（= CI 本地版）"

dev:
	@echo "W2 起在此实现：启动后端 + 四端前端 + mock 推送面板"

test:
	pytest backend/tests -q --cov=backend/domain --cov-report=term-missing

test-e2e:
	@echo "W4 起在此实现：playwright test"

test-ai:
	@echo "W5 起在此实现：pytest backend/tests/eval -m eval"

lint:
	ruff check .
	@echo "前端 lint 在 W2 后接入"

check: lint test
