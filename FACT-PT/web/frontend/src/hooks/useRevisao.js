/** The editorial review of one verification, as a draft: the page is the automated result (or
 *  the last saved version), and every edit - which news items count, what a passage says, a
 *  highlight, the verdict, the article's text - changes the draft only. One undo and one redo
 *  cover them all, whatever was edited. Nothing reaches the server until the person saves, and
 *  each save is one version, with its author and time.
 *
 *  An earlier version can be reopened in the draft, to be read on the page as it was; saving it
 *  then makes it the current one again (a restore). A draft not yet saved survives a reload, in
 *  this browser, for as long as no one saves another version on top of the one it started from.
 *
 *  A save that loses a race is a 409 carrying the review as it now is: the page keeps the draft
 *  and offers to drop it for the other version or to save it on top.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { vereditoDaRevisao } from "../lib/evidencia";

const PASSOS = 100;
// Typing in one field is one step of undo for as long as it does not pause for this long.
const PAUSA_DE_ESCRITA = 1000;
// How often the page asks how an article rewrite is going.
const ESPERA_PEDIDO = 4000;
const CHAVE_RASCUNHO = "facta-pt:rascunho:";

/** An id for a passage a person highlighted in the page, before the server sees it: the version
    needs to tell two new highlights apart, and the server keeps the id it is given. */
function novoId() {
  return `local-${Math.random().toString(36).slice(2, 10)}`;
}

/** The same JSON whatever order the keys came in: the server and the page build objects apart. */
function canonico(valor) {
  if (Array.isArray(valor)) return valor.map(canonico);
  if (valor && typeof valor === "object") {
    return Object.fromEntries(Object.keys(valor).sort().map((chave) => [chave, canonico(valor[chave])]));
  }
  return valor;
}

export const iguais = (a, b) => JSON.stringify(canonico(a)) === JSON.stringify(canonico(b));

/** The draft with its verdict following the evidence, as the server will compute it. */
function comVeredito(estado) {
  return { ...estado, veredito: vereditoDaRevisao(estado) };
}

function lerRascunho(runId) {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_RASCUNHO + runId) || "null");
  } catch {
    return null;
  }
}

function escreverRascunho(runId, rascunho) {
  try {
    if (rascunho) localStorage.setItem(CHAVE_RASCUNHO + runId, JSON.stringify(rascunho));
    else localStorage.removeItem(CHAVE_RASCUNHO + runId);
  } catch {
    // Storage unavailable or full: the draft just does not outlive the page.
  }
}

