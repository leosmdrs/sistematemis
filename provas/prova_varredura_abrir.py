"""Provas de como a Varredura abre um arquivo do material examinado.

Material apreendido não é confiável. O duplo clique abria o arquivo
direto na mídia de origem, com o programa que o Windows associasse a
ele — de modo que um atalho ou um roteiro deixado na mídia rodava na
estação de quem examina, e um documento aberto ali ganhava ao lado
arquivo de bloqueio e data de acesso nova.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from temis.tools import varredura as tela              # noqa: E402
from temis.tools import varredura_core as vc           # noqa: E402

_app = QApplication.instance() or QApplication([])


class OQueExecutaNaoEAberto(unittest.TestCase):

    def test_programas_roteiros_atalhos_e_macros_sao_recusados(self):
        for nome in ("a.exe", "a.BAT", "fotos.lnk", "a.ps1", "a.vbs",
                     "a.js", "a.hta", "a.msi", "planilha.xlsm", "a.url",
                     "a.scr", "a.jar", "a.chm", "relatorio.pdf.exe"):
            with self.subTest(nome):
                self.assertTrue(vc.tipo_que_executa(nome))

    def test_documento_imagem_e_video_seguem_abrindo(self):
        for nome in ("a.pdf", "a.docx", "a.jpg", "a.mp4", "a.txt",
                     "a.xlsx", "sem_extensao"):
            with self.subTest(nome):
                self.assertFalse(vc.tipo_que_executa(nome))

    def test_a_copia_tambem_recusa(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "a.cmd"
            origem.write_text("echo", encoding="utf-8")
            with self.assertRaises(vc.AberturaRecusada):
                vc.copia_para_abrir(origem, Path(pasta) / "copias")
            self.assertFalse((Path(pasta) / "copias" / "a.cmd").exists())


class AbreSeACopiaENaoAOrigem(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.midia = Path(self._dir.name) / "midia"
        self.midia.mkdir()
        self.origem = self.midia / "contrato.pdf"
        self.origem.write_bytes(b"%PDF-1.7 conteudo")

    def test_a_copia_e_igual_fica_fora_da_midia_e_nao_se_grava(self):
        copias = Path(self._dir.name) / "copias"
        copia = vc.copia_para_abrir(self.origem, copias)
        self.assertEqual(copia.read_bytes(), self.origem.read_bytes())
        self.assertNotEqual(copia.parent, self.midia)
        self.assertFalse(os.stat(copia).st_mode & 0o222)

    def test_homonimos_nao_se_sobrepoem(self):
        copias = Path(self._dir.name) / "copias"
        um = vc.copia_para_abrir(self.origem, copias)
        dois = vc.copia_para_abrir(self.origem, copias)
        self.assertNotEqual(um, dois)

    def ferramenta(self, alvo, resposta):
        abertos, avisos = [], []
        f = tela.VarreduraTool()
        self.addCleanup(f.deleteLater)
        f._caminho_absoluto = lambda: alvo
        for nome, valor in (
                ("question", staticmethod(lambda *a, **k: resposta)),
                ("warning", staticmethod(
                    lambda *a, **k: avisos.append(a[2])))):
            original = getattr(QMessageBox, nome)
            setattr(QMessageBox, nome, valor)
            self.addCleanup(setattr, QMessageBox, nome, original)
        original = getattr(os, "startfile", None)
        os.startfile = lambda caminho: abertos.append(Path(caminho))
        if original is None:
            self.addCleanup(delattr, os, "startfile")
        else:
            self.addCleanup(setattr, os, "startfile", original)
        return f, abertos, avisos

    def test_o_duplo_clique_abre_a_copia(self):
        f, abertos, _ = self.ferramenta(self.origem,
                                        QMessageBox.StandardButton.Yes)
        f._abrir_arquivo()
        self.assertEqual(len(abertos), 1)
        self.assertNotEqual(abertos[0], self.origem)
        self.assertNotEqual(abertos[0].parent, self.midia)
        self.assertEqual(abertos[0].read_bytes(), self.origem.read_bytes())
        f.shutdown()
        self.assertFalse(abertos[0].exists(), "a cópia ficou no disco")

    def test_sem_confirmar_nada_e_aberto(self):
        f, abertos, _ = self.ferramenta(self.origem,
                                        QMessageBox.StandardButton.No)
        f._abrir_arquivo()
        self.assertEqual(abertos, [])

    def test_tipo_que_executa_nem_pergunta(self):
        atalho = self.midia / "Fotos.lnk"
        atalho.write_bytes(b"L")
        f, abertos, avisos = self.ferramenta(atalho,
                                             QMessageBox.StandardButton.Yes)
        f._abrir_arquivo()
        self.assertEqual(abertos, [])
        self.assertTrue(any("executam" in a for a in avisos))


if __name__ == "__main__":
    unittest.main(verbosity=2)
