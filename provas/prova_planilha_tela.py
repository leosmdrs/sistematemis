"""Provas da tela da Análise de Planilha.

Uma operação atravessa três lugares: a classe no núcleo, o registro
`TIPOS` e a página do diálogo. Esquecer qualquer um dos três produz a
mesma falha silenciosa — a operação existe, o roteiro grava, e na volta
ela não está mais lá, ou volta diferente do que era. O termo continua
relacionando o passo, e passa a afirmar o que não foi feito.

Estas provas percorrem os três lugares. Rodam sem tela, pelo motor
offscreen do Qt, e por isso servem também onde não há monitor.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication              # noqa: E402

from temis.tools import planilha_core as pc           # noqa: E402
from temis.tools.planilha import DialogoOperacao      # noqa: E402

COLUNAS = ["Nome", "Sobrenome", "UF", "Valor", "Início", "Fim"]

#: Uma de cada família, com os campos fora do padrão de fábrica — valor
#: igual ao padrão passaria mesmo que a tela não lesse coisa alguma.
EXEMPLOS = [
    pc.Filtro(coluna="UF", condicao="igual", valor="SP", sensivel=True,
              manter=False),
    pc.Ordenacao(chaves=[("Valor", True)]),
    pc.Colunas(manter=["UF", "Nome"]),
    pc.Duplicidades(chaves=["Nome", "UF"], manter="ultima"),
    pc.Derivada(nome="Completo", calculo="juntar",
                origens=["Nome", "Sobrenome"], separador=" - "),
    pc.Derivada(nome="Raiz", calculo="extrair", origens=["Valor"],
                inicio=2, tamanho=3),
    pc.Derivada(nome="Dias", calculo="dias", origens=["Início", "Fim"]),
    pc.Agrupamento(chaves=["UF"],
                   resumos=[("contar", ""), ("somar", "Valor")]),
    pc.Marcacao(coluna_marca="Achado", marca="ALTO",
                justificativa="acima do teto", coluna="Valor",
                condicao="maior", valor="1000"),
]


class Diálogo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def novo(self, operacao=None):
        return DialogoOperacao(COLUNAS, operacao=operacao)

    def test_toda_familia_tem_a_sua_pagina(self):
        d = self.novo()
        self.assertEqual(len(d.FAMILIAS), d._paginas.count())

    def test_familia_e_nucleo_falam_do_mesmo_conjunto(self):
        # Nos dois sentidos: operação no núcleo sem página fica
        # inalcançável; página sem operação no núcleo grava lixo.
        d = self.novo()
        da_tela = {chave for _, chave in d.FAMILIAS}
        self.assertEqual(da_tela, set(pc.TIPOS))

    def test_a_operacao_volta_do_dialogo_igual_ao_que_entrou(self):
        for op in EXEMPLOS:
            with self.subTest(op.tipo + "/" + getattr(op, "calculo", "")):
                d = self.novo(op)
                volta = d.operacao()
                self.assertIsNotNone(volta, "o diálogo não devolveu operação")
                self.assertEqual(volta.dados(), op.dados())

    def test_abrir_uma_operacao_seleciona_a_pagina_dela(self):
        indices = {chave: i for i, (_, chave) in
                   enumerate(DialogoOperacao.FAMILIAS)}
        for op in EXEMPLOS:
            with self.subTest(op.tipo):
                d = self.novo(op)
                self.assertEqual(d._paginas.currentIndex(), indices[op.tipo])

    def test_a_descricao_sobrevive_a_ida_e_volta(self):
        # A frase é o que a peça imprime: se ela muda na volta, o termo
        # deixa de descrever a operação que está gravada.
        for op in EXEMPLOS:
            with self.subTest(op.tipo):
                self.assertEqual(self.novo(op).operacao().descrever(),
                                 op.descrever())


class RecusaOQueEstaIncompleto(unittest.TestCase):
    """Operação pela metade não pode virar passo do roteiro."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def montar(self, familia):
        d = DialogoOperacao(COLUNAS)
        i = {chave: n for n, (_, chave) in enumerate(d.FAMILIAS)}[familia]
        d._familia.setCurrentIndex(i)
        d._paginas.setCurrentIndex(i)
        return d

    def test_coluna_derivada_sem_nome(self):
        d = self.montar("derivada")
        d._r_titulo.setText("   ")
        self.assertIsNone(d.operacao())

    def test_coluna_derivada_sem_origem_marcada(self):
        d = self.montar("derivada")
        d._r_titulo.setText("Nova")
        self.assertIsNone(d.operacao())

    def test_agrupamento_sem_coluna_de_grupo(self):
        self.assertIsNone(self.montar("agrupamento").operacao())

    def test_marcacao_sem_marca(self):
        d = self.montar("marcacao")
        d._m_marca.setText("")
        self.assertIsNone(d.operacao())


if __name__ == "__main__":
    unittest.main(verbosity=2)
