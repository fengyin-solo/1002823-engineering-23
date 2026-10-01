.PHONY: install install-setup backend frontend prepare prepare-check test

# 安装前后端依赖（要求本机已有可用的 python3 -m venv / pip）。
install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

# 依赖自检 + 自动引导安装：缺 python3-venv / pip 也能引导到本地目录，装完自动复验；
# 缺依赖时停在安装这一步并打印缺什么。
install-setup:
	cd backend && ./scripts/bootstrap.sh
	cd frontend && npm install

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

# 苗木数据准备（可重复执行）：按品种导入示例数据 -> 自动核对 -> 就绪闸门 -> 日志留档。
# 退出码：0 通过已就绪；2 核对未通过（不算准备好）；5 数据文件错误。
prepare:
	cd backend && if [ -x .venv/bin/python ]; then .venv/bin/python -m app.scripts.prepare_cli; \
	  else PYTHONPATH=".pylibs:$$PYTHONPATH" python3 -m app.scripts.prepare_cli; fi

# 仅做依赖自检，不安装。
prepare-check:
	cd backend && python3 scripts/check_env.py

# 后端流水线单元测试（只用标准库，无需先装第三方依赖）。
test:
	cd backend && python3 -m unittest discover -s tests -v
