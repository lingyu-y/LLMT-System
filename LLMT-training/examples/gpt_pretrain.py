"""GPT-2 pretraining example script.

Usage:
    # Single GPU
    python gpt_pretrain.py --config config.json

    # Multi-GPU with torchrun
    torchrun --nproc_per_node=4 gpt_pretrain.py --config config.json

    # DeepSpeed
    deepspeed --num_gpus=4 gpt_pretrain.py --deepspeed --deepspeed_config ds_zero2.json

    # Megatron (via launcher)
    torchrun --nproc_per_node=4 gpt_pretrain.py \
        --num-layers 24 --hidden-size 1024 --num-attention-heads 16 ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from llmt_training.config.schema import TrainingConfig
from llmt_training.config.validator import ConfigValidator
from llmt_training.core.callbacks import CallbackList
from llmt_training.core.state import TrainingState
from llmt_training.models.registry import ModelRegistry
from llmt_training.data.data_utils import create_dataset_from_config, build_dataloaders
from llmt_training.trainers.factory import create_trainer
from llmt_training.reporting.callback_bridge import ReportingCallbackBridge


def parse_args():
    parser = argparse.ArgumentParser(description="GPT Pretraining")
    parser.add_argument("--config", type=str, default="", help="Path to training config JSON")
    parser.add_argument("--task-code", type=str, default="", help="Task code from backend")
    parser.add_argument("--deepspeed", action="store_true", help="Enable DeepSpeed")
    parser.add_argument("--deepspeed_config", type=str, default="", help="DeepSpeed config JSON path")
    return parser.parse_args()


def main():
    args = parse_args()

    # Load config
    if args.config and os.path.exists(args.config):
        with open(args.config, "r") as f:
            config = json.load(f)
    elif os.environ.get("LLMT_TRAINING_CONFIG"):
        config = json.loads(os.environ["LLMT_TRAINING_CONFIG"])
    else:
        # Default GPT-2 small config
        config = {
            "task_code": args.task_code or "local-gpt-pretrain",
            "framework": "deepspeed" if args.deepspeed else "pytorch",
            "parallel_strategy": "zero2" if args.deepspeed else "ddp",
            "model": {
                "model_type": "gpt2",
                "vocab_size": 50257,
                "hidden_size": 768,
                "num_layers": 12,
                "num_attention_heads": 12,
                "seq_length": 1024,
            },
            "data": {"dataset_path": "", "dataset_format": "npy"},
            "hyperparams": {
                "batch_size": 8,
                "learning_rate": 2e-5,
                "max_epochs": 3,
                "precision": "fp16",
            },
            "strategy": {"num_gpus": 1},
            "checkpoint": {"save_interval": 500, "checkpoint_dir": "./checkpoints/gpt-pretrain"},
            "reporting": {},
        }

    # Validate
    tc = TrainingConfig(**config)
    result = ConfigValidator.validate(tc)
    if not result.valid:
        print(f"Config validation failed: {result.errors}")
        sys.exit(1)
    if result.warnings:
        print(f"Config warnings: {result.warnings}")

    config_dict = config

    # Build model
    model_type = config_dict.get("model", {}).get("model_type", "gpt2")
    provider = ModelRegistry.get(model_type)
    model = provider.get_model(config_dict)
    loss_fn = provider.get_loss_fn(config_dict)

    # Build dataset
    dataset = create_dataset_from_config(config_dict)
    distributed = config_dict.get("strategy", {}).get("num_gpus", 1) > 1
    train_loader, eval_loader = build_dataloaders(dataset, config_dict, distributed=distributed)

    # Build callbacks
    state = TrainingState(
        task_code=config_dict.get("task_code", ""),
        max_epochs=config_dict.get("hyperparams", {}).get("max_epochs", 10),
        max_steps=config_dict.get("hyperparams", {}).get("max_steps"),
    )
    reporting_callback = ReportingCallbackBridge.from_config(config_dict)
    callbacks = CallbackList([reporting_callback])

    # Create trainer
    framework = config_dict.get("framework", "pytorch")
    strategy = config_dict.get("parallel_strategy", "ddp")
    trainer = create_trainer(
        framework=framework,
        parallel_strategy=strategy,
        config=config_dict,
        model=model,
        train_dataloader=train_loader,
        eval_dataloader=eval_loader,
        callbacks=callbacks,
        state=state,
        loss_fn=loss_fn,
    )

    # Train
    final_state = trainer.train()
    print(f"Training completed: status={final_state.status}, steps={final_state.global_step}")


if __name__ == "__main__":
    main()
