"""GPT model provider – GPT-2 architecture for pretraining."""

from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn

from llmt_training.core.base_model import BaseModelProvider
from llmt_training.core.simple_tokenizer import SimpleTokenizer


class GPTConfig:
    """GPT model configuration."""

    def __init__(
        self,
        vocab_size: int = 50257,
        hidden_size: int = 768,
        num_layers: int = 12,
        num_attention_heads: int = 12,
        intermediate_size: int | None = None,
        max_position_embeddings: int = 1024,
        seq_length: int | None = None,
        dropout: float = 0.1,
        layer_norm_eps: float = 1e-5,
        activation: str = "gelu_new",
    ):
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size or 4 * hidden_size
        self.max_position_embeddings = max_position_embeddings
        self.dropout = dropout
        self.layer_norm_eps = layer_norm_eps
        self.activation = activation


class GPTModel(nn.Module):
    """Simplified GPT-2 model for pretraining."""

    def __init__(self, config: GPTConfig):
        super().__init__()
        self.config = config
        self.embed_dim = config.hidden_size

        self.wte = nn.Embedding(config.vocab_size, self.embed_dim)
        self.wpe = nn.Embedding(config.max_position_embeddings, self.embed_dim)
        self.drop = nn.Dropout(config.dropout)
        self.h = nn.ModuleList([
            self._build_block(config) for _ in range(config.num_layers)
        ])
        self.ln_f = nn.LayerNorm(self.embed_dim, eps=config.layer_norm_eps)

        self._init_weights()

    def _build_block(self, config: GPTConfig) -> nn.Module:
        """Build a single transformer block."""
        class GPTBlock(nn.Module):
            def __init__(self, inner_config: GPTConfig):
                super().__init__()
                self.ln_1 = nn.LayerNorm(inner_config.hidden_size, eps=inner_config.layer_norm_eps)
                self.attn = nn.MultiheadAttention(
                    embed_dim=inner_config.hidden_size,
                    num_heads=inner_config.num_attention_heads,
                    dropout=inner_config.dropout,
                    batch_first=True,
                )
                self.ln_2 = nn.LayerNorm(inner_config.hidden_size, eps=inner_config.layer_norm_eps)
                self.mlp = nn.Sequential(
                    nn.Linear(inner_config.hidden_size, inner_config.intermediate_size),
                    nn.GELU() if inner_config.activation == "gelu_new" else nn.ReLU(),
                    nn.Linear(inner_config.intermediate_size, inner_config.hidden_size),
                    nn.Dropout(inner_config.dropout),
                )

            def forward(self, x, attention_mask=None):
                residual = x
                x = self.ln_1(x)
                attn_output, _ = self.attn(x, x, x, attn_mask=attention_mask, need_weights=False)
                x = residual + attn_output
                residual = x
                x = self.ln_2(x)
                x = self.mlp(x)
                x = residual + x
                return x

        return GPTBlock(config)

    def _init_weights(self):
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.bias is not None:
                    torch.nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
            elif isinstance(module, nn.LayerNorm):
                nn.init.ones_(module.weight)
                torch.nn.init.zeros_(module.bias)

    def forward(self, input_ids, attention_mask=None, **kwargs):
        bsz, seq_len = input_ids.shape
        position_ids = torch.arange(0, seq_len, device=input_ids.device).unsqueeze(0)

        hidden_states = self.wte(input_ids) + self.wpe(position_ids)
        hidden_states = self.drop(hidden_states)

        # Convert attention_mask for MultiheadAttention
        attn_mask = None
        if attention_mask is not None:
            # causal mask
            causal = torch.triu(
                torch.ones(seq_len, seq_len, device=input_ids.device), diagonal=1
            ).bool()
            attn_mask = causal.masked_fill(causal, float("-inf"))

        for block in self.h:
            hidden_states = block(hidden_states, attention_mask=attn_mask)

        hidden_states = self.ln_f(hidden_states)

        # Return with logits attribute for compatibility
        class ModelOutput:
            def __init__(self, logits):
                self.logits = logits

        # Weight tying: project hidden_states through the transposed embedding
        # matrix to produce logits. Using F.linear() instead of wte() because
        # nn.Embedding.forward expects integer indices, not float hidden states.
        logits = torch.nn.functional.linear(hidden_states, self.wte.weight)
        return ModelOutput(logits)


class GPTModelProvider(BaseModelProvider):
    """Provider for GPT-2 series models."""

    def get_model(self, config: dict[str, Any]) -> nn.Module:
        config = config.get("model", config)
        max_positions = config.get("max_position_embeddings") or config.get(
            "seq_length", 1024,
        )
        gpt_config = GPTConfig(
            vocab_size=config.get("vocab_size", 50257),
            hidden_size=config.get("hidden_size", 768),
            num_layers=config.get("num_layers", 12),
            num_attention_heads=config.get("num_attention_heads", 12),
            intermediate_size=config.get("intermediate_size"),
            max_position_embeddings=max_positions,
            dropout=config.get("dropout", 0.1),
            layer_norm_eps=config.get("layer_norm_eps", 1e-5),
            activation=config.get("activation", "gelu_new"),
        )
        return GPTModel(gpt_config)

    def get_tokenizer(self, config: dict[str, Any]) -> Any:
        vocab_size = config.get("vocab_size", 50257)
        try:
            from transformers import GPT2Tokenizer
            return GPT2Tokenizer.from_pretrained("gpt2", local_files_only=True)
        except Exception:
            return SimpleTokenizer(vocab_size=vocab_size)

    def get_loss_fn(self, config: dict[str, Any]) -> nn.Module:
        return nn.CrossEntropyLoss()
