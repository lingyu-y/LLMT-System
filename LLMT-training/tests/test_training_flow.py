"""Regression tests for short training and inference checkpoint loading."""

from __future__ import annotations

import os

import torch
from torch.utils.data import DataLoader

from llmt_training.data.pretrain_dataset import PretrainDataset
from llmt_training.inference import engine
from llmt_training.models.gpt_provider import GPTModelProvider
from llmt_training.trainers.pytorch_trainer import PyTorchTrainer


def _tiny_config(checkpoint_dir: str) -> dict:
    return {
        "framework": "pytorch",
        "parallel_strategy": "ddp",
        "model": {
            "model_type": "gpt2",
            "vocab_size": 32,
            "hidden_size": 16,
            "num_layers": 1,
            "num_attention_heads": 4,
            "seq_length": 8,
            "dropout": 0.0,
        },
        "hyperparams": {
            "batch_size": 2,
            "learning_rate": 1e-2,
            "max_epochs": 1,
            "max_steps": 1,
            "warmup_steps": 1000,
            "gradient_accumulation_steps": 1,
            "precision": "fp32",
        },
        "checkpoint": {
            "checkpoint_dir": checkpoint_dir,
            "save_interval": 500,
        },
    }


def test_short_pytorch_training_updates_weights_and_saves_final_checkpoint(tmp_path):
    config = _tiny_config(str(tmp_path))
    provider = GPTModelProvider()
    model = provider.get_model(config)
    before = {name: param.detach().clone() for name, param in model.named_parameters()}

    tokens = torch.arange(0, 80, dtype=torch.long) % config["model"]["vocab_size"]
    dataset = PretrainDataset(tokens, seq_length=config["model"]["seq_length"])
    loader = DataLoader(dataset, batch_size=2, shuffle=False, drop_last=True)

    trainer = PyTorchTrainer(
        config=config,
        model=model,
        train_dataloader=loader,
        loss_fn=provider.get_loss_fn(config),
    )
    state = trainer.train()

    assert state.status == "completed"
    assert os.path.isfile(tmp_path / "checkpoint.pt")
    assert any(
        not torch.equal(before[name], param.detach().cpu())
        for name, param in model.named_parameters()
    )


def test_inference_loader_accepts_pytorch_trainer_checkpoint(tmp_path, monkeypatch):
    config = _tiny_config(str(tmp_path))
    provider = GPTModelProvider()
    model = provider.get_model(config)
    checkpoint_path = tmp_path / "checkpoint.pt"
    torch.save({"model_state_dict": model.state_dict()}, checkpoint_path)

    engine.clear_cache()
    monkeypatch.setattr(
        engine,
        "_find_checkpoint_path",
        lambda model_code, version: (str(checkpoint_path), False),
    )

    loaded = engine.load_model(
        "tiny-model",
        "v1",
        model_type="gpt2",
        model_config=config["model"],
    )

    assert loaded is not None
    loaded_model, _ = loaded
    assert (
        loaded_model.state_dict()["wte.weight"].shape
        == model.state_dict()["wte.weight"].shape
    )
