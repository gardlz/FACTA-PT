/** The review's history: every saved version, newest first, down to the automated result (v0).
    Each row says who saved it, when, and what it changed. Any of them opens in the draft, to be
    read on the page as it was; an editor who then saves it makes it the current version again.
    It opens from a button in the review bar (`useBalao`). */

import { AnimatePresence, motion } from "framer-motion";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useBalao } from "../../hooks/useBalao";
import { dataHora } from "../../lib/formato";
import { SUAVE } from "../../lib/movimento";
import { Historico as IconeHistorico } from "../Icones";

function autorDe(versao) {
  return versao.autor?.nome || versao.autor?.utilizador || "";
}

export default function Historico({ revisao }) {
  const { t } = useTranslation();
  const { aberto, setAberto, raiz, botao, painel, desvio } = useBalao();
  const id = useId();
  const dados = revisao.dados;
  if (!dados) return null;
  const actual = dados.versao;
  const versoes = [...dados.historico].reverse();
  // The version the page shows: one reopened, or the current one while the draft is unchanged.
  const mostrada = revisao.restauradaDe ?? (revisao.alterado ? null : actual);
  const abrir = (versao) => {
    revisao.abrirVersao(versao);
    setAberto(false);
  };
  const marca = (versao) =>
    versao === actual ? t("revisao.historico.actual") : versao === mostrada ? t("revisao.historico.aVer") : null;
  const botaoAbrir = (versao) =>
    versao !== mostrada && (
      <button
        type="button"
        onClick={() => abrir(versao)}
        className="ml-auto px-1 py-0.5 font-semibold underline underline-offset-2 hover:text-tinta"
      >
        {versao === actual ? t("revisao.historico.voltar") : t("revisao.historico.abrir")}
      </button>
    );

  return (
    <div ref={raiz} className="relative">
      <button
        ref={botao}
        type="button"
        aria-expanded={aberto}
        aria-controls={id}
        onClick={() => setAberto((a) => !a)}
        className="inline-flex items-center gap-1.5 border border-divisor px-2.5 py-1 text-[12px] font-semibold transition-colors hover:bg-pairar aria-expanded:bg-tinta aria-expanded:text-fundo"
      >
        <IconeHistorico className="size-3.5" />
        {t("revisao.historico.titulo")}
      </button>
      <AnimatePresence>
        {aberto && (
          <motion.div
            ref={painel}
            id={id}
            role="region"
            aria-label={t("revisao.historico.titulo")}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            style={{ marginLeft: desvio }}
            transition={{ duration: 0.18, ease: SUAVE }}
            className="absolute top-[calc(100%+8px)] left-0 z-30 w-[min(430px,calc(100vw-2*var(--goteira)))] border-2 border-tinta bg-fundo p-4"
          >
            <ol className="grid gap-2">
              {versoes.map((versao) => (
                <li key={versao.versao} className="grid gap-1 border-b border-regra pb-2 text-[13px] last:border-b-0">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="font-titulo font-extrabold tabular-nums">v{versao.versao}</span>
                    <span className="font-semibold">
                      {t(`revisao.accao.${versao.accao}`)}
                      {versao.accao === "artigo" && versao.redator ? ` · ${versao.redator}` : ""}
                    </span>
                    <span className="text-mudo">{autorDe(versao)}</span>
                    <time className="text-mudo" dateTime={versao.em}>{dataHora(versao.em)}</time>
                    {marca(versao.versao) && (
                      <span className="ml-auto font-semibold tracking-[.06em] text-mudo uppercase">{marca(versao.versao)}</span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-mudo">
                    {versao.alteracoes.length > 0 && (
                      <span>{versao.alteracoes.map((campo) => t(`revisao.campo.${campo}`)).join(", ")}</span>
                    )}
                    {versao.restaurada_de !== null && versao.restaurada_de !== undefined && (
                      <span>{t("revisao.restauradaDe", { versao: versao.restaurada_de })}</span>
                    )}
                    {botaoAbrir(versao.versao)}
                  </div>
                </li>
              ))}
              <li className="grid gap-1 text-[13px]">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-titulo font-extrabold tabular-nums">v0</span>
                  <span className="font-semibold">{t("revisao.accao.automatica")}</span>
                  <span className="text-mudo">{t("revisao.origem.automatico")}</span>
                  {marca(0) && (
                    <span className="ml-auto font-semibold tracking-[.06em] text-mudo uppercase">{marca(0)}</span>
                  )}
                </div>
                <div className="flex">{botaoAbrir(0)}</div>
              </li>
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
