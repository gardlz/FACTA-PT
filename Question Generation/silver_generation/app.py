"""Streamlit interface for the manual evaluation of the silver questions: the fixed
sample of claim spans with article and questions, rated on general question quality
(ratings.json) and on adherence to the CLEVER guidelines (ratings_clever.json), both in
silver_generation/avaliacao/, each answer saved when given. The interface text is in Portuguese,
as it is the evaluation instrument.

    streamlit run silver_generation/app.py
"""

import html
import json
import os
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from amostra import (CASOS_ESPECIAIS, CONTEXT_DIR, FICHEIROS_SILVER,  # noqa: E402
                     METRICAS, METRICAS_CLEVER, METRICAS_CLEVER_POR_PERGUNTA, NOMES,
                     NOMES_CLEVER, N_SAMPLE, RATINGS_CLEVER_FILE,
                     RATINGS_FILE, SEED, carregar_amostra,
                     chave_pergunta,
                     criterios, criterios_clever, normalizar_clever, perguntas_avaliadas,
                     respostas_qualidade, span_avaliado, taxas_clever, taxas_qualidade)

CLEVER_FILE = RATINGS_CLEVER_FILE

PER_PAGE = 5
TOP_ANCHOR = "topo-da-pagina"

# One-line help per criterion; the full criteria are in the tabs at the top.
AJUDA = {
    "relevancia": "A pergunta verifica o claim span — e não informação periférica do artigo.",
    "fidelidade": "A pergunta mantém-se fiel ao contexto, sem inventar factos, nomes ou números.",
    "clareza": "A pergunta é autocontida: os pronomes estão resolvidos pelos nomes próprios.",
    "ancora": "A pergunta inclui a data e a região quando são relevantes para a verificação.",
}
AJUDA_CLEVER = {
    "estrutura": "O conjunto tem pelo menos uma pergunta geral sobre o facto central e uma "
                 "mais específica, que pede dado factual adicional.",
    "objeto": "A pergunta gira em torno do claim object anotado — o termo mais específico do "
              "span —, e não de outro elemento da claim.",
    "neutralidade": "A pergunta procura o facto sem pressupor o veredito e sem perguntar pela "
                    "opinião, intenção ou credibilidade do claimer.",
    "casos_especiais": "As regras condicionais das guidelines: claimer necessário, comparação "
                       "a desdobrar, estudo a localizar. Responde-se às três condições; se "
                       "nenhuma se verificar, o critério não se aplica a este span.",
}

BINARIO = [0, 1]
ROTULO = {0: "✗  Não cumpre", 1: "✓  Cumpre"}
ROTULO_SN = {0: "Não", 1: "Sim"}


# --- Data ------------------------------------------------------------------ #
def assinatura():
    """Changes when the silver files change (invalidates the cache)."""
    return tuple((f.stat().st_mtime if f.exists() else 0) for f in FICHEIROS_SILVER)


@st.cache_data
def carregar(assinatura_dos_ficheiros):
    """The fixed sample and the dataset size (the argument is part of the cache key)."""
    return carregar_amostra(), len(carregar_amostra(todos=True))


@st.cache_data
def carregar_artigo(documento):
    caminho = CONTEXT_DIR / documento
    return caminho.read_text(encoding="utf-8") if caminho.exists() else ""


@st.cache_data
def carregar_criterios(qual, mtime):
    """The criteria as written in their `.md` (mtime in the cache key)."""
    return criterios() if qual == "qualidade" else criterios_clever()


def mtime_criterios(qual):
    caminho = SCRIPT_DIR / ("CRITERIOS.md" if qual == "qualidade" else "CRITERIOS_CLEVER.md")
    return caminho.stat().st_mtime if caminho.exists() else 0


def localizar_span(texto, span, begin):
    """Position of the claim span in the article, found by text search.

    ClaimPT offsets are shifted with respect to the article files; the annotated offset only
    breaks ties between several occurrences.
    """
    posicoes, inicio = [], texto.find(span)
    while inicio != -1:
        posicoes.append(inicio)
        inicio = texto.find(span, inicio + 1)
    if not posicoes:
        return None
    return posicoes[0] if begin is None else min(posicoes, key=lambda p: abs(p - begin))


