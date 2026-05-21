"""Tests for config system – schema, merger, validator."""

import json
import pytest

from llmt_training.config.schema import (
    TrainingConfig,
    ModelConfig,
    DataConfig,
    HyperParamsConfig,
    StrategyConfig,
    CheckpointConfig,
    ReportingConfig,
)
from llmt_training.config.merger import ConfigMerger
from llmt_training.config.validator import ConfigValidator


class TestTrainingConfig:
    """Test TrainingConfig creation and defaults."""

    def test_default_config(self):
        config = TrainingConfig()
        assert config.framework == "deepspeed"
        assert config.parallel_strategy == "zero2"
        assert config.model.vocab_size == 50257
        assert config.hyperparams.batch_size == 32
        assert config.strategy.num_gpus == 1

    def test_strategy_sync_zero2(self):
        config = TrainingConfig(parallel_strategy="zero2")
        assert config.strategy.zero_stage == 2

    def test_strategy_sync_zero3_offload(self):
        config = TrainingConfig(parallel_strategy="zero3_offload")
        assert config.strategy.zero_stage == 3
        assert config.strategy.zero_offload is True
        assert config.strategy.zero_offload_params is True

    def test_strategy_sync_3d(self):
        config = TrainingConfig(parallel_strategy="3d")
        assert config.strategy.tensor_model_parallel_size >= 2
        assert config.strategy.pipeline_model_parallel_size >= 2

    def test_model_config_defaults(self):
        mc = ModelConfig(hidden_size=1024)
        assert mc.intermediate_size == 4096  # 4 * hidden_size


class TestConfigMerger:
    """Test DeepSpeed JSON and Megatron args generation."""

    def test_deepspeed_zero2_json(self):
        config = TrainingConfig(
            framework="deepspeed",
            parallel_strategy="zero2",
            hyperparams=HyperParamsConfig(learning_rate=3e-4, batch_size=16),
            strategy=StrategyConfig(num_gpus=4, zero_stage=2),
        )
        ds = ConfigMerger.to_deepspeed_json(config)

        assert ds["optimizer"]["type"] == "AdamW"
        assert ds["optimizer"]["params"]["lr"] == 3e-4
        assert ds["zero_optimization"]["stage"] == 2
        assert ds["fp16"]["enabled"] is True

    def test_deepspeed_zero3_offload(self):
        config = TrainingConfig(
            framework="deepspeed",
            parallel_strategy="zero3_offload",
        )
        ds = ConfigMerger.to_deepspeed_json(config)
        assert ds["zero_optimization"]["stage"] == 3
        assert "offload_optimizer" in ds["zero_optimization"]

    def test_megatron_args(self):
        config = TrainingConfig(
            framework="megatron",
            model=ModelConfig(num_layers=24, hidden_size=1024, num_attention_heads=16),
        )
        args = ConfigMerger.to_megatron_args(config)

        assert "--num-layers" in args
        assert "24" in args
        assert "--hidden-size" in args
        assert "1024" in args

    def test_deepspeed_overrides(self):
        config = TrainingConfig(
            deepspeed_overrides={"gradient_clipping": 5.0},
        )
        ds = ConfigMerger.to_deepspeed_json(config)
        assert ds["gradient_clipping"] == 5.0


class TestConfigValidator:
    """Test config validation rules."""

    def test_valid_config(self):
        config = TrainingConfig(framework="deepspeed", parallel_strategy="zero2")
        result = ConfigValidator.validate(config)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_zero_with_tp_incompatible(self):
        config = TrainingConfig(
            framework="deepspeed",
            parallel_strategy="zero2",
            strategy=StrategyConfig(
                zero_stage=2,
                tensor_model_parallel_size=2,
                num_gpus=8,
            ),
        )
        result = ConfigValidator.validate(config)
        assert result.valid is False
        assert any("ZeRO" in e for e in result.errors)

    def test_pytorch_with_zero_invalid(self):
        config = TrainingConfig(
            framework="pytorch",
            strategy=StrategyConfig(zero_stage=2),
        )
        result = ConfigValidator.validate(config)
        assert result.valid is False

    def test_hidden_size_not_divisible_by_heads(self):
        config = TrainingConfig(
            model=ModelConfig(hidden_size=768, num_attention_heads=7),
        )
        result = ConfigValidator.validate(config)
        assert result.valid is False
        assert any("hidden_size" in e for e in result.errors)

    def test_gpu_count_insufficient(self):
        config = TrainingConfig(
            strategy=StrategyConfig(
                num_gpus=2,
                tensor_model_parallel_size=4,
            ),
        )
        result = ConfigValidator.validate(config)
        assert result.valid is False
