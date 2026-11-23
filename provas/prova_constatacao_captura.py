"""Provas da captura, na Constatação Web.

Duas coisas se conferem aqui, as duas sobre a correspondência entre o que
o termo declara e o que está em disco.

A primeira: uma captura conclui **uma vez**. O navegador entrega o PDF e
o código-fonte cada um a seu tempo, e há um prazo para o caso de algum
não chegar. Sem trava, o prazo concluía de novo a captura já concluída,
regravava a imagem da tela com o que a janela mostrasse vinte segundos
depois e a punha duas vezes na diligência — com resumo coerente sobre o
arquivo trocado, de modo que nenhuma conferência acusava.

A segunda: a pasta de uma captura nunca é reaproveitada. Numerada pela
quantidade de capturas listadas, bastava remover uma para a seguinte
gravar por cima dos arquivos de outra.

O método `_capturar` é o real. Página, janela e rede são simuladas: não
se abre navegador nem se toca a rede.
"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, QUrl                # noqa: E402
from PyQt6.QtWidgets import QApplication              # noqa: E402

from temis.tools import constatacao as tela           # noqa: E402
from temis.tools import constatacao_core as cc        # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Imagem:
    def __init__(self, janela):
        self._conteudo = janela.mostrando

    def save(self, caminho):
        Path(caminho).write_bytes(self._conteudo)
        return True


class _Janela:
    mostrando = b"pagina A"

    def grab(self):
        return _Imagem(self)


class _Pagina:
    """Guarda os retornos, para o teste entregá-los quando quiser."""

    def __init__(self):
        self.ao_pdf = self.ao_html = None

    def url(self):
        return QUrl("https://exemplo.gov.br/noticia")

    def title(self):
        return "Notícia"

    def printToPdf(self, retorno):
        self.ao_pdf = retorno

    def toHtml(self, retorno):
        self.ao_html = retorno


class _Botao:
    def setEnabled(self, _):
        pass


class _Sinal:
    def __init__(self):
        self.mensagens = []

    def emit(self, texto):
        self.mensagens.append(texto)


class _Espiao:
    recursos = []

    def limpar(self):
        pass


class _Ferramenta(QObject):
    """O mínimo de que `_capturar` precisa, sem navegador."""

    _capturar = tela.ConstatacaoTool._capturar
    _remover = tela.ConstatacaoTool._remover

    def __init__(self, pasta):
        super().__init__()
        self._capturando = False
        self._btn_capturar = _Botao()
        self.status_msg = _Sinal()
        self._pagina = _Pagina()
        self._view = _Janela()
        self._espiao = _Espiao()
        self._sessao = cc.Sessao()
        self._pasta = Path(pasta)
        self.linha = -1

    def _preencher_lista(self):
        pass

    @property
    def _lista(self):
        return self

    def currentRow(self):
        return self.linha


def _temporizadores(obj):
    from PyQt6.QtCore import QTimer
    return obj.findChildren(QTimer)


class _ComFerramenta(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self._originais = (tela.WEBVIEW_DISPONIVEL, cc.resolver,
                           cc.certificado_tls, cc.registro_do_dominio)
        tela.WEBVIEW_DISPONIVEL = True
        cc.resolver = lambda host: ["203.0.113.7"]
        cc.certificado_tls = lambda host, *a, **k: cc.Certificado()
        cc.registro_do_dominio = lambda host: (cc.Registro(), b"")
        self.addCleanup(self._restaurar)
        self.f = _Ferramenta(self._dir.name)

    def _restaurar(self):
        (tela.WEBVIEW_DISPONIVEL, cc.resolver,
         cc.certificado_tls, cc.registro_do_dominio) = self._originais

    def capturar(self, entregar=True):
        self.f._capturar()
        if entregar:
            self.f._pagina.ao_pdf(b"%PDF-1.7 conteudo")
            self.f._pagina.ao_html("<html>conteudo</html>")


class ACapturaConcluiUmaVez(_ComFerramenta):

    def test_o_fim_do_prazo_nao_conclui_de_novo(self):
        self.capturar()
        self.assertEqual(len(self.f._sessao.capturas), 1)
        captura = self.f._sessao.capturas[0]
        resumo = captura.resumo
        imagem = Path(self._dir.name) / "01" / "tela.png"

        # Vinte segundos depois a janela mostra outra página.
        self.f._view.mostrando = b"pagina B"
        for t in _temporizadores(self.f):
            self.assertFalse(t.isActive(),
                             "o prazo tem de ser desarmado ao concluir")
            t.timeout.emit()

        self.assertEqual(len(self.f._sessao.capturas), 1)
        self.assertEqual(imagem.read_bytes(), b"pagina A")
        self.assertEqual(captura.resumo, resumo)
        self.assertEqual([p.nome for p in captura.pecas].count("tela.png"), 1)

    def test_a_imagem_e_do_instante_do_clique(self):
        self.capturar(entregar=False)
        self.f._view.mostrando = b"pagina B"      # o operador navegou
        self.f._pagina.ao_pdf(b"%PDF-1.7")
        self.f._pagina.ao_html("<html/>")
        imagem = Path(self._dir.name) / "01" / "tela.png"
        self.assertEqual(imagem.read_bytes(), b"pagina A")

    def test_o_resumo_da_imagem_confere_com_o_arquivo(self):
        self.capturar()
        peca = next(p for p in self.f._sessao.capturas[0].pecas
                    if p.nome == "tela.png")
        em_disco = hashlib.sha256(Path(peca.caminho).read_bytes()).hexdigest()
        self.assertEqual(peca.sha256, em_disco)

    def test_peca_que_nao_chega_no_prazo_vai_declarada_no_termo(self):
        self.capturar(entregar=False)
        self.f._pagina.ao_html("<html/>")
        self.assertEqual(self.f._sessao.capturas, [])
        for t in _temporizadores(self.f):
            t.timeout.emit()
        self.assertEqual(len(self.f._sessao.capturas), 1)
        captura = self.f._sessao.capturas[0]
        self.assertEqual(captura.ausentes, ["pagina.pdf"])
        self.assertIn("pagina.pdf", cc.build_html(self.f._sessao))
        self.assertIn("Peça não obtida", cc.build_html(self.f._sessao))

    def test_peca_atrasada_nao_e_gravada_depois_de_concluir(self):
        self.capturar(entregar=False)
        self.f._pagina.ao_html("<html/>")
        for t in _temporizadores(self.f):
            t.timeout.emit()
        self.f._pagina.ao_pdf(b"%PDF-1.7 atrasado")
        self.assertFalse((Path(self._dir.name) / "01" / "pagina.pdf").exists())
        self.assertEqual(len(self.f._sessao.capturas), 1)


class APastaDaCapturaNaoEReaproveitada(_ComFerramenta):

    def test_remover_e_capturar_de_novo_nao_grava_sobre_outra(self):
        self.capturar()
        self.capturar()
        segunda = self.f._sessao.capturas[1]
        antes = {p.nome: p.sha256 for p in segunda.pecas}

        self.f.linha = 0
        self.f._remover()
        self.f._view.mostrando = b"pagina C"
        self.capturar()

        self.assertTrue((Path(self._dir.name) / "03").is_dir())
        for p in segunda.pecas:
            em_disco = hashlib.sha256(
                Path(p.caminho).read_bytes()).hexdigest()
            self.assertEqual(em_disco, antes[p.nome], p.nome)

    def test_o_numero_so_cresce(self):
        s = cc.Sessao()
        self.assertEqual([s.proximo_numero() for _ in range(3)], [1, 2, 3])
        s.capturas.clear()
        self.assertEqual(s.proximo_numero(), 4)


class OCertificadoEODaPortaDaPagina(_ComFerramenta):

    def com_endereco(self, endereco):
        portas = []
        cc.certificado_tls = lambda host, porta=443: (
            portas.append(porta), cc.Certificado())[1]
        self.f._pagina.url = lambda: QUrl(endereco)
        self.capturar()
        return portas, self.f._sessao.capturas[-1]

    def test_pagina_em_outra_porta_tem_o_certificado_dessa_porta(self):
        portas, _ = self.com_endereco("https://exemplo.gov.br:8443/x")
        self.assertEqual(portas, [8443])

    def test_https_comum_segue_na_443(self):
        portas, _ = self.com_endereco("https://exemplo.gov.br/x")
        self.assertEqual(portas, [443])

    def test_pagina_sem_tls_nao_recebe_certificado_alheio(self):
        portas, captura = self.com_endereco("http://exemplo.gov.br/x")
        self.assertEqual(portas, [])
        self.assertIn("sem TLS", captura.certificado.erro)


class APaginaEmBrancoNaoECaptura(_ComFerramenta):

    def test_sem_endereco_da_rede_nada_e_capturado(self):
        self.f._pagina.url = lambda: QUrl("about:blank")
        self.f._capturar()
        self.assertEqual(self.f._sessao.capturas, [])
        self.assertFalse(self.f._capturando)


class AConclusao(unittest.TestCase):

    def test_conclui_quando_tudo_chega_e_so_uma_vez(self):
        vezes = []
        c = cc.Conclusao(("a", "b"), vezes.append)
        self.assertTrue(c.chegou("a"))
        self.assertEqual(vezes, [])
        self.assertTrue(c.chegou("b"))
        c.forcar()
        self.assertFalse(c.chegou("a"))
        self.assertEqual(vezes, [[]])

    def test_forcar_informa_o_que_faltou(self):
        vezes = []
        c = cc.Conclusao(("a", "b"), vezes.append)
        c.chegou("b")
        c.forcar()
        self.assertEqual(vezes, [["a"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
