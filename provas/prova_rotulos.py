"""Provas de que dado de terceiro não é lido como marcação na tela.

O título de uma página sob constatação, e o título, o canal e a descrição
de um vídeo, são escritos por quem publicou. O rótulo do Qt, deixado no
automático, decide sozinho se o texto é marcação: um título
`<img src="arquivo">` fazia a estação ler o arquivo apontado, e um
`<h1>…</h1>` compunha na tela da ferramenta um aviso que não era dela.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt                            # noqa: E402
from PyQt6.QtGui import QImage                         # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel       # noqa: E402

from temis import widgets                              # noqa: E402
from temis.tools import videoweb as tela               # noqa: E402

_app = QApplication.instance() or QApplication([])


class ORotuloSecundarioETextoSimples(unittest.TestCase):

    def test_marcacao_no_texto_nao_e_interpretada(self):
        rotulo = widgets.subtext("—", wrap=True)
        rotulo.setText("<b>Sessão expirada</b>")
        self.assertEqual(rotulo.textFormat(), Qt.TextFormat.PlainText)

    def test_imagem_referida_no_titulo_nao_e_carregada(self):
        # A mesma medida da constatação original: se o rótulo lê o
        # arquivo, cresce até as dimensões da imagem.
        with tempfile.TemporaryDirectory() as pasta:
            imagem = Path(pasta) / "local.png"
            QImage(400, 300, QImage.Format.Format_RGB32).save(str(imagem))
            titulo = f'<img src="{imagem.as_posix()}">'

            automatico = QLabel()
            automatico.setText(titulo)
            self.assertGreaterEqual(automatico.sizeHint().width(), 400,
                                    "a prova não reproduz o defeito")

            rotulo = widgets.subtext("—")
            rotulo.setText(titulo)
            self.assertLess(rotulo.sizeHint().height(), 100)

    def test_quem_precisa_de_marcacao_pede(self):
        rotulo = widgets.subtext("", formatado=True)
        self.assertEqual(rotulo.textFormat(), Qt.TextFormat.RichText)


class OVideoDaInternetNaoInterpretaOQueVemDaPlataforma(unittest.TestCase):

    MARCA = '<img src="x.png"><h1>aviso</h1>'

    def setUp(self):
        self.f = tela.VideoWebTool() if hasattr(tela, "VideoWebTool") \
            else self._ferramenta()
        self.addCleanup(self.f.deleteLater)
        self.f._mostrar(SimpleNamespace(
            titulo=self.MARCA, canal=self.MARCA, descricao=self.MARCA,
            publicado_em=self.MARCA, extrator=self.MARCA,
            licenca=self.MARCA, disponibilidade=self.MARCA,
            publica=False, duracao=10, restricao_idade=self.MARCA))

    def _ferramenta(self):
        from temis.tools.base import ToolPage
        classe = next(v for v in vars(tela).values()
                      if isinstance(v, type) and issubclass(v, ToolPage)
                      and v is not ToolPage)
        return classe()

    def test_titulo_e_descricao_sao_texto_simples(self):
        for rotulo in (self.f._lbl_titulo, self.f._lbl_descricao):
            self.assertEqual(rotulo.textFormat(), Qt.TextFormat.PlainText)
            self.assertEqual(rotulo.text(), self.MARCA)

    def test_os_dados_entram_escapados_no_rotulo_formatado(self):
        dados = self.f._lbl_dados.text()
        self.assertNotIn("<img", dados)
        self.assertNotIn("<h1>", dados)
        self.assertIn("&lt;img", dados)
        self.assertIn("<b>Canal:</b>", dados)


if __name__ == "__main__":
    unittest.main(verbosity=2)