def contexto_html(documento, claim_span, begin):
    """Article with the claim span highlighted."""
    texto = carregar_artigo(documento)
    if not texto:
        return "<em>(sem artigo de contexto)</em>"
    pos = localizar_span(texto, claim_span, begin)
    if pos is None:
        return html.escape(texto)
    fim = pos + len(claim_span)
    return (html.escape(texto[:pos]) + "<mark>" + html.escape(texto[pos:fim]) + "</mark>"
            + html.escape(texto[fim:]))


def span_html(claim_span, claim_objects):
    """The claim span with its claim object(s) underlined."""
    marcas = []
    for objeto in claim_objects:
        i = claim_span.find(objeto)
        if i != -1 and objeto.strip():
            marcas.append((i, i + len(objeto)))
    marcas.sort()
    saida, cursor = [], 0
    for inicio, fim in marcas:
        if inicio < cursor:
            continue
        saida.append(html.escape(claim_span[cursor:inicio]))
        saida.append(f"<u class='obj'>{html.escape(claim_span[inicio:fim])}</u>")
        cursor = fim
    saida.append(html.escape(claim_span[cursor:]))
    return "".join(saida)


# --- Answers --------------------------------------------------------------- #
def ler_ficheiro(caminho):
    """Saved answers; an unreadable file is kept aside as `.corrompido` and the app starts empty."""
    if not caminho.exists() or not caminho.stat().st_size:
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as erro:
        salvado = caminho.with_suffix(caminho.suffix + ".corrompido")
        salvado.write_bytes(caminho.read_bytes())
        st.warning(f"`{caminho.name}` estava ilegível ({erro}). Foi guardado em "
                   f"`{salvado.name}` e a avaliação recomeça vazia neste ficheiro.")
        return {}
    return dados if isinstance(dados, dict) else {}


def gravar(caminho, dados):
    """Atomic write (temporary file + replace); called on every answer."""
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    os.replace(temporario, caminho)


def chaves_do_span(registo):
    return [chave_pergunta(registo["id"], n) for n in range(1, len(registo["questions"]) + 1)]


def respostas_clever(clever, span_id):
    """{'estrutura': 0/1/None, 'casos': {...}, 'perguntas': {'1': {...}}}."""
    guardadas = clever.get(span_id) or {}
    return {
        "estrutura": guardadas["estrutura"] if guardadas.get("estrutura") in (0, 1) else None,
        "casos": dict(guardadas.get("casos") or {}),
        "perguntas": {str(k): dict(v) for k, v in (guardadas.get("perguntas") or {}).items()},
    }


def clever_por_pergunta(dados, n):
    da_pergunta = dados["perguntas"].get(str(n), {})
    return {m: (da_pergunta[m] if da_pergunta.get(m) in (0, 1) else None)
            for m in METRICAS_CLEVER_POR_PERGUNTA}


def pergunta_completa(respostas):
    return all(v is not None for v in respostas.values())


# Completeness and aggregation are defined once, in amostra.py.
clever_completo = span_avaliado


def focar(span_id):
    """Remember the card that was touched, so the view returns to it after the rerun."""
    st.session_state.foco = span_id
    st.session_state.foco_n = st.session_state.get("foco_n", 0) + 1


def guardar_qualidade(chave, metrica):
    valor = st.session_state[f"q:{chave}:{metrica}"]
    ratings = st.session_state.ratings
    entrada = ratings.setdefault(chave, {})
    if valor is None:
        entrada.pop(metrica, None)
        if not entrada:
            ratings.pop(chave, None)
    else:
        entrada[metrica] = valor
    gravar(RATINGS_FILE, ratings)
    focar(chave.split("::")[0])


def _entrada_clever(span_id):
    return st.session_state.clever.setdefault(
        span_id, {"estrutura": None, "casos": {}, "perguntas": {}})


def _limpar_clever(span_id):
    entrada = st.session_state.clever.get(span_id) or {}
    vazio = (entrada.get("estrutura") is None and not entrada.get("casos")
             and not any(entrada.get("perguntas", {}).values()))
    if vazio:
        st.session_state.clever.pop(span_id, None)


def guardar_estrutura(span_id):
    valor = st.session_state[f"c:{span_id}:estrutura"]
    entrada = _entrada_clever(span_id)
    entrada["estrutura"] = valor
    if valor is None:
        entrada.pop("estrutura", None)
    _limpar_clever(span_id)
    gravar(CLEVER_FILE, st.session_state.clever)
    focar(span_id)


