"""Fixed texts the server sends to the page, in the interface's two languages. The page names
its language in `Accept-Language`; what the models write is never translated."""

from __future__ import annotations

# key: (European Portuguese, English)
TEXTOS: dict[str, tuple[str, str]] = {
    "sem_sessao": (
        "É necessário entrar com uma conta.",
        "You need to sign in with an account.",
    ),
    "sem_permissao": (
        "A sua conta não tem permissão para esta ação.",
        "Your account does not have permission for this action.",
    ),
    "credenciais_invalidas": (
        "Utilizador ou palavra-passe incorretos.",
        "Incorrect username or password.",
    ),
    "palavra_passe_errada": (
        "Palavra-passe incorreta.",
        "Incorrect password.",
    ),
    "conta_inactiva": (
        "Esta conta está desactivada.",
        "This account is deactivated.",
    ),
    "utilizador_repetido": (
        "Já existe uma conta com esse nome de utilizador.",
        "An account with that username already exists.",
    ),
    "utilizador_invalido": (
        "Nome de utilizador inválido: 3 a 40 caracteres, letras minúsculas, dígitos, «.», «_» ou «-».",
        "Invalid username: 3 to 40 characters, lowercase letters, digits, '.', '_' or '-'.",
    ),
    "palavra_passe_curta": (
        "A palavra-passe tem de ter pelo menos {n} caracteres.",
        "The password must be at least {n} characters long.",
    ),
    "utilizador_ausente": (
        "Conta não encontrada.",
        "Account not found.",
    ),
    "ultimo_admin": (
        "Tem de ficar pelo menos um administrador activo.",
        "At least one active administrator must remain.",
    ),
    "conta_propria": (
        "Não pode desactivar nem retirar o papel à sua própria conta.",
        "You cannot deactivate your own account or take away its role.",
    ),
    "conta_propria_apagar": (
        "Não pode apagar a sua própria conta.",
        "You cannot delete your own account.",
    ),
    "plataforma_invalida": (
        "Definições da plataforma inválidas.",
        "Invalid platform settings.",
    ),
    "revisao_ausente": (
        "Revisão não encontrada.",
        "Review not found.",
    ),
    "revisao_conflito": (
        "Outra pessoa guardou uma revisão entretanto. Recarregue para ver a versão mais recente.",
        "Someone else saved a revision in the meantime. Reload to see the latest version.",
    ),
    "revisao_demasiadas": (
        "Não pode ligar mais de {n} evidências.",
        "You cannot link more than {n} pieces of evidence.",
    ),
    "revisao_excerto": (
        "O excerto {id} não existe nesta verificação.",
        "Excerpt {id} does not exist in this verification.",
    ),
    "revisao_documento": (
        "A notícia {id} não existe nesta verificação.",
        "News item {id} does not exist in this verification.",
    ),
    "revisao_destaque": (
        "O destaque não corresponde a um trecho da notícia.",
        "The highlight does not match a stretch of the news item.",
    ),
    "revisao_versao": (
        "A versão {versao} não existe nesta revisão.",
        "Version {versao} does not exist in this review.",
    ),
    "revisao_pedido": (
        "Já há uma reescrita do artigo em curso. Espere que termine.",
        "An article rewrite is already under way. Wait for it to finish.",
    ),
    "revisao_sem_evidencia": (
        "Não há evidência revista de onde escrever o artigo. Mantenha pelo menos uma passagem.",
        "There is no reviewed evidence to write the article from. Keep at least one passage.",
    ),
    "revisao_fila": (
        "Não foi possível pôr a reescrita na fila. Tente novamente.",
        "Could not queue the rewrite. Please try again.",
    ),
    "revisao_artigo_falhou": (
        "Não foi possível reescrever o artigo.",
        "Could not rewrite the article.",
    ),
    "revisao_artigo_longo": (
        "O artigo é demasiado longo.",
        "The article is too long.",
    ),
    "revisao_citacao": (
        "A citação {marcador} não pertence a nenhum artigo desta verificação.",
        "Citation {marcador} does not belong to any article of this verification.",
    ),
    "revisao_redator": (
        "Este modelo de redação não está disponível.",
        "This article writer is not available.",
    ),
    "revisao_artigo_desatualizado": (
        "A evidência mudou enquanto o artigo era escrito. Peça a reescrita outra vez.",
        "The evidence changed while the article was being written. Ask for the rewrite again.",
    ),
    "falha_guardar": (
        "Não foi possível guardar. O armazenamento pode estar cheio; tente novamente.",
        "Could not save. The storage may be full; please try again.",
    ),
    "demasiadas_tentativas": (
        "Demasiadas tentativas falhadas. Tente novamente dentro de alguns minutos.",
        "Too many failed attempts. Please try again in a few minutes.",
    ),
    "origem_invalida": (
        "Pedido de origem não permitida.",
        "Request from a disallowed origin.",
    ),
    "corpo_nao_json": (
        "O pedido tem de vir em JSON.",
        "The request must be sent as JSON.",
    ),
    "corpo_sem_tamanho": (
        "O pedido tem de indicar o seu tamanho (Content-Length).",
        "The request must state its size (Content-Length).",
    ),
    "corpo_grande": (
        "Pedido demasiado grande.",
        "Request too large.",
    ),
    "ocupado": (
        "Há demasiadas verificações em curso neste momento. Tente novamente dentro de instantes.",
        "Too many verifications are running right now. Please try again in a few moments.",
    ),
    "erro_inesperado": (
        "Erro inesperado ao executar a pipeline.",
        "Unexpected error while running the pipeline.",
    ),
    "execucao_nao_parada": (
        "Esta verificação não está parada: não há nada a reiniciar.",
        "This verification is not stopped: there is nothing to restart.",
    ),
    "execucao_expirada": (
        "Execução não encontrada ou já expirada.",
        "Run not found or already expired.",
    ),
    "verificacao_ausente": (
        "Verificação não encontrada.",
        "Verification not found.",
    ),
    "execucao_cancelada": (
        "Verificação cancelada.",
        "Verification cancelled.",
    ),
    "demasiadas_execucoes": (
        "Já tem {n} verificações em curso ou na fila. Espere que terminem, ou cancele uma, antes "
        "de pedir outra.",
        "You already have {n} checks running or waiting. Wait for them to finish, or cancel one, "
        "before asking for another.",
    ),
    "demasiadas_execucoes_endereco": (
        "Há {n} verificações em curso ou na fila a partir deste endereço. Espere que terminem "
        "antes de pedir outra.",
        "There are {n} checks running or waiting from this address. Wait for them to finish "
        "before asking for another.",
    ),
    "execucao_perdida": (
        "Verificação interrompida: o serviço reiniciou a meio. Tente de novo.",
        "Verification stopped: the service restarted midway. Please try again.",
    ),
    "execucao_abandonada": (
        "Verificação interrompida: a página deixou de a acompanhar.",
        "Verification stopped: the page stopped following it.",
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
