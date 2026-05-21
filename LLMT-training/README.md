# LLMT-Training

集成 PyTorch、DeepSpeed、Megatron-LM 的统一训练框架。

## 目录结构

```
LLMT-training/
├── config/                     # 配置管理
│   ├── schema.py               # 统一配置模型 (TrainingConfig)
│   ├── merger.py               # 配置转换 (→ DeepSpeed JSON / Megatron CLI)
│   ├── validator.py            # 配置交叉校验
│   └── defaults/               # 预置配置模板
│       ├── deepspeed_zero1.json
│       ├── deepspeed_zero2.json
│       ├── deepspeed_zero3.json
│       ├── deepspeed_zero3_offload.json
│       ├── megatron_gpt_345m.yml
│       └── megatron_bert_345m.yml
├── core/                       # 核心抽象
│   ├── state.py                # TrainingState (训练状态跟踪)
│   ├── callbacks.py            # TrainingCallback + CallbackList (生命周期回调)
│   ├── base_trainer.py         # BaseTrainer (训练器抽象基类)
│   ├── base_model.py           # BaseModelProvider (模型提供者抽象基类)
│   └── base_dataset.py         # BaseDataset (数据集抽象基类)
├── trainers/                   # 训练器实现
│   ├── pytorch_trainer.py      # PyTorch DDP 训练器
│   ├── deepspeed_trainer.py    # DeepSpeed ZeRO 训练器
│   ├── megatron_trainer.py     # Megatron-LM 训练器 (含 stub 模式)
│   └── factory.py              # create_trainer() 工厂函数
├── models/                     # 模型提供者
│   ├── gpt_provider.py         # GPT-2 (自回归预训练)
│   ├── bert_provider.py        # BERT (MLM + 分类)
│   └── registry.py             # ModelRegistry (模型注册表)
├── data/                       # 数据集
│   ├── pretrain_dataset.py     # 预训练数据集 (npy/bin 格式)
│   ├── finetune_dataset.py     # 微调数据集 (JSONL 格式)
│   ├── megatron_dataset.py     # Megatron 数据集适配器
│   └── data_utils.py           # DataLoader 构建 + 数据集工厂
├── launcher/                   # 分布式启动器
│   ├── torchrun_launcher.py    # torchrun 启动 (PyTorch DDP)
│   ├── deepspeed_launcher.py   # deepspeed CLI 启动
│   ├── megatron_launcher.py    # torchrun + Megatron 参数启动
│   └── factory.py              # create_launcher() 工厂函数
├── reporting/                  # 训练上报
│   ├── influxdb_writer.py      # InfluxDB 指标批量写入
│   ├── postgres_status.py      # PostgreSQL 状态更新
│   ├── minio_checkpointer.py   # MinIO 检查点管理
│   └── callback_bridge.py      # ReportingCallbackBridge (统一上报回调)
├── cli/                        # 命令行工具
│   ├── main.py                 # CLI 入口
│   └── train_cmd.py            # train / eval 子命令
├── examples/                   # 示例脚本
│   ├── gpt_pretrain.py         # GPT-2 预训练示例
│   ├── bert_finetune.py        # BERT 微调示例
│   └── configs/                # 示例配置文件
│       ├── gpt2_pretrain_deepspeed.json
│       └── bert_finetune_pytorch.json
├── tests/                      # 单元测试
│   ├── test_config.py          # 配置系统测试
│   ├── test_core.py            # 核心抽象测试
│   └── test_data.py            # 数据集测试
├── setup.py                    # pip 安装包配置
└── pyproject.toml              # 项目元数据
```

## 支持的训练策略

| 框架 | 策略 | 说明 |
|------|------|------|
| PyTorch | `ddp` | DistributedDataParallel 数据并行 |
| DeepSpeed | `zero1` | ZeRO Stage 1 (优化器分片) |
| DeepSpeed | `zero2` | ZeRO Stage 2 (优化器+梯度分片) |
| DeepSpeed | `zero3` | ZeRO Stage 3 (全参数分片) |
| DeepSpeed | `zero3_offload` | ZeRO Stage 3 + CPU Offload |
| Megatron | `tp` | 张量并行 (Tensor Parallelism) |
| Megatron | `pp` | 流水线并行 (Pipeline Parallelism) |
| Megatron | `3d` | 3D 并行 (DP + TP + PP) |

## 安装

```bash
# 基础安装 (PyTorch 训练)
pip install -e .

# DeepSpeed 支持
pip install -e ".[deepspeed]"

# 上报功能 (InfluxDB + MinIO)
pip install -e ".[reporting]"

# 全部安装
pip install -e ".[all]"
```

