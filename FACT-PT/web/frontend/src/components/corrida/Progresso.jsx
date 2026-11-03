/** The run's row at the top of a verification: the four steps as columns, each with a small
    drawing of what it does and a rule that fills as it works, then the verdict, the last to arrive.
    The sections under it appear as the steps end. */

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { duracaoDosPassos, estadoDosPassos } from "../../hooks/useCorrida";
import { duracao } from "../../lib/formato";
import { SUAVE } from "../../lib/movimento";
import { TOM_VEREDITO } from "../../lib/tons";
import { Avancar } from "../Icones";
import Ilustracao from "./Ilustracao";

/** What a finished step found, in one line. */
function feito(t, id, estado) {
  if (id === "perguntas") return t("passo.perguntas.feito", { count: estado.perguntas?.length || 0 });
  if (id === "evidencia") {
    const recuperadas = estado.relevancia ? estado.relevancia["notícias"] : estado.recuperados.length;
    return t("passo.evidencia.feito", { count: recuperadas, n: estado.documentos?.length || 0 });
  }
  if (id === "classificacao") return t("passo.classificacao.feito", { count: estado.classificacao?.stances.length || 0 });
  return estado.artigo?.model ? t("passo.artigo.feito", { modelo: estado.artigo.model }) : "";
}

/** A step's name: large for the one at work (and for the verdict, once it lands), small for the
    rest, growing and shrinking as the run moves along. */
const NOME = "font-titulo leading-[1.2] font-extrabold tracking-[-.01em] [text-wrap:balance] transition-[font-size] duration-300 ease-out";
const NOME_GRANDE = "text-[clamp(20px,2.1vw,25px)]";
const NOME_PEQUENO = "text-[16px]";

/** How each step's rule moves while an example plays back: quick then slow, steady, in bursts. */
const CURVA = {
  perguntas: "cubic-bezier(.2,.8,.4,1)",
  evidencia: "cubic-bezier(.45,.05,.55,.95)",
  classificacao: "cubic-bezier(.6,.1,.3,.9)",
  artigo: "cubic-bezier(.3,.5,.6,.95)",
};

/** How far a step's rule is filled, and how it gets there. It only ever grows: a played-back
    example fills it over the step's set time (`ritmo`); a real step's length is unknown, so its
    rule eases towards the end and waits there; a finished step fills the rest and stays full. */
function enchimento(id, situacao, ritmo) {
  if (situacao === "done" || situacao === "error") return { width: "100%", transition: "width .3s ease-out" };
  if (situacao === "running") {
    return ritmo
      ? { width: "100%", transition: `width ${ritmo[id]}ms ${CURVA[id]}` }
      : { width: "88%", transition: "width 40s cubic-bezier(.05,.7,.2,1)" };
  }
  return { width: "0%" };
}

/** Milliseconds since the step began running, ticking each second; 0 while it is not running. */
function useDecorrido(emCurso) {
  const [ms, setMs] = useState(0);
  useEffect(() => {
    if (!emCurso) return undefined;
    const inicio = performance.now();
    const relogio = setInterval(() => setMs(performance.now() - inicio), 1000);
    return () => clearInterval(relogio);
  }, [emCurso]);
  return emCurso ? ms : 0;
}

