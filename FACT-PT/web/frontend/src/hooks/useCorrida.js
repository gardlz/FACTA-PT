/** One pipeline run: streams its events into state, cancels the previous run when a new one
    starts, and fetches (and caches) the news items it cited. A run in the background (`fundo`,
    the account's `segundo_plano`) is never cancelled by the page: leaving it, closing it or
    starting another leaves it running, and `retomar` follows it again from its first event. */

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import * as api from "../lib/api";
import { comoData } from "../lib/datas";

/** The seven pipeline stages grouped into the four steps that mean something to a reader. A
    step's name and the line shown while it runs are `passo.<id>.nome` and `passo.<id>.trabalho`. */
export const PASSOS = [
  { id: "perguntas", etapas: ["questions"] },
  // Relevance is part of retrieval: it decides which retrieved news count as evidence.
  { id: "evidencia", etapas: ["retrieval", "dedup", "relevance"] },
  { id: "classificacao", etapas: ["excerpts", "stance"] },
  { id: "artigo", etapas: ["article"] },
];

const INICIAL = {
  // Bumped on every new run, so the page can react to a run starting.
  geracao: 0,
  visivel: false,
  // While a stored example is played back at a run's pace: how long each step takes, in ms, by
  // step id (see `RITMO`). Null for a real run.
  ritmo: null,
  dataDaClaim: null,
  estados: {},
  // How long each finished stage took, in ms, by stage name. A stored example has none: its
  // playback is staged, so any time would be made up.
  duracoes: {},
  motivos: {},
  perguntas: null,
  // Everything retrieved, and the part of it that counts as evidence (what the relevance stage
  // did not rule unrelated): null until that stage ends. The timeline and the tally show only
  // the evidence.
  recuperados: [],
  documentos: null,
  // The relevance stage's counts (`notícias`, `relevantes`, `percentagem`), when it ran.
  relevancia: null,
  classificacao: null,
  artigo: null,
  // Every article the run came with (a stored example has one per model, the chosen one first);
  // `artigo` is the first.
  artigos: [],
  // While the run waits in the server's queue: how many runs are ahead of it. Null otherwise.
  fila: null,
};

function passoDe(etapa) {
  return PASSOS.find((passo) => passo.etapas.includes(etapa));
}

function aplicarEvento(estado, evento) {
  if (evento.type === "queue") return { ...estado, fila: evento.ahead ?? null };
  if (evento.type !== "stage") return estado;
  const etapa = evento.stage;
  const novo = { ...estado, fila: null, estados: { ...estado.estados, [etapa.name]: etapa.status } };
  if (etapa.status === "done" && etapa.duration_ms != null) {
    novo.duracoes = { ...estado.duracoes, [etapa.name]: etapa.duration_ms };
  }
  if (etapa.status === "error") {
    const passo = passoDe(etapa.name);
    if (passo) novo.motivos = { ...estado.motivos, [passo.id]: etapa.detail };
  }
  if (evento.questions && evento.questions.length) novo.perguntas = evento.questions;
  if (evento.documents && evento.documents.length) novo.recuperados = evento.documents;
  // If the relevance stage was skipped or failed, nothing is left out.
  if (etapa.name === "relevance" && ["done", "skipped", "error"].includes(etapa.status)) {
    novo.documentos = novo.recuperados.filter((documento) => documento.relevant !== false);
    novo.relevancia = etapa.status === "done" && etapa.stats ? etapa.stats : null;
  }
  if (evento.stances) novo.classificacao = { stances: evento.stances, decisivos: evento.decisive || [] };
  // A run writes the article with the model it chose: one article. A stored example brings one
  // per model, the chosen model's first.
  if (evento.articles && evento.articles.length) {
    novo.artigos = evento.articles;
    novo.artigo = evento.articles[0];
  }
  return novo;
}

function reduzir(estado, accao) {
  if (accao.tipo === "preparar") {
    return { ...INICIAL, geracao: estado.geracao + 1, visivel: true, ritmo: accao.ritmo, dataDaClaim: accao.dataDaClaim };
  }
  if (accao.tipo === "evento") return aplicarEvento(estado, accao.evento);
  return estado;
}

/** Each step's state from its stages': skipped only if all its stages were, done once every
    stage is done or skipped, running from its first stage until then. */