> Megatron-LM 需要从源码安装，参考 [NVIDIA/Megatron-LM](https://github.com/NVIDIA/Megatron-LM)。

## 快速开始

### 1. 通过 API 启动训练

后端系统提供了完整的训练管理 API，可通过 HTTP 请求创建和管理训练任务：

```bash
# 创建训练任务
curl -X POST http://localhost:8000/api/training/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "task_name": "GPT-2 预训练",
    "dataset_id": 1,
    "framework": "deepspeed",
    "parallel_strategy": "zero2",
    "config": {
      "model_type": "gpt2",
      "hidden_size": 768,
      "num_layers": 12,
      "num_attention_heads": 12,
      "batch_size": 8,
      "learning_rate": 2e-5,
      "max_epochs": 3,
      "num_gpus": 4
    }
  }'

# 查看训练状态
curl http://localhost:8000/api/training/tasks/1 \
  -H "Authorization: Bearer <token>"

# 查看训练指标
curl "http://localhost:8000/api/training/tasks/1/metrics?metric_type=training_step&window=30s" \
  -H "Authorization: Bearer <token>"

# 取消训练
curl -X POST http://localhost:8000/api/training/tasks/1/cancel \
  -H "Authorization: Bearer <token>"
```

### 2. 通过 CLI 启动训练

```bash
# 安装后获得 llmt-train 命令
llmt-train train --config examples/configs/gpt2_pretrain_deepspeed.json

# 指定框架和策略
llmt-train train -c config.json -f pytorch -s ddp

# 评估检查点
llmt-train eval -c config.json --checkpoint ./checkpoints/step-1000.pt
```

### 3. 通过 Python 脚本启动

```python
from app.training.config.schema import TrainingConfig
from app.training.config.validator import ConfigValidator
from app.training.core.callbacks import CallbackList
from app.training.core.state import TrainingState
from app.training.models.registry import ModelRegistry
from app.training.data.data_utils import create_dataset_from_config, build_dataloaders
from app.training.trainers.factory import create_trainer
from app.training.reporting.callback_bridge import ReportingCallbackBridge

# 构建配置
config = {
    "task_code": "my-training",
    "framework": "deepspeed",
    "parallel_strategy": "zero2",
    "model": {"model_type": "gpt2", "vocab_size": 50257, "hidden_size": 768, "num_layers": 12, "num_attention_heads": 12, "seq_length": 1024},
    "data": {"dataset_path": "data/tokens.npy", "dataset_format": "npy"},
    "hyperparams": {"batch_size": 8, "learning_rate": 2e-5, "max_epochs": 3, "precision": "fp16"},
    "strategy": {"num_gpus": 1},
    "checkpoint": {"save_interval": 500, "checkpoint_dir": "./checkpoints"},
    "reporting": {},
}

# 校验
tc = TrainingConfig(**config)
result = ConfigValidator.validate(tc)
assert result.valid, f"Config errors: {result.errors}"

# 构建
provider = ModelRegistry.get("gpt2")
model = provider.get_model(config)
loss_fn = provider.get_loss_fn(config)

dataset = create_dataset_from_config(config)
train_loader, eval_loader = build_dataloaders(dataset, config)

state = TrainingState(task_code=config["task_code"], max_epochs=3)
callback = ReportingCallbackBridge.from_config(config)
callbacks = CallbackList([callback])

trainer = create_trainer(
    framework="deepspeed", parallel_strategy="zero2", config=config,
    model=model, train_dataloader=train_loader, eval_dataloader=eval_loader,
    callbacks=callbacks, state=state, loss_fn=loss_fn,
)

# 训练
final_state = trainer.train()
print(f"Training finished: {final_state.status}, steps={final_state.global_step}")
```

## 配置系统

### TrainingConfig 统一模型

所有训练参数通过 `TrainingConfig` 统一管理，包含 6 个子配置：

```python
class TrainingConfig(BaseModel):
    task_code: str                     # 任务编号
    framework: "pytorch" | "deepspeed" | "megatron"
    parallel_strategy: "ddp" | "zero1" | "zero2" | "zero3" | "zero3_offload" | "tp" | "pp" | "3d"

    model: ModelConfig                 # 模型架构 (vocab_size, hidden_size, num_layers, ...)
    data: DataConfig                   # 数据加载 (dataset_path, format, split, ...)
    hyperparams: HyperParamsConfig     # 超参数 (batch_size, lr, epochs, optimizer, ...)
    strategy: StrategyConfig           # 并行策略 (num_gpus, zero_stage, tp_size, pp_size, ...)
    checkpoint: CheckpointConfig       # 检查点 (save_interval, max_checkpoints, ...)
    reporting: ReportingConfig         # 指标上报 (influxdb_url, bucket, ...)

    deepspeed_overrides: dict | None   # DeepSpeed 配置覆盖
    megatron_overrides: dict | None    # Megatron 参数覆盖
```

### 配置转换

`ConfigMerger` 自动将统一配置转为框架特定格式：

```python
from app.training.config.merger import ConfigMerger

tc = TrainingConfig(framework="deepspeed", parallel_strategy="zero2")

# 生成 DeepSpeed JSON 配置
ds_json = ConfigMerger.to_deepspeed_json(tc)

# 生成 Megatron CLI 参数列表
megatron_args = ConfigMerger.to_megatron_args(tc)
```

### 配置校验

`ConfigValidator` 检查配置兼容性：

```python
from app.training.config.validator import ConfigValidator

result = ConfigValidator.validate(tc)
print(result.valid)       # True/False
print(result.errors)      # ["ZeRO 与张量并行不兼容", ...]
print(result.warnings)    # ["Megatron 建议至少启用 TP 或 PP", ...]
```

校验规则包括：
- ZeRO + 张量并行不兼容（DeepSpeed 框架下）
- 并行度不能超过 GPU 总数
- GPU 总数必须能被并行度整除
- `hidden_size` 必须能被 `num_attention_heads` 整除
- PyTorch 框架不支持 ZeRO / TP / PP
- 学习率、batch_size 等超参合法性

## 生命周期回调

`TrainingCallback` 提供 7 个 Hook 点：

| Hook | 触发时机 | 典型用途 |
|------|----------|----------|
| `on_train_begin` | 训练开始 | 初始化上报，标记状态为 running |
| `on_train_end` | 训练结束 | 刷新指标，标记 completed/failed |
| `on_epoch_begin` | 每个 epoch 开始 | — |
| `on_epoch_end` | 每个 epoch 结束 | — |
| `on_step_end` | 每步训练结束 | 写 InfluxDB 指标，更新 PostgreSQL 进度 |
| `on_checkpoint` | 保存检查点时 | 上传 MinIO |
| `on_error` | 发生错误时 | 刷新指标，标记 failed |

`CallbackList` 将多个回调聚合为一个。

## 训练上报

`ReportingCallbackBridge` 是统一上报入口，将训练过程数据同时写入三个存储：

```
TrainingStep ──→ InfluxDB (loss, lr, grad_norm, GPU 指标)
Status Update ─→ PostgreSQL (epoch, step, status, error)
Checkpoint  ──→ MinIO (模型检查点文件上传/下载)
```

## Megatron Stub 模式

当 Megatron-LM 未安装时，`MegatronTrainer` 自动切换到 stub 模式——运行模拟训练循环（生成模拟 loss），不依赖实际数据和模型。这在开发和测试环境下很有用，可以验证配置、回调、上报链路是否正常。

## 测试

### 运行单元测试

```bash
# 安装测试依赖
pip install pytest torch numpy

# 运行全部测试
pytest tests/ -v

# 运行特定模块
pytest tests/test_config.py -v    # 配置系统
pytest tests/test_core.py -v      # 核心抽象
pytest tests/test_data.py -v      # 数据集
```

### 测试覆盖范围

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_config.py` | TrainingConfig 默认值、策略同步、ConfigMerger DeepSpeed/Megatron 输出、ConfigValidator 校验规则 |
| `test_core.py` | TrainingState 序列化、CallbackList 分发、GPT/BERT 前向传播、ModelRegistry 注册 |
| `test_data.py` | PretrainDataset npy 加载、FinetuneDataset JSONL 加载、create_dataset_from_config 工厂 |

### 手动验证流程

**1. 验证配置系统（无需 GPU）：**

```python
# test_config_manual.py
from app.training.config.schema import TrainingConfig, StrategyConfig, ModelConfig
from app.training.config.merger import ConfigMerger
from app.training.config.validator import ConfigValidator
import json

# 测试默认配置
tc = TrainingConfig()
print(f"Default: framework={tc.framework}, strategy={tc.parallel_strategy}")

# 测试 ZeRO2 配置 → DeepSpeed JSON
tc = TrainingConfig(framework="deepspeed", parallel_strategy="zero2",
                    strategy=StrategyConfig(num_gpus=4))
ds = ConfigMerger.to_deepspeed_json(tc)
print(json.dumps(ds, indent=2))

# 测试无效配置 → 校验报错
tc = TrainingConfig(framework="pytorch",
                    strategy=StrategyConfig(zero_stage=2))
result = ConfigValidator.validate(tc)
print(f"Valid: {result.valid}, Errors: {result.errors}")
```

**2. 验证模型前向传播（需 CPU 即可）：**

```python
# test_model_manual.py
import torch
from app.training.models.gpt_provider import GPTModel, GPTConfig
from app.training.models.bert_provider import BertModel, BertConfig

# GPT-2 小模型
gpt = GPTModel(GPTConfig(vocab_size=100, hidden_size=64, num_layers=2,
                         num_attention_heads=4, seq_length=32))
out = gpt(torch.randint(0, 100, (2, 32)))
print(f"GPT output shape: {out.logits.shape}")  # (2, 32, 100)

# BERT 小模型
bert = BertModel(BertConfig(vocab_size=100, hidden_size=64, num_layers=2,
                            num_attention_heads=4, intermediate_size=256,
                            max_position_embeddings=32))
out = bert(torch.randint(0, 100, (2, 16)))
print(f"BERT output shape: {out.logits.shape}")  # (2, 16, 100)
```

**3. 验证数据集加载：**

```python
# test_data_manual.py
import numpy as np
import tempfile, os
from app.training.data.pretrain_dataset import PretrainDataset
from app.training.data.finetune_dataset import FinetuneDataset

# 创建临时 npy 数据
with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as f:
    np.save(f.name, np.arange(2000, dtype=np.int64))
    ds = PretrainDataset.from_config({
        "data": {"dataset_path": f.name, "dataset_format": "npy"},
        "model": {"seq_length": 128},
    })
    sample = ds[0]
    print(f"input_ids: {sample['input_ids'].shape}, labels: {sample['labels'].shape}")
    os.unlink(f.name)

# 创建临时 JSONL 数据
with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
    for i in range(10):
        f.write(f'{{"text": "sample {i}"}}\n')
    ds = FinetuneDataset.from_config({
        "data": {"dataset_path": f.name, "dataset_format": "jsonl"},
        "model": {"seq_length": 32},
    })
    print(f"FinetuneDataset length: {len(ds)}")
    os.unlink(f.name)
```

**4. 验证 Celery 训练任务（需 Redis + PostgreSQL）：**

```bash
# 启动 Celery Worker
celery -A app.core.celery_app worker --loglevel=info

# 在另一个终端，通过 API 创建训练任务
curl -X POST http://localhost:8000/api/training/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"task_name": "Test", "dataset_id": 1, "framework": "pytorch", "parallel_strategy": "ddp"}'
```

**5. 验证 Megatron Stub 模式（无需 Megatron-LM）：**

```python
# test_megatron_stub.py
from app.training.trainers.megatron_trainer import MegatronTrainer
from app.training.core.callbacks import CallbackList
from app.training.core.state import TrainingState

config = {
    "task_code": "test-stub",
    "framework": "megatron",
    "parallel_strategy": "tp",
    "hyperparams": {"max_epochs": 1, "max_steps": 5, "learning_rate": 1e-4},
    "model": {"model_type": "gpt2"},
}
state = TrainingState(task_code="test-stub", max_epochs=1, max_steps=5)
trainer = MegatronTrainer(config=config, callbacks=CallbackList(), state=state)
final = trainer.train()  # 会触发 stub 模式
print(f"Stub training: status={final.status}, steps={final.global_step}")
```

## 与后端集成

训练框架通过 Celery 异步任务与后端系统集成：

```
用户请求 → FastAPI API → TrainingService → Celery Task → LLMT-Training 框架
                ↓                                    ↓
           PostgreSQL                          ReportingCallbackBridge
           (任务状态)                           ↓          ↓          ↓
                                          InfluxDB   PostgreSQL   MinIO
                                          (指标)     (进度)      (检查点)
```

关键集成文件：
- `app/tasks/training_tasks.py` — Celery 任务，加载配置 → 校验 → 创建 Trainer → 执行训练
- `app/services/training_service.py` — 训练服务层，CRUD + 指标查询
- `app/api/v1/training.py` — 7 个 API 端点

## 依赖服务

| 服务 | 用途 | 默认地址 |
|------|------|----------|
| PostgreSQL | 业务数据、训练状态 | localhost:5432 |
| InfluxDB | 训练指标时序数据 | localhost:8086 |
| MinIO | 文件/检查点存储 | localhost:9000 |
| Redis | Celery 消息队列 | localhost:6379 |
| Elasticsearch | 系统日志 | localhost:9200 |
