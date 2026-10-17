"""Writing the article with Gemma 4 E4B: the `full` condition of `Article Generation/geracao/`.

Unlike that stage: transformers instead of vLLM, 8192 new tokens instead of 4096, a prompt cap,
a brake on stuck attempts, a third attempt with half the passages, and completion from the plan.
"""

from __future__ import annotations

import json
import logging
import mmap
import os
import threading
import time
from pathlib import Path

import torch
from transformers import LogitsProcessor, StoppingCriteria

from .. import gpu
from ..dispositivo import MARGEM_RAM, memoria_disponivel
from ..settings import Settings
from ..textutils import claim_context
from . import admissao, esquema, plano as pv, prompt_base as pb, render
from .completar import completar, paragrafos_por_seccao
from .resposta import LIMIAR_CICLO, interpretar, pontos, precisa_retentar, repeticao

logger = logging.getLogger(__name__)

DTYPE = torch.bfloat16
MAX_NOVOS = 8192
PENALIZACAO = 1.05
PENALIZACAO_RETENTATIVA = 1.15
# A generation is stuck when it ends in BRANCOS blank characters or repeats an 8-gram twice as
# often as the cycle threshold, checked every VERIFICAR_A_CADA tokens.
BRANCOS = 64
LIMIAR_PRESO = 2 * LIMIAR_CICLO
VERIFICAR_A_CADA = 32
# Against a deadline, an attempt starts only when there is time to read its prompt, which cannot
# be stopped halfway, and to write for a while after. Seconds per prompt token: a generous guess
# until an attempt measures it, and then the slowest reading measured, if slower.
LEITURA_POR_TOKEN = {"cpu": 0.04, "cuda": 0.001}
ESCRITA_MINIMA = 60.0
# On the GPU the prompt is read this many tokens at a time, so the memory for it grows with its
# length, not with its square: measured 0.76 GB above the weights for 16 384 tokens.
LEITURA_EM_BOCADOS = 1024
# GPU memory a call holds beyond the weights: about 80 kB per token of prompt and article, over a
# fixed part. Measured as memory reserved: 0.4 GB for 2 818 + 668 tokens (the evaluated median,
# TOKENS_MEDIANOS) and 1.3 GB for 13 398 + 1 714.
GPU_POR_TOKEN = 80_000
GPU_BASE = int(0.1e9)
TOKENS_MEDIANOS = 2818 + 668
# Room is made on the GPU for an article this long from a prompt at the cap. A longer one runs
# slower where the driver lends system memory, and can run out of GPU memory where it does not.
ARTIGO_PREVISTO = 2048
# Modules of the checkpoint idle for text: left out when the model goes to the GPU.
TORRES = ("vision_tower", "audio_tower", "embed_vision", "embed_audio")
# The weights go to the GPU through a pinned buffer of this many bytes (see `_enviar`), read from
# the checkpoint file in blocks aligned to BLOCO, as O_DIRECT requires.
BUFFER_DE_COPIA = 256 * 1024 * 1024
BLOCO = 4096
# The dtypes of a safetensors header, for the weights the GPU copy reads from the file.
DTYPES_DO_FICHEIRO = {"BF16": torch.bfloat16, "F16": torch.float16, "F32": torch.float32}


class ArticleError(RuntimeError):
    """The article could not be written."""


class ArticleCancelled(ArticleError):
    """Whoever asked for the article is gone, and the generation stopped."""


def _memoria_de_trabalho(tokens: int) -> int:
    """GPU memory a call holds beyond the weights for this many tokens of prompt and article."""
    return GPU_BASE + tokens * GPU_POR_TOKEN


def _tamanho_dos_pesos(pasta: Path) -> int:
    return sum(f.stat().st_size for f in pasta.glob("*.safetensors"))


def texto_inteiro(tokenizer, ids) -> str:
    """The text of `ids` up to its last whole character. A character the vocabulary lacks is
    written as byte tokens (a non-breaking space takes two), and decoding cut between them gives
    U+FFFD: a stuck run of such spaces would never read as blank. At most three tokens are cut."""
    for corte in range(4):
        texto = tokenizer.decode(ids[: len(ids) - corte], skip_special_tokens=True)
        if not texto.endswith("�"):
            break
    return texto


def preso(texto: str) -> bool:
    """Whether a generation is stuck: see `BRANCOS` and `LIMIAR_PRESO`."""
    cauda = texto[-BRANCOS:]
    return (len(cauda) == BRANCOS and cauda.isspace()) or repeticao(texto) >= LIMIAR_PRESO


