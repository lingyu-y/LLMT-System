"""Shared memory manager for federated learning parameter exchange."""

from __future__ import annotations

import logging
import multiprocessing as mp
from typing import Any

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class SharedMemoryManager:
    """Manages shared memory for parameter exchange between coordinator and participants.

    Uses multiprocessing shared memory to efficiently transfer model parameters
    between the main process (coordinator) and participant processes without
    serialization overhead.
    """

    def __init__(self, model: nn.Module):
        """Initialize shared memory from a model's state dict.

        Args:
            model: The model whose parameters will be shared.
        """
        self._param_shapes: dict[str, tuple[int, ...]] = {}
        self._param_dtypes: dict[str, np.dtype] = {}
        self._param_sizes: dict[str, int] = {}
        self._total_size = 0

        # Analyze model structure
        state_dict = model.state_dict()
        for name, param in state_dict.items():
            numel = param.numel()
            self._param_shapes[name] = tuple(param.shape)
            self._param_dtypes[name] = self._torch_dtype_to_numpy(param.dtype)
            self._param_sizes[name] = numel
            self._total_size += numel

        # Allocate shared memory as numpy array
        self._shared_array = mp.RawArray("f", self._total_size)
        self._numpy_buffer = np.frombuffer(self._shared_array, dtype=np.float32)

        # Map parameter name to slice
        self._param_slices: dict[str, tuple[int, int]] = {}
        offset = 0
        for name, size in self._param_sizes.items():
            self._param_slices[name] = (offset, offset + size)
            offset += size

        # Write initial model parameters
        self.write_model(model)
        logger.info(
            "SharedMemoryManager initialized: %d parameters, total size %d",
            len(self._param_shapes),
            self._total_size,
        )

    def write_model(self, model: nn.Module) -> None:
        """Write model state dict to shared memory.

        Args:
            model: The model whose parameters to write.
        """
        state_dict = model.state_dict()
        for name, param in state_dict.items():
            if name in self._param_slices:
                start, end = self._param_slices[name]
                self._numpy_buffer[start:end] = param.detach().cpu().flatten().numpy().astype(np.float32)

    def read_model(self, model: nn.Module) -> None:
        """Read shared memory into a model's state dict.

        Args:
            model: The model to load parameters into.
        """
        state_dict = model.state_dict()
        new_state_dict = {}
        for name, param in state_dict.items():
            if name in self._param_slices:
                start, end = self._param_slices[name]
                tensor = torch.from_numpy(
                    self._numpy_buffer[start:end].copy()
                ).reshape(param.shape)
                new_state_dict[name] = tensor.to(param.dtype)
            else:
                new_state_dict[name] = param

        model.load_state_dict(new_state_dict)

    def write_update(self, participant_id: str, update: dict[str, torch.Tensor]) -> None:
        """Write a participant's model update to a dedicated update buffer.

        Stores the update (Δw = w_local - w_global) for aggregation.

        Args:
            participant_id: The participant identifier.
            update: Dict mapping parameter names to update tensors.
        """
        if not hasattr(self, "_update_buffers"):
            self._update_buffers: dict[str, np.ndarray] = {}
            self._update_lock = mp.Lock()

        with self._update_lock:
            buffer = np.zeros(self._total_size, dtype=np.float32)
            for name, tensor in update.items():
                if name in self._param_slices:
                    start, end = self._param_slices[name]
                    buffer[start:end] = tensor.detach().cpu().flatten().numpy().astype(np.float32)
            self._update_buffers[participant_id] = buffer

    def read_updates(self) -> dict[str, dict[str, torch.Tensor]]:
        """Read all participant updates from shared memory.

        Returns:
            Dict mapping participant_id to their parameter update dict.
        """
        updates: dict[str, dict[str, torch.Tensor]] = {}
        if not hasattr(self, "_update_buffers"):
            return updates

        with self._update_lock:
            for pid, buffer in self._update_buffers.items():
                param_update = {}
                for name, shape in self._param_shapes.items():
                    if name in self._param_slices:
                        start, end = self._param_slices[name]
                        tensor = torch.from_numpy(
                            buffer[start:end].copy()
                        ).reshape(shape)
                        param_update[name] = tensor
                updates[pid] = param_update

            # Clear update buffers after reading
            self._update_buffers.clear()

        return updates

    def get_flat_parameters(self) -> np.ndarray:
        """Get a copy of the current global parameters as a flat numpy array."""
        return self._numpy_buffer.copy()

    def set_flat_parameters(self, flat: np.ndarray) -> None:
        """Set the global parameters from a flat numpy array."""
        self._numpy_buffer[:] = flat.astype(np.float32)

    @staticmethod
    def _torch_dtype_to_numpy(dtype: torch.dtype) -> np.dtype:
        """Convert torch dtype to numpy dtype."""
        mapping = {
            torch.float32: np.float32,
            torch.float64: np.float64,
            torch.float16: np.float16,
            torch.int64: np.int64,
            torch.int32: np.int32,
            torch.int16: np.int16,
            torch.int8: np.int8,
            torch.bfloat16: np.float32,  # Store as float32
        }
        return mapping.get(dtype, np.float32)
