/** The evidence on a timeline ending at the claim date. It fills with every news item retrieved,
    each dropping into place; once relevance has ruled (`triado`), the unrelated ones stay in place
    as dashed outlines, still readable and one click from being brought back, while the rest take
    the scale of what is left. Once classified, those that support the claim rise above the line,
    those that refute it drop below and those that decide nothing stay on it. Markers close in time
    stack up, so none covers another, and the timeline grows taller as they need.

    Each marker is a square split in bands, one per relation, in the proportion of the passages the
    news item has (four supporting and one refuting is four fifths green, one fifth red), with the
    number of passages on a small badge. An editor may rule a news item in or out from its panel. */

import { AnimatePresence, motion } from "framer-motion";
import { forwardRef, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLargura } from "../../hooks/useLargura";
import { comoData, DIA_MS } from "../../lib/datas";
import { alternado, empilhar, marcasDoEixo } from "../../lib/eixo";
import {
  contagensDaClassificacao,
  contagensPorDocumento,
  proporcao,
  relacaoDe,
  RELACOES,
  segmentosDoMarcador,
} from "../../lib/evidencia";
import { dataCurta, dataLonga } from "../../lib/formato";
import { SUAVE, SURGIR } from "../../lib/movimento";
import { TOM_MARCADOR } from "../../lib/tons";
import Ajuda from "../Ajuda";
import Bloco from "../Bloco";
import { Lapis } from "../Icones";
import Rotulo from "../Rotulo";

// Marker side and the least room between two markers on one level, in px.
const MARCA = 16;
const FOLGA = 6;
// Vertical step between stacked levels: on the line, and on either side of it.
const PASSO_LINHA = MARCA + 4;
const PASSO_LADO = MARCA + 8;
// Shortest stem of a marker off the line, and how far it keeps from the markers on the line.
const HASTE_MINIMA = 52;
const AFASTAMENTO = 14;
// Least height above and below the line, the bands for the zone labels (top, bottom) and the ruler.
const MEIA_ALTURA = 110;
const TOPO = 26;
const FUNDO = 24;
const REGUA = 22;
// Room kept free at the right for the claim wall.
const REMATE = 22;
// Width budget per tick label.
const LARGURA_POR_MARCA = 64;
// A date label's width (about 6.4px a character at 11px) and its gap from its marker.
const LETRA = 6.4;
const ESPACO_ROTULO = 4;
const ALMOFADA = 3;

const LADO = { supported: -1, refuted: 1 };

// A retrieved news item drops into place, one after another but never more than `CHEGADA_MAXIMA`
// seconds behind the first; one ruled unrelated stays, as a dashed outline. Its place on the line
// it keeps while it goes, as the others slide to their new one (the 600ms transitions below).
const CHEGADA_PASSO = 0.035;
const CHEGADA_MAXIMA = 0.6;
const MARCADOR_ANIMADO = {
  initial: { opacity: 0, y: -14 },
  animate: (ordem) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: SUAVE, delay: Math.min(CHEGADA_MAXIMA, ordem * CHEGADA_PASSO) },
  }),
  // Slow on both ends, so the reader sees which ones go: a fast start would read as a blink.
  exit: { opacity: 0, y: 18, transition: { duration: 0.8, ease: "easeInOut" } },
};

