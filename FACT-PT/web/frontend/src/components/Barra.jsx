/** Top bar: the name (back to the start), the models' state, the account, the interface language
    and the light/dark theme. `reservada`: the site is locked, so only the settings are offered.

    On a phone the bar keeps only the name and a menu button; everything else is in a menu that
    covers the page under the bar, and closes on a link, on Escape, or when the page widens. */

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, useLocation } from "react-router";
import { useTema } from "../hooks/useTema";
import { LINGUAS } from "../i18n";
import { SUAVE } from "../lib/movimento";
import { Fechar, Lua, Menu, Sair, Sol } from "./Icones";
import Modelos from "./Modelos";
import Segmentos from "./Segmentos";

export const BOTAO_ICONE =
  "grid size-8 flex-none place-items-center border border-divisor transition-colors hover:bg-pairar active:bg-regra";

// Tailwind's `md`: from here up the bar has room for everything.
const LARGA = "(min-width: 768px)";

/** The page-wide menu of a phone: open or not, closed on a change of page, on Escape and when the
    page widens past the phone's layout. The page under it does not scroll while it is open. */
function useMenu() {
  const [aberto, setAberto] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setAberto(false), [pathname]);
  useEffect(() => {
    if (!aberto) return undefined;
    const largura = window.matchMedia(LARGA);
    const fechar = () => largura.matches && setAberto(false);
    const tecla = (evento) => evento.key === "Escape" && setAberto(false);
    const antes = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    largura.addEventListener("change", fechar);
    document.addEventListener("keydown", tecla);
    return () => {
      document.body.style.overflow = antes;
      largura.removeEventListener("change", fechar);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto]);
  return [aberto, setAberto];
}

function Seccao({ titulo, children }) {
  return (
    <section className="border-t-2 border-divisor pt-4">
      <h2 className="mb-4 text-[12px] tracking-[.08em] text-mudo uppercase">{titulo}</h2>
      {children}
    </section>
  );
}

