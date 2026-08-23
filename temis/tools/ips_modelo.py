"""
O roteiro da Informação: partes, texto pronto, orientação e norma.

Este módulo é **conteúdo**, não mecanismo. Ele transcreve a minuta da
Corregedoria-Geral (SEI nº 56612608) e os dispositivos da Instrução
Normativa PRF nº 127, de 9 de maio de 2024, que dão base a cada parte.
Acrescentar, reordenar ou reescrever uma parte é mexer aqui — o resto da
ferramenta se ajusta sozinho.

A estrutura das seis partes não é escolha de projeto: vem do art. 92 da
IN 127, que enumera o que a Informação deve conter.

Dois tipos de texto pronto convivem no roteiro:

* **padrão** — redação que se repete em toda Informação (a citação da
  norma, "É o relatório.", a abertura da conclusão). Entra no documento
  como está e o encarregado ajusta se quiser.
* **exemplo** — a ilustração da minuta, escrita sobre um caso fictício.
  Fica à vista como guia, mas não vai para o documento enquanto não for
  reescrita. O modelo fala em "PRF FULANO DE TAL" e em quantias
  inventadas; esse texto chegar aos autos seria erro grave.
"""

from __future__ import annotations

from .ips_blocos import ALINEA, NUMERO, SEM_MARCADOR, TABELA


# ─────────────────────────────────────────
#  ATALHOS PARA MONTAR O ROTEIRO
# ─────────────────────────────────────────

def p(texto: str, nivel: int = 1, exemplo: bool = False) -> dict:
    """Parágrafo numerado (1.1, 1.2, 1.1.1…)."""
    return {"nivel": nivel, "estilo": NUMERO, "exemplo": exemplo,
            "html": f"<p>{texto}</p>"}


def alinea(texto: str, nivel: int = 2, exemplo: bool = False) -> dict:
    """Alínea a), b), c)."""
    return {"nivel": nivel, "estilo": ALINEA, "exemplo": exemplo,
            "html": f"<p>{texto}</p>"}


def cita(texto: str, nivel: int = 2) -> dict:
    """Transcrição de dispositivo: recuada e sem marcador."""
    return {"nivel": nivel, "estilo": SEM_MARCADOR, "exemplo": False,
            "html": f"<p>{texto}</p>"}


def subtitulo(texto: str) -> dict:
    """Divisão interna do elemento, em negrito e sem numeração."""
    return {"nivel": 1, "estilo": SEM_MARCADOR, "exemplo": False,
            "html": f"<p><b>{texto}</b></p>"}


def tabela(cabecalho: list[str], linhas: int = 2) -> dict:
    celulas = [list(cabecalho)]
    celulas += [[""] * len(cabecalho) for _ in range(linhas)]
    return {"tipo": TABELA, "nivel": 1, "estilo": SEM_MARCADOR,
            "celulas": celulas, "cabecalho": True, "exemplo": False}


# ─────────────────────────────────────────
#  1. IDENTIFICAÇÃO
# ─────────────────────────────────────────

IDENTIFICACAO = (
    p("Trata-se de Investigação Preliminar Sumária - IPS instaurada pela "
      "Ordem de Missão nº XX/XXXX, de XX/XX/XXXX (SEI! nº XXXX), publicada "
      "no Boletim de Serviço Eletrônico - BSE em XX/XX/XXXX, da lavra do "
      "Senhor Chefe da Corregedoria de XXXX, oriunda de Denúncia (SEI! nº "
      "XXXX), datada de XX/XX/XXXX, contra o servidor <b>PRF FULANO DE "
      "TAL</b>, matrícula SIAPE nº XXXXXX, lotado no Núcleo de Policiamento "
      "e Fiscalização - NPF da Superintendência da Polícia Rodoviária "
      "Federal no Estado de XXXX - SPRF-XX.", exemplo=True),
)

ORIENTACAO_IDENTIFICACAO = (
    "O item deve conter o documento que instaurou o procedimento em curso, "
    "ressaltando-se a autoridade responsável pela instauração e a data de "
    "sua publicação.\n\n"
    "Sempre que possível, a Informação deve apresentar o(s) servidor(es) "
    "acusado(s). Sugere-se que o nome seja inserido em caixa alta e em "
    "negrito, seguido do número de matrícula e da lotação.\n\n"
    "Caso se trate de servidor aposentado ou que já sofreu penalidade "
    "expulsiva, tal circunstância deve ser indicada desde logo."
)

