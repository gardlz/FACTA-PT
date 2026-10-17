"""Reading the model's answer, and when to retry (`Article Generation/geracao/gerar_artigos.py`).

The parse invents nothing: it strips code fences, takes the first complete JSON object and, when
that fails, closes it at its last complete value. A mended article is `reparado`, and is retried.
"""

from __future__ import annotations

import json
import re

_CERCA = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Cycle detector: an article loops when one word 8-gram occurs LIMIAR_CICLO times or more.
LIMIAR_CICLO = 6


def primeiro_json(texto: str) -> str | None:
    """The first complete JSON object of the text, by counting braces outside strings."""
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


def reparar_json(texto: str) -> dict | None:
    """Closes a truncated JSON at its last complete value; None when nothing can be saved. It
    invents no text: it only cuts and closes what was already written."""
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
    # From the latest cut to the earliest: the later, the more of the article is kept.
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
    """How many times the most repeated word 8-gram occurs: an article in a cycle says the same
    thing many times, which its length alone does not show."""
    palavras = texto.split()
    if len(palavras) < 8:
        return 0
    vistos, maior = {}, 0
    for i in range(len(palavras) - 7):
        grama = " ".join(palavras[i:i + 8])
        vistos[grama] = vistos.get(grama, 0) + 1
        maior = max(maior, vistos[grama])
    return maior


def para_blocos(dados: dict) -> list[dict]:
    """The answer's sections -> the heading/paragraph blocks the website reads."""
    blocos = []
    for seccao in dados.get("seccoes") or []:
        if not isinstance(seccao, dict):
            texto = str(seccao).strip()
            if texto:
                blocos.append({"type": "paragraph", "text": texto})
            continue
        titulo = (seccao.get("titulo") or "").strip()
        if titulo:
            blocos.append({"type": "heading", "text": titulo})
        for paragrafo in seccao.get("paragrafos") or []:
            texto = (paragrafo or "").strip() if isinstance(paragrafo, str) else ""
            if texto:
                blocos.append({"type": "paragraph", "text": texto})
    return blocos


def interpretar(bruto: str) -> dict:
    """Model text -> answer: `estado` is ok, reparado, sem_seccoes or sem_json."""
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
        return {"estado": falha or "sem_json",
                "artigo": {"title": None, "lead": None, "blocks": []}, "repeticao_max": 0}

    blocos = para_blocos(dados) if isinstance(dados.get("seccoes"), list) else []
    lead = dados.get("lead") if isinstance(dados.get("lead"), str) else ""
    texto_todo = " ".join([lead] + [b["text"] for b in blocos])
    estado = "sem_seccoes" if not blocos else ("reparado" if reparado else "ok")
    return {
        "estado": estado,
        "artigo": {"title": dados.get("title"), "lead": lead, "blocks": blocos},
        "repeticao_max": repeticao(texto_todo),
    }


def pontos(registo: dict) -> tuple:
    """Preference between two attempts at the same claim; larger is better."""
    limpo = registo["estado"] == "ok" and registo["repeticao_max"] < LIMIAR_CICLO
    posicao = {"ok": 2, "reparado": 1}.get(registo["estado"], 0)
    return (1 if limpo else 0, posicao, -registo["repeticao_max"])


def precisa_retentar(registo: dict) -> bool:
    """An article that did not come out, came out mended, or came out in a cycle."""
    return registo["estado"] != "ok" or registo["repeticao_max"] >= LIMIAR_CICLO
