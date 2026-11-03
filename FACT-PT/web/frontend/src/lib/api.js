/** Backend calls: the session, the example catalogue, a news item from a run, and the run itself.
    Each one names the interface's language, which the server's fixed messages follow. */

import { codigo } from "../i18n";

function cabecalhos(extra = {}) {
  return { "Accept-Language": codigo(), ...extra };
}

/** Sent on `window` when the server refuses a request for want of a session (it expired, or the
    password changed), so the shell goes back to the sign-in page. */
export const SESSAO_PERDIDA = "facta-pt:sessao-perdida";

/** A refused request, with the HTTP status and the seconds to wait that the server gave. */
export class ErroHttp extends Error {
  constructor(mensagem, estado, espera = 0) {
    super(mensagem);
    this.estado = estado;
    this.espera = espera;
  }
}

async function erroDe(resposta) {
  if (resposta.status === 401) window.dispatchEvent(new Event(SESSAO_PERDIDA));
  return new ErroHttp(await detalheDoErro(resposta), resposta.status, Number(resposta.headers.get("Retry-After")) || 0);
}

async function detalheDoErro(resposta) {
  try {
    const corpo = await resposta.json();
    if (Array.isArray(corpo.detail)) return corpo.detail.map((d) => d.msg).join("; ");
    if (corpo.detail) return corpo.detail;
  } catch {
    // Not JSON: the status says enough.
  }
  return `HTTP ${resposta.status}`;
}

async function pedirJson(url) {
  const resposta = await fetch(url, { headers: cabecalhos() });
  if (!resposta.ok) throw await erroDe(resposta);
  return resposta.json();
}

/** Whether this browser holds a session: `{ autenticada, protegido, utilizador, permissoes }`. */
export function sessao() {
  return pedirJson("/api/sessao");
}

/** Signs in with an account. Wrong credentials are a 401 `ErroHttp`, too many attempts a 429; it
    must not send `SESSAO_PERDIDA`, since there is no session to lose. */
export async function entrar(utilizador, palavraPasse) {
  const resposta = await fetch("/api/sessao", {
    method: "POST",
    headers: cabecalhos({ "Content-Type": "application/json" }),
    body: JSON.stringify({ utilizador, palavra_passe: palavraPasse }),
  });
  if (!resposta.ok) throw new ErroHttp(await detalheDoErro(resposta), resposta.status, Number(resposta.headers.get("Retry-After")) || 0);
}

export function sair() {
  return fetch("/api/sessao", { method: "DELETE", headers: cabecalhos() });
}

async function enviarJson(url, metodo, corpo, manter = false) {
  const resposta = await fetch(url, {
    method: metodo,
    headers: cabecalhos({ "Content-Type": "application/json" }),
    body: JSON.stringify(corpo),
    ...(manter ? { keepalive: true } : {}),
  });
  if (!resposta.ok) {
    const copia = resposta.clone();
    const erro = await erroDe(resposta);
    // A 409 carries the review as it is now, so the page can show the conflict.
    if (resposta.status === 409) erro.corpo = await copia.json().catch(() => null);
    throw erro;
  }
  return resposta.json();
}

export function exemplos() {
  return pedirJson("/api/exemplos");
}

/** What the models a run uses are doing - the three every run needs and the writer chosen, the
    server's default when there is none: `{ disponivel, modelos: [{ id, estado, detalhe, na_gpu }] }`. */
export function modelos(redator = "") {
  return pedirJson(`/api/modelos${redator ? `?redator=${encodeURIComponent(redator)}` : ""}`);
}

/** A finished verification, as the events its run sent: `{ run_id, guardada_em, input, eventos }`.
    A 404 `ErroHttp` when there is none - never finished, or no longer kept. */
export async function verificacao(runId, sinal) {
  const resposta = await fetch(`/api/verificacoes/${encodeURIComponent(runId)}`, { headers: cabecalhos(), signal: sinal });
  if (!resposta.ok) throw await erroDe(resposta);
  return resposta.json();
}

