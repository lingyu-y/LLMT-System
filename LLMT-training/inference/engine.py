"""Real-model inference engine — loads trained models from MinIO and runs
text generation using the same model providers that power training."""

from __future__ import annotations

import io
import logging
import os
import tempfile
import time
from typing import Any

import torch

_log = logging.getLogger(__name__)

# In-memory cache: model_code -> (model, tokenizer)
_cache: dict[str, tuple[torch.nn.Module, Any]] = {}


def _get_minio_client():
    """Lazy-import MinIO client to avoid hard dependency in training-only env."""
    try:
        from app.core.database import get_minio_client as _gmc
        return _gmc()
    except Exception:
        # Fallback: try direct construction (for standalone inference scripts)
        try:
            from minio import Minio
            return Minio(
                endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
                access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
                secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
                secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
            )
        except ImportError:
            return None


def _download_checkpoint(model_code: str, version: str) -> bytes | None:
    """Download the DeepSpeed model checkpoint — tries local first, then MinIO.

    Returns the raw bytes of the checkpoint file, or None on failure.
    """
    # 1. Try local checkpoint directory first (most recent training run)
    local_paths = [
        os.path.join("/tmp/llmt_checkpoints", "ckpt", "mp_rank_00_model_states.pt"),
        os.path.join("/tmp/llmt_checkpoints", "latest", "mp_rank_00_model_states.pt"),
        os.path.join("./checkpoints", "ckpt", "mp_rank_00_model_states.pt"),
    ]
    for lp in local_paths:
        if os.path.isfile(lp):
            with open(lp, "rb") as f:
                return f.read()

    # DeepSpeed convention: checkpoints/latest is a file containing the dir name
    latest_file = os.path.join("./checkpoints", "latest")
    if os.path.isfile(latest_file):
        with open(latest_file, "r") as f:
            latest_dir = f.read().strip()
        candidate = os.path.join("./checkpoints", latest_dir, "mp_rank_00_model_states.pt")
        if os.path.isfile(candidate):
            with open(candidate, "rb") as f:
                return f.read()

    # Fallback: scan checkpoints/ for any DeepSpeed step dir
    ckpt_root = "./checkpoints"
    if os.path.isdir(ckpt_root):
        for entry in sorted(os.listdir(ckpt_root), reverse=True):
            entry_path = os.path.join(ckpt_root, entry)
            if os.path.isdir(entry_path):
                candidate = os.path.join(entry_path, "mp_rank_00_model_states.pt")
                if os.path.isfile(candidate):
                    with open(candidate, "rb") as f:
                        return f.read()

    # 2. Try MinIO models bucket
    minio = _get_minio_client()
    if minio is None:
        _log.warning("Checkpoint not found locally and MinIO unavailable")
        return None

    try:
        from app.core.config import get_settings
        bucket = get_settings().MINIO_BUCKET_MODELS
    except Exception:
        bucket = "models"

    object_name = f"models/{model_code}/{version}/mp_rank_00_model_states.pt"
    try:
        response = minio.get_object(bucket, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except Exception as exc:
        _log.warning("Failed to download checkpoint %s/%s: %s", bucket, object_name, exc)
        try:
            for obj in minio.list_objects(bucket, prefix=f"models/{model_code}/{version}/", recursive=True):
                if obj.object_name.endswith("model_states.pt"):
                    response = minio.get_object(bucket, obj.object_name)
                    data = response.read()
                    response.close()
                    response.release_conn()
                    return data
        except Exception:
            pass
        return None


def _find_tokenizer_vocab(model_code: str = "", version: str = "") -> str | None:
    """Find tokenizer_vocab.json — tries local checkpoint dirs, then MinIO.

    Returns a local file path, or None if not found.
    """
    # Check same locations as _download_checkpoint
    local_dirs = [
        os.path.join("/tmp/llmt_checkpoints", "ckpt"),
        os.path.join("/tmp/llmt_checkpoints", "latest"),
        os.path.join("./checkpoints", "ckpt"),
    ]

    # DeepSpeed latest file
    latest_file = os.path.join("./checkpoints", "latest")
    if os.path.isfile(latest_file):
        with open(latest_file, "r") as f:
            latest_dir = f.read().strip()
        local_dirs.append(os.path.join("./checkpoints", latest_dir))

    # Scan checkpoints/ subdirs
    ckpt_root = "./checkpoints"
    if os.path.isdir(ckpt_root):
        for entry in sorted(os.listdir(ckpt_root), reverse=True):
            entry_path = os.path.join(ckpt_root, entry)
            if os.path.isdir(entry_path):
                local_dirs.append(entry_path)

    for d in local_dirs:
        candidate = os.path.join(d, "tokenizer_vocab.json")
        if os.path.isfile(candidate):
            return candidate

    # Try downloading from MinIO
    if model_code and version:
        minio = _get_minio_client()
        if minio is not None:
            try:
                from app.core.config import get_settings
                bucket = get_settings().MINIO_BUCKET_MODELS
            except Exception:
                bucket = "models"
            prefix = f"models/{model_code}/{version}/"
            try:
                for obj in minio.list_objects(bucket, prefix=prefix, recursive=True):
                    if obj.object_name.endswith("tokenizer_vocab.json"):
                        response = minio.get_object(bucket, obj.object_name)
                        data = response.read()
                        response.close()
                        response.release_conn()
                        # Write to local cache so subsequent loads are instant
                        tmp_path = os.path.join(tempfile.gettempdir(), f"tokenizer_vocab_{model_code}_{version}.json")
                        with open(tmp_path, "wb") as f:
                            f.write(data)
                        return tmp_path
            except Exception as exc:
                _log.debug("Failed to download tokenizer vocab from MinIO: %s", exc)

    return None


def _load_tokenizer(model_type: str, model_config: dict[str, Any] | None,
                    model_code: str = "", version: str = "") -> Any:
    """Load the appropriate tokenizer.

    1. Try loading a saved SimpleTokenizer vocab from the checkpoint directory.
    2. Fall back to the model provider's tokenizer (e.g. GPT2Tokenizer).
    3. If that fails too, use a fresh SimpleTokenizer.
    """
    cfg = model_config or {}
    vocab_size = cfg.get("vocab_size", 50257)

    # Try saved tokenizer vocab from checkpoint
    vocab_path = _find_tokenizer_vocab(model_code, version)
    if vocab_path is not None:
        try:
            from llmt_training.core.simple_tokenizer import SimpleTokenizer
            _log.info("Loading tokenizer from %s", vocab_path)
            return SimpleTokenizer.load_vocab(vocab_path)
        except Exception as exc:
            _log.warning("Failed to load saved tokenizer vocab: %s", exc)

    # Fall back to model provider tokenizer
    try:
        from llmt_training.models.registry import ModelRegistry
        provider = ModelRegistry.get(model_type)
        return provider.get_tokenizer(cfg)
    except Exception as exc:
        _log.warning("Model provider tokenizer unavailable: %s, using SimpleTokenizer", exc)
        from llmt_training.core.simple_tokenizer import SimpleTokenizer
        return SimpleTokenizer(vocab_size=vocab_size)


def load_model(model_code: str, version: str, model_type: str = "gpt2",
               model_config: dict[str, Any] | None = None) -> tuple[torch.nn.Module, Any] | None:
    """Load a trained model into a ready-for-inference state.

    Returns (model, tokenizer) tuple, or None on failure.
    """
    cache_key = f"{model_code}:{version}"
    if cache_key in _cache:
        return _cache[cache_key]

    # 1. Download checkpoint
    checkpoint_bytes = _download_checkpoint(model_code, version)
    if checkpoint_bytes is None:
        return None

    # 2. Build model via registry
    from llmt_training.models.registry import ModelRegistry
    provider = ModelRegistry.get(model_type)
    cfg = model_config or {}
    model = provider.get_model(cfg)
    tokenizer = _load_tokenizer(model_type, cfg, model_code, version)

    # 3. Load state dict
    try:
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as tmp:
            tmp.write(checkpoint_bytes)
            tmp_path = tmp.name

        checkpoint = torch.load(tmp_path, map_location="cpu")
        os.unlink(tmp_path)

        # DeepSpeed saves state dict under 'module' key
        if "module" in checkpoint:
            state_dict = checkpoint["module"]
        else:
            state_dict = checkpoint

        # Filter out non-parameter keys (optimizer states etc.)
        model_keys = set(model.state_dict().keys())
        filtered = {k: v for k, v in state_dict.items() if k in model_keys}

        model.load_state_dict(filtered, strict=False)
        model.eval()

        # Move to GPU if available
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device)

    except Exception as exc:
        _log.error("Failed to load checkpoint for %s: %s", cache_key, exc)
        return None

    # 4. Cache
    _cache[cache_key] = (model, tokenizer)
    if len(_cache) > 8:  # evict oldest
        _cache.pop(next(iter(_cache)))
    return model, tokenizer


