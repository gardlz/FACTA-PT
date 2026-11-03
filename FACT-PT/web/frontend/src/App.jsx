/** The shell: skip link, top bar and the page, once the server has accepted an account and the
    example catalogue has loaded. */

import { MotionConfig } from "framer-motion";
import { Component, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Acesso from "./components/Acesso";
import Barra from "./components/Barra";
import Rodape from "./components/Rodape";
import * as api from "./lib/api";
import Pagina from "./Pagina";

/** Shown when the interface fails, instead of a blank page. */
function FalhaDeArranque({ erro }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto my-[clamp(40px,12vh,120px)] grid max-w-[52ch] gap-3 px-5">
      <h1 className="text-[28px]">{t("arranque.titulo")}</h1>
      <p className="text-[15px] text-mudo">{t("arranque.texto")}</p>
      <code className="border-l-2 border-contraria bg-superficie px-3 py-2.5 font-mono text-[12px] break-words text-contraria">{String(erro?.message || erro)}</code>
    </div>
  );
}

class Contencao extends Component {
  state = { erro: null };

  static getDerivedStateFromError(erro) {
    return { erro };
  }

  render() {
    return this.state.erro ? <FalhaDeArranque erro={this.state.erro} /> : this.props.children;
  }
}

const SEM_SESSAO = { autenticada: false, protegido: true, utilizador: null, permissoes: [] };

export default function App() {
  const { t, i18n } = useTranslation();
  const [catalogo, setCatalogo] = useState(null);
  // The server's answer about this browser: null until it answers.
  const [sessao, setSessao] = useState(null);
  // The writer picked on the form: the bar shows the state of that one only.
  const [redator, setRedator] = useState("");
  const autenticada = Boolean(sessao?.autenticada);

  useEffect(() => {
    api
      .sessao()
      .then(setSessao)
      .catch(() => setSessao(SEM_SESSAO));
    // A request the server refuses for want of a session (it ran out) sends the page back to the sign-in.
    const perdida = () => setSessao(SEM_SESSAO);
    window.addEventListener(api.SESSAO_PERDIDA, perdida);
    return () => window.removeEventListener(api.SESSAO_PERDIDA, perdida);
  }, []);

  useEffect(() => {
    if (!autenticada) {
      setCatalogo(null);
      return undefined;
    }
    let activo = true;
    // Without the catalogue new claims can still be verified, with the server's defaults.
    api
      .exemplos()
      .then((r) => {
        if (activo) setCatalogo({ exemplos: r.exemplos || [], quantidade: r.top_k || null, redatores: r.redatores || null });
      })
      .catch(() => {
        if (activo) setCatalogo((anterior) => anterior || { exemplos: [], quantidade: null, redatores: null });
      });
    return () => {
      activo = false;
    };
  }, [autenticada, i18n.resolvedLanguage]);

  const aoSair = useCallback(async () => {
    await api.sair().catch(() => {});
    setSessao(SEM_SESSAO);
  }, []);

  /** After an administrator changes their own account, the bar shows the new name. */
  const actualizarSessao = useCallback(async () => {
    try {
      setSessao(await api.sessao());
    } catch {
      setSessao(SEM_SESSAO);
    }
  }, []);

  return (
    <MotionConfig reducedMotion="user">
      <a
        href="#raiz"
        className="absolute -top-12 left-3 z-[60] border-2 border-tinta bg-fundo px-4 py-2.5 font-semibold text-tinta no-underline transition-[top] focus:top-3"
      >
        {t("pagina.saltar")}
      </a>
      {/* The footer stays at the foot of a short page. */}
      <div className="flex min-h-dvh flex-col">
        <Barra reservada={!autenticada} sessao={sessao} aoSair={aoSair} redator={redator} />
        <main id="raiz" className="flex-1">
          <Contencao>
            {sessao && !autenticada && <Acesso aoEntrar={setSessao} />}
            {autenticada && catalogo && (
              <Pagina catalogo={catalogo} sessao={sessao} aoActualizarSessao={actualizarSessao} aoEscolherRedator={setRedator} />
            )}
          </Contencao>
        </main>
        <Rodape />
      </div>
    </MotionConfig>
  );
}