/** Every marker's place, in px from the top left: centre, stem and level. `largura` is the track's. */
function disposicao(marcadores, relacoes, largura) {
  const util = Math.max(1, largura - REMATE - MARCA);
  const itens = marcadores.map(({ documento, posicao }) => {
    const relacao = relacoes.get(documento.doc_id);
    return { documento, posicao, relacao, lado: LADO[relacao] || 0, x: MARCA / 2 + posicao * util };
  });

  // Each side stacks on its own; on the line, levels alternate above and below it.
  for (const lado of [-1, 0, 1]) {
    const doLado = itens.filter((item) => item.lado === lado);
    const niveis = empilhar(doLado.map((item) => item.x), MARCA + FOLGA, lado === 0 ? alternado : undefined);
    doLado.forEach((item, indice) => {
      item.nivel = niveis[indice];
    });
  }

  // Markers off the line start clear of the tallest stack on it.
  const naLinha = Math.max(0, ...itens.filter((i) => i.lado === 0).map((i) => Math.abs(i.nivel))) * PASSO_LINHA;
  const base = Math.max(HASTE_MINIMA, naLinha + MARCA + AFASTAMENTO);
  for (const item of itens) item.desvio = item.lado === 0 ? item.nivel * PASSO_LINHA : item.lado * (base + item.nivel * PASSO_LADO);

  const acima = Math.max(MEIA_ALTURA, ...itens.map((i) => -i.desvio + MARCA / 2 + 8));
  const abaixo = Math.max(MEIA_ALTURA, ...itens.map((i) => i.desvio + MARCA / 2 + 8));
  const linha = TOPO + acima;
  for (const item of itens) item.y = linha + item.desvio;
  return { itens, linha, altura: linha + abaixo + FUNDO + REGUA };
}

/** Which markers have room for their date beside them, without covering another marker, a stem
    or a date. Dates sit on a backing, so the axis and the grid pass behind them. */
function datasQueCabem(itens, linha, largura) {
  const caixas = itens.map((i) => ({ x0: i.x - MARCA / 2, x1: i.x + MARCA / 2, y0: i.y - MARCA / 2, y1: i.y + MARCA / 2 }));
  const hastes = itens
    .filter((i) => i.desvio !== 0)
    .map((i) => ({ x0: i.x - 1, x1: i.x + 1, y0: Math.min(linha, i.y), y1: Math.max(linha, i.y) }));
  const cruza = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
  const lugares = new Map();
  itens.forEach((item, indice) => {
    const largo = dataCurta(item.documento.published_at).length * LETRA + 2 * ALMOFADA;
    // Right of the marker first, unless it is near the claim wall.
    const lados = item.x + MARCA / 2 + ESPACO_ROTULO + largo > largura - REMATE ? [-1, 1] : [1, -1];
    for (const lado of lados) {
      const x0 = lado > 0 ? item.x + MARCA / 2 + ESPACO_ROTULO : item.x - MARCA / 2 - ESPACO_ROTULO - largo;
      const caixa = { x0, x1: x0 + largo, y0: item.y - MARCA / 2, y1: item.y + MARCA / 2 };
      if (x0 < 0 || caixa.x1 > largura - REMATE) continue;
      if (caixas.some((outra, j) => j !== indice && cruza(caixa, outra)) || hastes.some((haste) => cruza(caixa, haste))) continue;
      caixas.push(caixa);
      lugares.set(item.documento.doc_id, lado);
      break;
    }
  });
  return lugares;
}

/** The marker's fill: the bands of the relations it has, or nothing when it has no passage. */
function fundoDoMarcador(conta, total) {
  return total ? segmentosDoMarcador(conta, total) : undefined;
}

