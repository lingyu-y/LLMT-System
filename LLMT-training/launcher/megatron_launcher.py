"""Megatron launcher – uses torch.distributed.run."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from llmt_training.launcher.base_launcher import BaseLauncher


class MegatronLauncher(BaseLauncher):
    """Launch training using torch.distributed.run.

    Config is passed via LLMT_TRAINING_CONFIG environment variable.
    Launches via: torchrun --nproc_per_node=N trainer_script.py
    """

    def build_command(self, trainer_script: str, **kwargs: Any) -> list[str]:
        strategy = self.config.get("strategy", {})
        num_gpus = strategy.get("num_gpus", 1)
        num_nodes = strategy.get("num_nodes", 1)

        cmd = [
            sys.executable, "-m", "torch.distributed.run",
            f"--nproc_per_node={num_gpus}",
        ]

        if num_nodes > 1:
            master_addr = os.environ.get("MASTER_ADDR", "127.0.0.1")
            master_port = os.environ.get("MASTER_PORT", "29500")
            node_rank = int(os.environ.get("NODE_RANK", "0"))
            cmd.extend([
                f"--nnodes={num_nodes}",
                f"--node_rank={node_rank}",
                f"--master_addr={master_addr}",
                f"--master_port={master_port}",
            ])

        cmd.append(trainer_script)
        return cmd

    def launch(self, trainer_script: str, **kwargs: Any) -> int:
        """Launch Megatron training."""
        cmd = self.build_command(trainer_script, **kwargs)

        env = os.environ.copy()
        env["LLMT_TRAINING_CONFIG"] = kwargs.get("config_json", "")

        # Megatron requires CUDA_VISIBLE_DEVICES
        strategy = self.config.get("strategy", {})
        num_gpus = strategy.get("num_gpus", 1)
        if "CUDA_VISIBLE_DEVICES" not in env and num_gpus > 0:
            env["CUDA_VISIBLE_DEVICES"] = ",".join(str(i) for i in range(num_gpus))

        result = subprocess.run(cmd, env=env)
        return result.returncode
