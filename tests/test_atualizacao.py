"""Testes de temis/atualizacao.py — verificação, download e instalação."""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest

from temis import atualizacao as at


class FalsaResposta:
    """Substitui o objeto devolvido por urlopen em urllib.request."""

    def __init__(self, dados: bytes, headers: dict | None = None):
        self._dados = dados
        self.headers = headers or {}

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            saida, self._dados = self._dados, b""
            return saida
        saida, self._dados = self._dados[:n], self._dados[n:]
        return saida

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ─────────────────────────────────────────
#  VERSÃO
# ─────────────────────────────────────────

@pytest.mark.parametrize("a, b, esperado", [
    ("1.2.0", "1.14.0", -1),
    ("1.14.0", "1.14.0", 0),
    ("2.0.0", "1.14.0", 1),
    ("1.2", "1.2.0", 0),
    ("", "1.0.0", -1),
    ("1.2.3.4", "1.2.3", 1),
])
def test_comparar(a, b, esperado):
    assert at.comparar(a, b) == esperado


def test_mais_nova_usa_versao_instalada_por_padrao():
    assert at.mais_nova("99.0.0") is True
    assert at.mais_nova("0.0.1") is False


def test_mais_nova_compara_com_instalada_explicita():
    assert at.mais_nova("1.5.0", instalada="1.4.0") is True
    assert at.mais_nova("1.4.0", instalada="1.5.0") is False


# ─────────────────────────────────────────
#  Atualizacao / de_dict
# ─────────────────────────────────────────

def test_atualizacao_valida_exige_versao_url_e_hash_64():
    completa = at.Atualizacao(versao="1.0.0", url="https://x", sha256="a" * 64)
    assert completa.valida is True
    assert at.Atualizacao().valida is False
    assert at.Atualizacao(versao="1.0.0", url="https://x", sha256="curto").valida is False


@pytest.mark.parametrize("tamanho, esperado", [
    (500, "500 bytes"),
    (2048, "2 KB"),
    (5 * (1 << 20), "5,0 MB"),
])
def test_tamanho_legivel(tamanho, esperado):
    assert at.Atualizacao(tamanho=tamanho).tamanho_legivel == esperado


def test_de_dict_preenche_e_normaliza_campos():
    resultado = at.de_dict({
        "versao": " 1.2.3 ",
        "url": " https://x/y ",
        "sha256": "ABC ",
        "tamanho": "1024",
        "notas": " novidades ",
        "publicado": "2026-01-01",
        "critica": True,
    })
    assert resultado.versao == "1.2.3"
    assert resultado.url == "https://x/y"
    assert resultado.sha256 == "abc"
    assert resultado.tamanho == 1024
    assert resultado.critica is True


def test_de_dict_com_dicionario_vazio_gera_atualizacao_invalida():
    assert at.de_dict({}).valida is False


# ─────────────────────────────────────────
#  _abrir
# ─────────────────────────────────────────

def test_abrir_recusa_url_sem_https():
    with pytest.raises(at.ErroAtualizacao):
        at._abrir("http://exemplo.com/versao.json")


def test_abrir_delega_para_urlopen(monkeypatch):
    capturado = {}

    def falso_urlopen(pedido, timeout):
        capturado["url"] = pedido.full_url
        capturado["agente"] = pedido.headers.get("User-agent")
        capturado["timeout"] = timeout
        return FalsaResposta(b"{}")

    monkeypatch.setattr(at.urllib.request, "urlopen", falso_urlopen)
    at._abrir("https://exemplo.com/versao.json", tempo=9)
    assert capturado["url"] == "https://exemplo.com/versao.json"
    assert capturado["agente"] == at.AGENTE
    assert capturado["timeout"] == 9


# ─────────────────────────────────────────
#  consultar
# ─────────────────────────────────────────

MANIFESTO_OK = json.dumps({
    "versao": "99.0.0",
    "url": "https://exemplo.com/setup.exe",
    "sha256": "a" * 64,
}).encode("utf-8")


def test_consultar_devolve_atualizacao_quando_mais_nova(monkeypatch):
    monkeypatch.setattr(at, "_abrir", lambda url: FalsaResposta(MANIFESTO_OK))
    resultado = at.consultar("https://exemplo.com/versao.json")
    assert resultado is not None
    assert resultado.versao == "99.0.0"


def test_consultar_devolve_none_quando_nao_ha_versao_mais_nova(monkeypatch):
    manifesto = json.dumps({
        "versao": "0.0.1",
        "url": "https://exemplo.com/setup.exe",
        "sha256": "a" * 64,
    }).encode("utf-8")
    monkeypatch.setattr(at, "_abrir", lambda url: FalsaResposta(manifesto))
    assert at.consultar("https://exemplo.com/versao.json") is None


