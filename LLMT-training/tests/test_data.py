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
from llmt_training.core.simple_tokenizer import SimpleTokenizer


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

    def test_prompt_response_masks_prompt_labels(self):
        tokenizer = SimpleTokenizer(vocab_size=1000)
        ds = FinetuneDataset(
            [{"prompt": "Question one", "response": "Answer two"}],
            seq_length=8,
            tokenizer=tokenizer,
        )

        sample = ds[0]
        answer_id = tokenizer.word_to_id["Answer"]
        two_id = tokenizer.word_to_id["two"]

        assert sample["labels"][0].item() == -100
        assert sample["labels"][1].item() == answer_id
        assert sample["labels"][2].item() == two_id
        assert sample["labels"][3].item() == -100


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
