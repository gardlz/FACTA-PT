/** Date picker in the interface's language, drawn as part of the page: the native
    `<input type="date">` cannot be styled and looks different on each system. The value is kept
    as `YYYY-MM-DD` in a hidden field. */

import { el, botao } from "./dom.js";
import { aoMudarLingua, t } from "./i18n.js";

const SETA_ESQUERDA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg>';
const SETA_DIREITA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg>';

function iso(data) {
  const mes = String(data.getMonth() + 1).padStart(2, "0");
  const dia = String(data.getDate()).padStart(2, "0");
  return `${data.getFullYear()}-${mes}-${dia}`;
}

/** `YYYY-MM-DD` -> local Date, or null. Impossible dates are rejected: the Date constructor
    silently rolls them over (31 February becomes a day in March). */
export function deIso(texto) {
  const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(texto || ""));
  if (!partes) return null;
  const ano = Number(partes[1]);
  const mes = Number(partes[2]) - 1;
  const dia = Number(partes[3]);
  const data = new Date(ano, mes, dia);
  if (data.getFullYear() !== ano || data.getMonth() !== mes || data.getDate() !== dia) return null;
  return data;
}

function porExtenso(data) {
  return t("cal.porExtenso", { dia: data.getDate(), mes: t("cal.meses")[data.getMonth()], ano: data.getFullYear() });
}

/** Weekday index with Monday first, as in the Portuguese and British calendars. */
function diaDaSemana(data) {
  return (data.getDay() + 6) % 7;
}

function ultimoDiaDoMes(ano, mes) {
  return new Date(ano, mes + 1, 0).getDate();
}

/** Same date in another month, without overflowing: 31 January + 1 month is 28 or 29 February. */
function deslocarMeses(data, meses) {
  const alvo = new Date(data.getFullYear(), data.getMonth() + meses, 1);
  const dia = Math.min(data.getDate(), ultimoDiaDoMes(alvo.getFullYear(), alvo.getMonth()));
  return new Date(alvo.getFullYear(), alvo.getMonth(), dia);
}

