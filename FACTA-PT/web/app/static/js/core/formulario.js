/** Input form: claim, date and optional context, with validation. Returns the element and the
    operations the view uses on it. */

import { el } from "./dom.js";
import { criarCalendario } from "./calendario.js";
import { aoMudarLingua, t } from "./i18n.js";

export function criarFormulario({ aoSubmeter }) {
  const forma = el("form", "forma");
  forma.noValidate = true;

  const campoClaim = el("div", "campo");
  const etiquetaClaim = el("label");
  etiquetaClaim.htmlFor = "campo-claim";
  // A single-line `input`: a one-row `textarea` scrolls vertically once the text overflows
  // and no longer lines up with the date field.
  const claim = el("input");
  claim.id = "campo-claim";
  claim.type = "text";
  campoClaim.append(etiquetaClaim, claim);

  const campoData = el("div", "campo");
  const rotuloData = el("label");
  const pista = el("span", "campo__pista");
  const selector = criarCalendario({ id: "campo-data", rotulo: () => t("form.data") });
  rotuloData.htmlFor = selector.rotuloPara;
  campoData.append(rotuloData, selector.elemento, pista);

  const campoContexto = el("div", "campo");
  const rotuloContexto = el("label");
  rotuloContexto.htmlFor = "campo-contexto";
  const contexto = el("textarea");
  contexto.id = "campo-contexto";
  contexto.rows = 4;
  campoContexto.append(rotuloContexto, contexto);

  const accao = el("div", "forma__accao");
  const submeter = el("button", "botao botao--primario");
  submeter.type = "submit";
  const texto = el("span", "botao__texto");
  submeter.append(texto);
  submeter.insertAdjacentHTML(
    "beforeend",
    '<svg class="botao__seta" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h13m-5-6 6 6-6 6"/></svg>'
  );
  const limpar = el("button", "botao botao--fantasma");
  limpar.type = "button";
  accao.append(submeter, limpar);

  const erro = el("p", "erro");
  erro.hidden = true;
  erro.setAttribute("role", "alert");

  forma.append(campoClaim, campoData, campoContexto, accao, erro);

  let ocupado = false;
  // The message shown: a text, or a function giving it in the current language.
  let mensagemDeErro = null;

  function escreverErro() {
    const atual = typeof mensagemDeErro === "function" ? mensagemDeErro() : mensagemDeErro;
    erro.textContent = atual || "";
    erro.hidden = !atual;
  }

  function mostrarErro(mensagem) {
    mensagemDeErro = mensagem || null;
    escreverErro();
  }

  function textos() {
    etiquetaClaim.textContent = t("form.claim");
    claim.placeholder = t("form.claimPista");
    rotuloData.textContent = t("form.data");
    pista.textContent = t("form.dataPista");
    rotuloContexto.replaceChildren(t("form.contexto"), " ", el("span", "campo__opcional", t("form.opcional")));
    // The model only reads one sentence either side of the claim
    // (`inference/server/textutils.py`), so a paragraph is enough.
    contexto.placeholder = t("form.contextoPista");
    texto.textContent = ocupado ? t("form.aVerificar") : t("form.verificar");
    limpar.textContent = t("form.limpar");
    escreverErro();
  }

  textos();
  aoMudarLingua(textos);

  forma.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const entrada = {
      claim: claim.value.trim(),
      claim_date: selector.campo.value,
      context: contexto.value.trim(),
    };
    if (entrada.claim.length < 8) {
      mostrarErro(() => t("form.erroClaim"));
      claim.focus();
      return;
    }
    if (!entrada.claim_date) {
      mostrarErro(() => t("form.erroData"));
      selector.focar();
      return;
    }
    mostrarErro(null);
    aoSubmeter(entrada);
  });

  limpar.addEventListener("click", () => {
    claim.value = "";
    selector.definir("");
    contexto.value = "";
    mostrarErro(null);
    claim.focus();
  });

  return {
    elemento: forma,
    preencher(caso) {
      claim.value = caso.claim || "";
      selector.definir((caso.claim_date || "").slice(0, 10));
      contexto.value = caso.context || "";
      mostrarErro(null);
    },
    executar() {
      forma.requestSubmit();
    },
    ocupado(activo) {
      ocupado = activo;
      submeter.disabled = activo;
      submeter.classList.toggle("ocupado", activo);
      texto.textContent = activo ? t("form.aVerificar") : t("form.verificar");
    },
    erro: mostrarErro,
  };
}
