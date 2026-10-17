"""Question generation for a list of examples with an already loaded model.

Used by run_inference.py (zero-/few-shot), by the per-epoch dev evaluation and by the
final training script.
"""

from typing import Callable, List, Tuple

from parsing_utils import parse_questions


def _generation_kwargs(gen_cfg: dict) -> dict:
    """Generation config -> keyword arguments of `.generate()`."""
    kwargs = dict(
        max_new_tokens=gen_cfg.get("max_new_tokens", 192),
        do_sample=bool(gen_cfg.get("do_sample", False)),
        num_beams=gen_cfg.get("num_beams", 1),
        repetition_penalty=gen_cfg.get("repetition_penalty", 1.0),
    )
    if gen_cfg.get("no_repeat_ngram_size"):
        kwargs["no_repeat_ngram_size"] = gen_cfg["no_repeat_ngram_size"]
    # Only present for models whose YAML declares them (see model_utils.stop_token_overrides).
    for chave in ("eos_token_id", "pad_token_id"):
        if gen_cfg.get(chave) is not None:
            kwargs[chave] = gen_cfg[chave]
    return kwargs


def _decode_new_tokens(tokenizer, output_ids, input_len: int) -> str:
    """Decode only the generated tokens (decoder-only outputs include the prompt)."""
    new_ids = output_ids[input_len:]
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip()


def generate_for_examples(model, tokenizer, examples: List[dict], architecture: str,
                          gen_cfg: dict, prompt_fn: Callable[[dict], str],
                          max_source_length: int = 1024,
                          add_special_tokens: bool = True) -> List[Tuple[List[str], str]]:
    """Generate for each example; returns a list of (questions, raw_output).

    `add_special_tokens` must be False when the prompt is already in the chat template.
    """
    import torch

    model.eval()
    try:  # training with gradient checkpointing turns the cache off
        model.config.use_cache = True
    except Exception:
        pass
    device = next(model.parameters()).device
    kwargs = _generation_kwargs(gen_cfg)
    kwargs["use_cache"] = True
    is_decoder = architecture == "decoder_only"
    results: List[Tuple[List[str], str]] = []

    for i, ex in enumerate(examples, 1):
        prompt = prompt_fn(ex)
        enc = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=max_source_length,
                        add_special_tokens=add_special_tokens)
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model.generate(**enc, **kwargs)
        if is_decoder:
            raw = _decode_new_tokens(tokenizer, out[0], enc["input_ids"].shape[1])
        else:
            raw = tokenizer.decode(out[0], skip_special_tokens=True).strip()
        results.append((parse_questions(raw), raw))
        if i % 10 == 0:
            print(f"    geradas {i}/{len(examples)}")
    return results
