/** "What is FACTA-PT?": the project's description, kept out of the way in a popover that opens
    from a button beside the title (`useBalao`). Closes also when the link to the About page is
    followed. */

import { AnimatePresence, motion } from "framer-motion";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useBalao } from "../../hooks/useBalao";
import { SUAVE } from "../../lib/movimento";
import { Avancar, Info } from "../Icones";

export default function Descricao() {
  const { t } = useTranslation();
  const { aberto, setAberto, raiz, botao, painel, desvio } = useBalao();
  const id = useId();

  return (
    <div ref={raiz} className="relative md:ml-auto">
      <button
        ref={botao}
        type="button"
        aria-expanded={aberto}
        aria-controls={id}
        onClick={() => setAberto((a) => !a)}
        className="inline-flex items-center gap-2 border border-divisor px-3 py-2 text-[14px] transition-colors hover:bg-pairar aria-expanded:bg-tinta aria-expanded:text-fundo"
      >
        <Info className="size-4" />
        {t("entrada.oQueE")}
      </button>
      <AnimatePresence>
        {aberto && (
          <motion.div
            ref={painel}
            id={id}
            role="region"
            aria-label={t("entrada.oQueE")}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            style={{ marginLeft: desvio }}
            transition={{ duration: 0.18, ease: SUAVE }}
            className="absolute top-[calc(100%+8px)] left-0 z-20 flex w-[min(62ch,calc(100vw-2*var(--goteira)))] flex-col gap-4 border-2 border-tinta bg-fundo p-5"
          >
            <p className="text-[15px] leading-[1.65] [text-wrap:pretty]">{t("pagina.descricao")}</p>
            <p className="text-[15px] leading-[1.65] [text-wrap:pretty]">{t("pagina.comoUsar")}</p>
            <Link to="/sobre" className="inline-flex w-fit items-center gap-1.5 text-[14px] font-semibold underline underline-offset-3">
              {t("entrada.maisSobre")}
              <Avancar className="size-4" />
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
