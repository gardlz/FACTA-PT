/** Interface language: European Portuguese (default) or English. Only the interface is
    translated; the questions, news items and articles keep the language they come in. */

const CHAVE = "facta-pt:lingua";
export const LINGUAS = ["pt", "en"];

const TEXTOS = {
  pt: {
    "pagina.titulo": "FACTA-PT",
    "pagina.descricao": "Da claim ao artigo de verificação: perguntas, evidência da Lusa, classificação e texto com citações rastreáveis.",
    "pagina.saltar": "Saltar para o conteúdo",
    "pagina.tema": "Alternar tema",
    "pagina.lingua": "Idioma da interface",
    "arranque.titulo": "A interface não arrancou",
    "arranque.texto": "Recarregue a página. Se persistir, veja a consola do navegador e o registo do contentor.",
    "erro.noticia": "Não foi possível abrir a notícia: {erro}",

    "entrada.titulo": "Verificar uma claim",
    "entrada.nota": "A claim é confrontada com o corpus LUSA anterior ao dia em que foi proferida. O resultado é um artigo que explica o que a evidência mostra, com cada frase ligada à notícia que a sustenta.",
    "form.claim": "Claim",
    "form.claimPista": "Cole aqui a claim a verificar, tal como foi proferida.",
    "form.data": "Data em que foi proferida",
    "form.dataPista": "A pesquisa cobre notícias publicadas até à véspera.",
    "form.contexto": "Contexto",
    "form.opcional": "opcional",
    "form.contextoPista": "O parágrafo onde a claim foi proferida.",
    "form.verificar": "Verificar",
    "form.aVerificar": "A verificar…",
    "form.limpar": "Limpar",
    "form.quantidade": "Notícias por pergunta",
    "form.redator": "Modelo do artigo",
    "form.erroClaim": "A claim tem de ter pelo menos 8 caracteres.",
    "form.erroData": "Indique a data em que a claim foi proferida.",

    "cal.meses": ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "cal.diasCurtos": ["S", "T", "Q", "Q", "S", "S", "D"],
    "cal.diasLongos": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                       "sexta-feira", "sábado", "domingo"],
    "cal.porExtenso": ({ dia, mes, ano }) => `${dia} de ${mes} de ${ano}`,
    "cal.mesAnterior": "Mês anterior",
    "cal.mesSeguinte": "Mês seguinte",
    "cal.ano": "Ano",
    "cal.hoje": "Hoje",
    "cal.fechar": "Fechar",
    "cal.escolher": "Escolher data",
    "cal.escolhida": "{rotulo}: {data}. Alterar.",
    "cal.porEscolher": "{rotulo}: por escolher.",

    "casos.titulo": "Exemplos verificados",
    "casos.conta": ({ n }) => `${n} ${n === 1 ? "claim verificada" : "claims verificadas"}`,
    "casos.legenda": "O que a cor de cada exemplo quer dizer",
    "casos.anteriores": "Exemplos anteriores",
    "casos.seguintes": "Exemplos seguintes",
    "casos.semGravacao": "sem execução gravada com {n} notícias por pergunta",
    "veredito.supported": "Apoiada",
    "veredito.supported.nota": "a evidência recuperada apoia a claim",
    "veredito.refuted": "Contrariada",
    "veredito.refuted.nota": "a evidência recuperada contraria a claim",
    "veredito.nei": "Não decidida",
    "veredito.nei.nota": "há evidência relevante, mas não chega para decidir",
    "veredito.nei_sem_evidencia": "Sem evidência",
    "veredito.nei_sem_evidencia.nota": "nada do que foi recuperado serve de evidência",

    "passo.perguntas": "Perguntas de verificação",
    "passo.perguntas.trabalho": "A formular as perguntas que vão procurar a evidência…",
    "passo.evidencia": "Recuperação de evidências",
    "passo.evidencia.trabalho": "À procura de notícias no corpus LUSA…",
    "passo.classificacao": "Classificação da evidência",
    "passo.classificacao.trabalho": "A confrontar cada evidência com a claim…",
    "passo.artigo": "Artigo de verificação",
    "passo.artigo.trabalho": "A escrever o artigo…",
    "passo.emCurso": "em curso",
    "passo.saltado": "não executado",
    "passo.falhou": "falhou",

    "bloco.perguntas": "Perguntas de verificação",
    "bloco.eixo": "Evidência no tempo",
    "bloco.balanco": "O que a evidência decide",
    "eixo.meses": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"],
    "eixo.claim": "claim",
    "eixo.ultima": "última notícia",
    "eixo.marcador": "{titulo} - publicada a {data}",
    "eixo.leitura": "Cada marca é uma notícia relevante para a claim, na data em que foi publicada.",
    "eixo.relevantes": ({ r, n, p }) => `${n} ${n === 1 ? "notícia recuperada" : "notícias recuperadas"} · ${p} consideradas relevantes (${r})`,
    "eixo.semRelevantes": "Nenhuma das notícias recuperadas é relevante para a claim.",
    "balanco.supported": "Apoiam a claim",
    "balanco.refuted": "Contrariam a claim",
    "balanco.nei": "Não decidem",
    "balanco.total": ({ n }) => (n === 1 ? ["Foi encontrada ", " evidência"] : ["Foram encontradas ", " evidências"]),

    "artigo.selo": "Artigo de verificação",
    "artigo.escritoPor": "Escrito por {modelo}",
    "artigo.semArtigo": "Esta verificação não tem artigo de {modelo}.",
    "artigo.semArtigo.por_gerar": "O artigo de {modelo} para este exemplo ainda não foi gerado.",
    "artigo.semArtigo.indisponivel": "O modelo {modelo} não está disponível neste servidor, por isso o artigo não foi escrito.",
    "artigo.semArtigo.sem_corpus": "Sem o corpus LUSA não há evidência, por isso o artigo não foi escrito.",
    "artigo.citada": "Evidência citada",
    "artigo.janelas": "{n} excertos classificados",
    "rotulo.supported": "Apoia",
    "rotulo.refuted": "Contraria",
    "rotulo.nei": "Não decide",
    "citacao.comTitulo": "Citação {n}: {titulo}",
    "citacao.semTitulo": "Citação {n}",

    "gaveta.fechar": "Fechar documento",
    "gaveta.fonte": "Agência Lusa - {id}",
    "gaveta.semTitulo": "Notícia sem título",
    "gaveta.palavras": "{n} palavras",
    "gaveta.janelas": "Excertos classificados nesta passagem ({n})",
    "gaveta.janelasNota": "O artigo cita a passagem inteira. O classificador leu-a em excertos de três frases, cada um com a sua relação.",
    "gaveta.passagem": "Passagem citada",
    "gaveta.janela": "Excerto {n}",
  },

  en: {
    "pagina.titulo": "FACTA-PT",
    "pagina.descricao": "From claim to fact-checking article: questions, evidence from Lusa, classification and a text with traceable citations.",
    "pagina.saltar": "Skip to content",
    "pagina.tema": "Toggle theme",
    "pagina.lingua": "Interface language",
    "arranque.titulo": "The interface failed to start",
    "arranque.texto": "Reload the page. If the problem persists, check the browser console and the container log.",
    "erro.noticia": "The news item could not be opened: {erro}",

    "entrada.titulo": "Verify a claim",
    "entrada.nota": "The claim is checked against the LUSA corpus published before the day it was made. The result is an article that explains what the evidence shows, with each sentence linked to the news item that supports it.",
    "form.claim": "Claim",
    "form.claimPista": "Paste the claim to verify, exactly as it was made.",
    "form.data": "Date it was made",
    "form.dataPista": "The search covers news up to the day before.",
    "form.contexto": "Context",
    "form.opcional": "optional",
    "form.contextoPista": "The paragraph in which the claim was made.",
    "form.verificar": "Verify",
    "form.aVerificar": "Verifying…",
    "form.limpar": "Clear",
    "form.quantidade": "News items per question",
    "form.redator": "Article model",
    "form.erroClaim": "The claim must be at least 8 characters long.",
    "form.erroData": "Enter the date on which the claim was made.",

    "cal.meses": ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"],
    "cal.diasCurtos": ["M", "T", "W", "T", "F", "S", "S"],
    "cal.diasLongos": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "cal.porExtenso": ({ dia, mes, ano }) => `${dia} ${mes} ${ano}`,
    "cal.mesAnterior": "Previous month",
    "cal.mesSeguinte": "Next month",
    "cal.ano": "Year",
    "cal.hoje": "Today",
    "cal.fechar": "Close",
    "cal.escolher": "Choose a date",
    "cal.escolhida": "{rotulo}: {data}. Change.",
    "cal.porEscolher": "{rotulo}: not selected.",

    "casos.titulo": "Verified examples",
    "casos.conta": ({ n }) => `${n} ${n === 1 ? "verified claim" : "verified claims"}`,
    "casos.legenda": "What the colour of each example means",
    "casos.anteriores": "Previous examples",
    "casos.seguintes": "Next examples",
    "casos.semGravacao": "no run recorded with {n} news items per question",
    "veredito.supported": "Supported",
    "veredito.supported.nota": "the retrieved evidence supports the claim",
    "veredito.refuted": "Refuted",
    "veredito.refuted.nota": "the retrieved evidence refutes the claim",
    "veredito.nei": "Inconclusive",
    "veredito.nei.nota": "there is relevant evidence, but not enough to decide",
    "veredito.nei_sem_evidencia": "No evidence",
    "veredito.nei_sem_evidencia.nota": "nothing retrieved counts as evidence",

    "passo.perguntas": "Verification questions",
    "passo.perguntas.trabalho": "Writing the questions that will search for the evidence…",
    "passo.evidencia": "Evidence retrieval",
    "passo.evidencia.trabalho": "Searching the LUSA corpus for news…",
    "passo.classificacao": "Evidence classification",
    "passo.classificacao.trabalho": "Comparing each piece of evidence with the claim…",
    "passo.artigo": "Fact-checking article",
    "passo.artigo.trabalho": "Writing the article…",
    "passo.emCurso": "in progress",
    "passo.saltado": "not run",
    "passo.falhou": "failed",

    "bloco.perguntas": "Verification questions",
    "bloco.eixo": "Evidence over time",
    "bloco.balanco": "What the evidence decides",
    "eixo.meses": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "eixo.claim": "claim",
    "eixo.ultima": "latest news",
    "eixo.marcador": "{titulo} - published on {data}",
    "eixo.leitura": "Each mark is a news item relevant to the claim, placed on the date it was published.",
    "eixo.relevantes": ({ r, n, p }) => `${n} retrieved news ${n === 1 ? "item" : "items"} · ${p} considered relevant (${r})`,
    "eixo.semRelevantes": "None of the retrieved news items is relevant to the claim.",
    "balanco.supported": "Support the claim",
    "balanco.refuted": "Refute the claim",
    "balanco.nei": "Inconclusive",
    "balanco.total": ({ n }) => (n === 1 ? ["", " piece of evidence found"] : ["", " pieces of evidence found"]),

    "artigo.selo": "Fact-checking article",
    "artigo.escritoPor": "Written by {modelo}",
    "artigo.semArtigo": "This verification has no article by {modelo}.",
    "artigo.semArtigo.por_gerar": "The {modelo} article for this example has not been generated yet.",
    "artigo.semArtigo.indisponivel": "The {modelo} model is not available on this server, so no article was written.",
    "artigo.semArtigo.sem_corpus": "Without the LUSA corpus there is no evidence, so no article was written.",
    "artigo.citada": "Cited evidence",
    "artigo.janelas": "{n} classified excerpts",
    "rotulo.supported": "Supports",
    "rotulo.refuted": "Refutes",
    "rotulo.nei": "Inconclusive",
    "citacao.comTitulo": "Citation {n}: {titulo}",
    "citacao.semTitulo": "Citation {n}",

    "gaveta.fechar": "Close document",
    "gaveta.fonte": "Lusa News Agency - {id}",
    "gaveta.semTitulo": "Untitled news item",
    "gaveta.palavras": "{n} words",
    "gaveta.janelas": "Classified excerpts in this passage ({n})",
    "gaveta.janelasNota": "The article cites the whole passage. The classifier read it as three-sentence excerpts, each with its own relation.",
    "gaveta.passagem": "Cited passage",
    "gaveta.janela": "Excerpt {n}",
  },
};