export function documento(runId, docId) {
  return pedirJson(`/api/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(docId)}`);
}

// After a connection breaks: attempts in a row that bring nothing back before giving up, and the
// longest wait between two. A stream that brought something counts as reconnected, however soon
// it broke: Firefox cuts a stream about every 100 seconds, keep-alives notwithstanding, and a run
// takes hours on a laptop.
const RECONEXOES = 10;
const ESPERA_MAXIMA = 10000;

/** Waits `ms`, or rejects at once if `sinal` aborts. */
function pausa(ms, sinal) {
  return new Promise((resolver, rejeitar) => {
    const abortar = () => {
      clearTimeout(relogio);
      rejeitar(new DOMException("Aborted", "AbortError"));
    };
    const relogio = setTimeout(() => {
      sinal.removeEventListener("abort", abortar);
      resolver();
    }, ms);
    if (sinal.aborted) abortar();
    else sinal.addEventListener("abort", abortar, { once: true });
  });
}

/** Reads one event stream to its end, handing over each event and noting in `estado` the id of
    the last one (`id:`, the server's stream id), how many came (`recebidos`) and whether the run
    is over (the closing `fim`). */
async function lerEventos(resposta, aoEvento, estado) {
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
        // Lines starting with ":" are the server's keep-alive comments.
        if (linha.startsWith("id:")) estado.ultimo = linha.slice(3).trim() || estado.ultimo;
        if (!linha.startsWith("data:")) continue;
        const carga = linha.slice(5).trim();
        if (!carga) continue;
        const evento = JSON.parse(carga);
        estado.recebidos += 1;
        if (evento.type === "fim") estado.fim = true;
        else aoEvento(evento);
      }
      corte = acumulado.indexOf("\n\n");
    }
  }
}

/** Reads the run's events from the last one seen (`estado.ultimo`) to its end, again as many
    times as the connection breaks: browsers drop long streams. `falhas` is how many attempts in a
    row have already failed; `agora`, the first attempt goes at once (nothing has broken yet). */
async function seguir(estado, aoEvento, sinal, falhas = 0, ultimoErro = null, agora = false) {
  let primeira = agora;
  while (!estado.fim) {
    if (falhas > RECONEXOES) throw ultimoErro;
    if (!primeira) await pausa(Math.min(500 * 2 ** falhas, ESPERA_MAXIMA), sinal);
    primeira = false;
    let retoma;
    try {
      retoma = await fetch(`/api/runs/${encodeURIComponent(estado.runId)}/eventos?desde=${encodeURIComponent(estado.ultimo)}`, {
        headers: cabecalhos(),
        signal: sinal,
      });
    } catch (e) {
      if (sinal.aborted) throw e;
      falhas += 1;
      ultimoErro = e;
      continue;
    }
    // The run is gone (expired) or the session is: nothing to reconnect to.
    if (!retoma.ok) throw await erroDe(retoma);
    const antes = estado.recebidos;
    try {
      await lerEventos(retoma, aoEvento, estado);
      falhas = 0;
    } catch (e) {
      if (sinal.aborted) throw e;
      // The server answered (its first event says so): this break is a new one, not another
      // failed attempt.
      falhas = estado.recebidos > antes ? 1 : falhas + 1;
      ultimoErro = e;
    }
  }
}

/** Runs the pipeline and hands over each event as it arrives. The response is a server-sent
    event stream, read with `fetch` because `EventSource` cannot send a POST. A run that uses the
    models waits its turn in the server's queue (`queue` events say how many are ahead) and goes on
    there whatever happens to the connection: when it breaks, the run's events are read again from
    the last one seen (`seguir`). */
