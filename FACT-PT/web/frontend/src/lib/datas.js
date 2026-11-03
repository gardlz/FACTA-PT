/** Calendar-day arithmetic in local time. Dates travel as `YYYY-MM-DD`. */

export const DIA_MS = 86400000;

export function iso(data) {
  const mes = String(data.getMonth() + 1).padStart(2, "0");
  const dia = String(data.getDate()).padStart(2, "0");
  return `${data.getFullYear()}-${mes}-${dia}`;
}

/** `YYYY-MM-DD` -> local Date, or null. Impossible dates are rejected: the Date constructor
    silently rolls them over (31 February becomes a day in March). */
export function deIso(texto) {
  const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(texto || ""));
  if (!partes) return null;
  const ano = Number(partes[1]);
  const mes = Number(partes[2]) - 1;
  const dia = Number(partes[3]);
  const data = new Date(ano, mes, dia);
  if (data.getFullYear() !== ano || data.getMonth() !== mes || data.getDate() !== dia) return null;
  return data;
}

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

/** Weekday index with Monday first, as in the Portuguese and British calendars. */
export function diaDaSemana(data) {
  return (data.getDay() + 6) % 7;
}

export function ultimoDiaDoMes(ano, mes) {
  return new Date(ano, mes + 1, 0).getDate();
}

/** Same date in another month, without overflowing: 31 January + 1 month is 28 or 29 February. */
export function deslocarMeses(data, meses) {
  const alvo = new Date(data.getFullYear(), data.getMonth() + meses, 1);
  const dia = Math.min(data.getDate(), ultimoDiaDoMes(alvo.getFullYear(), alvo.getMonth()));
  return new Date(alvo.getFullYear(), alvo.getMonth(), dia);
}

export function mesmoDia(a, b) {
  return Boolean(
    a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  );
}
