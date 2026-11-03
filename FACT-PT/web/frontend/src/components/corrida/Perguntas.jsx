import { forwardRef } from "react";
import { useTranslation } from "react-i18next";
import Bloco from "../Bloco";

/** The verification questions the model wrote. */
const Perguntas = forwardRef(function Perguntas({ id, perguntas }, ref) {
  const { t } = useTranslation();
  return (
    <Bloco ref={ref} id={id} titulo={t("bloco.perguntas")}>
      <ol>
        {perguntas.map((pergunta) => (
          <li key={pergunta.index} className="flex gap-5 border-b border-regra py-4 text-[16px] leading-normal">
            <span className="flex-none pt-[3px] text-[12px] font-semibold text-mudo tabular-nums">Q{pergunta.index}</span>
            <span className="[text-wrap:pretty]">{pergunta.text}</span>
          </li>
        ))}
      </ol>
    </Bloco>
  );
});

export default Perguntas;
