/** A result section announced while its step is still running: its title at once, the step's line
    at the far end, and under them, where the content will be, the step's own drawing - the same
    writing animation as in the row above, at reading size. It is replaced by the real section when
    that arrives (`Pagina.jsx`), under the same key, so the title never moves. Decorative: the
    heading and the line say what is happening. */

import { useContext, useEffect } from "react";
import { useTranslation } from "react-i18next";
import Bloco, { Anunciadas } from "../Bloco";
import Ilustracao from "./Ilustracao";

export default function EmCurso({ id, titulo, passo }) {
  const { t } = useTranslation();
  const anunciadas = useContext(Anunciadas);
  useEffect(() => {
    anunciadas?.current.add(id);
  }, [anunciadas, id]);
  return (
    <Bloco id={id} titulo={titulo} nota={t(`passo.${passo}.trabalho`)}>
      <div className="em-curso py-6">
        <Ilustracao id={passo} estado="running" />
      </div>
    </Bloco>
  );
}
