"""Silver verification questions for ClaimPT claim spans with Gemini (one call per claim span).

Writes one JSONL line per span and resumes from what the output already holds; spans that
fail after the retries go to `<output>_failed.jsonl`. Reads ClaimPT, and the six CLEVER claim
spans of the few-shot demonstrations, from the root of the repository, and `.env` from this
stage's folder.

    python silver_generation/generate_questions.py --input ../ClaimPT/claimpt_test.json \
        --output silver_generation/outputs/claimpt_test_silver_questions.jsonl
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from clever_claimpt import (CLAIMPT_ARTIGOS, CLAIMPT_JSON, CLEVER_JSON, _clean,  # noqa: E402
                            iter_span_units, ler_json, parse_date, span_clever)

log = logging.getLogger("qg")


# Prompt (the task instrument, kept in European Portuguese).
CRITERIOS = """
Critérios para formulação de perguntas para verificação de claims:

1. Formulação das questões por segmento da claim
- As perguntas devem estar centradas obrigatoriamente no elemento claim span.
- Cada pergunta deve estar estritamente vinculada ao claim object correspondente ao seu span.

2. Quantas perguntas gerar (cardinalidade)
- O número de perguntas segue o número de subfactos distintos e verificáveis do claim span — tipicamente entre 1 e 4.
- Se o span contém um único facto indivisível, gerar UMA pergunta. Não a duplicar com uma paráfrase.
- Se contém dois ou mais subfactos distintos (números, datas, entidades, comparações, ações), gerar uma pergunta por subfacto, até 4.
- Quando desdobrável, é útil combinar uma pergunta de nível geral (temática ampla do claim object) com perguntas de nível específico (números, datas, nomes, valores, instituições).
- NÃO gerar paráfrases do mesmo subfacto. Em particular, evitar o par "É verdade que X?" + "Qual o valor de X?": se o subfacto é único, basta UMA pergunta (de preferência a específica).
- Utilizar os links de identity para substituir pronomes, como "este sistema", "isso", "elas" ou "lá", pelos nomes próprios das entidades, garantindo clareza para a busca.

3. Critérios adicionais
- Neutralidade: evitar termos subjetivos ou que induzam confirmação/negação. Em vez de "Por que razão a medida falhou?", usar "Qual foi o resultado da medida X?".
- Independentemente de o stance ser Affirm ou Refute, a pergunta deve ser imparcial e focar-se no facto alegado, não na opinião ou crença do claimer.
- Anchoring temporal: sempre que o elemento Time estiver presente, ou puder ser inferido via identity com a publication time, incluir a baliza temporal, por exemplo "até maio de 2025", "em 2015" ou "no apagão de 2025".
- Tópicos locais: mencionar explicitamente a região ou entidade territorial referida, por exemplo "em Braga", "em Vila Verde" ou "no Algarve", para evitar ambiguidades com factos semelhantes noutras localidades.
- Integrar o claimer apenas quando a validade do facto depende da autoridade de quem o profere, por exemplo uma declaração presidencial ou posição oficial de uma entidade. Não integrar o claimer apenas para citar o ato de fala, como "X afirmou em audição que...".
- Se a alegação referir estudos ou relatórios, estruturar a pergunta para localizar o documento específico.
- Em claims comparativas, como "mais do que no ano passado", desdobrar a verificação para obter os valores de ambos os pontos de comparação.

Etapas para a formulação:
1. Delimitar o claim span e garantir que tem significado completo.
2. Isolar o claim object — o termo mais específico dentro do claim span.
3. Identificar os subfactos distintos e verificáveis do span; o número de perguntas segue esses subfactos.
4. Usar claimer, time, identity e contexto apenas para desambiguar, resolver pronomes e situar temporalmente.
5. Escrever uma pergunta pesquisável por cada subfacto (geral para o tema, específica para os dados concretos).
""".strip()


# The six CLEVER claim spans of the few-shot block (Appendix A.3.3): the comment that introduces
# each one and, when the demonstration shows only some of the annotated claimers, their positions
# in the annotation.
DEMONSTRACOES = [
    ("clever_202_c2", "Facto único e indivisível -> UMA pergunta (não paráfrasear)", (0, 1)),
    ("clever_006_c6", 'Resolução pronominal ("aquilo" -> teto às rendas) -> geral + específica',
     (0, 1)),
    ("clever_004_c1", "Dois subfactos (o facto + o seu conteúdo) -> polar + aberta", None),
    ("clever_008_c3", "Três subfactos (o quê, por quem, quando) -> TRÊS perguntas", (3, 0)),
    ("clever_020_c3", 'Resolução ("desse objetivo" -> erradicar barracas), três ângulos -> '
                        "TRÊS perguntas", None),
    ("clever_157_c1", "Tópico local (Setúbal) x nacional, específico (ecografias) x geral -> "
                        "QUATRO perguntas", None),
]

CABECALHO_EXEMPLOS = """
### EXEMPLOS DE ANOTAÇÃO ###

