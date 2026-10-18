.PHONY: help dev test lint check handoff mock-api mock-ws

help:
	@echo 小暖陪诊 · 可用命令
	@echo   make dev        起 mock 接口(8000)与 mock 会话(8090)
	@echo   make test       跑单元测试（Windows 用 python -m pytest）
	@echo   make lint       代码规范检查
	@echo   make check      lint + 红线 + 测试（= 本地版 CI）
	@echo   make handoff    生成一份模块交接单

dev:
	python tools/mock_api.py & python tools/mock_ws.py

mock-api:
	python tools/mock_api.py

mock-ws:
	python tools/mock_ws.py

lint:
	ruff check .

test:
	python -m pytest backend/tests --cov=backend/domain --cov-report=term-missing

check: lint
	python tools/check_guard_words.py
	python tools/check_handoff.py
	python -m pytest backend/tests

handoff:
	python tools/new_handoff.py --module $(MODULE) --owner $(OWNER) --week $(WEEK)