const Eixo = forwardRef(function Eixo({
  id,
  plano,
  documentos,
  triado,
  relevancia,
  classificacao,
  evidencia,
  podeEditar,
  original,
  aoMudarRelevancia,
  realcado,
  aoAbrir,
}, ref) {
  const { t } = useTranslation();
  const pista = useRef(null);
  const largura = useLargura(pista) || 600;
  const [lido, setLido] = useState(null);

  const nota = relevancia && relevancia["notícias"]
    ? t("eixo.contas", { count: relevancia["notícias"], n: relevancia.relevantes })
    : !triado && documentos.length ? t("eixo.recuperados", { count: documentos.length }) : null;

  const classificado = Boolean(classificacao);
  // The run is stored, and its news items can be opened, once their passages are classified.
  const abrivel = classificado;
  const contagens = evidencia
    ? contagensPorDocumento(evidencia)
    : contagensDaClassificacao(documentos, classificacao);
  const relacoes = new Map(
    documentos.map((documento) => {
      const conta = contagens.get(documento.doc_id)?.conta || { supported: 0, refuted: 0, nei: 0 };
      const rotulos = new Set(RELACOES.filter((rotulo) => conta[rotulo] > 0));
      return [documento.doc_id, relacaoDe(rotulos, classificado, documento.relevant !== false)];
    })
  );
  const marcadores = plano.semRelevantes ? [] : plano.marcadores;
  const { itens, linha, altura } = disposicao(marcadores, relacoes, largura);
  const datas = datasQueCabem(itens, linha, largura);
  const util = Math.max(1, largura - REMATE - MARCA);
  const tecto = Math.max(2, Math.min(8, Math.floor(largura / LARGURA_POR_MARCA)));
  const marcas = plano.semRelevantes
    ? []
    : marcasDoEixo(plano.inicio, plano.fim, t("eixo.meses", { returnObjects: true }), tecto).filter(({ pos }) => pos > 0.04 && pos < 0.9);

  const ultima = marcadores.length ? comoData(marcadores[marcadores.length - 1].documento.published_at) : null;
  const dias = plano.eDaClaim && ultima ? Math.round((plano.fim - ultima) / DIA_MS) : null;
  // A news item still there once the drawer closes stays readable; one that left takes its
  // reading space with it. It is read from the current list, so ruling it in or out shows at once.
  const lidoAgora = lido ? documentos.find((d) => d.doc_id === lido.doc_id) || null : null;
  const relacaoLida = lidoAgora && relacoes.get(lidoAgora.doc_id);
  const contaLida = lidoAgora ? contagens.get(lidoAgora.doc_id) : null;
  const relevanteLido = lidoAgora ? lidoAgora.relevant !== false : true;
  const podeRular = Boolean(podeEditar && evidencia && lidoAgora);
  // What the pipeline decided for the news item being read, to tell a change of a person's.
  const relevanteAutomatico = lidoAgora
    ? original?.documentos?.find((d) => d.doc_id === lidoAgora.doc_id)?.relevante
    : undefined;
  const alteradoLido = podeRular && relevanteAutomatico !== undefined && relevanteAutomatico !== relevanteLido;

  return (
    <Bloco
      ref={ref}
      id={id}
      titulo={t("bloco.eixo")}
      ajuda={<Ajuda rotulo={t("eixo.comoLer")}>{t(triado ? "eixo.leitura" : "eixo.leituraRecuperados")}</Ajuda>}
      nota={nota}
    >
      <AnimatePresence mode="wait" initial={false}>
        {plano.semRelevantes ? (
          <motion.p key="vazio" {...SURGIR} className="mt-5 text-[15px] text-mudo">
            {t("eixo.semRelevantes")}
          </motion.p>
        ) : (
          <motion.div key="pista" exit={{ opacity: 0, transition: { duration: 0.3, ease: SUAVE } }}>
            <div ref={pista} className="relative mt-11 transition-[height] duration-600 ease-suave" style={{ height: altura }}>
              <span className="absolute top-0 left-0 text-[11px] tracking-[.06em] text-mudo uppercase">↑ {t("eixo.apoiam")}</span>
              <span className="absolute left-0 text-[11px] tracking-[.06em] text-mudo uppercase" style={{ bottom: REGUA + 4 }}>
                ↓ {t("eixo.contrariam")}
              </span>

              {marcas.map(({ pos, etiqueta }) => {
                const x = MARCA / 2 + pos * util;
                return (
                  <div key={`${etiqueta}-${pos}`} aria-hidden="true">
                    <div className="absolute w-px bg-regra" style={{ left: x, top: TOPO, bottom: REGUA }} />
                    <span className="absolute bottom-0 -translate-x-1/2 text-[11px] whitespace-nowrap text-mudo tabular-nums" style={{ left: x }}>
                      {etiqueta}
                    </span>
                  </div>
                );
              })}

              <div className="absolute inset-x-0 h-0.5 bg-divisor" style={{ top: linha - 1 }} />

              {/* The wall at the claim date; when the axis ends on the latest news instead, the label says so. */}
              <div className="absolute top-0 right-0 w-0.5 bg-tinta" style={{ bottom: REGUA }}>
                <span className="absolute top-0 right-1.5 text-[11px] font-semibold tracking-[.06em] whitespace-nowrap uppercase">
                  {plano.eDaClaim ? t("eixo.claim") : t("eixo.ultima")} · {dataCurta(plano.fim.toISOString())}
                </span>
              </div>

              <AnimatePresence>
                {itens.map(({ documento, relacao, x, y, desvio }, ordem) => {
                  const aceso = realcado === documento.doc_id || lidoAgora?.doc_id === documento.doc_id;
                  const mostrar = () => setLido(documento);
                  // The marker being read always shows its date, on a backing so it reads over its neighbours.
                  const ladoDaData = datas.get(documento.doc_id) ?? (aceso ? (x > largura * 0.7 ? -1 : 1) : null);
                  const registo = contagens.get(documento.doc_id);
                  const conta = registo?.conta || { supported: 0, refuted: 0, nei: 0 };
                  const total = registo?.total || 0;
                  const relevante = documento.relevant !== false;
                  const tom = !relevante
                    ? TOM_MARCADOR.irrelevante
                    : !classificado
                      ? TOM_MARCADOR.pendente
                      : total
                        ? "border-tinta"
                        : "border-pendente bg-fundo";
                  return (
                    // Opacity and a shift only: the markers inside are placed against the track.
                    <motion.div key={documento.doc_id} variants={MARCADOR_ANIMADO} custom={ordem} initial="initial" animate="animate" exit="exit">
                      {desvio !== 0 && (
                        <div
                          aria-hidden="true"
                          className={`absolute w-px transition-[left,top,height] duration-600 ease-suave ${aceso ? "bg-tinta" : "bg-divisor"}`}
                          style={{ left: x, top: Math.min(linha, y), height: Math.abs(desvio) }}
                        />
                      )}
                      <button
                        type="button"
                        aria-label={t("eixo.marcador", { titulo: documento.headline, data: dataLonga(documento.published_at) })}
                        onMouseEnter={mostrar}
                        onFocus={mostrar}
                        onClick={abrivel ? (evento) => aoAbrir(documento.doc_id, evento.currentTarget) : mostrar}
                        className={`absolute z-[1] border-2 transition-[left,top,transform,background-color,border-color] duration-600 ease-suave hover:z-[3] hover:scale-125 focus-visible:z-[3] focus-visible:scale-125 ${
                          abrivel ? "" : "cursor-default"
                        } ${tom}`}
                        style={{
                          width: MARCA,
                          height: MARCA,
                          left: x - MARCA / 2,
                          top: y - MARCA / 2,
                          background: relevante && classificado ? fundoDoMarcador(conta, total) : undefined,
                          boxShadow: aceso ? "0 0 0 3px var(--color-fundo), 0 0 0 4px var(--color-divisor)" : "0 0 0 2px var(--color-fundo)",
                        }}
                      >
                        {total > 1 && (
                          <span
                            aria-hidden="true"
                            className="absolute -top-2 -right-2 grid min-w-[12px] place-items-center border border-fundo bg-tinta px-0.5 text-[8px] leading-[10px] font-bold text-fundo tabular-nums"
                          >
                            {total}
                          </span>
                        )}
                      </button>
                      {ladoDaData !== null && (
                        <span
                          aria-hidden="true"
                          className={`pointer-events-none absolute bg-fundo text-[11px] leading-4 whitespace-nowrap tabular-nums transition-[left,right,top] duration-600 ease-suave ${
                            aceso ? "z-[2] text-tinta" : "text-mudo"
                          }`}
                          style={{
                            left: ladoDaData > 0 ? x + MARCA / 2 + ESPACO_ROTULO : undefined,
                            right: ladoDaData < 0 ? largura - (x - MARCA / 2 - ESPACO_ROTULO) : undefined,
                            top: y - MARCA / 2,
                            paddingInline: ALMOFADA,
                          }}
                        >
                          {dataCurta(documento.published_at)}
                        </span>
                      )}
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>

            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[12px] text-mudo">
              {["supported", "nei", "refuted"].map((chave) => (
                <span key={chave} className="flex items-center gap-1.5">
                  <span aria-hidden="true" className={`size-2.5 border-2 ${TOM_MARCADOR[chave]}`} />
                  {t(`rotulo.${chave}`)}
                </span>
              ))}
              {triado && (
                <span className="flex items-center gap-1.5">
                  <span aria-hidden="true" className={`size-2.5 border-2 ${TOM_MARCADOR.irrelevante}`} />
                  {t("eixo.irrelevante")}
                </span>
              )}
              {dias !== null && <span className="ml-auto">{t("eixo.lacuna", { count: dias })}</span>}
            </div>
            {podeEditar && evidencia && (
              <p className="mt-3 flex items-center gap-1.5 text-[12px] text-mudo">
                <Lapis aria-hidden="true" className="size-3.5 flex-none" />
                {t("eixo.dicaEdicao")}
              </p>
            )}

            {/* The news item being read opens under the track and closes with it, so the section
                keeps no empty room for it: the gap to the next section is the same as anywhere. */}
            <AnimatePresence initial={false}>
              {lidoAgora && (
                <motion.div
                  key="lido"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.4, ease: SUAVE }}
                  className="overflow-hidden"
                >
                  <div className="mt-5 border-t border-regra pt-4">
                    <div className="flex flex-col gap-1.5">
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-mudo">
                        <span className="font-semibold text-tinta">{dataLonga(lidoAgora.published_at)}</span>
                        {!relevanteLido && (
                          <span className="flex items-center gap-1.5 font-semibold">
                            <span aria-hidden="true" className={`size-2.5 border-2 ${TOM_MARCADOR.irrelevante}`} />
                            {t("eixo.irrelevante")}
                          </span>
                        )}
                        {classificado && relevanteLido && (relacaoLida === "ambos" ? (
                          <>
                            <Rotulo rotulo="supported" />
                            <Rotulo rotulo="refuted" />
                          </>
                        ) : (
                          <Rotulo rotulo={relacaoLida} />
                        ))}
                        {classificado && contaLida?.total > 0 && (
                          <span className="tabular-nums">
                            {t("eixo.passagens", { proporcao: proporcao(contaLida.conta), count: contaLida.total })}
                          </span>
                        )}
                        {classificado && !contaLida?.total && <span>{t("eixo.semPassagens")}</span>}
                      </div>
                      <span className="text-[16px] leading-[1.4]">{lidoAgora.headline}</span>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                        {abrivel && (
                          <button
                            type="button"
                            onClick={(evento) => aoAbrir(lidoAgora.doc_id, evento.currentTarget)}
                            className="self-start py-1 text-[14px] font-semibold underline underline-offset-3"
                          >
                            {t("eixo.abrir")}
                          </button>
                        )}
                        {podeRular && (
                          <button
                            type="button"
                            aria-pressed={relevanteLido}
                            onClick={() => aoMudarRelevancia(lidoAgora.doc_id, !relevanteLido)}
                            className="inline-flex items-center gap-1.5 self-start border border-divisor px-2.5 py-1 text-[13px] font-semibold transition-colors hover:bg-pairar"
                          >
                            <Lapis aria-hidden="true" className="size-3.5" />
                            {t(relevanteLido ? "eixo.tornarIrrelevante" : "eixo.tornarRelevante")}
                          </button>
                        )}
                        {alteradoLido && (
                          <>
                            <span className="text-[12px] font-semibold text-mudo">{t("eixo.alteradoAMao")}</span>
                            <button
                              type="button"
                              onClick={() => aoMudarRelevancia(lidoAgora.doc_id, relevanteAutomatico)}
                              className="py-1 text-[14px] font-semibold underline underline-offset-3 hover:text-mudo"
                            >
                              {t("revisao.voltarAutomatico")}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </Bloco>
  );
});

export default Eixo;