NORMA_IDENTIFICACAO = (
    "Art. 92. Finalizada a IPS ou após diligências preliminares, será "
    "elaborada Informação de caráter opinativo, com os dados indispensáveis "
    "ao juízo de admissibilidade da autoridade disciplinar competente, e "
    "deverá conter:\n"
    "I - identificação do procedimento;\n\n"
    "Art. 68. A IPS será instaurada pela autoridade disciplinar ou por chefe "
    "de unidade correcional a ela diretamente subordinada, de ofício ou com "
    "base em denúncia, representação ou relato de irregularidade, inclusive "
    "anônimas.\n"
    "§ 1º Após ciência dos fatos pela autoridade disciplinar competente para "
    "o caso, a instauração da IPS se dará por meio de Decisão "
    "Administrativa, publicada no Boletim de Serviço Eletrônico.\n"
    "§ 2º A publicação de que trata o parágrafo anterior poderá se dar por "
    "meio de Extrato.\n\n"
    "Art. 69. Na instauração da IPS deverá ser designado um ou mais "
    "servidores da PRF que atuarão como Encarregados do caso, sem exigência "
    "de estabilidade.\n"
    "§ 3º O prazo para conclusão da IPS será de 60 (sessenta) dias, podendo "
    "ser prorrogado por igual período, quando necessário à conclusão dos "
    "trabalhos, e mediante despacho da unidade correcional responsável pela "
    "instauração."
)


# ─────────────────────────────────────────
#  2. APRESENTAÇÃO DO FATO
# ─────────────────────────────────────────

APRESENTACAO = (
    p("Conforme a denúncia anônima apresentada (SEI! nº XXXX), o acusado, na "
      "data de XX/XX/XXXX, cerca das XX:XX h, no km XXX da BR XXX-XX, "
      "abordou o veículo XXX, placas XXX-XXXX, conduzido pelo Sr. BELTRANO "
      "DE TAL. Ao constatar que o condutor era inabilitado, o servidor "
      "solicitou a quantia de R$ 100,00 para deixar de reter o veículo e "
      "lavrar a autuação. Após a entrega da quantia em espécie, o veículo "
      "foi liberado.", exemplo=True),
)

ORIENTACAO_APRESENTACAO = (
    "O item deve indicar de maneira clara e objetiva os fatos que são objeto "
    "da persecução disciplinar. As informações consignadas devem ser capazes "
    "de responder, sempre que possível, às seguintes questões: quê?; onde?; "
    "quem?; quando?; como?; por quê? e com que meios? (heptâmetro de "
    "Quintiliano).\n\n"
    "Este NÃO é o momento adequado para indicar os elementos de convicção "
    "que amparem a narrativa apresentada. Mais adiante existirão itens "
    "específicos para este fim.\n\n"
    "Quando o processo disciplinar em curso envolver mais de um fato, cada "
    "um deles deve ser descrito individualmente, não sendo possível se ater "
    "apenas ao fato mais grave.\n\n"
    "Tenha em vista que a delimitação dos fatos também se presta a permitir "
    "a análise de eventual duplicidade de processos em curso, ou mesmo a "
    "existência de coisa julgada administrativa."
)

NORMA_APRESENTACAO = (
    "Art. 92. (…) II - apresentação da denúncia inicial e dos fatos "
    "apurados;\n\n"
    "Art. 71. A IPS instaurada deverá se ater aos fatos que foram "
    "cientificados à autoridade disciplinar e àqueles conexos.\n"
    "§ 1º Surgindo novos fatos no curso da apuração, que não guardem conexão "
    "com os fatos originários, ou que tratem de condutas de servidores não "
    "apontados inicialmente como investigados, o Encarregado deverá dar "
    "ciência do incidente à autoridade disciplinar.\n"
    "§ 2º A autoridade disciplinar, ao tomar conhecimento de novos fatos ou "
    "novos investigados no curso da IPS deverá prolatar decisão para "
    "continuidade da investigação nos mesmos autos ou em novo caderno "
    "processual."
)


# ─────────────────────────────────────────
#  3. DOCUMENTOS E DILIGÊNCIAS
# ─────────────────────────────────────────

DOCUMENTOS = (
    p("Inicialmente, Beltrano redigiu o Ofício nº XX/XXXX/XXX (SEI! nº "
      "XXXX), informando a autoridade competente a respeito do ilícito "
      "supostamente perpetrado pelo servidor Fulano de Tal.", exemplo=True),
    p("Por conseguinte, foi determinada a abertura de Investigação "
      "Preliminar Sumária - IPS, conforme consta da Decisão Administrativa "
      "nº XX/XXXX (SEI! nº XXXX).", exemplo=True),
    p("Ao longo da fase pré-processual, cumpre destacar a juntada dos "
      "seguintes elementos de convicção:", exemplo=True),
    alinea("Termo de Declaração de XXX (SEI! nº XXXX);", exemplo=True),
    alinea("Gravações da abordagem policial (SEI! nº XXXX); e", exemplo=True),
    alinea("Extrato Funcional do investigado (SEI! nº XXXX).", exemplo=True),
    p("É o relatório."),
)

