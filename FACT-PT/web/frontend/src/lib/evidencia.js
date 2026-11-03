/** What the classification says about each news item, and how the timeline is laid out. */

import { comoData, DIA_MS } from "./datas";
import { inicioDoEixo } from "./eixo";

export const RELACOES = ["supported", "refuted", "nei"];

/** The relations of each news item's decisive passages, by `doc_id`. Excerpt ids start with
    "<doc_id>-", which ties each passage to its news item. */
export function rotulosPorDocumento(documentos, classificacao) {
  const porExcerto = new Map((classificacao?.stances || []).map((estado) => [estado.excerpt_id, estado.label]));
  const decisivos = classificacao?.decisivos || [];
  return new Map(
    documentos.map((documento) => [
      documento.doc_id,
      new Set(decisivos.filter((id) => id.startsWith(`${documento.doc_id}-`)).map((id) => porExcerto.get(id)).filter(Boolean)),
    ])
  );
}

/** How many passages support, refute or decide nothing, over the news items kept as relevant: a
    news item with four supporting passages and one refuting counts 4 and 1. A news item with no
    decisive passage contributes the one undecided passage the classification kept for it. */
export function contagem(documentos, classificacao) {
  if (!classificacao) return { supported: 0, refuted: 0, nei: 0 };
  const relevantes = new Set(
    (documentos || []).filter((documento) => documento.relevant !== false).map((documento) => documento.doc_id)
  );
  const porExcerto = new Map((classificacao.stances || []).map((estado) => [estado.excerpt_id, estado.label]));
  const conta = { supported: 0, refuted: 0, nei: 0 };
  const comDecisivo = new Set();
  for (const id of classificacao.decisivos || []) {
    const docId = [...relevantes].find((candidato) => id.startsWith(`${candidato}-`));
    if (!docId) continue;
    const rotulo = porExcerto.get(id);
    if (RELACOES.includes(rotulo)) conta[rotulo] += 1;
    comDecisivo.add(docId);
  }
  relevantes.forEach((docId) => {
    if (!comDecisivo.has(docId)) conta.nei += 1;
  });
  return conta;
}

/** The same tally over a review's evidence: every passage with a relation, in a news item kept as
    relevant. Passages left out (`rotulo` null) count nowhere, and stay in the review. */
export function contagemDaRevisao(estado) {
  const conta = { supported: 0, refuted: 0, nei: 0 };
  if (!estado) return conta;
  const relevantes = new Set(
    (estado.documentos || []).filter((documento) => documento.relevante).map((documento) => documento.doc_id)
  );
  for (const excerto of estado.excertos || []) {
    if (relevantes.has(excerto.doc_id) && RELACOES.includes(excerto.rotulo)) conta[excerto.rotulo] += 1;
  }
  return conta;
}

/** The passages a news item's own result shows, before a review exists (an example, or a run
    still under way), as the review's first version takes them (`revisao._excertos_automaticos`):
    every supporting or refuting one, or, with none, the passage closest to deciding. `documento`
    carries its passages (`excerpts`), as the drawer fetches it. */
export function excertosAutomaticos(documento, classificacao) {
  const estados = new Map((classificacao?.stances || []).map((estado) => [estado.excerpt_id, estado]));
  const classificados = (documento?.excerpts || []).filter((excerto) => estados.has(excerto.id));
  let escolhidos = classificados.filter((excerto) => ["supported", "refuted"].includes(estados.get(excerto.id).label));
  if (!escolhidos.length && classificados.length) {
    // How far the nei logit is above the closest decisive one; without logits (an example), the
    // first passage.
    const margem = (excerto) => {
      const z = estados.get(excerto.id).logits;
      return z ? z.nei - Math.max(z.supported, z.refuted) : 0;
    };
    escolhidos = [classificados.reduce((melhor, excerto) => (margem(excerto) < margem(melhor) ? excerto : melhor))];
  }
  return escolhidos.map((excerto) => ({
    id: excerto.id,
    doc_id: documento.doc_id,
    begin: excerto.begin,
    end: excerto.end,
    rotulo: estados.get(excerto.id).label,
    origem: "automatico",
  }));
}

/** The passages of each news item, as the timeline shows them: whether it is relevant, how many
    passages of each relation it has, and how many it has in all. */
export function contagensPorDocumento(estado) {
  const porDocumento = new Map();
  for (const documento of estado?.documentos || []) {
    porDocumento.set(documento.doc_id, {
      relevante: Boolean(documento.relevante),
      conta: { supported: 0, refuted: 0, nei: 0 },
      total: 0,
    });
  }
  for (const excerto of estado?.excertos || []) {
    const registo = porDocumento.get(excerto.doc_id);
    if (!registo || !RELACOES.includes(excerto.rotulo)) continue;
    registo.conta[excerto.rotulo] += 1;
    registo.total += 1;
  }
  return porDocumento;
}

/** The same, before a review exists: the classification's decisive passages, and one undecided
    passage for a news item with none. */
