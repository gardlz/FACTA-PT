import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** A popover that opens from a button, right under it, and moves left only as far as it takes to
    stay inside the page's column (`[data-coluna]`). Closes on Escape, giving the focus back to the
    button, and on a click outside `raiz`. `desvio` is the panel's left margin. */
export function useBalao() {
  const [aberto, setAberto] = useState(false);
  const raiz = useRef(null);
  const botao = useRef(null);
  const painel = useRef(null);
  const [desvio, setDesvio] = useState(0);

  // Opening under the button would run past the column's edge when the button sits far right.
  useLayoutEffect(() => {
    const no = painel.current;
    const coluna = raiz.current?.closest("[data-coluna]");
    if (!aberto || !no || !coluna) return;
    const limite = coluna.getBoundingClientRect().right - parseFloat(getComputedStyle(coluna).paddingRight);
    setDesvio(Math.min(0, limite - (no.getBoundingClientRect().right - desvio)));
  }, [aberto]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!aberto) return undefined;
    const fora = (evento) => !raiz.current?.contains(evento.target) && setAberto(false);
    const tecla = (evento) => {
      if (evento.key !== "Escape") return;
      setAberto(false);
      botao.current?.focus();
    };
    document.addEventListener("pointerdown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("pointerdown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto]);

  return { aberto, setAberto, raiz, botao, painel, desvio };
}
