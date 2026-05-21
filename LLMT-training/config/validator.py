"""Config validator – cross-checks training config for compatibility issues."""

from __future__ import annotations

from dataclasses import dataclass, field

from llmt_training.config.schema import TrainingConfig


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ConfigValidator:
    """Validates a TrainingConfig for framework compatibility."""

    @staticmethod
    def validate(config: TrainingConfig) -> ValidationResult:
        result = ValidationResult()
        s = config.strategy
        hp = config.hyperparams

        # ---- Parallelism constraints ----

        total_parallel = s.tensor_model_parallel_size * s.pipeline_model_parallel_size
        total_gpus = s.num_gpus * s.num_nodes

        if total_parallel > total_gpus:
            result.errors.append(
                f"并行度 (TP={s.tensor_model_parallel_size} × PP={s.pipeline_model_parallel_size}"
                f"={total_parallel}) 超过可用 GPU 数 ({total_gpus})"
            )

        if total_gpus % total_parallel != 0:
            result.errors.append(
                f"GPU 总数 ({total_gpus}) 必须能被并行度 ({total_parallel}) 整除"
            )

        # ZeRO + TP incompatibility
        if s.zero_stage > 0 and s.tensor_model_parallel_size > 1 and config.framework == "deepspeed":
            result.errors.append(
                "DeepSpeed ZeRO 与张量并行(TP)不兼容；"
                "3D 并行请使用 Megatron + DeepSpeed 混合模式"
            )

        # ZeRO3 offload without ZeRO3
        if s.zero_offload and s.zero_stage < 3:
            result.warnings.append(
                "CPU offload 在 ZeRO Stage < 3 时仅支持 optimizer offload，"
                "参数 offload 需要 ZeRO Stage 3"
            )

        # ---- Framework-specific checks ----

        if config.framework == "megatron":
            if s.tensor_model_parallel_size == 1 and s.pipeline_model_parallel_size == 1:
                result.warnings.append("Megatron 框架建议至少启用 TP 或 PP 中的一种")
            if total_gpus <= 1:
                result.warnings.append("Megatron 框架通常需要多 GPU 环境")
            if not config.data.dataset_path:
                result.errors.append("Megatron 需要指定 dataset_path")

        if config.framework == "deepspeed":
            if s.zero_stage == 0 and config.parallel_strategy != "ddp":
                result.warnings.append(
                    "使用 DeepSpeed 框架但 ZeRO Stage 为 0，"
                    "考虑直接使用 PyTorch DDP 或选择 ZeRO Stage 1/2/3"
                )

        if config.framework == "pytorch":
            if s.zero_stage > 0:
                result.errors.append("PyTorch 框架不支持 ZeRO 优化，请使用 DeepSpeed 框架")
            if s.tensor_model_parallel_size > 1 or s.pipeline_model_parallel_size > 1:
                result.errors.append("PyTorch 框架不支持 TP/PP，请使用 Megatron 框架")

        # ---- Hyperparameter sanity ----

        if hp.learning_rate <= 0:
            result.errors.append("学习率必须为正数")
        if hp.batch_size <= 0:
            result.errors.append("batch_size 必须为正整数")
        if hp.max_epochs <= 0 and (hp.max_steps is None or hp.max_steps <= 0):
            result.errors.append("必须指定 max_epochs 或 max_steps")
        if hp.gradient_accumulation_steps < 1:
            result.errors.append("gradient_accumulation_steps 必须 >= 1")

        # ---- Model checks ----

        m = config.model
        if m.hidden_size % m.num_attention_heads != 0:
            result.errors.append(
                f"hidden_size ({m.hidden_size}) 必须能被 num_attention_heads "
                f"({m.num_attention_heads}) 整除"
            )

        result.valid = len(result.errors) == 0
        return result