Cada exemplo corresponde a UM claim span e à(s) pergunta(s) esperada(s). O número de
perguntas varia com o número de subfactos distintos do span (tipicamente 1 a 4).
""".strip()


def _textos(valor):
    valor = valor if isinstance(valor, list) else [valor] if valor else []
    return [_clean(v.get("text") if isinstance(v, dict) else v) for v in valor]


def exemplos_few_shot(caminho=CLEVER_JSON):
    """The few-shot block of the system instruction, built from the six CLEVER claim spans."""
    artigos = ler_json(caminho)
    blocos = [CABECALHO_EXEMPLOS]
    for n, (span_id, comentario, posicoes) in enumerate(DEMONSTRACOES, 1):
        artigo, item, span = span_clever(artigos, span_id)
        claimers = _textos(item.get("claimer"))
        if posicoes:
            claimers = [claimers[i] for i in posicoes]
        perguntas = [q["text"] for q in span["questions"]]
        blocos.append("\n".join([
            f"# EXEMPLO {n} — {comentario}",
            f"CLAIM SPAN: {_clean(span['text'])}",
            "CLAIM OBJECT(S):",
            *(f"- {o}" for o in _textos(item.get("claim_object"))),
            "CLAIMER(S):",
            *(f"- {c}" for c in claimers),
            f"DATA DE PUBLICAÇÃO: {parse_date(artigo['publication_time'])}",
            f"SAÍDA: {json.dumps({'questions': perguntas}, ensure_ascii=False)}",
        ]))
    return "\n\n".join(blocos)


def instrucao_de_sistema(exemplos_few_shot):
    """System instruction: role, criteria, output format and the few-shot demonstrations."""
    return f"""
És um anotador especializado em produzir perguntas para verificação de claims em português europeu.
Recebes UM claim span de cada vez e devolves perguntas que servem para verificar a veracidade desse span.

Elementos disponíveis:
- Claim span: segmento textual exato cuja veracidade tem de ser validada.
- Claim object(s): elemento, entidade, valor ou número focal da alegação dentro do span.
- Claimer(s): quem profere a alegação.
- Time / Publication time: informação temporal usada para anchoring temporal.
- Contexto: artigo usado apenas para desambiguar pronomes, entidades e referências.

Princípio central:
- O objetivo é verificar a veracidade do CLAIM SPAN.
- Todas as perguntas devem incidir diretamente sobre o claim span e o seu conteúdo factual.
- Contexto, data, claimer e claim object são apenas auxiliares para interpretar, desambiguar e situar temporalmente a claim.
- Não gerar perguntas sobre informação periférica do artigo.

{CRITERIOS}

Formato de saída:
Devolve APENAS JSON válido, sem texto adicional, no formato:
{{"questions": ["Pergunta 1?", "Pergunta 2?"]}}

{exemplos_few_shot}
""".strip()


USER_PROMPT_TEMPLATE = """
Tarefa: gerar perguntas google-query-like que verifiquem a veracidade do CLAIM SPAN abaixo, usando o claim object como foco principal e os restantes elementos apenas como apoio para interpretar a alegação.

Não gerar perguntas para informação periférica do contexto. Gerar perguntas apenas para o claim span.

CLAIM SPAN:
{claim_span}

CONTEXTO:
{context}

DATA DE PUBLICAÇÃO:
{publication_time}

TIME ASSOCIADO À CLAIM:
{claim_time}

CLAIMER(S):
{claimers}

CLAIM OBJECT(S):
{claim_objects}


