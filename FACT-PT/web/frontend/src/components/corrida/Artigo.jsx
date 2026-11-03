/** The fact-checking article, with each citation opening the news item it comes from, and the
    cited evidence underneath, one row per news item.

    Under the heading, a bar says where the article came from: the run's own writer, a rewrite
    from the reviewed evidence, or a person's edit. An editor may edit its text in place - the
    title, the lead, each paragraph and heading - as part of the draft, with a citation written as
    `[n]`; or ask for it to be written again, with the run's writer or another. The bar follows the
    worker while it writes. When several articles were written from the same evidence, a row of
    buttons switches between them, a toggle lays two side by side, and an editor can keep the one
    on view as the verification's own. When there is no article yet but there is a review, the bar is the only
    thing there: the article can be written from the evidence as it stands. */

import { forwardRef, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { dataCurta } from "../../lib/formato";
import { ROTULOS } from "../../lib/tons";
import Bloco from "../Bloco";
import { Fechar, Lapis } from "../Icones";
import Rotulo from "../Rotulo";
import TextoCitado from "../TextoCitado";

const MARCADOR = /\[\[C:(\d+):([^\]]+)\]\]/g;
const BOTAO = "border border-divisor px-2.5 py-1 font-semibold transition-colors hover:bg-pairar disabled:cursor-not-allowed disabled:opacity-40";
// An editable stretch keeps the type it is shown in, and is told apart only by a dashed outline.
const CAMPO = "block w-full resize-none overflow-hidden bg-transparent outline-1 -outline-offset-1 outline-regra outline-dashed focus:outline-2 focus:outline-tinta focus:outline-solid";

/** The citations grouped by news item, in order of first citation. */
function porNoticia(citacoes) {
  const grupos = [];
  for (const citacao of citacoes) {
    let grupo = grupos.find((g) => g.docId === citacao.doc_id);
    if (!grupo) grupos.push((grupo = { docId: citacao.doc_id, citacoes: [] }));
    grupo.citacoes.push(citacao);
  }
  return grupos;
}

/** The citations whose marker the text still carries: one taken out of the text leaves the list. */
function citadas(artigo) {
  const textos = [artigo.title, artigo.lead, ...artigo.blocks.map((bloco) => bloco.text)].join("\n");
  const usadas = new Set([...textos.matchAll(MARCADOR)].map((encontro) => `${encontro[1]}:${encontro[2]}`));
  return artigo.citations.filter((citacao) => usadas.has(`${citacao.marker}:${citacao.excerpt_id}`));
}

/** A citation marker as a person types it, `[n]`. */
const paraEdicao = (texto) => String(texto || "").replace(MARCADOR, "[$1]");

/** Back from `[n]` to the marker, for the citations the article has, or those of the automated
    one (a marker taken out and typed again). Returns the text and the citations it now needs. */
function deEdicao(texto, citacoes, reserva) {
  const novas = [];
  const convertido = texto.replace(/\[(\d+)\]/g, (todo, numero) => {
    let citacao = citacoes.find((c) => c.marker === numero);
    if (!citacao) {
      citacao = reserva.find((c) => c.marker === numero);
      if (citacao && !novas.includes(citacao)) novas.push(citacao);
    }
    return citacao ? `[[C:${numero}:${citacao.excerpt_id}]]` : todo;
  });
  return { texto: convertido, novas };
}

/** A textarea that grows with what it holds, in the type of what it stands for. */
function Campo({ valor, aoMudar, className, rotulo, ...resto }) {
  const no = useRef(null);
  useLayoutEffect(() => {
    const campo = no.current;
    if (!campo) return;
    campo.style.height = "auto";
    campo.style.height = `${campo.scrollHeight}px`;
  }, [valor]);
  return (
    <textarea
      ref={no}
      rows={1}
      value={valor}
      aria-label={rotulo}
      onChange={(evento) => aoMudar(evento.target.value)}
      className={`${CAMPO} ${className}`}
      {...resto}
    />
  );
}

