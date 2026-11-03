"""The state of each model, as the dots on the page's bar show it."""

from app.services.inference import estado_dos_modelos


def estados(corpo, redator="gemma"):
    return {m["id"]: m["estado"] for m in estado_dos_modelos(corpo, redator)}


def test_starting_up_loads_the_encoders_and_the_question_generator_but_not_the_writers():
    corpo = {"status": "a carregar", "models": {"relevance": True, "stance": True,
             "questions": False, "article_gemma": False, "article_amalia": False},
             "motivos": {}, "em_espera": [], "gpu": []}
    assert estados(corpo) == {"questions": "loading", "relevance": "ready", "stance": "ready",
                              "article_gemma": "waiting"}


def test_a_writer_that_takes_its_turn_waits_for_a_run():
    corpo = {"status": "ok", "models": {"relevance": True, "stance": True, "questions": True,
             "article_gemma": False, "article_amalia": False},
             "motivos": {}, "em_espera": ["article_gemma", "article_amalia"], "gpu": ["questions"]}
    assert estados(corpo) == {"questions": "ready", "relevance": "ready", "stance": "ready",
                              "article_gemma": "waiting"}


def test_a_model_that_refused_to_load_says_why():
    motivo = "o modelo precisa de cerca de 21 GB de memória e só há 13.3 GB disponíveis"
    corpo = {"status": "degradado", "models": {"relevance": True, "stance": True,
             "questions": True, "article_gemma": False, "article_amalia": False},
             "motivos": {"article_amalia": motivo}, "em_espera": [], "gpu": []}
    modelos = {m["id"]: m for m in estado_dos_modelos(corpo, "amalia")}
    assert modelos["article_amalia"]["estado"] == "error"
    assert modelos["article_amalia"]["detalhe"] == motivo


def test_only_the_writer_chosen_is_listed():
    corpo = {"status": "ok", "models": {}, "motivos": {"article_amalia": "sem memória"},
             "em_espera": [], "gpu": []}
    assert "article_amalia" not in estados(corpo, "gemma")
    assert "article_gemma" not in estados(corpo, "amalia")
    assert list(estados(corpo, "amalia_q4")) == ["questions", "relevance", "stance",
                                                  "article_amalia_q4"]


def test_a_model_on_the_gpu_says_so():
    corpo = {"status": "ok", "models": {"relevance": True, "stance": True, "questions": True,
             "article_gemma": True}, "motivos": {}, "em_espera": [], "gpu": ["questions"]}
    na_gpu = {m["id"]: m["na_gpu"] for m in estado_dos_modelos(corpo, "gemma")}
    assert na_gpu == {"questions": True, "relevance": False, "stance": False,
                      "article_gemma": False}


def test_the_amalia_models_on_modal_follow_the_state_of_its_gpu():
    corpo = {"status": "ok", "models": {"relevance": True, "stance": True, "questions": True,
             "article_gemma": True, "article_amalia": True}, "motivos": {}, "em_espera": [],
             "gpu": [], "remotos": {"questions": "desligado", "article_amalia": "desligado"}}
    assert estados(corpo, "amalia") == {"questions": "waiting", "relevance": "ready",
                                        "stance": "ready", "article_amalia": "waiting"}
    corpo["remotos"] = {"questions": "a_ligar", "article_amalia": "a_ligar"}
    assert estados(corpo, "amalia")["questions"] == "loading"
    assert estados(corpo, "amalia")["article_amalia"] == "loading"
    corpo["remotos"] = {"questions": "ligado", "article_amalia": "ligado"}
    assert set(estados(corpo, "amalia").values()) == {"ready"}


def test_a_model_on_modal_that_refused_to_load_still_says_why():
    corpo = {"status": "degradado", "models": {"relevance": True, "stance": True,
             "questions": False}, "motivos": {"questions": "a API está indisponível"},
             "em_espera": [], "gpu": [], "remotos": {"questions": "desligado"}}
    assert estados(corpo)["questions"] == "error"


def test_the_gemma_writer_is_named_after_the_model_it_runs():
    from app.schemas import nome_do_modelo

    assert nome_do_modelo("google/gemma-4-31b-it") == "Gemma 4 31B"
    assert nome_do_modelo("google/gemma-4-26b-a4b-it:free") == "Gemma 4 26B A4B (free)"
