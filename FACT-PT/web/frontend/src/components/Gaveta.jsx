/** Document drawer: a news item with the evidence kept from it highlighted, sliding in from the
    right. An editor may select a stretch of the text and link it as supporting, refuting or
    undecided evidence, change the relation of a passage already there, leave one out, or rule the
    news item itself relevant or not. A reader without the permission sees the same passages and
    can still click one to read what it says. */

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { dataLonga } from "../lib/formato";
import { SUAVE } from "../lib/movimento";
import { ROTULOS, TOM_ROTULO } from "../lib/tons";
import { BOTAO_ICONE } from "./Barra";
import { Fechar, Lapis } from "./Icones";
import Rotulo from "./Rotulo";

/** The passages to highlight, valid ones only. They may overlap or nest (a long refuting passage
    can contain a supporting one), so none is dropped: `Corpo` cuts the text where any starts or ends. */
function realces(texto, excertos) {
  return excertos.filter((e) => Number.isInteger(e.begin) && Number.isInteger(e.end) && e.begin >= 0 && e.end > e.begin && e.end <= texto.length);
}

/** The highlight of a stretch of text covered by `cobertos`: its relation when they agree,
    "ambos" (both colours) when it is both supported and refuted, and "excluido" when every
    passage over it has been left out of the evidence. */
function rotuloDoTrecho(cobertos) {
  const rotulos = new Set(cobertos.map((e) => e.rotulo));
  if (rotulos.has("supported") && rotulos.has("refuted")) return "ambos";
  if (rotulos.has("supported")) return "supported";
  if (rotulos.has("refuted")) return "refuted";
  if (rotulos.has("nei")) return "nei";
  return "excluido";
}

/** The smallest review passage covering a stretch: the one a click on it is asking about. An
    article citation drawn over the same stretch is not editable, so it is only chosen when nothing
    else covers the text, and a click on it does nothing. */
function maisProximo(cobertos) {
  const editaveis = cobertos.filter((e) => !String(e.id).startsWith("citacao-"));
  return [...editaveis].sort((a, b) => (a.end - a.begin) - (b.end - b.begin))[0] || null;
}

/** The text of [inicio, fim), with the stretch of `excerto` in it marked. */
function trechos(texto, inicio, fim, excerto) {
  if (!excerto || excerto.end <= inicio || excerto.begin >= fim) return texto.slice(inicio, fim);
  const [de, ate] = [Math.max(inicio, excerto.begin), Math.min(fim, excerto.end)];
  return [texto.slice(inicio, de), <span key="excerto" data-excerto>{texto.slice(de, ate)}</span>, texto.slice(ate, fim)];
}

/** The news item's text with the evidence highlighted. A cited passage that joins several
    classified excerpts says how many in its marker, and `excerto`, the one under the pointer, is
    marked within it. `aoEscolher`, when the drawer edits, opens the passage clicked. */
function Corpo({ doc, excertos, excerto, aoEscolher }) {
  const { t } = useTranslation();
  const texto = doc.content || "";
  const validos = realces(texto, excertos);
  const cortes = [...new Set([0, texto.length, ...validos.flatMap((e) => [e.begin, e.end])])].sort((a, b) => a - b);
  const partes = [];
  for (let i = 0; i < cortes.length - 1; i += 1) {
    const [inicio, fim] = [cortes[i], cortes[i + 1]];
    const cobertos = validos.filter((e) => e.begin <= inicio && e.end >= fim);
    if (!cobertos.length) {
      partes.push(texto.slice(inicio, fim));
      continue;
    }
    // An excluded passage stays visible under a counted one: the counted one says what the
    // stretch is worth, and the excluded one can still be brought back from the panel.
    const contados = cobertos.filter((e) => e.rotulo);
    const escolhidos = contados.length ? contados : cobertos;
    const alvo = maisProximo(escolhidos);
    const escolher = aoEscolher && alvo ? () => aoEscolher(alvo) : undefined;
    partes.push(
      <mark
        key={inicio}
        className="realce"
        data-rotulo={rotuloDoTrecho(escolhidos)}
        data-foco={cobertos.some((e) => e.foco) || undefined}
        data-humano={cobertos.some((e) => e.origem === "humano") || undefined}
        data-escolhivel={escolher ? true : undefined}
        role={escolher ? "button" : undefined}
        tabIndex={escolher ? 0 : undefined}
        onClick={escolher}
        onKeyDown={escolher ? (evento) => {
          if (evento.key !== "Enter" && evento.key !== " ") return;
          evento.preventDefault();
          escolher();
        } : undefined}
      >
        {validos
          .filter((e) => e.begin === inicio && e.marcador)
          .map((e) => (
            <span key={e.marcador} data-marcador className={`mr-1 inline-block border bg-fundo px-1 py-0.5 align-[2px] font-sans text-[10.5px] leading-none font-semibold tabular-nums ${TOM_ROTULO[e.rotulo]?.citacao || ""}`}>
              {e.marcador}
              {e.janelas?.length > 1 && <span className="font-normal"> · {t("gaveta.excertos", { n: e.janelas.length })}</span>}
            </span>
          ))}
        <span data-texto={inicio}>{trechos(texto, inicio, fim, excerto)}</span>
      </mark>
    );
  }
  return partes;
}