ORIENTACAO_DOCUMENTOS = (
    "É importante que fique claro quais foram os elementos que embasaram a "
    "decisão que determinou a instauração da Investigação Preliminar "
    "Sumária.\n\n"
    "Ademais, deve-se relatar as diligências empreendidas e enumerar os "
    "elementos de convicção angariados, indicando-se o número SEI! "
    "correspondente.\n\n"
    "O elemento se encerra com “É o relatório.”, que já vem escrito ao final."
)

NORMA_DOCUMENTOS = (
    "Art. 92. (…) III - documentos e diligências contidas no procedimento;\n\n"
    "Art. 70. A IPS será processada no âmbito da respectiva unidade "
    "correcional, que supervisionará sua instrução zelando pela completa "
    "apuração dos fatos, pela observância ao cronograma de trabalho "
    "estabelecido e pela utilização dos meios probatórios adequados, devendo "
    "ser adotados atos que compreendam:\n"
    "I - exame inicial das informações e provas existentes no momento da "
    "ciência dos fatos pela autoridade instauradora;\n"
    "II - realização de diligências, oitivas, e produção de informações "
    "necessárias para averiguar a procedência da denúncia ou relato de "
    "irregularidade, tais como:\n"
    "a) solicitar dos órgãos e entidades públicas e privadas todos os "
    "documentos relacionados com os fatos em apuração;\n"
    "b) diligenciar diretamente junto a agentes públicos e particulares, "
    "solicitando informações ou documentos que entender necessários;\n"
    "c) solicitar exames periciais que entender pertinentes; e\n"
    "d) intimar agentes públicos e particulares a prestarem esclarecimentos, "
    "quando necessário;\n"
    "III - manifestação conclusiva e fundamentada, que indique o cabimento "
    "de instauração de processo correcional acusatório, a possibilidade de "
    "celebração de TAC ou o arquivamento da denúncia, representação ou "
    "relato de irregularidade."
)


# ─────────────────────────────────────────
#  4. ANÁLISE PRESCRICIONAL
# ─────────────────────────────────────────

PRESCRICIONAL = (
    p("O fato chegou ao conhecimento da Administração Pública em "
      "XX/XX/XXXX, por meio do Ofício nº XXX/XXXX/XXX (SEI! nº XXXX).",
      exemplo=True),
    p("Por tratar-se de exame de admissibilidade, não houve a interrupção da "
      "prescrição, na forma do art. 142, §§ 1º e 3º, da Lei nº 8.112/90."),
    p("Eventual penalidade de advertência foi alcançada pela prescrição em "
      "XX/XX/XXXX.", exemplo=True),
    p("Por outro lado, as penalidades de suspensão ou demissão prescreverão "
      "somente em XX/XX/XXXX e XX/XX/XXXX, respectivamente.", exemplo=True),
)

ORIENTACAO_PRESCRICIONAL = (
    "Deve ser apresentado o cálculo da prescrição para cada uma das "
    "possíveis penalidades disciplinares. Não basta indicar apenas o "
    "resultado obtido, sendo imprescindível a menção às datas utilizadas no "
    "cálculo, bem como aos documentos que amparam tal conclusão, de modo a "
    "permitir a sindicabilidade da contagem.\n\n"
    "Caso a contagem do prazo prescricional perpasse pelo período "
    "compreendido entre 23/03/2020 e 21/07/2020, deve-se atentar para a "
    "suspensão dos prazos prescricionais em virtude da MPV 928/2020.\n\n"
    "Deve-se verificar se o fato em análise também configura ilícito penal. "
    "Em sendo assim, deve-se utilizar o prazo prescricional do crime "
    "correspondente ao ilícito disciplinar em tela, por inteligência do § 2º "
    "do art. 142 da Lei nº 8.112/90.\n\n"
    "Certificado o decurso do prazo prescricional, deve-se reconhecer a "
    "extinção da punibilidade do servidor. NÃO é possível oferecer Termo de "
    "Ajustamento de Conduta para condutas prescritas, conforme a Nota "
    "Técnica nº 1015/2022/CGUNE/CRG.\n\n"
    "A prescrição em perspectiva pode ser sugerida, desde que observados os "
    "parâmetros da Nota Técnica nº 1439/2020/CGUNE-CRG."
)

NORMA_PRESCRICIONAL = (
    "Art. 92. (…) IV - análise prescricional;\n\n"
    "Lei nº 8.112/90\n"
    "Art. 142. A ação disciplinar prescreverá:\n"
    "I - em 5 (cinco) anos, quanto às infrações puníveis com demissão, "
    "cassação de aposentadoria ou disponibilidade e destituição de cargo em "
    "comissão;\n"
    "II - em 2 (dois) anos, quanto à suspensão;\n"
    "III - em 180 (cento e oitenta) dias, quanto à advertência.\n"
    "§ 1º O prazo de prescrição começa a correr da data em que o fato se "
    "tornou conhecido.\n"
    "§ 2º Os prazos de prescrição previstos na lei penal aplicam-se às "
    "infrações disciplinares capituladas também como crime.\n"
    "§ 3º A abertura de sindicância ou a instauração de processo disciplinar "
    "interrompe a prescrição, até a decisão final proferida por autoridade "
    "competente."
)


