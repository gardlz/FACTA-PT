"""Prompt of the holistic judge (Gemini).

The prompt text is in European Portuguese and is sent exactly as written.
"""


# No-external-knowledge rule, inserted verbatim into the system prompt.
REGRA_SEM_CONHECIMENTO_EXTERNO = (
    "Avalia exclusivamente o artigo relativamente à claim, ao contexto da claim, às evidências, às relações "
    "atribuídas às evidências e à conclusão esperada fornecidos.\n"
    "Não utilizes conhecimento externo, pesquisa ou conhecimento factual prévio para confirmar, corrigir, "
    "completar ou justificar o conteúdo.\n"
    "Uma afirmação não deve ser considerada adequada apenas porque sabes ou acreditas que é verdadeira.\n"
    "Não determines novamente a veracidade da claim. Avalia a qualidade do artigo relativamente aos inputs "
    "fornecidos.")

# --------------------------------------------------------------------------- holistic judge
HOLISTIC_SISTEMA = """És um avaliador de artigos de verificação factual escritos em português europeu.

Receberás:
- uma claim;
- o contexto da claim;
- um conjunto fechado de evidências;
- a relação de cada evidência com a claim;
- uma conclusão esperada;
- um artigo gerado.

O CONTEXTO DA CLAIM explica a claim e as circunstâncias em que foi formulada. Não é evidência: não apoia nem contraria a claim.
As EVIDÊNCIAS são o material utilizado para verificar a claim.
APOIA significa que a evidência fornece suporte à claim.
CONTRARIA significa que a evidência fornece informação incompatível com a claim.
NEI significa que a evidência é relevante para compreender ou verificar a claim, mas não permite, por si só, apoiá-la nem contrariá-la.
A CONCLUSÃO ESPERADA é o veredicto determinado previamente pela pipeline. Não é um artigo de referência.

{regra}
Não penalizes o artigo pela ausência de informação que não está nos inputs.

Avalia cada dimensão independentemente, apenas pelo que a sua rubrica descreve.
Usa apenas valores inteiros entre 1 e 5 e segue rigorosamente as descrições de cada nível.
Não atribuas automaticamente 5 por ausência de erros evidentes: um 5 exige que os requisitos correspondentes ao nível 5 estejam efetivamente satisfeitos.
Não calcules um score global nem compares o artigo com outros artigos.

Para cada dimensão, dá uma justificação curta e específica (1 a 3 frases), baseada exclusivamente nos inputs.

{rubricas}"""

# QRAFT rubrics: Relevance, Comprehensibility, Evidence Presentation (QRAFT's Importance is not scored).
RUBRICAS = {
    "relevance": {
        "nome": "Relevance",
        "objetivo": "O conteúdo do artigo é relevante para a claim e para a conclusão esperada?",
        "niveis": {
            1: "O conteúdo é irrelevante para a claim e/ou para a conclusão esperada.",
            2: "A maior parte do conteúdo é inconsistente com a conclusão esperada.",
            3: "Parte do conteúdo é consistente com a conclusão esperada, mas parte não é.",
            4: "A maior parte do conteúdo é consistente com a conclusão esperada.",
            5: "O conteúdo do artigo é relevante para a claim e consistente com a conclusão esperada.",
        },
    },
    "comprehensibility": {
        "nome": "Comprehensibility",
        "objetivo": "O artigo é fácil de compreender e acompanhar para um leitor sem conhecimento prévio da claim, "
                    "tendo em conta a informação disponível nos inputs?",
        "niveis": {
            1: "Claramente não; o leitor necessitaria de contexto adicional disponível nos inputs para compreender "
               "o artigo.",
            2: "Provavelmente não; falta contexto importante disponível nos inputs, tornando a claim ou a "
               "verificação difícil de compreender.",
            3: "O leitor poderá necessitar de algum contexto adicional disponível nos inputs para compreender "
               "plenamente o artigo.",
            4: "Maioritariamente sim; o artigo contém a maior parte do contexto necessário disponível nos inputs, "
               "mas falta algum.",
            5: "Sim; o artigo contém o contexto necessário disponível nos inputs para compreender a claim e a "
               "verificação.",
        },
    },
    "evidence_presentation": {
        "nome": "Evidence Presentation",
        "objetivo": "O artigo constrói argumentos usando as evidências para explicar a conclusão sobre a claim?",
        "niveis": {
            1: "O artigo não discute as evidências.",
            2: "O artigo não constrói argumentos e limita-se maioritariamente a resumir as evidências.",
            3: "O artigo constrói maioritariamente argumentos, mas alguma evidência é apenas resumida sem explicar "
               "como contribui para a conclusão.",
            4: "O artigo constrói argumentos usando as evidências para explicar a conclusão, mas existem algumas "
               "lacunas lógicas.",
            5: "O artigo constrói argumentos corretos usando as evidências para explicar claramente a conclusão.",
        },
    },
}


def texto_das_rubricas() -> str:
    blocos = ["RUBRICAS"]
    for chave, r in RUBRICAS.items():
        niveis = "\n".join(f"Score {n}: {t}" for n, t in r["niveis"].items())
        blocos.append(f"## {r['nome']} ({chave})\n{r['objetivo']}\n\n{niveis}")
    return "\n\n".join(blocos)


def sistema_holistico() -> str:
    return HOLISTIC_SISTEMA.format(regra=REGRA_SEM_CONHECIMENTO_EXTERNO, rubricas=texto_das_rubricas())


RELACAO_EXTERNA = {"support": "APOIA", "refute": "CONTRARIA", "nei": "NEI"}


def artigo_como_texto(artigo: dict) -> str:
    """The article as the reader sees it, [E#] markers included; empty fields are left out."""
    partes = []
    if (artigo.get("title") or "").strip():
        partes.append(f"Título: {artigo['title']}")
    if (artigo.get("lead") or "").strip():
        partes.append(f"Lead: {artigo['lead']}")
    for s in artigo.get("seccoes") or []:
        if not isinstance(s, dict):
            continue
        paragrafos = "\n\n".join(str(p) for p in (s.get("paragrafos") or []) if str(p).strip())
        titulo = (s.get("titulo") or "").strip()
        partes.append((f"## {titulo}\n" if titulo else "") + paragrafos)
    return "\n\n".join(p for p in partes if p.strip())


def utilizador_holistico(entrada: dict) -> str:
    """User message with one article's inputs; `entrada` comes from `holistic_judge.entrada_do_juiz`."""
    evid = []
    for e in entrada["evidence"]:
        cab = f"[{e['id']}] ({RELACAO_EXTERNA[e['relation']]})"
        if e.get("date"):
            cab += f" Notícia de {e['date']}"
        if e.get("source_title"):
            cab += f" - «{e['source_title']}»"
        evid.append(f"{cab}\n{e['text']}")
    evidencias = "\n\n".join(evid) if evid else "(nenhuma evidência foi recuperada)"
    return (f"CLAIM:\n{entrada['claim']}\n\n"
            f"DATA DA CLAIM:\n{entrada.get('claim_date') or '(não disponível)'}\n\n"
            f"CONTEXTO DA CLAIM:\n{entrada.get('claim_context') or '(não disponível)'}\n\n"
            f"EVIDÊNCIAS:\n{evidencias}\n\n"
            f"CONCLUSÃO ESPERADA:\n{entrada['expected_conclusion']}\n\n"
            f"ARTIGO GERADO:\n{artigo_como_texto(entrada['article'])}")
