/** The page: input form and examples, pipeline progress, then the result (questions, evidence
    timeline, balance of relations and the cited article), scrolling along as it arrives. */

import { el, botao } from "./core/dom.js";
import { criarFormulario } from "./core/formulario.js";
import { comCitacoes, comoData as dia, dataCurta, dataLonga, nomeRotulo } from "./core/formato.js";
import { aoMudarLingua, t } from "./core/i18n.js";

/** The seven pipeline stages grouped into the four steps that mean something to a reader. A
    step's name and the line shown while it runs are the texts `passo.<id>` and
    `passo.<id>.trabalho`. */
const PASSOS = [
  { id: "perguntas", etapas: ["questions"] },
  {
    id: "evidencia",
    // Relevance is part of retrieval: it decides which retrieved news count as evidence.
    etapas: ["retrieval", "dedup", "relevance"],
  },
  { id: "classificacao", etapas: ["excerpts", "stance"] },
  { id: "artigo", etapas: ["article"] },
];

const BALANCO = ["supported", "refuted", "nei"];

/** Verdict of each example, shown as the card colour. It comes with the data (`veracity`):
    `nei` covers both conflicting and undecided evidence (sources are not weighed against each
    other), and `nei_sem_evidencia` means nothing retrieved counts as evidence. */
const VEREDITOS = ["supported", "refuted", "nei", "nei_sem_evidencia"];

function movimentoReduzido() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

const DIA_MS = 86400000;

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
function inicioDoEixo(maisAntiga, fim) {
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

/** Ruler ticks from start to end at the span's grain, positioned in percent. `tecto` is the
    most ticks that fit the track width, measured by the caller. */
function marcasDoEixo(inicio, fim, tecto = 8) {
  const nomesDosMeses = t("eixo.meses");
  const amplitude = Math.max(1, fim - inicio);
  const dias = amplitude / DIA_MS;
  const posicao = (data) => ((data - inicio) / amplitude) * 100;
  const marcas = [];
  const juntar = (data, etiqueta) => {
    const p = posicao(data);
    if (p >= 0 && p <= 100) marcas.push({ pos: p, etiqueta });
  };

  if (dias > 730) {
    const primeiro = inicio.getFullYear();
    const ultimo = fim.getFullYear();
    const passo = Math.max(1, Math.ceil((ultimo - primeiro + 1) / tecto));
    for (let ano = primeiro; ano <= ultimo; ano += passo) juntar(new Date(ano, 0, 1), String(ano));
    if (!marcas.length) marcas.push({ pos: 0, etiqueta: String(primeiro) });
    return marcas;
  }

  if (dias > 70) {
    const meses = Math.ceil(dias / 30.44);
    const passo = Math.max(1, Math.ceil(meses / tecto));
    const cursor = new Date(inicio.getFullYear(), inicio.getMonth(), 1);
    while (cursor <= fim) {
      const etiqueta = cursor.getFullYear() === fim.getFullYear()
        ? nomesDosMeses[cursor.getMonth()]
        : `${nomesDosMeses[cursor.getMonth()]} ${String(cursor.getFullYear()).slice(2)}`;
      juntar(new Date(cursor.getFullYear(), cursor.getMonth(), 1), etiqueta);
      cursor.setMonth(cursor.getMonth() + passo);
    }
    if (!marcas.length) marcas.push({ pos: 0, etiqueta: nomesDosMeses[inicio.getMonth()] });
    return marcas;
  }

  const passo = Math.max(1, Math.ceil(Math.max(1, dias) / Math.min(6, tecto)));
  const cursor = new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate());
  while (cursor <= fim) {
    juntar(new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate()),
           `${cursor.getDate()} ${nomesDosMeses[cursor.getMonth()]}`);
    cursor.setDate(cursor.getDate() + passo);
  }
  if (!marcas.length) marcas.push({ pos: 0, etiqueta: `${inicio.getDate()} ${nomesDosMeses[inicio.getMonth()]}` });
  return marcas;
}