export async function executar(entrada, aoEvento, sinal) {
  const resposta = await fetch("/api/run", {
    method: "POST",
    headers: cabecalhos({ "Content-Type": "application/json" }),
    body: JSON.stringify(entrada),
    signal: sinal,
  });
  if (!resposta.ok) throw await erroDe(resposta);

  const estado = { runId: null, ultimo: "0", fim: false, recebidos: 0 };
  const entregar = (evento) => {
    // The first event already names the run: it may wait in the queue before it starts.
    if (evento.run_id) estado.runId = evento.run_id;
    aoEvento(evento);
  };
  let falhas = 0;
  let ultimoErro = null;
  try {
    await lerEventos(resposta, entregar, estado);
  } catch (e) {
    if (sinal.aborted || !estado.runId) throw e;
    falhas = 1;
    ultimoErro = e;
  }
  await seguir(estado, entregar, sinal, falhas, ultimoErro);
}

/** Follows a run already under way from its first event: one in the background, opened again
    by its account, from this page or another. */
export async function acompanhar(runId, aoEvento, sinal) {
  await seguir({ runId, ultimo: "0", fim: false, recebidos: 0 }, aoEvento, sinal, 0, null, true);
}

/** The account's runs in the background of the last day: `{ execucoes: [...] }`. */
export function execucoes() {
  return pedirJson("/api/execucoes");
}

/** Asks again for a run of the account that stopped without a verification: the same request, in
    the queue under a new id, `{ run_id }`, which replaces the old run in the list. */
export function reiniciar(runId) {
  return enviarJson(`/api/execucoes/${encodeURIComponent(runId)}/reiniciar`, "POST", {});
}

/** One run in the background: what was asked and how far it got. 404 when it is not the
    account's, or is gone. */
export function execucao(runId) {
  return pedirJson(`/api/execucoes/${encodeURIComponent(runId)}`);
}

/** Cancels a run under way. Sent with `keepalive`, so that it still goes out when the page is
    closing. */
export function cancelar(runId) {
  fetch(`/api/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
    headers: cabecalhos(),
    keepalive: true,
  }).catch(() => {});
}

/** The editorial review of a saved verification: the automated state, the current one and every
    revision. A 404 `ErroHttp` when the verification was not kept (it has no review). */
export function revisao(runId) {
  return pedirJson(`/api/verificacoes/${encodeURIComponent(runId)}/revisao`);
}

/** One saved version in full (0 is the automated one): `{ versao, estado }`. */
export function versaoRevisao(runId, versao) {
  return pedirJson(`/api/verificacoes/${encodeURIComponent(runId)}/revisao/versoes/${versao}`);
}

/** Saves the draft as a new version. `corpo` is `{ versao, estado, restaurada_de? }`. A 409
    carries the current review in `erro.corpo.revisao`. */
export function guardarRevisao(runId, corpo) {
  return enviarJson(`/api/verificacoes/${encodeURIComponent(runId)}/revisao`, "PATCH", corpo);
}

/** Asks the server to write the article again from the saved evidence; `corpo` is
    `{ versao, redator? }`. The worker's progress
    comes back in the review's `pedido`; the page polls `revisao` while it waits. */
export function reescreverArtigo(runId, corpo) {
  return enviarJson(`/api/verificacoes/${encodeURIComponent(runId)}/revisao/artigo`, "POST", corpo);
}

// ---- Administration --------------------------------------------------------------------------

export function utilizadores() {
  return pedirJson("/api/admin/utilizadores");
}

export function criarUtilizador(corpo) {
  return enviarJson("/api/admin/utilizadores", "POST", corpo);
}

export function actualizarUtilizador(id, corpo) {
  return enviarJson(`/api/admin/utilizadores/${encodeURIComponent(id)}`, "PATCH", corpo);
}

export async function apagarUtilizador(id) {
  const resposta = await fetch(`/api/admin/utilizadores/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: cabecalhos(),
  });
  if (!resposta.ok) throw await erroDe(resposta);
}

export function plataforma() {
  return pedirJson("/api/admin/plataforma");
}

export function guardarPlataforma(corpo) {
  return enviarJson("/api/admin/plataforma", "PATCH", corpo);
}
