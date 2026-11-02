/** Document drawer: shows a news item with the cited passage highlighted. When the passage joins
    several of the windows the stance classifier labelled, it lists them under the header, and
    choosing one highlights it in the text. Builds its own DOM on first use, appended to the body. */

import { el, botao } from "./dom.js";
import { dataLonga, nomeRotulo } from "./formato.js";
import { aoMudarLingua, t } from "./i18n.js";

let raiz = null;
let devolverFoco = null;
// What the drawer shows, and which entry of the list is highlighted, so that a language switch
// can rewrite its header and its list.
let aberto = null;

function construir() {
  const veu = el("div", "veu");
  veu.hidden = true;

  const painel = el("aside", "gaveta");
  painel.hidden = true;
  painel.setAttribute("role", "dialog");
  painel.setAttribute("aria-modal", "true");
  painel.setAttribute("aria-labelledby", "gaveta-titulo");

  const topo = el("div", "gaveta__topo");
  const bloco = el("div", "gaveta__identidade");
  const etiqueta = el("span", "gaveta__etiqueta");
  const titulo = el("h2", "gaveta__titulo");
  titulo.id = "gaveta-titulo";
  const meta = el("div", "gaveta__meta");
  bloco.append(etiqueta, titulo, meta);

  const fechar = botao("botao botao--icone gaveta__fechar");
  fechar.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
  topo.append(bloco, fechar);

  // The classified windows of a passage that joins several, between the header and the text.
  const janelas = el("section", "gaveta__janelas");
  janelas.hidden = true;

  const corpo = el("div", "gaveta__corpo");
  // Focusable, so the text can be scrolled from the keyboard.
  corpo.tabIndex = 0;
  painel.append(topo, janelas, corpo);
  document.body.append(veu, painel);

  fechar.addEventListener("click", fecharGaveta);
  veu.addEventListener("click", fecharGaveta);
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") fecharGaveta();
  });

  return { veu, painel, etiqueta, titulo, meta, janelas, corpo, fechar };
}

function garantir() {
  if (raiz === null) raiz = construir();
  return raiz;
}

function fecharGaveta() {
  const g = garantir();
  if (g.painel.hidden) return;
  g.painel.hidden = true;
  g.veu.hidden = true;
  document.body.style.removeProperty("overflow");
  // Focus goes back to whatever opened the drawer.
  if (devolverFoco && document.contains(devolverFoco)) devolverFoco.focus();
  devolverFoco = null;
}

/** The header: source, headline, date, genre, byline, length and the passage's relation. */
function cabecalho(g, doc, excerpt) {
  g.fechar.setAttribute("aria-label", t("gaveta.fechar"));
  g.etiqueta.textContent = t("gaveta.fonte", { id: doc.doc_id });
  g.titulo.textContent = doc.headline || t("gaveta.semTitulo");

  g.meta.replaceChildren();
  const pedacos = [dataLonga(doc.published_at), doc.genre, doc.byline].filter(Boolean);
  if (doc.word_count) pedacos.push(t("gaveta.palavras", { n: doc.word_count }));
  pedacos.forEach((texto) => g.meta.append(el("span", "gaveta__meta-item", texto)));
  if (excerpt && excerpt.label) {
    g.meta.append(el("span", `rotulo rotulo--${excerpt.label}`, nomeRotulo(excerpt.label)));
  }
}

/** The news text, with [inicio, fim) highlighted when it is a stretch of it. Returns the mark. */
function realcar(g, texto, inicio, fim) {
  g.corpo.replaceChildren();
  if (!(Number.isInteger(inicio) && Number.isInteger(fim) && fim > inicio && fim <= texto.length)) {
    g.corpo.append(document.createTextNode(texto));
    return null;
  }
  const marca = el("mark", "realce", texto.slice(inicio, fim));
  g.corpo.append(document.createTextNode(texto.slice(0, inicio)), marca, document.createTextNode(texto.slice(fim)));
  return marca;
}

function mostrar(g, marca) {
  if (!marca) return;
  requestAnimationFrame(() => {
    // Where the mark sits inside the scrolling text, whatever the drawer shows above the text:
    // `offsetTop` counts from the drawer, and the list of windows would push it past the mark.
    const topo = marca.getBoundingClientRect().top - g.corpo.getBoundingClientRect().top + g.corpo.scrollTop;
    g.corpo.scrollTo({ top: Math.max(0, topo - g.corpo.clientHeight / 3), behavior: "smooth" });
  });
}

/** When the cited passage joins several classified windows: the passage, then each window with
    the label the classifier gave it. Choosing an entry highlights it in the text. */
function listarJanelas(g) {
  const { doc, excerpt } = aberto;
  const partes = (excerpt && excerpt.partes) || [];
  g.janelas.replaceChildren();
  g.janelas.hidden = partes.length < 2;
  if (g.janelas.hidden) return;

  g.janelas.append(el("h3", "gaveta__janelas-titulo", t("gaveta.janelas", { n: partes.length })));
  g.janelas.append(el("p", "gaveta__janelas-nota", t("gaveta.janelasNota")));
  const lista = el("div", "gaveta__janelas-lista");
  const entradas = [{ begin: excerpt.begin, end: excerpt.end, label: excerpt.label, nome: t("gaveta.passagem") }].concat(
    partes.map((parte, i) => ({ ...parte, nome: t("gaveta.janela", { n: i + 1 }) }))
  );
  entradas.forEach((entrada, i) => {
    const item = botao("gaveta__janela");
    item.setAttribute("aria-pressed", String(i === aberto.ativa));
    const cabeca = el("span", "gaveta__janela-cabeca");
    cabeca.append(el("span", null, entrada.nome), el("span", `rotulo rotulo--${entrada.label}`, nomeRotulo(entrada.label)));
    item.append(cabeca);
    if (entrada.text) item.append(el("span", "gaveta__janela-texto", entrada.text));
    item.addEventListener("click", () => {
      aberto.ativa = i;
      lista.querySelectorAll(".gaveta__janela").forEach((outro, j) => outro.setAttribute("aria-pressed", String(j === i)));
      mostrar(g, realcar(g, doc.content || "", entrada.begin, entrada.end));
    });
    lista.append(item);
  });
  g.janelas.append(lista);
}

// The news text stays as it is: only the header and the list are rewritten, keeping the reading
// position and the highlighted entry.
aoMudarLingua(() => {
  if (raiz !== null && !raiz.painel.hidden && aberto) {
    cabecalho(raiz, aberto.doc, aberto.excerpt);
    listarJanelas(raiz);
  }
});

export function abrir({ doc, excerpt, origem }) {
  const g = garantir();
  devolverFoco = origem || null;
  aberto = { doc, excerpt, ativa: 0 };
  cabecalho(g, doc, excerpt);
  listarJanelas(g);
  const marca = realcar(g, doc.content || "", excerpt && excerpt.begin, excerpt && excerpt.end);

  g.painel.hidden = false;
  g.veu.hidden = false;
  document.body.style.overflow = "hidden";
  g.corpo.scrollTop = 0;
  g.painel.querySelector(".gaveta__fechar").focus();
  mostrar(g, marca);
}
