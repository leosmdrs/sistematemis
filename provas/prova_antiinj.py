"""Provas do Anti-Injection: o relatório é do documento analisado.

O relatório de constatação afirma, quando não há achados, que não foram
identificados trechos ocultos. Essa frase só pode sair sobre um documento
que a ferramenta leu até o fim. Saía sobre outros: aberto um segundo
arquivo depois de uma análise bem-sucedida, o botão continuava ligado, e
se a análise do segundo falhasse — o caso natural é o PDF protegido por
senha — o relatório levava o nome dele e a conclusão de que nada havia.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz                                            # noqa: E402
from PyQt6.QtWidgets import (QApplication, QFileDialog,  # noqa: E402
                             QMessageBox)

from temis.tools import antiinj as tela                # noqa: E402

_app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.avisos = []
        self.relatorios = []
        self._trocar(QMessageBox, "critical",
                     staticmethod(lambda *a, **k: self.avisos.append(a[2])))
        self._trocar(QMessageBox, "warning",
                     staticmethod(lambda *a, **k: self.avisos.append(a[2])))
        prova = self

        class _Relatorio:
            def __init__(self, nome, paginas, achados, quando, pai):
                prova.relatorios.append((nome, list(achados)))

            def exec(self):
                return 0

        self._trocar(tela, "ReportDialog", _Relatorio)
        self.f = tela.AntiInjectionTool() if hasattr(
            tela, "AntiInjectionTool") else self._ferramenta()
        self.addCleanup(self.f.deleteLater)

    def _ferramenta(self):
        from temis.tools.base import ToolPage
        classe = next(v for v in vars(tela).values()
                      if isinstance(v, type) and issubclass(v, ToolPage)
                      and v is not ToolPage)
        return classe()

    def _trocar(self, alvo, nome, valor):
        original = alvo.__dict__.get(nome, getattr(alvo, nome))
        setattr(alvo, nome, valor)
        self.addCleanup(setattr, alvo, nome, original)

    def pdf(self, nome, senha=None):
        doc = fitz.open()
        doc.new_page().insert_text((72, 100), "Texto comum do documento.")
        alvo = str(Path(self._dir.name) / nome)
        if senha:
            doc.save(alvo, encryption=fitz.PDF_ENCRYPT_AES_256,
                     user_pw=senha, owner_pw=senha)
        else:
            doc.save(alvo)
        doc.close()
        return alvo

    def abrir(self, caminho, esperar=True):
        self._trocar(QFileDialog, "getOpenFileName",
                     staticmethod(lambda *a, **k: (caminho, "")))
        self.f._open_file()
        if esperar:
            self.esperar()

    def esperar(self):
        fio = getattr(self.f, "_thread", None)
        if fio is not None:
            fio.wait(10000)
        for _ in range(5):
            _app.processEvents()


class ORelatorioEDoDocumentoAnalisado(Base):

    def test_analise_bem_sucedida_libera_o_relatorio(self):
        self.abrir(self.pdf("a.pdf"))
        self.assertTrue(self.f._btn_report.isEnabled())
        self.f._show_report()
        self.assertEqual(self.relatorios[0][0], "a.pdf")

    def test_pdf_com_senha_nao_recebe_relatorio(self):
        self.abrir(self.pdf("a.pdf"))
        self.abrir(self.pdf("cifrado.pdf", senha="s3nh4"))
        self.assertFalse(self.f._btn_report.isEnabled())
        self.f._show_report()
        self.assertEqual(self.relatorios, [])
        self.assertTrue(any("senha" in a for a in self.avisos))
        self.assertIn("não foi analisado", self.f._lbl_breakdown.text())

    def test_falha_na_analise_desliga_o_relatorio(self):
        self.abrir(self.pdf("a.pdf"))

        class _Falha(tela.AnalyzeThread):
            def run(self):
                self.failed.emit("erro simulado")

        self._trocar(tela, "AnalyzeThread", _Falha)
        self.abrir(self.pdf("b.pdf"))
        self.assertFalse(self.f._btn_report.isEnabled())
        self.f._show_report()
        self.assertEqual(self.relatorios, [])
        self.assertIn("falhou", self.f._lbl_breakdown.text())

    def test_durante_a_analise_nao_ha_relatorio(self):
        self.abrir(self.pdf("a.pdf"))

        class _Lenta(tela.AnalyzeThread):
            def run(self):
                pass                       # nunca conclui

        self._trocar(tela, "AnalyzeThread", _Lenta)
        self.abrir(self.pdf("b.pdf"))
        self.assertFalse(self.f._btn_report.isEnabled())
        self.f._show_report()
        self.assertEqual(self.relatorios, [])

    def test_arquivo_que_nao_abre_nao_herda_o_relatorio_do_anterior(self):
        self.abrir(self.pdf("a.pdf"))
        ruim = Path(self._dir.name) / "ruim.pdf"
        ruim.write_bytes(b"isto nao e um pdf")
        self.abrir(str(ruim))
        self.assertFalse(self.f._btn_report.isEnabled())
        self.f._show_report()
        self.assertEqual(self.relatorios, [])


class AConclusaoNegativaDizOProprioAlcance(unittest.TestCase):
    """Sem achados, a peça diz o que examinou — e o que não alcança.

    A conclusão "não foram identificados trechos ocultos" era lida como
    atestado de que não há. O que a ferramenta constata é menos: que
    seis verificações não acharam. Há técnicas conhecidas que elas não
    alcançam, e a peça não as nomeava.
    """

    def pecas(self):
        from temis.tools import antiinj_core as core
        html = core.build_html("doc.pdf", 3, [], "23/11/2026 às 10:00")
        texto = core.build_report("doc.pdf", 3, [], "23/11/2026 às 10:00")
        return html, texto

    def test_a_conclusao_nao_afirma_ausencia(self):
        for peca in self.pecas():
            self.assertNotIn("Não foram identificados", peca)
            self.assertIn("não detectaram", peca)
            self.assertIn("não equivale a atestado", peca)

    def test_o_que_nao_e_alcancado_vai_nomeado(self):
        for peca in self.pecas():
            for tecnica in ("área de corte", "retângulo opaco",
                            "fundo que não seja branco", "como imagem"):
                self.assertIn(tecnica, peca)


if __name__ == "__main__":
    unittest.main(verbosity=2)
