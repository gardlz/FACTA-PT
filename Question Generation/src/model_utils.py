"""Model/tokenizer loading (offline), the ±1-sentence context window and decoding settings.

torch and transformers are imported inside the functions, so the data and metric modules
do not depend on them.
"""

import re
import warnings
from typing import Tuple


def _dtype(bf16: bool):
    import torch
    return torch.bfloat16 if bf16 else torch.float32


def load_tokenizer(model_name: str, offline: bool):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(
        model_name, local_files_only=offline, use_fast=True, trust_remote_code=True,
    )
    if tok.pad_token is None and getattr(tok, "eos_token", None) is not None:
        tok.pad_token = tok.eos_token
    return tok


def _forcar_fp32(model, model_name: str):
    """Cast to fp32 when a checkpoint sub-config left some weights in bf16.

    `torch_dtype` only applies at the top level; full fine-tuning and LoRA expect fp32
    weights with bf16 autocast. Never called for 4-bit (QLoRA) models.
    """
    import torch

    maus = {p.dtype for p in model.parameters() if p.is_floating_point()} - {torch.float32}
    if not maus:
        return model
    warnings.warn(
        f"{model_name}: pesos vieram em {', '.join(sorted(str(d) for d in maus))} apesar de se "
        f"ter pedido fp32 (sub-config do checkpoint); a forçar fp32 para cumprir o protocolo "
        f"(pesos fp32 + autocast bf16).")
    model = model.float()
    restantes = {p.dtype for p in model.parameters() if p.is_floating_point()} - {torch.float32}
    if restantes:
        raise RuntimeError(
            f"{model_name}: não foi possível forçar fp32; ficaram {sorted(str(d) for d in restantes)}.")
    return model


def load_encoder_decoder(model_name: str, offline: bool = True, bf16: bool = True,
                         load_in_4bit: bool = False) -> Tuple:
    """Load a seq2seq model, optionally quantised to 4-bit NF4 at load time (QLoRA)."""
    from transformers import AutoModelForSeq2SeqLM
    try:
        tokenizer = load_tokenizer(model_name, offline)
        kwargs = dict(local_files_only=offline, torch_dtype=_dtype(bf16), trust_remote_code=True)
        quant = _bnb_config(load_in_4bit, bf16)
        if quant is not None:
            kwargs["quantization_config"] = quant
            kwargs["device_map"] = {"": 0}      # single GPU
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name, **kwargs)
    except Exception as e:
        raise RuntimeError(
            f"Não foi possível carregar o modelo encoder-decoder '{model_name}' "
            f"(offline={offline}, 4bit={load_in_4bit}). O modelo tem de estar no cache local "
            f"(HF_HOME). Erro: {e}"
        ) from e
    if not bf16 and not load_in_4bit:
        model = _forcar_fp32(model, model_name)
    return model, tokenizer


def _bnb_config(load_in_4bit: bool, bf16: bool):
    if not load_in_4bit:
        return None
    from transformers import BitsAndBytesConfig
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=_dtype(bf16),
    )


def load_decoder(model_name: str, offline: bool = True, bf16: bool = True,
                 load_in_4bit: bool = False) -> Tuple:
    """Load a decoder-only model, optionally quantised to 4-bit NF4 (QLoRA)."""
    from transformers import AutoModelForCausalLM
    try:
        tokenizer = load_tokenizer(model_name, offline)
        kwargs = dict(local_files_only=offline, torch_dtype=_dtype(bf16), trust_remote_code=True)
        quant = _bnb_config(load_in_4bit, bf16)
        if quant is not None:
            kwargs["quantization_config"] = quant
            kwargs["device_map"] = {"": 0}      # single GPU
        model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)
    except Exception as e:
        raise RuntimeError(
            f"Não foi possível carregar o modelo decoder-only '{model_name}' "
            f"(offline={offline}, 4bit={load_in_4bit}). O modelo tem de estar no cache local "
            f"(HF_HOME). Erro: {e}"
        ) from e
    if not bf16 and not load_in_4bit:
        model = _forcar_fp32(model, model_name)
    return model, tokenizer


def to_device(model):
    """Move to CUDA unless the model was already placed by a device_map."""
    import torch
    if hasattr(model, "hf_device_map"):
        return model
    if torch.cuda.is_available():
        return model.to("cuda")
    return model


def free_model(*objs) -> None:
    """Release GPU memory between models."""
    import gc
    del objs
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _find_span(context: str, claim_span: str):
    """(start, end) of the claim span in the context, tolerant to whitespace; None if absent."""
    if not context or not claim_span:
        return None
    i = context.find(claim_span)
    if i >= 0:
        return i, i + len(claim_span)
    words = [re.escape(w) for w in claim_span.split() if w]
    if not words:
        return None
    m = re.search(r"\s+".join(words), context)
    if m:
        return m.start(), m.end()
    m = re.search(r"\s+".join(words[:6]), context)
    if m:
        return m.start(), min(len(context), m.start() + len(claim_span))
    return None


