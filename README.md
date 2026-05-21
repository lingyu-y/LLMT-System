# LLMT-System

离线大数据训练与应用系统课程设计项目。

当前仓库包含两个主要目录：

- `LLMT-frontend`：Vue 3 + Vite + TypeScript 前端原型
- `LLMT-backend`：FastAPI 后端与数据层基础设施配置

## 前端启动

前端目录是 [LLMT-frontend](/home/cst/LLMT-System/LLMT-frontend)。

推荐先确认本机 Node.js 版本满足 `>= 20.19`，然后执行：

```bash
cd LLMT-frontend
npm install
npm run dev
```

启动后默认访问地址：

```text
http://127.0.0.1:5173/
```

当前前端已经实现以下页面，并可通过左侧菜单切换：

- 仪表盘
- 数据处理
- 模型训练
- 模型管理
- 文档生成
- 系统管理

## 前端常用命令

在 [LLMT-frontend/package.json](/home/cst/LLMT-System/LLMT-frontend/package.json) 中已配置：

```bash
cd LLMT-frontend

# 开发模式
npm run dev

# 生产构建
npm run build

# 本地预览构建产物
npm run preview

# 类型检查
npm run type-check

# 代码检查
npm run lint
```

## 后端说明

后端目录是 [LLMT-backend](/home/cst/LLMT-System/LLMT-backend)。

当前后端已经完成基础配置：

- 统一配置类 `Settings`
- PostgreSQL / InfluxDB / MinIO / Elasticsearch 连接封装
- 健康检查接口
- Docker Compose 本地数据服务配置

如果需要启动后端依赖服务：

```bash
cd LLMT-backend
docker compose --env-file .env up -d
```

如果需要初始化四类后端存储：

```bash
cd LLMT-backend
conda activate llmt-backend
python scripts/init_datastores.py
```

这个脚本会自动：

- 执行 PostgreSQL 迁移
- 初始化 InfluxDB bucket
- 初始化 MinIO buckets
- 初始化 Elasticsearch 日志 index

后端健康检查接口：

```text
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/health/databases
```

## 目录结构

```text
LLMT-System/
├── LLMT-frontend/
├── LLMT-backend/
├── index.html
└── README.md
```
