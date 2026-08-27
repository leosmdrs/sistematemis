"""Prova do seletor de procedimento com \"Outro\".

Nem toda diligência instrui um IPS ou um PAD. O seletor passou a aceitar
um tipo livre, e estas provas garantem que ele oferece "Outro", abre a
digitação quando escolhido, e que a leitura devolve o que se digitou —
sem o rótulo — e volta a fechar ao reeleger IPS ou PAD.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication              # noqa: E402

from temis import widgets                             # noqa: E402


class OSeletorDeProcedimento(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def novo(self):
        return widgets.preparar_procedimento(widgets.NoScrollComboBox())

    def test_oferece_ips_pad_e_outro(self):
        c = self.novo()
        itens = [c.itemText(i) for i in range(c.count())]
        self.assertEqual(itens, ["IPS", "PAD", widgets.OUTRO_PROCEDIMENTO])

    def test_padrao_e_ips_e_nao_e_editavel(self):
        c = self.novo()
        self.assertEqual(widgets.ler_procedimento(c), "IPS")
        self.assertFalse(c.isEditable())

    def test_escolher_outro_abre_a_digitacao(self):
        c = self.novo()
        c.setCurrentIndex(2)
        self.assertTrue(c.isEditable())
        c.lineEdit().setText("Sindicância")
        self.assertEqual(widgets.ler_procedimento(c), "Sindicância")

    def test_outro_sem_digitar_nao_devolve_o_rotulo(self):
        # Escolher "Outro" e não digitar não pode gravar "Outro…" como
        # tipo de processo.
        c = self.novo()
        c.setCurrentIndex(2)
        self.assertEqual(widgets.ler_procedimento(c), "")

    def test_voltar_a_ips_fecha_a_digitacao(self):
        c = self.novo()
        c.setCurrentIndex(2)
        c.lineEdit().setText("Outra coisa")
        c.setCurrentIndex(0)
        self.assertFalse(c.isEditable())
        self.assertEqual(widgets.ler_procedimento(c), "IPS")

    def test_todos_os_termos_usam_o_seletor(self):
        # A troca tinha de alcançar as nove ferramentas que emitem termo
        # com procedimento — não só algumas.
        import re
        tools = Path(__file__).resolve().parents[1] / "temis" / "tools"
        esperados = ["constatacao", "metadados", "transcricao", "espelhamento",
                     "extracao", "gravacao", "ocrpdf", "varredura",
                     "derivado_dialogo"]
        for nome in esperados:
            texto = (tools / f"{nome}.py").read_text(encoding="utf-8")
            with self.subTest(nome):
                self.assertIn("preparar_procedimento(self._", texto)
                self.assertIn("ler_procedimento(self._", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
