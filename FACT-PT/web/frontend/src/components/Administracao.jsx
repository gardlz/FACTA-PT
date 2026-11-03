/** Administration: the accounts, the roles' permissions and the platform's defaults. Only an
    administrator reaches it; the server refuses every call anyway, and enforces the invariants
    (one active administrator always remains, nobody demotes, deactivates or deletes themselves). */

import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import * as api from "../lib/api";

const PAPEIS = ["jornalista", "administrador"];

const CAMPO =
  "w-full border-2 border-divisor bg-fundo px-3 py-2 text-[15px] outline-none transition-colors focus:border-tinta";

const BOTAO =
  "inline-flex items-center justify-center gap-1.5 border-2 border-tinta bg-tinta px-4 py-2 font-titulo text-[14px] font-extrabold text-fundo transition-colors hover:bg-[color-mix(in_srgb,var(--color-tinta)_85%,var(--color-fundo))] disabled:cursor-not-allowed disabled:opacity-45";

const BOTAO_CLARO =
  "inline-flex items-center justify-center gap-1.5 border border-divisor px-3 py-1.5 text-[13px] font-semibold transition-colors hover:bg-pairar disabled:cursor-not-allowed disabled:opacity-40";

function dataHora(iso, lingua) {
  if (!iso) return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return new Intl.DateTimeFormat(lingua, { dateStyle: "medium", timeStyle: "short" }).format(data);
}

function Aviso({ erro, aviso }) {
  if (!erro && !aviso) return null;
  return (
    <p
      role={erro ? "alert" : "status"}
      className={`flex items-center gap-2 text-[14px] ${erro ? "text-contraria" : "text-apoia"}`}
    >
      <span aria-hidden="true" className={`size-2 flex-none ${erro ? "bg-contraria" : "bg-apoia"}`} />
      {erro || aviso}
    </p>
  );
}

