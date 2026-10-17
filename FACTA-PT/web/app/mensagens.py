"""Fixed texts the server sends to the page, in the interface's two languages. The page names
its language in `Accept-Language`; what the models write is never translated."""

from __future__ import annotations

# key: (European Portuguese, English)
TEXTOS: dict[str, tuple[str, str]] = {
    "ocupado": (
        "Há demasiadas verificações em curso neste momento. Tente novamente dentro de instantes.",
        "Too many verifications are running right now. Please try again in a few moments.",
    ),
    "erro_inesperado": (
        "Erro inesperado ao executar a pipeline.",
        "Unexpected error while running the pipeline.",
    ),
    "execucao_expirada": (
        "Execução não encontrada ou já expirada.",
        "Run not found or already expired.",
    ),
    "noticia_ausente": (
        "Notícia não encontrada nesta execução.",
        "News item not found in this run.",
    ),
    "perguntas_sem_modelo": (
        "O modelo de geração de perguntas não está a correr, por isso uma claim nova não pode ser "
        "verificada agora. Escolha um dos exemplos, que mostram verificações já feitas pela "
        "pipeline.",
        "The question generation model is not running, so a new claim cannot be verified right "
        "now. Choose one of the examples, which show verifications already made by the pipeline.",
    ),
    "relevancia_sem_modelo": (
        "O modelo que decide se uma notícia é relevante não está a correr. Escolha um dos "
        "exemplos, que já trazem a evidência classificada.",
        "The model that decides whether a news item is relevant is not running. Choose one of "
        "the examples, which already hold the classified evidence.",
    ),
    "relacao_sem_modelo": (
        "O modelo de classificação da evidência não está a correr. Escolha um dos exemplos, que "
        "já trazem a evidência classificada.",
        "The evidence classification model is not running. Choose one of the examples, which "
        "already hold the classified evidence.",
    ),
    "sem_perguntas": (
        "o modelo não devolveu perguntas utilizáveis",
        "the model returned no usable questions",
    ),
    "classificador_invalido": (
        "resposta inválida do classificador: {erro}",
        "invalid response from the classifier: {erro}",
    ),
    "lusa_sem_credenciais": (
        "faltam API_URL_LUSA, USER_LUSA ou PASSWORD_LUSA no ambiente",
        "API_URL_LUSA, USER_LUSA or PASSWORD_LUSA is missing from the environment",
    ),
    "lusa_sem_vpn": (
        "não foi possível ligar à API da LUSA — verifique a ligação à VPN",
        "could not connect to the LUSA API — check the VPN connection",
    ),
    "lusa_sem_vpn_erro": (
        "não foi possível ligar à API da LUSA — verifique a ligação à VPN ({erro})",
        "could not connect to the LUSA API — check the VPN connection ({erro})",
    ),
    "lusa_login_recusado": (
        "login recusado pela API: HTTP {status}",
        "login refused by the API: HTTP {status}",
    ),
    "lusa_login_inesperado": (
        "resposta inesperada do login: {erro}",
        "unexpected login response: {erro}",
    ),
    "lusa_falha": (
        "falha em {caminho}",
        "request to {caminho} failed",
    ),
    "lusa_http": (
        "HTTP {status} em {caminho}",
        "HTTP {status} on {caminho}",
    ),
    "inferencia_erro": (
        "o serviço de inferência devolveu um erro: {detalhe}",
        "the inference service returned an error: {detalhe}",
    ),
    "inferencia_http": (
        "HTTP {status} em {caminho}: {texto}",
        "HTTP {status} on {caminho}: {texto}",
    ),
    "inferencia_sem_resposta": (
        "o serviço de inferência não respondeu em {segundos} s",
        "the inference service did not respond within {segundos} s",
    ),
    "resposta_invalida": (
        "resposta inválida em {caminho}: {erro}",
        "invalid response from {caminho}: {erro}",
    ),
    "resposta_sem_lista": (
        "resposta sem lista '{campo}'",
        "response without a '{campo}' list",
    ),
    "resposta_sem_artigo": (
        "resposta sem 'article' e 'evidence'",
        "response without 'article' and 'evidence'",
    ),
}


class Texto:
    """A fixed text not yet put in a language. The errors that can reach the page carry one
    instead of a string, so the stage that fails shows it in the language of the request;
    `str()` gives the Portuguese, as the logs have it."""

    def __init__(self, chave: str, **valores: object) -> None:
        self.chave = chave
        self.valores = valores

    def em(self, lingua: str) -> str:
        portugues, ingles = TEXTOS[self.chave]
        return (ingles if lingua == "en" else portugues).format(**self.valores)

    def __str__(self) -> str:
        return self.em("pt")

    def __repr__(self) -> str:
        return repr(str(self))


def texto(chave: str, lingua: str = "pt", **valores: object) -> str:
    return Texto(chave, **valores).em(lingua)


def lingua_do_pedido(cabecalho: str | None) -> str:
    """'en' when the first language in `Accept-Language` is English; 'pt' otherwise."""
    primeira = (cabecalho or "").split(",")[0].strip().lower()
    return "en" if primeira.startswith("en") else "pt"


def traduzir(mensagem: object, lingua: str) -> str:
    """`mensagem` in `lingua`: a `Texto`, or an error carrying one (also through another error);
    anything else as its own string."""
    while (isinstance(mensagem, BaseException) and len(mensagem.args) == 1
           and isinstance(mensagem.args[0], (Texto, BaseException))):
        mensagem = mensagem.args[0]
    return mensagem.em(lingua) if isinstance(mensagem, Texto) else str(mensagem)
