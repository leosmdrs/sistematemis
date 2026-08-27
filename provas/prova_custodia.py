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
                self.assertIn("reexecutado e conferido por terceiro", frase)

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


class OProgramaResumeASiMesmo(unittest.TestCase):
    """Declarar a versão diz qual programa; o resumo diz que é aquele."""

    def setUp(self):
        procedencia._RESUMO_PROGRAMA.clear()
        self.addCleanup(procedencia._RESUMO_PROGRAMA.clear)

    def test_do_codigo_fonte_nao_ha_executavel_a_resumir(self):
        # O executável seria o interpretador Python, e resumi-lo não
        # diria nada sobre o Têmis. A peça declara o que é verdade.
        self.assertEqual(procedencia.resumo_do_programa(), "")
        self.assertIn("a partir do código-fonte",
                      procedencia.frase(procedencia.motores()))

    def test_empacotado_resume_o_proprio_executavel(self):
        import sys
        import tempfile
        from temis.tools.hash_core import sha256_file
        with tempfile.TemporaryDirectory() as pasta:
            falso = Path(pasta) / "SistemaTemis.exe"
            falso.write_bytes(b"conteudo do executavel")
            guardado = (getattr(sys, "frozen", None), sys.executable)
            sys.frozen = True
            sys.executable = str(falso)
            try:
                resumo = procedencia.resumo_do_programa()
                frase = procedencia.frase([])
            finally:
                if guardado[0] is None:
                    del sys.frozen
                else:
                    sys.frozen = guardado[0]
                sys.executable = guardado[1]
            self.assertEqual(resumo, sha256_file(str(falso)))
            self.assertIn(resumo, frase)
            self.assertIn("executável que produziu esta peça", frase)


class ORegistroDeAtividadesSeEncadeia(unittest.TestCase):

    def sessao(self, quantas=3):
        from temis.tools import atividades_core as ac
        s = ac.Sessao(identificador="s1", versao=__version__,
                      inicio="2026-08-27T15:00:00-03:00",
                      maquina={"estacao": "Leonardo"})
        s.usos.append(ac.Uso(chave="tarja", nome="Tarja Preta",
                             abriu="2026-08-27T15:00:10-03:00",
                             fechou="2026-08-27T15:04:00-03:00",
                             segundos=230.0))
        elo = ""
        for n in range(1, quantas + 1):
            quando = f"2026-08-27T15:0{n}:00-03:00"
            texto = f"ato {n}"
            elo = ac.elo_de(elo, quando, "tarja", texto)
            s.anotacoes.append(ac.Anotacao(quando=quando, ferramenta="tarja",
                                           texto=texto, elo=elo))
        s.fim = "2026-08-27T15:10:00-03:00"
        s.encerrada = True
        s.elo_final = ac.fecho_de(s)
        return ac, s

    def test_sessao_intacta_confere(self):
        ac, s = self.sessao()
        self.assertEqual(ac.conferir(s), ("integro", ""))

    def test_alterar_uma_linha_rompe_a_corrente_e_aponta_onde(self):
        ac, s = self.sessao()
        s.anotacoes[1].texto = "ato 2, adulterado"
        situacao, explicacao = ac.conferir(s)
        self.assertEqual(situacao, "rompido")
        self.assertIn("anotação 2", explicacao)

    def test_remover_uma_linha_rompe(self):
        ac, s = self.sessao()
        del s.anotacoes[1]
        self.assertEqual(ac.conferir(s)[0], "rompido")

    def test_inserir_uma_linha_rompe(self):
        ac, s = self.sessao()
        s.anotacoes.insert(1, ac.Anotacao(quando="2026-08-27T15:01:30-03:00",
                                          ferramenta="tarja",
                                          texto="ato inventado", elo="x"))
        self.assertEqual(ac.conferir(s)[0], "rompido")

    def test_mover_texto_de_um_campo_para_o_outro_tambem_rompe(self):
        # Sem separador que o conteúdo não consiga imitar, trocar
        # "tarja"+"ato 1" por "tarj"+"aato 1" daria o mesmo resumo.
        ac, s = self.sessao()
        s.anotacoes[0].ferramenta = "tarj"
        s.anotacoes[0].texto = "aato 1"
        self.assertEqual(ac.conferir(s)[0], "rompido")

    def test_mexer_no_que_a_corrente_nao_cobre_o_fecho_pega(self):
        # A corrente é das anotações; o fecho é da sessão inteira. Mudar
        # a duração de uma ferramenta não rompe a primeira, e não pode
        # passar em silêncio.
        ac, s = self.sessao()
        s.usos[0].segundos = 9999.0
        situacao, explicacao = ac.conferir(s)
        self.assertEqual(situacao, "rompido")
        self.assertIn("resumo de fecho", explicacao)

    def test_sessao_interrompida_nao_e_sessao_adulterada(self):
        # Queda de energia não é adulteração, e chamar uma pela outra
        # seria acusar o que não se constatou.
        ac, s = self.sessao()
        s.encerrada = False
        s.elo_final = ""
        self.assertEqual(ac.conferir(s)[0], "aberto")

    def test_o_relatorio_declara_o_alcance_da_corrente(self):
        ac, s = self.sessao()
        QApplication.instance() or QApplication([])
        texto = sem_marcacao(ac.relatorio_html(s))
        self.assertIn("Integridade do registro", texto)
        self.assertIn(s.elo_final, texto)
        # A limitação vai impressa: registro que se apresentasse como
        # inviolável prometeria o que não tem.
        self.assertIn("não detém quem reproduza", texto)
        self.assertIn("citado fora deste arquivo", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
