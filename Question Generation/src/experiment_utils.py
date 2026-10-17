"""File names, prediction records, seeding and model selection, shared by the zero-shot,
few-shot and fine-tuning regimes.
"""

import os
import random
import re
from typing import List, Optional

from prompts import get_publication_time

ARCH_SHORT = {"encoder_decoder": "encdec", "decoder_only": "decoder"}


def set_seed(seed: int) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def arch_short(architecture: str) -> str:
    return ARCH_SHORT.get(architecture, architecture)


def prediction_filename(regime: str, train_setting: str, architecture: str,
                        model_short_name: str, seed: int) -> str:
    """{regime}__{train_setting}__{arch}__{model}__seed{seed}.jsonl"""
    return f"{regime}__{train_setting}__{arch_short(architecture)}__{model_short_name}__seed{seed}.jsonl"


def claimpt_percentage_of(train_setting: str) -> Optional[int]:
    """Silver percentage read from the setting name (`...silverNN`), or None."""
    match = re.search(r"silver(\d+)$", train_setting or "")
    return int(match.group(1)) if match else None


def build_prediction_record(example: dict, generated_questions: List[str], raw_output: str,
                            *, model_cfg: dict, regime: str, train_setting: str,
                            claimpt_percentage: Optional[int], seed: int,
                            generation_config: dict, few_shot_example_ids: List[str],
                            training: Optional[dict] = None) -> dict:
    """One line of a predictions JSONL: the example, the generated questions and the run settings."""
    return {
        "id": example.get("id", ""),
        "claim_span": example.get("claim_span", ""),
        "context": example.get("context", ""),
        "claim_objects": example.get("claim_objects", []),
        "claimers": example.get("claimers", []),
        "publication_time": get_publication_time(example),
        "claim_time": example.get("claim_time", ""),
        "reference_questions": example.get("reference_questions", []),
        "generated_questions": generated_questions,
        "raw_output": raw_output,

        "model_name": model_cfg.get("model_name_or_path", ""),
        "model_short_name": model_cfg.get("short_name", ""),
        "architecture": model_cfg.get("architecture", ""),
        "language_group": model_cfg.get("language_group", ""),

        "regime": regime,
        "train_setting": train_setting,
        "claimpt_percentage": claimpt_percentage,

        "seed": seed,
        "generation_config": generation_config,
        "few_shot_example_ids": few_shot_example_ids,

        "training": training,
    }


def select_models(models: List[dict], only: Optional[str]) -> List[dict]:
    """Filter the YAML models by --only (comma-separated short names); unknown names are an error."""
    if not only:
        return models
    wanted = {s.strip() for s in only.split(",") if s.strip()}
    escolhidos = [m for m in models if m.get("short_name") in wanted]
    faltam = wanted - {m.get("short_name") for m in escolhidos}
    if faltam:
        raise SystemExit(
            f"--only pediu {sorted(faltam)}, que não está(ão) neste YAML. "
            f"Disponíveis: {sorted(m.get('short_name', '') for m in models)}")
    return escolhidos
