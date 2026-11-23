"""Testes dos endereços de publicação.

O atualizador, o manifesto e a release precisam concordar sobre onde cada
arquivo fica. Cada um mora num arquivo diferente, e divergência entre eles
não quebra nada à vista: a estação só deixa de achar a versão nova.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from temis import atualizacao as at

RAIZ = Path(__file__).resolve().parents[1]


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(
        nome, RAIZ / "build" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


publicar = _carregar("publicar")
publicar_gitlab = _carregar("publicar_gitlab")


def test_os_tres_arquivos_apontam_para_o_mesmo_projeto():
    assert publicar.SERVIDOR == at.SERVIDOR == publicar_gitlab.SERVIDOR
    assert (publicar.REPOSITORIO_PADRAO == at.REPOSITORIO
            == publicar_gitlab.REPOSITORIO_PADRAO)


def test_manifesto_e_lido_do_permalink_da_ultima_release():
    assert at.URL_MANIFESTO == (
        "https://git.prf.gov.br/sistemas-nacionais/temis"
        "/-/releases/permalink/latest/downloads/versao.json")


def test_manifesto_aponta_o_instalador_para_o_anexo_da_release(
        monkeypatch, tmp_path):
    instalador = tmp_path / "SistemaTemis-9.9.9-setup.exe"
    instalador.write_bytes(b"instalador")
    monkeypatch.setattr(publicar, "DIST", tmp_path)

    publicar.escrever_manifesto(instalador, "9.9.9", "notas",
                                publicar.REPOSITORIO_PADRAO, False)

    dados = json.loads((tmp_path / "versao.json").read_text(encoding="utf-8"))
    assert dados["url"] == (
        "https://git.prf.gov.br/sistemas-nacionais/temis"
        "/-/releases/v9.9.9/downloads/SistemaTemis-9.9.9-setup.exe")
    # A estação recusa manifesto cujo endereço não seja exatamente este.
    assert dados["url"] == at.url_do_instalador("9.9.9")
    assert at.de_dict(dados).valida


def test_release_cadastra_os_anexos_nos_caminhos_que_a_estacao_procura():
    corpo = publicar_gitlab.corpo_release(
        "sistemas-nacionais/temis", "9.9.9", "notas",
        ["SistemaTemis-9.9.9-setup.exe", "versao.json"])

    assert corpo["tag_name"] == "v9.9.9"
    caminhos = {a["direct_asset_path"] for a in corpo["assets"]["links"]}
    # O fim do endereço do manifesto e o do instalador são estes caminhos.
    assert at.URL_MANIFESTO.endswith("/downloads/versao.json")
    assert caminhos == {"/versao.json", "/SistemaTemis-9.9.9-setup.exe"}
    for anexo in corpo["assets"]["links"]:
        assert anexo["url"].startswith(
            "https://git.prf.gov.br/api/v4/projects/"
            "sistemas-nacionais%2Ftemis/packages/generic/SistemaTemis/9.9.9/")
