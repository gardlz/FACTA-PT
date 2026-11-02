/** Input form: claim, date, optional context, how many news items each question keeps and the
    model that writes the article, with validation. Returns the element and the operations the
    view uses on it. */

import { botao, el } from "./dom.js";
import { criarCalendario } from "./calendario.js";
import { aoMudarLingua, t } from "./i18n.js";

/** A choice the run makes, as a segmented control over the options the server offers
    (`{valor, texto}`). Buttons, which fire no input event: one inside the form reads as the
    claim being edited and turns a picked example into a new claim. */
function criarEscolha(nome, opcoes, omissao, aoMudar = () => {}) {
  const grupo = el("div", `escolha escolha--${nome}`);
  const rotulo = el("span", "escolha__rotulo");
  rotulo.id = `escolha-${nome}`;
  const botoes = el("div", "segmentos");
  botoes.setAttribute("role", "group");
  botoes.setAttribute("aria-labelledby", rotulo.id);
  grupo.append(rotulo, botoes);

  let valor = opcoes.some((o) => o.valor === omissao) ? omissao : opcoes[0].valor;
  const opcoesBotoes = opcoes.map(({ valor: deste, texto }) => {
    const opcao = botao("segmentos__opcao", texto);
    opcao.addEventListener("click", () => {
      if (deste === valor) return;
      valor = deste;
      marcar();
      aoMudar(deste);
    });
    botoes.append(opcao);
    return { deste, opcao };
  });

  function marcar() {
    opcoesBotoes.forEach(({ deste, opcao }) => opcao.setAttribute("aria-pressed", String(deste === valor)));
  }
  marcar();

  return { elemento: grupo, rotulo, valor: () => valor };
}

export function criarFormulario({ aoSubmeter, quantidade = null, redatores = null, aoMudarQuantidade = () => {} }) {
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

  // What the run chooses: how many news items each question keeps, and the model that writes the
  // article. The options come from the server.
  const escolhaQuantidade = quantidade && quantidade.opcoes && quantidade.opcoes.length
    ? criarEscolha("quantidade", quantidade.opcoes.map((n) => ({ valor: n, texto: String(n) })),
                   quantidade.omissao, aoMudarQuantidade)
    : null;
  const escolhaRedator = redatores && redatores.opcoes && redatores.opcoes.length
    ? criarEscolha("redator", redatores.opcoes.map((r) => ({ valor: r.id, texto: r.nome })),
                   redatores.omissao)
    : null;
  const escolhas = el("div", "forma__opcoes");
  [escolhaQuantidade, escolhaRedator].filter(Boolean).forEach((escolha) => escolhas.append(escolha.elemento));

  const erro = el("p", "erro");
  erro.hidden = true;
  erro.setAttribute("role", "alert");

  forma.append(campoClaim, campoData, campoContexto);
  if (escolhas.children.length) forma.append(escolhas);
  forma.append(accao, erro);

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
    if (escolhaQuantidade) escolhaQuantidade.rotulo.textContent = t("form.quantidade");
    if (escolhaRedator) escolhaRedator.rotulo.textContent = t("form.redator");
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
    if (escolhaQuantidade) entrada.top_k = escolhaQuantidade.valor();
    if (escolhaRedator) entrada.redator = escolhaRedator.valor();
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
