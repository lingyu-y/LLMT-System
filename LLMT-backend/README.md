# LLMT Backend

离线大数据训练与应用系统后端项目，基于 FastAPI、SQLAlchemy、PostgreSQL，并集成 InfluxDB、MinIO、Elasticsearch。

## 本地启动

先启动 4 类本地数据服务：

```bash
docker compose --env-file .env up -d
```

再初始化 PostgreSQL、InfluxDB、MinIO、Elasticsearch：

```bash
conda activate llmt-backend
python scripts/setup_llmt_training_link.py
python scripts/init_datastores.py
```

这个初始化脚本会自动完成：

- 执行 `alembic upgrade head`
- 检查并创建 InfluxDB bucket
- 检查并创建 MinIO buckets
- 检查并创建 Elasticsearch 日志 index

`setup_llmt_training_link.py` 会在仓库根目录创建/修复 `llmt_training -> LLMT-training`，
用于让后端、DataLoader 子进程和训练任务都能 import `llmt_training`。也可以改用
editable 安装：

```bash
pip install -e ../LLMT-training
```

如果只想跳过其中某一步，也可以使用可选参数：

```bash
python scripts/init_datastores.py --skip-elasticsearch
python scripts/init_datastores.py --skip-postgres
```

## 运行后端

完成数据库和存储初始化后，可以启动 FastAPI：

```bash
conda activate llmt-backend
uvicorn app.main:app --reload
```

默认接口地址：

```text
http://127.0.0.1:8000
```

## 登录与注册

后端启动时会自动补齐开发环境基础角色、菜单和系统管理员账号：

```text
用户名：admin
密码：admin123
```

普通用户可以通过前端注册页自助注册，默认分配普通用户角色，可访问仪表盘和文档生成模块。

健康检查接口：

```text
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/health/databases
```

## 数据层说明

当前项目包含 4 类数据存储：

- PostgreSQL：结构化业务数据，使用 Alembic 管理表结构迁移
- InfluxDB：训练过程时序指标
- MinIO：数据集、模型、Checkpoint、导出文件的对象存储
- Elasticsearch：系统日志、操作日志、训练日志、异常日志检索