def guardar_caso(span_id, campo):
    valor = st.session_state[f"c:{span_id}:{campo}"]
    entrada = _entrada_clever(span_id)
    casos = entrada.setdefault("casos", {})
    if valor is None:
        casos.pop(campo, None)
    else:
        casos[campo] = valor
    # Unsetting a condition also removes its answer.
    for condicao, resposta, _, _ in CASOS_ESPECIAIS:
        if campo == condicao and valor != 1:
            casos.pop(resposta, None)
    _limpar_clever(span_id)
    gravar(CLEVER_FILE, st.session_state.clever)
    focar(span_id)


def guardar_clever_pergunta(span_id, n, metrica):
    valor = st.session_state[f"c:{span_id}:{n}:{metrica}"]
    entrada = _entrada_clever(span_id)
    perguntas = entrada.setdefault("perguntas", {})
    da_pergunta = perguntas.setdefault(str(n), {})
    if valor is None:
        da_pergunta.pop(metrica, None)
        if not da_pergunta:
            perguntas.pop(str(n), None)
    else:
        da_pergunta[metrica] = valor
    _limpar_clever(span_id)
    gravar(CLEVER_FILE, st.session_state.clever)
    focar(span_id)


# --- Appearance ------------------------------------------------------------ #
st.set_page_config(page_title="Perguntas silver · ClaimPT", page_icon="🔎", layout="wide")