export function useRevisao(runId) {
  const [dados, setDados] = useState(null);
  // The draft: `{ estado, restauradaDe }`, the version it reopened when it is a restore.
  const [rascunho, setRascunho] = useState(null);
  const [passado, setPassado] = useState([]);
  const [futuro, setFuturo] = useState([]);
  // "inactivo" (no review), "pronto", "a-guardar", "erro", "conflito".
  const [situacao, setSituacao] = useState("inactivo");
  const [erro, setErro] = useState(null);
  // The draft came back from this browser's storage, unsaved, when the page opened.
  const [recuperado, setRecuperado] = useState(false);

  const dadosRef = useRef(null);
  const rascunhoRef = useRef(null);
  const passadoRef = useRef([]);
  const futuroRef = useRef([]);
  const grupo = useRef({ chave: null, em: 0 });
  const aGuardar = useRef(false);
  const montado = useRef(true);
  // A save or load answers for the run it was made for, never for the one now on the page.
  const runIdRef = useRef(runId);
  runIdRef.current = runId;

  const porDados = useCallback((novos) => {
    dadosRef.current = novos;
    setDados(novos);
  }, []);

  const porRascunho = useCallback((novo) => {
    rascunhoRef.current = novo;
    setRascunho(novo);
  }, []);

  const porPilhas = useCallback((antes, depois) => {
    passadoRef.current = antes;
    futuroRef.current = depois;
    setPassado(antes);
    setFuturo(depois);
    grupo.current = { chave: null, em: 0 };
  }, []);

  const limpar = useCallback(() => {
    porDados(null);
    porRascunho(null);
    porPilhas([], []);
    setRecuperado(false);
  }, [porDados, porRascunho, porPilhas]);

  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  const actual = useCallback(() => runIdRef.current, []);

  const carregar = useCallback(
    async (descartar = false) => {
      if (!runId) {
        limpar();
        setSituacao("inactivo");
        setErro(null);
        return;
      }
      // Another verification's review must not stand in for this one while it loads.
      if (dadosRef.current?.run_id !== runId) limpar();
      try {
        const resposta = await api.revisao(runId);
        if (!montado.current || actual() !== runId) return;
        porDados(resposta);
        porPilhas([], []);
        // A draft left unsaved on this version comes back; one on an older version is stale.
        const guardado = descartar ? null : lerRascunho(runId);
        if (guardado && guardado.versao === resposta.versao && !iguais(guardado.estado, resposta.actual)) {
          porRascunho({ estado: guardado.estado, restauradaDe: guardado.restauradaDe ?? null });
          setRecuperado(true);
        } else {
          porRascunho({ estado: resposta.actual, restauradaDe: null });
          setRecuperado(false);
        }
        setSituacao("pronto");
        setErro(null);
      } catch (falha) {
        if (!montado.current || actual() !== runId) return;
        if (falha.estado === 404) {
          // Not a kept verification: it has no review (and never will).
          limpar();
          setSituacao("inactivo");
          setErro(null);
        } else {
          setErro(falha.message);
          setSituacao("erro");
        }
      }
    },
    [runId, limpar, actual, porDados, porRascunho, porPilhas]
  );

  useEffect(() => {
    carregar();
  }, [carregar]);

  const alterado = Boolean(rascunho && dados && (!iguais(rascunho.estado, dados.actual) || rascunho.restauradaDe != null));

  // The draft not yet saved is kept in this browser, against the version it started from.
  useEffect(() => {
    if (!runId || !dados?.pode_editar || !rascunho) return;
    escreverRascunho(runId, alterado ?{ versao: dados.versao, estado: rascunho.estado, restauradaDe: rascunho.restauradaDe } : null);
  }, [runId, dados, rascunho, alterado]);

  // Closing the page with a draft unsaved asks first (it would still come back on this browser).
  useEffect(() => {
    if (!alterado || !dados?.pode_editar) return undefined;
    const avisar = (evento) => {
      evento.preventDefault();
      evento.returnValue = "";
    };
    window.addEventListener("beforeunload", avisar);
    return () => window.removeEventListener("beforeunload", avisar);
  }, [alterado, dados]);

  /** Moves the draft to `novo`, remembering where it was for undo. `chave` names a field being
      typed in: keystrokes in the same field, without a pause, are a single step. */
  const mover = useCallback(
    (novo, chave = null) => {
      const antes = rascunhoRef.current;
      if (!antes || iguais(novo, antes)) return;
      const agora = Date.now();
      const continua = chave && grupo.current.chave === chave && agora - grupo.current.em < PAUSA_DE_ESCRITA;
      porRascunho(novo);
      if (!continua) {
        passadoRef.current = [...passadoRef.current.slice(-(PASSOS - 1)), antes];
        setPassado(passadoRef.current);
      }
      futuroRef.current = [];
      setFuturo([]);
      grupo.current = { chave, em: agora };
      setRecuperado(false);
      // A failed save is not retried on its own: the next save tries again.
      setSituacao((anterior) => (anterior === "erro" ? "pronto" : anterior));
    },
    [porRascunho]
  );

  /** Changes the draft's state: `mudanca` is the fields to set, or a function of the state. */
  const aplicar = useCallback(
    (mudanca, chave = null) => {
      const antes = rascunhoRef.current;
      if (!antes) return;
      const bruto = typeof mudanca === "function" ? mudanca(antes.estado) : { ...antes.estado, ...mudanca };
      mover({ ...antes, estado: comVeredito(bruto) }, chave);
    },
    [mover]
  );

  const desfazer = useCallback(() => {
    if (!passadoRef.current.length) return;
    const anterior = passadoRef.current.at(-1);
    porPilhas(passadoRef.current.slice(0, -1), [rascunhoRef.current, ...futuroRef.current].slice(0, PASSOS));
    porRascunho(anterior);
  }, [porPilhas, porRascunho]);

  const refazer = useCallback(() => {
    if (!futuroRef.current.length) return;
    const [seguinte, ...resto] = futuroRef.current;
    porPilhas([...passadoRef.current, rascunhoRef.current].slice(-PASSOS), resto);
    porRascunho(seguinte);
  }, [porPilhas, porRascunho]);

  /** Drops the draft for the last saved version. It is one step of undo like any other. */
  const descartar = useCallback(() => {
    const servidor = dadosRef.current;
    if (servidor) mover({ estado: servidor.actual, restauradaDe: null });
  }, [mover]);

  /** Opens an earlier version in the draft, to read it on the page; saved, it is a restore. */
  const abrirVersao = useCallback(
    async (versao) => {
      const servidor = dadosRef.current;
      if (!servidor) return;
      if (versao === servidor.versao) {
        descartar();
        return;
      }
      try {
        const resposta = await api.versaoRevisao(runId, versao);
        if (!montado.current || actual() !== runId) return;
        mover({ estado: resposta.estado, restauradaDe: versao });
        setErro(null);
      } catch (falha) {
        if (!montado.current || actual() !== runId) return;
        setErro(falha.message);
        setSituacao("erro");
      }
    },
    [runId, actual, mover, descartar]
  );

  /** Saves the draft as a new version. Resolves true when nothing is left unsaved. */
  const guardar = useCallback(async () => {
    const servidor = dadosRef.current;
    const local = rascunhoRef.current;
    if (!servidor || !local || !servidor.pode_editar) return false;
    if (iguais(local.estado, servidor.actual) && local.restauradaDe == null) return true;
    if (aGuardar.current) return false;
    aGuardar.current = true;
    setSituacao("a-guardar");
    try {
      const corpo = { versao: servidor.versao, estado: local.estado };
      if (local.restauradaDe != null) corpo.restaurada_de = local.restauradaDe;
      const resposta = await api.guardarRevisao(runId, corpo);
      if (!montado.current || actual() !== runId) return false;
      porDados(resposta);
      // What was edited while the request was in flight stays in the draft.
      if (rascunhoRef.current === local) porRascunho({ estado: resposta.actual, restauradaDe: null });
      setRecuperado(false);
      setSituacao("pronto");
      setErro(null);
      return true;
    } catch (falha) {
      if (!montado.current || actual() !== runId) return false;
      if (falha.estado === 409 && falha.corpo?.revisao) {
        // The draft stays; the page must choose which version wins.
        porDados(falha.corpo.revisao);
        setSituacao("conflito");
      } else {
        setSituacao("erro");
      }
      setErro(falha.message);
      return false;
    } finally {
      aGuardar.current = false;
    }
  }, [runId, actual, porDados, porRascunho]);

  /** After a conflict: drop the draft for the server's version, or save it on top of it. */
  const resolverConflito = useCallback(
    async (escolha) => {
      if (escolha === "recarregar") await carregar(true);
      else await guardar();
    },
    [carregar, guardar]
  );

  // One undo, one redo and one save for the whole page, from the keyboard too. In a field being
  // typed in, the draft's undo stands in for the browser's own, which a controlled field breaks.
  const podeEditar = Boolean(dados?.pode_editar);
  useEffect(() => {
    if (!podeEditar) return undefined;
    const tecla = (evento) => {
      if (!(evento.ctrlKey || evento.metaKey) || evento.altKey) return;
      const letra = evento.key.toLowerCase();
      if (letra === "z" && !evento.shiftKey) {
        evento.preventDefault();
        desfazer();
      } else if ((letra === "z" && evento.shiftKey) || letra === "y") {
        evento.preventDefault();
        refazer();
      } else if (letra === "s") {
        evento.preventDefault();
        guardar();
      }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [podeEditar, desfazer, refazer, guardar]);

  const mudarRelevancia = useCallback(
    (docId, relevante) =>
      aplicar((antes) => ({
        ...antes,
        documentos: (antes.documentos || []).map((documento) =>
          documento.doc_id === docId ? { ...documento, relevante } : documento
        ),
      })),
    [aplicar]
  );

  const mudarExcerto = useCallback(
    (id, campos) =>
      aplicar((antes) => ({
        ...antes,
        excertos: (antes.excertos || []).map((excerto) => (excerto.id === id ? { ...excerto, ...campos } : excerto)),
      })),
    [aplicar]
  );

  const removerExcerto = useCallback(
    (id) => aplicar((antes) => ({ ...antes, excertos: (antes.excertos || []).filter((excerto) => excerto.id !== id) })),
    [aplicar]
  );

  const adicionarDestaque = useCallback(
    (docId, begin, end, texto, rotulo) =>
      aplicar((antes) => ({
        ...antes,
        // Highlighting a passage of a news item ruled out brings it back as evidence.
        documentos: (antes.documentos || []).map((documento) =>
          documento.doc_id === docId ? { ...documento, relevante: true } : documento
        ),
        excertos: [
          ...(antes.excertos || []),
          { id: novoId(), doc_id: docId, begin, end, texto, rotulo, origem: "humano", nota: "", criado_por: null, criado_em: null },
        ],
      })),
    [aplicar]
  );

  const mudarVeredito = useCallback((veredito) => aplicar({ veredito_manual: veredito }), [aplicar]);

  /** Changes the article: `mudanca` is a function of it. `chave` names the field typed in. */
  const mudarArtigo = useCallback(
    (mudanca, chave = null) =>
      aplicar((antes) => (antes.artigo ? { ...antes, artigo: mudanca(antes.artigo) } : antes), chave),
    [aplicar]
  );

  /** Makes `artigo`, one the review already holds, the article of the draft and saves it: the
      pick among the articles written from the same evidence. */
  const usarArtigo = useCallback(
    async (artigo) => {
      aplicar((antes) => ({ ...antes, artigo }));
      return guardar();
    },
    [aplicar, guardar]
  );

  /** Asks the server to write the article again from the evidence as it stands. The draft is
      saved first - the button says so - so the writer reads exactly what the page shows. */
  const pedirReescrita = useCallback(
    async (redator) => {
      if (!(await guardar())) return false;
      const servidor = dadosRef.current;
      if (!servidor) return false;
      try {
        const corpo = { versao: servidor.versao };
        if (redator) corpo.redator = redator;
        const resposta = await api.reescreverArtigo(runId, corpo);
        if (!montado.current || actual() !== runId) return false;
        porDados(resposta);
        setErro(null);
        return true;
      } catch (falha) {
        if (!montado.current || actual() !== runId) return false;
        if (falha.estado === 409 && falha.corpo?.revisao) {
          porDados(falha.corpo.revisao);
          setSituacao("conflito");
        } else {
          setSituacao("erro");
        }
        setErro(falha.message);
        return false;
      }
    },
    [guardar, runId, actual, porDados]
  );

  // While the worker writes the article, the page asks how it is going. The version it brings
  // is the new base: a clean draft takes it whole, and a draft being edited keeps its edits and
  // takes the new article, unless its own article was being edited too.
  const pedidoActivo = Boolean(dados?.pedido && (dados.pedido.estado === "na-fila" || dados.pedido.estado === "em-curso"));
  useEffect(() => {
    if (!runId || !pedidoActivo) return undefined;
    const consultar = async () => {
      try {
        const resposta = await api.revisao(runId);
        if (!montado.current || actual() !== runId) return;
        const base = dadosRef.current;
        const local = rascunhoRef.current;
        porDados(resposta);
        if (!base || !local || resposta.versao === base.versao) return;
        if (iguais(local.estado, base.actual) && local.restauradaDe == null) {
          porRascunho({ estado: resposta.actual, restauradaDe: null });
        } else if (iguais(local.estado.artigo, base.actual.artigo)) {
          porRascunho({ ...local, estado: { ...local.estado, artigo: resposta.actual.artigo } });
        }
      } catch {
        // A failed poll changes nothing: the next one asks again.
      }
    };
    const relogio = setInterval(consultar, ESPERA_PEDIDO);
    return () => clearInterval(relogio);
  }, [runId, pedidoActivo, actual, porDados, porRascunho]);

  return {
    dados,
    estado: rascunho?.estado || null,
    situacao,
    erro,
    recuperado,
    podeEditar,
    alterado,
    restauradaDe: rascunho?.restauradaDe ?? null,
    podeDesfazer: passado.length > 0,
    podeRefazer: futuro.length > 0,
    artigoOrigem: dados?.artigo_origem || null,
    // The articles written from the evidence as it was saved, and how many more were written
    // from an earlier state of it.
    artigos: dados?.artigos || [],
    artigosAnteriores: dados?.artigos_anteriores || 0,
    redator: dados?.redator || "",
    pedido: dados?.pedido || null,
    historico: dados?.historico || [],
    desfazer,
    refazer,
    descartar,
    guardar,
    abrirVersao,
    mudarRelevancia,
    mudarExcerto,
    removerExcerto,
    adicionarDestaque,
    mudarVeredito,
    mudarArtigo,
    usarArtigo,
    recarregar: carregar,
    resolverConflito,
    pedirReescrita,
  };
}
