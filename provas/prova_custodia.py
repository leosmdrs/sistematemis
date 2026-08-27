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


class AHoraVaiQualificada(unittest.TestCase):
    """Instante afirmado sem qualificação é afirmação sem lastro."""

    def test_o_carimbo_traz_data_hora_e_fuso(self):
        from temis import relogio
        carimbo = relogio.carimbo()
        self.assertRegex(carimbo, r"\d{2}/\d{2}/\d{4} às \d{2}:\d{2}:\d{2} "
                                  r"\(UTC[+-]\d{2}:\d{2}\)")

    def test_o_fuso_usa_hifen_comum_e_nao_o_sinal_tipografico(self):
        # O texto da peça é copiado para o SEI, e o U+2212 não sobrevive
        # a toda codificação pelo caminho.
        from temis import relogio
        self.assertNotIn("−", relogio.carimbo())

    def test_o_instante_sabe_o_proprio_fuso(self):
        from temis import relogio
        self.assertIsNotNone(relogio.agora().tzinfo)

    def test_a_ressalva_diz_de_onde_vem_a_hora_e_o_que_nao_promete(self):
        from temis import relogio
        texto = relogio.ressalva()
        self.assertIn("relógio desta estação", texto)
        self.assertIn(relogio.deslocamento(), texto)
        self.assertIn("não constitui carimbo de tempo certificado", texto)

    def test_nao_apurado_nao_e_nao_sincronizado(self):
        # Dizer "não sincronizado" sem ter apurado seria a peça afirmando
        # defeito que não constatou.
        from temis import relogio
        for valor, esperado in ((True, "sincronizado"),
                                (False, "NÃO SINCRONIZADO"),
                                (None, "Não foi possível apurar")):
            with self.subTest(valor):
                guardado = list(relogio._ESTADO)
                relogio._ESTADO.clear()
                relogio._ESTADO.append({"sincronizado": valor, "fonte": "",
                                        "tipo": "", "servidor": ""})
                try:
                    self.assertIn(esperado, relogio.ressalva())
                finally:
                    relogio._ESTADO.clear()
                    relogio._ESTADO.extend(guardado)

    def test_toda_peca_leva_a_qualificacao_da_hora(self):
        from temis.impressao import rodape_texto
        self.assertIn("relógio desta estação", rodape_texto())

    def test_a_derivacao_carimba_quando_os_resumos_foram_tomados(self):
        import tempfile
        from temis.tools import derivado_core as dc
        with tempfile.TemporaryDirectory() as pasta:
            a, b = Path(pasta) / "a", Path(pasta) / "b"
            a.write_bytes(b"origem")
            b.write_bytes(b"saida")
            item = dc.medir(a, b)
        self.assertRegex(item.medido_em, r"\(UTC[+-]\d{2}:\d{2}\)")


class OMeioDeEntradaSeRegistra(unittest.TestCase):
    """A falta de indicação do meio de entrega é falha arrolada nos julgados."""

    def test_sem_nada_informado_a_frase_nao_existe(self):
        # Rótulo genérico preenchido para cumprir formulário é pior do
        # que silêncio: afirma percurso que ninguém apurou.
        j = mc.Juntada()
        self.assertFalse(j.houve_recebimento)
        self.assertEqual(j.frase_recebimento(), "")

    def test_monta_se_do_que_houver(self):
        so_meio = mc.Juntada(meio_entrega="ofício nº 45/2026")
        self.assertIn("por ofício nº 45/2026", so_meio.frase_recebimento())
        self.assertNotIn(" de ,", so_meio.frase_recebimento())
        completo = mc.Juntada(recebido_de="Setor X", meio_entrega="ofício",
                              recebido_em="26/08/2026")
        frase = completo.frase_recebimento()
        for pedaco in ("de Setor X", "por ofício", "em 26/08/2026"):
            with self.subTest(pedaco):
                self.assertIn(pedaco, frase)

    def test_a_frase_nao_promete_responder_pelo_que_antecede_a_entrega(self):
        j = mc.Juntada(meio_entrega="ofício")
        self.assertIn("a partir da leitura", j.frase_recebimento())
        self.assertIn("declarado por quem a promoveu", j.frase_recebimento())


if __name__ == "__main__":
    unittest.main(verbosity=2)
