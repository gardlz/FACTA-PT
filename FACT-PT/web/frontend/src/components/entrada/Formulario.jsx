/** Input form: claim, optional context, date, how many news items each question keeps and the
    model that writes the article. The values live in the page, which also runs the examples. While
    the claim is empty, a link by its label leads down to the examples. */

import { useId, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Avancar } from "../Icones";
import Segmentos from "../Segmentos";
import Calendario from "./Calendario";

/** The text key of what is wrong with `valores`, or null. */
export function validar(valores) {
  if (valores.claim.trim().length < 8) return "form.erroClaim";
  if (!valores.data) return "form.erroData";
  return null;
}

const ROTULO = "text-[12px] font-semibold tracking-[.08em] uppercase whitespace-nowrap";
// Fainter than the interface's own placeholders: a hint to write over, not text to read.
const PISTA = "placeholder:text-[color-mix(in_srgb,var(--color-tinta)_28%,transparent)]";

function Escolha({ rotulo, opcoes, valor, aoMudar }) {
  const id = useId();
  return (
    <div className="flex max-w-full min-w-0 flex-none flex-col gap-1.5">
      <span id={id} className={ROTULO}>{rotulo}</span>
      <Segmentos rotuloId={id} opcoes={opcoes} valor={valor} aoMudar={aoMudar} />
    </div>
  );
}