# Sentence end: ".", "!" or "?" followed by whitespace, except after common Portuguese
# abbreviations and single capital initials ("J. Silva").
_ABBREV = (r"(?<!\bSr)(?<!\bSra)(?<!\bDr)(?<!\bDra)(?<!\bEng)(?<!\bProf)(?<!\bex)(?<!\bp)"
           r"(?<!\bfig)(?<!\bart)(?<!\bpág)(?<!\bvs)"
           r"(?<!\s[A-ZÀ-Þ])")
_SENT_END_RE = re.compile(r"(?<=[.!?])(?=\s)")


def split_sentences(text: str):
    """Sentence (start, end) offsets; a deliberately simple, dependency-free splitter."""
    if not text:
        return []
    cuts = [0]
    for m in _SENT_END_RE.finditer(text):
        i = m.start()
        if re.search(_ABBREV + r"[.!?]$", text[:i]):
            cuts.append(i)
    cuts.append(len(text))
    spans = []
    for a, b in zip(cuts, cuts[1:]):
        if text[a:b].strip():
            spans.append((a, b))
    return spans or [(0, len(text))]


def sentence_window(context: str, claim_span: str, n_before: int = 1, n_after: int = 1):
    """Previous sentence + sentence(s) containing the claim span + next sentence, or None."""
    span = _find_span(context, claim_span)
    if span is None:
        return None
    start, end = span
    sents = split_sentences(context)
    hit = [i for i, (a, b) in enumerate(sents) if a < end and b > start]
    if not hit:
        return None
    lo = max(0, hit[0] - n_before)
    hi = min(len(sents) - 1, hit[-1] + n_after)
    return context[sents[lo][0]:sents[hi][1]].strip()


def _n_tokens(tokenizer, text: str) -> int:
    """Token count including special tokens."""
    return len(tokenizer(text, add_special_tokens=True)["input_ids"])


def _check_fits(tokenizer, prompt: str, example: dict, max_len: int, reserve: int) -> None:
    """Stop if the prompt does not fit the model window minus the tokens kept for the output.

    Every model receives the same prompt text, so a prompt is never shortened to fit.
    """
    budget = max_len - reserve
    n = _n_tokens(tokenizer, prompt)
    if n > budget:
        raise ValueError(
            f"A prompt de {example.get('id', '')} tem {n} tokens e a janela do modelo comporta "
            f"{budget} ({max_len}, menos {reserve} reservados para a geração). O contexto de ±1 "
            f"frase tem de ser o mesmo em todos os modelos: subir max_source_length/"
            f"max_seq_length no YAML deste modelo, ou tirá-lo do regime.")


def claim_context(example: dict) -> str:
    """The ±1-sentence window around the claim span (tokenizer-independent); "" if not found."""
    return sentence_window(example.get("context", ""), example.get("claim_span", "")) or ""


def fit_input(tokenizer, example: dict, max_len: int, reserve: int = 0) -> str:
    """Zero-shot / fine-tuning input with the ±1-sentence context; it must fit the model window."""
    from prompts import build_input, get_publication_time

    prompt = build_input(example.get("claim_span", ""), get_publication_time(example),
                         claim_context(example))
    _check_fits(tokenizer, prompt, example, max_len, reserve)
    return prompt


def fit_fewshot_input(tokenizer, example: dict, shots: list, max_len: int,
                      reserve: int = 0) -> str:
    """Few-shot input with the ±1-sentence context in the query and in every demonstration.

    The prompt must fit the model window, like the zero-shot one.
    """
    from prompts import build_fewshot_input

    query = {**example, "context": claim_context(example)}
    windowed = [{**s, "context": claim_context(s)} for s in shots]
    prompt = build_fewshot_input(query, windowed)
    _check_fits(tokenizer, prompt, example, max_len, reserve)
    return prompt


def wants_chat_template(tokenizer, architecture: str) -> bool:
    """True for a decoder-only model whose tokenizer has a chat template."""
    return architecture == "decoder_only" and getattr(tokenizer, "chat_template", None) is not None


def to_chat_prompt(tokenizer, prompt: str, template_kwargs: dict = None) -> str:
    """Wrap the prompt as a user turn of the model's chat template (special tokens included)."""
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True,
        **(template_kwargs or {}))


def stop_token_overrides(model_cfg: dict, tokenizer) -> dict:
    """Stop/pad token ids declared in the model YAML (`eos_token`/`pad_token`).

    Needed when a repository's generation_config disagrees with its own tokenizer
    (GlórIA declares an eos id that is an ordinary word). Models without the keys get {}.
    """
    overrides = {}
    for chave in ("eos_token", "pad_token"):
        token = model_cfg.get(chave)
        if not token:
            continue
        tid = tokenizer.convert_tokens_to_ids(token)
        # Round trip: an unknown token resolves to unk, which does not map back to it.
        if tid is None or tokenizer.convert_ids_to_tokens(tid) != token:
            raise RuntimeError(
                f"{chave}='{token}' não existe no vocabulário de "
                f"'{model_cfg.get('short_name')}'. Corrigir configs/*.yaml.")
        overrides[f"{chave}_id"] = tid
    return overrides


def neutral_generation_config() -> dict:
    """Greedy decoding with 192 new tokens, identical for both architectures and all regimes."""
    return {
        "max_new_tokens": 192,
        "do_sample": False,
        "num_beams": 1,
        "repetition_penalty": 1.0,
        "no_repeat_ngram_size": 0,
    }
