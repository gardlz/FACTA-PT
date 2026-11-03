import { useTranslation } from "react-i18next";
import { TOM_ROTULO } from "../lib/tons";

/** A passage's relation to the claim: a coloured square and "Apoia", "Contraria", "Não decide". */
export default function Rotulo({ rotulo }) {
  const { t } = useTranslation();
  const tom = TOM_ROTULO[rotulo];
  return (
    <span className={`inline-flex items-center gap-1.5 font-semibold whitespace-nowrap ${tom ? tom.texto : ""}`}>
      <span aria-hidden="true" className={`size-[7px] flex-none ${tom ? tom.fundo : "bg-mudo"}`} />
      {t(`rotulo.${rotulo}`, { defaultValue: rotulo })}
    </span>
  );
}
