/** Interface language: European Portuguese (default) or British English. Only the interface is
    translated; the questions, news items and articles keep the language they come in.

    The i18next languages are the full codes (`pt-PT`, `en-GB`): they are also `<html lang>`,
    the `Accept-Language` sent to the API and the locale dates are written in, and plurals follow
    them (plain `pt` would take Brazilian rules, where 0 is singular). */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enGB from "./en-GB.json";
import ptPT from "./pt-PT.json";

const CHAVE = "facta-pt:lingua";

/** What the switch offers, by the short name kept in storage. */
export const LINGUAS = [
  { sigla: "pt", codigo: "pt-PT", nome: "Português" },
  { sigla: "en", codigo: "en-GB", nome: "English" },
];

function guardada() {
  try {
    const sigla = localStorage.getItem(CHAVE);
    return (LINGUAS.find((l) => l.sigla === sigla) || LINGUAS[0]).codigo;
  } catch {
    return LINGUAS[0].codigo;
  }
}

function aplicarNaPagina(codigo) {
  document.documentElement.lang = codigo;
  document.title = i18n.t("pagina.titulo");
  const descricao = document.querySelector('meta[name="description"]');
  if (descricao) descricao.setAttribute("content", i18n.t("pagina.descricao"));
}

i18n.use(initReactI18next).init({
  resources: { "pt-PT": { translation: ptPT }, "en-GB": { translation: enGB } },
  lng: guardada(),
  fallbackLng: "pt-PT",
  supportedLngs: LINGUAS.map((l) => l.codigo),
  // React already escapes what it renders.
  interpolation: { escapeValue: false },
  returnNull: false,
});

aplicarNaPagina(i18n.language);

i18n.on("languageChanged", (codigo) => {
  aplicarNaPagina(codigo);
  const lingua = LINGUAS.find((l) => l.codigo === codigo);
  try {
    if (lingua) localStorage.setItem(CHAVE, lingua.sigla);
  } catch {
    // Not fatal: the choice just lasts until the page is reloaded.
  }
});

/** `pt-PT` or `en-GB`, for code outside React (API headers, number and date formats). */
export function codigo() {
  return i18n.resolvedLanguage || i18n.language || LINGUAS[0].codigo;
}

export default i18n;
