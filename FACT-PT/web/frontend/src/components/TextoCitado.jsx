import { useTranslation } from "react-i18next";
import { TOM_ROTULO } from "../lib/tons";

const MARCADOR = /\[\[C:(\d+):([^\]]+)\]\]/g;

/** An article block with each `[[C:<n>:<excerpt id>]]` marker turned into a citation button,
    outlined in the colour of what the passage says about the claim. Without `aoCitar` the
    markers are only drawn (an article laid beside another to compare, not the one on the page). */
export default function TextoCitado({ texto, citacoes, aoCitar }) {
  const { t } = useTranslation();
  const partes = [];
  let posicao = 0;
  for (const encontro of String(texto || "").matchAll(MARCADOR)) {
    if (encontro.index > posicao) partes.push(texto.slice(posicao, encontro.index));
    const numero = encontro[1];
    const citacao = citacoes.find((c) => c.excerpt_id === encontro[2]);
    const tom = TOM_ROTULO[citacao ? citacao.label : "nei"];
    if (!aoCitar) {
      partes.push(
        <span
          key={encontro.index}
          title={citacao?.headline}
          className={`mx-px inline-block border px-[5px] py-[3px] align-[2px] font-sans text-[11px] leading-none font-semibold tabular-nums ${tom.citacao}`}
        >
          {numero}
        </span>
      );
      posicao = encontro.index + encontro[0].length;
      continue;
    }
    partes.push(
      <button
        key={encontro.index}
        type="button"
        onClick={(evento) => aoCitar(citacao, evento.currentTarget)}
        title={citacao?.headline}
        aria-label={citacao ? t("citacao.comTitulo", { n: numero, titulo: citacao.headline }) : t("citacao.semTitulo", { n: numero })}
        className={`mx-px inline-block border px-[5px] py-[3px] align-[2px] font-sans text-[11px] leading-none font-semibold tabular-nums transition-colors hover:bg-marca ${tom.citacao}`}
      >
        {numero}
      </button>
    );
    posicao = encontro.index + encontro[0].length;
  }
  if (posicao < String(texto || "").length) partes.push(texto.slice(posicao));
  return partes;
}
