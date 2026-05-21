"""Tests for data utilities and datasets."""

import json
import os
import tempfile

import numpy as np
import pytest
import torch

from llmt_training.data.pretrain_dataset import PretrainDataset
from llmt_training.data.finetune_dataset import FinetuneDataset
from llmt_training.data.data_utils import create_dataset_from_config


class TestPretrainDataset:
    def test_from_numpy(self):
        with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as f:
            arr = np.arange(2000, dtype=np.int64)
            np.save(f.name, arr)
            path = f.name

        try:
            ds = PretrainDataset.from_config({
                "data": {"dataset_path": path, "dataset_format": "npy"},
                "model": {"seq_length": 128},
            })
            assert len(ds) > 0
            sample = ds[0]
            assert "input_ids" in sample
            assert "labels" in sample
            assert sample["input_ids"].shape == (128,)
        finally:
            os.unlink(path)

    def test_empty_dataset(self):
        ds = PretrainDataset(torch.zeros(0, dtype=torch.long), seq_length=128)
        assert len(ds) == 0


class TestFinetuneDataset:
    def test_from_jsonl(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8",
        ) as f:
            for i in range(10):
                f.write(json.dumps({"text": f"Sample text {i}"}) + "\n")
            path = f.name

        try:
            ds = FinetuneDataset.from_config({
                "data": {"dataset_path": path, "dataset_format": "jsonl"},
                "model": {"seq_length": 32},
            })
            assert len(ds) == 10
        finally:
            os.unlink(path)


class TestCreateDataset:
    def test_npy_format(self):
        ds = create_dataset_from_config({
            "data": {"dataset_path": "", "dataset_format": "npy"},
            "model": {"seq_length": 32},
        })
        assert isinstance(ds, PretrainDataset)

    def test_jsonl_format(self):
        ds = create_dataset_from_config({
            "data": {"dataset_path": "", "dataset_format": "jsonl"},
            "model": {"seq_length": 32},
        })
        assert isinstance(ds, FinetuneDataset)
