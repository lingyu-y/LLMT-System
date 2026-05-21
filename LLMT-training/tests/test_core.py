"""Tests for core abstractions – state, callbacks, model registry."""

import pytest
import torch

from llmt_training.core.state import TrainingState
from llmt_training.core.callbacks import TrainingCallback, CallbackList
from llmt_training.models.registry import ModelRegistry
from llmt_training.models.gpt_provider import GPTModelProvider, GPTConfig, GPTModel
from llmt_training.models.bert_provider import BERTModelProvider, BertConfig, BertModel


class TestTrainingState:
    def test_default_state(self):
        state = TrainingState()
        assert state.status == "created"
        assert state.epoch == 0
        assert state.loss == 0.0

    def test_to_dict(self):
        state = TrainingState(task_code="test-123", epoch=5, loss=0.5)
        d = state.to_dict()
        assert d["task_code"] == "test-123"
        assert d["epoch"] == 5
        assert d["loss"] == 0.5


class TestCallbackList:
    def test_callback_list_calls_all(self):
        events = []

        class CB1(TrainingCallback):
            def on_train_begin(self, state, **kwargs):
                events.append("cb1_train_begin")

        class CB2(TrainingCallback):
            def on_train_begin(self, state, **kwargs):
                events.append("cb2_train_begin")

        cl = CallbackList([CB1(), CB2()])
        cl.on_train_begin(TrainingState())
        assert events == ["cb1_train_begin", "cb2_train_begin"]

    def test_add_callback(self):
        cl = CallbackList()
        cl.add(TrainingCallback())
        assert len(cl.callbacks) == 1


class TestGPTModel:
    def test_gpt_model_forward(self):
        config = GPTConfig(
            vocab_size=100, hidden_size=64, num_layers=2,
            num_attention_heads=4, seq_length=32,
        )
        model = GPTModel(config)
        input_ids = torch.randint(0, 100, (2, 32))
        with torch.no_grad():
            output = model(input_ids)
        assert output.logits.shape == (2, 32, 100)

    def test_gpt_provider(self):
        provider = GPTModelProvider()
        model = provider.get_model({"vocab_size": 100, "hidden_size": 64, "num_layers": 2, "num_attention_heads": 4})
        loss_fn = provider.get_loss_fn({})
        assert isinstance(loss_fn, torch.nn.CrossEntropyLoss)


class TestBERTModel:
    def test_bert_model_forward(self):
        config = BertConfig(
            vocab_size=100, hidden_size=64, num_layers=2,
            num_attention_heads=4, intermediate_size=256, max_position_embeddings=32,
        )
        model = BertModel(config)
        input_ids = torch.randint(0, 100, (2, 16))
        with torch.no_grad():
            output = model(input_ids)
        assert output.logits.shape[0] == 2
        assert output.logits.shape[2] == 100


class TestModelRegistry:
    def test_list_models(self):
        models = ModelRegistry.list_models()
        assert "gpt2" in models
        assert "bert" in models

    def test_get_gpt2(self):
        provider = ModelRegistry.get("gpt2")
        assert isinstance(provider, GPTModelProvider)

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown model type"):
            ModelRegistry.get("nonexistent")
