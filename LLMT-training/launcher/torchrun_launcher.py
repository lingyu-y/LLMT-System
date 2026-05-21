"""Torchrun launcher – single-GPU or DDP via torch.distributed.run."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from llmt_training.launcher.base_launcher import BaseLauncher


class TorchrunLauncher(BaseLauncher):
    """Launch training using torch.distributed.run (torchrun).

    - Single GPU: runs the script directly
    - Multi-GPU: uses torchrun with nproc_per_node
    - Multi-Node: adds nnodes, node_rank, master_addr, master_port
    """

    def build_command(self, trainer_script: str, **kwargs: Any) -> list[str]:
        strategy = self.config.get("strategy", {})
        num_gpus = strategy.get("num_gpus", 1)
        num_nodes = strategy.get("num_nodes", 1)

        if num_gpus == 1 and num_nodes == 1:
            # Single GPU – run directly
            return [sys.executable, trainer_script]

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
        """Launch the training process and wait for completion."""
        cmd = self.build_command(trainer_script, **kwargs)

        # Pass config via environment variable
        env = os.environ.copy()
        env["LLMT_TRAINING_CONFIG"] = kwargs.get("config_json", "")
        if self.config.get("hyperparams", {}).get("precision") == "bf16":
            env["TORCH_CUDA_ARCH_LIST"] = env.get("TORCH_CUDA_ARCH_LIST", "8.0")

        result = subprocess.run(cmd, env=env)
        return result.returncode
