"""Testes da assinatura do manifesto de atualização.

Três camadas: o algoritmo (contra os vetores da RFC 8032 e contra uma
biblioteca independente), a exigência de assinatura no atualizador, e a
ferramenta com que quem publica gera a chave e assina.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path

import pytest

from temis import atualizacao as at
from temis import ed25519

RAIZ = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "assinatura", RAIZ / "build" / "assinatura.py")
ferramenta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ferramenta)

# RFC 8032, seção 7.1 — (chave privada, chave pública, mensagem, assinatura)
VETORES = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


# ─────────────────────────────────────────
#  o algoritmo
# ─────────────────────────────────────────

@pytest.mark.parametrize("privada, publica, mensagem, assinatura", VETORES)
def test_vetores_da_rfc_8032(privada, publica, mensagem, assinatura):
    privada, publica, mensagem, assinatura = (
        bytes.fromhex(x) for x in (privada, publica, mensagem, assinatura))
    assert ed25519.publica_de(privada) == publica
    assert ed25519.assinar(privada, mensagem) == assinatura
    assert ed25519.confere(publica, mensagem, assinatura)


def test_qualquer_bit_trocado_invalida():
    privada, publica, _, _ = (bytes.fromhex(x) for x in VETORES[2])
    mensagem = b"SistemaTemis atualizacao v1\n1.16.0\n" + b"a" * 64
    assinatura = ed25519.assinar(privada, mensagem)
    assert ed25519.confere(publica, mensagem, assinatura)
    for i in range(0, 64, 5):
        ruim = bytearray(assinatura)
        ruim[i] ^= 1
        assert not ed25519.confere(publica, mensagem, bytes(ruim))
    assert not ed25519.confere(publica, mensagem + b"x", assinatura)
    outra = ed25519.publica_de(bytes.fromhex(VETORES[0][0]))
    assert not ed25519.confere(outra, mensagem, assinatura)


@pytest.mark.parametrize("publica, assinatura", [
    (b"", b""), (b"\x00" * 31, b"\x00" * 64), (b"\x00" * 32, b"\x00" * 63),
    (b"\xff" * 32, b"\xff" * 64), (b"\x00" * 32, b"\x00" * 64),
])
def test_entrada_malformada_e_recusada_sem_levantar(publica, assinatura):
    assert ed25519.confere(publica, b"mensagem", assinatura) is False


def test_confere_com_biblioteca_independente():
    cryptography = pytest.importorskip("cryptography")      # noqa: F841
    from cryptography.hazmat.primitives import serialization as s
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    for i in range(25):
        privada, mensagem = os.urandom(32), os.urandom(i * 11)
        chave = Ed25519PrivateKey.from_private_bytes(privada)
        publica = chave.public_key().public_bytes(
            s.Encoding.Raw, s.PublicFormat.Raw)
        assert ed25519.publica_de(privada) == publica
        assert ed25519.assinar(privada, mensagem) == chave.sign(mensagem)
        assert ed25519.confere(publica, mensagem, chave.sign(mensagem))


# ─────────────────────────────────────────
#  o atualizador
# ─────────────────────────────────────────

PRIVADA = bytes.fromhex(VETORES[0][0])
PUBLICA = VETORES[0][1]
RESUMO = "ab" * 32
TAMANHO = 123456


@pytest.fixture(autouse=True)
def _sem_politica(monkeypatch):
    monkeypatch.setattr(at, "_ler_registro", lambda: {})


class _Resposta:
    def __init__(self, dados):
        self._dados = dados

    def read(self, n=-1):
        return self._dados

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _manifesto(versao="99.0.0", sha256=RESUMO, tamanho=TAMANHO,
               assinar_com=PRIVADA, **extra):
    dados = {"versao": versao, "url": at.url_do_instalador(versao),
             "sha256": sha256, "tamanho": tamanho, "notas": "novidades"}
    if assinar_com is not None:
        dados["assinatura"] = ferramenta.assinar(
            assinar_com, versao, sha256, tamanho)
    dados.update(extra)
    return dados


def _servir(monkeypatch, dados):
    monkeypatch.setattr(
        at, "_abrir",
        lambda url: _Resposta(json.dumps(dados).encode("utf-8")))


def test_sem_chave_registrada_a_assinatura_nao_e_exigida(monkeypatch):
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", ())
    _servir(monkeypatch, _manifesto(assinar_com=None))
    assert at.consultar("https://x/versao.json").versao == "99.0.0"


def test_manifesto_assinado_e_aceito(monkeypatch):
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA,))
    _servir(monkeypatch, _manifesto())
    assert at.consultar("https://x/versao.json").versao == "99.0.0"


def test_manifesto_sem_assinatura_e_recusado(monkeypatch):
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA,))
    _servir(monkeypatch, _manifesto(assinar_com=None))
    with pytest.raises(at.ErroAtualizacao, match="assinatura de quem publica"):
        at.consultar("https://x/versao.json")


def test_assinatura_de_outra_chave_e_recusada(monkeypatch):
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA,))
    intrusa = bytes.fromhex(VETORES[1][0])
    _servir(monkeypatch, _manifesto(assinar_com=intrusa))
    with pytest.raises(at.ErroAtualizacao, match="assinatura"):
        at.consultar("https://x/versao.json")


@pytest.mark.parametrize("troca", [
    {"sha256": "cd" * 32},                     # outro instalador
    {"tamanho": TAMANHO + 1},
    {"versao": "99.0.1", "url": at.url_do_instalador("99.0.1")},
])
def test_trocar_o_que_foi_assinado_invalida(monkeypatch, troca):
    """Quem toma o repositório reaproveita uma assinatura antiga."""
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA,))
    dados = _manifesto()
    dados.update(troca)
    _servir(monkeypatch, dados)
    with pytest.raises(at.ErroAtualizacao, match="assinatura"):
        at.consultar("https://x/versao.json")


def test_notas_nao_sao_assinadas_e_podem_mudar(monkeypatch):
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA,))
    _servir(monkeypatch, _manifesto(notas="outro texto"))
    assert at.consultar("https://x/versao.json").notas == "outro texto"


def test_chave_de_reserva_tambem_vale(monkeypatch):
    reserva = bytes.fromhex(VETORES[2][0])
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA, VETORES[2][1]))
    _servir(monkeypatch, _manifesto(assinar_com=reserva))
    assert at.consultar("https://x/versao.json") is not None


def test_versao_que_nao_e_mais_nova_segue_em_silencio(monkeypatch):
    # A release corrente pode ser anterior à chave, e sem assinatura:
    # isso não é erro a mostrar a cada abertura.
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA,))
    _servir(monkeypatch, _manifesto(versao="0.0.1", assinar_com=None))
    assert at.consultar("https://x/versao.json") is None


def test_baixar_tambem_exige_a_assinatura(monkeypatch, tmp_path):
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA,))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(at, "_abrir",
                        lambda url, tempo=30: pytest.fail("baixou"))
    info = at.de_dict(_manifesto(assinar_com=None))
    with pytest.raises(at.ErroAtualizacao, match="assinatura"):
        at.baixar(info)


def test_assinatura_que_nao_e_base64_nao_estoura(monkeypatch):
    monkeypatch.setattr(at, "CHAVES_PUBLICAS", (PUBLICA, "não é hex"))
    assert at.assinatura_confere("1.0.0", RESUMO, 1, "???") is False
    assert at.assinatura_confere("1.0.0", RESUMO, 1, "") is False


# ─────────────────────────────────────────
#  a ferramenta de quem publica
# ─────────────────────────────────────────

@pytest.fixture
def fonte(tmp_path, monkeypatch):
    """Uma cópia do bloco de chaves, para não tocar no programa."""
    alvo = tmp_path / "atualizacao.py"
    alvo.write_text(
        "antes\n# <chaves-publicas>\nCHAVES_PUBLICAS: tuple = ()\n"
        "# </chaves-publicas>\ndepois\n", encoding="utf-8")
    monkeypatch.setattr(ferramenta, "FONTE", alvo)
    return alvo


def test_o_programa_publicado_tem_o_bloco_de_chaves():
    assert isinstance(ferramenta.chaves_registradas(
        RAIZ / "temis" / "atualizacao.py"), list)


def test_gerar_registrar_assinar_e_conferir(tmp_path, fonte, capsys,
                                            monkeypatch):
    chave = tmp_path / "pendrive" / "temis.chave"
    assert ferramenta.main(["gerar-chave", str(chave)]) == 0
    assert chave.is_file()
    publicas = ferramenta.chaves_registradas(fonte)
    assert len(publicas) == 1
    texto = fonte.read_text(encoding="utf-8")
    assert texto.startswith("antes\n") and texto.endswith("depois\n")
    # A chave privada não vai para o programa.
    assert ferramenta.ler_chave(chave).hex() not in texto

    capsys.readouterr()
    assert ferramenta.main(["assinar", "--chave", str(chave),
                            "--versao", "1.16.0", "--sha256", RESUMO,
                            "--tamanho", str(TAMANHO)]) == 0
    assinatura = capsys.readouterr().out.strip()
    assert len(base64.b64decode(assinatura)) == 64

    monkeypatch.setattr(at, "CHAVES_PUBLICAS", tuple(publicas))
    assert at.assinatura_confere("1.16.0", RESUMO, TAMANHO, assinatura)
    assert ferramenta.main(["conferir", "--versao", "1.16.0",
                            "--sha256", RESUMO, "--tamanho", str(TAMANHO),
                            "--assinatura", assinatura]) == 0
    assert ferramenta.main(["conferir", "--versao", "1.16.1",
                            "--sha256", RESUMO, "--tamanho", str(TAMANHO),
                            "--assinatura", assinatura]) == 1
    assert ferramenta.main(["exige"]) == 0


def test_uma_chave_nunca_e_gravada_por_cima_de_outra(tmp_path, fonte):
    chave = tmp_path / "temis.chave"
    ferramenta.main(["gerar-chave", str(chave)])
    original = chave.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        ferramenta.main(["gerar-chave", str(chave)])
    assert chave.read_text(encoding="utf-8") == original


def test_chave_de_reserva_e_acrescentada_e_nao_repetida(tmp_path, fonte):
    um, dois = tmp_path / "uso.chave", tmp_path / "reserva.chave"
    ferramenta.main(["gerar-chave", str(um)])
    ferramenta.main(["gerar-chave", str(dois)])
    ferramenta.main(["registrar", str(um)])            # já estava
    assert len(ferramenta.chaves_registradas(fonte)) == 2


def test_sem_chave_registrada_o_fluxo_nao_exige(fonte):
    assert ferramenta.main(["exige"]) == 1


@pytest.mark.parametrize("versao, sha256, tamanho", [
    ("1.16", RESUMO, 10), ("1.16.0", "curto", 10), ("1.16.0", RESUMO, 0),
])
def test_assinar_recusa_dado_malformado(versao, sha256, tamanho):
    with pytest.raises(SystemExit):
        ferramenta.assinar(PRIVADA, versao, sha256, tamanho)


def test_arquivo_que_nao_e_chave_e_recusado(tmp_path):
    falso = tmp_path / "x.txt"
    falso.write_text("# comentario\nnao e chave\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ferramenta.ler_chave(falso)
