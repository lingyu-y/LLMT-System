# LLMT-System 项目记忆

## 项目概述
- 离线大数据训练与应用系统，课程设计项目
- 后端: FastAPI + Python 3.10 + PostgreSQL/InfluxDB/MinIO/Elasticsearch
- 前端: Vue 3 + Element Plus + ECharts
- 训练框架: LLMT-training (PyTorch + DeepSpeed + Megatron-LM)

## 关键架构
- 后端分层: API -> Service -> Repository -> Model
- 4 数据库: PostgreSQL (业务数据), InfluxDB (训练指标), MinIO (文件存储), Elasticsearch (日志检索)
- 训练异步执行: Celery + Redis broker
- 训练框架: LLMT-training/ 独立模块，可 pip install

## 训练框架结构 (LLMT-training/)
- config/schema.py: TrainingConfig 统一配置
- config/merger.py: 生成 DeepSpeed JSON / Megatron CLI args
- trainers/: PyTorchTrainer, DeepSpeedTrainer, MegatronTrainer
- models/: GPT, BERT providers + ModelRegistry
- data/: PretrainDataset, FinetuneDataset, MegatronDataset
- launcher/: Torchrun, DeepSpeed, Megatron 启动器
- reporting/: InfluxDB + PostgreSQL + MinIO 上报
- ReportingCallbackBridge: 统一回调适配器

## 数据库连接
- PostgreSQL: localhost:5432, db=llmt_system
- InfluxDB: localhost:8086, org=llmt, bucket=training_metrics
- MinIO: localhost:9000
- Elasticsearch: localhost:9200
- Redis: localhost:6379 (Celery broker)

## 用户偏好
- 用户说"只负责写代码即可，运行和测试我来做" – 不要主动运行/测试
