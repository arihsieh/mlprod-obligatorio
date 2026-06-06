#!/usr/bin/env python3
"""Download mmBERT-small from Hugging Face (cache for training)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.config import load_config
from mindful_news.training.train import download_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the base model for fine-tuning.")
    parser.add_argument("--model-id", help="Override config training.model_id")
    args = parser.parse_args()

    cfg = load_config().get("training", {})
    model_id = args.model_id or cfg.get("model_id", "jhu-clsp/mmBERT-small")
    cache_dir = Path(cfg.get("cache_dir", "models/cache"))

    print(f"Downloading {model_id} -> {cache_dir}")
    tokenizer, model, resolved_id = download_model(model_id=model_id, cache_dir=cache_dir)
    params = sum(p.numel() for p in model.parameters())
    print(f"Model: {resolved_id}")
    print(f"Parameters: {params:,}")
    print(f"Vocab size: {tokenizer.vocab_size}")
    print("Done.")


if __name__ == "__main__":
    main()