def run_inference(
    model: torch.nn.Module,
    tokenizer: Any,
    text: str,
    max_new_tokens: int = 50,
    temperature: float = 0.8,
    top_p: float = 0.9,
    top_k: int = 50,
) -> tuple[str, float]:
    """Run text generation inference.

    Returns (generated_text, latency_ms).
    """
    t0 = time.perf_counter()

    device = next(model.parameters()).device

    # Tokenize
    encoding = tokenizer(text, return_tensors="pt")
    input_ids = encoding["input_ids"].to(device)
    attention_mask = encoding.get("attention_mask")
    if attention_mask is not None:
        attention_mask = attention_mask.to(device)

    # Generate
    with torch.no_grad():
        generated_ids = _generate(
            model,
            input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            pad_token_id=getattr(tokenizer, "pad_token_id", None)
            or getattr(tokenizer, "eos_token_id", None)
            or 0,
        )

    # Decode only the new tokens
    new_ids = generated_ids[0, input_ids.shape[1]:]
    output_text = tokenizer.decode(new_ids, skip_special_tokens=True)

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return output_text, latency_ms


@torch.no_grad()
def _generate(
    model: torch.nn.Module,
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor | None,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
    pad_token_id: int,
) -> torch.Tensor:
    """Simple autoregressive generation loop."""
    generated = input_ids.clone()

    for _ in range(max_new_tokens):
        # Truncate to max model context length if needed
        seq_len = generated.shape[1]
        pos_ids = torch.arange(0, seq_len, device=generated.device).unsqueeze(0)

        outputs = model(input_ids=generated, attention_mask=attention_mask)

        logits = outputs.logits[:, -1, :]  # last token

        # Temperature
        if temperature > 0:
            logits = logits / temperature

        # top-k
        if top_k > 0:
            v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
            logits[logits < v[:, [-1]]] = float("-inf")

        # top-p
        if top_p < 1.0:
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cumulative_probs = torch.cumsum(
                torch.softmax(sorted_logits, dim=-1), dim=-1
            )
            sorted_indices_to_remove = cumulative_probs > top_p
            sorted_indices_to_remove[:, 1:] = sorted_indices_to_remove[:, :-1].clone()
            sorted_indices_to_remove[:, 0] = False
            indices_to_remove = sorted_indices_to_remove.scatter(
                1, sorted_indices, sorted_indices_to_remove
            )
            logits[indices_to_remove] = float("-inf")

        probs = torch.softmax(logits, dim=-1)
        next_token = torch.multinomial(probs, num_samples=1)

        generated = torch.cat([generated, next_token], dim=-1)

        # Stop on EOS
        if pad_token_id is not None and next_token.item() == pad_token_id:
            break

    return generated


def clear_cache() -> None:
    """Clear the model cache (for testing / memory management)."""
    _cache.clear()
