/** Scale of the evidence timeline: where it starts and ends, and the ruler ticks. */

import { DIA_MS } from "./datas";

/** Ruler grain from the span length (years above two years, months above ten weeks, else
    days), not from whether the dates cross a year boundary. */
function graoDoEixo(dias) {
  return dias > 730 ? "ano" : dias > 70 ? "mes" : "dia";
}

function recuarPara(data, grao) {
  if (grao === "ano") return new Date(data.getFullYear(), 0, 1);
  if (grao === "mes") return new Date(data.getFullYear(), data.getMonth(), 1);
  return new Date(data.getFullYear(), data.getMonth(), data.getDate());
}

/** The axis opens on the ruler tick just before the oldest news, so its left edge always has
    a label. */
export function inicioDoEixo(maisAntiga, fim) {
  let inicio = maisAntiga;
  // Moving the start back widens the span and may coarsen the grain (months to years), which
  // moves the start back again. The grain only gets coarser, so this settles in a few rounds.
  for (let volta = 0; volta < 3; volta += 1) {
    const seguinte = recuarPara(maisAntiga, graoDoEixo((fim - inicio) / DIA_MS));
    if (seguinte.getTime() === inicio.getTime()) return inicio;
    inicio = seguinte;
  }
  return inicio;
}

/** Ruler ticks from start to end at the span's grain, each at a 0-1 position. `tecto` is the
    most ticks that fit the track width; `meses` the month abbreviations. */
export function marcasDoEixo(inicio, fim, meses, tecto = 8) {
  const amplitude = Math.max(1, fim - inicio);
  const dias = amplitude / DIA_MS;
  const marcas = [];
  const juntar = (data, etiqueta) => {
    const pos = (data - inicio) / amplitude;
    if (pos >= 0 && pos <= 1) marcas.push({ pos, etiqueta });
  };

  if (dias > 730) {
    const primeiro = inicio.getFullYear();
    const ultimo = fim.getFullYear();
    const passo = Math.max(1, Math.ceil((ultimo - primeiro + 1) / tecto));
    for (let ano = primeiro; ano <= ultimo; ano += passo) juntar(new Date(ano, 0, 1), String(ano));
    return marcas.length ? marcas : [{ pos: 0, etiqueta: String(primeiro) }];
  }

  if (dias > 70) {
    const passo = Math.max(1, Math.ceil(Math.ceil(dias / 30.44) / tecto));
    const cursor = new Date(inicio.getFullYear(), inicio.getMonth(), 1);
    while (cursor <= fim) {
      const nome = meses[cursor.getMonth()];
      juntar(new Date(cursor), cursor.getFullYear() === fim.getFullYear() ? nome : `${nome} ${String(cursor.getFullYear()).slice(2)}`);
      cursor.setMonth(cursor.getMonth() + passo);
    }
    return marcas.length ? marcas : [{ pos: 0, etiqueta: meses[inicio.getMonth()] }];
  }

  const passo = Math.max(1, Math.ceil(Math.max(1, dias) / Math.min(6, tecto)));
  const cursor = new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate());
  while (cursor <= fim) {
    juntar(new Date(cursor), `${cursor.getDate()} ${meses[cursor.getMonth()]}`);
    cursor.setDate(cursor.getDate() + passo);
  }
  return marcas.length ? marcas : [{ pos: 0, etiqueta: `${inicio.getDate()} ${meses[inicio.getMonth()]}` }];
}

/** The level of each marker at `xs` (px, in ascending order) so that no two on one level are
    closer than `distancia`: each takes the first level with room, trying them in the order
    `ordem` gives (by default 0, 1, 2…). */
export function empilhar(xs, distancia, ordem = (i) => i) {
  const ultimos = new Map();
  return xs.map((x) => {
    for (let i = 0; ; i += 1) {
      const nivel = ordem(i);
      const ultimo = ultimos.get(nivel);
      if (ultimo === undefined || x - ultimo >= distancia) {
        ultimos.set(nivel, x);
        return nivel;
      }
    }
  });
}

/** 0, 1, -1, 2, -2…: levels on both sides of a line, nearest first. */
export function alternado(i) {
  return i % 2 ? (i + 1) / 2 : -i / 2;
}
