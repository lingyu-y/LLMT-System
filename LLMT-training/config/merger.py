"""Config merger – converts TrainingConfig to framework-specific configs."""

from __future__ import annotations

import copy
import json
from typing import Any

from llmt_training.config.schema import TrainingConfig


class ConfigMerger:
    """Converts a unified TrainingConfig into DeepSpeed JSON or Megatron CLI args."""

    @staticmethod
    def to_deepspeed_json(config: TrainingConfig) -> dict[str, Any]:
        """Generate a DeepSpeed configuration dict from TrainingConfig.

        Returns:
            A dict that can be serialized to deepspeed_config.json.
        """
        hp = config.hyperparams
        s = config.strategy
        m = config.model

        ds_config: dict[str, Any] = {
            "train_batch_size": hp.batch_size * s.data_parallel_size * hp.gradient_accumulation_steps,
            "train_micro_batch_size_per_gpu": hp.batch_size,
            "gradient_accumulation_steps": hp.gradient_accumulation_steps,
            "gradient_clipping": hp.max_grad_norm,
        }

        # Optimizer
        if hp.optimizer == "adamw":
            ds_config["optimizer"] = {
                "type": "AdamW",
                "params": {
                    "lr": hp.learning_rate,
                    "betas": [hp.beta1, hp.beta2],
                    "eps": hp.adam_epsilon,
                    "weight_decay": hp.weight_decay,
                },
            }
        elif hp.optimizer == "adam":
            ds_config["optimizer"] = {
                "type": "Adam",
                "params": {
                    "lr": hp.learning_rate,
                    "betas": [hp.beta1, hp.beta2],
                    "eps": hp.adam_epsilon,
                },
            }
        else:
            ds_config["optimizer"] = {
                "type": hp.optimizer.capitalize(),
                "params": {"lr": hp.learning_rate},
            }

        # Scheduler
        scheduler_type = {
            "linear_warmup_decay": "WarmupDecayLR",
            "cosine": "WarmupCosineLR",
            "constant_warmup": "WarmupConstantLR",
            "polynomial": "WarmupPolynomialLR",
        }.get(hp.scheduler, "WarmupDecayLR")

        ds_config["scheduler"] = {
            "type": scheduler_type,
            "params": {
                "warmup_min_lr": 0,
                "warmup_max_lr": hp.learning_rate,
                "warmup_num_steps": hp.warmup_steps,
                "total_num_steps": hp.max_steps or (hp.max_epochs * 1000),
            },
        }

        # Precision
        if hp.precision == "fp16":
            ds_config["fp16"] = {"enabled": True}
        elif hp.precision == "bf16":
            ds_config["bf16"] = {"enabled": True}

        # ZeRO
        if s.zero_stage > 0:
            zero_config: dict[str, Any] = {
                "stage": s.zero_stage,
                "overlap_comm": s.overlap_comm,
                "reduce_scatter": s.reduce_scatter,
                "contiguous_gradients": s.contiguous_gradients,
            }
            if s.zero_offload:
                offload_device = "cpu"
                zero_config["offload_optimizer"] = {
                    "device": offload_device,
                    "pin_memory": True,
                }
                if s.zero_offload_params:
                    zero_config["offload_param"] = {
                        "device": offload_device,
                        "pin_memory": True,
                    }
            ds_config["zero_optimization"] = zero_config

        # Activation checkpointing
        if s.activation_checkpointing:
            ds_config["activation_checkpointing"] = {
                "partition_activations": s.partition_activations,
                "cpu_checkpointing": s.cpu_checkpointing,
                "contiguous_memory_optimization": s.partition_activations,
                "number_checkpoints": None,
                "synchronize_checkpoint_boundary": False,
                "profile": False,
            }

        # Logging
        ds_config["steps_per_print"] = config.checkpoint.eval_interval
        ds_config["wall_clock_breakdown"] = False

        # Apply user overrides
        if config.deepspeed_overrides:
            ds_config = _deep_merge(ds_config, config.deepspeed_overrides)

        return ds_config

    @staticmethod
    def to_megatron_args(config: TrainingConfig) -> list[str]:
        """Generate Megatron-LM CLI arguments from TrainingConfig.

        Returns:
            A list of CLI argument strings (e.g. ["--num-layers", "12", ...]).
        """
        m = config.model
        hp = config.hyperparams
        s = config.strategy
        d = config.data
        ckpt = config.checkpoint

        args: list[str] = [
            # Model architecture
            "--num-layers", str(m.num_layers),
            "--hidden-size", str(m.hidden_size),
            "--num-attention-heads", str(m.num_attention_heads),
            "--seq-length", str(m.seq_length),
            "--max-position-embeddings", str(m.max_position_embeddings or m.seq_length),

            # Model type
            "--model-type", m.model_type if m.model_type in ("gpt2", "bert") else "gpt2",

            # Parallelism
            "--tensor-model-parallel-size", str(s.tensor_model_parallel_size),
            "--pipeline-model-parallel-size", str(s.pipeline_model_parallel_size),

            # Training
            "--micro-batch-size", str(hp.batch_size),
            "--global-batch-size", str(hp.batch_size * s.data_parallel_size * hp.gradient_accumulation_steps),
            "--train-iters", str(hp.max_steps or (hp.max_epochs * 1000)),
            "--lr", str(hp.learning_rate),
            "--min-lr", str(hp.min_lr),
            "--lr-decay-style", hp.scheduler.replace("_warmup_decay", "").replace("_warmup", ""),
            "--lr-warmup-iters", str(hp.warmup_steps),
            "--weight-decay", str(hp.weight_decay),
            "--clip-grad", str(hp.max_grad_norm),
            "--adam-beta1", str(hp.beta1),
            "--adam-beta2", str(hp.beta2),
            "--adam-eps", str(hp.adam_epsilon),

            # Data
            "--data-path", d.dataset_path,
            "--seed", str(d.seed),
            "--num-workers", str(d.num_workers),

            # Checkpoint
            "--save-interval", str(ckpt.save_interval),
            "--eval-interval", str(ckpt.eval_interval),
            "--save", ckpt.checkpoint_dir,
            "--load", ckpt.checkpoint_dir,
        ]

        # Precision
        if hp.precision == "fp16":
            args.append("--fp16")
        elif hp.precision == "bf16":
            args.append("--bf16")

        # Activation checkpointing
        if s.activation_checkpointing:
            args.append("--checkpoint-activations")
            if s.cpu_checkpointing:
                args.append("--checkpoint-activations-cpu")

        # Dataloader type
        if d.dataset_format == "megatron_bin_idx":
            args.extend(["--data-impl", "mmap"])
        else:
            args.extend(["--data-impl", "lazy"])

        # Apply user overrides
        if config.megatron_overrides:
            for key, value in config.megatron_overrides.items():
                if isinstance(value, bool):
                    if value:
                        args.append(f"--{key}")
                else:
                    args.extend([f"--{key}", str(value)])

        return args


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins on conflicts)."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
