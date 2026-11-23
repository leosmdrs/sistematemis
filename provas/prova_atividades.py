"""Provas do Relatório de Atividades: o fecho e a sua conferência.

O registro da sessão é oferecido para os autos, e o que o sustenta é o
resumo de fecho. Três coisas se conferem: que a sessão encerrada volta
do disco **com** o fecho, e portanto confere; que o fecho cobre também
as falhas do próprio registrador; e que as sessões gravadas antes disso
continuam conferindo pelo cálculo com que foram fechadas.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication              # noqa: E402

from temis.tools import atividades_core as ac         # noqa: E402

_app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.pasta = Path(self._dir.name)

    def sessao_encerrada(self):
        r = ac.Registrador(self.pasta)
        r.iniciar()
        r.abriu("tarja", "Tarja Preta")
        r.anotar("Tarja Preta", "Documento salvo")
        r.anotar("Tarja Preta", "Termo emitido")
        r.encerrar()
        return r

    def do_disco(self, r):
        return ac.ler_sessao(r.caminho_dados())


class OFechoSobreviveALeitura(Base):

    def test_sessao_encerrada_relida_confere(self):
        r = self.sessao_encerrada()
        self.assertEqual(ac.conferir(r.sessao)[0], "integro")
        relida = self.do_disco(r)
        self.assertEqual(relida.elo_final, r.sessao.elo_final)
        self.assertEqual(ac.conferir(relida)[0], "integro")

    def test_o_relatorio_refeito_nao_diz_que_a_sessao_ficou_aberta(self):
        r = self.sessao_encerrada()
        peca = ac.relatorio_html(self.do_disco(r))
        self.assertNotIn("não foi encerrada normalmente", peca)
        self.assertIn(r.sessao.elo_final, peca)

    def test_sessao_interrompida_continua_aberta_e_nao_rompida(self):
        r = ac.Registrador(self.pasta)
        r.iniciar()
        r.anotar("Tarja Preta", "Documento salvo")
        self.assertEqual(ac.conferir(self.do_disco(r))[0], "aberto")


class OFechoAcusaAlteracao(Base):

    def alterar(self, r, mudanca):
        dados = json.loads(r.caminho_dados().read_text(encoding="utf-8"))
        mudanca(dados)
        r.caminho_dados().write_text(json.dumps(dados), encoding="utf-8")
        return self.do_disco(r)

    def test_anotacao_alterada_rompe(self):
        r = self.sessao_encerrada()
        s = self.alterar(r, lambda d: d["anotacoes"][0].update(texto="x"))
        self.assertEqual(ac.conferir(s)[0], "rompido")

    def test_campo_fora_da_corrente_alterado_rompe(self):
        r = self.sessao_encerrada()
        s = self.alterar(r, lambda d: d["operador"].update(nome="Outro"))
        self.assertEqual(ac.conferir(s)[0], "rompido")

    def test_falha_do_registrador_apagada_rompe(self):
        r = ac.Registrador(self.pasta)
        r.iniciar()
        r.anotar("Tarja Preta", "Documento salvo")
        r.sessao.erros.append("gravação: PermissionError: negado")
        r.encerrar()
        self.assertEqual(ac.conferir(self.do_disco(r))[0], "integro")
        s = self.alterar(r, lambda d: d["erros"].clear())
        self.assertEqual(ac.conferir(s)[0], "rompido")

    def test_falha_ao_escrever_o_relatorio_fica_coberta_pelo_fecho(self):
        r = ac.Registrador(self.pasta)
        r.iniciar()
        r.anotar("Tarja Preta", "Documento salvo")
        r.caminho_relatorio().mkdir()            # escrever aqui falha
        self.assertIsNone(r.encerrar())
        relida = self.do_disco(r)
        self.assertTrue(any("relatório" in e for e in relida.erros))
        self.assertEqual(ac.conferir(relida)[0], "integro")


class SessaoAntigaContinuaConferindo(Base):

    def test_fecho_calculado_sem_as_falhas_ainda_confere(self):
        r = ac.Registrador(self.pasta)
        r.iniciar()
        r.anotar("Tarja Preta", "Documento salvo")
        r.sessao.erros.append("gravação: OSError: disco cheio")
        r.encerrar()
        # Como as versões anteriores gravavam: fecho sem as falhas, e
        # sem o campo que diz de que ele é feito.
        r.sessao.fecho_versao = 1
        antigo = ac.fecho_de(r.sessao)
        dados = json.loads(r.caminho_dados().read_text(encoding="utf-8"))
        dados["elo_final"] = antigo
        del dados["fecho_versao"]
        r.caminho_dados().write_text(json.dumps(dados), encoding="utf-8")

        relida = self.do_disco(r)
        self.assertEqual(relida.fecho_versao, 1)
        self.assertEqual(ac.conferir(relida)[0], "integro")

    def test_sessao_nova_fecha_pela_versao_atual(self):
        r = self.sessao_encerrada()
        self.assertEqual(self.do_disco(r).fecho_versao, ac.FECHO_ATUAL)


class RelatoDepoisDoFechoNaoEntra(Base):

    def test_anotacao_tardia_nao_rompe_a_sessao(self):
        r = self.sessao_encerrada()
        quantas = len(r.sessao.anotacoes)
        r.anotar("Vídeo da Internet", "Captura concluída")
        self.assertEqual(len(r.sessao.anotacoes), quantas)
        self.assertEqual(ac.conferir(self.do_disco(r))[0], "integro")


class ORegistroNaoGuardaDadoDeCaso(Base):
    """O ato fica; o que identifica o caso sai antes de ser anotado."""

    CASOS = (
        ("Pesquisa “123.456.789-00” registrada no termo (3 resultado(s)).",
         ("123.456.789-00",)),
        ("Caso: “Operação Exemplo”", ("Operação Exemplo",)),
        ("Resultado salvo: oitiva-fulano-de-tal.xlsx",
         ("oitiva-fulano-de-tal",)),
        (r"Aberto: C:\Users\beltrano\Documentos\PAD 08650.000123-2026\a.pdf",
         ("beltrano", "08650", "a.pdf")),
        ("Acesso a endereço https://sistema.exemplo/consulta?cpf=1",
         ("sistema.exemplo",)),
        ("Enviado para fulano.silva@exemplo.gov.br", ("fulano.silva",)),
        ("Processo 08650.000123/2026-11 conferido", ("000123",)),
    )

    def test_o_dado_sai_e_o_ato_fica(self):
        for texto, proibidos in self.CASOS:
            with self.subTest(texto[:30]):
                limpo = ac.sem_dado_de_caso(texto)
                for dado in proibidos:
                    self.assertNotIn(dado, limpo)
                self.assertEqual(limpo.split()[0], texto.split()[0])

    def test_o_que_nao_e_dado_fica_como_esta(self):
        for texto in ("Documento salvo", "3 ocorrência(s) tarjada(s)",
                      "Gravação encerrada: 00:12:40, 35,2 MB.",
                      "Captura 2 registrada · resumo ab12cd34ef56…"):
            self.assertEqual(ac.sem_dado_de_caso(texto), texto)

    def test_a_anotacao_gravada_ja_vem_limpa_e_a_corrente_confere(self):
        r = ac.Registrador(self.pasta)
        r.iniciar()
        r.anotar("Varredura", "Pesquisa “123.456.789-00” registrada")
        r.encerrar()
        em_disco = r.caminho_dados().read_text(encoding="utf-8")
        self.assertNotIn("123.456.789-00", em_disco)
        self.assertEqual(ac.conferir(self.do_disco(r))[0], "integro")


class ORegistroNaoDescreveARedeInterna(Base):

    def test_dominio_serie_mac_e_enderecos_nao_sao_guardados(self):
        r = ac.Registrador(self.pasta)
        r.iniciar()
        for chave in ("dominio", "serie", "mac", "enderecos"):
            self.assertNotIn(chave, r.sessao.maquina)

    def test_sessao_antiga_que_os_tinha_nao_os_imprime(self):
        r = self.sessao_encerrada()
        r.sessao.maquina.update(
            mac="AA-BB-CC-DD-EE-FF", serie="SN123456",
            enderecos=["10.20.30.40"], dominio="INTRANET")
        peca = ac.relatorio_html(r.sessao)
        for dado in ("AA-BB-CC-DD-EE-FF", "SN123456", "10.20.30.40",
                     "INTRANET"):
            self.assertNotIn(dado, peca)


if __name__ == "__main__":
    unittest.main(verbosity=2)