st.markdown("""
<style>
  :root {
    --acento: 70,130,255;      /* questions          */
    --span: 240,165,0;         /* claim span         */
    --objeto: 0,170,140;       /* claim object       */
    --claimer: 150,110,240;    /* claimer            */
    --ok: 34,160,100;
    --neutro: 128,128,128;
  }
  .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1180px; }
  h1, h2, h3 { letter-spacing: -0.02em; }

  /* Header ----------------------------------------------------------------- */
  .hero { border-radius: 14px; padding: 1.4rem 1.6rem 1.2rem 1.6rem; margin-bottom: 1.1rem;
          border: 1px solid rgba(var(--neutro),0.22);
          background: linear-gradient(120deg, rgba(var(--acento),0.10), rgba(var(--span),0.07)); }
  .hero h1 { margin: 0 0 0.25rem 0; font-size: 1.65rem; }
  .hero p  { margin: 0; opacity: 0.78; line-height: 1.55; font-size: 0.94rem; max-width: 74ch; }
  .hero .tag { display: inline-block; margin-bottom: 0.55rem; padding: 0.18rem 0.6rem;
               border-radius: 999px; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.09em;
               text-transform: uppercase; background: rgba(var(--span),0.18);
               border: 1px solid rgba(var(--span),0.45); }

  .label { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase;
           opacity: 0.5; margin: 0 0 0.4rem 0; }

  .card-head { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
               margin-bottom: 0.7rem; }
  .idx { font-variant-numeric: tabular-nums; font-weight: 800; font-size: 0.95rem; opacity: 0.35; }
  .chip { display: inline-flex; align-items: center; gap: 0.32rem; padding: 0.16rem 0.6rem;
          border-radius: 999px; font-size: 0.76rem; font-weight: 600; line-height: 1.5;
          border: 1px solid rgba(var(--neutro),0.32); background: rgba(var(--neutro),0.09); }
  .chip-doc { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.72rem; }
  .chip-data { background: rgba(225,85,120,0.13); border-color: rgba(225,85,120,0.42); }
  .chip-ok { background: rgba(var(--ok),0.13); border-color: rgba(var(--ok),0.45); }
  .chip-falta { background: rgba(var(--neutro),0.10); }

  /* Claim span and metadata ------------------------------------------------- */
  .span-box { background: linear-gradient(90deg, rgba(var(--span),0.15), rgba(var(--span),0.03));
              border-left: 3px solid rgb(var(--span)); padding: 0.9rem 1.05rem;
              border-radius: 8px; font-size: 1.04rem; line-height: 1.6; font-weight: 500; }
  .span-box u.obj { text-decoration: none; background: rgba(var(--objeto),0.20);
                    border-bottom: 2px solid rgba(var(--objeto),0.75); border-radius: 3px;
                    padding: 0.05em 2px; font-weight: 600; }
  .pill { display: inline-block; padding: 0.2rem 0.65rem; margin: 0 0.35rem 0.35rem 0;
          border-radius: 999px; font-size: 0.8rem; line-height: 1.5; font-weight: 500;
          border: 1px solid transparent; }
  .pill-object { background: rgba(var(--objeto),0.14); border-color: rgba(var(--objeto),0.45); }
  .pill-claimer { background: rgba(var(--claimer),0.14); border-color: rgba(var(--claimer),0.45); }
  .pill-none { opacity: 0.45; font-size: 0.85rem; }

  /* Questions (expander) ---------------------------------------------------- */
  div[data-testid="stExpander"] details { border: 1px solid rgba(var(--acento),0.22);
      border-left: 3px solid rgba(var(--acento),0.6); border-radius: 8px;
      background: rgba(var(--acento),0.055); margin-bottom: 0.45rem; }
  div[data-testid="stExpander"] details[open] { background: rgba(var(--acento),0.035); }
  div[data-testid="stExpander"] summary { padding: 0.6rem 0.9rem; line-height: 1.5; }
  div[data-testid="stExpander"] summary p { font-size: 0.98rem; font-weight: 500; }

  /* Rating blocks ----------------------------------------------------------- */
  .bloco { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
           padding: 0.2rem 0.55rem; border-radius: 5px; display: inline-block; }
  .bloco-q { background: rgba(var(--acento),0.16); border: 1px solid rgba(var(--acento),0.42); }
  .bloco-c { background: rgba(var(--objeto),0.16); border: 1px solid rgba(var(--objeto),0.42); }

  .metric-name { font-size: 0.9rem; padding-top: 0.4rem; line-height: 1.35;
                 display: flex; align-items: center; gap: 0.4rem; }
  .sub { font-size: 0.86rem; opacity: 0.75; padding-top: 0.4rem; padding-left: 1.5rem;
         border-left: 2px solid rgba(var(--neutro),0.3); margin-left: 0.35rem; }

  /* Set-level criteria: a Streamlit container, selected by its key. */
  [class*="st-key-conjunto-"] {
      border: 1px dashed rgba(var(--objeto),0.5) !important; border-radius: 10px;
      background: rgba(var(--objeto),0.045); box-shadow: none; }


  /* Criterion names carry their help in the HTML title attribute (badge()). */
  span[title] { cursor: help; border-bottom: 1px dotted rgba(var(--neutro),0.4); }

  /* Article ----------------------------------------------------------------- */
  .ctx-box { white-space: pre-wrap; max-height: 300px; overflow-y: auto; font-size: 0.86rem;
             line-height: 1.7; padding: 0.95rem 1.1rem; border-radius: 9px;
             border: 1px solid rgba(var(--neutro),0.22); background: rgba(var(--neutro),0.055);
             box-shadow: inset 0 2px 8px rgba(0,0,0,0.09); }
  .ctx-box::-webkit-scrollbar { width: 9px; }
  .ctx-box::-webkit-scrollbar-track { background: transparent; }
  .ctx-box::-webkit-scrollbar-thumb { background: rgba(var(--neutro),0.35); border-radius: 5px; }
  .ctx-box mark { background: rgba(var(--span),0.45); padding: 0.1em 3px; border-radius: 3px;
                  font-weight: 600; }

  .progresso-nome { font-size: 0.8rem; opacity: 0.7; }
</style>
""", unsafe_allow_html=True)


def badge(texto, ajuda):
    """Criterion name with its explanation in the HTML `title` (browser tooltip)."""
    return f"<span title='{html.escape(ajuda, quote=True)}'>{texto}</span>"


# --- State ----------------------------------------------------------------- #
# amostra.py reports missing files with SystemExit, which Streamlit does not catch.
try:
    amostra, total_spans = carregar(assinatura())
except SystemExit as erro:
    st.error(str(erro))
    st.stop()

if "ratings" not in st.session_state:
    st.session_state.ratings = ler_ficheiro(RATINGS_FILE)
if "clever" not in st.session_state:
    st.session_state.clever = ler_ficheiro(CLEVER_FILE)
if "pagina" not in st.session_state:
    st.session_state.pagina = 0
ratings, clever = st.session_state.ratings, st.session_state.clever

todas_chaves = [c for registo in amostra for c in chaves_do_span(registo)]
feitas_q = [c for c in todas_chaves if pergunta_completa(respostas_qualidade(ratings, c))]
feitos_c = [r["id"] for r in amostra
            if clever_completo(respostas_clever(clever, r["id"]), len(r["questions"]))]

