"""Provas do que sustenta a cadeia de custódia nas peças.

Duas coisas, pelo mesmo motivo. O Superior Tribunal de Justiça deixou de
presumir a idoneidade da prova digital pela fé pública de quem a colheu:
confiabilidade e integridade passaram a ser matéria de demonstração, e o
ônus é de quem produziu a prova.

Disso decorrem as duas exigências provadas aqui. A peça precisa dizer
**com o quê** foi produzida, sem o que o método não se reexecuta nem se
contesta. E o sistema precisa saber **conferir** resumo, e não apenas
gerá-lo — resumo gerado sem par a confrontar prova que o arquivo não
mudou de agora em diante, e nada sobre o que se recebeu.
"""

import os
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication              # noqa: E402

from temis import __version__, procedencia            # noqa: E402
from temis.tools import metadados_core as mc          # noqa: E402


def sem_marcacao(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


class ToraPecaDizComOQueFoiProduzida(unittest.TestCase):

    def test_a_frase_sai_com_nenhum_um_ou_varios_motores(self):
        # Com um motor só, a montagem por fatia já deixou um "com ."
        # solto na peça.
        for quantos in (0, 1, 2, 3):
            chaves = ("pdf", "imagem", "planilha")[:quantos]
            with self.subTest(quantos=quantos):
                frase = procedencia.frase(procedencia.motores(*chaves))
                self.assertIn(__version__, frase)
                self.assertNotIn("com .", frase)
                self.assertTrue(frase.endswith("por terceiro."))

    def test_motor_que_nao_existe_nao_entra_na_peca(self):
        # Declarar dependência que não houve é afirmação falsa, e numa
        # peça de custódia é a mais cara de todas.
        self.assertEqual(procedencia.motores("inexistente"), [])

    def test_toda_peca_do_sistema_chama_o_rodape(self):
        # O mesmo que o autoteste confere, aqui dentro da suíte: assim a
        # falha aparece a quem alterar o código, e não só a quem instalar.
        import ast
        faltando = []
        for arquivo in sorted((RAIZ / "temis" / "tools").glob("*_core.py")):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in arvore.body:
                if (isinstance(no, ast.FunctionDef)
                        and no.name in ("build_html", "relatorio_html")
                        and not any(isinstance(x, ast.Name)
                                    and x.id == "rodape_html"
                                    for x in ast.walk(no))):
                    faltando.append(f"{arquivo.name}:{no.name}")
        self.assertEqual(faltando, [])

    def test_a_versao_sai_impressa_na_peca(self):
        QApplication.instance() or QApplication([])
        from temis.tools import derivado_core as dc
        termo = dc.TermoDerivado(nome="Fulano", motores=("pdf",))
        for forma in (dc.build_html(termo), dc.build_texto(termo)):
            with self.subTest(forma[:20]):
                self.assertIn(__version__, sem_marcacao(forma))


class OResumoDeclaradoSeConfronta(unittest.TestCase):

    def test_normaliza_o_que_se_cola_de_qualquer_lugar(self):
        alvo = "a" * 64
        for forma in (alvo.upper(),
                      " ".join(alvo[i:i + 8] for i in range(0, 64, 8)),
                      ":".join(alvo[i:i + 2] for i in range(0, 64, 2)),
                      alvo + "  arquivo.pdf",
                      alvo[:32] + "\n" + alvo[32:]):
            with self.subTest(forma[:24]):
                self.assertEqual(mc.normalizar_resumo(forma), alvo)

    def test_reconhece_a_forma_de_um_sha256(self):
        self.assertTrue(mc.resumo_valido("A" * 64))
        self.assertFalse(mc.resumo_valido("a" * 63))
        self.assertFalse(mc.resumo_valido(""))

    def test_confere_diverge_e_nao_perguntado_sao_tres_coisas(self):
        # None não é "não confere". Confundir os dois faria a peça
        # declarar divergência onde houve ausência de referência, que é
        # afirmação grave e falsa.
        igual = mc.Arquivo(caminho="a.pdf", sha256="a" * 64,
                           declarado=("A" * 64))
        outro = mc.Arquivo(caminho="b.pdf", sha256="a" * 64,
                           declarado="b" * 64)
        mudo = mc.Arquivo(caminho="c.pdf", sha256="a" * 64)
        ilegivel = mc.Arquivo(caminho="d.pdf", declarado="a" * 64)
        self.assertIs(igual.confere, True)
        self.assertIs(outro.confere, False)
        self.assertIsNone(mudo.confere)
        self.assertIsNone(ilegivel.confere, "sem resumo calculado não confere")


class APecaDeclaraAConferencia(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def peca(self, arquivos):
        return sem_marcacao(mc.build_html(
            arquivos, "27/08/2026", mc.Declarante(nome="Fulano"),
            mc.SO_HASH, mc.Juntada(numero_processo="123")))

    def test_sem_resumo_declarado_a_peca_nao_fala_em_conferencia(self):
        texto = self.peca([mc.Arquivo(caminho="a.pdf", sha256="a" * 64)])
        self.assertNotIn("Conferência de Integridade", texto)
        self.assertNotIn("Alcance da conferência", texto)

    def test_com_resumo_declarado_o_titulo_e_o_alcance_aparecem(self):
        texto = self.peca([mc.Arquivo(caminho="a.pdf", sha256="a" * 64,
                                      declarado="a" * 64)])
        self.assertIn("Conferência de Integridade", texto)
        self.assertIn("Alcance da conferência", texto)
        self.assertIn("CONFERE", texto)

    def test_a_divergencia_e_nomeada_e_contada(self):
        texto = self.peca([
            mc.Arquivo(caminho="bate.pdf", sha256="a" * 64, declarado="a" * 64),
            mc.Arquivo(caminho="nao.pdf", sha256="b" * 64, declarado="c" * 64)])
        self.assertIn("1 conferiram", texto)
        self.assertIn("1 divergiram", texto)
        self.assertIn("nao.pdf", texto)

    def test_a_peca_nao_promete_mais_do_que_a_conferencia_dá(self):
        # O alcance é o que impede que se atribua à conferência prova da
        # procedência do arquivo, que ela não dá.
        texto = self.peca([mc.Arquivo(caminho="a.pdf", sha256="a" * 64,
                                      declarado="a" * 64)])
        self.assertIn("Nada se afirma", texto)
        self.assertIn("recebido de terceiro", texto)

    def test_arquivo_sem_declaracao_aparece_como_nao_declarado(self):
        texto = self.peca([
            mc.Arquivo(caminho="a.pdf", sha256="a" * 64, declarado="a" * 64),
            mc.Arquivo(caminho="b.pdf", sha256="b" * 64)])
        self.assertIn("não declarado", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
