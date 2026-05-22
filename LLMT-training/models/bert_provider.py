"""BERT model provider – BERT architecture for fine-tuning and MLM pretraining."""

from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn

from llmt_training.core.base_model import BaseModelProvider
from llmt_training.core.simple_tokenizer import SimpleTokenizer


class BertConfig:
    """BERT model configuration."""

    def __init__(
        self,
        vocab_size: int = 30522,
        hidden_size: int = 768,
        num_layers: int = 12,
        num_attention_heads: int = 12,
        intermediate_size: int = 3072,
        max_position_embeddings: int = 512,
        type_vocab_size: int = 2,
        dropout: float = 0.1,
        layer_norm_eps: float = 1e-12,
    ):
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size
        self.max_position_embeddings = max_position_embeddings
        self.type_vocab_size = type_vocab_size
        self.dropout = dropout
        self.layer_norm_eps = layer_norm_eps


class BertModel(nn.Module):
    """Simplified BERT model for pretraining/fine-tuning."""

    def __init__(self, config: BertConfig):
        super().__init__()
        self.config = config
        self.embed_dim = config.hidden_size

        # Embeddings
        self.word_embeddings = nn.Embedding(config.vocab_size, self.embed_dim)
        self.position_embeddings = nn.Embedding(config.max_position_embeddings, self.embed_dim)
        self.token_type_embeddings = nn.Embedding(config.type_vocab_size, self.embed_dim)
        self.embedding_layer_norm = nn.LayerNorm(self.embed_dim, eps=config.layer_norm_eps)
        self.embedding_dropout = nn.Dropout(config.dropout)

        # Encoder layers
        self.encoder_layers = nn.ModuleList([
            self._build_layer(config) for _ in range(config.num_layers)
        ])

        # MLM head
        self.mlm_dense = nn.Linear(config.hidden_size, config.hidden_size)
        self.mlm_layer_norm = nn.LayerNorm(config.hidden_size, eps=config.layer_norm_eps)
        self.mlm_decoder = nn.Linear(config.hidden_size, config.vocab_size, bias=False)
        self.mlm_bias = nn.Parameter(torch.zeros(config.vocab_size))

        # Classification head (for fine-tuning)
        self.classifier_dropout = nn.Dropout(config.dropout)
        self.classifier = nn.Linear(config.hidden_size, 2)  # binary by default

        self._init_weights()

    def _build_layer(self, config: BertConfig) -> nn.Module:
        class BertLayer(nn.Module):
            def __init__(self, cfg: BertConfig):
                super().__init__()
                self.attention = nn.MultiheadAttention(
                    embed_dim=cfg.hidden_size,
                    num_heads=cfg.num_attention_heads,
                    dropout=cfg.dropout,
                    batch_first=True,
                )
                self.attention_layer_norm = nn.LayerNorm(cfg.hidden_size, eps=cfg.layer_norm_eps)
                self.intermediate = nn.Linear(cfg.hidden_size, cfg.intermediate_size)
                self.output_dense = nn.Linear(cfg.intermediate_size, cfg.hidden_size)
                self.output_layer_norm = nn.LayerNorm(cfg.hidden_size, eps=cfg.layer_norm_eps)
                self.dropout = nn.Dropout(cfg.dropout)

            def forward(self, hidden_states, attention_mask=None):
                residual = hidden_states
                hidden_states = self.attention_layer_norm(hidden_states)
                attn_output, _ = self.attention(
                    hidden_states, hidden_states, hidden_states,
                    attn_mask=attention_mask, need_weights=False,
                )
                hidden_states = residual + self.dropout(attn_output)
                residual = hidden_states
                hidden_states = self.output_layer_norm(hidden_states)
                hidden_states = self.intermediate(hidden_states)
                hidden_states = nn.functional.gelu(hidden_states)
                hidden_states = self.output_dense(hidden_states)
                hidden_states = self.dropout(hidden_states)
                hidden_states = residual + hidden_states
                return hidden_states

        return BertLayer(config)

    def _init_weights(self):
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, input_ids, attention_mask=None, token_type_ids=None, **kwargs):
        bsz, seq_len = input_ids.shape
        position_ids = torch.arange(0, seq_len, device=input_ids.device).unsqueeze(0)

        if token_type_ids is None:
            token_type_ids = torch.zeros_like(input_ids)

        # Embeddings
        hidden_states = (
            self.word_embeddings(input_ids)
            + self.position_embeddings(position_ids)
            + self.token_type_embeddings(token_type_ids)
        )
        hidden_states = self.embedding_layer_norm(hidden_states)
        hidden_states = self.embedding_dropout(hidden_states)

        # Encoder
        extended_mask = None
        if attention_mask is not None:
            # Convert [bsz, seq_len] -> [bsz, 1, 1, seq_len] for self-attention
            extended_mask = attention_mask[:, None, None, :].float()
            extended_mask = (1.0 - extended_mask) * -10000.0

        for layer in self.encoder_layers:
            hidden_states = layer(hidden_states, attention_mask=extended_mask)

        # MLM head
        prediction_scores = self.mlm_dense(hidden_states)
        prediction_scores = nn.functional.gelu(prediction_scores)
        prediction_scores = self.mlm_layer_norm(prediction_scores)
        prediction_scores = self.mlm_decoder(prediction_scores) + self.mlm_bias

        class ModelOutput:
            def __init__(self, logits, pooler_output=None):
                self.logits = logits
                self.pooler_output = pooler_output

        # Pooler: take [CLS] token
        pooler_output = hidden_states[:, 0]
        return ModelOutput(prediction_scores, pooler_output)


class BERTModelProvider(BaseModelProvider):
    """Provider for BERT models (MLM + classification)."""

    def get_model(self, config: dict[str, Any]) -> nn.Module:
        bert_config = BertConfig(
            vocab_size=config.get("vocab_size", 30522),
            hidden_size=config.get("hidden_size", 768),
            num_layers=config.get("num_layers", 12),
            num_attention_heads=config.get("num_attention_heads", 12),
            intermediate_size=config.get("intermediate_size", 3072),
            max_position_embeddings=config.get("max_position_embeddings", 512),
            type_vocab_size=config.get("type_vocab_size", 2),
            dropout=config.get("dropout", 0.1),
            layer_norm_eps=config.get("layer_norm_eps", 1e-12),
        )
        return BertModel(bert_config)

    def get_tokenizer(self, config: dict[str, Any]) -> Any:
        vocab_size = config.get("vocab_size", 30522)
        try:
            from transformers import BertTokenizer
            try:
                return BertTokenizer.from_pretrained("bert-base-uncased", local_files_only=True)
            except Exception:
                return SimpleTokenizer(vocab_size=vocab_size)
        except Exception:
            return SimpleTokenizer(vocab_size=vocab_size)

    def get_loss_fn(self, config: dict[str, Any]) -> nn.Module:
        return nn.CrossEntropyLoss()
