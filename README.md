# 园林绿化养护管理平台

面向城市园林绿化植物的栽植养护、修剪造型、病虫害防治、灌溉施肥与绿地巡查的一体化绿化管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   ├── app/seedling_pipeline/ 苗木数据准备流水线（示例数据/核对/台账/日志）
│   ├── app/store.py          内存数据仓库与示例数据
│   ├── scripts/check_env.py  依赖自检（标准库，缺依赖停在安装步）
│   └── scripts/bootstrap.sh  自检 -> 安装 -> 复验
├── Makefile
├── .gitignore
└── docker-compose.yml
```

## 启动

### 依赖自检与安装（缺依赖会停在安装步）

```bash
make install-setup        # 推荐：先自检缺什么，再自动引导安装，装完复验
# 或只处理后端：
cd backend && ./scripts/bootstrap.sh
```

- 自检脚本 `backend/scripts/check_env.py` 只用标准库，逐个核对 `requirements.txt`；
  缺依赖时会明确打印**缺哪个包、怎么装**，并以退出码 3 停止——流程停在安装这一步，不会带病往下跑。
- 精简环境没有 `python3-venv`/`pip` 时，`bootstrap.sh` 会自动用 `get-pip.py` 引导到
  后端本地目录 `.pylibs/`（不污染系统 Python）。
- 单独自检：`make prepare-check`。

### 后端

```bash
cd backend
./run.sh                  # 启动前先过依赖闸门；缺依赖会拒绝启动并说明缺什么
```

健康检查：`curl http://127.0.0.1:8000/api/health`，返回里 `seedling_ready` 表示
苗木数据是否已核对通过、准备就绪。

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。
前端在后端不可达时会在页面上用红色横幅保留**接口无响应的具体原因**（未启动/超时/HTTP 错误码）。

## 苗木基地数据准备（可重复流程）

苗木数据不再靠人工往本地库里录，而是走一段可重复执行的流水线
（`backend/app/seedling_pipeline/`）：

```
示例数据(按品种分组 JSON) → 规范化 → 幂等导入 → 自动核对 → 就绪闸门 → 台账/日志留档
```

命令行：

```bash
make prepare              # 或 cd backend && .venv/bin/python -m app.scripts.prepare_cli
make test                 # 流水线单元测试（标准库，无需第三方依赖）
```

页面上「苗木基地」也有「重新执行数据准备 / 查看核对日志」按钮；后端接口：

| 接口 | 作用 |
| --- | --- |
| `POST /api/seedling/prepare/run` | 重跑一遍导入 + 自动核对 |
| `GET  /api/seedling/prepare/status` | 是否就绪、各品种数量、checksum 指纹、对不上的编号 |
| `GET  /api/seedling/prepare/log` | 最近一次核对日志全文（留档） |

关键约定（每条都对应固定的一处代码，不散落）：

- **示例数据按培育品种分组**：`app/seedling_pipeline/data/seedling_samples.json` 的
  `varieties` 表，导入时按品种名确定性排序拍平。
- **出圃周期与在圃数量自洽**：品种口径是唯一事实源 `catalog.py`，
  `标准在圃数量 = 每批株数 × 出圃周期月数`；出圃周期不符或在圃数量不符都会被核对拦下。
- **以出圃数量为准写死在一处**：`catalog.QUANTITY_AUTHORITY = "出圃数量"`，
  数量对不上时一律以出圃数量回推在圃数量，日志/接口/页面都引用这同一个常量。
- **导入后自动核对、不过不算就绪**：`reconcile.py` 逐条核对，不通过时 `ready=false`，
  并把**对不上的苗圃编号**列入 `mismatch_codes` 与日志；此时台账与运行数据都不更新。
- **重复导入同一编号只认第一次**：按苗圃编号幂等（`importer.apply_to_store` 与准备台账
  `var/seedling_prepare/manifest.json`），重复编号跳过，绝不叠成两份。
- **换环境得到同一份**：示例数据与台账都是确定性 JSON，数量指纹 `checksum`
  （对编号/品种/周期/出圃/在圃/计划做 SHA-256）在任何机器上一致，可用于核对"是不是同一份"。
- **核对日志留档**：每次运行写到 `backend/logs/seedling_prepare/`（带时间戳的明细 +
  `latest.log` / `latest.json`）。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 绿地台账 | `plot` | 绿地 | 绿地编号、绿地名称、所属区域 |
| 乔木管理 | `tree` | 乔木 | 树木编号、树种名称、胸径 |
| 灌木管理 | `shrub` | 灌木 | 灌木编号、品种名称、栽植面积 |
| 草坪管理 | `lawn` | 草坪 | 草坪编号、草种类型、草坪面积 |
| 花卉造景 | `flower` | 花卉造景 | 造景编号、造景主题、花卉品种 |
| 病虫害防治 | `pest` | 防治记录 | 防治编号、受害植物、病虫种类 |
| 灌溉作业 | `irrigation` | 灌溉任务 | 灌溉编号、灌溉区域、灌溉方式 |
| 施肥作业 | `fertilize` | 施肥记录 | 施肥编号、施肥区域、肥料类型 |
| 修剪造型 | `prune` | 修剪任务 | 修剪编号、修剪对象、修剪类型 |
| 绿地巡查 | `patrol` | 巡查记录 | 巡查编号、巡查区域、巡查日期 |
| 杂草清除 | `weed` | 除草任务 | 除草编号、除草区域、杂草种类 |
| 树木支撑 | `support` | 支撑设施 | 支撑编号、所属树木、支撑方式 |
| 苗木移植 | `transplant` | 移植记录 | 移植编号、移植树种、移植数量 |
| 园建设施 | `facility` | 园建设施 | 设施编号、设施名称、设施类型 |
| 园林机械 | `equipment` | 园林机械 | 机械编号、机械名称、规格型号 |
| 苗木基地 | `seedling` | 苗圃 | 苗圃编号、培育品种、出圃周期、出圃数量、在圃数量、计划总量 |
| 水体养护 | `waterbody` | 水体 | 水体编号、水体类型、水体面积 |
| 名木古树 | `code` | 名木古树 | 古树编号、树种、树龄 |
| 市民热线 | `complaint` | 热线记录 | 记录编号、来电人、来电内容 |
| 季度养护方案 | `seasonplan` | 养护方案 | 方案编号、方案季度、覆盖绿地 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