# ─────────────────────────────────────────
#  5. EXAME DE ADMISSIBILIDADE E JUSTA CAUSA
# ─────────────────────────────────────────

ADMISSIBILIDADE = (
    p("No âmbito da Polícia Rodoviária Federal, a IPS está regulamentada "
      "pela Instrução Normativa PRF nº 127, de 09 de maio de 2024, cujo art. "
      "67 a define da seguinte forma:"),
    cita("Art. 67. No âmbito da PRF fica estabelecida a Investigação "
         "Preliminar Sumária (IPS), como procedimento investigativo de "
         "caráter preparatório, informal e não punitivo, de acesso restrito, "
         "que objetiva a coleta de elementos de informação para a análise "
         "acerca da existência de autoria e materialidade suficientes para a "
         "instauração de processo correcional acusatório."),
    p("Trata-se, portanto, de procedimento dispensável, com caráter "
      "eminentemente instrumental, que se volta, em primeiro plano, a "
      "permitir a análise adequada da justa causa para a instauração de "
      "eventual processo administrativo disciplinar."),
    p("Além disso, a regulamentação interna inclui a possibilidade de "
      "celebração do Termo de Ajustamento de Conduta - TAC, cujos requisitos "
      "objetivos envolvem a caracterização do ilícito disciplinar como de "
      "potencial menor ofensivo. Por conseguinte, também é necessário que a "
      "IPS angarie elementos aptos a, conforme o <i>standard probatório</i> "
      "característico da fase pré-processual, lastrear a realização do "
      "enquadramento e da dosimetria preliminares."),
    p("Vale consignar, ainda, que a autoridade disciplinar não está "
      "vinculada às conclusões apresentadas pelo encarregado da IPS, podendo "
      "adotar qualquer das decisões descritas no art. 73 da Instrução "
      "Normativa, a saber:"),
    cita("<b>Art. 73. A autoridade disciplinar competente não está vinculada "
         "ao opinativo da IPS, podendo motivadamente:</b>"),
    cita("I - proceder ao Juízo de Admissibilidade nos termos do art. 32;"),
    cita("II - suspender a investigação, na previsão do art. 72;"),
    cita("III - solicitar a realização de outras diligências; e"),
    cita("VI - decidir pela instauração de outro procedimento correcional "
         "cabível."),
    cita("§ 1º Na conclusão da IPS, verificando-se que o fato que ensejou "
         "infração disciplinar esteja capitulado como ilícito penal ou ato "
         "de improbidade, a autoridade competente, ao término do juízo de "
         "admissibilidade, encaminhará cópia dos autos ao Ministério "
         "Público, independentemente da imediata instauração do processo "
         "correcional acusatório."),
    cita("<u>§ 2º A depender da complexidade do tema disciplinar ou a "
         "critério do chefe da unidade de correição, poderá ser solicitada "
         "nova manifestação técnica por analista, com emissão de nova peça "
         "informativa, a fim de subsidiar o juízo de admissibilidade após a "
         "conclusão do procedimento investigativo.</u>"),
    cita("§ 3º Sendo constatados indícios da prática de atos ilícitos "
         "perpetrados por pessoas jurídicas contra a Administração Pública, "
         "a autoridade instauradora, ao término do juízo de admissibilidade, "
         "determinará a remessa de cópias do processo à autoridade "
         "competente, nos termos da legislação em vigor."),
    p("Feitas estas considerações, torna-se possível avançar sobre a "
      "Investigação em análise."),

    subtitulo("Dos indícios de autoria e de materialidade:"),
    p("As oitivas realizadas fornecem informações coesas, não existindo "
      "contradições internas ou externas que mereçam destaque, sobretudo no "
      "que diz respeito ao depoimento do Sr. Fulano de Tal e da Sra. Fulana "
      "de Tal, que ocupavam o veículo abordado pelo servidor e, em uníssono, "
      "indicam a entrega de quantia em dinheiro para que não fosse realizada "
      "a autuação.", exemplo=True),
    p("Neste mesmo sentido, as imagens do circuito de câmeras da Delegacia "
      "(SEI! nº XXXX) indicam que o veículo conduzido pelos depoentes foi "
      "realmente abordado pelo acusado, que estava sozinho na ocasião. As "
      "gravações evidenciam que os fatos ocorreram de forma coerente com a "
      "narrativa apresentada pelos abordados, sendo até mesmo possível "
      "observar o servidor guardando a quantia de R$ XX,XX no bolso da capa "
      "de seu colete balístico. Na sequência, verifica-se a liberação do "
      "veículo, sem que tenha sido feito qualquer registro da abordagem nos "
      "sistemas móveis, conforme consta da Parte Diária Informatizada (SEI! "
      "nº XXXX).", exemplo=True),
    p("Assim, verifica-se que há, em princípio, prova da materialidade e "
      "indícios suficientes de autoria, restando configurada a justa causa "
      "para a deflagração da persecução disciplinar.", exemplo=True),

    subtitulo("Do enquadramento preliminar:"),
    p("Na seara administrativa, a caracterização da conduta descrita no "
      "tipo-penal do art. 317, § 1º, incorre, simultaneamente, em violação à "
      "previsão do art. 117, inc. IX, c/c art. 132, inc. XIII, ambos da Lei "
      "nº 8.112/90. Para mais, perfaz hipótese de improbidade "
      "administrativa, trazendo à lume a violação ao art. 132, inc. IV, da "
      "Lei nº 8.112/90 c/c art. 9º, inc. X, da Lei nº 8.429/92. Por fim, não "
      "se pode olvidar a subsunção da conduta ao que consta do art. 132, "
      "inc. XI, da Lei nº 8.112/90.", exemplo=True),
    p("Haveria, ainda, de se falar na ocorrência de violação ao art. 132, "
      "inc. I, da Lei nº 8.112/90, porquanto a conduta também esteja "
      "capitulada como crime contra a Administração Pública, nos termos do "
      "art. 317 do Código Penal. Contudo, em se tratando deste enquadramento "
      "específico, por inteligência do Parecer vinculante AGU GQ-124, "
      "faz-se necessário aguardar o trânsito em julgado da ação penal "
      "correspondente, de modo que, por ora, deve ser afastado.",
      exemplo=True),
    p("Portanto, conclui-se que os fatos imputados ao investigado, em juízo "
      "de convicção sumária, se amoldam aos seguintes ilícitos "
      "disciplinares: art. 117, inc. IX, c/c art. 132, inc. XIII, ambos da "
      "Lei nº 8.112/90; art. 132, inc. IV, da Lei nº 8.112/90 c/c art. 9º, "
      "inc. X, da Lei nº 8.429/92; e art. 132, inc. XI, da Lei nº 8.112/90.",
      exemplo=True),

    subtitulo("Da dosimetria preliminar:"),
    p("<b>Exemplo 1 — ilícito do art. 132.</b> Em se tratando de ilícito "
      "contemplado no rol do art. 132 da Lei nº 8.112/90, não é dado à "
      "autoridade administrativa abrandar a reprimenda, que, por expressa "
      "determinação legal, há que ser a pena capital administrativa. É o que "
      "se extrai da Súmula nº 650 do STJ:", exemplo=True),
    cita("Súmula 650 — A autoridade administrativa não dispõe de "
         "discricionariedade para aplicar ao servidor pena diversa de "
         "demissão quando caracterizadas as hipóteses previstas no artigo "
         "132 da Lei 8.112/1990."),
    p("Portanto, em linha com o enquadramento preliminar acima, fica "
      "evidente que os indícios coligidos dão conta de prática grave, cujo "
      "preceito secundário excede em muito o máximo para a caracterização da "
      "infração de menor potencial ofensivo.", exemplo=True),
    p("<b>Exemplo 2 — demais casos.</b> A Controladoria-Geral da União "
      "disponibiliza a Calculadora de Viabilidade de TAC, que permite "
      "identificar, com maior grau de objetividade e sindicabilidade, se a "
      "infração em análise é de menor potencial ofensivo.", exemplo=True),
    p("Apesar disso, é certo que o resultado apresentado depende diretamente "
      "dos parâmetros inseridos pelo operador. Nesse esteio, cada uma das "
      "circunstâncias será fundamentada de maneira específica a seguir. Há "
      "que se reiterar, contudo, que o juízo a ser feito é de cognição "
      "sumária, lastreado tão somente nos elementos constantes dos autos, "
      "que ainda não foram submetidos ao crivo do contraditório e da ampla "
      "defesa.", exemplo=True),
    p("Nestes passos, conforme se verá a seguir, considera-se que a "
      "celebração do TAC é possível. Vejamos:", exemplo=True),
    alinea("<b>Natureza:</b> refere-se ao elemento subjetivo da conduta. No "
           "caso, vê-se que a conduta do servidor decorreu da inobservância "
           "do dever de cuidado que o cargo público lhe impõe. Não há, "
           "porém, elementos que indiquem que sua negligência foi superior "
           "àquela que é ínsita à violação de norma de natureza disciplinar "
           "na modalidade culposa, justificando a utilização do grau "
           "mínimo.", exemplo=True),
    alinea("<b>Gravidade:</b> deve ser avaliada conforme o grau de ofensa à "
           "norma, isto é, segundo o critério da lesividade. Ficou "
           "evidenciada a gravidade média da conduta, tendo em vista que ela "
           "acabou por afetar, a um só tempo, o direito do usuário do "
           "serviço público e a própria imagem institucional. Será fixado o "
           "grau 10.", exemplo=True),
    alinea("<b>Dano:</b> é avaliado conforme o grau da lesão ao bem jurídico "
           "protegido. Ficou devidamente comprovado que a conduta do "
           "servidor ensejou dano ao usuário do serviço público, o que "
           "permite a fixação do grau 10 (dano médio).", exemplo=True),
    alinea("<b>Agravantes:</b> não há.", exemplo=True),
    alinea("<b>Maus antecedentes:</b> correspondem às anotações que constam "
           "nos assentamentos do servidor, que podem evidenciar a falta de "
           "compromisso no desempenho das suas atividades. O servidor não "
           "ostenta maus antecedentes, pelo que será utilizado o grau "
           "mínimo.", exemplo=True),
    alinea("<b>Atenuantes:</b> não há.", exemplo=True),
    alinea("<b>Bons antecedentes:</b> correspondem às anotações que constam "
           "nos assentamentos do servidor, que podem demonstrar o grau da "
           "sua dedicação e comprometimento com o trabalho e com a "
           "instituição a que serve. Tendo em vista que o servidor possui XX "
           "elogios em seus assentamentos funcionais, sugere-se a utilização "
           "do grau X.", exemplo=True),

    subtitulo("Dos requisitos para o oferecimento de TAC:"),
    p("No microssistema correcional da Polícia Rodoviária Federal, o TAC "
      "está regulamentado no art. 41 e seguintes da Instrução Normativa PRF "
      "nº 127, de 09 de maio de 2024. Nesse esteio, verifica-se que os "
      "requisitos para sua celebração são os seguintes:"),
    alinea("não possuir registro vigente de penalidade disciplinar em seus "
           "assentamentos funcionais (art. 44, inc. I);"),
    alinea("não ter firmado TAC nos últimos dois anos, contados desde a "
           "publicação do instrumento anterior até a data do novo fato sob "
           "análise. Esta restrição não incide quando a infração ora em "
           "análise tiver sido cometida em momento prévio ao TAC celebrado "
           "(art. 44, inc. II e parágrafo único);"),
    alinea("haver ressarcido ou se comprometido a ressarcir, dentre as "
           "obrigações do TAC proposto, eventual dano causado à "
           "Administração Pública (art. 44, inc. III); e"),
    alinea("tratar-se de infração disciplinar punível com advertência ou "
           "suspensão de até 30 (trinta) dias — infração de menor potencial "
           "ofensivo, nos termos do art. 145, inc. II, da Lei nº 8.112/90, "
           "ou com penalidade similar, prevista em lei ou regulamento "
           "interno (art. 41, caput, e art. 42)."),
    p("No caso, conforme Certidão (SEI! nº XXXX), o servidor atende a todos "
      "os requisitos subjetivos acima — alíneas “a” e “b”. Além disso, a "
      "conduta não gerou prejuízo financeiro aferível à Administração "
      "Pública. Por fim, conforme a dosimetria preliminar realizada no item "
      "anterior, o ilícito supostamente perpetrado se enquadra aos limites "
      "descritos na alínea “d” acima.", exemplo=True),
    p("Portanto, estão presentes todos os requisitos normativos, devendo ser "
      "oferecido o TAC ao investigado.", exemplo=True),

    subtitulo("Da matriz de responsabilidade:"),
    tabela(["Fato", "Agente", "Elementos de convicção", "Elementos faltantes",
            "Possível tipificação"], linhas=2),
)

