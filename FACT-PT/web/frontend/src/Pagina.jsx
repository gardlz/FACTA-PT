/** The page: the start (examples and form) or a verification. A verification opens at once: its
    row of steps fills as the pipeline runs, ending in the verdict, and the sections (questions,
    evidence timeline, tally and the cited article) arrive under it as they are ready. The claim
    heads it, with the context it was made in.

    Two routes: `/` for the start and `/verificacao` for a verification, so the browser's back
    button returns to the form. A verification has an address to share: an example's is
    `/verificacao/<example id>`, and a new claim's, once its run has ended and the server has kept
    it, `/verificacao/<run id>`, which opens it again whenever it is visited. A run in the
    background (the account's `segundo_plano`) has that address from its start: opened while it
    runs, the page follows it from its first event. */

import { AnimatePresence } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router";
import Administracao from "./components/Administracao";
import Artigo from "./components/corrida/Artigo";
import Balanco from "./components/corrida/Balanco";
import Eixo from "./components/corrida/Eixo";
import EmCurso from "./components/corrida/EmCurso";
import Perguntas from "./components/corrida/Perguntas";
import Resultado from "./components/corrida/Resultado";
import Entrada from "./components/entrada/Entrada";
import Exemplos, { vereditoDe } from "./components/entrada/Exemplos";
import Formulario, { validar } from "./components/entrada/Formulario";
import Gaveta from "./components/Gaveta";
import Sobre from "./components/Sobre";
import Verificacoes from "./components/Verificacoes";
import { useCorrida, estadoDosPassos } from "./hooks/useCorrida";
import { iguais, useRevisao } from "./hooks/useRevisao";
import * as api from "./lib/api";
import { comoData } from "./lib/datas";
import { excertosAutomaticos, planoDoEixo, vereditoDaEvidencia } from "./lib/evidencia";

/** The server's default for a choice, when it is one of the options it offers. */
function omissao(escolha, chave = (o) => o) {
  if (!escolha?.opcoes?.length) return null;
  const valores = escolha.opcoes.map(chave);
  return valores.includes(escolha.omissao) ? escolha.omissao : valores[0];
}

const CHAVE_REDATOR = "facta-pt:redator";

/** The writer the reader chose last, if the server still offers it; kept in this browser only. */
function redatorGuardado(escolha) {
  try {
    const id = localStorage.getItem(CHAVE_REDATOR);
    return escolha?.opcoes?.some((o) => o.id === id) ? id : null;
  } catch {
    return null;
  }
}

function guardarRedator(id) {
  try {
    localStorage.setItem(CHAVE_REDATOR, id);
  } catch {
    // Storage unavailable: the choice just is not remembered.
  }
}

function deExemplo(exemplo) {
  return { claim: exemplo.claim || "", data: (exemplo.claim_date || "").slice(0, 10), contexto: exemplo.context || "" };
}

// What the server names a run: the last part of the address of a verification it kept.
const ID_DE_EXECUCAO = /^[0-9a-f]{6,32}$/;

/** A verification's route. Opened by its address with nothing run for it yet, an example runs
    again and a kept verification is fetched; anything else leads back to the form. */
function Verificacao({ corrida, exemplos, aoAbrirExemplo, aoAbrirGuardada, children }) {
  const { t } = useTranslation();
  const { exemploId } = useParams();
  const emFalta = exemploId && corrida?.exemploId !== exemploId && corrida?.runId !== exemploId;
  const guardada = emFalta && ID_DE_EXECUCAO.test(exemploId) ? exemploId : null;
  const caso = emFalta && !guardada ? exemplos.find((e) => e.id === exemploId) : null;
  // Once per address: StrictMode runs effects twice, and each run would restart the example.
  const pedido = useRef(null);
  useEffect(() => {
    const endereco = caso?.id ?? guardada;
    if (!endereco) pedido.current = null;
    else if (pedido.current !== endereco) {
      pedido.current = endereco;
      if (caso) aoAbrirExemplo(caso);
      else aoAbrirGuardada(guardada);
    }
  }, [caso, guardada, aoAbrirExemplo, aoAbrirGuardada]);
  if (caso) return null;
  if (guardada) {
    return (
      <p role="status" className="mt-24 text-center text-[14px] text-mudo">
        {t("corrida.aAbrir")}
      </p>
    );
  }
  if (!corrida || emFalta) return <Navigate to="/" replace />;
  return children;
}

