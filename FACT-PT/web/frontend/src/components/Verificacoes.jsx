/** The account's recent verifications (those that ran in the background, of the last day): waiting,
    under way or over, each one a link to its page, which follows it while it runs. One that stopped
    without a verification (cancelled, failed or lost) can be asked for again. Only for an account
    with `segundo_plano`. While any is still going, the list asks the server again every few
    seconds. */

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate } from "react-router";
import * as api from "../lib/api";
import { dataHora } from "../lib/formato";
import { SURGIR } from "../lib/movimento";
import { Refazer } from "./Icones";

const INTERVALO = 5000;
const A_DECORRER = new Set(["na-fila", "em-curso"]);

const TOM = {
  "na-fila": "border border-mudo",
  "em-curso": "animate-pulse bg-indeciso motion-reduce:animate-none",
  guardada: "bg-apoia",
  terminada: "bg-contraria",
  perdida: "bg-contraria",
};

function situacaoDe(execucao) {
  if (execucao.estado === "terminada") return execucao.guardada ? "guardada" : "terminada";
  return execucao.estado;
}

export default function Verificacoes({ sessao }) {
  const { t } = useTranslation();
  const permitido = Boolean(sessao?.permissoes?.includes("segundo_plano"));
  // Null until the server answers, so the empty state does not flash on the way in.
  const [execucoes, setExecucoes] = useState(null);
  const [aReiniciar, setAReiniciar] = useState(null);
  const [erro, setErro] = useState(null);
  // Bumped to read the list at once, after a restart.
  const [leitura, setLeitura] = useState(0);

  useEffect(() => {
    if (!permitido) return undefined;
    let parado = false;
    let relogio;
    const ler = async () => {
      let lista = null;
      try {
        lista = (await api.execucoes()).execucoes;
        if (!parado) setExecucoes(lista);
      } catch {
        // A failed read leaves the last list shown (or, the first time, an empty one).
        if (!parado) setExecucoes((anterior) => anterior ?? []);
      }
      if (!parado && lista?.some((execucao) => A_DECORRER.has(execucao.estado))) relogio = setTimeout(ler, INTERVALO);
    };
    ler();
    return () => {
      parado = true;
      clearTimeout(relogio);
    };
  }, [permitido, leitura]);

  const reiniciar = useCallback(async (runId) => {
    setAReiniciar(runId);
    setErro(null);
    try {
      await api.reiniciar(runId);
      setLeitura((n) => n + 1);
    } catch (e) {
      setErro(e.message);
    } finally {
      setAReiniciar(null);
    }
  }, []);

  if (!permitido) return <Navigate to="/" replace />;

  return (
    <motion.div {...SURGIR} className="pt-[clamp(20px,3vw,40px)]">
      <header className="grid max-w-[70ch] gap-2 pb-6">
        <h1 className="text-[clamp(28px,4vw,40px)] leading-[1.1] tracking-[-.02em]">{t("verificacoes.titulo")}</h1>
        <p className="text-[15px] text-mudo">{t("verificacoes.nota")}</p>
      </header>

      {erro && (
        <p role="alert" className="mb-4 flex items-center gap-2 text-[14px] text-contraria">
          <span aria-hidden="true" className="size-2 flex-none bg-contraria" />
          {erro}
        </p>
      )}

      {execucoes && !execucoes.length && (
        <p className="border-t-2 border-divisor pt-4 text-[15px] text-mudo">
          {t("verificacoes.vazio")} <Link to="/" className="text-tinta underline underline-offset-3">{t("verificacoes.nova")}</Link>
        </p>
      )}

      {execucoes?.length > 0 && (
        <ul className="border-t-2 border-divisor">
          {execucoes.map((execucao) => {
            const situacao = situacaoDe(execucao);
            const parada = situacao === "terminada" || situacao === "perdida";
            return (
              <li key={execucao.run_id} className="flex items-center gap-3 border-b border-regra max-sm:flex-col max-sm:items-stretch max-sm:gap-0">
                <Link
                  to={`/verificacao/${execucao.run_id}`}
                  className="-mx-2 flex min-w-0 flex-1 items-baseline gap-4 px-2 py-3 text-tinta no-underline transition-colors hover:bg-pairar max-sm:mx-0 max-sm:flex-col max-sm:gap-1 max-sm:px-0"
                >
                  <span className="min-w-0 flex-1 truncate text-[15px] max-sm:w-full">«{execucao.claim}»</span>
                  <span className="flex flex-none items-center gap-2 text-[13px] text-mudo">
                    <span aria-hidden="true" className={`size-2 flex-none rounded-full ${TOM[situacao]}`} />
                    {t(`verificacoes.estado.${situacao}`, { count: execucao.frente ?? 0 })}
                    <time dateTime={execucao.pedida_em}>· {dataHora(execucao.pedida_em)}</time>
                  </span>
                </Link>
                {parada && (
                  <button
                    type="button"
                    onClick={() => reiniciar(execucao.run_id)}
                    disabled={aReiniciar === execucao.run_id}
                    className="inline-flex flex-none items-center gap-2 border border-divisor px-3 py-1.5 text-[13px] font-semibold transition-colors hover:bg-pairar disabled:opacity-50 max-sm:mb-3 max-sm:self-start"
                  >
                    <Refazer className="size-[14px]" />
                    {t("verificacoes.reiniciar")}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </motion.div>
  );
}
