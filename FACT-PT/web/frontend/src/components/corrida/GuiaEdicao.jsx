/** A tip for an editor, under the review bar: the four things a review lets them change, each
    taking them to its section. It can be hidden, and comes back from the "?" button in the bar;
    whether it was hidden is remembered in this browser only, and the page works without it. */

import { useTranslation } from "react-i18next";
import { Fechar, Lapis } from "../Icones";

export const CHAVE_GUIA = "facta-pt:guia-edicao-escondida";

export function guiaEscondida() {
  try {
    return localStorage.getItem(CHAVE_GUIA) === "1";
  } catch {
    return false;
  }
}

export function lembrarGuia(escondida) {
  try {
    if (escondida) localStorage.setItem(CHAVE_GUIA, "1");
    else localStorage.removeItem(CHAVE_GUIA);
  } catch {
    // Storage unavailable: the tip just shows again next time.
  }
}

/** Scrolls to a section, below the top bar and the review bar (as the section rail does). */
export function irParaSeccao(id) {
  const no = document.getElementById(id);
  if (no) window.scrollTo({ top: no.getBoundingClientRect().top + window.scrollY - 128, behavior: "smooth" });
}

const ITENS = [
  { chave: "eixo", seccao: "sec-eixo" },
  { chave: "gaveta", seccao: "sec-eixo" },
  { chave: "veredito", seccao: "sec-veredito" },
  { chave: "artigo", seccao: "sec-artigo" },
];

export default function GuiaEdicao({ aoFechar }) {
  const { t } = useTranslation();
  return (
    <section aria-label={t("revisao.guia.titulo")} className="mb-2 grid gap-2 border-l-2 border-tinta bg-superficie px-4 py-3 text-[13px]">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 font-semibold">
          <Lapis className="size-4" />
          {t("revisao.guia.titulo")}
        </p>
        <button
          type="button"
          onClick={aoFechar}
          aria-label={t("revisao.guia.fechar")}
          title={t("revisao.guia.fechar")}
          className="p-1 text-mudo hover:text-tinta"
        >
          <Fechar className="size-3.5" />
        </button>
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-1">
        {ITENS.map(({ chave, seccao }) => (
          <li key={chave}>
            <button type="button" onClick={() => irParaSeccao(seccao)} className="py-0.5 text-left underline underline-offset-3 hover:text-mudo">
              {t(`revisao.guia.itens.${chave}`)}
            </button>
          </li>
        ))}
      </ul>
      <p className="text-mudo">{t("revisao.guia.nota")}</p>
    </section>
  );
}
