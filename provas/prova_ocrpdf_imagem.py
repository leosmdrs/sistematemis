"""Provas da conversão de imagem em PDF, no PDF Pesquisável.

De um PDF, a ferramenta preserva a imagem de cada página byte a byte. De
um arquivo de imagem ela faz um documento novo — e fazia mal, sob um
termo que afirmava "preservada exatamente": a foto com orientação no
EXIF saía deitada, o PNG transparente saía como página preta, a imagem
de 16 bits saía toda branca, e os metadados sumiam sem menção.

Não usa o reconhecimento óptico do Windows: confere a conversão e o que
a peça afirma sobre ela.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image                                  # noqa: E402
from PyQt6.QtWidgets import QApplication               # noqa: E402

_app = QApplication.instance() or QApplication([])

from temis.tools import ocrpdf_core as oc              # noqa: E402


class Base(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.pasta = Path(self._dir.name)

    def pagina(self, caminho, adaptacoes=None):
        doc = oc._abrir_como_pdf(Path(caminho), adaptacoes)
        pix = doc[0].get_pixmap()
        doc.close()
        return pix


class AImagemSaiComoEVista(Base):

    def test_png_transparente_nao_vira_pagina_preta(self):
        alvo = self.pasta / "transparente.png"
        Image.new("RGBA", (60, 40), (0, 0, 0, 0)).save(alvo)
        feito = []
        pix = self.pagina(alvo, feito)
        self.assertEqual(pix.pixel(pix.width // 2, pix.height // 2),
                         (255, 255, 255))
        self.assertTrue(any("transparentes" in f for f in feito))

    def test_a_orientacao_do_exif_e_aplicada(self):
        alvo = self.pasta / "deitada.jpg"
        imagem = Image.new("RGB", (80, 40), (200, 200, 200))
        exif = imagem.getexif()
        exif[0x0112] = 6                     # girar 90° para exibir
        imagem.save(alvo, exif=exif)
        feito = []
        pix = self.pagina(alvo, feito)
        # Era 80 de largura por 40 de altura; exibida, fica em pé.
        self.assertEqual(pix.height, 2 * pix.width)
        self.assertTrue(any("orientação" in f for f in feito))

    def test_imagem_de_16_bits_nao_sai_toda_branca(self):
        alvo = self.pasta / "dezesseis.png"
        # Quatro faixas verticais, do preto ao branco de 16 bits.
        niveis = [0, 20000, 40000, 65535]
        imagem = Image.new("I;16", (160, 40))
        imagem.putdata([niveis[x // 40] for _y in range(40)
                        for x in range(160)])
        imagem.save(alvo)
        feito = []
        pix = self.pagina(alvo, feito)
        tons = [pix.pixel(int(pix.width * (i + 0.5) / 4), pix.height // 2)[0]
                for i in range(4)]
        self.assertEqual(tons, sorted(tons))
        self.assertEqual(len(set(tons)), 4, "os tons foram cortados em 255")
        self.assertTrue(any("8 bits" in f for f in feito))

    def test_imagem_comum_nao_recebe_adaptacao(self):
        alvo = self.pasta / "comum.png"
        Image.new("RGB", (20, 20), (10, 120, 200)).save(alvo)
        feito = []
        pix = self.pagina(alvo, feito)
        self.assertEqual(pix.pixel(pix.width // 2, pix.height // 2),
                         (10, 120, 200))
        self.assertEqual(feito, [])


class OTermoNaoAfirmaIdentidadeDoQueFoiConvertido(Base):

    def termo(self, *documentos):
        return oc.TermoOCR(documentos=list(documentos))

    def test_entrada_em_imagem_e_dita_como_derivada(self):
        d = oc.Documento(entrada="foto.jpg", saida="foto.pdf",
                         adaptacoes=["a orientação indicada nos metadados "
                                     "da imagem foi aplicada"])
        texto = " ".join(oc.ressalvas_do(self.termo(d)))
        self.assertIn("derivado", texto)
        self.assertIn("foto.jpg", texto)
        self.assertIn("orientação", texto)
        self.assertIn("localização", texto)
        self.assertNotIn("preservada exatamente", texto)

    def test_entrada_em_pdf_mantem_a_afirmacao_que_e_verdadeira(self):
        d = oc.Documento(entrada="autos.pdf", saida="autos-ocr.pdf")
        texto = " ".join(oc.ressalvas_do(self.termo(d)))
        self.assertIn("preservada exatamente", texto)
        self.assertNotIn("derivado", texto)

    def test_lote_misto_diz_as_duas_coisas(self):
        texto = " ".join(oc.ressalvas_do(self.termo(
            oc.Documento(entrada="autos.pdf", saida="a.pdf"),
            oc.Documento(entrada="foto.png", saida="b.pdf"))))
        self.assertIn("recebidos em PDF", texto)
        self.assertIn("foto.png", texto)

    def test_a_camada_nao_e_dita_atras_da_imagem(self):
        d = oc.Documento(entrada="autos.pdf", saida="a.pdf")
        html = oc.build_html(self.termo(d))
        self.assertNotIn("atrás da imagem", html)
        self.assertIn("sobreposto à imagem", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