/** The accounts: create one, change its role, deactivate it, reset its password, delete it. */
function Utilizadores({ sessao, aoActualizarSessao, erro, setErro, aviso, setAviso }) {
  const { t, i18n } = useTranslation();
  const [lista, setLista] = useState(null);
  const [novo, setNovo] = useState({ utilizador: "", nome: "", papel: "jornalista", palavra_passe: "" });
  const [reporId, setReporId] = useState(null);
  const [novaPasse, setNovaPasse] = useState("");
  const [apagarId, setApagarId] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const idForm = useId();

  useEffect(() => {
    let vivo = true;
    api
      .utilizadores()
      .then((r) => vivo && setLista(r.utilizadores))
      .catch((falha) => vivo && setErro(falha.message));
    return () => {
      vivo = false;
    };
  }, [setErro]);

  function falhou(falha) {
    setErro(falha.message);
    setAviso(null);
  }

  async function criar(evento) {
    evento.preventDefault();
    if (ocupado) return;
    setOcupado(true);
    setErro(null);
    setAviso(null);
    try {
      const criado = await api.criarUtilizador({
        utilizador: novo.utilizador.trim(),
        nome: novo.nome.trim(),
        papel: novo.papel,
        palavra_passe: novo.palavra_passe,
      });
      setLista((antes) => [...(antes || []), criado]);
      setNovo({ utilizador: "", nome: "", papel: "jornalista", palavra_passe: "" });
      setAviso(t("admin.utilizadores.criada", { utilizador: criado.utilizador }));
    } catch (falha) {
      falhou(falha);
    } finally {
      setOcupado(false);
    }
  }

  /** Saves one account's changes; false when the server refused them, so a caller that clears a
      form knows not to. */
  async function alterar(id, campos) {
    setErro(null);
    setAviso(null);
    try {
      const mudado = await api.actualizarUtilizador(id, campos);
      setLista((antes) => antes.map((u) => (u.id === id ? mudado : u)));
      setAviso(t("admin.guardado"));
      if (id === sessao?.utilizador?.id) aoActualizarSessao?.();
      return true;
    } catch (falha) {
      falhou(falha);
      return false;
    }
  }

  async function repor(evento) {
    evento.preventDefault();
    if (!reporId || !novaPasse) return;
    // The form stays open, with what was typed, if the password was not changed.
    if (!(await alterar(reporId, { palavra_passe: novaPasse }))) return;
    setReporId(null);
    setNovaPasse("");
  }

  async function apagar(conta) {
    if (ocupado) return;
    setOcupado(true);
    setErro(null);
    setAviso(null);
    try {
      await api.apagarUtilizador(conta.id);
      setLista((antes) => antes.filter((u) => u.id !== conta.id));
      setAviso(t("admin.utilizadores.apagada", { utilizador: conta.utilizador }));
    } catch (falha) {
      falhou(falha);
    } finally {
      setApagarId(null);
      setOcupado(false);
    }
  }

  return (
    <div className="grid gap-8">
      <section className="grid gap-4">
        <h2 className="rubrica">{t("admin.utilizadores.titulo")}</h2>
        {!lista ? (
          <p className="text-[14px] text-mudo">{t("admin.aCarregar")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-[14px]">
              <thead>
                <tr className="border-b-2 border-divisor text-[11px] tracking-[.08em] text-mudo uppercase">
                  <th className="py-2 pr-4 font-semibold">{t("admin.utilizadores.conta")}</th>
                  <th className="py-2 pr-4 font-semibold">{t("admin.utilizadores.papel")}</th>
                  <th className="py-2 pr-4 font-semibold">{t("admin.utilizadores.estado")}</th>
                  <th className="py-2 pr-4 font-semibold">{t("admin.utilizadores.ultimaEntrada")}</th>
                  <th className="py-2 font-semibold">{t("admin.utilizadores.accoes")}</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((u) => (
                  <tr key={u.id} className="border-b border-regra align-top">
                    <td className="py-3 pr-4">
                      <span className="block font-semibold">{u.nome || u.utilizador}</span>
                      <span className="text-[12px] text-mudo">@{u.utilizador}</span>
                    </td>
                    <td className="py-3 pr-4">
                      <select
                        aria-label={t("admin.utilizadores.papelDe", { utilizador: u.utilizador })}
                        value={u.papel}
                        onChange={(evento) => alterar(u.id, { papel: evento.target.value })}
                        className="border border-divisor bg-fundo px-2 py-1.5 text-[13px]"
                      >
                        {PAPEIS.map((papel) => (
                          <option key={papel} value={papel}>{t(`papel.${papel}`)}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-3 pr-4">
                      <span className={u.activo ? "text-apoia" : "text-mudo"}>
                        {t(u.activo ? "admin.utilizadores.activa" : "admin.utilizadores.inactiva")}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-[13px] text-mudo">
                      {u.ultima_entrada ? dataHora(u.ultima_entrada, i18n.language) : t("admin.utilizadores.nunca")}
                    </td>
                    <td className="py-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => alterar(u.id, { activo: !u.activo })}
                          className={BOTAO_CLARO}
                        >
                          {t(u.activo ? "admin.utilizadores.desactivar" : "admin.utilizadores.activar")}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setReporId(reporId === u.id ? null : u.id);
                            setNovaPasse("");
                          }}
                          className={BOTAO_CLARO}
                          aria-expanded={reporId === u.id}
                        >
                          {t("admin.utilizadores.repor")}
                        </button>
                        {u.id !== sessao?.utilizador?.id && (
                          <button
                            type="button"
                            onClick={() => setApagarId(apagarId === u.id ? null : u.id)}
                            className={BOTAO_CLARO}
                            aria-expanded={apagarId === u.id}
                          >
                            {t("admin.utilizadores.apagar")}
                          </button>
                        )}
                      </div>
                      {apagarId === u.id && (
                        <div role="group" className="mt-2 flex flex-wrap items-center gap-2">
                          <span className="text-[13px] text-contraria">
                            {t("admin.utilizadores.apagarAviso", { utilizador: u.utilizador })}
                          </span>
                          <button type="button" disabled={ocupado} onClick={() => apagar(u)} className={BOTAO_CLARO}>
                            {t("admin.utilizadores.apagarConfirmar")}
                          </button>
                          <button type="button" onClick={() => setApagarId(null)} className={BOTAO_CLARO}>
                            {t("admin.utilizadores.apagarCancelar")}
                          </button>
                        </div>
                      )}
                      {reporId === u.id && (
                        <form onSubmit={repor} className="mt-2 flex flex-wrap items-center gap-2">
                          <input
                            type="password"
                            autoComplete="new-password"
                            required
                            minLength={12}
                            maxLength={512}
                            value={novaPasse}
                            onChange={(evento) => setNovaPasse(evento.target.value)}
                            aria-label={t("admin.utilizadores.novaPasse")}
                            placeholder={t("admin.utilizadores.novaPasse")}
                            className={`${CAMPO} max-w-[240px]`}
                          />
                          <button type="submit" disabled={!novaPasse} className={BOTAO_CLARO}>
                            {t("admin.utilizadores.guardarPasse")}
                          </button>
                        </form>
                      )}
                    </td>
                  </tr>
                ))}
                {!lista.length && (
                  <tr>
                    <td colSpan={5} className="py-4 text-mudo">{t("admin.utilizadores.semContas")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        <Aviso erro={erro} aviso={aviso} />
      </section>

      <section className="grid gap-4 border-t-2 border-divisor pt-6">
        <h2 className="rubrica">{t("admin.utilizadores.nova")}</h2>
        <form onSubmit={criar} className="grid gap-4 md:grid-cols-2">
          <div className="grid gap-1.5">
            <label htmlFor={`${idForm}-utilizador`} className="text-[12px] font-semibold uppercase tracking-[.08em]">
              {t("admin.utilizadores.utilizador")}
            </label>
            <input
              id={`${idForm}-utilizador`}
              required
              minLength={3}
              maxLength={40}
              pattern="[a-z0-9][a-z0-9._\-]{2,39}"
              autoComplete="off"
              value={novo.utilizador}
              onChange={(evento) => setNovo({ ...novo, utilizador: evento.target.value })}
              className={CAMPO}
            />
            <span className="text-[12px] text-mudo">{t("admin.utilizadores.utilizadorPista")}</span>
          </div>
          <div className="grid gap-1.5">
            <label htmlFor={`${idForm}-nome`} className="text-[12px] font-semibold uppercase tracking-[.08em]">
              {t("admin.utilizadores.nome")}
            </label>
            <input
              id={`${idForm}-nome`}
              maxLength={120}
              value={novo.nome}
              onChange={(evento) => setNovo({ ...novo, nome: evento.target.value })}
              className={CAMPO}
            />
          </div>
          <div className="grid gap-1.5">
            <label htmlFor={`${idForm}-papel`} className="text-[12px] font-semibold uppercase tracking-[.08em]">
              {t("admin.utilizadores.papel")}
            </label>
            <select
              id={`${idForm}-papel`}
              value={novo.papel}
              onChange={(evento) => setNovo({ ...novo, papel: evento.target.value })}
              className={CAMPO}
            >
              {PAPEIS.map((papel) => (
                <option key={papel} value={papel}>{t(`papel.${papel}`)}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-1.5">
            <label htmlFor={`${idForm}-passe`} className="text-[12px] font-semibold uppercase tracking-[.08em]">
              {t("admin.utilizadores.palavraPasse")}
            </label>
            <input
              id={`${idForm}-passe`}
              type="password"
              required
              minLength={12}
              maxLength={512}
              autoComplete="new-password"
              value={novo.palavra_passe}
              onChange={(evento) => setNovo({ ...novo, palavra_passe: evento.target.value })}
              className={CAMPO}
            />
            <span className="text-[12px] text-mudo">{t("admin.utilizadores.palavraPassePista")}</span>
          </div>
          <div className="md:col-span-2">
            <button type="submit" disabled={ocupado} className={BOTAO}>
              {t("admin.utilizadores.criar")}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

/** The role matrix: the administrator's row is fixed, the journalist's is editable. */
function Permissoes({ erro, setErro, aviso, setAviso }) {
  const { t } = useTranslation();
  const [estado, setEstado] = useState(null);
  const [escolhidas, setEscolhidas] = useState([]);

  useEffect(() => {
    let vivo = true;
    api
      .plataforma()
      .then((r) => {
        if (!vivo) return;
        setEstado(r);
        setEscolhidas(r.permissoes.jornalista || []);
      })
      .catch((falha) => vivo && setErro(falha.message));
    return () => {
      vivo = false;
    };
  }, [setErro]);

  async function guardar() {
    setErro(null);
    setAviso(null);
    try {
      const novo = await api.guardarPlataforma({ permissoes: { jornalista: escolhidas } });
      setEstado(novo);
      setEscolhidas(novo.permissoes.jornalista || []);
      setAviso(t("admin.guardado"));
    } catch (falha) {
      setErro(falha.message);
    }
  }

  if (!estado) return <p className="text-[14px] text-mudo">{t("admin.aCarregar")}</p>;
  const editaveis = estado.editaveis;
  const alternar = (permissao) =>
    setEscolhidas((antes) => (antes.includes(permissao) ? antes.filter((p) => p !== permissao) : [...antes, permissao]));

  return (
    <div className="grid gap-5">
      <p className="max-w-[70ch] text-[14px] text-mudo">{t("admin.permissoes.nota")}</p>
      <div className="grid gap-4">
        {["jornalista", "administrador"].map((papel) => (
          <div key={papel} className="grid gap-2 border-b border-regra pb-4 md:grid-cols-[180px_1fr]">
            <span className="font-titulo text-[15px] font-extrabold">{t(`papel.${papel}`)}</span>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {estado.todas.map((permissao) => {
                const fixa = papel !== "jornalista";
                const marcada = fixa ? estado.permissoes[papel].includes(permissao) : escolhidas.includes(permissao);
                return (
                  <label
                    key={permissao}
                    className={`inline-flex items-center gap-2 text-[13.5px] ${fixa ? "text-mudo" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={marcada}
                      disabled={fixa || !editaveis.includes(permissao)}
                      onChange={() => alternar(permissao)}
                      className="size-4 accent-[var(--color-tinta)]"
                    />
                    {t(`permissao.${permissao}`)}
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div>
        <button type="button" onClick={guardar} className={BOTAO}>{t("admin.permissoes.guardar")}</button>
      </div>
      <Aviso erro={erro} aviso={aviso} />
    </div>
  );
}

/** The defaults a new run starts with. */
function Plataforma({ catalogo, erro, setErro, aviso, setAviso }) {
  const { t } = useTranslation();
  const [estado, setEstado] = useState(null);
  const [definicoes, setDefinicoes] = useState(null);

  useEffect(() => {
    let vivo = true;
    api
      .plataforma()
      .then((r) => {
        if (!vivo) return;
        setEstado(r);
        setDefinicoes(r.definicoes);
      })
      .catch((falha) => vivo && setErro(falha.message));
    return () => {
      vivo = false;
    };
  }, [setErro]);

  async function guardar(evento) {
    evento.preventDefault();
    setErro(null);
    setAviso(null);
    try {
      const novo = await api.guardarPlataforma({ definicoes });
      setEstado(novo);
      setDefinicoes(novo.definicoes);
      setAviso(t("admin.guardado"));
    } catch (falha) {
      setErro(falha.message);
    }
  }

  if (!estado || !definicoes) return <p className="text-[14px] text-mudo">{t("admin.aCarregar")}</p>;
  const topK = catalogo?.quantidade?.opcoes?.length ? catalogo.quantidade.opcoes : [definicoes.top_k_omissao];
  const redatores = catalogo?.redatores?.opcoes?.length
    ? catalogo.redatores.opcoes
    : [{ id: definicoes.redator_omissao, nome: definicoes.redator_omissao }];
  const mudar = (campos) => setDefinicoes((antes) => ({ ...antes, ...campos }));

  return (
    <form onSubmit={guardar} className="grid max-w-[640px] gap-6">
      <div className="grid gap-1.5">
        <label htmlFor="admin-top-k" className="text-[12px] font-semibold uppercase tracking-[.08em]">
          {t("admin.plataforma.topK")}
        </label>
        <select
          id="admin-top-k"
          value={definicoes.top_k_omissao}
          onChange={(evento) => mudar({ top_k_omissao: Number(evento.target.value) })}
          className={`${CAMPO} max-w-[160px]`}
        >
          {topK.map((valor) => (
            <option key={valor} value={valor}>{valor}</option>
          ))}
        </select>
      </div>
      <div className="grid gap-1.5">
        <label htmlFor="admin-redator" className="text-[12px] font-semibold uppercase tracking-[.08em]">
          {t("admin.plataforma.redator")}
        </label>
        <select
          id="admin-redator"
          value={definicoes.redator_omissao}
          onChange={(evento) => mudar({ redator_omissao: evento.target.value })}
          className={CAMPO}
        >
          {redatores.map((opcao) => (
            <option key={opcao.id} value={opcao.id}>{opcao.nome}</option>
          ))}
        </select>
      </div>
      <div>
        <button type="submit" className={BOTAO}>{t("admin.plataforma.guardar")}</button>
      </div>
      <Aviso erro={erro} aviso={aviso} />
    </form>
  );
}

export default function Administracao({ sessao, catalogo, aoActualizarSessao }) {
  const { t } = useTranslation();
  const permissoes = sessao?.permissoes || [];
  const podeUtilizadores = permissoes.includes("gerir_utilizadores");
  const podePlataforma = permissoes.includes("gerir_plataforma");
  const abas = [
    podeUtilizadores && "utilizadores",
    podePlataforma && "permissoes",
    podePlataforma && "plataforma",
  ].filter(Boolean);
  const [aba, setAba] = useState(abas[0] || null);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);

  if (!abas.length) {
    return (
      <div className="mx-auto grid max-w-[52ch] gap-3 py-24">
        <h1 className="text-[28px]">{t("admin.semPermissao")}</h1>
        <p className="text-[15px] text-mudo">{t("admin.semPermissaoNota")}</p>
      </div>
    );
  }

  const mudarAba = (nova) => {
    setAba(nova);
    setErro(null);
    setAviso(null);
  };

  return (
    <div className="py-10">
      <header className="grid max-w-[70ch] gap-2 pb-6">
        <h1 className="text-[clamp(28px,4vw,40px)] leading-[1.1] tracking-[-.02em]">{t("admin.titulo")}</h1>
        <p className="text-[15px] text-mudo">{t("admin.nota")}</p>
      </header>
      <div role="tablist" aria-label={t("admin.titulo")} className="mb-8 flex flex-wrap gap-1 border-b-2 border-divisor">
        {abas.map((nome) => (
          <button
            key={nome}
            type="button"
            role="tab"
            id={`aba-${nome}`}
            aria-selected={aba === nome}
            aria-controls={`painel-${nome}`}
            onClick={() => mudarAba(nome)}
            className={`-mb-[2px] border-b-2 px-4 py-2.5 font-titulo text-[13px] font-extrabold uppercase tracking-[.06em] transition-colors ${
              aba === nome ? "border-tinta text-tinta" : "border-transparent text-mudo hover:text-tinta"
            }`}
          >
            {t(`admin.abas.${nome}`)}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`painel-${aba}`} aria-labelledby={`aba-${aba}`}>
        {aba === "utilizadores" && podeUtilizadores && (
          <Utilizadores
            sessao={sessao}
            aoActualizarSessao={aoActualizarSessao}
            erro={erro}
            setErro={setErro}
            aviso={aviso}
            setAviso={setAviso}
          />
        )}
        {aba === "permissoes" && podePlataforma && (
          <Permissoes erro={erro} setErro={setErro} aviso={aviso} setAviso={setAviso} />
        )}
        {aba === "plataforma" && podePlataforma && (
          <Plataforma catalogo={catalogo} erro={erro} setErro={setErro} aviso={aviso} setAviso={setAviso} />
        )}
      </div>
    </div>
  );
}
