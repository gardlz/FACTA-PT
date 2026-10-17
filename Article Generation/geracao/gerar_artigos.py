"""Generate the fact-checking articles of one condition with one open model, using offline vLLM.

All plans in `dados/planos/<condicao>/` go in one batch under the editorial JSON grammar, and each
article is written to `dados/artigos/<condicao>/<model>/`; spans whose article is already there are
skipped. Before the model is loaded, every prompt is checked to leave the full --max_tokens for the
article; articles that fail, need repair or loop are retried.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

# vllm and transformers are imported inside main(), so importing this module (carbono.py does) does
# not need them.
import esquema as ev                           # noqa: E402
import plano as pv                             # noqa: E402
import prompt_base as pb                          # noqa: E402
import render as rv                            # noqa: E402

PLANOS = pv.SAIDAS / "planos"
ARTIGOS = pv.SAIDAS / "artigos"
SUFIXO_SEM_GRAMATICA = "_sem_gramatica"
DTYPE = "bfloat16"  # forced for every model

# Four times the default max_tokens. verificar_comprimentos() checks, with the model's own
# tokenizer, that every prompt still leaves the full max_tokens for the article.
MAX_MODEL_LEN = 16384


# --------------------------------------------------------------------------- model output
# Supported models and their short names (the name of the article folder).
NOMES = {
    "amalia-llm/AMALIA-9B-0626-DPO": "amalia_9b",
    "utter-project/EuroLLM-9B-Instruct-2512": "eurollm_9b",
    "google/gemma-4-E4B-it": "gemma4_e4b",
    "PORTULAN/gervasio-8b-portuguese-ptpt-decoder": "gervasio_8b",
    "meta-llama/Llama-3.2-3B-Instruct": "llama32_3b",
    "meta-llama/Llama-3.1-8B-Instruct": "llama_3_1_8b_instruct",
    "Qwen/Qwen3.5-4B": "qwen35_4b",
    "Qwen/Qwen3.5-9B": "qwen35_9b",
}


def nome_curto(modelo: str) -> str:
    if modelo not in NOMES:
        raise SystemExit(f"[recusa] modelo fora da lista: {modelo!r}. "
                         f"Modelos: {', '.join(NOMES)}.")
    return NOMES[modelo]


# Fixed formats for models without a registered chat template (system, user, assistant header).
_LLAMA3 = ("<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{sistema}<|eot_id|>"
           "<|start_header_id|>user<|end_header_id|>\n\n{plano}<|eot_id|>"
           "<|start_header_id|>assistant<|end_header_id|>\n\n")

_CHATML = ("<|im_start|>system\n{sistema}<|im_end|>\n"
           "<|im_start|>user\n{plano}<|im_end|>\n"
           "<|im_start|>assistant\n")

# Cycle detector: an article loops when one word 8-gram occurs LIMIAR_CICLO times or more.
LIMIAR_CICLO = 6
_CERCA = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def primeiro_json(texto: str) -> Optional[str]:
    """First complete JSON object in the text, by brace matching; anything after it is ignored."""
    inicio = texto.find("{")
    if inicio < 0:
        return None
    profundidade, dentro_de_string, escape = 0, False, False
    for i, caracter in enumerate(texto[inicio:], inicio):
        if dentro_de_string:
            if escape:
                escape = False
            elif caracter == "\\":
                escape = True
            elif caracter == '"':
                dentro_de_string = False
            continue
        if caracter == '"':
            dentro_de_string = True
        elif caracter == "{":
            profundidade += 1
        elif caracter == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio:i + 1]
    return None


def reparar_json(texto: str) -> Optional[dict]:
    """Close a truncated JSON object at its last complete value; None if nothing can be saved."""
    inicio = texto.find("{")
    if inicio < 0:
        return None
    cortes, pilha, dentro, escape = [], [], False, False
    for i, caracter in enumerate(texto[inicio:], inicio):
        if dentro:
            if escape:
                escape = False
            elif caracter == "\\":
                escape = True
            elif caracter == '"':
                dentro = False
                cortes.append((i + 1, tuple(pilha)))
            continue
        if caracter == '"':
            dentro = True
        elif caracter in "{[":
            pilha.append(caracter)
        elif caracter in "}]":
            if pilha:
                pilha.pop()
            cortes.append((i + 1, tuple(pilha)))
    # Latest cut first: the later the cut, the more of the article is kept.
    for corte, aberto in reversed(cortes[-500:]):
        candidato = texto[:corte].rstrip().rstrip(",")
        candidato += "".join("}" if c == "{" else "]" for c in reversed(aberto))
        try:
            dados = json.loads(candidato)
        except json.JSONDecodeError:
            continue
        if isinstance(dados, dict):
            return dados
    return None


def repeticao(texto: str) -> int:
    """Count of the most frequent word 8-gram in the text (the cycle detector)."""
    palavras = texto.split()
    if len(palavras) < 8:
        return 0
    vistos, maior = {}, 0
    for i in range(len(palavras) - 7):
        grama = " ".join(palavras[i:i + 8])
        vistos[grama] = vistos.get(grama, 0) + 1
        maior = max(maior, vistos[grama])
    return maior


def _pontos(registo: dict):
    """Ranking key between two attempts at the same span; higher is better."""
    limpo = registo["estado"] == "ok" and registo["repeticao_max"] < LIMIAR_CICLO
    posicao = {"ok": 2, "reparado": 1}.get(registo["estado"], 0)
    return (1 if limpo else 0, posicao, -registo["repeticao_max"])


def precisa_retentar(registo: dict) -> bool:
    """True for an article that failed, needed repair, or loops."""
    return registo["estado"] != "ok" or registo["repeticao_max"] >= LIMIAR_CICLO


def _extras_esquema() -> dict:
    """Request-level `disable_any_whitespace=True`; exits if this vLLM does not support it."""
    from vllm.sampling_params import StructuredOutputsParams
    # Without it, xgrammar allows unlimited whitespace between JSON tokens, and a stuck model can
    # spend all of max_tokens on indentation.
    if "disable_any_whitespace" not in (getattr(StructuredOutputsParams, "__dataclass_fields__", {})
                                        or {}):
        raise SystemExit("[recusa] este vLLM não tem `disable_any_whitespace` nos parâmetros da "
                         "gramática, e a geração precisa dele.")
    return {"disable_any_whitespace": True}


# --------------------------------------------------------------------------- utilities
def contar_estados(registos) -> Dict[str, int]:
    return dict(sorted(Counter(r["estado"] for r in registos).items()))


def _recusa(titulo: str, problemas: List[str], remedio: str) -> None:
    """Exit before generating, listing what is wrong (the first 10 problems) and the fix."""
    linhas = [f"[recusa] {titulo}"] + [f"  - {p}" for p in problemas[:10]]
    if len(problemas) > 10:
        linhas.append(f"  ... e mais {len(problemas) - 10}")
    linhas.append(remedio)
    raise SystemExit("\n".join(linhas))


# --------------------------------------------------------------------------- plans
def carregar_planos(pasta: Path) -> List[dict]:
    """Plans in the folder (one `<claim_span_id>.json` per claim span), in file order."""
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(pasta.glob("*.json"))]


def resolver_planos(args) -> Tuple[str, Path]:
    """(condition, plans folder): `dados/planos/<condicao>`."""
    pasta = PLANOS / args.condicao
    if not pasta.is_dir():
        raise SystemExit(f"[recusa] a pasta dos planos não existe: {pasta}")
    return args.condicao, pasta


def nome_da_pasta_do_modelo(curto: str, com_gramatica: bool) -> str:
    """`<modelo_curto>`, or `<modelo_curto>_sem_gramatica` for a run without the grammar."""
    return curto if com_gramatica else curto + SUFIXO_SEM_GRAMATICA


def pasta_de_saida(args, condicao: str, curto: str) -> Path:
    """`dados/artigos/<condicao>/<model folder>`."""
    return ARTIGOS / condicao / nome_da_pasta_do_modelo(curto, not args.sem_gramatica)


# --------------------------------------------------------------------------- prompt
def construir_prompt(tokenizer, plano: dict, modelo: str, formato: str = "auto") -> str:
    """The exact prompt: base prompt as system turn, plan message as user turn, in `formato`."""
    sistema, corpo = pb.PROMPT_BASE, rv.mensagem(plano)
    if formato == "llama3":
        return _LLAMA3.format(sistema=sistema, plano=corpo)
    if formato == "chatml":
        return _CHATML.format(sistema=sistema, plano=corpo)
    if tokenizer.chat_template is None:
        raise SystemExit(f"[recusa] {modelo} não tem chat template: usa --formato llama3 ou "
                         "chatml.")
    extra = {}
    if "qwen" in modelo.lower():
        # Reasoning models: without this the article comes after a <think> block.
        extra["enable_thinking"] = False
    return tokenizer.apply_chat_template(pb.mensagens(corpo), tokenize=False,
                                         add_generation_prompt=True, **extra)


def verificar_comprimentos(tokenizer, prompts: Dict[str, str], max_tokens: int,
                           max_model_len: int) -> Dict[str, int]:
    """Tokens per prompt; exits if a prompt does not leave the full max_tokens for the article."""
    # Special tokens (BOS) included, as vLLM counts them when it tokenizes the text.
    n = {i: len(tokenizer(p)["input_ids"]) for i, p in prompts.items()}
    excedem = sorted((i for i in n if n[i] + max_tokens > max_model_len), key=lambda i: -n[i])
    if excedem:
        _recusa(f"{len(excedem)} prompts não deixam {max_tokens} tokens para o artigo dentro de "
                f"--max_model_len {max_model_len}.",
                [f"{i}: {n[i]} tokens de prompt" for i in excedem],
                "Sobe --max_model_len (se o modelo o suportar) ou baixa --max_tokens; um modelo "
                "cujo contexto nativo não chegue fica fora da geração.")
    return n


# --------------------------------------------------------------------------- response
def interpretar(bruto: str) -> dict:
    """Model text -> response record. Nothing is rewritten; only complete content is recovered."""
    texto = _CERCA.sub("", (bruto or "").strip())
    achado = primeiro_json(texto)
    dados, falha, reparado = None, None, False
    if achado is None:
        falha = "sem_json"
    else:
        try:
            dados = json.loads(achado)
        except json.JSONDecodeError as e:
            falha = f"json_invalido: {e.msg}"
    if dados is None:
        dados = reparar_json(texto)
        reparado = dados is not None
    if not isinstance(dados, dict):
        return {"estado": falha or "sem_json", "resposta": None, "repeticao_max": 0}

    blocos = ev.para_blocos(dados) if isinstance(dados.get("seccoes"), list) else []
    lead = dados.get("lead") if isinstance(dados.get("lead"), str) else ""
    texto_todo = " ".join([lead] + [b["text"] for b in blocos])
    if not blocos:
        estado = "sem_seccoes"
    else:
        estado = "reparado" if reparado else "ok"
    return {"estado": estado, "resposta": dados, "repeticao_max": repeticao(texto_todo)}


# --------------------------------------------------------------------------- article record
def montar(plano: dict, saida) -> dict:
    """One article record: what the model wrote and how the generation went."""
    gerado = saida.outputs[0]
    bruto = gerado.text
    truncado = gerado.finish_reason == "length"
    lido = interpretar(bruto)
    if truncado and lido["estado"] not in ("ok", "reparado"):
        lido["estado"] = "truncado"
    return {
        "claim_span_id": plano["claim_span_id"],
        "resposta": lido["resposta"],
        "estado": lido["estado"],
        "repeticao_max": lido["repeticao_max"],
        "bruto": bruto,
        "finish_reason": gerado.finish_reason,
        "truncado": truncado,
    }


# --------------------------------------------------------------------------- command line
def argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelo", required=True,
                   help="Id do modelo no Hugging Face (um dos modelos de NOMES).")
    p.add_argument("--condicao", choices=sorted(pv.CONDICOES), default="full",
                   help="Condição da ablação (full por omissão). Os planos vêm de "
                        "dados/planos/<condicao>.")
    p.add_argument("--max_tokens", type=int, default=4096)
    p.add_argument("--max_model_len", type=int, default=MAX_MODEL_LEN,
                   help="Contexto máximo do modelo. Antes de gerar confirma-se que cada prompt "
                        "deixa os --max_tokens inteiros para o artigo.")
    p.add_argument("--repeticao", type=float, default=1.05,
                   help="Penalização de repetição da primeira tentativa.")
    p.add_argument("--retentar", type=int, default=1,
                   help="Tentativas extra só para os artigos que não saíram ou saíram em ciclo.")
    p.add_argument("--retentar_repeticao", type=float, default=1.15,
                   help="Penalização da 1.ª retentativa (+0.10 em cada seguinte). Com "
                        "temperatura 0 é a única alavanca: mudar a semente não muda nada.")
    p.add_argument("--temperatura", type=float, default=0.0, help="0 = greedy (determinístico).")
    p.add_argument("--top_p", type=float, default=1.0,
                   help="Núcleo da amostragem. Só tem efeito com --temperatura > 0.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--formato", choices=("auto", "llama3", "chatml"), default="auto",
                   help="auto usa o chat template do modelo (e falha se ele não o tiver). llama3 "
                        "para o Gervásio, chatml para o EuroLLM-9B (os tokens estão no "
                        "vocabulário, o template não está registado).")
    p.add_argument("--gpu_memory_utilization", type=float, default=0.90)
    p.add_argument("--sem_gramatica", action="store_true",
                   help="Desliga a gramática editorial (condições sem gramática da ablação). A "
                        "pasta do modelo leva o sufixo _sem_gramatica.")
    return p.parse_args()


def main() -> None:
    args = argumentos()
    com_gramatica = not args.sem_gramatica

    # 1. Plans (no GPU, no vLLM).
    condicao, pasta_planos = resolver_planos(args)
    todos = carregar_planos(pasta_planos)
    if not todos:
        raise SystemExit(f"[recusa] a pasta dos planos não tem planos: {pasta_planos}")

    curto = nome_curto(args.modelo)
    destino = pasta_de_saida(args, condicao, curto)

    # 2. Grammar options, still without GPU.
    extras_esquema = {}
    if com_gramatica:
        from vllm.sampling_params import StructuredOutputsParams
        extras_esquema = _extras_esquema()

    # Spans that already have an article in the output folder are not generated again.
    destino.mkdir(parents=True, exist_ok=True)
    planos = [pl for pl in todos if not (destino / f"{pl['claim_span_id']}.json").exists()]
    if not planos:
        print(f"[{curto}] nada a fazer: todos os artigos já existem em {destino}.")
        return

    # 3. Prompts in the model's format, and the check that they all fit.
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams

    tokenizer = AutoTokenizer.from_pretrained(args.modelo, trust_remote_code=True)
    prompts = {pl["claim_span_id"]: construir_prompt(tokenizer, pl, args.modelo, args.formato)
               for pl in planos}
    comprimentos = verificar_comprimentos(tokenizer, prompts, args.max_tokens, args.max_model_len)
    maior = max(comprimentos, key=comprimentos.get)
    print(f"[{curto}] {condicao}: {len(planos)} planos | prompt máx. {comprimentos[maior]} "
          f"tokens ({maior}) | max_model_len {args.max_model_len} | max_tokens {args.max_tokens}")

    # 4. Model.
    extra_llm = {}
    # In vLLM 0.19.1 the xgrammar backend reads disable_any_whitespace only from the engine config
    # and ignores the per-request value. The backend is pinned to xgrammar.
    if com_gramatica:
        extra_llm["structured_outputs_config"] = {"backend": "xgrammar",
                                                  "disable_any_whitespace": True}
    llm = LLM(model=args.modelo, dtype=DTYPE, seed=args.seed,
              max_model_len=args.max_model_len, tensor_parallel_size=1,
              gpu_memory_utilization=args.gpu_memory_utilization, trust_remote_code=True,
              **extra_llm)

    def amostrar(lote: List[dict], penalizacao: float):
        """Sampling parameters for a batch, with one grammar per plan."""
        comuns = dict(temperature=args.temperatura, top_p=args.top_p,
                      max_tokens=args.max_tokens, seed=args.seed,
                      repetition_penalty=penalizacao)
        if not com_gramatica:
            return SamplingParams(**comuns)
        return [SamplingParams(structured_outputs=StructuredOutputsParams(
                    json=ev.esquema_do_plano(plano), **extras_esquema), **comuns)
                for plano in lote]

    def gerar(lote: List[dict], penalizacao: float) -> Dict[str, dict]:
        saidas = llm.generate([prompts[pl["claim_span_id"]] for pl in lote],
                              amostrar(lote, penalizacao))
        return {pl["claim_span_id"]: montar(pl, sa) for pl, sa in zip(lote, saidas)}

    # 5. Generate, then retry only what failed or loops. The batch is not rerun, so articles that
    #    came out fine keep their first output.
    registos = gerar(planos, args.repeticao)
    por_id = {pl["claim_span_id"]: pl for pl in planos}
    for tentativa in range(2, args.retentar + 2):
        fila = sorted(i for i, r in registos.items() if precisa_retentar(r))
        if not fila:
            break
        penalizacao = args.retentar_repeticao + (tentativa - 2) * 0.10
        print(f"[{curto}] tentativa {tentativa}: {len(fila)} artigos com "
              f"repetition_penalty={penalizacao:.2f} - {', '.join(fila)}")
        for ident_span, candidato in gerar([por_id[i] for i in fila], penalizacao).items():
            anterior = registos[ident_span]
            if _pontos(candidato) > _pontos(anterior):
                registos[ident_span] = candidato
            else:
                print(f"  {ident_span}: a retentativa não melhorou "
                      f"({anterior['estado']}/rep={anterior['repeticao_max']} manteve-se)")

    # 6. One file per article.
    for span_id, registo in registos.items():
        (destino / f"{span_id}.json").write_text(
            json.dumps(registo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[{curto}] {len(registos)} artigos -> {destino}")
    for estado, n in contar_estados(registos.values()).items():
        print(f"  {estado:24} {n:3}")
    em_ciclo = sorted(i for i, r in registos.items() if r["repeticao_max"] >= LIMIAR_CICLO)
    if em_ciclo:
        print(f"  AINDA EM CICLO ({len(em_ciclo)}): {', '.join(em_ciclo)}")


if __name__ == "__main__":
    main()