export default function Formulario({ valores, aoAlterar, aoEditar, totalExemplos, aoVerExemplos, aoSubmeter, aoErro, erro, erroChave, ocupado, redatores }) {
  const { t } = useTranslation();
  const claim = useRef(null);
  const data = useRef(null);

  const pistaClaim = t("form.claimPista");

  // The claim box grows with its text, also when an example fills it; empty, with its placeholder,
  // which the box's height does not otherwise count.
  useLayoutEffect(() => {
    const no = claim.current;
    if (!no) return;
    const vazio = !no.value;
    if (vazio) no.value = pistaClaim;
    no.style.height = "auto";
    no.style.height = `${no.scrollHeight}px`;
    if (vazio) no.value = "";
  }, [valores.claim, pistaClaim]);

  function submeter(evento) {
    evento.preventDefault();
    const falha = validar(valores);
    if (falha) {
      aoErro({ chave: falha });
      (falha === "form.erroClaim" ? claim.current : data.current)?.focus();
      return;
    }
    aoSubmeter();
  }

  // Typing in the claim or its context makes a picked example a new claim, which then runs through
  // the models instead of being served from the stored examples.
  const escrever = (campo) => (evento) => {
    aoAlterar({ [campo]: evento.target.value });
    aoEditar();
    aoErro(null);
  };

  // The claim's own error sits by its box, red until the next keystroke; others go under the form.
  const erroNaClaim = erroChave === "form.erroClaim";

  // A single writer is no choice: the run takes it without asking.
  const opcoesRedator = redatores?.opcoes?.length > 1 ? redatores.opcoes.map((r) => ({ valor: r.id, texto: r.nome })) : null;

  return (
    <form noValidate onSubmit={submeter} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div
          className={`flex flex-col gap-2.5 border-2 px-5 pt-4 pb-5 transition-[background,box-shadow,border-color] focus-within:bg-superficie ${
            erroNaClaim
              ? "border-contraria focus-within:shadow-[inset_0_0_0_1px_var(--color-contraria)]"
              : "border-tinta focus-within:shadow-[inset_0_0_0_1px_var(--color-tinta)]"
          }`}
        >
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor="campo-claim" className={ROTULO}>{t("form.claim")}</label>
            {/* Until something is typed, the examples are one click away. */}
            {!valores.claim && totalExemplos > 0 ? (
              <button
                type="button"
                onClick={aoVerExemplos}
                className="inline-flex items-center gap-1 text-[12px] font-semibold text-mudo underline-offset-3 transition-colors hover:text-tinta hover:underline"
              >
                {t("form.usarExemplo")}
                <Avancar className="size-3.5 rotate-90" />
              </button>
            ) : (
              <span className={`text-[12px] tabular-nums ${erroNaClaim ? "text-contraria" : "text-mudo"}`}>{valores.claim.trim().length} / 8+</span>
            )}
          </div>
          {/* A claim is one sentence: Enter verifies it, Shift+Enter still breaks the line. */}
          <textarea
            ref={claim}
            id="campo-claim"
            rows={1}
            value={valores.claim}
            onChange={escrever("claim")}
            onKeyDown={(evento) => {
              if (evento.key === "Enter" && !evento.shiftKey && !evento.nativeEvent.isComposing) {
                evento.preventDefault();
                evento.currentTarget.form.requestSubmit();
              }
            }}
            placeholder={pistaClaim}
            aria-invalid={erroNaClaim || undefined}
            aria-describedby={erroNaClaim ? "erro-claim" : undefined}
            className={`w-full resize-none overflow-hidden border-0 bg-transparent p-0 text-[clamp(18px,1.9vw,22px)] leading-[1.35] tracking-[-.015em] outline-none focus-visible:outline-none ${PISTA}`}
          />
        </div>
        {erroNaClaim && (
          <p id="erro-claim" role="alert" className="flex items-center gap-2 text-[14px] text-contraria">
            <span aria-hidden="true" className="size-2 flex-none bg-contraria" />
            {erro}
          </p>
        )}
      </div>

      {/* Same layout as the claim box: its label inside, at the top. */}
      <div className="flex flex-col gap-2 border border-divisor px-4 pt-3.5 pb-4 transition-colors hover:border-[color-mix(in_srgb,var(--color-tinta)_55%,transparent)] focus-within:border-tinta focus-within:bg-superficie hover:focus-within:border-tinta">
        <div className="flex items-baseline justify-between gap-3">
          <label htmlFor="campo-contexto" className={ROTULO}>{t("form.contexto")}</label>
          <span className="text-[12px] text-mudo">{t("form.opcional")}</span>
        </div>
        {/* The model only reads one sentence either side of the claim
            (`inference/server/textutils.py`), so a paragraph is enough. */}
        <textarea
          id="campo-contexto"
          rows={3}
          value={valores.contexto}
          onChange={escrever("contexto")}
          placeholder={t("form.contextoPista")}
          className={`min-h-[64px] w-full resize-y border-0 bg-transparent p-0 text-[14.5px] leading-[1.6] outline-none focus-visible:outline-none ${PISTA}`}
        />
      </div>

      <div className="flex flex-wrap items-end gap-x-7 gap-y-4">
        <div className="flex flex-none flex-col gap-1.5">
          <label htmlFor="campo-data" className={ROTULO}>{t("form.data")}</label>
          <Calendario ref={data} id="campo-data" rotulo={t("form.data")} valor={valores.data} aoMudar={(novo) => { aoAlterar({ data: novo }); aoErro(null); }} />
        </div>
        {opcoesRedator && (
          <Escolha rotulo={t("form.redator")} opcoes={opcoesRedator} valor={valores.redator} aoMudar={(r) => aoAlterar({ redator: r })} />
        )}
        <button
          type="submit"
          disabled={ocupado}
          className="ml-auto inline-flex min-w-[220px] items-center justify-between gap-1.5 bg-tinta px-4 py-3 font-titulo text-[15px] font-extrabold text-fundo transition-colors hover:bg-[color-mix(in_srgb,var(--color-tinta)_85%,var(--color-fundo))] disabled:cursor-not-allowed disabled:opacity-45 max-sm:ml-0 max-sm:w-full"
        >
          {ocupado ? t("form.aVerificar") : t("form.verificar")}
          {ocupado ? (
            <span aria-hidden="true" className="size-[15px] animate-spin rounded-full border-2 border-current/35 border-t-current" />
          ) : (
            <Avancar className="size-[18px]" />
          )}
        </button>
      </div>

      {erro && !erroNaClaim && (
        <p role="alert" className="flex items-center gap-2 text-[14px] text-contraria">
          <span aria-hidden="true" className="size-2 flex-none bg-contraria" />
          {erro}
        </p>
      )}
    </form>
  );
}