/** How the rewrite is going, where the article came from, and the editor's controls. */
function BarraArtigo({ revisao, redatores, temArtigo, aEditar, aoEditar }) {
  const { t } = useTranslation();
  const opcoes = redatores?.opcoes || [];
  const [redator, setRedator] = useState(null);
  if (!revisao?.dados) return null;
  const pedido = revisao.pedido;
  const podeEditar = revisao.podeEditar;
  const emCurso = Boolean(pedido && (pedido.estado === "na-fila" || pedido.estado === "em-curso"));
  const nomeDe = (id) => opcoes.find((o) => o.id === id)?.nome || id;
  const erro =
    pedido?.estado === "erro"
      ? t(`artigo.erro.${pedido.erro}`, { redator: nomeDe(pedido.redator), defaultValue: t("artigo.erroGenerico") })
      : null;
  const estado = emCurso ? t(`artigo.pedido.${pedido.estado}`) : erro || (podeEditar && !temArtigo ? t("artigo.reescreverPista") : "");
  // The run's writer by default, while the deployment still offers it.
  const escolhido = redator ?? (opcoes.some((o) => o.id === revisao.redator) ? revisao.redator : opcoes[0]?.id || revisao.redator);
  const origem = revisao.artigoOrigem;
  const autor = origem?.autor?.nome || origem?.autor?.utilizador || "";

  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-regra py-2 text-[12px] text-mudo">
      {estado && (
        <span role="status" className={`flex items-center gap-1.5 ${erro ? "text-contraria" : ""}`}>
          <span aria-hidden="true" className={`size-2 flex-none ${erro ? "bg-contraria" : emCurso ? "bg-indeciso" : "bg-mudo"}`} />
          {estado}
        </span>
      )}
      {podeEditar && temArtigo && (
        <button
          type="button"
          onClick={aoEditar}
          aria-pressed={aEditar}
          title={t("artigo.pistaEdicao")}
          className={`${BOTAO} inline-flex items-center gap-1.5 aria-pressed:bg-tinta aria-pressed:text-fundo`}
        >
          <Lapis aria-hidden="true" className="size-3.5" />
          {aEditar ? t("artigo.concluirEdicao") : t("artigo.editar")}
        </button>
      )}
      {podeEditar && (
        <span className="flex flex-wrap items-center gap-2">
          {opcoes.length > 1 && (
            <label className="flex items-center gap-1.5">
              <span className="sr-only">{t("artigo.redator")}</span>
              <select
                value={escolhido}
                onChange={(evento) => setRedator(evento.target.value)}
                disabled={emCurso}
                className="border border-divisor bg-fundo px-1.5 py-1 text-[12px] font-semibold text-tinta outline-none focus:border-tinta"
              >
                {opcoes.map((opcao) => (
                  <option key={opcao.id} value={opcao.id}>
                    {opcao.nome}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button type="button" onClick={() => revisao.pedirReescrita(escolhido)} disabled={emCurso} className={BOTAO}>
            {emCurso ? t("artigo.pedido.aEscrever") : revisao.alterado ? t("artigo.guardarEReescrever") : t("artigo.reescrever")}
          </button>
        </span>
      )}
      {origem && (
        <span className="ml-auto">
          {origem.accao === "artigo"
            ? t("artigo.origem.artigo", { versao: origem.versao, redator: nomeDe(origem.redator) })
            : t(`artigo.origem.${origem.accao}`, { versao: origem.versao, autor })}
        </span>
      )}
    </div>
  );
}

/** The articles written from the same evidence - an example's, one per model, or a reviewed run's
    rewrites - to read one after the other, lay side by side, and (an editor) pick as the
    verification's own. `versoes` is `{ lista, vista, comparada, anteriores, aoVer, aoComparar,
    aoUsar }`, each of the list `{ chave, rotulo, artigo }`; `aoUsar` is null unless the person may
    save the article on view. */
function EscolhaArtigo({ versoes }) {
  const { t } = useTranslation();
  const { lista, vista, comparada, anteriores, aoVer, aoComparar, aoUsar } = versoes;
  if (lista.length < 2) return null;
  const outras = lista.filter((candidato) => candidato.chave !== vista);
  const comparando = comparada !== null;
  const com = outras.find((candidato) => candidato.chave === comparada) || outras[0];
  return (
    <div className="mt-4 grid gap-2 text-[12px] text-mudo">
      <div className="flex flex-wrap items-center gap-2">
        <span id="artigo-versoes">{t("artigo.modeloDoArtigo")}</span>
        <span role="group" aria-labelledby="artigo-versoes" className="flex flex-wrap gap-2">
          {lista.map((candidato) => (
            <button
              key={candidato.chave}
              type="button"
              aria-pressed={candidato.chave === vista}
              onClick={() => aoVer(candidato.chave)}
              className={`${BOTAO} text-tinta aria-pressed:bg-tinta aria-pressed:text-fundo`}
            >
              {candidato.rotulo}
            </button>
          ))}
        </span>
        <button type="button" aria-pressed={comparando} onClick={() => aoComparar(comparando ? null : outras[0].chave)} className={`${BOTAO} text-tinta aria-pressed:bg-tinta aria-pressed:text-fundo`}>
          {t("artigo.comparar")}
        </button>
        {comparando && (
          <label className="flex items-center gap-1.5">
            {t("artigo.compararCom")}
            <select
              value={com.chave}
              onChange={(evento) => aoComparar(evento.target.value)}
              className="border border-divisor bg-fundo px-1.5 py-1 text-[12px] font-semibold text-tinta outline-none focus:border-tinta"
            >
              {outras.map((candidato) => (
                <option key={candidato.chave} value={candidato.chave}>
                  {candidato.rotulo}
                </option>
              ))}
            </select>
          </label>
        )}
        {aoUsar && (
          <button type="button" onClick={aoUsar} title={t("artigo.usarEstePista")} className={`${BOTAO} border-tinta bg-tinta text-fundo hover:bg-tinta hover:opacity-85`}>
            {t("artigo.usarEste")}
          </button>
        )}
      </div>
      {anteriores > 0 && <p>{t("artigo.anteriores", { count: anteriores })}</p>}
    </div>
  );
}

/** One article in the side-by-side view: its model, then its text. */
function Coluna({ rotulo, artigo, aoCitar }) {
  return (
    <div className="min-w-0">
      <div className="mb-3 border-b border-divisor pb-2 text-[12px] font-semibold tracking-[.06em] text-mudo uppercase">{rotulo}</div>
      <h3 className="mb-3 text-[22px] leading-[1.2] tracking-[-.01em] [text-wrap:balance]">{artigo.title}</h3>
      <p className="mb-6 text-[16px] leading-[1.6] [text-wrap:pretty]">
        <TextoCitado texto={artigo.lead} citacoes={artigo.citations} aoCitar={aoCitar} />
      </p>
      {artigo.blocks.map((bloco, indice) =>
        bloco.type === "heading" ? (
          <h4 key={indice} className="mt-6 mb-2 text-[15px] tracking-[-.005em]">{bloco.text}</h4>
        ) : (
          <p key={indice} className="mb-3 text-[15px] leading-[1.65] [text-wrap:pretty]">
            <TextoCitado texto={bloco.text} citacoes={artigo.citations} aoCitar={aoCitar} />
          </p>
        )
      )}
    </div>
  );
}

/** The article's text as fields: the same type, each stretch editable, citations as `[n]`. */
function Edicao({ artigo, original, aoMudar }) {
  const { t } = useTranslation();
  const reserva = original?.citations || [];
  const mudarTexto = (chave, valor, aplicar) =>
    aoMudar((antes) => {
      const { texto, novas } = deEdicao(valor, antes.citations, reserva);
      return { ...aplicar(antes, texto), citations: [...antes.citations, ...novas] };
    }, `artigo:${chave}`);
  const mudarBloco = (indice, valor) =>
    mudarTexto(`bloco:${indice}`, valor, (antes, texto) => ({
      ...antes,
      blocks: antes.blocks.map((bloco, i) => (i === indice ? { ...bloco, text: texto } : bloco)),
    }));
  const removerBloco = (indice) => aoMudar((antes) => ({ ...antes, blocks: antes.blocks.filter((_, i) => i !== indice) }));
  const acrescentar = (tipo) => aoMudar((antes) => ({ ...antes, blocks: [...antes.blocks, { type: tipo, text: "" }] }));

  return (
    <>
      <p className="mt-6 text-[12px] text-mudo">{t("artigo.pistaEdicao")}</p>
      <Campo
        rotulo={t("artigo.campo.titulo")}
        valor={paraEdicao(artigo.title)}
        aoMudar={(valor) => mudarTexto("title", valor, (antes, texto) => ({ ...antes, title: texto }))}
        className="mt-4 mb-4 text-[clamp(26px,3vw,36px)] leading-[1.15] tracking-[-.02em]"
      />
      <Campo
        rotulo={t("artigo.campo.lead")}
        valor={paraEdicao(artigo.lead)}
        aoMudar={(valor) => mudarTexto("lead", valor, (antes, texto) => ({ ...antes, lead: texto }))}
        className="mb-10 text-[19px] leading-[1.6]"
      />
      {artigo.blocks.map((bloco, indice) => (
        <div key={indice} className="group relative">
          <Campo
            rotulo={t(bloco.type === "heading" ? "artigo.campo.intertitulo" : "artigo.campo.paragrafo", { n: indice + 1 })}
            valor={paraEdicao(bloco.text)}
            aoMudar={(valor) => mudarBloco(indice, valor)}
            className={bloco.type === "heading" ? "mt-8 mb-2.5 text-[16px] font-semibold tracking-[-.005em]" : "mb-3.5 text-[17px] leading-[1.7]"}
          />
          <button
            type="button"
            onClick={() => removerBloco(indice)}
            aria-label={t("artigo.removerBloco")}
            title={t("artigo.removerBloco")}
            className="absolute top-1 -right-9 p-1.5 text-mudo opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 hover:text-contraria focus-visible:opacity-100 max-md:right-1"
          >
            <Fechar className="size-3.5" />
          </button>
        </div>
      ))}
      <div className="mt-2 flex flex-wrap gap-2 text-[12px]">
        <button type="button" onClick={() => acrescentar("paragraph")} className={BOTAO}>
          {t("artigo.acrescentarParagrafo")}
        </button>
        <button type="button" onClick={() => acrescentar("heading")} className={BOTAO}>
          {t("artigo.acrescentarIntertitulo")}
        </button>
      </div>
    </>
  );
}

const Artigo = forwardRef(function Artigo({ id, artigo, versoes, aVer = false, original, aoCitar, aoRealcar, revisao, redatores }, ref) {
  const { t } = useTranslation();
  const [aEditar, setAEditar] = useState(false);
  // An article on view in place of the draft's is read, not edited: the draft's text is not it.
  const editavel = Boolean(artigo && !aVer && revisao?.podeEditar && revisao.estado?.artigo);
  const lista = versoes?.lista || [];
  const comparada = versoes?.comparada ?? null;
  const outra = comparada !== null && lista.length > 1
    ? lista.find((c) => c.chave === comparada && c.chave !== versoes.vista) || lista.find((c) => c.chave !== versoes.vista)
    : null;
  const citacoes = artigo ? citadas(artigo) : [];
  return (
    <Bloco ref={ref} id={id} como="article" titulo={t("artigo.selo")} nota={artigo?.model && t("artigo.escritoPor", { modelo: artigo.model })}>
      <BarraArtigo revisao={revisao} redatores={redatores} temArtigo={Boolean(artigo) && !aVer} aEditar={aEditar && editavel} aoEditar={() => setAEditar((a) => !a)} />
      {versoes && <EscolhaArtigo versoes={versoes} />}

      {!artigo ? (
        <p className="mt-8 text-[15px] text-mudo">{t("artigo.semArtigo")}</p>
      ) : (
        <>
          {aEditar && editavel ? (
            <Edicao artigo={artigo} original={original} aoMudar={revisao.mudarArtigo} />
          ) : outra ? (
            <div className="mt-8 grid gap-x-10 gap-y-12 md:grid-cols-2">
              <Coluna rotulo={lista.find((c) => c.chave === versoes.vista)?.rotulo || artigo.model} artigo={artigo} aoCitar={aoCitar} />
              <Coluna rotulo={outra.rotulo} artigo={outra.artigo} />
            </div>
          ) : (
            <>
              <h3 className="mt-8 mb-4 text-[clamp(26px,3vw,36px)] leading-[1.15] tracking-[-.02em] [text-wrap:balance]">{artigo.title}</h3>
              {/* The lead carries citation markers too, like the body. */}
              <p className="mb-10 text-[19px] leading-[1.6] [text-wrap:pretty]">
                <TextoCitado texto={artigo.lead} citacoes={artigo.citations} aoCitar={aoCitar} />
              </p>

              <div className="">
                {artigo.blocks.map((bloco, indice) =>
                  bloco.type === "heading" ? (
                    <h4 key={indice} className="mt-8 mb-2.5 text-[16px] tracking-[-.005em] first:mt-0">{bloco.text}</h4>
                  ) : (
                    <p key={indice} className="mb-3.5 text-[17px] leading-[1.7] [text-wrap:pretty]">
                      <TextoCitado texto={bloco.text} citacoes={artigo.citations} aoCitar={aoCitar} />
                    </p>
                  )
                )}
              </div>
            </>
          )}

          {/* Nothing listed when nothing is cited (an article written without decisive evidence). */}
          {citacoes.length > 0 && (
            <>
              <h3 className="rubrica mt-14 border-b-2 border-divisor pb-3">{t("artigo.citada")}</h3>
              <ol>
                {porNoticia(citacoes).map(({ docId, citacoes: doGrupo }) => {
                  const primeira = doGrupo[0];
                  return (
                    <li key={docId}>
                      <button
                        type="button"
                        onClick={(evento) => aoCitar(primeira, evento.currentTarget)}
                        onMouseEnter={() => aoRealcar(docId)}
                        onMouseLeave={() => aoRealcar(null)}
                        onFocus={() => aoRealcar(docId)}
                        onBlur={() => aoRealcar(null)}
                        className="-mx-2 flex w-[calc(100%+16px)] gap-5 border-b border-regra px-2 py-4 text-left transition-colors hover:bg-pairar focus-visible:-outline-offset-2"
                      >
                        <span className="w-11 flex-none pt-0.5 text-[12px] font-semibold text-mudo tabular-nums">
                          {doGrupo.map((c) => c.marker).join(" · ")}
                        </span>
                        <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                          <span className="text-[15px] leading-[1.4]">{primeira.headline}</span>
                          <span className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-mudo">
                            <span>{dataCurta(primeira.published_at)}</span>
                            <span>{t("artigo.excertos", { count: doGrupo.length })}</span>
                            {/* Every relation the news item's passages have, not just the first's. */}
                            {ROTULOS.filter((r) => doGrupo.some((c) => c.label === r)).map((r) => (
                              <Rotulo key={r} rotulo={r} />
                            ))}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </>
          )}
        </>
      )}
    </Bloco>
  );
});

export default Artigo;
