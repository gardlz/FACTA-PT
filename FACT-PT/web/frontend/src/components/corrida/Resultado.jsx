/** The verification: the claim, its date and its context, then a rail of sections beside the
    questions, the evidence timeline, the tally and the article, each appearing as its step ends.
    The row of steps ending in the verdict is temporarily hidden (`MOSTRAR_PIPELINE`), and the
    verdict stands in a band under the context meanwhile. */

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { estadoDosPassos } from "../../hooks/useCorrida";
import { useBalao } from "../../hooks/useBalao";
import { useLargura } from "../../hooks/useLargura";
import { vereditoDaRevisao } from "../../lib/evidencia";
import { dataLonga } from "../../lib/formato";
import { SUAVE, SURGIR } from "../../lib/movimento";
import { TOM_VEREDITO, VEREDITOS } from "../../lib/tons";
import { Anunciadas } from "../Bloco";
import { Avancar, Lapis, Recuar } from "../Icones";
import BarraRevisao from "./BarraRevisao";
import Progresso from "./Progresso";

// The row of steps above the sections, temporarily out of the page: the sections announce
// themselves while they are written (their title, their drawing) and the section rail spins
// beside the one under way. Put it back by flipping this to `true`.
const MOSTRAR_PIPELINE = false;

/** The verdict of the draft, for an editor: the band's verdict is a button, and it opens the
    choices in place - following the evidence (and what it gives now), or one set by hand. */
function EscolhaVeredito({ veredito, revisao, className, children }) {
  const { t } = useTranslation();
  const { aberto, setAberto, raiz, botao, painel, desvio } = useBalao();
  const id = useId();
  const manual = revisao.estado?.veredito_manual || null;
  const daEvidencia = revisao.estado
    ? vereditoDaRevisao({ ...revisao.estado, veredito_manual: null })
    : veredito;
  const escolher = (valor) => {
    revisao.mudarVeredito(valor);
    setAberto(false);
  };
  const opcao = (valor, rotulo, nota) => (
    <li key={valor ?? "evidencia"}>
      <button
        type="button"
        role="menuitemradio"
        aria-checked={manual === valor}
        onClick={() => escolher(valor)}
        className="flex w-full items-center gap-3 px-3 py-2 text-left text-[14px] hover:bg-pairar aria-checked:font-semibold"
      >
        <span aria-hidden="true" className={`size-3 flex-none ${TOM_VEREDITO[valor ?? daEvidencia]?.fundo || "bg-mudo"}`} />
        <span className="flex flex-col">
          {rotulo}
          {nota && <span className="text-[12px] font-normal text-mudo">{nota}</span>}
        </span>
      </button>
    </li>
  );
  return (
    <span ref={raiz} className="relative">
      <button
        ref={botao}
        type="button"
        aria-haspopup="menu"
        aria-expanded={aberto}
        aria-controls={id}
        title={t("revisao.mudarVeredito")}
        onClick={() => setAberto((a) => !a)}
        className={`inline-flex items-center gap-2 underline decoration-regra decoration-2 underline-offset-[6px] hover:decoration-current ${className}`}
      >
        {children}
        {/* Says it can be changed: an arrow alone does not. */}
        <span className="inline-flex items-center gap-1 font-sans text-[13px] leading-none font-semibold tracking-normal text-mudo">
          <Lapis aria-hidden="true" className="size-4" />
          {t("revisao.alterar")}
        </span>
      </button>
      <AnimatePresence>
        {aberto && (
          <motion.ul
            ref={painel}
            id={id}
            role="menu"
            aria-label={t("revisao.veredito")}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            style={{ marginLeft: desvio }}
            transition={{ duration: 0.18, ease: SUAVE }}
            className="absolute top-[calc(100%+10px)] left-0 z-30 w-[min(320px,calc(100vw-2*var(--goteira)))] border-2 border-tinta bg-fundo py-1 font-sans"
          >
            {opcao(null, t("revisao.seguirEvidenciaDa", { veredito: t(`veredito.${daEvidencia}.nome`) }), t("revisao.automaticoNota"))}
            <li role="presentation" className="mt-1 border-t border-regra px-3 pt-2 pb-1 text-[11px] tracking-[.06em] text-mudo uppercase">
              {t("revisao.aMao")}
            </li>
            {VEREDITOS.map((valor) => opcao(valor, t(`veredito.${valor}.nome`)))}
          </motion.ul>
        )}
      </AnimatePresence>
    </span>
  );
}