ORIENTACAO_ADMISSIBILIDADE = (
    "Este é o elemento mais longo, e já vem montado com o texto padrão da "
    "minuta: a citação do art. 67, as considerações sobre o caráter da IPS, "
    "a transcrição do art. 73 e os requisitos do TAC entram no documento "
    "como estão.\n\n"
    "Os trechos marcados como exemplo tratam de um caso fictício e só entram "
    "no documento depois de reescritos.\n\n"
    "INDÍCIOS DE AUTORIA E MATERIALIDADE — devem ser analisados os elementos "
    "de convicção angariados, especialmente com o escopo de verificar se "
    "amparam a hipótese que ensejou a instauração da Investigação. O "
    "standard probatório exigido neste momento NÃO é a certeza para além da "
    "dúvida razoável, razão pela qual deve-se adotar especial cautela com a "
    "linguagem empregada: ainda não foi oportunizado ao investigado o "
    "contraditório e a ampla defesa. Não existindo prova da materialidade ou "
    "indícios de autoria, não haverá justa causa, sendo o arquivamento "
    "medida que se impõe — avance direto para a Conclusão.\n\n"
    "ENQUADRAMENTO PRELIMINAR — indique a qual ilícito disciplinar a conduta "
    "se amolda, sobretudo ante a necessidade de identificar se é de menor "
    "potencial ofensivo. Não se admite o “overcharging”, isto é, a imputação "
    "de ilícito mais grave com o condão de obstar o oferecimento do TAC sem "
    "fundamentação idônea. Atente para a vedação ao bis in idem e para o "
    "concurso aparente entre infrações.\n\n"
    "DOSIMETRIA PRELIMINAR — há dois caminhos, e apenas um se aplica. Se o "
    "enquadramento constar do rol taxativo do art. 132 da Lei nº 8.112/90, a "
    "dosimetria fica prejudicada (Exemplo 1). Nos demais casos, faça a "
    "dosimetria preliminar (Exemplo 2), de preferência com a Calculadora de "
    "Viabilidade de TAC da CGU, em epad.cgu.gov.br. A mera reprodução do "
    "print da calculadora não satisfaz a "
    "necessidade de fundamentação: divida a fundamentação em itens e "
    "apresente o print ao final. A gravidade abstrata do ilícito não é "
    "motivação idônea para agravar a reprimenda.\n\n"
    "REQUISITOS DO TAC — sendo a infração de menor potencial ofensivo, pode "
    "sugerir o TAC, desde que atendidos os requisitos subjetivos; não sendo "
    "o caso, sugira a instauração de Sindicância Acusatória - SINAC. Se a "
    "infração NÃO for de menor potencial ofensivo, indique que o TAC é "
    "inviável e consigne eventuais descumprimentos dos demais requisitos.\n\n"
    "MATRIZ DE RESPONSABILIDADE — insira tantas linhas quantos forem os "
    "fatos objeto da investigação."
)

