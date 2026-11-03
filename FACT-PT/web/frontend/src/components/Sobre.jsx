/** The About page: what the project is, how it works, the models behind it, its limits and who
    built it. */

import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { EQUIPA, INSTITUICOES, MODELOS } from "../lib/sobre";
import { SURGIR } from "../lib/movimento";
import Ilustracao from "./corrida/Ilustracao";

const PASSOS = ["perguntas", "evidencia", "classificacao", "artigo"];

// The grids of the page (steps, models, people, institutions) and their items, all alike: a rule
// under each item, a small uppercase label, a name, and a quieter line.
const GRELHA = "mt-6 grid grid-cols-[repeat(auto-fit,minmax(min(100%,220px),1fr))] gap-x-5 gap-y-6";
const ITEM = "flex flex-col gap-1 border-b border-divisor pb-4";
const ROTULO = "text-[12px] font-semibold tracking-[.08em] text-mudo uppercase";
const NOME = "font-titulo text-[18px] leading-[1.25] font-extrabold tracking-[-.01em] [text-wrap:balance]";
const DETALHE = "text-[14px] leading-[1.5] text-mudo [text-wrap:pretty]";
const LIGACAO = "w-fit underline decoration-1 underline-offset-3 hover:decoration-2";

/** A section: the uppercase heading over its 2px rule, as in a verification's result. */
function Seccao({ titulo, children }) {
  return (
    <section className="mt-16">
      <h2 className="rubrica border-b-2 border-divisor pb-3">{titulo}</h2>
      {children}
    </section>
  );
}

/** One step of "how it works": its drawing sits finished, and loops while the pointer is on the
    step (always finished for readers who asked for less motion). */
function Passo({ id, numero }) {
  const { t } = useTranslation();
  const reduzir = useReducedMotion();
  const [sobre, setSobre] = useState(false);
  return (
    <li
      onPointerEnter={() => setSobre(true)}
      onPointerLeave={() => setSobre(false)}
      className={ITEM}
    >
      <div className="pb-4">
        <Ilustracao id={id} estado={sobre && !reduzir ? "running" : "done"} />
      </div>
      <span className={`${ROTULO} tabular-nums`}>{String(numero).padStart(2, "0")}</span>
      <span className={NOME}>{t(`passo.${id}.nome`)}</span>
      <span className={DETALHE}>{t(`sobre.funciona.passos.${id}`)}</span>
    </li>
  );
}

export default function Sobre() {
  const { t } = useTranslation();
  const sigla = (id) => INSTITUICOES.find((i) => i.id === id)?.sigla;
  return (
    <motion.div {...SURGIR} className="pt-[clamp(40px,8vw,96px)]">
      <h1 className="mb-5 text-[clamp(40px,7vw,76px)] leading-none tracking-[-.035em] [text-wrap:balance]">{t("sobre.titulo")}</h1>
      <p className="text-[19px] leading-[1.6] text-mudo [text-wrap:pretty]">{t("sobre.nota")}</p>

      <Seccao titulo={t("sobre.consiste.titulo")}>
        {/* The same text as the start page's "What is FACTA-PT?". */}
        <p className="mt-6 text-[17px] leading-[1.7] [text-wrap:pretty]">{t("pagina.descricao")}</p>
      </Seccao>

      <Seccao titulo={t("sobre.funciona.titulo")}>
        <ol className={GRELHA}>
          {PASSOS.map((id, indice) => (
            <Passo key={id} id={id} numero={indice + 1} />
          ))}
        </ol>
      </Seccao>

      <Seccao titulo={t("sobre.modelos.titulo")}>
        <p className="mt-6 text-[16px] leading-[1.7] text-mudo [text-wrap:pretty]">
          {t("sobre.modelos.nota")}
        </p>

        <ul className={GRELHA}>
          {Object.entries(
            MODELOS.reduce((grupos, modelo) => {
              ;(grupos[modelo.tarefa] ??= []).push(modelo)
              return grupos
            }, {})
          ).map(([tarefa, modelos]) => (
            <li key={tarefa} className={ITEM}>
              <span className={ROTULO}>{t(`sobre.modelos.tarefas.${tarefa}`)}</span>
              {modelos.map(({ nome, url }) => (
                <a key={url} href={url} target="_blank" rel="noreferrer" className={`${NOME} ${LIGACAO} break-words`}>
                  {nome}
                </a>
              ))}
            </li>
          ))}
        </ul>
      </Seccao>

      <Seccao titulo={t("sobre.limites.titulo")}>
        <p className="mt-6 border-l-2 border-indeciso pl-4 text-[16px] leading-[1.7] [text-wrap:pretty]">{t("sobre.limites.texto")}</p>
      </Seccao>

      <Seccao titulo={t("sobre.equipa.titulo")}>
        <ul className={GRELHA}>
          {EQUIPA.map(({ nome, papel, instituicoes }) => (
            <li key={nome} className={ITEM}>
              <span className={ROTULO}>{t(`sobre.papeis.${papel}`)}</span>
              <span className={NOME}>{nome}</span>
              <span className={DETALHE}>{instituicoes.map(sigla).filter(Boolean).join(" · ")}</span>
            </li>
          ))}
        </ul>
      </Seccao>

      <Seccao titulo={t("sobre.instituicoes.titulo")}>
        <ul className={GRELHA}>
          {INSTITUICOES.map(({ id, sigla, nome, url }) => (
            <li key={id} className={ITEM}>
              {url ? (
                <a href={url} target="_blank" rel="noreferrer" className={`${NOME} ${LIGACAO}`}>{sigla}</a>
              ) : (
                <span className={NOME}>{sigla}</span>
              )}
              <span className={DETALHE}>{nome}</span>
            </li>
          ))}
        </ul>
      </Seccao>
    </motion.div>
  );
}