export default function Pagina({ catalogo, sessao, aoActualizarSessao, aoEscolherRedator }) {
  const { t } = useTranslation();
  const { exemplos, quantidade, redatores } = catalogo;

  // The form starts empty, with only its placeholders.
  const [valores, setValores] = useState(() => ({
    claim: "",
    data: "",
    contexto: "",
    topK: omissao(quantidade),
    redator: redatorGuardado(redatores) ?? omissao(redatores, (r) => r.id),
  }));
  // A picked example runs from what was stored for it; any edit makes it a new claim.
  const [exemploId, setExemploId] = useState(null);
  // Counts the form's calls to the examples, each one scrolling to them and lighting them up.
  const [chamada, setChamada] = useState(0);
  // `{ chave, valores }` for a message of the interface, `{ texto }` for one from the server.
  const [erro, setErro] = useState(null);
  const [gaveta, setGaveta] = useState(null);
  const [realcado, setRealcado] = useState(null);
  // What was sent: claim, date, and the example's recorded verdict. Null until the first run.
  const [corrida, setCorrida] = useState(null);
  const navegar = useNavigate();
  const { pathname } = useLocation();
  const naVerificacao = pathname.startsWith("/verificacao");
  // Runs that go on with nobody watching, for an account allowed them.
  const fundo = Boolean(sessao?.permissoes?.includes("segundo_plano"));

  // Where the page is, for a callback that outlives the render it was made in.
  const caminho = useRef(pathname);
  caminho.current = pathname;

  // The server kept the verification that just ended: its address goes in the address bar, to be
  // copied. Only if the reader is still looking at it - they may have gone back to the form.
  const aoGuardar = useCallback(
    (runId) => {
      setCorrida((anterior) => anterior && { ...anterior, runId, guardada: true });
      if (caminho.current === "/verificacao") navegar(`/verificacao/${runId}`, { replace: true });
    },
    [navegar]
  );

  // A run in the background has its address as soon as the server names it.
  const aoNomear = useCallback(
    (runId) => {
      setCorrida((anterior) => anterior && { ...anterior, runId });
      if (caminho.current === "/verificacao") navegar(`/verificacao/${runId}`, { replace: true });
    },
    [navegar]
  );

  const { estado, ocupado, cancelavel, executar, retomar, abrir, cancelar, documento } = useCorrida(setErro, aoGuardar, { fundo, aoNomear });
  // The editorial review of the verification, once the server has kept it.
  const revisao = useRevisao(corrida?.guardada ? corrida.runId : null);

  const alterar = useCallback((parcial) => {
    if (parcial.redator) guardarRedator(parcial.redator);
    setValores((anteriores) => ({ ...anteriores, ...parcial }));
  }, []);

  // The bar shows the state of the writer picked here, not of every writer on offer.
  useEffect(() => {
    aoEscolherRedator?.(valores.redator ?? "");
  }, [valores.redator, aoEscolherRedator]);

  // When the interface language changes, a picked example in the form follows the new catalogue.
  useEffect(() => {
    if (!exemploId) return;
    const caso = exemplos.find((e) => e.id === exemploId);
    if (caso) setValores((anteriores) => ({ ...anteriores, ...deExemplo(caso) }));
  }, [exemplos, exemploId]);

  // An example already open on the verification page reloads in the new language when the catalogue changes.
  useEffect(() => {
    if (!corrida?.exemploId) return;
    const caso = exemplos.find((e) => e.id === corrida.exemploId);
    const claim = caso?.claim?.trim() || "";
    const contexto = (caso?.context || "").trim();
    if (!caso || (claim === corrida.claim && contexto === corrida.contexto)) return;
    const pedido = { claim, claim_date: corrida.data, context: contexto, exemplo_id: caso.id };
    if (quantidade?.opcoes?.length) pedido.top_k = valores.topK;
    if (redatores?.opcoes?.length) pedido.redator = valores.redator;
    setCorrida((anterior) => anterior && { ...anterior, claim, contexto });
    setGaveta(null);
    executar(pedido, comoData(corrida.data), { imediato: !ocupado });
  }, [exemplos, corrida, quantidade, redatores, valores.topK, valores.redator, ocupado, executar]);

  function correr(dados, exemplo) {
    setErro(null);
    const pedido = { claim: dados.claim.trim(), claim_date: dados.data, context: dados.contexto.trim(), exemplo_id: exemplo };
    if (quantidade?.opcoes?.length) pedido.top_k = dados.topK;
    if (redatores?.opcoes?.length) pedido.redator = dados.redator;
    const caso = exemplo && exemplos.find((e) => e.id === exemplo);
    const meta = { exemploId: exemplo, claim: pedido.claim, data: dados.data, contexto: pedido.context, veredito: caso ? vereditoDe(caso, quantidade ? dados.topK : null) : null };
    setCorrida(meta);
    setGaveta(null);
    const destino = exemplo ? `/verificacao/${encodeURIComponent(exemplo)}` : "/verificacao";
    // Opened from its address, the example is already there: no second history entry.
    navegar(destino, { replace: pathname === destino });
    window.scrollTo(0, 0);
    executar(pedido, comoData(dados.data));
  }

  /** Opens a verification from its address: one the server kept or, not kept yet, the account's
      run in the background, followed from its first event. */
  const abrirGuardada = useCallback(
    async (runId) => {
      try {
        const entrada = await abrir(runId);
        if (!entrada) return;
        setCorrida({ runId, guardada: true, claim: entrada.claim, data: entrada.claim_date, contexto: entrada.context, veredito: null });
      } catch (e) {
        if (e.name === "AbortError") return;
        if (e.estado === 404 && fundo) {
          try {
            const execucao = await api.execucao(runId);
            if (caminho.current !== `/verificacao/${runId}`) return;
            setCorrida({ runId, guardada: false, claim: execucao.claim, data: execucao.claim_date, contexto: execucao.context, veredito: null });
            retomar(runId, comoData(execucao.claim_date));
            return;
          } catch {
            // Not the account's, or gone: as for any address with nothing behind it.
          }
        }
        setErro({ texto: e.message });
        navegar("/", { replace: true });
      }
    },
    [abrir, retomar, fundo, navegar]
  );

  /** An example picked on the start page only fills the form, so a misclick costs nothing: the
      reader looks it over and verifies it with the button. */
  function preencherExemplo(caso) {
    setValores((anteriores) => ({ ...anteriores, ...deExemplo(caso) }));
    setExemploId(caso.id);
    setErro(null);
    window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  /** An example opened from its address runs straight away. */
  function escolherExemplo(caso) {
    const dados = { ...valores, ...deExemplo(caso) };
    setValores(dados);
    setExemploId(caso.id);
    const falha = validar(dados);
    if (falha) setErro({ chave: falha });
    else correr(dados, caso.id);
  }

  // Leaving a page: the drawer closes and the next one starts at its top.
  useEffect(() => {
    setGaveta(null);
    window.scrollTo(0, 0);
  }, [pathname]);

  /* --- Following the run ------------------------------------------------------ */

  // The review's draft is what the page shows and a person edits: which news items count, what
  // each passage says, the verdict and the article. Without a review (an example, or one still
  // loading), the pipeline's own result.
  const evidencia = revisao.estado;
  const podeEditar = Boolean(revisao.dados && revisao.podeEditar);

  // The timeline keeps every retrieved news item: the review rules one in or out, and an
  // irrelevant one stays as a dashed outline, still readable and one click from coming back.
  const naLinha = useMemo(() => {
    if (!estado.recuperados.length) return null;
    const relevancia = new Map((evidencia?.documentos || []).map((documento) => [documento.doc_id, documento.relevante]));
    return estado.recuperados.map((documento) => ({
      ...documento,
      relevant: relevancia.has(documento.doc_id) ? relevancia.get(documento.doc_id) : documento.relevant !== false,
    }));
  }, [estado.recuperados, evidencia]);

  // The relevance counts the timeline notes: the review's, once it is there, so ruling a news item
  // in or out changes the note with it.
  const relevancia = useMemo(() => {
    if (!evidencia?.documentos || !naLinha) return estado.relevancia;
    return {
      "notícias": naLinha.length,
      relevantes: naLinha.filter((documento) => documento.relevant !== false).length,
    };
  }, [evidencia, naLinha, estado.relevancia]);

  const plano = planoDoEixo(naLinha, relevancia, estado.dataDaClaim);
  const comPerguntas = Boolean(estado.perguntas);
  const comEixo = Boolean(plano);
  const comBalanco = Boolean(estado.classificacao && estado.documentos);
  const artigoBase = evidencia ? evidencia.artigo : estado.artigo;

  // The articles written from the same evidence - a reviewed run's rewrites, or an example's one
  // per model - to read one after the other, side by side, or (an editor) keep one of.
  const candidatos = useMemo(() => {
    const lista = evidencia
      ? revisao.artigos.map((c) => ({
          chave: String(c.versao),
          artigo: c.artigo,
          rotulo: c.versao === 0 ? c.artigo.model : `${c.artigo.model} · v${c.versao}`,
        }))
      : estado.artigos.map((artigo) => ({ chave: artigo.model, artigo, rotulo: artigo.model }));
    return lista.length > 1 ? lista : [];
  }, [evidencia, revisao.artigos, estado.artigos]);
  // The one on view in place of the draft's article, and the one laid beside it: keys of the list.
  const [vista, setVista] = useState(null);
  const [comparada, setComparada] = useState(null);
  const versaoGuardada = revisao.dados?.versao;
  useEffect(() => {
    setVista(null);
    setComparada(null);
  }, [estado.geracao, corrida?.runId, versaoGuardada]);
  const visto = candidatos.find((c) => c.chave === vista) || null;
  const atual = candidatos.find((c) => iguais(c.artigo, artigoBase))?.chave ?? null;
  const artigoMostrado = visto ? visto.artigo : artigoBase;
  const versoes = candidatos.length
    ? {
        lista: candidatos,
        vista: visto ? visto.chave : atual,
        comparada,
        anteriores: evidencia ? revisao.artigosAnteriores : 0,
        aoVer: (chave) => setVista(chave === atual ? null : chave),
        aoComparar: setComparada,
        aoUsar: podeEditar && visto ? () => revisao.usarArtigo(visto.artigo) : null,
      }
    : null;
  const comArtigo = Boolean(artigoMostrado || (revisao.dados && estado.classificacao));
  const semResultado = !comPerguntas && !comEixo && !comBalanco && !comArtigo;
  // The steps under way: a section shows its title and drawing before its content arrives, so the
  // page says where the run is working rather than staying blank under the row of steps.
  const emCurso = new Set(
    estadoDosPassos(estado.estados)
      .filter((passo) => passo.estado === "running")
      .map((passo) => passo.id)
  );
  // An example comes with its verdict recorded; a new claim has none until its own evidence is
  // classified, and then takes the verdict the evidence gives.
  const vereditoAutomatico = corrida?.veredito || vereditoDaEvidencia(estado.documentos, estado.classificacao);
  // The review's verdict follows its evidence, unless a person set it by hand; without a review,
  // the pipeline's.
  const veredito = evidencia?.veredito || vereditoAutomatico;
  // The last version a person saved (an article rewrite is a version too, but the worker's).
  const ultimaRevisao = [...(revisao.dados?.historico || [])].reverse().find((versao) => versao.accao !== "artigo");
  const revisaoEditada = Boolean(ultimaRevisao);
  const autorRevisao = ultimaRevisao?.autor || null;

  // A run that failed before giving anything back: return to the form, which shows the error.
  useEffect(() => {
    if (erro && naVerificacao && !ocupado && semResultado) navegar("/", { replace: true });
  }, [erro, naVerificacao, ocupado, semResultado, navegar]);

  /* --- Documents and citations ----------------------------------------------- */

  /** Opens a news item with every passage the review keeps from it and every one the article cites
      highlighted, and `foco` (a citation, or none) the one it glides to. */
  const abrirDocumento = useCallback(
    (docId, foco, origem) => {
      documento(docId)
        .then((doc) => doc && setGaveta({ doc, foco: foco || null, origem }))
        .catch((e) => setErro({ chave: "erro.noticia", valores: { erro: e.message } }));
    },
    [documento]
  );

  const abrirCitacao = useCallback(
    (citacao, origem) => {
      if (citacao) abrirDocumento(citacao.doc_id, citacao, origem);
    },
    [abrirDocumento]
  );

  const abrirDoEixo = useCallback((docId, origem) => abrirDocumento(docId, null, origem), [abrirDocumento]);

  const fecharGaveta = useCallback(() => setGaveta(null), []);

  // The passages the drawer highlights: the review's evidence for the news item (a person's
  // highlights among them, with the relation they were given) and the article's citations, which
  // carry the numbered markers. A citation over the same stretch as a review passage is drawn over
  // it, and a click still reaches the passage underneath.
  const excertosGaveta = useMemo(() => {
    if (!gaveta) return [];
    const doc = gaveta.doc;
    const conteudo = doc.content || "";
    // Without a review (an example, or a run still under way), the passages the result shows.
    const deste = evidencia
      ? (evidencia.excertos || []).filter((excerto) => excerto.doc_id === doc.doc_id)
      : excertosAutomaticos(doc, estado.classificacao);
    const revistos = deste
      .map((excerto) => ({
        ...excerto,
        texto: excerto.texto || conteudo.slice(excerto.begin, excerto.end),
        foco: false,
      }));
    const citadas = (artigoMostrado?.citations || [])
      .filter((citacao) => citacao.doc_id === doc.doc_id)
      .map((citacao) => ({
        id: `citacao-${citacao.marker}`,
        doc_id: citacao.doc_id,
        begin: citacao.begin,
        end: citacao.end,
        rotulo: citacao.label,
        origem: "automatico",
        texto: citacao.excerpt_text || conteudo.slice(citacao.begin, citacao.end),
        marcador: citacao.marker,
        foco: gaveta.foco ? citacao.marker === gaveta.foco.marker : false,
        // The classified windows of its relation the cited passage is made of.
        janelas: (citacao.excerpts || []).filter((janela) => janela.label === citacao.label),
      }));
    return [...revistos, ...citadas];
  }, [gaveta, evidencia, artigoMostrado, estado.classificacao]);

  const relevanteGaveta = gaveta
    ? evidencia?.documentos?.find((documento) => documento.doc_id === gaveta.doc.doc_id)?.relevante ??
      gaveta.doc.relevant !== false
    : true;

  const textoDoErro = erro && (erro.chave ? t(erro.chave, erro.valores) : erro.texto);
  // The index names each section by its own title, and spins beside the one under way.
  const seccoes = [
    { id: "sec-perguntas", rotulo: t("bloco.perguntas"), pronta: comPerguntas, curso: emCurso.has("perguntas") },
    { id: "sec-eixo", rotulo: t("bloco.eixo"), pronta: comEixo, curso: emCurso.has("evidencia") },
    { id: "sec-balanco", rotulo: t("bloco.balanco"), pronta: comBalanco, curso: emCurso.has("classificacao") },
    { id: "sec-artigo", rotulo: t("artigo.selo"), pronta: comArtigo, curso: emCurso.has("artigo") },
  ];

  const verificacao = (
    <Verificacao corrida={corrida} exemplos={exemplos} aoAbrirExemplo={escolherExemplo} aoAbrirGuardada={abrirGuardada}>
      {corrida && (
        <Resultado
          key={`r${estado.geracao}`}
          claim={corrida.claim}
          data={corrida.data}
          contexto={corrida.contexto}
          veredito={veredito}
          revisao={revisao}
          revisaoEditada={revisaoEditada}
          autorRevisao={autorRevisao}
          versaoRevisao={ultimaRevisao?.versao}
          estado={estado}
          ocupado={ocupado}
          aoCancelar={cancelavel ? cancelar : null}
          erro={textoDoErro}
          seccoes={seccoes}
          guardada={Boolean(corrida.runId)}
        >
          <AnimatePresence>
            {comPerguntas ? (
              <Perguntas key="perguntas" id="sec-perguntas" perguntas={estado.perguntas} />
            ) : (
              emCurso.has("perguntas") && (
                <EmCurso key="perguntas" id="sec-perguntas" titulo={t("bloco.perguntas")} passo="perguntas" />
              )
            )}
            {!comEixo && emCurso.has("evidencia") && (
              <EmCurso key="eixo" id="sec-eixo" titulo={t("bloco.eixo")} passo="evidencia" />
            )}
            {comEixo && (
              <Eixo
                key="eixo"
                id="sec-eixo"
                plano={plano}
                documentos={naLinha}
                triado={estado.documentos !== null}
                relevancia={relevancia}
                classificacao={estado.classificacao}
                evidencia={evidencia}
                podeEditar={podeEditar}
                original={revisao.dados?.original}
                aoMudarRelevancia={revisao.mudarRelevancia}
                realcado={realcado}
                aoAbrir={abrirDoEixo}
              />
            )}
            {comBalanco && (
              <Balanco
                key="balanco"
                id="sec-balanco"
                documentos={estado.documentos}
                classificacao={estado.classificacao}
                evidencia={evidencia}
                revista={revisaoEditada}
              />
            )}
            {comArtigo ? (
              <Artigo
                key="artigo"
                id="sec-artigo"
                artigo={artigoMostrado}
                versoes={versoes}
                aVer={Boolean(visto)}
                original={revisao.dados?.original?.artigo || null}
                aoCitar={abrirCitacao}
                aoRealcar={setRealcado}
                revisao={revisao}
                redatores={redatores}
              />
            ) : (
              emCurso.has("artigo") && (
                <EmCurso key="artigo" id="sec-artigo" titulo={t("artigo.selo")} passo="artigo" />
              )
            )}
          </AnimatePresence>
        </Resultado>
      )}
    </Verificacao>
  );

  return (
    // `minmax(0, 1fr)`: an `auto` column would grow to the examples row's full scroll width.
    <div data-coluna className="mx-auto grid max-w-[var(--coluna)] grid-cols-[minmax(0,1fr)] px-[var(--goteira)] pb-24">
      <Routes>
        <Route
          path="/"
          element={
            <Entrada>
              <Formulario
                valores={valores}
                aoAlterar={alterar}
                aoEditar={() => setExemploId(null)}
                totalExemplos={exemplos.length}
                aoVerExemplos={() => setChamada((n) => n + 1)}
                aoSubmeter={() => correr(valores, exemploId)}
                aoErro={setErro}
                erro={textoDoErro}
                erroChave={erro?.chave}
                ocupado={ocupado}
                redatores={redatores}
              />
              {exemplos.length > 0 && <Exemplos exemplos={exemplos} quantidade={quantidade ? valores.topK : null} aoEscolher={preencherExemplo} chamada={chamada} />}
            </Entrada>
          }
        />
        {/* One route for both, so the address changing when a run is kept does not remount it. */}
        <Route path="/verificacao/:exemploId?" element={verificacao} />
        <Route path="/sobre" element={<Sobre />} />
        <Route path="/verificacoes" element={<Verificacoes sessao={sessao} />} />
        <Route
          path="/administracao"
          element={
            <Administracao
              sessao={sessao}
              catalogo={catalogo}
              aoActualizarSessao={aoActualizarSessao}
            />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Gaveta
        aberto={gaveta ? { doc: gaveta.doc, excertos: excertosGaveta, relevante: relevanteGaveta, origem: gaveta.origem } : null}
        aoFechar={fecharGaveta}
        podeEditar={podeEditar}
        original={revisao.dados?.original}
        aoDestacar={revisao.adicionarDestaque}
        aoMudarExcerto={revisao.mudarExcerto}
        aoRemoverExcerto={revisao.removerExcerto}
        aoMudarRelevancia={revisao.mudarRelevancia}
      />
    </div>
  );
}
