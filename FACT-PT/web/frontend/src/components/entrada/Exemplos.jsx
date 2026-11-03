/** The worked examples, under the form: a scrolling row of small cards, each claim opening its
    recorded verification. Called from the form (`chamada`), the row scrolls into view and the
    accent draws across the cards in view, the same accent as the title's word "claim". */

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useBalao } from "../../hooks/useBalao";
import { SUAVE } from "../../lib/movimento";
import { BOTAO_ICONE } from "../Barra";
import { Info } from "../Icones";

/** An example's verdict as recorded with `quantidade` news items per question; null when it was
    not recorded with that number. */
export function vereditoDe(exemplo, quantidade) {
  if (quantidade === null) return exemplo.veracity || null;
  return (exemplo.veredictos || {})[String(quantidade)] || null;
}

// Milliseconds the accent takes to draw across a card, how long it stays, how long it takes to
// fade, and how far behind its neighbour each card starts.
const ENTRA = 450;
const FICA = 900;
const SAI = 500;
const PASSO = 70;
// How long a smooth scroll is given to land where `scrollend` is not supported.
const ROLAGEM = 900;

/** Lights up the heading and, left to right, the cards in view that can be picked. Returns the
    animations, to cancel. */
function realcar(titulo, pista) {
  const total = ENTRA + FICA + SAI;
  const curva = (de, para) => [
    { ...de, offset: 0, easing: "cubic-bezier(.2,.7,.3,1)" },
    { ...para, offset: ENTRA / total },
    { ...para, offset: (ENTRA + FICA) / total, easing: "ease" },
    { ...de, offset: 1 },
  ];
  const vista = pista.getBoundingClientRect();
  const cartoes = [...pista.querySelectorAll("button:not(:disabled)")].filter((c) => {
    const r = c.getBoundingClientRect();
    return r.right > vista.left + 1 && r.left < vista.right - 1;
  });
  const animacoes = [titulo.animate(curva({ color: "var(--color-tinta)" }, { color: "var(--color-destaque)" }), { duration: total + PASSO * cartoes.length })];
  cartoes.forEach((cartao, indice) => {
    const opcoes = { duration: total, delay: indice * PASSO };
    // The rule draws in from the left, so the row reads as one line being drawn; then both fade.
    const traco = [
      { transform: "scaleX(0)", opacity: 1, offset: 0, easing: "cubic-bezier(.2,.7,.3,1)" },
      { transform: "scaleX(1)", opacity: 1, offset: ENTRA / total },
      { transform: "scaleX(1)", opacity: 1, offset: (ENTRA + FICA) / total, easing: "ease" },
      { transform: "scaleX(1)", opacity: 0, offset: 1 },
    ];
    animacoes.push(cartao.querySelector("[data-traco]").animate(traco, opcoes));
    animacoes.push(cartao.querySelector("[data-banho]").animate(curva({ opacity: 0 }, { opacity: 1 }), opcoes));
  });
  return animacoes;
}

export default function Exemplos({ exemplos, quantidade, aoEscolher, chamada }) {
  const { t } = useTranslation();
  const { aberto, setAberto, raiz, botao, painel, desvio } = useBalao();
  const idNota = useId();
  const seccao = useRef(null);
  const titulo = useRef(null);
  const pista = useRef(null);

  // Scrolls to the row, then lights it once it has landed: on `scrollend`, or straight away when
  // the row was already in place and nothing scrolled. Readers who asked for less motion only jump.
  useEffect(() => {
    if (!chamada) return undefined;
    const reduzir = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const antes = window.scrollY;
    seccao.current.scrollIntoView({ behavior: reduzir ? "auto" : "smooth", block: "start" });
    if (reduzir || !titulo.current.animate) return undefined;

    let animacoes = [];
    let espera = null;
    const tocar = () => {
      window.removeEventListener("scrollend", tocar);
      clearTimeout(espera);
      animacoes.forEach((a) => a.cancel());
      animacoes = realcar(titulo.current, pista.current);
    };
    const quadro = requestAnimationFrame(() => {
      if (window.scrollY === antes) return tocar();
      window.addEventListener("scrollend", tocar);
      espera = setTimeout(tocar, "onscrollend" in window ? ROLAGEM * 2 : ROLAGEM);
    });
    return () => {
      cancelAnimationFrame(quadro);
      window.removeEventListener("scrollend", tocar);
      clearTimeout(espera);
      animacoes.forEach((a) => a.cancel());
    };
  }, [chamada]);

  return (
    <section ref={seccao} id="exemplos" className="mt-8 scroll-mt-[calc(var(--barra-altura)+24px)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-divisor pb-2.5">
        <h2 ref={titulo} className="rubrica">{t("casos.titulo")}</h2>
        <div className="flex items-center gap-3">
          <span className="hidden text-[12px] text-mudo sm:inline">{t("casos.pista")}</span>
          <div ref={raiz} className="relative">
            <button
              ref={botao}
              type="button"
              aria-label={t("casos.sobre")}
              aria-expanded={aberto}
              aria-controls={idNota}
              onClick={() => setAberto((a) => !a)}
              className={`${BOTAO_ICONE} aria-expanded:bg-tinta aria-expanded:text-fundo`}
            >
              <Info className="size-4" />
            </button>
            <AnimatePresence>
              {aberto && (
                <motion.div
                  ref={painel}
                  id={idNota}
                  role="region"
                  aria-label={t("casos.sobre")}
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  style={{ marginLeft: desvio }}
                  transition={{ duration: 0.18, ease: SUAVE }}
                  className="absolute top-[calc(100%+8px)] left-0 z-20 w-[min(52ch,calc(100vw-2*var(--goteira)))] border-2 border-tinta bg-fundo p-5"
                >
                  <p className="text-[15px] leading-[1.65] [text-wrap:pretty]">{t("casos.nota")}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      <div ref={pista} className="sem-barra mt-4 flex snap-x snap-mandatory overflow-x-auto scroll-smooth border-l border-divisor">
        {exemplos.map((exemplo) => {
          // An example not recorded with the chosen number cannot be picked with it: its run would
          // be the models' instead.
          const gravado = vereditoDe(exemplo, quantidade) !== null;
          return (
            <button
              key={exemplo.id}
              type="button"
              disabled={!gravado}
              title={gravado ? exemplo.claim : t("casos.semGravacao", { n: quantidade })}
              onClick={() => aoEscolher(exemplo)}
              className="relative flex min-h-[104px] flex-[0_0_max(25%,190px)] snap-start flex-col border-t-2 border-r border-b border-t-tinta border-r-divisor border-b-divisor px-4 py-3.5 text-left transition-colors hover:bg-pairar focus-visible:-outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
            >
              {/* Hidden at rest: what `realcar` lights up, over the card's top rule and its face. */}
              <span data-traco aria-hidden="true" className="pointer-events-none absolute -top-0.5 left-0 -right-px h-0.5 origin-left bg-destaque opacity-0" />
              <span data-banho aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[color-mix(in_srgb,var(--color-destaque)_9%,transparent)] opacity-0" />
              <span className="relative line-clamp-3 text-[14.5px] leading-[1.4] [text-wrap:pretty]">«{exemplo.claim}»</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