# The CLEVER criteria have two units, hence two progress counts (questions and spans).
avaliacoes_c = [normalizar_clever(clever.get(r["id"]) or {}, len(r["questions"]))
                for r in amostra]
feitas_cq = sum(perguntas_avaliadas(a, a["n_perguntas"])[0] for a in avaliacoes_c)


def estado_do_span(registo):
    """(quality complete?, CLEVER criteria complete?) for the chips and the filter."""
    q = all(pergunta_completa(respostas_qualidade(ratings, c)) for c in chaves_do_span(registo))
    c = registo["id"] in feitos_c
    return q, c


# --- Header ---------------------------------------------------------------- #
st.markdown(f"""
<div class='hero'>
  <span class='tag'>anotação silver · não é gold</span>
  <h1>🔎 Perguntas silver · ClaimPT</h1>
  <p>As perguntas foram geradas pelo Gemini a partir de cada <b>claim span</b> do ClaimPT, sem
  anotação humana. Aqui avalia-se uma amostra fixa de {len(amostra)} claim spans em duas dimensões
  complementares: a <b>qualidade</b> de cada pergunta e a <b>conformidade com o protocolo de
  anotação</b> que produziu as perguntas gold do CLEVER. A amostra é reprodutível (seed {SEED})
  e junta treino e teste.</p>
</div>
""", unsafe_allow_html=True)

aba_q, aba_c, aba_como = st.tabs(["📏  Critérios de qualidade", "📐  Critérios de anotação (CLEVER)",
                                  "❓  Como avaliar"])
with aba_q:
    st.caption("Unidade: a **pergunta**. Guardada em `ratings.json`.")
    st.markdown(carregar_criterios("qualidade", mtime_criterios("qualidade")))
with aba_c:
    st.caption("Duas unidades: **estrutura** e **casos especiais** são do *conjunto* (uma "
               "resposta por span); **concordância com o claim object** e **neutralidade** são "
               "de *cada pergunta*. Guardada em `ratings_clever.json`.")
    st.markdown(carregar_criterios("clever", mtime_criterios("clever")))
with aba_como:
    st.markdown("""
**Uma pergunta de cada vez, um span de cada vez.** Cada pergunta abre-se com um clique: lá dentro
estão seis respostas — as quatro métricas de qualidade (relevância, fidelidade, clareza, âncora)
e os dois critérios do CLEVER que se julgam **pergunta a pergunta** (concordância com o claim
object, neutralidade). Por baixo das perguntas, no bloco tracejado, estão os dois critérios que só
existem para o **conjunto**: a estrutura geral→específica e os casos especiais.

**Os dois critérios de pergunta respondem-se em cada pergunta, mesmo quando a resposta é a
mesma:** numa claim com duas perguntas, uma pode estar centrada no claim object e a outra
desviar-se para um adjunto.

**O mesmo requisito não se avalia duas vezes.** Falta de data ou de região é *Âncora*; um pronome
por resolver é *Clareza*. Nenhum dos dois se penaliza outra vez nos critérios do CLEVER.

**Os casos especiais são condições, não uma nota.** Marca-se se a condição se verifica *no claim
span*; só quando se verifica é que se pergunta se as perguntas lhe respondem. Se as três forem
respondidas «Não», o critério **não se aplica** e o span fica fora dessa taxa.

**Cada resposta é gravada no momento em que é dada.** A aplicação pode ser fechada a meio da
avaliação e retomada mais tarde no ponto em que ficou.
""")

