/** Backend calls: the example catalogue, a news item from a run, and the run itself. Each one
    names the interface's language, which the server's fixed messages follow. */

import { codigo } from "./i18n.js";

function cabecalhos(extra = {}) {
  return { "Accept-Language": codigo(), ...extra };
}

async function pedirJson(url) {
  const resposta = await fetch(url, { headers: cabecalhos() });
  if (!resposta.ok) {
    let detalhe = `HTTP ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (corpo && corpo.detail) detalhe = corpo.detail;
    } catch (erro) {
      void erro;
    }
    throw new Error(detalhe);
  }
  return resposta.json();
}

export function exemplos() {
  return pedirJson("/api/exemplos");
}

export function documento(runId, docId) {
  return pedirJson(`/api/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(docId)}`);
}

/** Runs the pipeline and hands over each event as it arrives. The response is a server-sent
    event stream, read with `fetch` because `EventSource` cannot send a POST. */
export async function executar(entrada, aoEvento, sinal) {
  const resposta = await fetch("/api/run", {
    method: "POST",
    headers: cabecalhos({ "Content-Type": "application/json" }),
    body: JSON.stringify(entrada),
    signal: sinal,
  });

  if (!resposta.ok) {
    let detalhe = `HTTP ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (Array.isArray(corpo.detail)) {
        detalhe = corpo.detail.map((d) => d.msg).join("; ");
      } else if (corpo.detail) {
        detalhe = corpo.detail;
      }
    } catch (erro) {
      void erro;
    }
    throw new Error(detalhe);
  }

  const leitor = resposta.body.getReader();
  const descodificador = new TextDecoder();
  let acumulado = "";

  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    acumulado += descodificador.decode(value, { stream: true });

    let corte = acumulado.indexOf("\n\n");
    while (corte !== -1) {
      const bruto = acumulado.slice(0, corte);
      acumulado = acumulado.slice(corte + 2);
      for (const linha of bruto.split("\n")) {
        if (!linha.startsWith("data:")) continue;
        const carga = linha.slice(5).trim();
        if (carga) aoEvento(JSON.parse(carga));
      }
      corte = acumulado.indexOf("\n\n");
    }
  }
}