def _seccoes_em_falta(plano: dict, blocos: list[dict]) -> list[str]:
    """The plan's sections the article does not bring whole: a heading with at least one paragraph,
    and the fixed texts verbatim. A generation cut at the limit and mended can stop halfway."""
    paragrafos = paragrafos_por_seccao(blocos)
    em_falta = []
    for seccao in plano["seccoes"]:
        escritos = paragrafos.get(seccao["titulo"])
        if not escritos or ("texto_fixo" in seccao and escritos != [seccao["texto_fixo"]]):
            em_falta.append(seccao["titulo"])
    return em_falta


class _Gramatica(LogitsProcessor):
    """The plan's grammar, applied to each token's logits with xgrammar's CPU kernel. On CUDA the
    row is masked on the CPU and copied back: xgrammar's own processor would launch a Triton
    kernel, which needs a C compiler and a writable cache the image lacks. The mask is the same."""

    def __init__(self, compilada) -> None:
        import xgrammar as xgr

        self._xgr = xgr
        self._matcher = xgr.GrammarMatcher(compilada)
        self._mascara = xgr.allocate_token_bitmask(1, compilada.tokenizer_info.vocab_size)
        self._primeiro = True

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        if not self._primeiro and not self._matcher.accept_token(int(input_ids[0, -1])):
            raise ArticleError("a gramática recusou um token que ela própria tinha permitido")
        self._primeiro = False
        self._matcher.fill_next_token_bitmask(self._mascara)
        linha = scores if scores.device.type == "cpu" else scores.cpu()
        self._xgr.apply_token_bitmask_inplace(linha, self._mascara)
        if linha is not scores:
            scores.copy_(linha)
        return scores


class _Cancelado(StoppingCriteria):
    """Stops the generation once whoever asked for it is gone."""

    def __init__(self, evento: threading.Event) -> None:
        self._evento = evento

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs):
        return torch.full((input_ids.shape[0],), self._evento.is_set(), dtype=torch.bool,
                          device=input_ids.device)


class _Preso(StoppingCriteria):
    """Stops a stuck attempt: left alone it would run to the ceiling (an hour on CPU) and be
    written again all the same."""

    def __init__(self, tokenizer, inicio: int) -> None:
        self._tokenizer = tokenizer
        self._inicio = inicio
        self.disparou = False

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs):
        novos = input_ids.shape[1] - self._inicio
        if novos and novos % VERIFICAR_A_CADA == 0 and not self.disparou:
            self.disparou = preso(texto_inteiro(self._tokenizer, input_ids[0, self._inicio:]))
        return torch.full((input_ids.shape[0],), self.disparou, dtype=torch.bool,
                          device=input_ids.device)


class _Prazo(StoppingCriteria):
    """Stops the generation at the deadline, and notes when the first new token came: how long
    reading the prompt took."""

    def __init__(self, prazo: float | None) -> None:
        self._prazo = prazo
        self.primeiro: float | None = None
        self.disparou = False

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs):
        agora = time.monotonic()
        if self.primeiro is None:
            self.primeiro = agora
        if self._prazo is not None and agora >= self._prazo:
            self.disparou = True
        return torch.full((input_ids.shape[0],), self.disparou, dtype=torch.bool,
                          device=input_ids.device)


def _no_ficheiro(pasta: Path, modelo) -> dict[str, tuple[str, int]]:
    """Where each weight of the model lies in the checkpoint, byte for byte as it is in memory: the
    file and its first byte. A weight saved in another dtype or shape is left out."""
    locais = {}
    for ficheiro in sorted(pasta.glob("*.safetensors")):
        with open(ficheiro, "rb") as f:
            tamanho = int.from_bytes(f.read(8), "little")
            cabecalho = json.loads(f.read(tamanho))
        for nome, info in cabecalho.items():
            if nome != "__metadata__":
                locais[nome] = (str(ficheiro), 8 + tamanho + info["data_offsets"][0],
                                DTYPES_DO_FICHEIRO.get(info["dtype"]), info["shape"])
    return {
        nome: local[:2]
        for nome, parametro in modelo.named_parameters()
        if (local := locais.get(nome)) and local[2:] == (parametro.dtype, list(parametro.shape))
    }