NORMA_ADMISSIBILIDADE = (
    "Art. 92. (…) V - exame de admissibilidade e, se for o caso, a indicação "
    "de justa causa para instauração do PAD, composta de:\n"
    "a) indícios de autoria e materialidade;\n"
    "b) enquadramento preliminar;\n"
    "c) dosimetria preliminar; e\n"
    "d) matriz de responsabilidade.\n\n"
    "Art. 67. No âmbito da PRF fica estabelecida a Investigação Preliminar "
    "Sumária (IPS), como procedimento investigativo de caráter preparatório, "
    "informal e não punitivo, de acesso restrito, que objetiva a coleta de "
    "elementos de informação para a análise acerca da existência de autoria "
    "e materialidade suficientes para a instauração de processo correcional "
    "acusatório.\n\n"
    "Art. 41. O Termo de Ajustamento de Conduta (TAC) é instrumento de "
    "resolução consensual de conflito, de natureza negocial, nos casos de "
    "infração disciplinar de menor potencial ofensivo.\n"
    "§ 2º Em todos os casos, a decisão da autoridade disciplinar que afastar "
    "a celebração de TAC deverá ser motivada, de forma a demonstrar os "
    "fundamentos de fato e de direito que a sustentam.\n\n"
    "Art. 42. Considera-se infração disciplinar de menor potencial ofensivo "
    "a conduta punível com advertência ou suspensão de até 30 (trinta) dias, "
    "nos termos do art. 145, inciso II, da Lei nº 8.112, de 11 de dezembro "
    "de 1990, ou com penalidade similar, prevista em lei ou regulamento "
    "interno.\n\n"
    "Art. 44. O TAC somente poderá ser celebrado quando o servidor "
    "interessado:\n"
    "I - não possuir registro vigente de penalidade disciplinar em seus "
    "assentamentos funcionais;\n"
    "II - não tiver firmado TAC nos últimos dois anos, contados desde a "
    "publicação do instrumento anterior até a data do novo fato sob análise; "
    "e\n"
    "III - tiver ressarcido ou se comprometido a ressarcir, dentre as "
    "obrigações do TAC proposto, eventual dano causado à Administração "
    "Pública.\n"
    "Parágrafo único. Não incide a restrição do inciso II quando a infração "
    "de menor potencial ofensivo tiver sido cometida em momento prévio ao "
    "TAC anteriormente celebrado."
)


