/** The start page's heading, with the word "claim" in the accent colour for a moment when the
    page loads, and for as long as the pointer is on it (the styling is `destaque`). */

import { useEffect, useRef } from "react";

const PALAVRA = /\b(claim)\b/i;
const FORA = { color: "var(--color-tinta)", backgroundSize: "0% 100%" };
const DENTRO = { color: "var(--color-destaque)", backgroundSize: "100% 100%" };
// Milliseconds the accent takes to sweep in and how long it stays.
const ENTRA = 700;
const FICA = 2500;
// How long it takes to fade out: the same as the pointer leaving (`destaque` in `index.css`).
const SAI_COR = 300;
const SAI_FUNDO = 500;

export default function Titulo({ texto }) {
  const palavra = useRef(null);

  // Sweeps in, holds, and fades out. Skipped for readers who asked for less motion.
  useEffect(() => {
    const no = palavra.current;
    if (!no?.animate || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    const total = ENTRA + FICA + SAI_FUNDO;
    const opcoes = { duration: total, delay: 350, fill: "backwards" };
    // The colour and the highlight leave on their own clocks, as they do on hover. The easing is
    // set per stretch (in, then out), since one on the whole animation would bend the timings.
    const saida = (propriedade, ms) => [
      { [propriedade]: FORA[propriedade], offset: 0, easing: "cubic-bezier(.2,.7,.3,1)" },
      { [propriedade]: DENTRO[propriedade], offset: ENTRA / total },
      { [propriedade]: DENTRO[propriedade], offset: (ENTRA + FICA) / total, easing: "ease" },
      { [propriedade]: FORA[propriedade], offset: (ENTRA + FICA + ms) / total },
      { [propriedade]: FORA[propriedade], offset: 1 },
    ];
    const animacoes = [no.animate(saida("color", SAI_COR), opcoes), no.animate(saida("backgroundSize", SAI_FUNDO), opcoes)];
    return () => animacoes.forEach((a) => a.cancel());
  }, []);

  const partes = texto.split(PALAVRA);
  return partes.map((parte, indice) =>
    indice % 2 ? (
      <span key={indice} ref={palavra} className="destaque">
        {parte}
      </span>
    ) : (
      parte
    )
  );
}
