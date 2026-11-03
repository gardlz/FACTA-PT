import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { SURGIR } from "../../lib/movimento";
import Descricao from "./Descricao";
import Titulo from "./Titulo";

/** The start page: title, what the tool does, then the form and the examples. */
export default function Entrada({ children }) {
  const { t } = useTranslation();
  return (
    <motion.div {...SURGIR} className="pt-[clamp(20px,3vw,40px)]">
      <div className="mb-8 flex flex-wrap items-baseline gap-x-6 gap-y-4">
        <h1 className="text-[clamp(36px,5vw,60px)] leading-none tracking-[-.035em] [text-wrap:balance]"><Titulo texto={t("entrada.titulo")} /></h1>
        <Descricao />
      </div>
      {children}
    </motion.div>
  );
}