/** The verdict band under the claim, standing in for the step row's last column while that row
    is hidden: what is being done while the run has no verdict yet, then the verdict, once the
    classification gives it, and the run's note on it. The verdict follows the evidence; an editor
    may set it by hand from the band itself. When a person revised it, the line under the band
    says who and at which version. */
function Veredito({ veredito, estado, ocupado, revisao, revisaoEditada, autor, versao }) {
  const { t } = useTranslation();
  const conhecido = veredito && estado.classificacao;
  if (!conhecido && !ocupado) return null;
  const emCurso = estadoDosPassos(estado.estados).find((passo) => passo.estado === "running");
  const tom = conhecido ? TOM_VEREDITO[veredito] || TOM_VEREDITO.nei_sem_evidencia : null;
  return (
    <div className="flex flex-col gap-3">
      <section id="sec-veredito" aria-live="polite" className="flex flex-wrap items-center gap-x-5 gap-y-3 border-y-2 border-divisor py-6">
        <span aria-hidden="true" className={`size-5 flex-none transition-colors duration-300 ${tom ? tom.fundo : "bg-pendente"}`} />
        {conhecido && revisao?.podeEditar && revisao.estado ? (
          <EscolhaVeredito
            veredito={veredito}
            revisao={revisao}
            className={`font-titulo text-[clamp(28px,3.4vw,40px)] leading-none font-extrabold tracking-[-.02em] ${tom.texto}`}
          >
            {t(`veredito.${veredito}.nome`)}
          </EscolhaVeredito>
        ) : (
          <span className={`font-titulo text-[clamp(28px,3.4vw,40px)] leading-none font-extrabold tracking-[-.02em] ${tom ? tom.texto : "text-pendente"}`}>
            {conhecido ? t(`veredito.${veredito}.nome`) : t("corrida.aVerificar")}
          </span>
        )}
        <span className="flex-[1_1_260px] text-[15px] text-mudo">
          {conhecido ? t(`veredito.${veredito}.nota`) : emCurso ? t(`passo.${emCurso.id}.trabalho`) : ""}
        </span>
      </section>
      {/* Who stands behind the verdict: the pipeline, or a person's review. */}
      {conhecido && revisao?.estado && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-mudo">
          <span>
            {revisao.estado.veredito_manual ? t("revisao.vereditoManual") : t("revisao.vereditoAutomatico")}
            {revisaoEditada && ` · ${t("corrida.revistoPor", { autor: autor?.nome || autor?.utilizador || "" })}`}
            {revisaoEditada && versao ? ` · v${versao}` : ""}
          </span>
          {revisao.estado.veredito_manual && revisao.podeEditar && (
            <button
              type="button"
              onClick={() => revisao.mudarVeredito(null)}
              className="py-0.5 font-semibold text-tinta underline underline-offset-3 hover:text-mudo"
            >
              {t("revisao.voltarAutomatico")}
            </button>
          )}
        </p>
      )}
      {/* As under the step row: what each step produced is in the sections below. */}
      <p className="inline-flex items-center gap-1.5 text-[13px] text-mudo">
        {t("corrida.maisPassos")}
        <Avancar aria-hidden="true" className="size-3.5 rotate-90" />
      </p>
    </div>
  );
}

// How far below the top of the window a section's heading must have scrolled to be the one
// being read: past the top bar, the review bar under it, and the gap the rail scrolls to (`ir`).
const LINHA_DE_LEITURA = 180;

/** The id of the section being read, among `ids` (those on the page, in order): the last one
    whose top has scrolled past the reading line, the first while none has, and the last once the
    page is scrolled to its end, where a short last section may never reach the line. */
