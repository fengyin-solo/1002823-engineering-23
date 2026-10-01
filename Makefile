.PHONY: install backend frontend prepare test

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

# 苗木基地数据准备：依赖检查 → 按品种读取示例数据 → 自洽核对 → 首次导入 → 日志留档
prepare:
	cd backend && ./prepare.sh

test:
	cd backend && .venv/bin/python -m unittest discover -s tests -v
