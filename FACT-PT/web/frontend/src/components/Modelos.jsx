/** One dot per model a run uses - the three every run needs and the writer chosen on the form -
    green ready, yellow loading, hollow loads when a run needs it, red unavailable - and, opened,
    each model's name, state, whether it is on the GPU, and the reason it gave when it refused to
    load. The state is asked of the server every few seconds. */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import * as api from "../lib/api";

const PONTO = {
  ready: "bg-apoia",
  loading: "animate-pulse bg-indeciso",
  waiting: "border border-mudo",
  error: "bg-contraria",
  unavailable: "bg-contraria",
};

const INTERVALO = 5000;
const INTERVALO_ESCONDIDO = 20000;

/** The models' state, null until the first answer. A server that does not answer is one
    unavailable "service" rather than a row per model. */
function useModelos(redator) {
  const [modelos, setModelos] = useState(null);
  useEffect(() => {
    let parado = false;
    let relogio;
    const ler = async () => {
      try {
        const resposta = await api.modelos(redator);
        if (!parado) setModelos(resposta.disponivel ? resposta.modelos : [{ id: "servico", estado: "unavailable", detalhe: "" }]);
      } catch {
        if (!parado) setModelos([{ id: "servico", estado: "unavailable", detalhe: "" }]);
      }
      if (!parado) relogio = setTimeout(ler, document.hidden ? INTERVALO_ESCONDIDO : INTERVALO);
    };
    ler();
    return () => {
      parado = true;
      clearTimeout(relogio);
    };
  }, [redator]);
  return modelos;
}

function Ponto({ estado }) {
  return <span aria-hidden="true" className={`size-2.5 flex-none rounded-full ${PONTO[estado]}`} />;
}

/** Each model's name, state and reason it refused to load, if it did. */
function Lista({ modelos }) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-col gap-3">
      {modelos.map((m) => (
        <li key={m.id} className="flex items-start gap-2.5 text-[14px] leading-[1.35]">
          <span className="mt-1 flex">
            <Ponto estado={m.estado} />
          </span>
          <span className="min-w-0">
            <span className="font-semibold">{t(`modelos.${m.id}`)}</span>
            <span className="text-mudo"> · {t(`modelos.estado.${m.estado}`)}{m.na_gpu && ` · ${t("modelos.naGpu")}`}</span>
            {m.detalhe && <span className="mt-0.5 block text-[13px] text-contraria [text-wrap:pretty]">{m.detalhe}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The dots, opening the list. `emLinha` shows the list itself instead (the bar's menu on a
    phone), wrapped by the function it is, once the state is known. */
export default function Modelos({ redator = "", emLinha = null }) {
  const { t } = useTranslation();
  const modelos = useModelos(redator);
  const [aberto, setAberto] = useState(false);
  const raiz = useRef(null);

  useEffect(() => {
    if (!aberto) return undefined;
    const fora = (evento) => {
      if (raiz.current && !raiz.current.contains(evento.target)) setAberto(false);
    };
    const tecla = (evento) => evento.key === "Escape" && setAberto(false);
    document.addEventListener("pointerdown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("pointerdown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto]);

  if (!modelos) return null;
  if (emLinha) return emLinha(<Lista modelos={modelos} />);
  const nome = (modelo) => t(`modelos.${modelo.id}`);
  const resumo = modelos.map((m) => `${nome(m)}: ${t(`modelos.estado.${m.estado}`)}`).join("; ");

  return (
    <div ref={raiz} className="relative">
      <button
        type="button"
        aria-expanded={aberto}
        aria-label={`${t("modelos.titulo")}. ${resumo}`}
        title={t("modelos.titulo")}
        onClick={() => setAberto((a) => !a)}
        className="flex h-8 items-center gap-1.5 px-2 transition-colors hover:bg-pairar active:bg-regra"
      >
        {modelos.map((m) => (
          <Ponto key={m.id} estado={m.estado} />
        ))}
      </button>
      {aberto && (
        <div className="absolute top-full right-0 z-40 mt-2 w-[min(88vw,340px)] border-2 border-divisor bg-fundo p-4 max-sm:-right-24">
          <p className="mb-3 text-[12px] tracking-[.08em] text-mudo uppercase">{t("modelos.titulo")}</p>
          <Lista modelos={modelos} />
        </div>
      )}
    </div>
  );
}
