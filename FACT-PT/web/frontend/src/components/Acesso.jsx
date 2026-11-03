/** The sign-in page, shown in place of the site until the server has accepted an account. The
    check is the server's: this only asks it and shows its answer. */

import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import * as api from "../lib/api";
import { Avancar } from "./Icones";

export default function Acesso({ aoEntrar }) {
  const { t } = useTranslation();
  const campo = useRef(null);
  const idErro = useId();
  const [utilizador, setUtilizador] = useState("");
  const [palavraPasse, setPalavraPasse] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState(null);

  async function submeter(evento) {
    evento.preventDefault();
    if (ocupado || !utilizador || !palavraPasse) return;
    setOcupado(true);
    setErro(null);
    try {
      await api.entrar(utilizador.trim(), palavraPasse);
      // The server said yes; if the browser dropped the cookie (plain HTTP), there is no session.
      const sessao = await api.sessao();
      if (!sessao.autenticada) throw new api.ErroHttp(t("acesso.semCookie"), 0);
      setPalavraPasse("");
      aoEntrar(sessao);
    } catch (falha) {
      // The server's own messages (wrong credentials, too many attempts) already follow the language.
      setErro(falha instanceof api.ErroHttp ? falha.message : t("acesso.falha", { erro: falha.message }));
      setPalavraPasse("");
      setOcupado(false);
      campo.current?.focus();
    }
  }

  return (
    <div className="mx-auto my-[clamp(20px,5vh,48px)] grid max-w-[360px] gap-4 px-[var(--goteira)]">
      <div className="grid gap-1">
        <h1 className="text-[clamp(22px,3.2vw,28px)] leading-[1.1] tracking-[-.02em]">{t("acesso.titulo")}</h1>
        <p className="text-[14px] text-mudo">{t("acesso.texto")}</p>
      </div>
      <form onSubmit={submeter} className="grid gap-2.5">
        <div className="flex flex-col gap-1 border-2 border-tinta px-3 py-2 transition-[background,box-shadow] focus-within:bg-superficie focus-within:shadow-[inset_0_0_0_1px_var(--color-tinta)]">
          <label htmlFor="campo-utilizador" className="text-[11px] font-semibold tracking-[.08em] uppercase">{t("acesso.utilizador")}</label>
          <input
            ref={campo}
            id="campo-utilizador"
            type="text"
            name="utilizador"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            autoFocus
            required
            maxLength={40}
            value={utilizador}
            onChange={(evento) => setUtilizador(evento.target.value)}
            aria-invalid={erro ? true : undefined}
            aria-describedby={erro ? idErro : undefined}
            className="w-full border-0 bg-transparent p-0 text-[15px] outline-none focus-visible:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1 border-2 border-tinta px-3 py-2 transition-[background,box-shadow] focus-within:bg-superficie focus-within:shadow-[inset_0_0_0_1px_var(--color-tinta)]">
          <label htmlFor="campo-palavra-passe" className="text-[11px] font-semibold tracking-[.08em] uppercase">{t("acesso.campo")}</label>
          <input
            id="campo-palavra-passe"
            type="password"
            name="palavra-passe"
            autoComplete="current-password"
            required
            maxLength={512}
            value={palavraPasse}
            onChange={(evento) => setPalavraPasse(evento.target.value)}
            aria-invalid={erro ? true : undefined}
            aria-describedby={erro ? idErro : undefined}
            className="w-full border-0 bg-transparent p-0 text-[15px] outline-none focus-visible:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={ocupado || !utilizador || !palavraPasse}
          className="inline-flex items-center justify-between gap-1.5 bg-tinta px-4 py-2.5 font-titulo text-[15px] font-extrabold text-fundo transition-colors hover:bg-[color-mix(in_srgb,var(--color-tinta)_85%,var(--color-fundo))] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {ocupado ? t("acesso.aEntrar") : t("acesso.entrar")}
          {ocupado ? (
            <span aria-hidden="true" className="size-[14px] animate-spin rounded-full border-2 border-current/35 border-t-current" />
          ) : (
            <Avancar className="size-4" />
          )}
        </button>
        {erro && (
          <p id={idErro} role="alert" className="flex items-center gap-2 text-[14px] text-contraria">
            <span aria-hidden="true" className="size-2 flex-none bg-contraria" />
            {erro}
          </p>
        )}
      </form>
    </div>
  );
}