# --- Sidebar --------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### Progresso")
    st.markdown("<div class='progresso-nome'>Qualidade · por pergunta</div>", unsafe_allow_html=True)
    st.progress(len(feitas_q) / max(len(todas_chaves), 1),
                text=f"{len(feitas_q)}/{len(todas_chaves)} perguntas")
    st.markdown("<div class='progresso-nome'>Anotação CLEVER · por pergunta</div>",
                unsafe_allow_html=True)
    st.progress(feitas_cq / max(len(todas_chaves), 1),
                text=f"{feitas_cq}/{len(todas_chaves)} perguntas")
    st.markdown("<div class='progresso-nome'>Anotação CLEVER · conjunto, por span</div>",
                unsafe_allow_html=True)
    st.progress(len(feitos_c) / max(len(amostra), 1), text=f"{len(feitos_c)}/{len(amostra)} spans")

    st.divider()
    st.markdown("### Taxa de cumprimento")
    if feitas_q:
        st.caption(f"Qualidade · {len(feitas_q)} pergunta(s)")
        for m, (ok, n) in taxas_qualidade(ratings, todas_chaves).items():
            st.metric(NOMES[m], f"{100 * ok / n:.0f}%")
    else:
        st.caption("Qualidade: ainda sem respostas.")

    # Each criterion in its own unit, with the denominator shown.
    taxas = taxas_clever(avaliacoes_c)
    if any(n for _, n, _ in taxas.values()):
        st.caption("Anotação CLEVER · cada critério na sua unidade")
        for m in METRICAS_CLEVER:
            ok, n, unidade = taxas[m]
            if n:
                st.metric(NOMES_CLEVER[m], f"{100 * ok / n:.0f}%",
                          f"{ok}/{n} {unidade}s", delta_color="off")
            else:
                st.metric(NOMES_CLEVER[m], "—",
                          "não se aplica a nenhum" if m == "casos_especiais" else "sem respostas",
                          delta_color="off")
    else:
        st.caption("Anotação CLEVER: ainda sem respostas.")

    st.divider()
    filtro = st.radio("Mostrar", ["Todos os spans", "Só os que faltam avaliar",
                                  "Só os já avaliados"], key="filtro")
    st.divider()
    c1, c2 = st.columns(2)
    c1.download_button("⬇ Qualidade", json.dumps(ratings, ensure_ascii=False, indent=2),
                       file_name="ratings.json", mime="application/json",
                       use_container_width=True)
    c2.download_button("⬇ CLEVER", json.dumps(clever, ensure_ascii=False, indent=2),
                       file_name="ratings_clever.json", mime="application/json",
                       use_container_width=True)
    st.caption(f"{total_spans} spans no dataset · amostra de {N_SAMPLE} pela seed {SEED}")


# --- Selection and paging -------------------------------------------------- #
def visivel(registo):
    q, c = estado_do_span(registo)
    if filtro == "Só os que faltam avaliar":
        return not (q and c)
    if filtro == "Só os já avaliados":
        return q and c
    return True


visiveis = [r for r in amostra if visivel(r)]
if not visiveis:
    st.info("Nada a mostrar com este filtro.")
    st.stop()

paginas = (len(visiveis) + PER_PAGE - 1) // PER_PAGE
st.session_state.pagina = min(st.session_state.pagina, paginas - 1)
inicio = st.session_state.pagina * PER_PAGE
pagina = visiveis[inicio:inicio + PER_PAGE]

st.html(f"<div id='{TOP_ANCHOR}' style='scroll-margin-top: 4.5rem'></div>")
st.caption(f"Página {st.session_state.pagina + 1} de {paginas} · a mostrar "
           f"{inicio + 1}–{min(inicio + PER_PAGE, len(visiveis))} de {len(visiveis)} claim spans")


# --- Cards ----------------------------------------------------------------- #
def controlo(coluna, rotulos, chave, valor, on_change, args, ajuda=None):
    return coluna.segmented_control(chave, BINARIO, default=valor,
                                    format_func=lambda v: rotulos[v], key=chave,
                                    on_change=on_change, args=args,
                                    label_visibility="collapsed", help=ajuda)


