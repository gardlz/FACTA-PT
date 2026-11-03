/** A "?" beside a section's heading that opens how to read the section, in a popover like "What is
    FACTA-PT?" (`useBalao`). `rotulo` names the button and the popover for screen readers. */

import { AnimatePresence, motion } from "framer-motion";
import { useId } from "react";
import { useBalao } from "../hooks/useBalao";
import { SUAVE } from "../lib/movimento";

export default function Ajuda({ rotulo, children }) {
  const { aberto, setAberto, raiz, botao, painel, desvio } = useBalao();
  const id = useId();

  return (
    <div ref={raiz} className="relative">
      <button
        ref={botao}
        type="button"
        aria-label={rotulo}
        aria-expanded={aberto}
        aria-controls={id}
        onClick={() => setAberto((a) => !a)}
        className="inline-flex size-6 items-center justify-center border border-divisor text-[13px] font-semibold transition-colors hover:bg-pairar aria-expanded:bg-tinta aria-expanded:text-fundo"
      >
        ?
      </button>
      <AnimatePresence>
        {aberto && (
          <motion.div
            ref={painel}
            id={id}
            role="region"
            aria-label={rotulo}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            style={{ marginLeft: desvio }}
            transition={{ duration: 0.18, ease: SUAVE }}
            className="absolute top-[calc(100%+8px)] left-0 z-20 w-[min(52ch,calc(100vw-2*var(--goteira)))] border-2 border-tinta bg-fundo p-5"
          >
            <p className="text-[15px] leading-[1.65] [text-wrap:pretty]">{children}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
