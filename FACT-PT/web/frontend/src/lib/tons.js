/** Colour classes for each verdict (of an example) and each relation (of a passage). Written
    out in full so Tailwind finds them. */

export const VEREDITOS = ["supported", "refuted", "nei", "nei_sem_evidencia"];

export const TOM_VEREDITO = {
  supported: { texto: "text-apoia", fundo: "bg-apoia", borda: "border-apoia" },
  refuted: { texto: "text-contraria", fundo: "bg-contraria", borda: "border-contraria" },
  nei: { texto: "text-indeciso", fundo: "bg-indeciso", borda: "border-indeciso" },
  nei_sem_evidencia: { texto: "text-neutro", fundo: "bg-neutro", borda: "border-neutro" },
};

export const ROTULOS = ["supported", "refuted", "nei"];

/** `citacao` is the outlined number in the article's text. */
export const TOM_ROTULO = {
  supported: { texto: "text-apoia", fundo: "bg-apoia", borda: "border-apoia", citacao: "border-apoia text-apoia" },
  refuted: { texto: "text-contraria", fundo: "bg-contraria", borda: "border-contraria", citacao: "border-contraria text-contraria" },
  nei: { texto: "text-indeciso", fundo: "bg-indeciso", borda: "border-indeciso", citacao: "border-indeciso text-indeciso" },
};

/** A timeline marker's border and fill, by `relacaoDe`. A news item ruled irrelevant keeps its
    place on the timeline as a dashed outline. */
export const TOM_MARCADOR = {
  supported: "border-apoia bg-apoia",
  refuted: "border-contraria bg-contraria",
  nei: "border-indeciso bg-indeciso",
  ambos: "border-tinta bg-[linear-gradient(90deg,var(--color-apoia)_50%,var(--color-contraria)_50%)]",
  pendente: "border-pendente bg-pendente",
  irrelevante: "border-dashed border-divisor bg-fundo opacity-60",
};
