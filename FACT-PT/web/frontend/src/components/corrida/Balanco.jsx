/** What the evidence decides: the passages supporting, refuting or deciding nothing, as three
    large counts. The tally is over passages, not news items: a news item with four supporting
    passages and one refuting counts four and one. With an editorial review, it counts the
    evidence the review keeps, and follows every edit. */

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { forwardRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { contagem, contagemDaRevisao } from "../../lib/evidencia";
import { SUAVE } from "../../lib/movimento";
import { ROTULOS, TOM_ROTULO } from "../../lib/tons";
import Bloco from "../Bloco";

/** A number that counts up to its value. */
function Contador({ valor }) {
  const reduzido = useReducedMotion();
  const corrente = useMotionValue(reduzido ? valor : 0);
  const inteiro = useTransform(corrente, (v) => Math.round(v));
  useEffect(() => {
    if (reduzido) {
      corrente.set(valor);
      return undefined;
    }
    const controlo = animate(corrente, valor, { duration: 0.9, ease: SUAVE });
    return () => controlo.stop();
  }, [valor, reduzido, corrente]);
  return <motion.span>{inteiro}</motion.span>;
}

const Balanco = forwardRef(function Balanco({ id, documentos, classificacao, evidencia, revista }, ref) {
  const { t } = useTranslation();
  // The review's evidence once there is one: it is what the timeline shows, and what a person
  // edits. Without a review (an example), the pipeline's own classification.
  const conta = evidencia ? contagemDaRevisao(evidencia) : contagem(documentos, classificacao);
  const total = conta.supported + conta.refuted + conta.nei;

  return (
    <Bloco ref={ref} id={id} titulo={t("bloco.balanco")}>
      <p className="mt-5 mb-1 text-[20px] leading-[1.4] tracking-[-.01em]">{t("balanco.total", { count: total })}</p>
      {evidencia && (
        <p className="mb-1 text-[12px] text-mudo">
          {t(revista ? "balanco.fonteRevista" : "balanco.fonteAutomatica")}
        </p>
      )}
      {/* One row at every width: on a phone the numbers and their labels shrink to fit. */}
      <div className="grid grid-cols-3">
        {ROTULOS.map((rotulo) => (
          <div key={rotulo} className="flex min-w-0 flex-col gap-2 border-b border-regra py-6 pr-5 max-sm:pr-3">
            <span className={`font-titulo text-[clamp(36px,11vw,56px)] leading-none font-extrabold tracking-[-.03em] tabular-nums ${TOM_ROTULO[rotulo].texto}`}>
              <Contador valor={conta[rotulo]} />
            </span>
            <span className="flex items-baseline gap-2 text-[14px] leading-[1.3] max-sm:text-[12px]">
              <span aria-hidden="true" className={`size-[9px] flex-none ${TOM_ROTULO[rotulo].fundo}`} />
              {t(`balanco.${rotulo}`)}
            </span>
          </div>
        ))}
      </div>
    </Bloco>
  );
});

export default Balanco;
