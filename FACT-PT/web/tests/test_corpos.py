"""Request bodies: JSON only, of a known and bounded size, refused before anything reads them; and
no XML parser anywhere in the site, so an XML attack has nothing to reach."""

import ast
from pathlib import Path

import pytest

from app.main import CORPO_MAXIMO
from conftest import PALAVRA_PASSE

WEB = Path(__file__).resolve().parents[1]

XXE = """<?xml version="1.0"?>
<!DOCTYPE entrada [<!ENTITY segredo SYSTEM "file:///etc/passwd">]>
<entrada><utilizador>admin</utilizador><palavra_passe>&segredo;</palavra_passe></entrada>"""

MIL_MILHOES_DE_RISOS = """<?xml version="1.0"?>
<!DOCTYPE lol [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>
<lol>&lol3;</lol>"""


def enviar(cliente, url, corpo, tipo):
    return cliente.post(url, content=corpo, headers={"Content-Type": tipo})


@pytest.mark.parametrize("corpo", [XXE, MIL_MILHOES_DE_RISOS])
@pytest.mark.parametrize("tipo", ["application/xml", "text/xml", "application/soap+xml"])
def test_an_xml_body_is_refused_at_the_door(cliente, corpo, tipo):
    for url in ("/api/sessao", "/api/run"):
        resposta = enviar(cliente, url, corpo, tipo)
        assert resposta.status_code == 415
        assert "set-cookie" not in resposta.headers
        # The refusal carries the security headers, as every response does.
        assert resposta.headers["x-content-type-options"] == "nosniff"


def test_xml_labelled_as_json_is_never_read_as_xml(cliente):
    assert enviar(cliente, "/api/sessao", XXE, "application/json").status_code == 422


def test_the_bodies_a_cross_site_form_can_send_are_refused(cliente):
    for tipo in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        assert enviar(cliente, "/api/sessao", '{"utilizador": "admin", "palavra_passe": "x"}', tipo).status_code == 415


def test_a_body_of_unknown_length_is_refused(cliente):
    resposta = cliente.post("/api/sessao", content=iter([b'{"utilizador": "admin", "palavra_passe": "x"}']),
                            headers={"Content-Type": "application/json"})
    assert resposta.status_code == 411


def test_an_oversized_body_is_refused_before_it_is_read(cliente):
    corpo = b'{"utilizador": "admin", "palavra_passe": "' + b"x" * CORPO_MAXIMO + b'"}'
    assert enviar(cliente, "/api/sessao", corpo, "application/json").status_code == 413


def test_the_refusal_speaks_the_language_of_the_page(cliente):
    resposta = cliente.post("/api/sessao", content=XXE, headers={
        "Content-Type": "application/xml", "Accept-Language": "en-GB"})
    assert resposta.json()["detail"] == "The request must be sent as JSON."


def test_json_with_a_charset_still_signs_in(cliente):
    resposta = enviar(cliente, "/api/sessao", f'{{"utilizador": "admin", "palavra_passe": "{PALAVRA_PASSE}"}}',
                      "application/json; charset=utf-8")
    assert resposta.status_code == 204


def test_requests_without_a_body_are_untouched(cliente):
    assert cliente.get("/api/sessao").status_code == 200
    assert cliente.delete("/api/sessao").status_code == 204


def test_no_module_of_the_site_imports_an_xml_parser():
    """The standard library's XML parsers expand entities, and lxml can resolve external ones.
    Should the site ever need XML, parse it with `defusedxml`, never with these."""
    proibidos = {"xml", "lxml", "xmltodict", "untangle"}
    encontrados = []
    for ficheiro in [*(WEB / "app").rglob("*.py"), *(WEB / "inference" / "server").rglob("*.py")]:
        for no in ast.walk(ast.parse(ficheiro.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.level == 0:
                nomes = [no.module or ""]
            else:
                continue
            encontrados += [f"{ficheiro.relative_to(WEB)}: {n}" for n in nomes
                            if n.split(".")[0] in proibidos]
    assert encontrados == []
