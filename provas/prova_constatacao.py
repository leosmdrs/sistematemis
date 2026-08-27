"""Provas da consulta ao registro do domínio, na Constatação Web.

O certificado diz quem o **servidor** afirma ser; o registro diz quem
respondeu pelo **nome**. Certificado se obtém em minutos, para qualquer
domínio, e não identifica pessoa alguma — de modo que, numa apuração, o
registro costuma ser o dado que interessa.

Estas provas não tocam a rede: a resposta do registro é simulada, e o que
se confere é a leitura dela e o que a peça diz a respeito. Prova que
depende de servidor de terceiro falha por motivo alheio ao código, e
prova que falha por motivo alheio deixa de ser lida.
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication              # noqa: E402

from temis.tools import constatacao_core as cc       # noqa: E402

#: Uma resposta como o registro.br devolve, reduzida ao que se lê dela.
RESPOSTA = {
    "objectClassName": "domain",
    "ldhName": "exemplo.com.br",
    "status": ["active"],
    "events": [
        {"eventAction": "registration", "eventDate": "2013-02-22T10:00:00Z"},
        {"eventAction": "last changed", "eventDate": "2024-12-04T08:30:00Z"},
        {"eventAction": "expiration", "eventDate": "2027-02-22T00:00:00Z"},
    ],
    "nameservers": [{"ldhName": "ns2.exemplo.com.br"},
                    {"ldhName": "ns1.exemplo.com.br"}],
    "entities": [
        {"handle": "01409598000130", "roles": ["registrant"],
         "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                  ["fn", {}, "text", "Órgão de Exemplo"]]]},
        {"handle": "REG-BR", "roles": ["registrar"],
         "vcardArray": ["vcard", [["fn", {}, "text", "Registro.br"]]]},
    ],
}


class LeituraDaRespostaDoRegistro(unittest.TestCase):

    def setUp(self):
        self.chamadas = []
        original = cc._abrir
        bootstrap = list(cc._BOOTSTRAP)
        cc._BOOTSTRAP.clear()
        cc._BOOTSTRAP.append({"services": [
            [["br"], ["https://rdap.registro.br"]],
            [["com"], ["https://rdap.verisign.com/com/v1"]],
        ]})

        def falso(url, tempo=8):
            self.chamadas.append(url)
            if "/domain/exemplo.com.br" in url:
                return json.dumps(RESPOSTA).encode("utf-8")
            raise OSError("404")

        cc._abrir = falso

        def repor():
            cc._abrir = original
            cc._BOOTSTRAP.clear()
            cc._BOOTSTRAP.extend(bootstrap)
        self.addCleanup(repor)

    def test_le_titular_documento_datas_e_dns(self):
        r, bruto = cc.registro_do_dominio("exemplo.com.br")
        self.assertTrue(r.obtido)
        self.assertEqual(r.titular, "Órgão de Exemplo")
        self.assertEqual(r.documento, "01409598000130")
        self.assertEqual(r.responsavel, "Registro.br")
        self.assertEqual(r.criado_em, "2013-02-22")
        self.assertEqual(r.alterado_em, "2024-12-04")
        self.assertEqual(r.expira_em, "2027-02-22")
        self.assertEqual(r.situacao, ["active"])
        # Ordenados: a peça não deve mudar conforme a ordem em que o
        # registro devolveu os servidores.
        self.assertEqual(r.servidores_dns,
                         ["ns1.exemplo.com.br", "ns2.exemplo.com.br"])
        self.assertTrue(bruto, "a resposta bruta tem de voltar")

    def test_encurta_o_nome_ate_o_registro_responder(self):
        # "www.exemplo.com.br" não é domínio registrado; "exemplo.com.br"
        # é. Assim não é preciso carregar a lista pública de sufixos.
        r, _ = cc.registro_do_dominio("www.exemplo.com.br")
        self.assertTrue(r.obtido)
        self.assertEqual(r.dominio, "exemplo.com.br")
        self.assertTrue(any("www.exemplo.com.br" in u for u in self.chamadas),
                        "tentou o nome inteiro primeiro")

    def test_escolhe_a_terminacao_mais_longa_da_lista_da_iana(self):
        cc._BOOTSTRAP.clear()
        cc._BOOTSTRAP.append({"services": [
            [["br"], ["https://curto"]],
            [["com.br"], ["https://longo"]],
        ]})
        self.assertEqual(cc._servidor_rdap("exemplo.com.br"), "https://longo")

    def test_registro_que_nao_responde_vira_erro_e_nao_queda(self):
        r, bruto = cc.registro_do_dominio("nao-existe.com")
        self.assertFalse(r.obtido)
        self.assertTrue(r.erro)
        self.assertEqual(bruto, b"")

    def test_endereco_sem_dominio_nao_consulta_nada(self):
        r, _ = cc.registro_do_dominio("")
        self.assertFalse(r.obtido)
        self.assertEqual(self.chamadas, [])

    def test_titular_suprimido_nao_vira_titular_vazio_mentiroso(self):
        # Registros de domínios genéricos ocultam o titular por proteção
        # de dados. O campo volta vazio, e a peça diz "não publicado" —
        # que é diferente de "não há titular".
        sem_titular = dict(RESPOSTA)
        sem_titular["entities"] = [{"handle": "X", "roles": ["registrar"],
                                    "vcardArray": ["vcard", [
                                        ["fn", {}, "text", "Reg"]]]}]
        cc._abrir = lambda url, tempo=8: json.dumps(sem_titular).encode()
        r, _ = cc.registro_do_dominio("exemplo.com.br")
        self.assertTrue(r.obtido)
        self.assertEqual(r.titular, "")
        self.assertEqual(r.responsavel, "Reg")


class APecaDeclaraOQueOhRegistroE(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def termo(self, com_registro=True):
        c = cc.Captura(url="https://exemplo.com.br/", titulo="Exemplo",
                       ips=["200.1.2.3"])
        c.certificado = cc.Certificado(titular="exemplo.com.br", emissor="CA",
                                       impressao="a" * 64, valido_de="a",
                                       valido_ate="b", numero_serie="01")
        if com_registro:
            c.registro = cc.Registro(
                dominio="exemplo.com.br", servidor="https://rdap.registro.br",
                titular="Órgão de Exemplo", documento="01409598000130",
                criado_em="2013-02-22", situacao=["active"],
                servidores_dns=["ns1.exemplo.com.br"])
        s = cc.Sessao()
        s.capturas.append(c)
        html = cc.build_html(s, cc.Declarante(nome="Fulano"),
                             cc.Procedimento())
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    def test_o_registro_sai_na_peca_com_titular_e_identificador(self):
        texto = self.termo()
        for pedaco in ("Registro — domínio", "Órgão de Exemplo",
                       "01409598000130", "rdap.registro.br"):
            with self.subTest(pedaco):
                self.assertIn(pedaco, texto)

    def test_a_peca_diz_que_o_registro_e_declaracao_de_terceiro(self):
        # Apresentar declaração alheia como apuração própria é o excesso
        # que derruba a peça inteira.
        texto = self.termo()
        self.assertIn("declarações de quem mantém o registro", texto)
        self.assertIn("não apuração desta ferramenta", texto)

    def test_sem_registro_a_ressalva_nao_aparece(self):
        texto = self.termo(com_registro=False)
        self.assertNotIn("declarações de quem mantém o registro", texto)


class AsNormasVaoCitadas(unittest.TestCase):

    def test_a_peca_nomeia_as_duas_normas(self):
        from temis import procedencia
        frase = procedencia.frase([])
        self.assertIn("ISO/IEC 27037", frase)
        self.assertIn("RFC 3227", frase)

    def test_a_citacao_nao_promete_conformidade_em_bloco(self):
        # Norma não se atende por adesão. A frase diz quanto ao quê, e
        # aponta onde está o que fica de fora.
        from temis import procedencia
        frase = procedencia.frase([])
        self.assertIn("quanto à documentação", frase)
        self.assertIn("o que fica fora dela", frase)
        self.assertIn("NORMAS.md", frase)

    def test_o_mapeamento_existe_e_declara_o_que_nao_e_coberto(self):
        normas = (Path(__file__).resolve().parents[1] / "NORMAS.md"
                  ).read_text(encoding="utf-8")
        for marca in ("ISO/IEC 27037", "RFC 3227", "Auditabilidade",
                      "Reprodutibilidade", "ordem de volatilidade"):
            with self.subTest(marca):
                self.assertIn(marca, normas)
        self.assertEqual(normas.count("O que não é coberto"), 2,
                         "as duas normas precisam declarar o que fica fora")


if __name__ == "__main__":
    unittest.main(verbosity=2)