# ─────────────────────────────────────────
#  6. CONCLUSÃO
# ─────────────────────────────────────────

CONCLUSAO = (
    p("Por todo o exposto, sugere-se:"),
    alinea("Prosseguir com a Investigação Preliminar Sumária - IPS em face "
           "do servidor <b>PRF FULANO DE TAL</b>, matrícula SIAPE nº XXXXXX, "
           "lotado em XXXX, especialmente para que sejam realizadas as "
           "diligências indicadas no item XXX;", exemplo=True),
    alinea("Instaurar Sindicância Patrimonial - SINPA em face do servidor "
           "<b>PRF FULANO DE TAL</b>, matrícula SIAPE nº XXXXXX, lotado em "
           "XXXX;", exemplo=True),
    alinea("Arquivar o procedimento investigativo em curso, em razão de "
           "XXXX;", exemplo=True),
    alinea("Propor ao servidor <b>PRF FULANO DE TAL</b>, matrícula SIAPE nº "
           "XXXXXX, lotado em XXXX, a celebração de Termo de Ajustamento de "
           "Conduta - TAC;", exemplo=True),
    alinea("Instaurar Sindicância Acusatória - SINAC em face do servidor "
           "<b>PRF FULANO DE TAL</b>, matrícula SIAPE nº XXXXXX, lotado em "
           "XXXX;", exemplo=True),
    alinea("Instaurar Processo Administrativo Disciplinar com Rito Sumário "
           "em face do servidor <b>PRF FULANO DE TAL</b>, matrícula SIAPE nº "
           "XXXXXX, lotado em XXXX;", exemplo=True),
    alinea("Instaurar Processo Administrativo Disciplinar em face do "
           "servidor <b>PRF FULANO DE TAL</b>, matrícula SIAPE nº XXXXXX, "
           "lotado em XXXX;", exemplo=True),
    alinea("Recomendar XXXX;", exemplo=True),
    alinea("Encaminhar XXXX.", exemplo=True),
)