for registo in pagina:
    span_id = registo["id"]
    idx = amostra.index(registo) + 1
    chaves = chaves_do_span(registo)
    dados_c = respostas_clever(clever, span_id)
    feito_q, feito_c = estado_do_span(registo)
    n_perguntas = len(registo["questions"])

    with st.container(border=True):
        st.html(f"<div id='claim-{idx}' style='scroll-margin-top: 4rem'></div>")
        st.markdown(
            f"<div class='card-head'>"
            f"<span class='idx'>#{idx:02d}</span>"
            f"<span class='chip chip-doc'>{html.escape(registo['document'])}</span>"
            f"<span class='chip chip-data'>📅 {html.escape(registo.get('publication_time') or '—')}</span>"
            + (f"<span class='chip'>⏱ {html.escape(registo['claim_time'])}</span>"
               if registo.get("claim_time") else "")
            + f"<span class='chip {'chip-ok' if feito_q else 'chip-falta'}'>"
              f"{'✓' if feito_q else '◻'} qualidade</span>"
              f"<span class='chip {'chip-ok' if feito_c else 'chip-falta'}'>"
              f"{'✓' if feito_c else '◻'} anotação</span>"
            "</div>", unsafe_allow_html=True)

        st.markdown("<div class='label'>Claim span · <span style='opacity:0.8'>a verde e "
                    "sublinhado, o claim object</span></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='span-box'>{span_html(registo['claim_span'], registo['claim_objects'])}</div>",
                    unsafe_allow_html=True)

        meta_e, meta_d = st.columns(2)
        for coluna, titulo, valores, estilo in [
            (meta_e, "Claim object(s)", registo["claim_objects"], "pill-object"),
            (meta_d, "Claimer(s)", registo["claimers"], "pill-claimer"),
        ]:
            pilulas = "".join(f"<span class='pill {estilo}'>{html.escape(v)}</span>"
                              for v in valores)
            coluna.markdown(f"<div class='label'>{titulo}</div>"
                            + (pilulas or "<span class='pill-none'>—</span>"),
                            unsafe_allow_html=True)

        st.markdown("")
        feitas_qualidade = sum(1 for c in chaves
                               if pergunta_completa(respostas_qualidade(ratings, c)))
        feitas_clever = perguntas_avaliadas(dados_c, n_perguntas)[0]
        st.markdown(f"<div class='label'>Perguntas geradas ({n_perguntas}) · "
                    f"{feitas_qualidade}/{n_perguntas} com a qualidade avaliada · "
                    f"{feitas_clever}/{n_perguntas} com os dois critérios do CLEVER</div>",
                    unsafe_allow_html=True)

        for n, pergunta in enumerate(registo["questions"], start=1):
            chave = chave_pergunta(span_id, n)
            resp_q = respostas_qualidade(ratings, chave)
            resp_c = clever_por_pergunta(dados_c, n)
            marca = "✅" if pergunta_completa(resp_q) and pergunta_completa(resp_c) else "◻️"
            with st.expander(f"{marca}  {n}.  {pergunta}"):
                cabeca_e, cabeca_d = st.columns([3, 1])
                cabeca_e.markdown("<span class='bloco bloco-q'>Qualidade da pergunta</span>",
                                  unsafe_allow_html=True)
                cabeca_d.markdown(
                    f"<div style='text-align:right;font-size:0.8rem;opacity:0.6;padding-top:0.2rem'>"
                    f"{sum(1 for v in resp_q.values() if v == 1)}/{len(METRICAS)} cumpridos</div>",
                    unsafe_allow_html=True)
                for m in METRICAS:
                    nome_col, escala_col = st.columns([2, 3], vertical_alignment="center")
                    nome_col.markdown(f"<div class='metric-name'>{badge(NOMES[m], AJUDA[m])}</div>",
                                      unsafe_allow_html=True)
                    controlo(escala_col, ROTULO, f"q:{chave}:{m}", resp_q[m],
                             guardar_qualidade, (chave, m), AJUDA[m])

                st.markdown("")
                st.markdown("<span class='bloco bloco-c'>Protocolo de anotação · esta pergunta</span>",
                            unsafe_allow_html=True)
                for m in METRICAS_CLEVER_POR_PERGUNTA:
                    nome_col, escala_col = st.columns([2, 3], vertical_alignment="center")
                    nome_col.markdown(
                        f"<div class='metric-name'>{badge(NOMES_CLEVER[m], AJUDA_CLEVER[m])}</div>",
                        unsafe_allow_html=True)
                    controlo(escala_col, ROTULO, f"c:{span_id}:{n}:{m}", resp_c[m],
                             guardar_clever_pergunta, (span_id, n, m), AJUDA_CLEVER[m])

        # --- Set-level criteria (claim span) ----------------------------------- #
        st.markdown("")
        conjunto = st.container(border=True, key=f"conjunto-{span_id}")
        conjunto.markdown("<span class='bloco bloco-c'>Protocolo de anotação · o conjunto das "
                          f"{n_perguntas} perguntas</span>", unsafe_allow_html=True)

        nome_col, escala_col = conjunto.columns([2, 3], vertical_alignment="center")
        nome_col.markdown(
            f"<div class='metric-name'>{badge(NOMES_CLEVER['estrutura'], AJUDA_CLEVER['estrutura'])}</div>",
            unsafe_allow_html=True)
        controlo(escala_col, ROTULO, f"c:{span_id}:estrutura", dados_c["estrutura"],
                 guardar_estrutura, (span_id,), AJUDA_CLEVER["estrutura"])

        conjunto.markdown("")
        # The special-case verdict is derived (amostra.veredito_casos) and not shown here.
        conjunto.markdown(
            f"<div class='label'>"
            f"{badge(NOMES_CLEVER['casos_especiais'], AJUDA_CLEVER['casos_especiais'])}</div>",
            unsafe_allow_html=True)
        for condicao, resposta, pergunta_condicao, pergunta_resposta in CASOS_ESPECIAIS:
            nome_col, escala_col = conjunto.columns([2, 3], vertical_alignment="center")
            nome_col.markdown(f"<div class='metric-name'>{html.escape(pergunta_condicao)}</div>",
                              unsafe_allow_html=True)
            valor = dados_c["casos"].get(condicao)
            controlo(escala_col, ROTULO_SN, f"c:{span_id}:{condicao}",
                     valor if valor in (0, 1) else None, guardar_caso, (span_id, condicao),
                     "Verifica-se no CLAIM SPAN, não nas perguntas. Se as três condições "
                     "forem respondidas «Não», o critério não se aplica a este span.")
            if dados_c["casos"].get(condicao) == 1:
                sub_col, sub_escala = conjunto.columns([2, 3], vertical_alignment="center")
                sub_col.markdown(f"<div class='sub'>↳ {html.escape(pergunta_resposta)}</div>",
                                 unsafe_allow_html=True)
                sub_valor = dados_c["casos"].get(resposta)
                controlo(sub_escala, ROTULO_SN, f"c:{span_id}:{resposta}",
                         sub_valor if sub_valor in (0, 1) else None, guardar_caso,
                         (span_id, resposta),
                         "Esta resposta é sobre as PERGUNTAS: respondem à condição "
                         "assinalada acima?")
        conjunto.caption(
            "Marca-se se cada condição se verifica **no claim span**; só quando se verifica é "
            "que se pergunta se as perguntas lhe respondem. Se as três forem respondidas "
            "«Não», o critério não se aplica a este span.")

        st.markdown("")
        st.markdown("<div class='label'>Artigo de contexto</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='ctx-box'>{contexto_html(registo['document'], registo['claim_span'], registo.get('span_begin'))}</div>",
                    unsafe_allow_html=True)