Instruções finais:
- Gera uma pergunta por cada subfacto distinto e verificável do span (tipicamente 1 a 4).
- Se o span tem um só subfacto, gera apenas 1 pergunta. Não gerar paráfrases do mesmo subfacto.
- Aplica anchoring temporal sempre que pertinente, por exemplo "em 2025", "até maio de 2025" ou "em 2015".
- Em tópicos locais, menciona explicitamente a região ou entidade territorial.
- Substitui pronomes pelos nomes próprios das entidades.
- Integra o claimer apenas se a validade do facto depender da autoridade dele.
- Devolve apenas JSON válido, sem comentários nem explicações.
""".strip()


def _bullets(items, empty="Não fornecido."):
    items = [str(x).strip() for x in items if str(x).strip()]
    return "\n".join(f"- {x}" for x in items) if items else f"- {empty}"


def build_user_prompt(claim_span, context, publication_time, claim_time, claimers, claim_objects):
    """`USER_PROMPT_TEMPLATE` filled for one claim span."""
    return USER_PROMPT_TEMPLATE.format(
        claim_span=(claim_span or "").strip() or "Não fornecido.",
        context=(context or "").strip() or "Não fornecido.",
        publication_time=(publication_time or "").strip() or "Não fornecida.",
        claim_time=(claim_time or "").strip() or "Não fornecido.",
        claimers=_bullets(claimers),
        claim_objects=_bullets(claim_objects),
    )


def read_records(path):
    """Dataset as a list of dicts (JSON array or JSONL)."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".jsonl" or text[0] != "[":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def load_context(document, context_dir):
    """Article text, or "" if it does not exist."""
    if not document:
        return ""
    path = context_dir / document
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_client():
    """Gemini client with GEMINI_API_KEY (or GOOGLE_API_KEY) from .env."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(f"GEMINI_API_KEY não encontrada em {REPO_ROOT / '.env'}.")
    return genai.Client(api_key=api_key)


_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={"questions": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING))},
    required=["questions"],
)


def _normalize_question(text):
    text = " ".join(str(text).split()).lstrip("-–•* ").strip(" \"'").rstrip(".;:! ")
    return text + "?" if text and not text.endswith("?") else text


def _parse_questions(raw):
    """Validate the JSON and return clean, de-duplicated questions."""
    parsed = json.loads(raw)  # ValueError if not valid JSON
    if not isinstance(parsed, dict) or not isinstance(parsed.get("questions"), list):
        raise ValueError('JSON sem o campo "questions" (lista).')
    questions, seen = [], set()
    for item in parsed["questions"]:
        if not isinstance(item, str):
            continue
        q = _normalize_question(item)
        if len(q) >= 8 and q.casefold() not in seen:
            seen.add(q.casefold())
            questions.append(q)
    return questions


def generate_questions(client, model, system_instruction, user_prompt, temperature, retries,
                       backoff=2.0, max_backoff=60.0):
    """Questions for one span, with exponential-backoff retries (503, 429, timeouts, bad JSON)."""
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=_SCHEMA,
    )
    last_error = RuntimeError("sem tentativas")
    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(model=model, contents=user_prompt, config=config)
            return _parse_questions(response.text or "")
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(min(backoff * (2 ** (attempt - 1)), max_backoff))
    raise last_error


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, default=CLAIMPT_JSON["train"], help="ClaimPT as a JSON array or JSONL (default: claimpt_train.json).")
    p.add_argument("--output", type=Path, default=SCRIPT_DIR / "outputs/claimpt_train_silver_questions.jsonl", help="Output JSONL (silver dataset).")
    p.add_argument("--failed", type=Path, default=None, help="JSONL of failed spans. Default: next to the output.")
    p.add_argument("--context-dir", type=Path, default=CLAIMPT_ARTIGOS, help="Folder with the articles (context).")
    p.add_argument("--model", default="gemini-3.5-flash", help="Gemini model name.")
    p.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature (0 = deterministic).")
    p.add_argument("--sleep", type=float, default=1.0, help="Seconds to wait between calls.")
    p.add_argument("--retries", type=int, default=5, help="Attempts per span (exponential backoff) before failing.")
    p.add_argument("--max-examples", dest="max_examples", type=int, default=None, help="Limit the number of spans generated (tests).")
    return p.parse_args()


def load_done_ids(output_path):
    """Ids already in the output (resume)."""
    if not output_path.exists():
        return set()
    return {json.loads(line)["id"] for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()}


def append_jsonl(path, record):
    """Append one record and flush."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def main():
    args = parse_args()
    system_instruction = instrucao_de_sistema(exemplos_few_shot())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    failed_path = args.failed or args.output.with_name(args.output.stem + "_failed.jsonl")
    client = load_client()

    units = [u for r in read_records(args.input) for u in iter_span_units(r)]
    done = load_done_ids(args.output)
    pending = [u for u in units if u["id"] not in done]
    log.info("Modelo=%s | spans totais=%d | já feitos=%d | pendentes=%d", args.model, len(units), len(done), len(pending))

    generated = 0
    for unit in pending:
        if args.max_examples is not None and generated >= args.max_examples:
            log.info("Atingido --max-examples=%d. A parar.", args.max_examples)
            break
        try:
            questions = generate_questions(
                client=client,
                model=args.model,
                system_instruction=system_instruction,
                user_prompt=build_user_prompt(
                    claim_span=unit["claim_span"],
                    context=load_context(unit["document"], args.context_dir),
                    publication_time=unit["publication_time"],
                    claim_time=unit["claim_time"],
                    claimers=unit["claimers"],
                    claim_objects=unit["claim_objects"],
                ),
                temperature=args.temperature,
                retries=args.retries,
            )
            append_jsonl(args.output, {**unit, "questions": questions})
            generated += 1
            log.info("[%d/%d] %s -> %d perguntas", generated, len(pending), unit["id"], len(questions))
        except Exception as error:
            log.error("Falha em %s: %s", unit["id"], error)
            append_jsonl(failed_path, {"id": unit["id"], "document": unit["document"],
                                       "claim_span": unit["claim_span"], "error": str(error)})
        if args.sleep > 0:
            time.sleep(args.sleep)

    log.info("Concluído. Gerados %d spans nesta execução. Output: %s", generated, args.output)


if __name__ == "__main__":
    main()
