"""Data utilities – collate functions, DataLoader builders, train/eval splitting."""

from __future__ import annotations

from typing import Any

import torch
from torch.utils.data import DataLoader, DistributedSampler, Subset, random_split

from llmt_training.core.base_dataset import BaseDataset


def build_dataloaders(
    dataset: BaseDataset,
    config: dict[str, Any],
    distributed: bool = False,
) -> tuple[DataLoader, DataLoader | None]:
    """Build train and eval DataLoaders from a dataset and config.

    Args:
        dataset: The full dataset to split.
        config: Training config dict.
        distributed: Whether to use DistributedSampler.

    Returns:
        (train_dataloader, eval_dataloader)
    """
    data_cfg = config.get("data", {})
    hyperparams = config.get("hyperparams", {})
    train_split = data_cfg.get("train_split", 0.95)
    batch_size = hyperparams.get("batch_size", 32)
    num_workers = data_cfg.get("num_workers", 4)
    pin_memory = data_cfg.get("pin_memory", True)
    seed = data_cfg.get("seed", 42)

    # Split dataset
    total = len(dataset)
    if total == 0:
        raise ValueError(
            "数据集为空（0 个样本），请检查 dataset_path 是否正确指向一个有效的数据文件。"
            "如果数据存储在 MinIO，系统会自动下载；如果路径不存在，将导致空数据集。"
        )
    train_size = int(total * train_split)
    eval_size = total - train_size

    if eval_size > 0:
        train_dataset, eval_dataset = random_split(
            dataset, [train_size, eval_size],
            generator=torch.Generator().manual_seed(seed),
        )
    else:
        train_dataset = dataset
        eval_dataset = None

    # Samplers
    train_sampler = DistributedSampler(train_dataset) if distributed else None
    eval_sampler = DistributedSampler(eval_dataset, shuffle=False) if distributed and eval_dataset else None

    # DataLoaders
    collate_fn = dataset.get_collate_fn() if hasattr(dataset, "get_collate_fn") else None

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=(train_sampler is None),
        sampler=train_sampler,
        num_workers=num_workers,
        pin_memory=pin_memory,
        collate_fn=collate_fn,
        drop_last=True,
    )

    eval_loader = None
    if eval_dataset is not None:
        eval_loader = DataLoader(
            eval_dataset,
            batch_size=batch_size,
            shuffle=False,
            sampler=eval_sampler,
            num_workers=num_workers,
            pin_memory=pin_memory,
            collate_fn=collate_fn,
            drop_last=False,
        )

    return train_loader, eval_loader


def create_dataset_from_config(config: dict[str, Any]) -> BaseDataset:
    """Create the appropriate dataset based on config.

    Args:
        config: Full training config dict.

    Returns:
        A BaseDataset instance.
    """
    from llmt_training.data.pretrain_dataset import PretrainDataset
    from llmt_training.data.finetune_dataset import FinetuneDataset
    from llmt_training.data.megatron_dataset import MegatronDataset

    data_cfg = config.get("data", {})
    fmt = data_cfg.get("dataset_format", "jsonl")

    if fmt == "megatron_bin_idx":
        return MegatronDataset.from_config(config)
    elif fmt in ("jsonl", "parquet"):
        return FinetuneDataset.from_config(config)
    elif fmt in ("npy", "bin"):
        return PretrainDataset.from_config(config)
    else:
        # Default to pretrain
        return PretrainDataset.from_config(config)
