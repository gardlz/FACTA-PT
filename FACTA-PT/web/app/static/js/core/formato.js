/** Wording and formatting shared by the view and the document drawer. */

import { el } from "./dom.js";
import { deIso } from "./calendario.js";
import { codigo, t } from "./i18n.js";

/** What a relation is called next to a citation: "Apoia", "Contraria", "Não decide". */
export function nomeRotulo(rotulo) {
  return t(`rotulo.${rotulo}`, {}, rotulo);
}

const MARCADOR = /\[\[C:(\d+):([^\]]+)\]\]/g;

/** Parses a date as a local calendar day: `new Date("YYYY-MM-DD")` reads it as UTC midnight,
    which shows as the previous day west of Greenwich. */
export function comoData(valor) {
  if (!valor) return null;
  const texto = String(valor);
  const local = deIso(texto.slice(0, 10));
  if (local && texto.length <= 10) return local;
  const data = new Date(texto);
  return Number.isNaN(data.getTime()) ? null : data;
}

export function dataCurta(iso) {
  const data = comoData(iso);
  if (!data) return iso ? String(iso).slice(0, 10) : "";
  return data.toLocaleDateString(codigo(), { day: "2-digit", month: "short", year: "numeric" });
}

export function dataLonga(iso) {
  const data = comoData(iso);
  if (!data) return iso ? String(iso).slice(0, 10) : "";
  return data.toLocaleDateString(codigo(), { day: "2-digit", month: "long", year: "numeric" });
}

/** Turns an article block into nodes, each `[[C:<n>:<excerpt id>]]` marker becoming a
    citation button. */
export function comCitacoes(texto, citacoes, aoCitar) {
  const fragmento = document.createDocumentFragment();
  let posicao = 0;
  MARCADOR.lastIndex = 0;
  let encontro = MARCADOR.exec(texto);
  while (encontro !== null) {
    if (encontro.index > posicao) {
      fragmento.append(document.createTextNode(texto.slice(posicao, encontro.index)));
    }
    const numero = encontro[1];
    const citacao = citacoes.find((c) => c.excerpt_id === encontro[2]);
    const marca = el("button", "cite", numero);
    marca.type = "button";
    marca.dataset.label = citacao ? citacao.label : "nei";
    marca.setAttribute(
      "aria-label",
      citacao ? t("citacao.comTitulo", { n: numero, titulo: citacao.headline }) : t("citacao.semTitulo", { n: numero })
    );
    marca.addEventListener("click", () => aoCitar(citacao, marca));
    fragmento.append(marca);
    posicao = encontro.index + encontro[0].length;
    encontro = MARCADOR.exec(texto);
  }
  if (posicao < texto.length) fragmento.append(document.createTextNode(texto.slice(posicao)));
  return fragmento;
}

