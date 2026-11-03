/** Footer: what the project is, the institutions behind it and the way round the site. */

import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { INSTITUICOES } from "../lib/sobre";

const LIGACAO = "w-fit text-[14px] text-mudo no-underline transition-colors hover:text-tinta";

export default function Rodape() {
  const { t } = useTranslation();
  return (
    <footer className="border-t-2 border-divisor">
      {/* Same column as the page and the bar. */}
      <div className="mx-auto max-w-[var(--coluna)] px-[var(--goteira)] pt-10 pb-8">
        <div className="grid gap-x-10 gap-y-9 sm:grid-cols-[1.4fr_1.6fr_1fr]">
          <div className="flex flex-col gap-3">
            <span className="font-titulo text-[18px] font-extrabold tracking-[-.01em]">FACT-PT</span>
            <p className="max-w-[34ch] text-[14px] leading-[1.5] text-mudo [text-wrap:pretty]">{t("rodape.descricao")}</p>
          </div>

          <div className="flex flex-col gap-3">
            <h2 className="rubrica">{t("rodape.instituicoes")}</h2>
            <ul className="flex flex-col gap-2.5">
              {INSTITUICOES.map(({ id, sigla, nome, url }) => (
                <li key={id} className="flex flex-col text-[14px] leading-[1.35]">
                  {url ? (
                    <a href={url} target="_blank" rel="noreferrer" className="w-fit font-semibold underline underline-offset-3">{sigla}</a>
                  ) : (
                    <span className="font-semibold">{sigla}</span>
                  )}
                  <span className="text-mudo">{nome}</span>
                </li>
              ))}
            </ul>
          </div>

          <nav aria-label={t("rodape.navegar")} className="flex flex-col gap-3">
            <h2 className="rubrica">{t("rodape.navegar")}</h2>
            <ul className="flex flex-col gap-2.5">
              <li><Link to="/" className={LIGACAO}>{t("rodape.verificar")}</Link></li>
              <li><Link to="/sobre" className={LIGACAO}>{t("rodape.sobre")}</Link></li>
            </ul>
          </nav>
        </div>

        <div className="mt-10 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-t border-regra pt-4 text-[12px] text-mudo">
          <span>{t("rodape.corpus")}</span>
          <span className="tabular-nums">{t("rodape.direitos", { ano: new Date().getFullYear() })}</span>
        </div>
      </div>
    </footer>
  );
}