export function estadoDosPassos(estados) {
  return PASSOS.map((passo) => {
    const situacoes = passo.etapas.map((etapa) => estados[etapa] || "pending");
    let estado = "pending";
    if (situacoes.includes("error")) estado = "error";
    else if (situacoes.includes("running")) estado = "running";
    else if (situacoes.includes("done")) {
      // Some stages done and the rest still to come: the step is under way, between two stages.
      estado = situacoes.every((s) => s === "done" || s === "skipped") ? "done" : "running";
    } else if (situacoes.every((s) => s === "skipped")) estado = "skipped";
    return { ...passo, estado };
  });
}

/** How long each step took, in ms, by step id: the sum of its stages'. Null for a step with no
    time to report (not run, skipped, or an example). */
export function duracaoDosPassos(duracoes) {
  return Object.fromEntries(
    PASSOS.map((passo) => {
      const medidas = passo.etapas.map((etapa) => duracoes[etapa]).filter((ms) => ms != null);
      return [passo.id, medidas.length ? medidas.reduce((soma, ms) => soma + ms, 0) : null];
    })
  );
}

/** A stored example comes back at once, every stage already done. It is played back at the pace
    of a run, each step for about this long (ms), split among its stages: writing the article
    takes longest, as it does for the models. */
const RITMO = { perguntas: 2100, evidencia: 2800, classificacao: 2400, artigo: 3800 };
// Each playback varies every step by up to this much either way, so no two look alike.
const VARIACAO = 0.2;

function ritmoAoAcaso() {
  return Object.fromEntries(Object.entries(RITMO).map(([id, ms]) => [id, Math.round(ms * (1 - VARIACAO + 2 * VARIACAO * Math.random()))]));
}

/** Waits `ms`, or less if `sinal` aborts. */
function esperar(ms, sinal) {
  return new Promise((resolver) => {
    const fim = () => {
      clearTimeout(relogio);
      sinal.removeEventListener("abort", fim);
      resolver();
    };
    const relogio = setTimeout(fim, ms);
    sinal.addEventListener("abort", fim);
  });
}

/** `aoGuardar(runId)` is called when a run that ended is kept by the server: from then on the
    verification has an address of its own. `aoNomear(runId)`, when the server names a run in the
    background, which has its address from then on. */