def _abrir(ficheiro: str) -> int:
    """A descriptor that reads the file past the page cache (O_DIRECT) where the file system
    allows it, tried on a first block; else an ordinary one. It stays open while the service runs,
    so that the bytes read are those of the file the model was loaded from."""
    try:
        descritor = os.open(ficheiro, os.O_RDONLY | os.O_DIRECT)
    except (OSError, AttributeError):
        return os.open(ficheiro, os.O_RDONLY)
    teste = mmap.mmap(-1, BLOCO)
    try:
        os.preadv(descritor, [teste], 0)
        return descritor
    except OSError:
        os.close(descritor)
        return os.open(ficheiro, os.O_RDONLY)
    finally:
        teste.close()


def _ler(descritor: int, janela: memoryview, deslocamento: int, n: int) -> int:
    """Bytes [deslocamento, deslocamento + n) of a file into the buffer `janela`, in blocks aligned
    to BLOCO; where in the buffer they start."""
    inicio = deslocamento // BLOCO * BLOCO
    desvio = deslocamento - inicio
    comprimento = -(-(desvio + n) // BLOCO) * BLOCO
    if os.preadv(descritor, [janela[:comprimento]], inicio) < desvio + n:
        raise ArticleError("o checkpoint acaba antes do que o seu cabeçalho diz")
    return desvio


class _NaRAM(torch.nn.Module):
    """A table that stays in main memory while the rest of the model is on the GPU: each call
    looks its rows up on the CPU and sends only those over."""

    def __init__(self, tabela: torch.nn.Module) -> None:
        super().__init__()
        # Out of the module registry, so that moving the model leaves it where it is.
        self._tabela = (tabela,)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        return self._tabela[0](ids.cpu()).to(ids.device)


class ArticleWriter(gpu.ModeloMovel):
    descricao = "o modelo de redação"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._tokenizer = None
        self._compilador = None
        self._paragem: list[int] = []
        # Tokens the checkpoint takes in all, prompt and article together.
        self._contexto = 0
        # The slowest reading measured, in seconds per prompt token (0 until one is).
        self._leitura_medida = 0.0
        self._dispositivo = ""
        # On the GPU, the weights as they are in main memory - the checkpoint, mapped from disk -
        # and where each lies in the checkpoint file: an open descriptor and the first byte.
        self._na_ram: dict[str, torch.Tensor] = {}
        self._no_ficheiro: dict[str, tuple[int, int]] = {}
        # Why the model is not loaded, when it is not.
        self.motivo = ""

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def folga(self) -> int:
        """GPU memory a call holds beyond the weights, for a prompt at the cap (`ARTIGO_PREVISTO`)."""
        return _memoria_de_trabalho(self._settings.article_max_prompt_tokens + ARTIGO_PREVISTO)

    @property
    def ram_ao_sair(self) -> int:
        """Leaving the GPU takes no main memory: the weights there are the checkpoint, mapped."""
        return 0

    def _enviar(self) -> None:
        """Copies the weights to the GPU through a pinned buffer, read from the checkpoint file
        past the page cache (`_abrir`): at the disk's speed, without filling main memory. A weight
        the file does not hold as it is in memory is copied from main memory."""
        fixo = torch.empty(BUFFER_DE_COPIA, dtype=torch.uint8, pin_memory=True)
        janela = memoryview(fixo.numpy())
        passo = BUFFER_DE_COPIA - BLOCO
        for nome, parametro in self._model.named_parameters():
            tipo, forma = parametro.dtype, parametro.shape
            origem = parametro.data.reshape(-1).view(torch.uint8)
            destino = torch.empty_like(origem, device=self._casa)
            local = self._no_ficheiro.get(nome)
            for inicio in range(0, origem.numel(), passo):
                n = min(passo, origem.numel() - inicio)
                if local is None:
                    fixo[:n].copy_(origem[inicio:inicio + n])
                    desvio = 0
                else:
                    desvio = _ler(local[0], janela, local[1] + inicio, n)
                destino[inicio:inicio + n].copy_(fixo[desvio:desvio + n])
            parametro.data = destino.view(tipo).view(forma)
        # What is left: the buffers, a few kilobytes.
        self._model.to(self._casa)

    def para_ram(self) -> None:
        # The weights in main memory are the checkpoint, mapped from disk: leaving the GPU points
        # the model back at them, with nothing to copy back and no memory to find for them.
        self._na_gpu = False
        for nome, parametro in self._model.named_parameters():
            parametro.data = self._na_ram[nome]
        self._model.to("cpu")

    def _recusar(self, motivo: str) -> None:
        self.motivo = motivo
        logger.error("modelo de redação não carregado: %s", motivo)

    def _pasta(self) -> Path:
        """The checkpoint folder: a local path as given, or the pinned revision of a Hugging
        Face id, from the cache when it is there and downloaded (once) when it is not."""
        caminho = self._settings.article_model_path
        if Path(caminho).is_dir():
            return Path(caminho)
        from huggingface_hub import snapshot_download

        revisao = self._settings.article_model_revision or None
        try:
            return Path(snapshot_download(caminho, revision=revisao, local_files_only=True))
        except Exception:  # noqa: BLE001 - not in the cache yet, whatever the hub says
            logger.info("a descarregar %s @ %s para a cache", caminho, revisao)
            return Path(snapshot_download(caminho, revision=revisao))

    def _colocar(self, modelo, pedido: str, pasta: Path) -> str | None:
        """The GPU when asked for, or on auto if it holds the weights and a median article with the
        others moved out; else the CPU (None if a GPU asked for is too small). On the GPU the idle
        towers are dropped and the per-layer embedding table (5.6 GB) stays in main memory."""
        if pedido == "cpu" or not torch.cuda.is_available():
            return "cpu"
        interno = modelo.model
        torres = [getattr(interno, nome) for nome in TORRES
                  if getattr(interno, nome, None) is not None]
        tabela = modelo.get_per_layer_input_embeddings()
        ocupa = gpu.bytes_de(modelo) - gpu.bytes_de(tabela) - sum(map(gpu.bytes_de, torres))
        capacidade = gpu.capacidade()
        minimo = ocupa + _memoria_de_trabalho(TOKENS_MEDIANOS)
        if pedido == "cuda" and capacidade < ocupa:
            self._recusar(f"o modelo precisa de {gpu.gb(ocupa)} na GPU e esta só tem "
                          f"{gpu.gb(capacidade)}")
            return None
        if pedido == "auto" and capacidade < minimo:
            logger.info("o modelo de redação precisa de %s na GPU e esta só tem %s: fica no CPU",
                        gpu.gb(minimo), gpu.gb(capacidade))
            return "cpu"
        for nome in TORRES:
            setattr(interno, nome, None)
        modelo.set_per_layer_input_embeddings(_NaRAM(tabela))
        self._na_ram = {nome: parametro.data for nome, parametro in modelo.named_parameters()}
        locais = _no_ficheiro(pasta, modelo)
        descritores = {ficheiro: _abrir(ficheiro) for ficheiro, _ in locais.values()}
        self._no_ficheiro = {nome: (descritores[ficheiro], deslocamento)
                             for nome, (ficheiro, deslocamento) in locais.items()}
        self._casa = "cuda"
        self.ocupa = ocupa
        return "cuda"

    def load(self) -> None:
        if not self._settings.article_model_path:
            return self._recusar("ARTICLE_MODEL_PATH por definir")
        pedido = (self._settings.article_device or "auto").lower()
        if pedido not in ("auto", "cuda", "cpu"):
            return self._recusar(f"ARTICLE_DEVICE desconhecido: {pedido!r} (auto, cuda ou cpu)")
        if pedido == "cuda" and not torch.cuda.is_available():
            return self._recusar("ARTICLE_DEVICE=cuda, mas este contentor não tem CUDA")
        pasta = self._pasta()
        tamanho = _tamanho_dos_pesos(pasta)
        if not tamanho:
            return self._recusar(f"sem pesos em {pasta}")

        import xgrammar as xgr
        from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig

        tokenizer = AutoTokenizer.from_pretrained(pasta)
        # The whole model, as in the evaluated run (the towers are idle for text), mapped from the
        # checkpoint into main memory; `_colocar` decides where it runs.
        modelo = AutoModelForCausalLM.from_pretrained(pasta, dtype=DTYPE, device_map="cpu").eval()
        dispositivo = self._colocar(modelo, pedido, pasta)
        if dispositivo is None:
            return
        if dispositivo == "cpu":
            # On the CPU the whole checkpoint is read, and the margin also covers the attention
            # cache (about 16 kB per token) and the sliding-window mask, which grows with the
            # square of the prompt (0.8 GB at 16k tokens).
            livre = memoria_disponivel()
            if livre is not None and livre < tamanho * MARGEM_RAM:
                return self._recusar(
                    f"o modelo precisa de cerca de {tamanho * MARGEM_RAM / 1e9:.0f} GB de memória "
                    f"e só há {livre / 1e9:.1f} GB disponíveis neste contentor")
        # Stop tokens from the checkpoint's generation config, as in the evaluated run.
        paragem = GenerationConfig.from_pretrained(pasta).eos_token_id
        self._paragem = [paragem] if isinstance(paragem, int) else list(paragem)
        # The grammar masks the whole output layer, so it is sized by the model, not the
        # tokenizer. Every plan has its own schema: caching compiled grammars only grows.
        texto = modelo.config.get_text_config()
        info = xgr.TokenizerInfo.from_huggingface(tokenizer, vocab_size=texto.vocab_size)
        self._compilador = xgr.GrammarCompiler(info, cache_enabled=False)
        self._contexto = int(texto.max_position_embeddings)
        self._tokenizer = tokenizer
        self._model = modelo
        self._dispositivo = dispositivo
        self.motivo = ""
        logger.info("modelo de redação carregado: %s em %s (%.1f GB, contexto %d, paragem %s)",
                    pasta, dispositivo, tamanho / 1e9, self._contexto, self._paragem)

    def _gerar(self, ids: torch.Tensor, gramatica, penalizacao: float,
               cancelado: threading.Event, prazo: float | None = None) -> dict:
        from transformers import GenerationConfig

        # A fresh configuration: the checkpoint's own samples (temperature 1, top-k 64, top-p
        # 0.95), and greedy decoding must not inherit any of it.
        configuracao = GenerationConfig(
            do_sample=False,
            max_new_tokens=MAX_NOVOS,
            repetition_penalty=penalizacao,
            eos_token_id=self._paragem,
            pad_token_id=self._tokenizer.pad_token_id,
            bos_token_id=self._tokenizer.bos_token_id,
            prefill_chunk_size=LEITURA_EM_BOCADOS if self._dispositivo == "cuda" else None,
        )
        entrada = ids.to(self._model.device)
        guarda = _Preso(self._tokenizer, entrada.shape[1])
        relogio = _Prazo(prazo)
        comeco = time.monotonic()
        with torch.inference_mode():
            saida = self._model.generate(
                input_ids=entrada,
                attention_mask=torch.ones_like(entrada),
                generation_config=configuracao,
                # One per generate() call: it keeps the grammar's state.
                logits_processor=[_Gramatica(gramatica)],
                stopping_criteria=[_Cancelado(cancelado), guarda, relogio],
            )
        if relogio.primeiro is not None:
            leitura = relogio.primeiro - comeco
            self._leitura_medida = max(self._leitura_medida, leitura / entrada.shape[1])
        novos = saida[0, entrada.shape[1]:]
        parou = len(novos) > 0 and int(novos[-1]) in self._paragem
        lido = interpretar(self._tokenizer.decode(novos, skip_special_tokens=True))
        if not parou and lido["estado"] not in ("ok", "reparado"):
            lido["estado"] = "truncado"
        return lido

    def _ha_tempo(self, versao: dict, prazo: float | None) -> bool:
        """Whether an attempt at this plan can start before the deadline."""
        if prazo is None:
            return True
        por_token = max(LEITURA_POR_TOKEN.get(self._dispositivo, LEITURA_POR_TOKEN["cpu"]),
                        self._leitura_medida)
        return prazo - time.monotonic() > versao["ids"].shape[1] * por_token + ESCRITA_MINIMA

    def _versao(self, claim: str, claim_date: str, janela: str, passagens: list[dict]) -> dict:
        """The plan of a set of passages, and the prompt the model reads for it."""
        plano = pv.construir(claim, claim_date, janela, passagens)
        mensagem = render.mensagem(plano)
        prompt = self._tokenizer.apply_chat_template(
            pb.mensagens(mensagem), tokenize=False, add_generation_prompt=True
        )
        # The template already writes the BOS: adding special tokens would put a second one.
        ids = self._tokenizer(prompt, add_special_tokens=False, return_tensors="pt")["input_ids"]
        return {"plano": plano, "ids": ids}

    def _tentar(self, versao: dict, penalizacao: float, cancelado: threading.Event,
                prazo: float | None) -> dict:
        """One attempt at the article of a plan."""
        plano = versao["plano"]
        if versao["ids"].shape[1] + MAX_NOVOS > self._contexto:
            raise ArticleError(f"a prompt tem {versao['ids'].shape[1]} tokens e não deixa "
                               f"{MAX_NOVOS} para o artigo dentro dos {self._contexto} que o "
                               "modelo aceita")
        if "gramatica" not in versao:
            versao["gramatica"] = self._compilador.compile_json_schema(
                json.dumps(esquema.esquema_do_plano(plano), ensure_ascii=False),
                any_whitespace=False,
            )
        try:
            tentativa = self._gerar(versao["ids"], versao["gramatica"], penalizacao, cancelado,
                                    prazo)
        except torch.OutOfMemoryError:
            # Where the driver lends no system memory, a long prompt can outgrow the GPU: the
            # attempt wrote nothing, and the next one reads half the passages.
            torch.cuda.empty_cache()
            logger.warning("a GPU ficou sem memória numa prompt de %d tokens", versao["ids"].shape[1])
            tentativa = interpretar("")
            tentativa["estado"] = "sem_memoria"
        tentativa["versao"] = versao
        tentativa["em_falta"] = _seccoes_em_falta(plano, tentativa["artigo"]["blocks"])
        return tentativa

    def write(self, claim: str, claim_date: str, context: str, passagens: list[dict],
              cancelado: threading.Event | None = None, prazo: float | None = None) -> dict:
        """The article, always with every section of its plan; `prazo` is a `time.monotonic()`
        deadline. An unclean attempt is retried with the heavier penalty; if neither finishes, a
        third reads half the passages, and failing that the fullest attempt is completed."""
        if not self.loaded:
            raise ArticleError("modelo de redação não carregado")
        cancelado = cancelado or threading.Event()
        if cancelado.is_set():
            raise ArticleCancelled("o pedido foi abandonado antes de o artigo começar")

        # The claim's context is the ±1 sentence window the question generator also reads.
        janela = claim_context(context, claim)
        limite = self._settings.article_max_prompt_tokens
        versoes: dict[tuple[str, ...], dict] = {}

        def versao_de(escolhidas: list[dict]) -> dict:
            chave = tuple(p["id"] for p in escolhidas)
            if chave not in versoes:
                versoes[chave] = self._versao(claim, claim_date, janela, escolhidas)
            return versoes[chave]

        lidas = admissao.admitir(
            passagens, lambda escolhidas: versao_de(escolhidas)["ids"].shape[1] <= limite
        )
        completa = versao_de(lidas)
        tentativas: list[dict] = []
        melhor = None
        if self._ha_tempo(completa, prazo):
            melhor = self._tentar(completa, PENALIZACAO, cancelado, prazo)
            tentativas.append(melhor)
            if (precisa_retentar(melhor) and melhor["estado"] != "sem_memoria"
                    and not cancelado.is_set()):
                if self._ha_tempo(completa, prazo):
                    tentativas.append(
                        self._tentar(completa, PENALIZACAO_RETENTATIVA, cancelado, prazo)
                    )
                    if pontos(tentativas[-1]) > pontos(melhor):
                        melhor = tentativas[-1]
        if (melhor is None or melhor["em_falta"]) and not cancelado.is_set():
            reduzidas = admissao.metade(lidas)
            if len(reduzidas) < len(lidas):
                curta = versao_de(reduzidas)
                if self._ha_tempo(curta, prazo):
                    tentativas.append(
                        self._tentar(curta, PENALIZACAO_RETENTATIVA, cancelado, prazo)
                    )
                    if not tentativas[-1]["em_falta"]:
                        melhor = tentativas[-1]
        if cancelado.is_set():
            raise ArticleCancelled("o pedido foi abandonado e a geração parou")

        if melhor is not None and not melhor["em_falta"]:
            artigo, final = melhor["artigo"], melhor["versao"]
        else:
            if tentativas:
                melhor = max(tentativas, key=lambda t: (-len(t["em_falta"]), pontos(t)))
                artigo, final = melhor["artigo"], melhor["versao"]
            else:
                artigo, final = {"title": None, "lead": "", "blocks": []}, completa
            artigo, completadas = completar(final["plano"], artigo)
            logger.warning("artigo completado sem o modelo em %s (%d tentativas)",
                           completadas, len(tentativas))
        evidencias = pv.todas_as_evidencias(final["plano"])

        return {
            "article": artigo,
            "evidence": [
                {"ref": e["ref"], "id": e["id"], "doc_id": e["doc_id"], "begin": e["begin"],
                 "end": e["end"], "label": e["relacao"]}
                for e in evidencias
            ],
        }