def test_consultar_manifesto_incompleto(monkeypatch):
    manifesto = json.dumps({"versao": "99.0.0"}).encode("utf-8")
    monkeypatch.setattr(at, "_abrir", lambda url: FalsaResposta(manifesto))
    with pytest.raises(at.ErroAtualizacao, match="incompleto"):
        at.consultar("https://exemplo.com/versao.json")


def test_consultar_json_ilegivel(monkeypatch):
    monkeypatch.setattr(at, "_abrir", lambda url: FalsaResposta(b"{nao e json"))
    with pytest.raises(at.ErroAtualizacao, match="ilegível"):
        at.consultar("https://exemplo.com/versao.json")


def test_consultar_resposta_grande_demais(monkeypatch):
    grande = b"x" * (at.LIMITE_MANIFESTO + 10)
    monkeypatch.setattr(at, "_abrir", lambda url: FalsaResposta(grande))
    with pytest.raises(at.ErroAtualizacao, match="inesperada"):
        at.consultar("https://exemplo.com/versao.json")


def test_consultar_http_404(monkeypatch):
    def levanta(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(at, "_abrir", levanta)
    with pytest.raises(at.ErroAtualizacao, match="Nenhuma versão publicada"):
        at.consultar("https://exemplo.com/versao.json")


def test_consultar_http_outro_codigo(monkeypatch):
    def levanta(url):
        raise urllib.error.HTTPError(url, 500, "Erro", {}, None)
    monkeypatch.setattr(at, "_abrir", levanta)
    with pytest.raises(at.ErroAtualizacao, match="500"):
        at.consultar("https://exemplo.com/versao.json")


def test_consultar_url_error(monkeypatch):
    def levanta(url):
        raise urllib.error.URLError("sem rede")
    monkeypatch.setattr(at, "_abrir", levanta)
    with pytest.raises(at.ErroAtualizacao, match="Sem acesso"):
        at.consultar("https://exemplo.com/versao.json")


def test_consultar_timeout(monkeypatch):
    def levanta(url):
        raise TimeoutError("expirou")
    monkeypatch.setattr(at, "_abrir", levanta)
    with pytest.raises(at.ErroAtualizacao, match="Falha de rede"):
        at.consultar("https://exemplo.com/versao.json")


# ─────────────────────────────────────────
#  pasta_download
# ─────────────────────────────────────────

def test_pasta_download_usa_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("TMPDIR", raising=False)
    destino = at.pasta_download()
    assert destino == tmp_path / "SistemaTemis" / "atualizacoes"
    assert destino.is_dir()


def test_pasta_download_cai_para_tmpdir_do_sistema(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(at.tempfile, "gettempdir", lambda: str(tmp_path))
    destino = at.pasta_download()
    assert destino == tmp_path / "SistemaTemis" / "atualizacoes"
    assert destino.is_dir()


# ─────────────────────────────────────────
#  baixar
# ─────────────────────────────────────────

def _info_para(conteudo: bytes) -> at.Atualizacao:
    return at.Atualizacao(
        versao="9.9.9",
        url="https://exemplo.com/setup.exe",
        sha256=hashlib.sha256(conteudo).hexdigest(),
        tamanho=len(conteudo),
    )


def test_baixar_confere_hash_e_devolve_caminho_definitivo(monkeypatch, tmp_path):
    conteudo = b"conteudo-do-instalador" * 100
    info = _info_para(conteudo)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(at, "_abrir", lambda url, tempo=30: FalsaResposta(conteudo))

    eventos = []
    caminho = at.baixar(info, progresso=lambda feito, total: eventos.append((feito, total)))

    assert caminho.name == "SistemaTemis-9.9.9-setup.exe"
    assert caminho.read_bytes() == conteudo
    assert not caminho.with_suffix(".parcial").exists()
    assert eventos[-1][0] == len(conteudo)


def test_baixar_cancelado_remove_parcial(monkeypatch, tmp_path):
    info = _info_para(b"dados")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(at, "_abrir", lambda url, tempo=30: FalsaResposta(b"dados"))

    with pytest.raises(at.ErroAtualizacao, match="cancelado"):
        at.baixar(info, cancelado=lambda: True)

    destino = at.pasta_download() / "SistemaTemis-9.9.9-setup.exe"
    assert not destino.with_suffix(".parcial").exists()
    assert not destino.exists()


def test_baixar_hash_divergente_descarta_arquivo(monkeypatch, tmp_path):
    conteudo = b"conteudo-real"
    info = at.Atualizacao(
        versao="9.9.9", url="https://exemplo.com/setup.exe",
        sha256="0" * 64, tamanho=len(conteudo),
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(at, "_abrir", lambda url, tempo=30: FalsaResposta(conteudo))

    with pytest.raises(at.ErroAtualizacao, match="não confere"):
        at.baixar(info)

    destino = at.pasta_download() / "SistemaTemis-9.9.9-setup.exe"
    assert not destino.exists()
    assert not destino.with_suffix(".parcial").exists()


def test_baixar_falha_de_rede_descarta_parcial(monkeypatch, tmp_path):
    info = _info_para(b"dados")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def levanta(url, tempo=30):
        raise urllib.error.URLError("caiu a rede")

    monkeypatch.setattr(at, "_abrir", levanta)
    with pytest.raises(at.ErroAtualizacao, match="Falha ao baixar"):
        at.baixar(info)


# ─────────────────────────────────────────
#  instalar / instalado_como_programa
# ─────────────────────────────────────────

def test_instalar_arquivo_inexistente(tmp_path):
    with pytest.raises(at.ErroAtualizacao, match="não foi encontrado"):
        at.instalar(tmp_path / "nao-existe.exe")


def test_instalar_recusa_fora_do_windows(monkeypatch, tmp_path):
    arquivo = tmp_path / "setup.exe"
    arquivo.write_bytes(b"x")
    monkeypatch.setattr(at.sys, "platform", "linux")
    with pytest.raises(at.ErroAtualizacao, match="Windows"):
        at.instalar(arquivo)


def test_instalar_chama_popen_no_windows(monkeypatch, tmp_path):
    arquivo = tmp_path / "setup.exe"
    arquivo.write_bytes(b"x")
    monkeypatch.setattr(at.sys, "platform", "win32")
    capturado = {}

    def falso_popen(args, close_fds):
        capturado["args"] = args
        capturado["close_fds"] = close_fds

    monkeypatch.setattr(at.subprocess, "Popen", falso_popen)
    at.instalar(arquivo)
    assert capturado["args"][0] == str(arquivo)
    assert capturado["args"][1:] == at.ARGUMENTOS_INSTALADOR
    assert capturado["close_fds"] is True


def test_instalar_erro_ao_iniciar_processo(monkeypatch, tmp_path):
    arquivo = tmp_path / "setup.exe"
    arquivo.write_bytes(b"x")
    monkeypatch.setattr(at.sys, "platform", "win32")

    def falso_popen(args, close_fds):
        raise OSError("negado")

    monkeypatch.setattr(at.subprocess, "Popen", falso_popen)
    with pytest.raises(at.ErroAtualizacao, match="Não foi possível iniciar"):
        at.instalar(arquivo)


def test_instalado_como_programa(monkeypatch):
    monkeypatch.setattr(at.sys, "frozen", True, raising=False)
    assert at.instalado_como_programa() is True
    monkeypatch.setattr(at.sys, "frozen", False, raising=False)
    assert at.instalado_como_programa() is False


# ─────────────────────────────────────────
#  PREFERÊNCIAS
# ─────────────────────────────────────────

def test_arquivo_config_usa_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    caminho = at.arquivo_config()
    assert caminho == tmp_path / "SistemaTemis" / "config.json"
    assert caminho.parent.is_dir()


def test_arquivo_config_cai_para_home_config(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    caminho = at.arquivo_config()
    assert caminho == tmp_path / ".config" / "SistemaTemis" / "config.json"


def test_preferencias_dispensou():
    prefs = at.Preferencias(versao_dispensada="1.2.3")
    assert prefs.dispensou("1.2.3") is True
    assert prefs.dispensou("9.9.9") is False
    assert prefs.dispensou("") is False


def test_ler_preferencias_arquivo_ausente_devolve_padrao(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    prefs = at.ler_preferencias()
    assert prefs == at.Preferencias()


def test_gravar_e_ler_preferencias_ida_e_volta(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    original = at.Preferencias(verificar=False, versao_dispensada="1.5.0")
    at.gravar_preferencias(original)

    lida = at.ler_preferencias()
    assert lida == original
    assert not at.arquivo_config().with_suffix(".tmp").exists()


def test_ler_preferencias_json_invalido_devolve_padrao(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    at.arquivo_config().write_text("{ nao e json", encoding="utf-8")
    assert at.ler_preferencias() == at.Preferencias()