function Passo({ passo, numero, estado, motivo, duracaoMs }) {
  const { t } = useTranslation();
  const situacao = passo.estado;
  const pendente = situacao === "pending" || situacao === "skipped";
  // A played-back example runs for seconds on a staged pace: no time is shown for it.
  const decorrido = useDecorrido(situacao === "running" && !estado.ritmo);
  const tempo = situacao === "done" && duracaoMs != null ? duracao(duracaoMs) : decorrido >= 1000 ? duracao(decorrido) : "";
  const sinal = [situacao === "done" ? "✓" : t(`passo.estado.${situacao}`), tempo].filter(Boolean).join(" · ");
  const detalhe =
    situacao === "running" ? t(`passo.${passo.id}.trabalho`) : situacao === "done" ? feito(t, passo.id, estado) : situacao === "error" ? motivo || t("passo.falhou") : "";
  return (
    <li className={`relative flex flex-col gap-2 border-t-2 border-regra pt-3 pb-6 transition-opacity duration-400 ${pendente ? "opacity-35" : ""}`}>
      <span
        aria-hidden="true"
        className={`absolute -top-0.5 left-0 h-0.5 ${situacao === "error" ? "bg-contraria" : "bg-tinta"}`}
        style={enchimento(passo.id, situacao, estado.ritmo)}
      />
      <div className="pt-3 pb-4">
        <Ilustracao id={passo.id} estado={situacao} />
      </div>
      <div className="flex justify-between gap-2 text-[12px] text-mudo tabular-nums">
        <span>{String(numero).padStart(2, "0")}</span>
        <span className={situacao === "error" ? "text-contraria" : ""}>{sinal}</span>
      </div>
      <span className={`${NOME} ${situacao === "running" ? NOME_GRANDE : NOME_PEQUENO}`}>
        {t(`passo.${passo.id}.nome`)}
      </span>
      <span className={`min-h-[2.9em] text-[14px] leading-[1.45] [text-wrap:pretty] ${situacao === "error" ? "text-contraria" : "text-mudo"}`}>{detalhe}</span>
    </li>
  );
}

/** Each verdict's mark, drawn stroke by stroke inside its square: a tick, a cross, a question
    and a search that came back empty. Paths on a 24 × 24 grid; `ponto` is a dot drawn after them. */
const MARCA = {
  supported: { tracos: ["M5 12.5l4.5 4.5L19 7.5"] },
  refuted: { tracos: ["M6.5 6.5l11 11", "M17.5 6.5l-11 11"] },
  nei: { tracos: ["M8.8 9.2a3.2 3.2 0 1 1 4.8 2.8c-1 .6-1.6 1.3-1.6 2.4v.6"], ponto: [12, 18.6] },
  nei_sem_evidencia: { tracos: ["M15.2 15.2L20 20", "M10.5 5a5.5 5.5 0 1 0 0 11a5.5 5.5 0 1 0 0-11"] },
};

function Marca({ veredito }) {
  const { tracos, ponto } = MARCA[veredito] || MARCA.nei_sem_evidencia;
  // After the square lands; each stroke follows the one before.
  const inicio = 0.5;
  const passo = 0.22;
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="relative size-6 text-fundo">
      {tracos.map((d, i) => (
        <motion.path
          key={d}
          d={d}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.6"
          strokeLinecap="square"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.32, ease: SUAVE, delay: inicio + i * passo }}
        />
      ))}
      {ponto && (
        <motion.rect
          x={ponto[0] - 1.4}
          y={ponto[1] - 1.4}
          width="2.8"
          height="2.8"
          fill="currentColor"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 500, damping: 16, delay: inicio + tracos.length * passo + 0.1 }}
        />
      )}
    </svg>
  );
}

/** The verdict, as the row's last column: dim until the excerpts are weighed, waiting while the
    article is written, then landing in its colour once the run ends. */
