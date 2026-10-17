/** Document drawer: shows a news item with the cited passage highlighted. Builds its own DOM
    on first use, appended to the body. */

import { el, botao } from "./dom.js";
import { dataLonga, nomeRotulo } from "./formato.js";
import { aoMudarLingua, t } from "./i18n.js";

let raiz = null;
let devolverFoco = null;
// What the drawer shows, so that a language switch can rewrite its header.
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

  const corpo = el("div", "gaveta__corpo");
  // Focusable, so the text can be scrolled from the keyboard.
  corpo.tabIndex = 0;
  painel.append(topo, corpo);
  document.body.append(veu, painel);

  fechar.addEventListener("click", fecharGaveta);
  veu.addEventListener("click", fecharGaveta);
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") fecharGaveta();
  });

  return { veu, painel, etiqueta, titulo, meta, corpo, fechar };
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

// The news text stays as it is: only the header is rewritten, keeping the reading position.
aoMudarLingua(() => {
  if (raiz !== null && !raiz.painel.hidden && aberto) cabecalho(raiz, aberto.doc, aberto.excerpt);
});

export function abrir({ doc, excerpt, origem }) {
  const g = garantir();
  devolverFoco = origem || null;
  aberto = { doc, excerpt };
  cabecalho(g, doc, excerpt);

  const texto = doc.content || "";
  const inicio = excerpt && excerpt.begin;
  const fim = excerpt && excerpt.end;
  const temRealce = Number.isInteger(inicio) && Number.isInteger(fim) && fim > inicio && fim <= texto.length;

  g.corpo.replaceChildren();
  let marca = null;
  if (temRealce) {
    marca = el("mark", "realce", texto.slice(inicio, fim));
    g.corpo.append(document.createTextNode(texto.slice(0, inicio)), marca, document.createTextNode(texto.slice(fim)));
  } else {
    g.corpo.append(document.createTextNode(texto));
  }

  g.painel.hidden = false;
  g.veu.hidden = false;
  document.body.style.overflow = "hidden";
  g.corpo.scrollTop = 0;
  g.painel.querySelector(".gaveta__fechar").focus();

  if (marca) {
    requestAnimationFrame(() => {
      g.corpo.scrollTo({ top: Math.max(0, marca.offsetTop - g.corpo.clientHeight / 3), behavior: "smooth" });
    });
  }
}