export function useCorrida(aoErro, aoGuardar, { fundo = false, aoNomear } = {}) {
  const [estado, despachar] = useReducer(reduzir, INICIAL);
  const [ocupado, setOcupado] = useState(false);
  // Whether the run under way can be cancelled: a real one, named by the server, not yet over.
  const [cancelavel, setCancelavel] = useState(false);
  const abortar = useRef(null);
  const corrida = useRef({ id: null, documentos: new Map() });
  // The run under way on the server, until it ends: cancelled there when the page replaces it
  // with another or closes - it no longer stops with the connection (`api.executar`).
  const emCurso = useRef(null);
  // Whether the run under way is an example played back at a run's pace.
  const simular = useRef(false);
  // The latest callback, without restarting anything when the page passes a new one.
  const erroRef = useRef(aoErro);
  erroRef.current = aoErro;
  const guardarRef = useRef(aoGuardar);
  guardarRef.current = aoGuardar;
  const nomearRef = useRef(aoNomear);
  nomearRef.current = aoNomear;
  const fundoRef = useRef(fundo);
  fundoRef.current = fundo;

  /** Lets go of the run under way: cancelled on the server, unless it runs in the background. */
  const largar = useCallback(() => {
    if (emCurso.current && !fundoRef.current) api.cancelar(emCurso.current);
    emCurso.current = null;
  }, []);

  useEffect(() => {
    const fechar = () => {
      if (emCurso.current && !fundoRef.current) api.cancelar(emCurso.current);
    };
    window.addEventListener("pagehide", fechar);
    return () => window.removeEventListener("pagehide", fechar);
  }, []);

  /** Streams a run into state: a new one (`entrada`), or (`runId`) one under way, from its first
      event. */
  const seguir = useCallback(async ({ entrada = null, runId = null, dataDaClaim, imediato = false }) => {
    if (abortar.current) abortar.current.abort();
    largar();
    const controlo = new AbortController();
    abortar.current = controlo;
    simular.current = Boolean(entrada?.exemplo_id) && !imediato;
    const ritmo = simular.current ? ritmoAoAcaso() : null;
    despachar({ tipo: "preparar", dataDaClaim, ritmo });
    erroRef.current(null);
    setOcupado(true);
    setCancelavel(false);

    const entregar = (evento) => {
      // The first event names the run, waiting in the queue or not.
      if (evento.run_id && corrida.current.id !== evento.run_id) {
        corrida.current = { id: evento.run_id, documentos: new Map() };
        emCurso.current = evento.run_id;
        if (!entrada?.exemplo_id) {
          setCancelavel(true);
          if (fundoRef.current) nomearRef.current?.(evento.run_id);
        }
      }
      if ((evento.type === "done" || evento.type === "error") && emCurso.current === corrida.current.id) {
        emCurso.current = null;
        setCancelavel(false);
      }
      if (evento.type === "error") erroRef.current({ texto: evento.message });
      despachar({ tipo: "evento", evento });
      if (evento.type === "done" && evento.guardada) guardarRef.current?.(corrida.current.id);
    };

    // An example's stages each show as running for their share of the step before ending.
    let fila = Promise.resolve();
    const aoEvento = (evento) => {
      fila = fila.then(async () => {
        if (controlo.signal.aborted) return;
        const etapa = evento.type === "stage" && evento.stage;
        if (simular.current && etapa && (etapa.status === "done" || etapa.status === "skipped")) {
          despachar({ tipo: "evento", evento: { type: "stage", stage: { ...etapa, status: "running" } } });
          const passo = passoDe(etapa.name);
          await esperar(passo ? ritmo[passo.id] / passo.etapas.length : 0, controlo.signal);
          if (controlo.signal.aborted) return;
        }
        entregar(evento);
      });
    };

    try {
      if (entrada) await api.executar(entrada, aoEvento, controlo.signal);
      else {
        // The stream's events do not name the run (only the first of `/api/run` does).
        aoEvento({ type: "queue", run_id: runId, ahead: null });
        await api.acompanhar(runId, aoEvento, controlo.signal);
      }
      await fila;
    } catch (e) {
      if (e.name !== "AbortError") erroRef.current({ texto: e.message });
    } finally {
      // A newer run owns the busy state once it has started.
      if (abortar.current === controlo) {
        abortar.current = null;
        setOcupado(false);
        setCancelavel(false);
      }
    }
  }, [largar]);

  const executar = useCallback((entrada, dataDaClaim, { imediato = false } = {}) => seguir({ entrada, dataDaClaim, imediato }), [seguir]);

  /** Follows again a run in the background under way, from its first event. */
  const retomar = useCallback((runId, dataDaClaim) => seguir({ runId, dataDaClaim }), [seguir]);

  /** Opens a verification the server kept, from its address: the events its run sent, all at
      once, as a run that had just ended. Resolves with what was asked (`input`), or rejects with
      the server's reason - there is none by that address. */
  const abrir = useCallback(async (runId) => {
    if (abortar.current) abortar.current.abort();
    largar();
    const controlo = new AbortController();
    abortar.current = controlo;
    simular.current = false;
    erroRef.current(null);
    setOcupado(true);
    setCancelavel(false);
    try {
      const dados = await api.verificacao(runId, controlo.signal);
      if (controlo.signal.aborted) return null;
      corrida.current = { id: runId, documentos: new Map() };
      despachar({ tipo: "preparar", dataDaClaim: comoData(dados.input.claim_date), ritmo: null });
      for (const evento of dados.eventos) despachar({ tipo: "evento", evento });
      return dados.input;
    } finally {
      if (abortar.current === controlo) {
        abortar.current = null;
        setOcupado(false);
      }
    }
  }, [largar]);

  /** Cancels the run under way, waiting in the queue or running: the server closes its events with
      the reason, and the stream ends as for any other run. */
  const cancelar = useCallback(() => {
    if (emCurso.current) api.cancelar(emCurso.current);
    setCancelavel(false);
  }, []);

  const documento = useCallback(async (docId) => {
    const { id, documentos } = corrida.current;
    if (!id) return null;
    if (!documentos.has(docId)) documentos.set(docId, await api.documento(id, docId));
    return documentos.get(docId);
  }, []);

  return { estado, ocupado, cancelavel, executar, retomar, abrir, cancelar, documento };
}
