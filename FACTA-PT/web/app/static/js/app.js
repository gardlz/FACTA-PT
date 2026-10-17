/** Entry point: mounts the view, streams each run into it, opens cited news in the drawer and
    switches the light/dark theme and the interface language. */

import * as api from "./core/api.js";
import { abrir as abrirGaveta } from "./core/gaveta.js";
import { el } from "./core/dom.js";
import { aoMudarLingua, definirLingua, lingua, t } from "./core/i18n.js";
import { montar } from "./vista.js";

const CHAVE_TEMA = "facta-pt:tema";

const raiz = document.getElementById("raiz");
const botaoTema = document.getElementById("tema");
const seletorLingua = document.getElementById("lingua");
const opcoesLingua = Array.from(seletorLingua.querySelectorAll("[data-lingua]"));

const corrida = { id: null, documentos: new Map(), abortar: null };
let vista = null;

/* --- Theme ----------------------------------------------------------------- */

function aplicarTema(tema) {
  document.documentElement.dataset.theme = tema;
  try {
    localStorage.setItem(CHAVE_TEMA, tema);
  } catch (e) {
    void e;
  }
}

function temaGuardado() {
  try {
    return localStorage.getItem(CHAVE_TEMA) || "auto";
  } catch (e) {
    void e;
    return "auto";
  }
}

botaoTema.addEventListener("click", () => {
  const atual = document.documentElement.dataset.theme;
  const escuro = atual === "dark" || (atual !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  aplicarTema(escuro ? "light" : "dark");
});

/* --- Language ----------------------------------------------------------------- */

/** The texts of the page outside the view: title, description, skip link and top bar. */
function textosDaPagina() {
  document.title = t("pagina.titulo");
  const descricao = document.querySelector('meta[name="description"]');
  if (descricao) descricao.setAttribute("content", t("pagina.descricao"));
  const saltar = document.querySelector(".skip");
  if (saltar) saltar.textContent = t("pagina.saltar");
  botaoTema.setAttribute("aria-label", t("pagina.tema"));
  seletorLingua.setAttribute("aria-label", t("pagina.lingua"));
  opcoesLingua.forEach((opcao) => opcao.setAttribute("aria-pressed", String(opcao.dataset.lingua === lingua())));
}

opcoesLingua.forEach((opcao) => opcao.addEventListener("click", () => definirLingua(opcao.dataset.lingua)));
aoMudarLingua(textosDaPagina);

/* --- Documents and citations ------------------------------------------------- */

async function abrirDocumento(docId, excerto, origem) {
  if (!corrida.id) return;
  let documento = corrida.documentos.get(docId);
  if (!documento) {
    documento = await api.documento(corrida.id, docId);
    corrida.documentos.set(docId, documento);
  }
  abrirGaveta({ doc: documento, excerpt: excerto, origem });
}

function abrirCitacao(citacao, origem) {
  if (!citacao) return;
  abrirDocumento(citacao.doc_id, { begin: citacao.begin, end: citacao.end, label: citacao.label }, origem).catch(
    (e) => vista && vista.aoErro(() => t("erro.noticia", { erro: e.message }))
  );
}

/* --- Run ---------------------------------------------------------------------- */

async function executar(entrada) {
  if (corrida.abortar) corrida.abortar.abort();
  corrida.abortar = new AbortController();
  vista.aoErro(null);
  vista.aoOcupado(true);
  try {
    await api.executar(
      entrada,
      (evento) => {
        if (evento.type === "start") {
          corrida.id = evento.run_id;
          corrida.documentos.clear();
        }
        if (evento.type === "error") vista.aoErro(evento.message);
        vista.aoEvento(evento);
      },
      corrida.abortar.signal
    );
  } catch (e) {
    if (e.name !== "AbortError") vista.aoErro(e.message);
  } finally {
    vista.aoOcupado(false);
    corrida.abortar = null;
  }
}

/* --- Startup -------------------------------------------------------------------- */

function falhaDeArranque(erro) {
  raiz.replaceChildren();
  const aviso = el("div", "arranque-falhou");
  aviso.append(el("h1", null, t("arranque.titulo")));
  aviso.append(el("p", null, t("arranque.texto")));
  aviso.append(el("code", null, String((erro && erro.message) || erro)));
  raiz.append(aviso);
}

async function iniciar() {
  aplicarTema(temaGuardado());
  textosDaPagina();
  let topicos = [];
  try {
    const resposta = await api.exemplos();
    topicos = resposta.topicos || [];
  } catch (e) {
    // Not fatal: without examples, new claims can still be verified.
    void e;
  }
  raiz.replaceChildren();
  vista = montar(raiz, { topicos, executar, abrirCitacao, abrirDocumento });
}

iniciar().catch(falhaDeArranque);