// Language codes: `<html lang>`, `Accept-Language` and the locale dates are written in.
const CODIGOS = { pt: "pt-PT", en: "en-GB" };

const ouvintes = [];

function guardada() {
  try {
    const valor = localStorage.getItem(CHAVE);
    return LINGUAS.includes(valor) ? valor : "pt";
  } catch (e) {
    void e;
    return "pt";
  }
}

let atual = guardada();
document.documentElement.lang = CODIGOS[atual];

export function lingua() {
  return atual;
}

/** `pt-PT` or `en-GB`. */
export function codigo() {
  return CODIGOS[atual];
}

/** Switches the language and tells every part of the page that translates itself. */
export function definirLingua(nova) {
  if (!LINGUAS.includes(nova) || nova === atual) return;
  atual = nova;
  try {
    localStorage.setItem(CHAVE, nova);
  } catch (e) {
    void e;
  }
  document.documentElement.lang = codigo();
  ouvintes.forEach((aoMudar) => aoMudar(nova));
}

/** Runs `aoMudar` after every language switch. For parts of the page built once: what is
    redrawn from data translates by being redrawn. */
export function aoMudarLingua(aoMudar) {
  ouvintes.push(aoMudar);
}

/** The text of `chave` in the current language, with `{name}` placeholders filled from
    `valores`; lists and plurals come as the entry holds them. An unknown key gives `reserva`. */
export function t(chave, valores = {}, reserva = chave) {
  const texto = chave in TEXTOS[atual] ? TEXTOS[atual][chave] : TEXTOS.pt[chave];
  if (texto === undefined) return reserva;
  if (typeof texto === "function") return texto(valores);
  if (typeof texto !== "string") return texto;
  return texto.replace(/\{(\w+)\}/g, (_, nome) => (valores[nome] === undefined ? "" : String(valores[nome])));
}
