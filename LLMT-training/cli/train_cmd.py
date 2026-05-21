"""Train command – CLI interface for launching training jobs."""

from __future__ import annotations

import json
import sys

try:
    import click
    HAS_CLICK = True
except ImportError:
    HAS_CLICK = False


def _run_train(config_path: str, framework: str, strategy: str, task_code: str):
    """Run a training job from a config file."""
    from llmt_training.config.schema import TrainingConfig
    from llmt_training.config.validator import ConfigValidator
    from llmt_training.core.callbacks import CallbackList
    from llmt_training.core.state import TrainingState
    from llmt_training.models.registry import ModelRegistry
    from llmt_training.data.data_utils import create_dataset_from_config, build_dataloaders
    from llmt_training.trainers.factory import create_trainer
    from llmt_training.reporting.callback_bridge import ReportingCallbackBridge

    # Load config
    with open(config_path, "r") as f:
        config = json.load(f)

    # Override framework/strategy if specified
    if framework:
        config["framework"] = framework
    if strategy:
        config["parallel_strategy"] = strategy
    if task_code:
        config["task_code"] = task_code

    # Validate
    tc = TrainingConfig(**config)
    result = ConfigValidator.validate(tc)
    if not result.valid:
        print(f"Config validation failed: {result.errors}")
        sys.exit(1)
    if result.warnings:
        for w in result.warnings:
            print(f"Warning: {w}")

    # Build components
    model_type = config.get("model", {}).get("model_type", "gpt2")
    provider = ModelRegistry.get(model_type)
    model = provider.get_model(config)
    loss_fn = provider.get_loss_fn(config)

    dataset = create_dataset_from_config(config)
    distributed = config.get("strategy", {}).get("num_gpus", 1) > 1
    train_loader, eval_loader = build_dataloaders(dataset, config, distributed=distributed)

    state = TrainingState(
        task_code=config.get("task_code", "cli-train"),
        max_epochs=config.get("hyperparams", {}).get("max_epochs", 10),
    )
    reporting_callback = ReportingCallbackBridge.from_config(config)
    callbacks = CallbackList([reporting_callback])

    fw = config.get("framework", "pytorch")
    ps = config.get("parallel_strategy", "ddp")
    trainer = create_trainer(
        framework=fw, parallel_strategy=ps, config=config,
        model=model, train_dataloader=train_loader,
        eval_dataloader=eval_loader, callbacks=callbacks,
        state=state, loss_fn=loss_fn,
    )

    # Run
    final_state = trainer.train()
    print(f"\nTraining finished: status={final_state.status}, "
          f"steps={final_state.global_step}, loss={final_state.loss:.4f}")


def _run_eval(config_path: str, checkpoint_path: str):
    """Run evaluation on a checkpoint."""
    with open(config_path, "r") as f:
        config = json.load(f)

    model_type = config.get("model", {}).get("model_type", "gpt2")
    provider = ModelRegistry.get(model_type)
    model = provider.get_model(config)

    dataset = create_dataset_from_config(config)
    train_loader, eval_loader = build_dataloaders(dataset, config)

    fw = config.get("framework", "pytorch")
    ps = config.get("parallel_strategy", "ddp")
    trainer = create_trainer(
        framework=fw, parallel_strategy=ps, config=config,
        model=model, train_dataloader=train_loader,
        eval_dataloader=eval_loader,
    )

    trainer.load_checkpoint(checkpoint_path)
    metrics = trainer.evaluate()
    print(f"Evaluation results: {metrics}")


if HAS_CLICK:
    @click.group()
    def cli():
        """LLMT-Training CLI – Launch and manage training jobs."""
        pass

    @cli.command()
    @click.option("--config", "-c", required=True, help="Path to training config JSON")
    @click.option("--framework", "-f", default="", help="Override framework (pytorch/deepspeed/megatron)")
    @click.option("--strategy", "-s", default="", help="Override parallel strategy")
    @click.option("--task-code", "-t", default="", help="Task code from backend")
    def train(config: str, framework: str, strategy: str, task_code: str):
        """Launch a training job."""
        _run_train(config, framework, strategy, task_code)

    @cli.command()
    @click.option("--config", "-c", required=True, help="Path to training config JSON")
    @click.option("--checkpoint", "-ckpt", required=True, help="Path to checkpoint")
    def eval(config: str, checkpoint: str):
        """Evaluate a model checkpoint."""
        _run_eval(config, checkpoint)

else:
    # Fallback CLI without click
    def cli():
        """Simple CLI without click dependency."""
        if len(sys.argv) < 2:
            print("Usage: llmt-train train --config <path> [--framework <fw>] [--strategy <str>]")
            print("       llmt-train eval --config <path> --checkpoint <path>")
            sys.exit(1)

        command = sys.argv[1]
        if command == "train":
            config_path = ""
            framework = ""
            strategy = ""
            task_code = ""
            i = 2
            while i < len(sys.argv):
                if sys.argv[i] in ("--config", "-c") and i + 1 < len(sys.argv):
                    config_path = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i] in ("--framework", "-f") and i + 1 < len(sys.argv):
                    framework = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i] in ("--strategy", "-s") and i + 1 < len(sys.argv):
                    strategy = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i] in ("--task-code", "-t") and i + 1 < len(sys.argv):
                    task_code = sys.argv[i + 1]
                    i += 2
                else:
                    i += 1
            if not config_path:
                print("Error: --config is required")
                sys.exit(1)
            _run_train(config_path, framework, strategy, task_code)

        elif command == "eval":
            config_path = ""
            checkpoint_path = ""
            i = 2
            while i < len(sys.argv):
                if sys.argv[i] in ("--config", "-c") and i + 1 < len(sys.argv):
                    config_path = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i] in ("--checkpoint", "-ckpt") and i + 1 < len(sys.argv):
                    checkpoint_path = sys.argv[i + 1]
                    i += 2
                else:
                    i += 1
            if not config_path or not checkpoint_path:
                print("Error: --config and --checkpoint are required")
                sys.exit(1)
            _run_eval(config_path, checkpoint_path)
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
