/** Dates as the interface's language writes them. */

import i18n, { codigo } from "../i18n";
import { comoData } from "./datas";

/** "13 set 2022" / "13 Sep 2022": the month abbreviations are the interface's own, as some
    locales write a short month as a number ("13/09/2022"). */
export function dataCurta(valor) {
  const data = comoData(valor);
  if (!data) return valor ? String(valor).slice(0, 10) : "";
  const meses = i18n.t("eixo.meses", { returnObjects: true });
  return `${data.getDate()} ${meses[data.getMonth()]} ${data.getFullYear()}`;
}

/** "7 de maio de 2025" / "7 May 2025". */
export function dataLonga(valor) {
  const data = comoData(valor);
  if (!data) return valor ? String(valor).slice(0, 10) : "";
  return data.toLocaleDateString(codigo(), { day: "numeric", month: "long", year: "numeric" });
}

/** "7 de mai. de 2025, 14:32" / "7 May 2025, 14:32": a revision's time, with its date. */
export function dataHora(valor) {
  const data = comoData(valor);
  if (!data) return valor ? String(valor) : "";
  return new Intl.DateTimeFormat(codigo(), { dateStyle: "medium", timeStyle: "short" }).format(data);
}

/** A length of time as a reader says it, the same in both languages but for the decimal mark:
    "0,8 s", "12 s", "2 min 05 s", "1 h 02 min". */
export function duracao(ms) {
  const segundos = ms / 1000;
  if (segundos < 10) {
    return `${segundos.toLocaleString(codigo(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
  }
  const total = Math.round(segundos);
  if (total < 60) return `${total} s`;
  const minutos = Math.floor(total / 60);
  if (minutos < 60) return `${minutos} min ${String(total % 60).padStart(2, "0")} s`;
  return `${Math.floor(minutos / 60)} h ${String(minutos % 60).padStart(2, "0")} min`;
}