/** Where a point of the rendered text falls in the source: the text nodes before it, in order,
    without the citation badges (`[data-marcador]`), which are not part of the news item. */
function deslocamento(raiz, no, deslocamentoNo) {
  if (!raiz.contains(no) || no.nodeType !== Node.TEXT_NODE) return null;
  if (no.parentElement?.closest("[data-marcador]")) return null;
  const caminhante = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  let total = 0;
  let atual = caminhante.nextNode();
  while (atual) {
    if (!atual.parentElement?.closest("[data-marcador]")) {
      if (atual === no) return total + deslocamentoNo;
      total += atual.nodeValue.length;
    }
    atual = caminhante.nextNode();
  }
  return null;
}

/** The selected stretch, trimmed of surrounding whitespace and matched against the source, so the
    server receives exactly `content[begin:end] === texto`. Null when it is not a usable passage. */
function selecaoDoCorpo(raiz, conteudo) {
  const selecao = window.getSelection();
  if (!raiz || !selecao || selecao.rangeCount === 0 || selecao.isCollapsed) return null;
  const intervalo = selecao.getRangeAt(0);
  if (!raiz.contains(intervalo.commonAncestorContainer)) return null;
  const inicio = deslocamento(raiz, intervalo.startContainer, intervalo.startOffset);
  const fim = deslocamento(raiz, intervalo.endContainer, intervalo.endOffset);
  if (inicio === null || fim === null) return null;
  let [begin, end] = inicio <= fim ? [inicio, fim] : [fim, inicio];
  if (begin < 0 || end > conteudo.length || end - begin < 2) return null;
  const bruto = conteudo.slice(begin, end);
  const esquerda = bruto.length - bruto.trimStart().length;
  const direita = bruto.length - bruto.trimEnd().length;
  begin += esquerda;
  end -= direita;
  const texto = conteudo.slice(begin, end);
  if (texto.length < 2) return null;
  return { begin, end, texto };
}

/** One button per relation, with the passage's current one filled in. */
function BotoesDeRelacao({ rotulo, aoMudar }) {
  const { t } = useTranslation();
  return ROTULOS.map((chave) => (
    <button
      key={chave}
      type="button"
      aria-pressed={rotulo === chave}
      onClick={() => aoMudar(chave)}
      className={`inline-flex items-center gap-1.5 border-2 px-2.5 py-1.5 text-[13px] font-semibold transition-colors ${
        rotulo === chave
          ? "border-tinta bg-tinta text-fundo"
          : `${TOM_ROTULO[chave].borda} ${TOM_ROTULO[chave].texto} hover:bg-fundo`
      }`}
    >
      <span aria-hidden="true" className={`size-2 ${rotulo === chave ? "bg-fundo" : TOM_ROTULO[chave].fundo}`} />
      {t(`rotulo.${chave}`)}
    </button>
  ));
}

/** Where in the news item's text the pointer is, or null when it is not over a highlighted
    passage's text. */
function posicaoDoPonteiro(evento) {
  let no = null;
  let desvio = 0;
  if (document.caretPositionFromPoint) {
    const posicao = document.caretPositionFromPoint(evento.clientX, evento.clientY);
    [no, desvio] = [posicao?.offsetNode, posicao?.offset];
  } else if (document.caretRangeFromPoint) {
    const posicao = document.caretRangeFromPoint(evento.clientX, evento.clientY);
    [no, desvio] = [posicao?.startContainer, posicao?.startOffset];
  }
  const trecho = (no?.nodeType === Node.TEXT_NODE ? no.parentElement : no)?.closest?.("[data-texto]");
  if (!trecho) return null;
  const antes = document.createRange();
  antes.setStart(trecho, 0);
  antes.setEnd(no, desvio);
  return Number(trecho.dataset.texto) + antes.toString().length;
}

