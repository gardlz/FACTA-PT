/** The bar under the verdict, for the whole draft: what is on the page (the saved version, a draft
    with changes, an earlier version reopened), one undo and one redo for every edit, whatever it
    was, and the save that makes it a version. It stays in view while the page scrolls, so an edit
    to the article far below is saved from the same place. Read-only roles see which version is
    shown and the history, and may reopen an earlier version to read it. */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BOTAO_ICONE } from "../Barra";
import { Desfazer, Info, Refazer } from "../Icones";
import GuiaEdicao, { guiaEscondida, lembrarGuia } from "./GuiaEdicao";
import Historico from "./Historico";

const BOTAO = "border border-divisor px-2.5 py-1 text-[12px] font-semibold transition-colors hover:bg-pairar disabled:cursor-not-allowed disabled:opacity-40";

function Situacao({ revisao }) {
  const { t } = useTranslation();
  const { dados, situacao, alterado, restauradaDe, recuperado, podeEditar } = revisao;
  let tom = "bg-mudo";
  let texto;
  if (situacao === "a-guardar") {
    tom = "bg-indeciso";
    texto = t("revisao.situacao.aGuardar");
  } else if (situacao === "conflito" || situacao === "erro") {
    tom = "bg-contraria";
    texto = t(`revisao.situacao.${situacao}`);
  } else if (restauradaDe != null) {
    tom = "bg-indeciso";
    texto = t(podeEditar ? "revisao.situacao.aVerVersao" : "revisao.situacao.aVerVersaoLeitura", { versao: restauradaDe });
  } else if (alterado) {
    tom = "bg-indeciso";
    texto = t(recuperado ? "revisao.situacao.recuperado" : "revisao.situacao.porGuardar");
  } else {
    texto = dados.versao ? t("revisao.situacao.guardada", { versao: dados.versao }) : t("revisao.situacao.automatica");
    if (podeEditar) texto = `${texto} · ${t("revisao.semAlteracoes")}`;
  }
  return (
    <span role="status" className="flex items-center gap-1.5 text-mudo">
      <span aria-hidden="true" className={`size-2 flex-none ${tom}`} />
      {texto}
    </span>
  );
}

export default function BarraRevisao({ revisao }) {
  const { t } = useTranslation();
  const { dados, podeEditar, situacao, erro, alterado, restauradaDe } = revisao;
  // The editor's tip shows until it is hidden once (remembered in this browser).
  const [guia, setGuia] = useState(() => !guiaEscondida());
  const mostrarGuia = () => {
    lembrarGuia(guia);
    setGuia(!guia);
  };

  if (!dados) {
    if (situacao !== "erro" || !erro) return null;
    return (
      <p role="alert" className="flex items-center gap-2 border-l-2 border-contraria bg-superficie px-4 py-2 text-[13px] text-contraria">
        <span aria-hidden="true" className="size-2 flex-none bg-contraria" />
        {t("revisao.erroCarregar", { erro })}
      </p>
    );
  }

  const aGuardar = situacao === "a-guardar";

  return (
    <>
      <div className="sticky top-[var(--barra-altura)] z-20 -mx-[var(--goteira)] grid gap-2 bg-fundo px-[var(--goteira)]">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-regra py-2 text-[12px]">
          <Situacao revisao={revisao} />

          {podeEditar ? (
            <>
              <span className="flex items-center">
                <button
                  type="button"
                  onClick={revisao.desfazer}
                  disabled={!revisao.podeDesfazer}
                  aria-label={t("revisao.desfazer")}
                  title={t("revisao.desfazerAtalho")}
                  className={`${BOTAO_ICONE} disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  <Desfazer className="size-4" />
                </button>
                <button
                  type="button"
                  onClick={revisao.refazer}
                  disabled={!revisao.podeRefazer}
                  aria-label={t("revisao.refazer")}
                  title={t("revisao.refazerAtalho")}
                  className={`${BOTAO_ICONE} -ml-px disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  <Refazer className="size-4" />
                </button>
              </span>
              {/* Always there, so an editor sees where saving happens before the first edit. */}
              <span className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={revisao.descartar} disabled={!alterado || aGuardar} className={BOTAO}>
                  {t("revisao.descartar")}
                </button>
                <button
                  type="button"
                  onClick={() => revisao.guardar()}
                  disabled={!alterado || aGuardar || situacao === "conflito"}
                  title={t("revisao.guardarAtalho")}
                  className={`${BOTAO} border-tinta bg-tinta text-fundo hover:bg-tinta hover:opacity-85`}
                >
                  {restauradaDe != null ? t("revisao.guardarRestauro", { versao: restauradaDe }) : t("revisao.guardar")}
                </button>
              </span>
              <button
                type="button"
                onClick={mostrarGuia}
                aria-expanded={guia}
                title={t("revisao.guia.abrir")}
                className="inline-flex items-center gap-1.5 px-1 py-1 font-semibold text-mudo hover:text-tinta"
              >
                <Info className="size-4" />
                {t("revisao.guia.abrir")}
              </button>
            </>
          ) : (
            <>
              <span className="text-mudo">{t("revisao.soLeitura")}</span>
              {restauradaDe != null && (
                <button type="button" onClick={revisao.descartar} className={BOTAO}>
                  {t("revisao.voltarActual")}
                </button>
              )}
            </>
          )}

          <span className="ml-auto">
            <Historico revisao={revisao} />
          </span>
        </div>

        {situacao === "conflito" && (
          <div role="alert" className="mb-2 grid gap-2 border-l-2 border-contraria bg-superficie px-4 py-2">
            <p className="text-[13px] text-contraria">{erro || t("revisao.situacao.conflito")}</p>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => revisao.resolverConflito("recarregar")} className={BOTAO}>
                {t("revisao.conflito.recarregar")}
              </button>
              <button type="button" onClick={() => revisao.resolverConflito("manter")} className={BOTAO}>
                {t("revisao.conflito.manter")}
              </button>
            </div>
          </div>
        )}

        {situacao === "erro" && erro && (
          <div role="alert" className="mb-2 flex flex-wrap items-center gap-3 border-l-2 border-contraria bg-superficie px-4 py-2">
            <p className="text-[13px] text-contraria">{erro}</p>
            {podeEditar && alterado && (
              <button type="button" onClick={() => revisao.guardar()} className={BOTAO}>
                {t("revisao.tentarNovamente")}
              </button>
            )}
          </div>
        )}
      </div>
      {podeEditar && guia && <GuiaEdicao aoFechar={mostrarGuia} />}
    </>
  );
}
