import { motion } from "framer-motion";
import { createContext, forwardRef, useContext, useState } from "react";
import { APARECER } from "../lib/movimento";

/** The ids of the sections announced by a placeholder (`EmCurso`) during this verification, in a
    ref held by `Resultado`. The section that replaces its placeholder does not arrive again - its
    heading is already there - and only what is inside it appears, over the same time. */
export const Anunciadas = createContext(null);

/** A result section, rising into place: an uppercase heading over a 2px rule, an optional help
    (`ajuda`, an `Ajuda`) right after it and an optional note at the far end, then the body. `id` is
    the anchor the section rail scrolls to. */
const Bloco = forwardRef(function Bloco({ id, titulo, ajuda, nota, como = "section", children }, ref) {
  const Elemento = como === "article" ? motion.article : motion.section;
  const anunciadas = useContext(Anunciadas);
  // Read once, on mount: the placeholder is gone by the time the real section is there.
  const [jaAnunciada] = useState(() => Boolean(anunciadas?.current.has(id)));
  return (
    <Elemento ref={ref} id={id} {...APARECER} initial={jaAnunciada ? false : APARECER.initial} className="scroll-mt-24">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b-2 border-divisor pb-3">
        <div className="flex items-center gap-2.5">
          <h2 className="rubrica">{titulo}</h2>
          {ajuda}
        </div>
        {nota && <div className="text-[12px] text-mudo tabular-nums">{nota}</div>}
      </div>
      {jaAnunciada ? (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={APARECER.transition}>
          {children}
        </motion.div>
      ) : (
        children
      )}
    </Elemento>
  );
});

export default Bloco;
