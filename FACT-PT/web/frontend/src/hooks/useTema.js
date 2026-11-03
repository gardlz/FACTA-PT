/** Light or dark theme, following the system until the reader picks one. */

import { useCallback, useEffect, useState } from "react";

const CHAVE = "facta-pt:tema";

function escuroAgora() {
  const atual = document.documentElement.dataset.theme;
  return atual === "dark" || (atual !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

/** `[escuro, alternar]`: whether the page is dark now, and the switch. */
export function useTema() {
  const [escuro, setEscuro] = useState(escuroAgora);

  // While the reader has not picked one, the theme follows the system as it changes.
  useEffect(() => {
    const consulta = window.matchMedia("(prefers-color-scheme: dark)");
    const mudou = () => setEscuro(escuroAgora());
    consulta.addEventListener("change", mudou);
    return () => consulta.removeEventListener("change", mudou);
  }, []);

  const alternar = useCallback(() => {
    const tema = escuroAgora() ? "light" : "dark";
    document.documentElement.dataset.theme = tema;
    setEscuro(tema === "dark");
    try {
      localStorage.setItem(CHAVE, tema);
    } catch {
      // Not fatal: the choice just lasts until the page is reloaded.
    }
  }, []);

  return [escuro, alternar];
}