export function contagensDaClassificacao(documentos, classificacao) {
  const porDocumento = new Map();
  for (const documento of documentos || []) {
    porDocumento.set(documento.doc_id, {
      relevante: documento.relevant !== false,
      conta: { supported: 0, refuted: 0, nei: 0 },
      total: 0,
    });
  }
  const porExcerto = new Map((classificacao?.stances || []).map((estado) => [estado.excerpt_id, estado.label]));
  const comDecisivo = new Set();
  for (const id of classificacao?.decisivos || []) {
    const docId = [...porDocumento.keys()].find((candidato) => id.startsWith(`${candidato}-`));
    const registo = porDocumento.get(docId);
    const rotulo = porExcerto.get(id);
    if (!registo || !RELACOES.includes(rotulo)) continue;
    registo.conta[rotulo] += 1;
    registo.total += 1;
    comDecisivo.add(docId);
  }
  porDocumento.forEach((registo, docId) => {
    if (!registo.relevante || comDecisivo.has(docId)) return;
    registo.conta.nei = 1;
    registo.total = 1;
  });
  return porDocumento;
}

/** The verdict a run's own evidence gives, or null until the classification is in. It is the
    rule the article writer applies to the same evidence (`server/artigo/veredito.py`, `decidir`):
    one side without the other decides, however much non-deciding evidence there is; evidence on
    both sides cancels out, whatever the counts; non-deciding evidence alone leaves the claim
    undecided; and nothing to weigh is said as such. It reads `contagem`, the tally the page shows,
    so the verdict and the numbers under it agree. */
export function vereditoDaEvidencia(documentos, classificacao) {
  if (!classificacao) return null;
  const conta = contagem(documentos || [], classificacao);
  return vereditoDaContagem(conta);
}

/** The verdict a review's evidence gives, unless a person set it by hand. */
export function vereditoDaRevisao(estado) {
  if (!estado) return null;
  if (estado.veredito_manual) return estado.veredito_manual;
  return vereditoDaContagem(contagemDaRevisao(estado));
}

function vereditoDaContagem(conta) {
  if (conta.supported && conta.refuted) return "nei";
  if (conta.supported) return "supported";
  if (conta.refuted) return "refuted";
  return conta.nei ? "nei" : "nei_sem_evidencia";
}

/** The timeline's content once the relevance stage ended, or null when there is nothing to show:
    the evidence placed on a scale, or (`semRelevantes`) just the fact that none of what was
    retrieved is relevant. */
export function planoDoEixo(documentos, relevancia, dataDaClaim) {
  if (documentos === null || (!documentos.length && !relevancia)) return null;
  const total = relevancia ? relevancia["notícias"] : 0;
  const comData = documentos
    .map((documento) => ({ documento, data: comoData(documento.published_at) }))
    .filter((registo) => registo.data !== null)
    .sort((a, b) => a.data - b.data);
  if (!comData.length) return !documentos.length && total ? { semRelevantes: true, total } : null;

  const maisAntiga = comData[0].data;
  const ultima = comData[comData.length - 1].data;
  // A claim date before the oldest news would collapse the scale, so the axis then ends on the
  // latest news.
  const eDaClaim = Boolean(dataDaClaim && dataDaClaim > maisAntiga);
  const fim = eDaClaim ? dataDaClaim : ultima;
  const inicio = inicioDoEixo(maisAntiga, fim);
  const amplitude = Math.max(DIA_MS, fim - inicio);

  // Where each marker sits along the axis (0-1); how they stack depends on the drawn width.
  const marcadores = comData.map(({ documento, data }) => ({
    documento,
    posicao: Math.min(1, Math.max(0, (data - inicio) / amplitude)),
  }));

  return { semRelevantes: false, total, inicio, fim, eDaClaim, marcadores };
}

/** What a news item says, for its marker: "pendente" before classification, "irrelevante" when
    the review (or the pipeline) ruled it out, "ambos" when it has passages on both sides. */
export function relacaoDe(rotulos, classificado, relevante = true) {
  if (!relevante) return "irrelevante";
  if (!classificado) return "pendente";
  if (rotulos.has("supported") && rotulos.has("refuted")) return "ambos";
  if (rotulos.has("supported")) return "supported";
  if (rotulos.has("refuted")) return "refuted";
  return "nei";
}

/** The proportions of a marker's square, as hard-stop gradient bands, one per relation it has.
    A news item with four supporting passages and one refuting is four fifths green, one fifth
    red; the square's width is the number of passages it has. Null when it has none. */
export function segmentosDoMarcador(conta, total) {
  if (!total) return null;
  const cores = {
    supported: "var(--color-apoia)",
    refuted: "var(--color-contraria)",
    nei: "var(--color-indeciso)",
  };
  const paragens = [];
  let acumulado = 0;
  for (const rotulo of RELACOES) {
    if (!conta[rotulo]) continue;
    const fim = acumulado + (conta[rotulo] / total) * 100;
    paragens.push(`${cores[rotulo]} ${acumulado}% ${fim}%`);
    acumulado = fim;
  }
  return `linear-gradient(90deg, ${paragens.join(", ")})`;
}

/** "4:1" for four supporting and one refuting passage. With undecided passages the three counts
    are always shown, "4:1:2", so none of them is read as another's; with only one relation, its
    count. */
export function proporcao(conta) {
  if (conta.nei) return `${conta.supported}:${conta.refuted}:${conta.nei}`;
  if (conta.supported && conta.refuted) return `${conta.supported}:${conta.refuted}`;
  return RELACOES.filter((rotulo) => conta[rotulo]).map((rotulo) => conta[rotulo]).join(":");
}