ORIENTACAO_CONCLUSAO = (
    "As alíneas vêm todas como exemplo: mantenha apenas as que se aplicam ao "
    "caso e apague as demais. Em qualquer sugestão que envolva servidor, é "
    "necessário mencionar novamente o nome completo, a matrícula SIAPE e a "
    "lotação.\n\n"
    "PROSSEGUIR COM A IPS — quando não existirem elementos suficientes para "
    "a superação do standard probatório deste momento, ou para o "
    "enquadramento e a dosimetria preliminares, indique as novas diligências "
    "a empreender: quem deve ser ouvido, que documentos buscar.\n\n"
    "SINPA — quando existirem indícios de enriquecimento ilícito, inclusive "
    "de evolução patrimonial incompatível (art. 14 do Decreto nº 10.571/2020 "
    "e art. 75 e seguintes da IN 127).\n\n"
    "ARQUIVAR — indique a fundamentação, prezando pela técnica jurídica. "
    "Diferencie insuficiência de provas de prova de que o servidor não "
    "concorreu para o fato.\n\n"
    "TAC — presentes os requisitos do art. 41 e seguintes da IN 127.\n\n"
    "SINAC — art. 82 e seguintes da IN 127. Exige infração de menor "
    "potencial ofensivo cujo autor NÃO possa celebrar TAC por inobservância "
    "dos demais requisitos.\n\n"
    "PAD SUMÁRIO — acúmulo ilegal de cargos, inassiduidade habitual ou "
    "abandono de cargo (art. 85 e seguintes da IN 127).\n\n"
    "PAD — quando não couber nenhum dos desfechos anteriores (art. 87 e "
    "seguintes da IN 127).\n\n"
    "RECOMENDAR / ENCAMINHAR — quando o procedimento revelar necessidade de "
    "alterar um Manual ou procedimento interno, ou de remeter os autos a "
    "outra área ou órgão (MPF, CGU, Corregedoria-Geral)."
)

NORMA_CONCLUSAO = (
    "Art. 92. (…) VI - conclusão, com as sugestões previstas no art. 72.\n\n"
    "Art. 93. Na hipótese de sugestão de instauração de processo correcional "
    "acusatório, a Informação deverá conter na sua conclusão, de forma clara "
    "e concisa, a identificação do servidor nos seguintes termos: nome "
    "completo, matrícula, cargo e lotação.\n"
    "Parágrafo único. Nos casos de sugestão de instauração de PAD SUMÁRIO, a "
    "conclusão da Informação deverá conter, além dos requisitos do caput, a "
    "indicação precisa dos cargos objeto de acumulação ilegal, a indicação "
    "precisa do período de ausência intencional do servidor ao serviço "
    "superior a 30 (trinta) dias ou a indicação dos dias de falta ao serviço "
    "sem causa justificada, por período igual ou superior a 60 (sessenta) "
    "dias interpoladamente, durante o período de 12 (doze) meses, nos termos "
    "do art. 133 e art. 140 da Lei nº 8.112, de 1990.\n\n"
    "Art. 32. § 2º O juízo de admissibilidade será o ato administrativo por "
    "meio do qual a autoridade disciplinar decidirá, de forma fundamentada:\n"
    "I - pelo arquivamento do feito por falta de objeto (…);\n"
    "II - pela instauração de processo correcional acusatório, caso conclua "
    "pela existência de justa causa, com indícios mínimos de autoria e "
    "materialidade, além de viabilidade da aplicação de penalidades "
    "administrativas; ou\n"
    "III - pela celebração de TAC, se presentes seus requisitos."
)
