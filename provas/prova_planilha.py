"""Provas da Análise de Planilha.

O que se prova aqui não é que o código roda: é que ele calcula o que a
peça diz que calculou. Cada operação do roteiro é conferida em três
frentes — o resultado, o que o passo relata (as incomparáveis inclusive)
e a volta pelo roteiro salvo, porque operação que grava e não relê
transforma a análise inteira em papel.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis.tools import planilha_core as pc     # noqa: E402


def tabela(colunas, linhas):
    return pc.Tabela(colunas=list(colunas), linhas=[tuple(l) for l in linhas])


class ColunaDerivada(unittest.TestCase):

    def setUp(self):
        self.t = tabela(
            ["Nome", "Sobrenome", "Início", "Fim", "Doc"],
            [("João", "Silva", "01/01/2026", "31/01/2026", "12345678901"),
             ("Ana", "", "10/02/2026", "12/02/2026", "98765432100"),
             ("Bia", "Souza", "não é data", "05/03/2026", "11122233344")])

    def test_juntar_ignora_os_vazios(self):
        op = pc.Derivada(nome="Completo", calculo="juntar",
                         origens=["Nome", "Sobrenome"], separador=" ")
        r, p = op.aplicar(self.t)
        self.assertEqual(r.coluna("Completo"),
                         ["João Silva", "Ana", "Bia Souza"])
        self.assertEqual((p.antes, p.depois), (3, 3))
        self.assertEqual(p.incomparaveis, 0)

    def test_extrair_pedaco_do_texto(self):
        op = pc.Derivada(nome="Raiz", calculo="extrair", origens=["Doc"],
                         inicio=1, tamanho=3)
        r, _ = op.aplicar(self.t)
        self.assertEqual(r.coluna("Raiz"), ["123", "987", "111"])

    def test_extrair_tamanho_zero_vai_ate_o_fim(self):
        op = pc.Derivada(nome="Final", calculo="extrair", origens=["Doc"],
                         inicio=10, tamanho=0)
        r, _ = op.aplicar(self.t)
        self.assertEqual(r.coluna("Final"), ["01", "00", "44"])

    def test_dias_conta_e_a_data_ilegivel_vira_incomparavel(self):
        op = pc.Derivada(nome="Dias", calculo="dias",
                         origens=["Início", "Fim"])
        r, p = op.aplicar(self.t)
        self.assertEqual(r.coluna("Dias"), [30, 2, pc.VAZIO])
        self.assertEqual(p.incomparaveis, 1)
        # A linha não sumiu: a peça não pode dizer que ficou de fora.
        self.assertEqual(p.depois, 3)
        self.assertIn("vazia", p.destino_incomparaveis)

    def test_nao_sobrescreve_coluna_existente(self):
        op = pc.Derivada(nome="Nome", calculo="juntar", origens=["Doc"])
        r, p = op.aplicar(self.t)
        self.assertEqual(r.colunas, self.t.colunas)
        self.assertEqual(r.linhas, self.t.linhas)
        self.assertIn("já existe", p.aviso)

    def test_sem_nome_nao_executa(self):
        r, p = pc.Derivada(nome="   ", origens=["Nome"]).aplicar(self.t)
        self.assertEqual(r.colunas, self.t.colunas)
        self.assertIn("nome", p.aviso)

    def test_coluna_de_origem_que_sumiu_vira_aviso(self):
        op = pc.Derivada(nome="X", calculo="juntar", origens=["Inexistente"])
        r, p = op.aplicar(self.t)
        self.assertEqual(r.colunas, self.t.colunas)
        self.assertIn("não existe", p.aviso)

    def test_a_peca_nomeia_as_colunas_certas_com_virgula_no_nome(self):
        # Nome de coluna com vírgula já quebrou a frase uma vez.
        op = pc.Derivada(nome="D", calculo="dias",
                         origens=["Entrada, saída", "Fim"])
        self.assertIn('de "Entrada, saída" até "Fim"', op.descrever())


class Agrupar(unittest.TestCase):

    def setUp(self):
        self.t = tabela(
            ["UF", "Valor", "Data"],
            [("SP", 100, "01/03/2026"),
             ("RJ", 50, "02/03/2026"),
             ("SP", "n/d", "05/03/2026"),
             ("SP", 25.5, "03/03/2026")])
        self.op = pc.Agrupamento(
            chaves=["UF"],
            resumos=[("contar", ""), ("somar", "Valor"), ("maximo", "Data")])

    def test_um_grupo_por_chave_na_ordem_de_aparicao(self):
        r, p = self.op.aplicar(self.t)
        self.assertEqual(r.coluna("UF"), ["SP", "RJ"])
        self.assertEqual((p.antes, p.depois), (4, 2))

    def test_conta_soma_e_maior(self):
        r, _ = self.op.aplicar(self.t)
        self.assertEqual(r.colunas,
                         ["UF", "Quantidade", "Soma de Valor",
                          "Maior de Data"])
        self.assertEqual(r.coluna("Quantidade"), [3, 1])
        self.assertEqual(r.coluna("Soma de Valor"), [125.5, 50.0])
        self.assertEqual(r.coluna("Maior de Data"),
                         ["05/03/2026", "02/03/2026"])

    def test_celula_que_nao_e_numero_e_contada_e_nao_some(self):
        _, p = self.op.aplicar(self.t)
        self.assertEqual(p.incomparaveis, 1)
        self.assertIn("não entrou na conta", p.destino_incomparaveis)

    def test_media_so_divide_pelo_que_era_numero(self):
        op = pc.Agrupamento(chaves=["UF"], resumos=[("media", "Valor")])
        r, _ = op.aplicar(self.t)
        self.assertEqual(r.coluna("Média de Valor"), [62.75, 50.0])

    def test_menor_atende_a_data(self):
        op = pc.Agrupamento(chaves=["UF"], resumos=[("minimo", "Data")])
        r, _ = op.aplicar(self.t)
        self.assertEqual(r.coluna("Menor de Data"),
                         ["01/03/2026", "02/03/2026"])

    def test_nome_repetido_de_coluna_recebe_desempate(self):
        # A planilha já traz uma coluna "Quantidade", e ela é chave do
        # grupo. O título calculado colidiria; duas colunas de mesmo nome
        # fariam o passo seguinte ler a errada, calada.
        t = tabela(["UF", "Quantidade"], [("SP", 1), ("SP", 2)])
        op = pc.Agrupamento(chaves=["UF", "Quantidade"],
                            resumos=[("contar", "")])
        r, _ = op.aplicar(t)
        self.assertEqual(r.colunas, ["UF", "Quantidade", "Quantidade (2)"])
        self.assertEqual(len(set(r.colunas)), len(r.colunas))

    def test_sem_coluna_de_grupo_nao_executa(self):
        r, p = pc.Agrupamento(chaves=[], resumos=[("contar", "")]).aplicar(
            self.t)
        self.assertEqual(r.linhas, self.t.linhas)
        self.assertIn("nenhuma coluna de grupo", p.aviso)

    def test_grupos_se_formam_pelo_texto_exato(self):
        t = tabela(["UF"], [("SP",), ("sp",)])
        r, _ = pc.Agrupamento(chaves=["UF"],
                              resumos=[("contar", "")]).aplicar(t)
        self.assertEqual(r.n_linhas, 2)
        self.assertIn("texto exato", pc.Agrupamento(
            chaves=["UF"], resumos=[]).descrever())


class MarcarLinhas(unittest.TestCase):

    def setUp(self):
        self.t = tabela(["Nome", "Valor"],
                        [("A", 100), ("B", 5000), ("C", "sem valor")])
        self.alta = pc.Marcacao(coluna="Valor", condicao="maior",
                                valor="1000", marca="ALTO",
                                justificativa="acima do teto do edital")

    def test_marca_so_quem_atende(self):
        r, p = self.alta.aplicar(self.t)
        self.assertEqual(r.coluna("Marcação"), ["", "ALTO", ""])
        self.assertEqual((p.antes, p.depois), (3, 3))

    def test_o_que_nao_deu_para_avaliar_e_contado_e_segue_sem_marca(self):
        _, p = self.alta.aplicar(self.t)
        self.assertEqual(p.incomparaveis, 1)
        self.assertIn("sem marca", p.destino_incomparaveis)

    def test_a_justificativa_vai_na_peca(self):
        d = self.alta.descrever()
        self.assertIn("Justificativa: acima do teto do edital.", d)
        self.assertIn('Marcadas com "ALTO"', d)

    def test_quantas_marcou_aparece_no_passo(self):
        _, p = self.alta.aplicar(self.t)
        self.assertIn("Marcadas 1 linha(s).", p.descricao)

    def test_a_segunda_marca_se_soma_e_nao_apaga_a_primeira(self):
        r, _ = self.alta.aplicar(self.t)
        outra = pc.Marcacao(coluna="Nome", condicao="igual", valor="B",
                            marca="REVISAR", justificativa="pedido do chefe")
        r2, _ = outra.aplicar(r)
        self.assertEqual(r2.coluna("Marcação"), ["", "ALTO; REVISAR", ""])
        self.assertEqual(r2.n_colunas, 3)

    def test_a_mesma_marca_duas_vezes_nao_duplica(self):
        r, _ = self.alta.aplicar(self.t)
        r2, _ = self.alta.aplicar(r)
        self.assertEqual(r2.coluna("Marcação"), ["", "ALTO", ""])

    def test_marca_em_branco_nao_executa(self):
        op = pc.Marcacao(coluna="Valor", condicao="preenchido", marca="  ")
        r, p = op.aplicar(self.t)
        self.assertEqual(r.colunas, self.t.colunas)
        self.assertIn("em branco", p.aviso)


class CondicaoUnica(unittest.TestCase):
    """O filtro e a marcação precisam julgar exatamente igual."""

    def test_a_mesma_condicao_decide_o_mesmo_nos_dois(self):
        t = tabela(["Nome"], [("José",), ("JOSE",), ("Maria",)])
        f, _ = pc.Filtro(coluna="Nome", condicao="igual",
                         valor="jose").aplicar(t)
        m, _ = pc.Marcacao(coluna="Nome", condicao="igual", valor="jose",
                           marca="X").aplicar(t)
        marcadas = [l[0] for l in m.linhas if l[1]]
        self.assertEqual([l[0] for l in f.linhas], marcadas)

    def test_ordinal_sobre_texto_nao_da_falso_e_sim_indefinido(self):
        self.assertIsNone(pc.avaliar("maior", "abc", "10"))
        self.assertIs(pc.avaliar("maior", "20", "10"), True)

    def test_o_filtro_continua_se_lendo_como_antes(self):
        d = pc.Filtro(coluna="UF", condicao="igual", valor="SP").descrever()
        self.assertEqual(
            d, 'Mantidas as linhas em que "UF" igual a "SP", sem distinguir '
               "maiúsculas nem acentos")
        d2 = pc.Filtro(coluna="V", condicao="maior", valor="10",
                       manter=False).descrever()
        self.assertEqual(
            d2, 'Descartadas as linhas em que "V" maior que "10"')


class RoteiroQueVoltaInteiro(unittest.TestCase):
    """A prova que sustenta a peça: gravar, reler e chegar no mesmo lugar."""

    def montar(self):
        return [
            pc.Derivada(nome="Completo", calculo="juntar",
                        origens=["Nome", "UF"], separador=" - "),
            pc.Marcacao(coluna="Valor", condicao="maior", valor="60",
                        marca="ALTO", justificativa="acima da média"),
            pc.Filtro(coluna="UF", condicao="igual", valor="sp"),
            pc.Agrupamento(chaves=["UF"],
                           resumos=[("contar", ""), ("somar", "Valor")]),
        ]

    def test_toda_operacao_nova_esta_no_registro(self):
        for op in self.montar():
            self.assertIn(op.tipo, pc.TIPOS, op.tipo + " fora de TIPOS")

    def test_o_roteiro_salvo_reproduz_o_mesmo_resumo(self):
        base = tabela(["Nome", "UF", "Valor"],
                      [("A", "SP", 100), ("B", "RJ", 50),
                       ("C", "SP", 25), ("D", "SP", "n/d")])
        a = pc.Analise(origem="x.xlsx", operacoes=self.montar())
        antes, _ = a.executar(base)

        # A ida e a volta pelo formato gravado, que é o caminho real.
        b = pc.Analise.de_dados(a.dados())
        depois, _ = b.executar(base)

        self.assertEqual(antes.resumo(), depois.resumo())
        self.assertEqual(antes.colunas, depois.colunas)
        self.assertEqual(antes.linhas, depois.linhas)

    def test_o_arquivo_de_roteiro_faz_a_volta_completa(self):
        import json
        import tempfile
        a = pc.Analise(origem="x.xlsx", operacoes=self.montar())
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "roteiro.json"
            pc.salvar_roteiro(a, caminho)
            lida = pc.ler_roteiro(caminho)
            self.assertEqual(json.loads(caminho.read_text(encoding="utf-8"))
                             ["operacoes"][0]["tipo"], "derivada")
        self.assertEqual([o.tipo for o in lida.operacoes],
                         [o.tipo for o in a.operacoes])
        self.assertEqual(lida.dados(), a.dados())


class CruzarComOutraPlanilha(unittest.TestCase):
    """O PROCV, e o que ele precisa declarar para virar peça."""

    def setUp(self):
        import tempfile
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.esquerda = tabela(
            ["Matricula", "Nome"],
            [("001", "Ana"), ("002", "Bruno"), ("003", "Caio")])
        # A chave 003 aparece duas vezes do outro lado, de propósito.
        self.direita = self.gravar(
            "cadastro.xlsx", ["Mat", "Lotacao"],
            [("001", "Sede"), ("003", "Norte"), ("003", "Sul")])

    def gravar(self, nome, colunas, linhas):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(list(colunas))
        for linha in linhas:
            ws.append(list(linha))
        caminho = Path(self.pasta.name) / nome
        wb.save(caminho)
        return caminho

    def cruzamento(self, **ajustes):
        campos = dict(arquivo=str(self.direita), chave_aqui="Matricula",
                      chave_la="Mat", trazer=["Lotacao"])
        campos.update(ajustes)
        return pc.Cruzamento(**campos)

    def test_traz_a_coluna_da_outra_planilha(self):
        r, p = self.cruzamento().aplicar(self.esquerda)
        self.assertEqual(r.colunas, ["Matricula", "Nome", "Lotacao"])
        self.assertEqual(r.coluna("Lotacao"), ["Sede", "", "Norte"])
        self.assertIn("Encontraram par 2 linha(s); 1, não.", p.descricao)

    def test_chave_repetida_usa_a_primeira_e_declara_que_repetia(self):
        _, p = self.cruzamento().aplicar(self.esquerda)
        self.assertIn("1 chave(s)", p.aviso)
        self.assertIn("primeira ocorrência", p.aviso)

    def test_sem_par_descartada(self):
        r, _ = self.cruzamento(sem_par="descartar").aplicar(self.esquerda)
        self.assertEqual(r.coluna("Matricula"), ["001", "003"])

    def test_sem_par_e_o_que_fica_e_a_relacao_das_divergencias(self):
        r, _ = self.cruzamento(sem_par="somente").aplicar(self.esquerda)
        self.assertEqual(r.coluna("Matricula"), ["002"])

    def test_casa_sem_distinguir_caixa_e_acento_por_padrao(self):
        esquerda = tabela(["Chave"], [("JOSÉ",)])
        direita = self.gravar("outra.xlsx", ["Chave", "Dado"],
                              [("jose", "achou")])
        op = pc.Cruzamento(arquivo=str(direita), chave_aqui="Chave",
                           chave_la="Chave", trazer=["Dado"])
        r, _ = op.aplicar(esquerda)
        self.assertEqual(r.coluna("Dado"), ["achou"])
        r2, _ = pc.Cruzamento(arquivo=str(direita), chave_aqui="Chave",
                              chave_la="Chave", trazer=["Dado"],
                              sensivel=True).aplicar(esquerda)
        self.assertEqual(r2.coluna("Dado"), [""])

    def test_coluna_trazida_de_nome_repetido_nao_encobre_a_daqui(self):
        direita = self.gravar("nomes.xlsx", ["Mat", "Nome"],
                              [("001", "Ana Maria")])
        r, _ = pc.Cruzamento(arquivo=str(direita), chave_aqui="Matricula",
                             chave_la="Mat",
                             trazer=["Nome"]).aplicar(self.esquerda)
        self.assertEqual(r.colunas, ["Matricula", "Nome", "Nome (2)"])
        self.assertEqual(r.coluna("Nome"), ["Ana", "Bruno", "Caio"])
        self.assertEqual(r.coluna("Nome (2)"), ["Ana Maria", "", ""])

    def test_planilha_que_sumiu_vira_aviso_e_nao_queda(self):
        op = self.cruzamento(arquivo=str(Path(self.pasta.name) / "nada.xlsx"))
        r, p = op.aplicar(self.esquerda)
        self.assertEqual(r.linhas, self.esquerda.linhas)
        self.assertIn("não encontrada", p.aviso)

    def test_coluna_chave_ausente_do_outro_lado_vira_aviso(self):
        r, p = self.cruzamento(chave_la="Inexistente").aplicar(self.esquerda)
        self.assertEqual(r.colunas, self.esquerda.colunas)
        self.assertIn("não existe na planilha cruzada", p.aviso)

    def test_planilha_trocada_depois_de_escolhida_e_denunciada(self):
        op = self.cruzamento(resumo_arquivo="0" * 64)
        _, p = op.aplicar(self.esquerda)
        self.assertIn("mudou depois de escolhida", p.aviso)
        # E ainda assim executa: o passo relata, não interrompe a análise.
        self.assertIn("Encontraram par", p.descricao)

    def test_arquivo_alterado_no_disco_e_relido(self):
        r1, _ = self.cruzamento().aplicar(self.esquerda)
        self.assertEqual(r1.coluna("Lotacao"), ["Sede", "", "Norte"])
        self.gravar("cadastro.xlsx", ["Mat", "Lotacao"],
                    [("001", "Leste"), ("002", "Oeste")])
        r2, _ = self.cruzamento().aplicar(self.esquerda)
        self.assertEqual(r2.coluna("Lotacao"), ["Leste", "Oeste", ""])

    def test_a_peca_relaciona_as_duas_origens_e_ganha_a_ressalva(self):
        analise = pc.Analise(origem=str(self.direita),
                             operacoes=[self.cruzamento()])
        resultado, passos = analise.executar(self.esquerda)
        saida = Path(self.pasta.name) / "resultado.xlsx"
        pc.gravar(resultado, saida)
        termo = pc.montar_termo(analise, resultado, passos, str(saida))
        self.assertEqual(len(termo.itens[0].origens), 2)
        self.assertIn(pc.RESSALVA_CRUZAMENTO, termo.ressalvas)

    def test_sem_cruzamento_a_ressalva_nao_aparece(self):
        analise = pc.Analise(origem=str(self.direita), operacoes=[])
        saida = Path(self.pasta.name) / "so.xlsx"
        pc.gravar(self.esquerda, saida)
        termo = pc.montar_termo(analise, self.esquerda, [], str(saida))
        self.assertEqual(len(termo.itens[0].origens), 1)
        self.assertNotIn(pc.RESSALVA_CRUZAMENTO, termo.ressalvas)

    def test_o_roteiro_com_cruzamento_faz_a_volta(self):
        op = self.cruzamento(sem_par="somente", sensivel=True,
                             resumo_arquivo="a" * 64, linha_cabecalho=1)
        volta = pc.TIPOS["cruzamento"].de_dados(op.dados())
        self.assertEqual(volta.dados(), op.dados())

    def test_a_auxiliar_e_relacionada_como_arquivo_do_roteiro(self):
        analise = pc.Analise(operacoes=[self.cruzamento(), self.cruzamento()])
        # A mesma planilha duas vezes conta uma só: a peça relaciona
        # arquivos, não passos.
        self.assertEqual(pc.arquivos_auxiliares(analise), [str(self.direita)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