/** The classified excerpt at `posicao`, in a passage that joins several. Excerpts overlap - each
    starts a sentence after the one before -, so of those that hold it, the last to start. */
function excertoEm(excertos, posicao) {
  let escolhido = null;
  for (const e of excertos) {
    if (!(e.janelas?.length > 1) || posicao < e.begin || posicao >= e.end) continue;
    for (const janela of e.janelas) {
      if (janela.begin <= posicao && posicao < janela.end && (!escolhido || janela.begin > escolhido.begin)) escolhido = janela;
    }
  }
  return escolhido;
}

function Painel({ doc, excertos, relevante, aoFechar, podeEditar, original, aoDestacar, aoMudarExcerto, aoRemoverExcerto, aoMudarRelevancia }) {
  const { t } = useTranslation();
  const fechar = useRef(null);
  const corpo = useRef(null);
  const [selecao, setSelecao] = useState(null);
  const [escolhido, setEscolhido] = useState(null);
  // The classified excerpt under the pointer, in a cited passage that joins several.
  const [janela, setJanela] = useState(null);

  useEffect(() => {
    fechar.current?.focus();
    const tecla = (evento) => evento.key === "Escape" && aoFechar();
    document.addEventListener("keydown", tecla);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", tecla);
      document.body.style.removeProperty("overflow");
    };
  }, [aoFechar]);

  // A new document starts at its top, then glides to the passage it was opened for. The focus is
  // part of the key, so adding a highlight while the drawer is open does not scroll it again.
  const foco = excertos.find((e) => e.foco)?.begin;
  useEffect(() => {
    const no = corpo.current;
    if (!no) return undefined;
    no.scrollTop = 0;
    const marca = no.querySelector("mark[data-foco]") || no.querySelector("mark");
    if (!marca) return undefined;
    const quadro = requestAnimationFrame(() => {
      no.scrollTo({ top: Math.max(0, marca.offsetTop - no.clientHeight / 3), behavior: "smooth" });
    });
    return () => cancelAnimationFrame(quadro);
  }, [doc, foco]);

  // A new document means a new selection and a new passage: the old ones belong to the text just
  // closed.
  useEffect(() => {
    setSelecao(null);
    setEscolhido(null);
  }, [doc]);

  function lerSelecao() {
    if (!podeEditar) return;
    const achado = selecaoDoCorpo(corpo.current, doc.content || "");
    setSelecao(achado);
    if (achado) setEscolhido(null);
  }

  function escolher(excerto) {
    // Selecting text to link it is not a click on the passage underneath.
    if (window.getSelection()?.toString().trim()) return;
    window.getSelection()?.removeAllRanges();
    setSelecao(null);
    setEscolhido(excerto.id);
  }

  function destacar(rotulo) {
    if (!selecao) return;
    aoDestacar(doc.doc_id, selecao.begin, selecao.end, selecao.texto, rotulo);
    window.getSelection()?.removeAllRanges();
    setSelecao(null);
  }

  function alterar(rotulo) {
    const excerto = excertos.find((e) => e.id === escolhido);
    if (!excerto) return;
    aoMudarExcerto(excerto.id, { rotulo });
  }

  function excluir() {
    const excerto = excertos.find((e) => e.id === escolhido);
    if (!excerto) return;
    if (excerto.origem === "humano") {
      aoRemoverExcerto(excerto.id);
      setEscolhido(null);
      return;
    }
    aoMudarExcerto(excerto.id, { rotulo: null });
  }

  const meta = [dataLonga(doc.published_at), doc.genre, doc.byline].filter(Boolean);
  if (doc.word_count) meta.push(t("gaveta.palavras", { n: doc.word_count }));
  const relacoes = [...new Set(excertos.filter((e) => e.rotulo).map((e) => e.rotulo))];
  const escolhidoExcerto = escolhido ? excertos.find((e) => e.id === escolhido) : null;
  const textoEscolhido = escolhidoExcerto
    ? escolhidoExcerto.texto || (doc.content || "").slice(escolhidoExcerto.begin, escolhidoExcerto.end)
    : "";
  // What the pipeline said of the chosen passage, to tell a change of a person's.
  const rotuloAutomatico = escolhidoExcerto && escolhidoExcerto.origem !== "humano"
    ? original?.excertos?.find((e) => e.id === escolhidoExcerto.id)?.rotulo
    : undefined;
  const alterada = rotuloAutomatico !== undefined && rotuloAutomatico !== escolhidoExcerto?.rotulo;

  return (
    <>
      <motion.div
        className="fixed inset-0 z-40 bg-[color-mix(in_srgb,var(--color-tinta)_30%,transparent)]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        onClick={aoFechar}
      />
      <motion.aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="gaveta-titulo"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ duration: 0.28, ease: SUAVE }}
        className="fixed inset-y-0 right-0 z-50 flex w-[min(560px,100vw)] flex-col border-l-2 border-divisor bg-fundo"
      >
        <div className="grid gap-5 px-[clamp(20px,3vw,40px)] pt-6">
          <div className="flex items-center justify-between gap-3 border-b-2 border-divisor pb-3">
            <span className="rubrica">{t("gaveta.fonte", { id: doc.doc_id })}</span>
            <button ref={fechar} type="button" aria-label={t("gaveta.fechar")} onClick={aoFechar} className={BOTAO_ICONE}>
              <Fechar className="size-4" />
            </button>
          </div>
          <h2 id="gaveta-titulo" className="text-[24px] leading-[1.2] [text-wrap:balance]">{doc.headline || t("gaveta.semTitulo")}</h2>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-regra pb-4 text-[13px] text-mudo">
            {meta.map((texto, indice) => (
              <span key={indice}>{texto}</span>
            ))}
            {relacoes.map((rotulo) => (
              <Rotulo key={rotulo} rotulo={rotulo} />
            ))}
            {!relevante && (
              <span className="flex items-center gap-1.5 font-semibold">
                <span aria-hidden="true" className="size-2.5 border-2 border-dashed border-divisor" />
                {t("gaveta.irrelevante")}
              </span>
            )}
          </div>
          {podeEditar && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-start gap-2 border-l-2 border-tinta bg-superficie px-3 py-2 text-[13px]">
                <Lapis aria-hidden="true" className="mt-0.5 size-4 flex-none" />
                {t("gaveta.destacarPassos")}
              </p>
              <button
                type="button"
                aria-pressed={relevante}
                onClick={() => aoMudarRelevancia(doc.doc_id, !relevante)}
                className="inline-flex items-center gap-1.5 border border-divisor px-2.5 py-1.5 text-[12px] font-semibold transition-colors hover:bg-pairar"
              >
                <span aria-hidden="true" className={`size-2.5 border-2 ${relevante ? "border-tinta bg-tinta" : "border-dashed border-divisor"}`} />
                {t(relevante ? "gaveta.tornarIrrelevante" : "gaveta.tornarRelevante")}
              </button>
            </div>
          )}
        </div>
        {/* Focusable, so the text can be scrolled from the keyboard. */}
        <div
          ref={corpo}
          tabIndex={0}
          onMouseUp={lerSelecao}
          onKeyUp={lerSelecao}
          onTouchEnd={lerSelecao}
          onMouseMove={(evento) => {
            const posicao = posicaoDoPonteiro(evento);
            setJanela(posicao === null ? null : excertoEm(excertos, posicao));
          }}
          onMouseLeave={() => setJanela(null)}
          className="relative flex-1 overflow-y-auto px-[clamp(20px,3vw,40px)] pt-4 pb-12 text-[16px] leading-[1.7] break-words whitespace-pre-wrap focus-visible:outline-none"
        >
          <Corpo key={`${doc.doc_id}-${foco}`} doc={doc} excertos={excertos} excerto={janela} aoEscolher={podeEditar ? escolher : null} />
        </div>

        {selecao && podeEditar && (
          <div className="grid gap-3 border-t-2 border-divisor bg-superficie px-[clamp(20px,3vw,40px)] py-3">
            <p className="max-h-16 overflow-y-auto border-l-2 border-tinta pl-2 text-[13px] leading-[1.5] text-mudo">
              «{selecao.texto}»
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[12px] font-semibold tracking-[.06em] uppercase">{t("gaveta.ligarComo")}</span>
              {ROTULOS.map((rotulo) => (
                <button
                  key={rotulo}
                  type="button"
                  onClick={() => destacar(rotulo)}
                  className={`inline-flex items-center gap-1.5 border-2 px-2.5 py-1.5 text-[13px] font-semibold transition-colors ${TOM_ROTULO[rotulo].borda} ${TOM_ROTULO[rotulo].texto} hover:bg-fundo`}
                >
                  <span aria-hidden="true" className={`size-2 ${TOM_ROTULO[rotulo].fundo}`} />
                  {t(`rotulo.${rotulo}`)}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  window.getSelection()?.removeAllRanges();
                  setSelecao(null);
                }}
                className="ml-auto px-2 py-1.5 text-[13px] font-semibold text-mudo underline underline-offset-2 hover:text-tinta"
              >
                {t("gaveta.cancelarSelecao")}
              </button>
            </div>
          </div>
        )}

        {escolhidoExcerto && (
          <div className="grid gap-3 border-t-2 border-divisor bg-superficie px-[clamp(20px,3vw,40px)] py-3">
            <p className="max-h-16 overflow-y-auto border-l-2 border-tinta pl-2 text-[13px] leading-[1.5] text-mudo">
              «{textoEscolhido}»
            </p>
            <p className="text-[12px] font-semibold text-mudo">
              {escolhidoExcerto.origem === "humano"
                ? t("gaveta.origemHumana")
                : alterada
                  ? t("gaveta.alteradaAMao")
                  : t("gaveta.origemAutomatica")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[12px] font-semibold tracking-[.06em] uppercase">
                {escolhidoExcerto.rotulo === null ? t("gaveta.excluida") : t("gaveta.alterarComo")}
              </span>
              <BotoesDeRelacao rotulo={escolhidoExcerto.rotulo} aoMudar={alterar} />
              {escolhidoExcerto.rotulo !== null && (
                <button
                  type="button"
                  onClick={excluir}
                  className="px-2 py-1.5 text-[13px] font-semibold text-mudo underline underline-offset-2 hover:text-contraria"
                >
                  {escolhidoExcerto.origem === "humano" ? t("gaveta.removerDestaque") : t("gaveta.excluir")}
                </button>
              )}
              {alterada && (
                <button
                  type="button"
                  onClick={() => aoMudarExcerto(escolhidoExcerto.id, { rotulo: rotuloAutomatico })}
                  className="px-2 py-1.5 text-[13px] font-semibold underline underline-offset-2 hover:text-mudo"
                >
                  {t("revisao.voltarAutomatico")}
                </button>
              )}
              <button
                type="button"
                onClick={() => setEscolhido(null)}
                className="ml-auto px-2 py-1.5 text-[13px] font-semibold text-mudo underline underline-offset-2 hover:text-tinta"
              >
                {t("gaveta.fecharPassagem")}
              </button>
            </div>
          </div>
        )}
      </motion.aside>
    </>
  );
}

