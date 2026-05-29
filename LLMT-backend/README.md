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

完成数据库和存储初始化后，主后端和在线推理服务分开启动。主后端负责鉴权、数据库、
训练任务和模型版本管理；推理服务单独加载模型权重，避免大模型推理把主后端进程拖垮。

先确认 `.env` 中配置了独立推理服务地址和推理保护参数：

```env
LLMT_INFERENCE_SERVICE_URL=http://127.0.0.1:8001
LLMT_INFERENCE_MAX_CHECKPOINT_MB=2048
LLMT_INFERENCE_CACHE_SIZE=0
LLMT_INFERENCE_DEVICE=cpu
```

终端 1：启动主后端：

```bash
conda activate llmt-backend
uvicorn app.main:app --reload --port 8000
```

终端 2：启动独立推理服务：

```bash
conda activate llmt-backend
uvicorn app.inference_service:app --host 127.0.0.1 --port 8001
```

默认地址：

```text
主后端：http://127.0.0.1:8000
推理服务：http://127.0.0.1:8001
```

健康检查：

```bash
curl --noproxy '*' http://127.0.0.1:8000/api/v1/health
curl --noproxy '*' http://127.0.0.1:8001/health
```

如果开发机开启了系统代理/梯子，请确保本地地址直连，不走代理：

```bash
export NO_PROXY=localhost,127.0.0.1,::1
export no_proxy=localhost,127.0.0.1,::1
```

主后端转发到推理服务时会忽略代理环境变量；浏览器和终端仍建议把 `localhost`、
`127.0.0.1` 加到代理绕过列表，避免前端开发代理返回 502。

## Clair 镜像漏洞扫描

`docker-compose.yml` 已包含独立的 `clair-postgres`。镜像版 `clair` 服务已放入
`clair-image` profile，默认 `docker compose up -d` 不会启动它，避免本地二进制模式下
重复拉取 Clair 镜像。如果已经在本机下载并编译了 Clair 二进制，推荐使用本节的
“本地二进制启动”方式。

### 本地二进制启动 Clair

终端 1：启动 Clair 数据库：

```bash
cd /home/cst/LLMT-System/LLMT-backend
docker compose up -d clair-postgres
```

也可以启动项目其它数据服务：

```bash
docker compose --env-file .env up -d
```

这条命令默认不会启动镜像版 Clair。

终端 2：启动本地 Clair。保持这个终端不要关闭：

```bash
/home/cst/clair-v4.9.0/clair \
  -conf /home/cst/LLMT-System/LLMT-backend/clair/config.local.yaml \
  -mode combo
```

终端 3：检查 Clair 是否可访问：

```bash
curl --noproxy '*' http://127.0.0.1:6060/openapi/v1
```

后端 `.env` 中启用真实扫描：

```env
CLAIR_SCAN_ENABLED=true
CLAIR_API_URL=http://127.0.0.1:6060
CLAIR_SCAN_TIMEOUT_SECONDS=120
CLAIR_SIMULATION_FALLBACK=false
CLAIR_REGISTRY_SCHEME=http
CLAIR_REGISTRY_INSECURE=true
```

如果镜像仓库需要认证，可配置二选一：

```env
CLAIR_REGISTRY_AUTH_HEADER=Bearer <token>
# 或
CLAIR_REGISTRY_USERNAME=<username>
CLAIR_REGISTRY_PASSWORD=<password>
```

扫描时在模型管理页面的“容器镜像漏洞扫描”输入镜像地址，例如：

```text
registry.local:5000/llmt/model-api:v1
```

也可以把镜像地址存入模型元数据 `hyperparams_json.image_ref` 或
`hyperparams_json.container_image`，页面会自动带出。Clair 必须能访问该镜像仓库和 layer
blob 地址；如果仓库运行在同一个 compose 网络中，建议使用服务名而不是 `localhost`。

### 构建并推送推理服务镜像

如果当前只有模型版本、还没有模型服务镜像，可以先构建推理服务镜像。模型权重仍从
MinIO 加载，镜像里放的是推理运行环境。

先确认本地镜像是否已存在：

```bash
docker images | grep llmt-inference
```

如果没有，先构建：

```bash
cd /home/cst/LLMT-System
docker build -f LLMT-backend/Dockerfile.inference -t llmt-inference:v1 .
```

启动本地 registry。如果已存在 `local-registry`，这步会提示冲突，可跳过：

```bash
docker run -d -p 5000:5000 --name local-registry registry:2
```

`local-registry` 是后台 Docker 容器，不需要额外占用一个终端。后续只需启动已有容器：

```bash
docker start local-registry
```

检查 registry 是否可访问：

```bash
curl --noproxy '*' http://127.0.0.1:5000/v2/
```

正常会返回：

```json
{}
```

给镜像打 registry tag 并推送：

```bash
docker tag llmt-inference:v1 127.0.0.1:5000/llmt/inference:v1
docker push 127.0.0.1:5000/llmt/inference:v1
```

检查镜像是否已推送到 registry：

```bash
curl --noproxy '*' http://127.0.0.1:5000/v2/_catalog
curl --noproxy '*' http://127.0.0.1:5000/v2/llmt/inference/tags/list
```

如果 `docker push` 报：

```text
An image does not exist locally with the tag: localhost:5000/llmt/inference
```

说明还没有执行 `docker tag`，或前面的 `docker build` 没有成功。按顺序重新执行：

```bash
docker images | grep llmt-inference
docker tag llmt-inference:v1 127.0.0.1:5000/llmt/inference:v1
docker push 127.0.0.1:5000/llmt/inference:v1
```

前端模型管理页填写：

```text
127.0.0.1:5000/llmt/inference:v1
```

### 重启后端并扫描

修改 `.env` 后需要重启后端：

```bash
cd /home/cst/LLMT-System/LLMT-backend
uvicorn app.main:app --reload --port 8000
```

前端扫描报告中 `scanner` 显示 `clair` 表示真实 Clair 扫描成功；如果报错，按错误信息检查
Clair 进程、镜像仓库、镜像 tag 和 registry 连通性。

## 登录与注册

后端启动时会自动补齐开发环境基础角色、菜单和系统管理员账号：

```text
用户名：admin
密码：admin123
```

普通用户可以通过前端注册页自助注册，默认分配普通用户角色，可访问仪表盘和文档生成模块。

健康检查接口：

```text
http://127.0.0.1:8000/api/v1/health
http://127.0.0.1:8000/api/v1/health/databases
```

## 数据层说明

当前项目包含 4 类数据存储：

- PostgreSQL：结构化业务数据，使用 Alembic 管理表结构迁移
- InfluxDB：训练过程时序指标
- MinIO：数据集、模型、Checkpoint、导出文件的对象存储
- Elasticsearch：系统日志、操作日志、训练日志、异常日志检索