function useSeccaoActual(ids) {
  const [actual, setActual] = useState(ids[0] ?? null);
  const chave = ids.join(" ");
  useEffect(() => {
    const lista = chave ? chave.split(" ") : [];
    let quadro = 0;
    const medir = () => {
      quadro = 0;
      const nos = lista.map((id) => document.getElementById(id)).filter(Boolean);
      if (!nos.length) return setActual(null);
      const noFim = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      const passadas = nos.filter((no) => no.getBoundingClientRect().top <= LINHA_DE_LEITURA);
      setActual((noFim ? nos.at(-1) : passadas.at(-1) || nos[0]).id);
    };
    const pedir = () => {
      if (!quadro) quadro = requestAnimationFrame(medir);
    };
    medir();
    window.addEventListener("scroll", pedir, { passive: true });
    window.addEventListener("resize", pedir);
    return () => {
      cancelAnimationFrame(quadro);
      window.removeEventListener("scroll", pedir);
      window.removeEventListener("resize", pedir);
    };
  }, [chave]);
  return actual;
}

/** `seccoes` are `{ id, rotulo, pronta, curso }`: a section not yet arrived cannot be jumped to,
    and while its step runs it shows a spinner at its end. The one being read is marked as the
    reader scrolls. */
function Carril({ seccoes }) {
  const { t } = useTranslation();
  const actual = useSeccaoActual(seccoes.filter((s) => s.pronta).map((s) => s.id));
  const ir = (id) => {
    const no = document.getElementById(id);
    if (no) window.scrollTo({ top: no.getBoundingClientRect().top + window.scrollY - 128, behavior: "smooth" });
  };
  return (
    <nav aria-label={t("corrida.seccoes")} className="flex flex-[0_0_180px] flex-col border-t-2 border-divisor md:sticky md:top-36 max-md:flex-auto max-md:basis-full">
      {seccoes.map(({ id, rotulo, pronta, curso }, indice) => {
        const aqui = pronta && id === actual;
        return (
          <button
            key={id}
            type="button"
            disabled={!pronta}
            aria-current={aqui ? "location" : undefined}
            aria-busy={curso && !pronta ? true : undefined}
            onClick={() => ir(id)}
            className={`relative flex items-baseline gap-3 border-b border-regra py-3 text-left text-[14px] underline-offset-3 transition-[padding,color] duration-200 hover:underline disabled:cursor-default disabled:opacity-40 disabled:hover:no-underline ${
              aqui ? "pl-3 font-semibold" : "pl-0"
            }`}
          >
            <span
              aria-hidden="true"
              className={`absolute inset-y-2 left-0 w-0.5 bg-tinta transition-transform duration-200 ${aqui ? "scale-y-100" : "scale-y-0"}`}
            />
            <span className={`text-[11px] tabular-nums ${aqui ? "text-tinta" : "text-mudo"}`}>{String(indice + 1).padStart(2, "0")}</span>
            <span className="leading-[1.35] [text-wrap:balance]">{rotulo}</span>
            {curso && !pronta && (
              <span
                aria-hidden="true"
                className="ml-auto size-3.5 flex-none animate-spin self-center rounded-full border-2 border-regra border-t-tinta motion-reduce:animate-none"
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}

/** The context the claim was made in, with the claim marked where it stands in it. A long one
    shows its first lines (`line-clamp-3`), and the rest when the reader asks. */
function Contexto({ texto, claim }) {
  const { t } = useTranslation();
  const caixa = useRef(null);
  const largura = useLargura(caixa);
  const [aberto, setAberto] = useState(false);
  // Whether the clamp hides anything: measured while clamped, again whenever the width changes.
  const [cortado, setCortado] = useState(false);
  useLayoutEffect(() => {
    const no = caixa.current;
    if (no && !aberto) setCortado(no.scrollHeight > no.clientHeight + 1);
  }, [texto, largura, aberto]);

  const inicio = claim ? texto.indexOf(claim) : -1;
  return (
    <div className="mt-8">
      <div className="mb-2 text-[12px] tracking-[.08em] text-mudo uppercase">{t("form.contexto")}</div>
      <p ref={caixa} className={`text-[16px] leading-[1.6] whitespace-pre-line text-mudo [text-wrap:pretty] ${aberto ? "" : "line-clamp-3"}`}>
        {inicio < 0 ? (
          texto
        ) : (
          <>
            {texto.slice(0, inicio)}
            <span className="marcado text-tinta">{claim}</span>
            {texto.slice(inicio + claim.length)}
          </>
        )}
      </p>
      {(cortado || aberto) && (
        <button
          type="button"
          aria-expanded={aberto}
          onClick={() => setAberto((antes) => !antes)}
          className="mt-2 py-1 text-[14px] font-semibold underline underline-offset-3"
        >
          {t(aberto ? "corrida.contextoMenos" : "corrida.contextoTodo")}
        </button>
      )}
    </div>
  );
}

/** Copies the address of the verification, once the server has kept it (`runId`): the button is
    not there before, as there is nothing to share yet. */
function CopiarLigacao() {
  const { t } = useTranslation();
  const [copiada, setCopiada] = useState(false);
  useEffect(() => {
    if (!copiada) return undefined;
    const relogio = setTimeout(() => setCopiada(false), 2000);
    return () => clearTimeout(relogio);
  }, [copiada]);
  const copiar = () => {
    navigator.clipboard
      .writeText(window.location.href)
      .then(() => setCopiada(true))
      // No clipboard (an insecure page, a refusal): the address is in the bar to be copied.
      .catch(() => {});
  };
  return (
    <button type="button" onClick={copiar} className="px-1 py-1.5 text-[14px] font-semibold text-mudo transition-colors hover:text-tinta">
      <span role="status">{t(copiada ? "corrida.ligacaoCopiada" : "corrida.copiarLigacao")}</span>
    </button>
  );
}

export default function Resultado({ claim, data, contexto, veredito, revisao, revisaoEditada, autorRevisao, versaoRevisao, estado, ocupado, aoCancelar, erro, seccoes, guardada, children }) {
  const { t } = useTranslation();
  // Resultado is remounted for every run, so this starts empty each time.
  const anunciadas = useRef(new Set());
  return (
    <motion.div {...SURGIR} className="pt-6">
      <div className="flex items-center justify-between gap-4">
        <Link to="/" className="-ml-1 inline-flex items-center gap-1.5 px-1 py-1.5 font-titulo text-[14px] font-extrabold text-tinta no-underline hover:bg-pairar">
          <Recuar className="size-4" />
          {t("corrida.nova")}
        </Link>
        {guardada && <CopiarLigacao />}
      </div>

      <section className="pt-12 pb-10">
        <div className="mb-4 text-[12px] tracking-[.08em] text-mudo uppercase">
          {t("form.claim")}
          {data && ` · ${dataLonga(data)}`}
        </div>
        <p className="text-[clamp(26px,3.8vw,44px)] leading-[1.18] tracking-[-.02em] [text-wrap:pretty]">
          «<span className="marcado">{claim}</span>»
        </p>
        {contexto && <Contexto texto={contexto} claim={claim} />}
      </section>

      {MOSTRAR_PIPELINE ? (
        <Progresso estado={estado} ocupado={ocupado} veredito={veredito} aoCancelar={aoCancelar} />
      ) : (
        <>
          <Veredito
            veredito={veredito}
            estado={estado}
            ocupado={ocupado}
            revisao={revisao}
            revisaoEditada={revisaoEditada}
            autor={autorRevisao}
            versao={versaoRevisao}
          />
          <BarraRevisao revisao={revisao} />
        </>
      )}

      {/* The step row carried the cancel button; while it is hidden, a run can still be stopped
          from where the row used to be. */}
      {!MOSTRAR_PIPELINE && aoCancelar && (
        <div className="mt-6 flex justify-end">
          <button type="button" onClick={aoCancelar} className="p-1 text-[14px] font-semibold text-mudo transition-colors hover:text-contraria">
            {t("corrida.cancelar")}
          </button>
        </div>
      )}

      {erro && (
        <p role="alert" className="mt-6 flex items-center gap-2 text-[14px] text-contraria">
          <span aria-hidden="true" className="size-2 flex-none bg-contraria" />
          {erro}
        </p>
      )}

      <div className="mt-14 flex flex-wrap items-start gap-x-16 gap-y-10">
        <Carril seccoes={seccoes} />
        <Anunciadas.Provider value={anunciadas}>
          <div className="flex min-w-0 flex-[1_1_560px] flex-col gap-[72px]">{children}</div>
        </Anunciadas.Provider>
      </div>
    </motion.div>
  );
}