export default function Barra({ reservada, sessao, aoSair, redator = "" }) {
  const { t, i18n } = useTranslation();
  const [escuro, alternarTema] = useTema();
  const [aberto, setAberto] = useMenu();
  const id = useId();
  const botao = useRef(null);
  const painel = useRef(null);
  const opcoes = LINGUAS.map(({ sigla, codigo, nome }) => ({ valor: codigo, lang: codigo, titulo: nome, texto: sigla.toUpperCase() }));
  const permissoes = sessao?.permissoes || [];
  const podeAdministrar = permissoes.includes("gerir_utilizadores") || permissoes.includes("gerir_plataforma");
  const comVerificacoes = permissoes.includes("segundo_plano");
  const utilizador = sessao?.utilizador;

  // The focus goes into the menu when it opens, and back to its button when it closes.
  const abriu = useRef(false);
  useEffect(() => {
    if (aberto) painel.current?.querySelector("a, button")?.focus();
    else if (abriu.current) botao.current?.focus();
    abriu.current = aberto;
  }, [aberto]);

  const ligacao = ({ isActive }) =>
    `px-1 py-1.5 text-[14px] no-underline transition-colors uppercase ${isActive ? "font-semibold text-tinta underline decoration-2 underline-offset-[10px]" : "text-mudo hover:text-tinta"}`;
  const ligacaoMenu = ({ isActive }) =>
    `flex items-center justify-between border-b border-regra py-4 font-titulo text-[28px] leading-none font-extrabold tracking-[-.02em] no-underline transition-colors ${
      isActive ? "text-tinta" : "text-mudo hover:text-tinta"
    }`;
  const lingua = (
    <Segmentos pequeno rotulo={t("pagina.lingua")} opcoes={opcoes} valor={i18n.resolvedLanguage} aoMudar={(codigo) => i18n.changeLanguage(codigo)} />
  );
  const tema = escuro ? <Sol className="size-[15px]" /> : <Lua className="size-[15px]" />;

  return (
    <>
      <header className="sticky top-0 z-30 h-[var(--barra-altura)] border-b-2 border-divisor bg-fundo">
        {/* Same column as the page, so the name and the controls line up with its content. */}
        <div className="mx-auto flex h-full max-w-[var(--coluna)] items-center gap-4 px-[var(--goteira)]">
          <Link to="/" className="font-titulo text-[18px] font-extrabold tracking-[-.01em] text-tinta no-underline max-md:mr-auto">
            FACT-PT
          </Link>
          <nav aria-label={t("nav.principal")} className="mr-auto ml-4 flex items-center gap-4 max-md:hidden">
            {!reservada && comVerificacoes && <NavLink to="/verificacoes" className={ligacao}>{t("nav.verificacoes")}</NavLink>}
            {!reservada && <NavLink to="/sobre" className={ligacao}>{t("nav.sobre")}</NavLink>}
            {!reservada && podeAdministrar && <NavLink to="/administracao" className={ligacao}>{t("nav.administracao")}</NavLink>}
          </nav>
          <div className="flex items-center gap-4 max-md:hidden">
            {!reservada && <Modelos redator={redator} />}
            {!reservada && utilizador && (
              <div className="flex flex-col items-end border-l border-regra pl-3 leading-tight">
                <span className="text-[13px] font-semibold text-tinta">{utilizador.nome || utilizador.utilizador}</span>
                <span className="text-[11px] text-mudo">{t(`papel.${utilizador.papel}`)}</span>
              </div>
            )}
            {lingua}
            <button type="button" onClick={alternarTema} aria-label={t("pagina.tema")} title={t("pagina.tema")} className={BOTAO_ICONE}>
              {tema}
            </button>
            {!reservada && utilizador && (
              <button type="button" onClick={aoSair} aria-label={t("nav.sair")} title={t("nav.sair")} className={BOTAO_ICONE}>
                <Sair className="size-[15px]" />
              </button>
            )}
          </div>
          <button
            ref={botao}
            type="button"
            onClick={() => setAberto((a) => !a)}
            aria-expanded={aberto}
            aria-controls={id}
            aria-label={t(aberto ? "nav.fechar" : "nav.menu")}
            className={`${BOTAO_ICONE} size-10 md:hidden`}
          >
            {aberto ? <Fechar className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </header>

      <AnimatePresence>
        {aberto && (
          <motion.div
            ref={painel}
            id={id}
            role="dialog"
            aria-modal="true"
            aria-label={t("nav.principal")}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: SUAVE }}
            className="fixed inset-x-0 top-[var(--barra-altura)] bottom-0 z-30 overflow-y-auto overscroll-contain bg-fundo md:hidden"
          >
            <div className="flex min-h-full flex-col gap-10 px-[var(--goteira)] pt-4 pb-10">
              {!reservada && (
                <nav aria-label={t("nav.principal")} className="flex flex-col">
                  <NavLink to="/" end className={ligacaoMenu}>{t("nav.inicio")}</NavLink>
                  {comVerificacoes && <NavLink to="/verificacoes" className={ligacaoMenu}>{t("nav.verificacoes")}</NavLink>}
                  <NavLink to="/sobre" className={ligacaoMenu}>{t("nav.sobre")}</NavLink>
                  {podeAdministrar && <NavLink to="/administracao" className={ligacaoMenu}>{t("nav.administracao")}</NavLink>}
                </nav>
              )}

              {!reservada && utilizador && (
                <Seccao titulo={t("nav.conta")}>
                  <div className="flex items-center justify-between gap-4">
                    <span className="flex flex-col leading-tight">
                      <span className="text-[16px] font-semibold text-tinta">{utilizador.nome || utilizador.utilizador}</span>
                      <span className="text-[13px] text-mudo">{t(`papel.${utilizador.papel}`)}</span>
                    </span>
                    <button
                      type="button"
                      onClick={aoSair}
                      className="inline-flex items-center gap-2 border border-divisor px-3 py-2 text-[14px] font-semibold transition-colors hover:bg-pairar"
                    >
                      <Sair className="size-[15px]" />
                      {t("nav.sair")}
                    </button>
                  </div>
                </Seccao>
              )}

              {!reservada && <Modelos redator={redator} emLinha={(lista) => <Seccao titulo={t("nav.modelos")}>{lista}</Seccao>} />}

              <Seccao titulo={t("nav.preferencias")}>
                <div className="flex flex-wrap items-center gap-4">
                  {lingua}
                  <button
                    type="button"
                    onClick={alternarTema}
                    className="inline-flex items-center gap-2 border border-divisor px-3 py-1.5 text-[13px] font-semibold transition-colors hover:bg-pairar"
                  >
                    {tema}
                    {t(escuro ? "nav.temaClaro" : "nav.temaEscuro")}
                  </button>
                </div>
              </Seccao>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