function Desfecho({ veredito, conhecido, aguarda }) {
  const { t } = useTranslation();
  const tom = TOM_VEREDITO[veredito] || TOM_VEREDITO.nei_sem_evidencia;
  const sinal = conhecido ? "✓" : t(`passo.estado.${aguarda ? "running" : "pending"}`);
  return (
    <li
      className={`relative col-span-2 flex flex-col gap-2 border-t-2 border-regra pt-3 pb-6 transition-opacity duration-400 md:col-span-1 ${
        conhecido || aguarda ? "" : "opacity-35"
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute -top-0.5 left-0 h-0.5 ${conhecido ? tom.fundo : "bg-tinta"}`}
        style={{ width: conhecido ? "100%" : "0%", transition: "width .7s cubic-bezier(.2,.7,.3,1)" }}
      />
      <div aria-hidden="true" className="flex h-[92px] items-center pt-3 pb-4">
        <span className="relative grid size-12 place-items-center border-2 border-pendente">
          {aguarda && !conhecido && <span className="size-5 animate-pulse bg-pendente" />}
          <AnimatePresence>
            {conhecido && (
              <>
                <motion.span
                  key="cor"
                  className={`absolute -inset-0.5 grid place-items-center ${tom.fundo}`}
                  initial={{ scale: 0.2, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 420, damping: 18, delay: 0.25 }}
                >
                  <Marca veredito={veredito} />
                </motion.span>
                <motion.span
                  key="onda"
                  className={`absolute -inset-0.5 border-2 ${tom.borda}`}
                  initial={{ scale: 1, opacity: 0.8 }}
                  animate={{ scale: 2.2, opacity: 0 }}
                  transition={{ duration: 0.9, ease: SUAVE, delay: 0.4 }}
                />
              </>
            )}
          </AnimatePresence>
        </span>
      </div>
      <div className="flex justify-between gap-2 text-[12px] text-mudo tabular-nums">
        <span>{t("corrida.veredito")}</span>
        <span>{sinal}</span>
      </div>
      {conhecido ? (
        <>
          <motion.span
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: SUAVE, delay: 0.35 }}
            className={`${NOME} ${NOME_GRANDE} ${tom.texto}`}
          >
            {t(`veredito.${veredito}.nome`)}
          </motion.span>
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.45, delay: 0.6 }}
            className="text-[14px] leading-[1.45] text-mudo [text-wrap:pretty]"
          >
            {t(`veredito.${veredito}.nota`)}
          </motion.span>
        </>
      ) : (
        <span className={`${NOME} ${NOME_PEQUENO} text-pendente`}>…</span>
      )}
    </li>
  );
}

/** `veredito` is the example's recorded verdict, or the one a new claim's own evidence gives
    (`vereditoDaEvidencia`), null until the classification is in: the column waits, dim, until
    then, so the row always ends where the run does. */
export default function Progresso({ estado, ocupado, veredito, aoCancelar }) {
  const { t } = useTranslation();
  const passos = estadoDosPassos(estado.estados);
  const duracoes = duracaoDosPassos(estado.duracoes);
  const emCurso = passos.find((passo) => passo.estado === "running");
  const medidos = Object.values(duracoes).filter((ms) => ms != null);
  const total = medidos.reduce((soma, ms) => soma + ms, 0);
  const conhecido = Boolean(veredito && estado.classificacao && !ocupado);
  const aguarda = Boolean(veredito && estado.classificacao && ocupado);
  const anuncio = conhecido ? t(`veredito.${veredito}.nome`) : emCurso ? t(`passo.${emCurso.id}.trabalho`) : "";
  return (
    <div className="flex flex-col gap-3">
      <section aria-label={t("corrida.passos")} className="flex flex-col gap-4 border-y-2 border-divisor pt-4">
        <div className="flex min-h-[30px] flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <span className="text-[12px] tracking-[.08em] text-mudo uppercase tabular-nums">
            {ocupado ? t("corrida.aVerificar") : medidos.length > 0 ? `${t("corrida.tempoTotal")} · ${duracao(total)}` : ""}
          </span>
          {ocupado && aoCancelar && (
            <button type="button" onClick={aoCancelar} className="p-1 text-[14px] font-semibold text-mudo transition-colors hover:text-contraria">
              {t("corrida.cancelar")}
            </button>
          )}
        </div>
        {estado.fila !== null && (
          <p role="status" className="text-[14px] text-mudo">{t("corrida.fila", { count: estado.fila })}</p>
        )}
        <ol className="grid grid-cols-2 gap-x-5 md:grid-cols-[repeat(4,minmax(0,1fr))_minmax(0,1.3fr)]">
          {passos.map((passo, indice) => (
            <Passo key={passo.id} passo={passo} numero={indice + 1} estado={estado} motivo={estado.motivos[passo.id]} duracaoMs={duracoes[passo.id]} />
          ))}
          <Desfecho veredito={veredito} conhecido={conhecido} aguarda={aguarda} />
        </ol>
        <p role="status" className="sr-only">{anuncio}</p>
      </section>
      {/* The row says one line per step; what each step produced is in the sections under it. */}
      <p className="inline-flex items-center gap-1.5 text-[13px] text-mudo">
        {t("corrida.maisPassos")}
        <Avancar aria-hidden="true" className="size-3.5 rotate-90" />
      </p>
    </div>
  );
}