# --- Paging ---------------------------------------------------------------- #
def navegar(delta):
    nova = max(0, min(paginas - 1, st.session_state.pagina + delta))
    if nova != st.session_state.pagina:
        st.session_state.pagina = nova
        st.session_state.scroll = True


st.divider()
esq, meio, dir_ = st.columns([1, 2, 1], vertical_alignment="center")
esq.button("← Anterior", use_container_width=True, disabled=st.session_state.pagina == 0,
           on_click=navegar, args=(-1,))
dir_.button("Seguinte →", use_container_width=True,
            disabled=st.session_state.pagina >= paginas - 1, on_click=navegar, args=(1,))
meio.markdown(f"<div style='text-align:center;opacity:0.7'>Página "
              f"<b>{st.session_state.pagina + 1}</b> de {paginas}</div>", unsafe_allow_html=True)

# Scrolling is done from a small iframe component; the page marker makes it reload.
if st.session_state.get("scroll"):
    st.session_state.scroll = False
    st.session_state.pop("foco", None)
    components.html(f"""
        <script>
          const doc = window.parent.document;
          const alvo = doc.getElementById("{TOP_ANCHOR}")
                    || doc.querySelector('div[data-testid="stVerticalBlockBorderWrapper"]');
          if (alvo) alvo.scrollIntoView({{behavior: "smooth", block: "start"}});
        </script>
        <!-- page {st.session_state.pagina} -->""", height=0)
elif st.session_state.get("foco"):
    # Bring the touched card back into view only if the page shrank under it.
    alvo_idx = next((amostra.index(r) + 1 for r in pagina
                     if r["id"] == st.session_state["foco"]), None)
    st.session_state.pop("foco", None)
    if alvo_idx is not None:
        components.html(f"""
            <script>
              const doc = window.parent.document;
              const alvo = doc.getElementById("claim-{alvo_idx}");
              if (alvo) alvo.scrollIntoView({{behavior: "auto", block: "nearest"}});
            </script>
            <!-- focus {st.session_state.get('foco_n', 0)} -->""", height=0)
