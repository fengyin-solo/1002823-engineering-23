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
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 苗木基地数据准备（可重复流程）

苗木基地的数据不再手工录本地库，整条准备流程固定为：

```text
依赖检查 → 读取示例数据（按培育品种分文件）→ 编号去重 → 出圃周期/数量自洽核对
        → 按苗圃编号首次导入 → 写 prepared.json / report.json → 核对日志留档
```

执行入口（CLI、安装脚本、页面接口是同一条流水线）：

```bash
cd backend
./prepare.sh                       # 装依赖 + 依赖检查 + 跑完整流程
.venv/bin/python -m app.seedprep.cli --check   # 只做依赖检查
.venv/bin/python -m app.seedprep.cli           # 只跑数据准备（JSON 输出加 --json）
```

页面上「苗木基地」模块有同名面板，可随时点「重新执行数据准备」并查看核对结果与日志。

### 文件约定

```text
backend/data/seedling/
├── catalog.json          品种目录：品种 → 出圃周期，是周期核对的唯一标准（随仓库走）
├── samples/<品种>.json   示例数据：按培育品种分文件，文件内品种必须与文件名一致
├── prepared.json         核对通过后准备好的数据，带签名（随仓库走，另一处环境取同一份）
└── report.json           最近一次核对报告：数量汇总、对不上的编号、签名（随仓库走）
backend/var/logs/seedling/  每次准备的核对日志，按时间戳留档 + latest.log（不随仓库走）
backend/var/seedling-store.json  本机页面操作（登记/状态流转）的运行期数据（不随仓库走）
```

### 固定口径（写死在一处）

- **数量**：`在圃数量 = 培育数量 - 出圃数量`，出圃数量与在圃数量冲突时
  **以出圃数量为准**。该口径只定义在 `app/seedprep/policy.py`
  （`QUANTITY_RULE_SOURCE`），核对、导入、页面登记共用同一份。
- **出圃周期**：同一培育品种的周期以 `catalog.json` 为准，示例里周期与目录不一致即对不上。

### 行为约定

- 依赖没装好时停在安装这一步：CLI 退出码 1 并逐项说明缺什么、怎么装；
  页面接口返回 503，原因直接显示在页面上。
- 核对不通过时**不导入、不算准备好**，`prepared.json` 保持上一版；
  报告与页面会列出对不上的苗圃编号与原因（缺字段、周期不符、数量对不上等）。
- 同一批示例中苗圃编号重复的只认第一次，后续记录跳过；
  重复跑流程时已存在的编号原样保留，不叠成两份，数据签名保持不变。
- 另一处环境克隆仓库后即使不跑流程，后端也直接使用随仓库的 `prepared.json`，
  取到的数量与这里完全一致（数量汇总见 `report.json`，条目带 SHA-256 签名）。
- 接口无响应或返回错误时，原因会记录在苗木基地页面的「接口异常留痕」横幅中，
  刷新后仍保留，直到手动清空。

### 测试

```bash
cd backend && .venv/bin/python -m unittest discover -s tests -v
```

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
| 苗木基地 | `seedling` | 苗圃 | 苗圃编号、苗圃名称、苗圃面积 |
| 水体养护 | `waterbody` | 水体 | 水体编号、水体类型、水体面积 |
| 名木古树 | `code` | 名木古树 | 古树编号、树种、树龄 |
| 市民热线 | `complaint` | 热线记录 | 记录编号、来电人、来电内容 |
| 季度养护方案 | `seasonplan` | 养护方案 | 方案编号、方案季度、覆盖绿地 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