/** `rotulo` names the field, as a function so that it follows the language. */
export function criarCalendario({ id, rotulo = () => t("cal.escolher") } = {}) {
  const guardado = el("input");
  guardado.type = "hidden";
  guardado.id = `${id}-valor`;

  const invólucro = el("div", "calendario");

  // The field's label targets this button: a hidden input can be neither labelled nor focused.
  const alvo = botao("calendario__alvo");
  alvo.id = id;
  alvo.setAttribute("aria-haspopup", "dialog");
  alvo.setAttribute("aria-expanded", "false");
  const texto = el("span", "calendario__texto");
  alvo.append(texto);
  alvo.insertAdjacentHTML(
    "beforeend",
    '<svg class="calendario__icone" viewBox="0 0 24 24" aria-hidden="true">' +
      '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>'
  );

  const painel = el("div", "calendario__painel");
  painel.hidden = true;
  painel.setAttribute("role", "dialog");

  const cabeca = el("div", "calendario__cabeca");
  const mesAtras = botao("calendario__navegar");
  mesAtras.insertAdjacentHTML("beforeend", SETA_ESQUERDA);

  const titulo = el("span", "calendario__mes");
  titulo.setAttribute("aria-live", "polite");

  // A select for the year: with month arrows alone, a date a few years back is dozens of
  // clicks away.
  const selectorAno = el("select", "calendario__ano");
  const anoCorrente = new Date().getFullYear();
  for (let ano = anoCorrente + 1; ano >= anoCorrente - 60; ano -= 1) {
    const opcao = el("option", null, String(ano));
    opcao.value = String(ano);
    selectorAno.append(opcao);
  }

  const mesFrente = botao("calendario__navegar");
  mesFrente.insertAdjacentHTML("beforeend", SETA_DIREITA);
  cabeca.append(mesAtras, titulo, selectorAno, mesFrente);

  const semana = el("div", "calendario__semana");
  for (let indice = 0; indice < 7; indice += 1) semana.append(el("abbr", "calendario__inicial"));

  const grelha = el("div", "calendario__grelha");
  grelha.setAttribute("role", "grid");

  const rodape = el("div", "calendario__rodape");
  const hoje = botao("calendario__atalho");
  const fechar = botao("calendario__atalho");
  rodape.append(hoje, fechar);

  painel.append(cabeca, semana, grelha, rodape);
  invólucro.append(guardado, alvo, painel);

  let visivel = new Date();
  let seleccionada = null;
  let focada = new Date();

  function mostrarValor() {
    texto.textContent = seleccionada ? porExtenso(seleccionada) : t("cal.escolher");
    invólucro.dataset.preenchido = String(Boolean(seleccionada));
    alvo.setAttribute(
      "aria-label",
      seleccionada
        ? t("cal.escolhida", { rotulo: rotulo(), data: porExtenso(seleccionada) })
        : t("cal.porEscolher", { rotulo: rotulo() })
    );
  }

  /** Every fixed text of the picker, in the current language; an open panel is redrawn. */
  function textos() {
    painel.setAttribute("aria-label", rotulo());
    grelha.setAttribute("aria-label", rotulo());
    mesAtras.setAttribute("aria-label", t("cal.mesAnterior"));
    mesFrente.setAttribute("aria-label", t("cal.mesSeguinte"));
    selectorAno.setAttribute("aria-label", t("cal.ano"));
    hoje.textContent = t("cal.hoje");
    fechar.textContent = t("cal.fechar");
    const curtos = t("cal.diasCurtos");
    const longos = t("cal.diasLongos");
    Array.from(semana.children).forEach((inicial, indice) => {
      inicial.textContent = curtos[indice];
      inicial.title = longos[indice];
    });
    mostrarValor();
    if (!painel.hidden) desenhar();
  }

  function mesmoDia(a, b) {
    return Boolean(
      a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
    );
  }

  function desenhar() {
    titulo.textContent = t("cal.meses")[visivel.getMonth()];
    selectorAno.value = String(visivel.getFullYear());
    grelha.replaceChildren();

    const primeiro = new Date(visivel.getFullYear(), visivel.getMonth(), 1);
    const inicio = new Date(primeiro.getFullYear(), primeiro.getMonth(), 1 - diaDaSemana(primeiro));
    const agora = new Date();

    // ARIA grid cells must sit inside rows, or screen readers cannot announce their position.
    for (let linha = 0; linha < 6; linha += 1) {
      const fila = el("div", "calendario__fila");
      fila.setAttribute("role", "row");
      for (let coluna = 0; coluna < 7; coluna += 1) {
        const numero = linha * 7 + coluna;
        const dia = new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + numero);
        const celula = botao("calendario__dia", String(dia.getDate()));
        celula.setAttribute("role", "gridcell");
        celula.dataset.fora = String(dia.getMonth() !== visivel.getMonth());
        celula.dataset.hoje = String(mesmoDia(dia, agora));
        celula.setAttribute("aria-label", porExtenso(dia));
        if (mesmoDia(dia, seleccionada)) {
          celula.dataset.escolhido = "true";
          celula.setAttribute("aria-selected", "true");
        }
        celula.tabIndex = mesmoDia(dia, focada) ? 0 : -1;
        celula.addEventListener("click", () => escolher(dia));
        fila.append(celula);
      }
      grelha.append(fila);
    }

    // Keep one cell reachable with Tab: if the focused day is not drawn, the first day of the
    // month takes its place.
    if (!grelha.querySelector('[tabindex="0"]')) {
      const primeiroDoMes = grelha.querySelectorAll('[data-fora="false"]')[0];
      if (primeiroDoMes) primeiroDoMes.tabIndex = 0;
    }
  }

  function focarDia(dia) {
    focada = dia;
    visivel = new Date(dia.getFullYear(), dia.getMonth(), 1);
    desenhar();
    const celula = grelha.querySelector('[tabindex="0"]');
    if (celula) celula.focus();
  }

  function navegar(meses) {
    focarDia(deslocarMeses(focada, meses));
  }

  function escolher(dia) {
    seleccionada = dia;
    focada = dia;
    guardado.value = iso(dia);
    mostrarValor();
    abrirPainel(false);
    alvo.focus();
  }

  function foraDoPainel(evento) {
    const dentro = evento.target === invólucro || (invólucro.contains && invólucro.contains(evento.target));
    if (!dentro) abrirPainel(false);
  }

  function abrirPainel(abrir) {
    const estavaAberto = !painel.hidden;
    painel.hidden = !abrir;
    alvo.setAttribute("aria-expanded", String(abrir));
    if (abrir) {
      focada = seleccionada || new Date();
      visivel = new Date(focada.getFullYear(), focada.getMonth(), 1);
      desenhar();
      const celula = grelha.querySelector('[tabindex="0"]');
      if (celula) celula.focus();
      // The outside-click listener lives only while the panel is open.
      if (!estavaAberto) document.addEventListener("click", foraDoPainel);
    } else if (estavaAberto) {
      document.removeEventListener("click", foraDoPainel);
    }
  }

  alvo.addEventListener("click", () => abrirPainel(painel.hidden));
  mesAtras.addEventListener("click", () => navegar(-1));
  mesFrente.addEventListener("click", () => navegar(1));
  selectorAno.addEventListener("change", () => {
    const ano = Number(selectorAno.value);
    const mes = focada.getMonth();
    focarDia(new Date(ano, mes, Math.min(focada.getDate(), ultimoDiaDoMes(ano, mes))));
  });
  hoje.addEventListener("click", () => escolher(new Date()));
  fechar.addEventListener("click", () => {
    abrirPainel(false);
    alvo.focus();
  });

  const PASSOS = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };

  // Escape closes from anywhere in the panel; navigation keys belong to the grid. Enter is not
  // handled here, so every button keeps its own activation.
  painel.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") {
      evento.preventDefault();
      abrirPainel(false);
      alvo.focus();
    }
  });

  grelha.addEventListener("keydown", (evento) => {
    if (PASSOS[evento.key] !== undefined) {
      evento.preventDefault();
      focarDia(new Date(focada.getFullYear(), focada.getMonth(), focada.getDate() + PASSOS[evento.key]));
      return;
    }
    if (evento.key === "PageUp" || evento.key === "PageDown") {
      evento.preventDefault();
      const salto = evento.key === "PageUp" ? -1 : 1;
      navegar(evento.shiftKey ? salto * 12 : salto);
      return;
    }
    if (evento.key === "Home" || evento.key === "End") {
      evento.preventDefault();
      const deslocamento = evento.key === "Home" ? -diaDaSemana(focada) : 6 - diaDaSemana(focada);
      focarDia(new Date(focada.getFullYear(), focada.getMonth(), focada.getDate() + deslocamento));
    }
  });

  textos();
  aoMudarLingua(textos);

  return {
    elemento: invólucro,
    campo: guardado,
    rotuloPara: alvo.id,
    definir(valor) {
      const data = deIso(valor);
      seleccionada = data;
      guardado.value = data ? iso(data) : "";
      mostrarValor();
      if (!painel.hidden) {
        focada = data || new Date();
        visivel = new Date(focada.getFullYear(), focada.getMonth(), 1);
        desenhar();
      }
    },
    focar() {
      alvo.focus();
    },
  };
}