export function montar(raiz, ctx) {
  /** Sets a fixed text now and after every language switch; for the parts built once. */
  function traduzivel(aplicar) {
    aplicar();
    aoMudarLingua(aplicar);
  }

  let dataDaClaim = null;
  let exemploEscolhido = null;
  // Everything retrieved, and the part of it that counts as evidence (what the relevance stage
  // did not rule unrelated). The axis and the balance show only the evidence.
  let recuperados = [];
  let documentos = [];
  // What the balance and the article were last drawn from, so a language switch can redraw them.
  let classificacao = null;
  let artigoDesenhado = null;
  let ultimoRevelado = null;
  let preparado = false;

  /* --- Scrolling that follows the result --------------------------------- */

  let soltarCancelamento = null;
  // Set when the reader interrupts the glide; the page is then theirs until the next run.
  let desistido = false;

  // Clearance for the sticky top bar.
  const MARGEM_TOPO = 78;
  // Cruising speed in px/s: quick, but slow enough to read what scrolls past.
  const VELOCIDADE = 1000;
  // Acceleration in px/s², so the glide eases in and out.
  const ACELERACAO = 1500;
  // Braking gain in 1/s: near the target, the speed is the remaining distance times this.
  const TRAVAGEM = 3;

  // One glide with a moving target: each result block that arrives retargets it instead of
  // starting another, so blocks arriving close together read as one smooth scroll.
  let destino = null;
  let velocidade = 0;
  let animacao = 0;

  function pararAnimacao() {
    animacao += 1;
    destino = null;
    velocidade = 0;
    if (soltarCancelamento) soltarCancelamento();
  }

  /** Stops the glide for the rest of the run at the reader's first wheel, touch or key press. */
  function armarCancelamento() {
    if (soltarCancelamento) return;
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const parar = () => {
      desistido = true;
      pararAnimacao();
    };
    const soltar = () => {
      window.removeEventListener("wheel", parar);
      window.removeEventListener("touchstart", parar);
      window.removeEventListener("keydown", parar);
      soltarCancelamento = null;
    };
    soltarCancelamento = soltar;
    window.addEventListener("wheel", parar, { passive: true });
    window.addEventListener("touchstart", parar, { passive: true });
    window.addEventListener("keydown", parar);
  }

  function correr() {
    animacao += 1;
    const meu = animacao;
    armarCancelamento();
    let anterior = null;

    const passo = (instante) => {
      if (meu !== animacao || destino === null) return;
      // An open drawer pauses the glide; closing it resumes.
      const gaveta = typeof document !== "undefined" && typeof document.querySelector === "function"
        ? document.querySelector(".gaveta")
        : null;
      if (gaveta && !gaveta.hidden) {
        anterior = null;
        velocidade = 0;
        window.requestAnimationFrame(passo);
        return;
      }

      // Capped, so a tab coming back from the background does not jump all at once.
      const dt = anterior === null ? 1 / 60 : Math.min(0.05, (instante - anterior) / 1000);
      anterior = instante;

      const actual = typeof window.scrollY === "number" ? window.scrollY : 0;
      const falta = destino - actual;
      if (Math.abs(falta) < 0.5) {
        window.scrollTo(0, destino);
        destino = null;
        velocidade = 0;
        if (soltarCancelamento) soltarCancelamento();
        return;
      }

      const desejada = Math.min(VELOCIDADE, Math.abs(falta) * TRAVAGEM);
      const salto = ACELERACAO * dt;
      velocidade = velocidade < desejada
        ? Math.min(desejada, velocidade + salto)
        : Math.max(desejada, velocidade - salto);

      const avanco = Math.min(Math.abs(falta), velocidade * dt);
      window.scrollTo(0, actual + Math.sign(falta) * avanco);
      window.requestAnimationFrame(passo);
    };
    window.requestAnimationFrame(passo);
  }

  /** Jumps straight to an element, without gliding: used for the progress panel on submit,
      while the glide is kept for the result. */
  function irJaPara(elemento) {
    ultimoRevelado = elemento;
    if (!elemento || elemento.hidden) return;
    if (typeof window === "undefined" || typeof elemento.getBoundingClientRect !== "function") return;
    pararAnimacao();
    const actual = typeof window.scrollY === "number" ? window.scrollY : 0;
    window.scrollTo(0, Math.max(0, elemento.getBoundingClientRect().top + actual - MARGEM_TOPO));
  }

  /** The result that just arrived becomes the target of the glide. */
  function revelar(elemento) {
    if (!elemento || elemento.hidden || elemento === ultimoRevelado) return;
    ultimoRevelado = elemento;
    if (desistido || movimentoReduzido()) return;
    if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return;
    if (typeof elemento.getBoundingClientRect !== "function") return;

    const actual = typeof window.scrollY === "number" ? window.scrollY : 0;
    const caixa = elemento.getBoundingClientRect();
    // Already fully in view and no glide running: nothing to do.
    if (destino === null && caixa.top >= MARGEM_TOPO && caixa.bottom <= (window.innerHeight || 0)) {
      return;
    }

    const emCurso = destino !== null;
    destino = caixa.top + actual - MARGEM_TOPO;
    // A running glide just takes the new target; restarting it would jolt the page.
    if (!emCurso) correr();
  }

  /* --- Input -------------------------------------------------------------- */

  const formulario = criarFormulario({
    aoSubmeter: (dados) => {
      dataDaClaim = dia(dados.claim_date);
      prepararProgresso();
      ctx.executar({ ...dados, exemplo_id: exemploEscolhido });
    },
  });

  const entrada = el("section", "entrada");
  const cabeca = el("div", "entrada__cabeca");
  const titulo = el("h1", "entrada__titulo");
  const nota = el("p", "entrada__nota");
  traduzivel(() => {
    titulo.textContent = t("entrada.titulo");
    nota.textContent = t("entrada.nota");
  });
  cabeca.append(titulo, nota);
  entrada.append(cabeca, formulario.elemento);

  // Editing a picked example makes it a new claim, which then runs through the models instead
  // of being served from the stored examples.
  formulario.elemento.addEventListener("input", () => {
    exemploEscolhido = null;
    entrada.dataset.exemplo = "";
  });

  function escolherExemplo(exemplo) {
    exemploEscolhido = exemplo.id;
    entrada.dataset.exemplo = exemplo.id;
    formulario.preencher(exemplo);
    dataDaClaim = dia(exemplo.claim_date);
    formulario.executar();
  }

  // One tooltip for every card, on the body: inside the carousel, the scrolling track would
  // clip it.
  let balao = null;
  // No tooltip while dragging: each `mouseenter` measures the layout and would force reflows
  // in the middle of the gesture.
  let aArrastar = false;

  function mostrarBalao(cartao, texto) {
    if (aArrastar) return;
    if (typeof document === "undefined" || typeof cartao.getBoundingClientRect !== "function") return;
    if (balao === null) {
      balao = el("div", "balao");
      balao.setAttribute("aria-hidden", "true");
      balao.hidden = true;
      document.body.append(balao);
    }
    balao.textContent = texto;
    balao.hidden = false;
    balao.dataset.visivel = "";
    const caixa = cartao.getBoundingClientRect();
    const largura = balao.offsetWidth || 300;
    const altura = balao.offsetHeight || 60;
    const janela = typeof window !== "undefined" ? window.innerWidth || 1024 : 1024;
    const esquerda = Math.min(Math.max(8, caixa.left + caixa.width / 2 - largura / 2), janela - largura - 8);
    const acimaCabe = caixa.top > altura + 12;
    balao.dataset.lado = acimaCabe ? "acima" : "abaixo";
    balao.style.setProperty("--x", `${Math.round(esquerda)}px`);
    balao.style.setProperty("--y", `${Math.round(acimaCabe ? caixa.top - altura - 8 : caixa.bottom + 8)}px`);
    balao.dataset.visivel = "true";
  }

  function esconderBalao() {
    if (!balao) return;
    balao.dataset.visivel = "";
    balao.hidden = true;
  }

  function cartaoExemplo(exemplo) {
    const cartao = botao("caso");
    const veredito = exemplo.veracity || "nei";
    cartao.dataset.veracity = veredito;
    const meta = el("span", "caso__meta");
    cartao.append(el("span", "caso__claim", exemplo.claim), meta);
    // The visible claim is clamped to two lines, so the label carries the full text and, as
    // colour is not announced, the verdict. The tooltip shows the full text too.
    traduzivel(() => {
      const data = dataCurta(exemplo.claim_date);
      meta.textContent = data;
      cartao.setAttribute("aria-label", `${exemplo.claim} - ${data} - ${t(`veredito.${veredito}`, {}, veredito)}`);
    });
    cartao.addEventListener("click", () => escolherExemplo(exemplo));
    cartao.addEventListener("mouseenter", () => mostrarBalao(cartao, exemplo.claim));
    cartao.addEventListener("focus", () => mostrarBalao(cartao, exemplo.claim));
    cartao.addEventListener("mouseleave", esconderBalao);
    cartao.addEventListener("blur", esconderBalao);
    return cartao;
  }

  // Dot sizes in px (plain, active, gap), matching app.css; used to fit the dots on one row.
  const PONTO = 6;
  const PONTO_MARCADO = 17;
  const PONTO_INTERVALO = 5;

  /** Looping carousel with position dots; nothing to scroll means no arrows and no dots. One
      arrow click moves exactly one dot, so the arrow step is derived from the dot count. */
  function criarCarrossel(exemplos) {
    const caixa = el("div", "carrossel");
    const pista = el("div", "carrossel__pista");
    exemplos.forEach((exemplo) => pista.append(cartaoExemplo(exemplo)));

    const anterior = botao("carrossel__seta carrossel__seta--antes");
    anterior.insertAdjacentHTML("beforeend", '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg>');

    const seguinte = botao("carrossel__seta carrossel__seta--depois");
    seguinte.insertAdjacentHTML("beforeend", '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg>');

    traduzivel(() => {
      anterior.setAttribute("aria-label", t("casos.anteriores"));
      seguinte.setAttribute("aria-label", t("casos.seguintes"));
    });

    const pontos = el("div", "carrossel__pontos");
    // The dots only show position (no tablist semantics): hidden from assistive technology and
    // out of the tab order, but still clickable. Keyboard users move through the cards.
    pontos.setAttribute("aria-hidden", "true");

    const limite = () => Math.max(0, pista.scrollWidth - pista.clientWidth);
    const rolavel = () => limite() > 4;

    // Target of the smooth scroll in progress: mid-scroll, `scrollLeft` is only part-way, so
    // the next arrow step starts from here.
    let alvo = 0;
    let deslocando = false;

    function irPara(posicao) {
      alvo = posicao;
      deslocando = true;
      pista.scrollTo({ left: posicao, behavior: movimentoReduzido() ? "auto" : "smooth" });
    }

    /** Start of the next arrow step: the pending target mid-scroll, else the real position. */
    function partida() {
      return deslocando ? alvo : pista.scrollLeft;
    }

    /** Drops the pending target: the smooth scroll arrived, or the reader took over the track. */
    function largarDestino() {
      deslocando = false;
      alvo = pista.scrollLeft;
    }

    // One step per dot; before there are dots, most of a track width.
    function passoDaSeta() {
      const total = pontos.children.length;
      if (total > 1) return limite() / (total - 1);
      return Math.max(200, pista.clientWidth * 0.85);
    }

    function rolar(sentido) {
      const fim = limite();
      const daqui = Math.min(fim, Math.max(0, partida()));
      let destino = daqui + sentido * passoDaSeta();
      if (sentido > 0 && daqui >= fim - 4) destino = 0;
      if (sentido < 0 && daqui <= 4) destino = fim;
      irPara(Math.min(fim, Math.max(0, destino)));
    }

    anterior.addEventListener("click", () => rolar(-1));
    seguinte.addEventListener("click", () => rolar(1));

    function quantosPontos() {
      const largura = Math.max(1, pista.clientWidth);
      // One dot per track width, so a step never skips a card.
      const paginas = Math.ceil(pista.scrollWidth / largura);
      // At most one row: the container wraps, and a second row of dots would read as
      // something else.
      const cabem = Math.floor((largura - (PONTO_MARCADO - PONTO)) / (PONTO + PONTO_INTERVALO));
      return Math.max(2, Math.min(paginas, cabem));
    }

    function marcarActivo() {
      const total = pontos.children.length;
      if (!total) return;
      const fim = limite();
      const fraccao = fim > 0 ? pista.scrollLeft / fim : 0;
      const activo = Math.round(fraccao * (total - 1));
      // `children` is an HTMLCollection, which has no `forEach`.
      Array.from(pontos.children).forEach((ponto, indice) => {
        ponto.dataset.activo = String(indice === activo);
      });
    }

    function desenharPontos() {
      const total = quantosPontos();
      if (pontos.children.length !== total) {
        pontos.replaceChildren();
        for (let indice = 0; indice < total; indice += 1) {
          const ponto = botao("carrossel__ponto");
          ponto.tabIndex = -1;
          ponto.addEventListener("click", () => irPara((indice / (total - 1)) * limite()));
          pontos.append(ponto);
        }
      }
      marcarActivo();
    }

    function actualizar() {
      largarDestino();
      const activo = rolavel();
      caixa.dataset.rolavel = String(activo);
      anterior.hidden = !activo;
      seguinte.hidden = !activo;
      pontos.hidden = !activo;
      if (activo) desenharPontos();
      else pontos.replaceChildren();
    }

    pista.addEventListener("wheel", largarDestino, { passive: true });
    pista.addEventListener("touchstart", largarDestino, { passive: true });

    let pendente = 0;
    let assentar = 0;
    pista.addEventListener("scroll", () => {
      // Reached the requested target: from here on the real position decides.
      if (deslocando && Math.abs(pista.scrollLeft - alvo) < 1) deslocando = false;
      if (typeof window !== "undefined" && typeof window.setTimeout === "function") {
        // Once the track settles (smooth scroll done, finger lifted), where it stopped
        // becomes the target.
        window.clearTimeout(assentar);
        assentar = window.setTimeout(largarDestino, 140);
      }
      if (pendente || typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return;
      pendente = window.requestAnimationFrame(() => {
        pendente = 0;
        marcarActivo();
      });
    });

    /* --- Grab and drag ------------------------------------------------------ */

    // Drag to scroll with the mouse: touch and trackpads already scroll the track natively.
    let agarrada = null;
    // The click that ends a drag must not open the card under the cursor.
    let ignorarClique = false;

    function largar(evento, cancelado) {
      if (agarrada === null || evento.pointerId !== agarrada.id) return;
      // A gesture cancelled by the browser fires no click, so arming the flag would swallow a
      // later, unrelated one.
      ignorarClique = agarrada.arrastou && !cancelado;
      aArrastar = false;
      const id = agarrada.id;
      agarrada = null;
      pista.dataset.agarrado = "";
      pista.dataset.arrasto = "";
      largarDestino();
      if (pista.hasPointerCapture && pista.hasPointerCapture(id)) pista.releasePointerCapture(id);
    }

    pista.addEventListener("pointerdown", (evento) => {
      ignorarClique = false;
      // Touch scrolls natively; only mouse and pen need this.
      if (evento.pointerType === "touch" || evento.button !== 0) return;
      // Nothing to scroll (the same condition that hides the arrows): leave the click alone.
      if (!rolavel()) return;
      // Freeze any smooth scroll in flight, or the position saved below goes stale.
      pista.scrollTo({ left: pista.scrollLeft, behavior: "auto" });
      largarDestino();
      agarrada = { x: evento.clientX, scroll: pista.scrollLeft, arrastou: false, id: evento.pointerId };
      pista.dataset.agarrado = "true";
    });

    pista.addEventListener("pointermove", (evento) => {
      if (agarrada === null || evento.pointerId !== agarrada.id) return;
      // Button already released: the `pointerup` was missed (there is no capture until the
      // drag starts), so drop the gesture.
      if ((evento.buttons & 1) === 0) {
        agarrada = null;
        aArrastar = false;
        pista.dataset.agarrado = "";
        pista.dataset.arrasto = "";
        return;
      }
      const andou = evento.clientX - agarrada.x;
      // Under 5px it is a click with some hand tremor, not a drag.
      if (!agarrada.arrastou && Math.abs(andou) < 5) return;

      // Only one read after the write: reading `scrollLeft` after setting it forces a
      // synchronous reflow.
      const antes = pista.scrollLeft;
      pista.scrollLeft = agarrada.scroll - andou;
      const depois = pista.scrollLeft;
      deslocando = false;
      alvo = depois;

      if (!agarrada.arrastou) {
        // Only moving the track counts as a drag; pushing against an end keeps the click.
        if (depois === antes) return;
        agarrada.arrastou = true;
        aArrastar = true;
        esconderBalao();
        pista.dataset.arrasto = "true";
        // Capture only once dragging: captured from `pointerdown`, the click would go to the
        // track instead of the card.
        if (pista.setPointerCapture) pista.setPointerCapture(evento.pointerId);
      }
      evento.preventDefault();
    });

    // On the window: until the drag starts there is no capture, and `pointerup` goes to
    // whatever is under the cursor.
    if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
      window.addEventListener("pointerup", (evento) => largar(evento, false));
      window.addEventListener("pointercancel", (evento) => largar(evento, true));
    }
    // Otherwise the browser may start a native drag and cancel the gesture.
    pista.addEventListener("dragstart", (evento) => evento.preventDefault());

    // Capture phase, to arrive before the card's own listener.
    pista.addEventListener("click", (evento) => {
      if (!ignorarClique) return;
      ignorarClique = false;
      // Keyboard clicks (Enter or Space) have `detail` 0 and never end a drag.
      if (evento.detail === 0) return;
      evento.preventDefault();
      evento.stopPropagation();
    }, true);

    caixa.append(anterior, pista, seguinte, pontos);

    // Measure after layout, and again whenever the track resizes.
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(actualizar);
    } else {
      actualizar();
    }
    if (typeof ResizeObserver === "function") {
      new ResizeObserver(actualizar).observe(pista);
    } else if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
      window.addEventListener("resize", actualizar);
    }

    return caixa;
  }

  const topicos = (ctx.topicos || []).filter((topico) => topico.exemplos && topico.exemplos.length);
  if (topicos.length) {
    const casos = el("div", "casos");
    // Cards wear their verdict as a tinted background; the CSS keys on this.
    casos.dataset.marca = "fundo";
    const cabecaCasos = el("div", "casos__cabeca");
    const tituloCasos = el("span", "casos__titulo");
    const notaCasos = el("span", "casos__nota");
    const total = topicos.reduce((n, topico) => n + topico.exemplos.length, 0);
    traduzivel(() => {
      tituloCasos.textContent = t("casos.titulo");
      notaCasos.textContent = t("casos.conta", { n: total });
    });
    cabecaCasos.append(tituloCasos, notaCasos);
    casos.append(cabecaCasos);

    // Colour legend: without it, nothing says what each card colour means.
    const legenda = el("ul", "legenda");
    traduzivel(() => legenda.setAttribute("aria-label", t("casos.legenda")));
    VEREDITOS.forEach((chave) => {
      const item = el("li", "legenda__item");
      item.dataset.veracity = chave;
      const nome = el("span", "legenda__nome");
      const explicacao = el("span", "legenda__nota");
      traduzivel(() => {
        nome.textContent = t(`veredito.${chave}`);
        explicacao.textContent = t(`veredito.${chave}.nota`);
      });
      item.append(el("span", "legenda__marca"), nome, explicacao);
      legenda.append(item);
    });
    casos.append(legenda);

    topicos.forEach((topico) => {
      const grupo = el("div", "topico");
      const cabeca = el("div", "topico__cabeca");
      const nome = el("h2", "topico__nome");
      // Named by its id; a topic without a translation keeps the name it came with.
      traduzivel(() => {
        nome.textContent = t(`topico.${topico.id}`, {}, topico.nome);
      });
      cabeca.append(nome);
      cabeca.append(el("span", "topico__conta", String(topico.exemplos.length)));
      grupo.append(cabeca, criarCarrossel(topico.exemplos));
      casos.append(grupo);
    });

    entrada.append(casos);
    const primeiro = topicos[0].exemplos[0];
    formulario.preencher(primeiro);
    exemploEscolhido = primeiro.id;
    entrada.dataset.exemplo = primeiro.id;
    dataDaClaim = dia(primeiro.claim_date);
  }

  /* --- Progress ------------------------------------------------------------ */

  const progresso = el("section", "progresso");
  progresso.hidden = true;
  const anuncio = el("p", "progresso__anuncio");
  anuncio.setAttribute("role", "status");
  const trilho = el("ol", "trilho");
  const cartoesPasso = new Map();

  PASSOS.forEach((passo, indice) => {
    const item = el("li", "etapa");
    item.dataset.status = "pending";
    const marca = el("span", "etapa__marca", String(indice + 1));
    const corpo = el("div", "etapa__corpo");
    const nome = el("span", "etapa__nome");
    traduzivel(() => {
      nome.textContent = t(`passo.${passo.id}`);
    });
    corpo.append(nome);
    const estado = el("span", "etapa__estado");
    corpo.append(estado);
    item.append(marca, corpo);
    trilho.append(item);
    cartoesPasso.set(passo.id, { item, marca, estado });
  });
  progresso.append(trilho, anuncio);

  /* --- Result -------------------------------------------------------------- */

  const resultado = el("section", "resultado");
  resultado.hidden = true;

  const blocoPerguntas = el("div", "bloco");
  blocoPerguntas.hidden = true;
  const perguntasTopo = el("div", "bloco__topo");
  const tituloPerguntas = el("h2", "bloco__titulo");
  perguntasTopo.append(tituloPerguntas);
  const listaPerguntas = el("ol", "perguntas");
  blocoPerguntas.append(perguntasTopo, listaPerguntas);

  const eixo = el("div", "bloco");
  eixo.hidden = true;
  const eixoTopo = el("div", "bloco__topo");
  const tituloEixo = el("h2", "bloco__titulo");
  eixoTopo.append(tituloEixo);
  const pista = el("div", "pista");
  const regua = el("div", "regua");
  const leitura = el("p", "leitura");
  eixo.append(eixoTopo, pista, regua, leitura);

  const balanco = el("div", "bloco");
  balanco.hidden = true;
  const balancoTopo = el("div", "bloco__topo");
  const tituloBalanco = el("h2", "bloco__titulo");
  balancoTopo.append(tituloBalanco);
  const cartoes = el("div", "cartoes");
  const totalEvidencias = el("p", "balanco__total");
  balanco.append(balancoTopo, cartoes, totalEvidencias);

  traduzivel(() => {
    tituloPerguntas.textContent = t("bloco.perguntas");
    tituloEixo.textContent = t("bloco.eixo");
    tituloBalanco.textContent = t("bloco.balanco");
  });

  resultado.append(blocoPerguntas, eixo, balanco);

  const artigo = el("article", "artigo");
  artigo.hidden = true;

  const palco = el("div", "ideal");
  palco.append(entrada, progresso, resultado, artigo);
  raiz.append(palco);

  function prepararProgresso() {
    preparado = true;
    recuperados = [];
    documentos = [];
    classificacao = null;
    artigoDesenhado = null;
    estados.clear();
    motivos.clear();
    ultimoRevelado = null;
    desistido = false;
    pararAnimacao();
    progresso.hidden = false;
    resultado.hidden = true;
    blocoPerguntas.hidden = true;
    eixo.hidden = true;
    balanco.hidden = true;
    artigo.hidden = true;
    actualizarPassos();
    irJaPara(progresso);
  }

  function desenharPerguntas(lista) {
    listaPerguntas.replaceChildren();
    lista.forEach((pergunta) => {
      const item = el("li", "pergunta");
      item.append(el("span", "pergunta__n", `Q${pergunta.index}`));
      item.append(el("span", null, pergunta.text));
      listaPerguntas.append(item);
    });
    blocoPerguntas.hidden = false;
  }

  /* --- Timeline ------------------------------------------------------------- */

  const marcadores = new Map();
  // Scale of the drawn axis, kept so the ruler can be redrawn when the track width changes.
  let escala = null;

  // Width budget per tick label: the widest ("nov 24", about 43px) plus room between ticks.
  const LARGURA_POR_MARCA = 56;

  /** Ticks this close to the axis end are skipped: they would land on the claim wall. */
  const LIMIAR_ENCOSTO = 0.02;

  function desenharRegua() {
    regua.replaceChildren();
    if (escala === null) return;
    const largura = Math.max(1, pista.clientWidth);
    const tecto = Math.max(2, Math.min(8, Math.floor(largura / LARGURA_POR_MARCA)));
    marcasDoEixo(escala.inicio, escala.fim, tecto).forEach(({ pos, etiqueta }) => {
      const colocada = pos / 100;
      if (1 - colocada < LIMIAR_ENCOSTO) return;
      const marca = el("span", "regua__marca", etiqueta);
      // The tick at the axis start is left-aligned, so its label stays inside the track.
      if (colocada <= 0.0001) marca.classList.add("regua__marca--inicio");
      marca.style.setProperty("--pos", colocada.toFixed(5));
      regua.append(marca);
    });
    aliviarRegua();
  }

  /** Removes, once drawn, the ticks that overlap the previous one: the cap on the tick count
      only estimates label widths. The first tick always stays. */
  function aliviarRegua() {
    const FOLGA = 6;
    let limite = -Infinity;
    // Copied from the live HTMLCollection, which has no `forEach` and shrinks on removal.
    Array.from(regua.children).forEach((marca) => {
      const caixa = marca.getBoundingClientRect();
      if (!caixa.width) return;
      if (caixa.left < limite + FOLGA) {
        marca.remove();
        return;
      }
      limite = caixa.right;
    });
  }

  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => desenharRegua()).observe(pista);
  }

  /** The wall at the end of the axis, with the claim date labelled above it rather than on
      the ruler, where it would read as one more news date. */
  function parede(fim, eDaClaim) {
    const linha = el("div", "parede");
    const etiqueta = el("span", "parede__etiqueta");
    // When the axis ends on the latest news instead of the claim date, the label says so.
    etiqueta.append(el("span", "parede__nome", eDaClaim ? t("eixo.claim") : t("eixo.ultima")));
    etiqueta.append(el("span", "parede__data", dataCurta(fim.toISOString())));
    linha.append(etiqueta);
    pista.append(linha);
  }

  function desenharEixo(lista) {
    pista.replaceChildren();
    marcadores.clear();
    escala = null;
    regua.replaceChildren();

    const comData = lista
      .map((documento) => ({ documento, data: dia(documento.published_at) }))
      .filter((registo) => registo.data !== null)
      .sort((a, b) => a.data - b.data);
    if (!comData.length) {
      eixo.hidden = true;
      return;
    }

    const maisAntiga = comData[0].data;
    const ultima = comData[comData.length - 1].data;
    // A claim date before the oldest news would collapse the scale, so the axis then ends on
    // the latest news.
    const eDaClaim = Boolean(dataDaClaim && dataDaClaim > maisAntiga);
    const fim = eDaClaim ? dataDaClaim : ultima;
    const inicio = inicioDoEixo(maisAntiga, fim);
    const amplitude = Math.max(DIA_MS, fim - inicio);

    pista.append(el("div", "pista__linha"));

    parede(fim, eDaClaim);

    const niveis = [];
    comData.forEach(({ documento, data }) => {
      const posicao = Math.min(1, Math.max(0, (data - inicio) / amplitude));
      let nivel = 0;
      while (niveis[nivel] !== undefined && posicao - niveis[nivel] < 0.032) nivel += 1;
      niveis[nivel] = posicao;

      const marcador = botao("marcador");
      marcador.style.setProperty("--pos", posicao.toFixed(5));
      marcador.style.setProperty("--nivel", String(nivel));
      marcador.dataset.rotulo = "pendente";
      marcador.setAttribute(
        "aria-label",
        t("eixo.marcador", { titulo: documento.headline, data: dataLonga(documento.published_at) })
      );
      const mostrar = () => {
        leitura.replaceChildren(
          el("strong", null, dataLonga(documento.published_at)),
          el("span", null, ` - ${documento.headline}`)
        );
      };
      marcador.addEventListener("mouseenter", mostrar);
      marcador.addEventListener("focus", mostrar);
      marcador.addEventListener("click", () => ctx.abrirDocumento(documento.doc_id, null, marcador));
      pista.append(marcador);
      marcadores.set(documento.doc_id, marcador);
    });
    pista.style.setProperty("--niveis", String(niveis.length));

    leitura.textContent = t("eixo.leitura");
    // Unhidden before drawing the ruler: the tick count depends on the measured width.
    eixo.hidden = false;
    escala = { inicio, fim };
    desenharRegua();
  }

  function colorirEixo(stances, decisivos) {
    const porExcerto = new Map(stances.map((estado) => [estado.excerpt_id, estado]));
    documentos.forEach((documento) => {
      const marcador = marcadores.get(documento.doc_id);
      if (!marcador) return;
      const rotulos = new Set(
        decisivos
          .filter((id) => id.startsWith(`${documento.doc_id}-`))
          .map((id) => porExcerto.get(id))
          .filter(Boolean)
          .map((estado) => estado.label)
      );
      if (rotulos.has("supported") && rotulos.has("refuted")) marcador.dataset.rotulo = "ambos";
      else if (rotulos.has("supported")) marcador.dataset.rotulo = "supported";
      else if (rotulos.has("refuted")) marcador.dataset.rotulo = "refuted";
      else marcador.dataset.rotulo = "nei";
    });
  }

  /** Counts evidence (distinct news), not excerpts. A news item with passages on both sides
      counts in both, so the total is shown separately. */
  function desenharBalanco(stances, decisivos) {
    // Excerpt ids start with "<doc_id>-", which ties each decisive excerpt to its news item
    // (as in `colorirEixo`).
    const rotuloPorExcerto = new Map(stances.map((estado) => [estado.excerpt_id, estado.label]));
    const contagem = { supported: 0, refuted: 0, nei: 0 };

    documentos.forEach((documento) => {
      const rotulos = new Set(
        decisivos
          .filter((id) => id.startsWith(`${documento.doc_id}-`))
          .map((id) => rotuloPorExcerto.get(id))
          .filter(Boolean)
      );
      if (!rotulos.size) contagem.nei += 1;
      if (rotulos.has("supported")) contagem.supported += 1;
      if (rotulos.has("refuted")) contagem.refuted += 1;
    });

    cartoes.replaceChildren();
    BALANCO.forEach((rotulo) => {
      const cartao = el("div", `cartao cartao--${rotulo}`);
      cartao.append(el("span", "cartao__numero", String(contagem[rotulo])));
      cartao.append(el("span", "cartao__rotulo", t(`balanco.${rotulo}`)));
      cartoes.append(cartao);
    });

    const total = documentos.length;
    // The number is set in bold, so the sentence comes as the text before and after it.
    const [antes, depois] = t("balanco.total", { n: total });
    totalEvidencias.replaceChildren(
      document.createTextNode(antes),
      el("strong", null, String(total)),
      document.createTextNode(depois)
    );
    balanco.hidden = false;
  }

  /* --- Article --------------------------------------------------------------- */

  function realcar(docId, activo) {
    const marcador = marcadores.get(docId);
    if (marcador) marcador.dataset.aceso = String(activo);
  }

  function desenharArtigo(dados) {
    artigo.replaceChildren();
    const cabecalho = el("div", "artigo__cabecalho");
    cabecalho.append(el("span", "selo", t("artigo.selo")));
    cabecalho.append(el("h2", "artigo__titulo", dados.title));
    // The lead carries citation markers too, like the body.
    const lead = el("p", "artigo__lead");
    lead.append(comCitacoes(dados.lead, dados.citations, ctx.abrirCitacao));
    cabecalho.append(lead);

    const texto = el("div", "artigo__corpo");
    dados.blocks.forEach((bloco) => {
      if (bloco.type === "heading") {
        texto.append(el("h3", null, bloco.text));
      } else {
        const paragrafo = el("p");
        paragrafo.append(comCitacoes(bloco.text, dados.citations, ctx.abrirCitacao));
        texto.append(paragrafo);
      }
    });

    // No footer when nothing is cited (an article written without decisive evidence).
    const comCitacoes_ = (dados.citations || []).length > 0;
    const rodape = el("footer", "artigo__rodape");
    rodape.hidden = !comCitacoes_;
    rodape.append(el("h3", null, t("artigo.citada")));
    const fontes = el("ol", "fontes");
    dados.citations.forEach((citacao) => {
      const item = el("li");
      const alvo = botao("fonte");
      alvo.append(el("span", "fonte__n", citacao.marker));
      const conteudo = el("div", "fonte__conteudo");
      conteudo.append(el("div", "fonte__titulo", citacao.headline));
      const meta = el("div", "fonte__meta");
      meta.append(el("span", null, dataCurta(citacao.published_at)));
      meta.append(el("span", `rotulo rotulo--${citacao.label}`, nomeRotulo(citacao.label)));
      conteudo.append(meta);
      alvo.append(conteudo);
      alvo.addEventListener("click", () => ctx.abrirCitacao(citacao, alvo));
      alvo.addEventListener("mouseenter", () => realcar(citacao.doc_id, true));
      alvo.addEventListener("mouseleave", () => realcar(citacao.doc_id, false));
      item.append(alvo);
      fontes.append(item);
    });
    rodape.append(fontes);

    artigo.append(cabecalho, texto, rodape);
    artigo.hidden = false;
  }

  /* --- Step state ------------------------------------------------------------- */

  const estados = new Map();
  const motivos = new Map();

  function passoDe(etapa) {
    return PASSOS.find((passo) => passo.etapas.includes(etapa));
  }

  function actualizarPassos() {
    let emCurso = null;
    PASSOS.forEach((passo, indice) => {
      const cartao = cartoesPasso.get(passo.id);
      const situacoes = passo.etapas.map((etapa) => estados.get(etapa) || "pending");
      // A step is skipped only if all its stages were; one skipped stage does not skip it.
      let estado = "pending";
      if (situacoes.includes("error")) estado = "error";
      else if (situacoes.includes("running")) estado = "running";
      else if (situacoes.includes("done")) {
        estado = situacoes.every((s) => s === "done" || s === "skipped") ? "done" : "pending";
      } else if (situacoes.every((situacao) => situacao === "skipped")) estado = "skipped";

      cartao.item.dataset.status = estado;
      cartao.marca.textContent = estado === "done" ? "✓" : estado === "error" ? "!" : String(indice + 1);
      cartao.estado.textContent =
        estado === "error" ? motivos.get(passo.id) || t("passo.falhou")
        : estado === "running" ? t("passo.emCurso")
        : "";
      if (estado === "running" && emCurso === null) emCurso = passo;
    });
    anuncio.textContent = emCurso ? t(`passo.${emCurso.id}.trabalho`) : "";
    progresso.dataset.activo = String(emCurso !== null);
  }

  /* --- Language ------------------------------------------------------------------ */

  // The result blocks hold dates, counts and labels in the interface's language: a switch
  // redraws them from what they were drawn from. What the models wrote stays as it is.
  aoMudarLingua(() => {
    actualizarPassos();
    if (!eixo.hidden) {
      desenharEixo(documentos);
      if (classificacao) colorirEixo(classificacao.stances, classificacao.decisivos);
    }
    if (!balanco.hidden && classificacao) desenharBalanco(classificacao.stances, classificacao.decisivos);
    if (!artigo.hidden && artigoDesenhado) desenharArtigo(artigoDesenhado);
  });

  /* --- Run events ---------------------------------------------------------------- */

  return {
    aoEvento(evento) {
      if (evento.type === "start") {
        // Submitting already prepared the page; only prepare it here if that did not happen.
        if (!preparado) prepararProgresso();
        preparado = false;
        return;
      }
      if (evento.type !== "stage") return;

      const etapa = evento.stage;
      estados.set(etapa.name, etapa.status);
      if (etapa.status === "error") {
        const passo = passoDe(etapa.name);
        if (passo) motivos.set(passo.id, etapa.detail);
      }
      actualizarPassos();

      if (evento.questions && evento.questions.length) {
        desenharPerguntas(evento.questions);
        resultado.hidden = false;
        revelar(resultado);
      }
      if (evento.documents && evento.documents.length) recuperados = evento.documents;
      // The axis shows evidence only: it waits for the relevance stage and leaves out what it
      // ruled unrelated. If that stage was skipped or failed, nothing is left out.
      if (etapa.name === "relevance" && ["done", "skipped", "error"].includes(etapa.status)) {
        documentos = recuperados.filter((documento) => documento.relevant !== false);
        if (documentos.length) {
          desenharEixo(documentos);
          resultado.hidden = false;
          revelar(eixo);
        }
      }
      if (evento.stances) {
        classificacao = { stances: evento.stances, decisivos: evento.decisive || [] };
        colorirEixo(classificacao.stances, classificacao.decisivos);
        desenharBalanco(classificacao.stances, classificacao.decisivos);
        resultado.hidden = false;
        revelar(balanco);
      }
      if (evento.article) {
        artigoDesenhado = evento.article;
        desenharArtigo(evento.article);
        revelar(artigo);
      }
    },
    aoOcupado(activo) {
      formulario.ocupado(activo);
      palco.dataset.ocupado = String(activo);
    },
    aoErro(mensagem) {
      formulario.erro(mensagem);
      if (mensagem && resultado.hidden) revelar(entrada);
    },
  };
}
