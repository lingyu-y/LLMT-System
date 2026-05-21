"""DeepSpeed launcher – uses deepspeed CLI for multi-GPU/multi-node training."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any

from llmt_training.launcher.base_launcher import BaseLauncher
from llmt_training.config.schema import TrainingConfig
from llmt_training.config.merger import ConfigMerger


class DeepSpeedLauncher(BaseLauncher):
    """Launch training using the DeepSpeed CLI.

    Generates the DeepSpeed JSON config file and launches via:
      deepspeed --num_gpus=N --num_nodes=N trainer_script.py --deepspeed --deepspeed_config=...
    """

    def build_command(self, trainer_script: str, **kwargs: Any) -> list[str]:
        strategy = self.config.get("strategy", {})
        num_gpus = strategy.get("num_gpus", 1)
        num_nodes = strategy.get("num_nodes", 1)

        cmd = [
            sys.executable, "-m", "deepspeed",
            f"--num_gpus={num_gpus}",
        ]

        if num_nodes > 1:
            master_addr = os.environ.get("MASTER_ADDR", "127.0.0.1")
            master_port = os.environ.get("MASTER_PORT", "29500")
            node_rank = int(os.environ.get("NODE_RANK", "0"))
            cmd.extend([
                f"--num_nodes={num_nodes}",
                f"--hostfile={kwargs.get('hostfile', 'hostfile')}" if kwargs.get("hostfile") else f"--num_nodes={num_nodes}",
                f"--master_addr={master_addr}",
                f"--master_port={master_port}",
                f"--node_rank={node_rank}",
            ])

        cmd.extend([
            trainer_script,
            "--deepspeed",
        ])

        return cmd

    def launch(self, trainer_script: str, **kwargs: Any) -> int:
        """Write DeepSpeed config and launch training."""
        cmd = self.build_command(trainer_script, **kwargs)

        # Generate and write DeepSpeed JSON config
        ds_config_path = self._write_ds_config()

        cmd.extend([f"--deepspeed_config={ds_config_path}"])

        env = os.environ.copy()
        env["LLMT_TRAINING_CONFIG"] = kwargs.get("config_json", "")

        result = subprocess.run(cmd, env=env)
        return result.returncode

    def _write_ds_config(self) -> str:
        """Write DeepSpeed config to a temporary JSON file and return its path."""
        try:
            tc = TrainingConfig(**self.config)
            ds_config = ConfigMerger.to_deepspeed_json(tc)
        except Exception:
            # Fallback: minimal config
            hp = self.config.get("hyperparams", {})
            ds_config = {
                "train_batch_size": "auto",
                "train_micro_batch_size_per_gpu": "auto",
                "gradient_accumulation_steps": "auto",
                "fp16": {"enabled": hp.get("precision") == "fp16"},
                "bf16": {"enabled": hp.get("precision") == "bf16"},
                "zero_optimization": {"stage": self.config.get("strategy", {}).get("zero_stage", 2)},
                "optimizer": {
                    "type": "AdamW",
                    "params": {
                        "lr": hp.get("learning_rate", 2e-5),
                        "betas": [0.9, 0.999],
                        "eps": 1e-8,
                        "weight_decay": 0.01,
                    },
                },
            }

        ckpt_dir = self.config.get("checkpoint", {}).get("checkpoint_dir", "./checkpoints")
        os.makedirs(ckpt_dir, exist_ok=True)
        ds_config_path = os.path.join(ckpt_dir, "ds_config.json")

        with open(ds_config_path, "w") as f:
            json.dump(ds_config, f, indent=2)

        return ds_config_path
