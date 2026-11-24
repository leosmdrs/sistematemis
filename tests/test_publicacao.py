"""Testes da preparação e da publicação de uma versão.

Não há atualização automática: o que se publica é o instalador, com o
resumo SHA-256 que quem baixa confere. Os testes cuidam de que esse
resumo saia certo e chegue à release, e de que nenhum resto do antigo
atualizador volte a entrar no programa.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(
        nome, RAIZ / "build" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


publicar = _carregar("publicar")
publicar_gitlab = _carregar("publicar_gitlab")


def test_resumos_saem_no_formato_do_sha256sum(monkeypatch, tmp_path):
    instalador = tmp_path / "SistemaTemis-9.9.9-setup.exe"
    instalador.write_bytes(b"instalador")
    monkeypatch.setattr(publicar, "DIST", tmp_path)

    alvo = publicar.escrever_resumos(instalador, "9.9.9")

    esperado = hashlib.sha256(b"instalador").hexdigest()
    assert alvo.read_text(encoding="utf-8") == (
        f"{esperado}  SistemaTemis-9.9.9-setup.exe\n")
    assert publicar_gitlab.resumo_declarado(
        alvo, "SistemaTemis-9.9.9-setup.exe") == esperado
    assert not (tmp_path / "versao.json").exists()


def test_resumo_de_arquivo_ausente_e_vazio(tmp_path):
    resumos = tmp_path / "SHA256SUMS.txt"
    resumos.write_text("a" * 64 + "  outro.exe\n", encoding="utf-8")
    assert publicar_gitlab.resumo_declarado(resumos, "SistemaTemis.exe") == ""


def test_release_traz_o_resumo_e_os_dois_anexos():
    corpo = publicar_gitlab.corpo_release(
        "sistemas-nacionais/temis", "9.9.9",
        publicar_gitlab.descricao("Novidades.", "SistemaTemis-9.9.9-setup.exe",
                                  "b" * 64),
        ["SistemaTemis-9.9.9-setup.exe", "SHA256SUMS.txt"])

    assert corpo["tag_name"] == "v9.9.9"
    assert "b" * 64 in corpo["description"]
    assert corpo["description"].startswith("Novidades.")
    nomes = {a["name"] for a in corpo["assets"]["links"]}
    assert nomes == {"SistemaTemis-9.9.9-setup.exe", "SHA256SUMS.txt"}
    for anexo in corpo["assets"]["links"]:
        assert anexo["url"].startswith(
            "https://git.prf.gov.br/api/v4/projects/"
            "sistemas-nacionais%2Ftemis/packages/generic/SistemaTemis/9.9.9/")


def test_o_programa_nao_consulta_atualizacao():
    """A garantia dada à análise de segurança, conferida no código."""
    pacote = RAIZ / "temis"
    assert not (pacote / "atualizacao.py").exists()
    assert not (pacote / "atualizacao_ui.py").exists()
    for arquivo in pacote.rglob("*.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        assert "atualizacao" not in fonte.replace("desatualizacao", ""), arquivo
        assert "versao.json" not in fonte, arquivo
        assert "sistematemis/releases" not in fonte, arquivo