/** `aberto` is `{ doc, excertos, relevante, origem }`: the news item, the passages kept from it
    (`{ id, begin, end, rotulo, origem, texto, marcador, foco, janelas }`, `janelas` the classified
    excerpts a cited passage is made of) and where focus goes back to on close. `podeEditar` turns the drawer into the review's editing surface. */
export default function Gaveta({ aberto, aoFechar, podeEditar = false, original, aoDestacar, aoMudarExcerto, aoRemoverExcerto, aoMudarRelevancia }) {
  const origem = useRef(null);
  if (aberto) origem.current = aberto.origem;
  return (
    <AnimatePresence
      onExitComplete={() => {
        if (origem.current && document.contains(origem.current)) origem.current.focus();
        origem.current = null;
      }}
    >
      {aberto && (
        <Painel
          key="gaveta"
          doc={aberto.doc}
          excertos={aberto.excertos}
          relevante={aberto.relevante !== false}
          aoFechar={aoFechar}
          podeEditar={podeEditar}
          original={original}
          aoDestacar={aoDestacar}
          aoMudarExcerto={aoMudarExcerto}
          aoRemoverExcerto={aoRemoverExcerto}
          aoMudarRelevancia={aoMudarRelevancia}
        />
      )}
    </AnimatePresence>
  );
}
