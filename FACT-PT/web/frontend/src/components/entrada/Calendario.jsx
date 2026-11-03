/** Date picker in the interface's language: the native `<input type="date">` cannot be styled
    and looks different on each system. The value is `YYYY-MM-DD`, or "" when none is chosen. */

import { AnimatePresence, motion } from "framer-motion";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { deIso, deslocarMeses, diaDaSemana, iso, mesmoDia, ultimoDiaDoMes } from "../../lib/datas";
import { SUAVE } from "../../lib/movimento";
import { Calendario as IconeCalendario, SetaDireita, SetaEsquerda } from "../Icones";

const PASSOS = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };

const ANO_CORRENTE = new Date().getFullYear();
// A select for the year: with month arrows alone, a date a few years back is dozens of clicks away.
const ANOS = Array.from({ length: 62 }, (_, i) => ANO_CORRENTE + 1 - i);

const NAVEGAR = "grid size-[30px] place-items-center border border-transparent text-mudo transition-colors hover:border-divisor hover:bg-pairar hover:text-tinta";
const ATALHO = "px-1 py-[7px] text-[12.5px] font-semibold underline-offset-3 hover:underline";

const Calendario = forwardRef(function Calendario({ id, valor, aoMudar, rotulo }, ref) {
  const { t } = useTranslation();
  const meses = t("cal.meses", { returnObjects: true });
  const curtos = t("cal.diasCurtos", { returnObjects: true });
  const longos = t("cal.diasLongos", { returnObjects: true });

  const seleccionada = deIso(valor);
  const [aberto, setAberto] = useState(false);
  // The day with keyboard focus; the panel always shows its month.
  const [focada, setFocada] = useState(() => seleccionada || new Date());
  const raiz = useRef(null);
  const alvo = useRef(null);
  const grelha = useRef(null);
  const focarCelula = useRef(false);

  useImperativeHandle(ref, () => ({ focar: () => alvo.current && alvo.current.focus() }), []);

  const porExtenso = (data) => t("cal.porExtenso", { dia: data.getDate(), mes: meses[data.getMonth()], ano: data.getFullYear() });

  // After a keyboard move redraws the grid, focus follows to the new day.
  useEffect(() => {
    if (!aberto || !focarCelula.current) return;
    focarCelula.current = false;
    const celula = grelha.current && grelha.current.querySelector('[tabindex="0"]');
    if (celula) celula.focus();
  });

  // The outside-click listener lives only while the panel is open.
  useEffect(() => {
    if (!aberto) return undefined;
    const foraDoPainel = (evento) => {
      if (raiz.current && !raiz.current.contains(evento.target)) setAberto(false);
    };
    document.addEventListener("pointerdown", foraDoPainel);
    return () => document.removeEventListener("pointerdown", foraDoPainel);
  }, [aberto]);

  function abrir() {
    setFocada(seleccionada || new Date());
    focarCelula.current = true;
    setAberto(true);
  }

  function fechar() {
    setAberto(false);
    if (alvo.current) alvo.current.focus();
  }

  function focarDia(dia) {
    setFocada(dia);
    focarCelula.current = true;
  }

  function escolher(dia) {
    aoMudar(iso(dia));
    setFocada(dia);
    fechar();
  }

  function teclaNaGrelha(evento) {
    if (PASSOS[evento.key] !== undefined) {
      evento.preventDefault();
      focarDia(new Date(focada.getFullYear(), focada.getMonth(), focada.getDate() + PASSOS[evento.key]));
    } else if (evento.key === "PageUp" || evento.key === "PageDown") {
      evento.preventDefault();
      const salto = evento.key === "PageUp" ? -1 : 1;
      focarDia(deslocarMeses(focada, evento.shiftKey ? salto * 12 : salto));
    } else if (evento.key === "Home" || evento.key === "End") {
      evento.preventDefault();
      const deslocamento = evento.key === "Home" ? -diaDaSemana(focada) : 6 - diaDaSemana(focada);
      focarDia(new Date(focada.getFullYear(), focada.getMonth(), focada.getDate() + deslocamento));
    }
  }

  const primeiro = new Date(focada.getFullYear(), focada.getMonth(), 1);
  const inicio = new Date(primeiro.getFullYear(), primeiro.getMonth(), 1 - diaDaSemana(primeiro));
  const hoje = new Date();
  const filas = Array.from({ length: 6 }, (_, linha) =>
    Array.from({ length: 7 }, (__, coluna) => new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + linha * 7 + coluna))
  );

  return (
    <div ref={raiz} className="relative">
      {/* The field's label targets this button. */}
      <button
        ref={alvo}
        id={id}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={aberto}
        aria-label={seleccionada ? t("cal.escolhida", { rotulo, data: porExtenso(seleccionada) }) : t("cal.porEscolher", { rotulo })}
        onClick={() => (aberto ? setAberto(false) : abrir())}
        className={`flex h-9 w-[200px] items-center justify-between gap-2.5 border px-2.5 text-left text-[14px] transition-colors hover:bg-pairar focus-visible:outline-offset-0 ${
          aberto ? "border-tinta" : "border-divisor"
        } ${seleccionada ? "text-tinta" : "text-mudo"}`}
      >
        <span className="min-w-0 truncate">{seleccionada ? porExtenso(seleccionada) : t("cal.escolher")}</span>
        <IconeCalendario className="size-4 flex-none text-mudo" />
      </button>

      <AnimatePresence>
        {aberto && (
          <motion.div
            role="dialog"
            aria-label={rotulo}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16, ease: SUAVE }}
            onKeyDown={(evento) => {
              if (evento.key === "Escape") {
                evento.preventDefault();
                fechar();
              }
            }}
            className="absolute top-[calc(100%+6px)] left-0 z-20 grid w-[288px] max-w-[calc(100vw-32px)] gap-2.5 border-2 border-tinta bg-fundo p-3.5 shadow-[0_12px_32px_color-mix(in_srgb,var(--color-tinta)_22%,transparent)]"
          >
            <div className="flex items-center gap-1.5">
              <button type="button" className={NAVEGAR} aria-label={t("cal.mesAnterior")} onClick={() => focarDia(deslocarMeses(focada, -1))}>
                <SetaEsquerda className="size-[17px]" />
              </button>
              <span aria-live="polite" className="flex-1 text-center text-[13.5px] font-semibold capitalize">
                {meses[focada.getMonth()]}
              </span>
              <select
                aria-label={t("cal.ano")}
                value={focada.getFullYear()}
                onChange={(evento) => {
                  const ano = Number(evento.target.value);
                  const mes = focada.getMonth();
                  focarDia(new Date(ano, mes, Math.min(focada.getDate(), ultimoDiaDoMes(ano, mes))));
                }}
                className="cursor-pointer border border-divisor bg-fundo px-1.5 py-[5px] text-[13px] font-semibold text-tinta tabular-nums"
              >
                {ANOS.map((ano) => <option key={ano} value={ano}>{ano}</option>)}
              </select>
              <button type="button" className={NAVEGAR} aria-label={t("cal.mesSeguinte")} onClick={() => focarDia(deslocarMeses(focada, 1))}>
                <SetaDireita className="size-[17px]" />
              </button>
            </div>

            <div className="grid grid-cols-7 gap-0.5">
              {curtos.map((inicial, indice) => (
                <abbr key={indice} title={longos[indice]} className="text-center text-[10.5px] font-semibold text-mudo uppercase no-underline">
                  {inicial}
                </abbr>
              ))}
            </div>

            {/* ARIA grid cells must sit inside rows; the rows are `contents`, so the days lay out on one grid. */}
            <div ref={grelha} role="grid" aria-label={rotulo} onKeyDown={teclaNaGrelha} className="grid grid-cols-7 gap-0.5">
              {filas.map((fila, linha) => (
                <div key={linha} role="row" className="contents">
                  {fila.map((dia) => {
                    const escolhido = mesmoDia(dia, seleccionada);
                    const fora = dia.getMonth() !== focada.getMonth();
                    return (
                      <button
                        key={dia.getTime()}
                        type="button"
                        role="gridcell"
                        aria-selected={escolhido || undefined}
                        aria-label={porExtenso(dia)}
                        tabIndex={mesmoDia(dia, focada) ? 0 : -1}
                        onClick={() => escolher(dia)}
                        className={`grid aspect-square place-items-center border text-[13px] tabular-nums transition-colors focus-visible:-outline-offset-2 ${
                          escolhido
                            ? "border-tinta bg-tinta font-semibold text-fundo"
                            : `hover:bg-pairar ${mesmoDia(dia, hoje) ? "border-divisor font-semibold" : "border-transparent"} ${fora ? "text-mudo" : "text-tinta"}`
                        }`}
                      >
                        {dia.getDate()}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>

            <div className="flex justify-between gap-2 border-t border-regra pt-0.5">
              <button type="button" className={ATALHO} onClick={() => escolher(new Date())}>{t("cal.hoje")}</button>
              <button type="button" className={ATALHO} onClick={fechar}>{t("cal.fechar")}</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

export default Calendario;
