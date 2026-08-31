"""
Guias de uso das ferramentas — o "Como usar" de cada tela.

Um sistema de dez ferramentas tem um problema que não se resolve com boa
interface: quem abre a Varredura pela primeira vez não sabe se ela serve
ao caso que tem em mãos, nem por onde começar. A descrição do portal
responde *o que é*; aqui se responde *para que serve, quando serve, e o
que fazer primeiro*.

Cada guia tem quatro partes, nesta ordem, porque é a ordem em que as
perguntas aparecem:

* **finalidade** — o problema concreto que a ferramenta resolve;
* **quando** — as situações em que se recorre a ela;
* **passos** — o caminho na tela, com os nomes dos botões como eles
  estão escritos;
* **limites** — o que ela não faz, e o que exige cuidado.

Os limites não são rodapé: uma ferramenta correcional que promete mais
do que entrega produz peça que não se sustenta. Onde há ressalva, ela
está aqui pelo mesmo motivo que está impressa no termo.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from .icons import draw_icon
from .theme import PALETTE
from .widgets import fit_to_screen, hsep


@dataclass(frozen=True)
class Guia:
    """O texto de ajuda de uma ferramenta."""

    finalidade: str
    quando: tuple[str, ...] = ()
    passos: tuple[str, ...] = ()
    limites: tuple[str, ...] = ()


# ─────────────────────────────────────────
#  OS GUIAS
# ─────────────────────────────────────────

GUIAS: dict[str, Guia] = {

    # ── vértice: o procedimento ───────────
    "ips": Guia(
        finalidade=(
            "Monta a Informação de Juízo de Admissibilidade — a peça que o "
            "encarregado assina para dizer se um fato comunicado merece ou "
            "não apuração formal. É o documento que abre, ou encerra, o "
            "procedimento correcional.\n\n"
            "O trabalho de fato não é escrever: é não deixar nada de fora. "
            "A Informação tem seis partes obrigatórias e cada uma responde "
            "a uma exigência da IN 127. A ferramenta guarda esse roteiro "
            "pronto, com a orientação e o texto padrão de cada item, e "
            "numera tudo sozinha conforme se preenche."),
        quando=(
            "Chegou uma denúncia, representação ou comunicação de "
            "irregularidade e é preciso decidir sobre a admissibilidade.",
            "A peça precisa sair no formato que o SEI aceita, com a "
            "numeração dos itens correta.",
            "Uma Informação começada precisa ser retomada dias depois, do "
            "ponto em que parou.",
        ),
        passos=(
            "Clique em <b>Nova Informação</b> e dê um nome que você "
            "reconheça depois — costuma ser o número do processo.",
            "Percorra as etapas pela lista da esquerda. Cada uma traz, no "
            "alto, o que aquele item precisa conter; onde a IN 127 tem "
            "texto próprio, ele já vem escrito.",
            "Escreva em cada bloco. Os botões ao lado do campo inserem "
            "<b>Parágrafo</b>, <b>Tabela</b> e imagens; a numeração dos "
            "itens se refaz sozinha.",
            "Use <b>O que diz a norma</b> sempre que a exigência do item "
            "não estiver clara.",
            "Marque cada parte como concluída ao terminá-la, para "
            "enxergar o que falta.",
            "Confira em <b>Ver prévia da Informação</b> e exporte com "
            "<b>Exportar HTML para o SEI</b> — ou em PDF, se for para "
            "circular fora dos autos.",
        ),
        limites=(
            "O trabalho fica gravado neste computador, e não no SEI. "
            "Terminada a peça, exporte e junte aos autos.",
            "O roteiro e os textos padrão seguem a IN 127. Norma nova pede "
            "conferência antes de reaproveitar a peça.",
        ),
    ),

    # ── identificação e captura da prova ──
    "metadados": Guia(
        finalidade=(
            "Faz duas coisas que sempre andaram juntas: calcula o SHA-256 "
            "de cada arquivo — o número que o identifica e permite provar, "
            "depois, que a cópia juntada é a mesma que se recebeu — e lê o "
            "que o arquivo informa sobre si mesmo.\n\n"
            "Esse segundo ponto costuma valer tanto quanto o conteúdo. Uma "
            "fotografia anexada aos autos diz o modelo do aparelho, o "
            "instante da captura e, quando o celular gravou, as "
            "coordenadas do lugar. Um documento do Word guarda o nome de "
            "quem o editou por último, mesmo depois de o texto ter sido "
            "todo reescrito."),
        quando=(
            "Vai juntar arquivos aos autos e precisa do termo de juntada "
            "com os hashes.",
            "Quer saber quando, com que aparelho e por quem um arquivo foi "
            "produzido.",
            "Desconfia que a data alegada para uma foto ou documento não é "
            "a verdadeira.",
            "Precisa saber onde uma fotografia foi tirada.",
        ),
        passos=(
            "Clique em <b>Abrir arquivos…</b> e escolha um ou vários. "
            "Cada um é lido e resumido criptograficamente.",
            "Escolha na barra do alto quanto de metadado quer no "
            "documento: <b>Só hash</b>, <b>Relevantes</b> ou "
            "<b>Completo</b>.",
            "Percorra a lista da esquerda para ver o que cada arquivo "
            "revelou. O que interessa à apuração sai destacado, e "
            "coordenadas geográficas saem em vermelho.",
            "Preencha o nº SEI de cada arquivo, se já os tiver juntado.",
            "Para ir além do que o arquivo declara, escolha o modo "
            "<b>Avançado</b>: ele procura fluxos alternativos do sistema de "
            "arquivos — inclusive a marca que guarda o endereço de onde o "
            "arquivo foi baixado —, revisões anteriores preservadas dentro "
            "do documento, propriedades que o programa de edição não "
            "mostra, e dados anexados depois do fim do formato.",
            "Clique em <b>Gerar termo</b>, complete a abertura e salve em "
            "PDF ou HTML.",
        ),
        limites=(
            "O exame avançado constata a existência do que encontra, mas "
            "não recupera o conteúdo: ele diz que há uma revisão anterior "
            "dentro do documento, não a extrai. Extração é perícia.",
            "A ausência de achados no exame avançado não prova que o "
            "arquivo não foi alterado — prova apenas que as marcas "
            "procuradas não estavam lá.",
            "Metadado é informação declarada pelo programa que gravou o "
            "arquivo, e pode ser editado. Serve de indício, não de prova "
            "cabal por si só.",
            "Nem todo arquivo traz metadado: quem envia foto por aplicativo "
            "de mensagem costuma recebê-la já sem EXIF.",
            "A leitura é passiva — o arquivo é aberto somente para leitura "
            "e nunca reescrito.",
        ),
    ),

    "constatacao": Guia(
        finalidade=(
            "Registra conteúdo publicado na internet de modo que sirva aos "
            "autos. Uma captura de tela não serve: não prova quando foi "
            "feita, nem de que endereço veio, e some se a página for "
            "apagada no dia seguinte.\n\n"
            "Aqui a página é aberta num navegador embutido e, no momento da "
            "captura, guarda-se o que a torna verificável: o endereço, o "
            "que o servidor respondeu, o certificado do site com quem o "
            "emitiu e para quem, o endereço de rede consultado "
            "independentemente, a imagem da página inteira, o texto e o "
            "código-fonte — cada peça com seu SHA-256."),
        quando=(
            "Uma publicação em rede social, notícia ou página oficial é "
            "objeto ou prova da apuração.",
            "O conteúdo pode ser apagado ou editado, e precisa ficar "
            "registrado como estava.",
            "É preciso demonstrar que o conteúdo estava naquele endereço, "
            "naquele momento.",
        ),
        passos=(
            "Digite o endereço na barra e navegue até a página exata — "
            "role até o trecho que interessa, aceite o que precisar "
            "aceitar, entre na conta se o conteúdo exigir.",
            "Clique em <b>Capturar esta página</b>. A captura é do que "
            "está na tela naquele instante.",
            "Marque a opção de conteúdo restrito se ele só era visível "
            "após login — isso fica declarado no termo.",
            "Confira as peças capturadas na lista e clique em <b>Gerar "
            "termo</b>.",
            "Use <b>Salvar peças (ZIP)</b> para guardar os arquivos "
            "originais da captura, com índice e hashes.",
        ),
        limites=(
            "Esta é a única ferramenta do sistema que acessa a internet. "
            "O endereço visitado sai desta máquina.",
            "O registro prova o que estava publicado naquele endereço "
            "naquele momento, e não a veracidade do que ali se afirma.",
            "Conteúdo atrás de login é capturado como você o vê, com a sua "
            "sessão. O termo registra essa circunstância porque ela é "
            "relevante para quem for avaliar a peça.",
            "<b>Vídeo não toca aqui.</b> O navegador embutido não traz os "
            "formatos H.264 e AAC, usados por Instagram, TikTok e pela "
            "maior parte do vídeo na web. A página, o texto, a legenda e a "
            "imagem são registrados normalmente; o vídeo em movimento, "
            "não. Para registrá-lo, reproduza-o no navegador do sistema e "
            "grave com a <b>Gravação de Tela</b> — as duas peças se "
            "complementam nos autos.",
            "Não há carimbo de tempo de terceiro: a data é a do "
            "computador. Para conteúdo que se pretenda contestar, vale "
            "considerar ata notarial.",
        ),
    ),

    # ── extração de conteúdo do material ──
    "varredura": Guia(
        finalidade=(
            "Resolve o problema do dispositivo apreendido: um pendrive, um "
            "cartão de memória ou uma pasta com milhares de arquivos, dos "
            "quais não se sabe o que interessa até encontrar. Abrir um por "
            "um é inviável.\n\n"
            "A varredura percorre tudo uma vez, calcula o SHA-256 de cada "
            "arquivo, extrai o texto que houver — inclusive de páginas "
            "digitalizadas, por reconhecimento óptico — e monta um índice "
            "de busca. Dali em diante a procura é instantânea e não toca "
            "mais no dispositivo, que pode ser devolvido ou lacrado."),
        quando=(
            "Um dispositivo foi apreendido ou entregue e é preciso saber o "
            "que há dentro.",
            "Você procura uma palavra, um nome ou um valor e não sabe em "
            "qual dos arquivos ele está.",
            "Quer ver todas as fotografias de um acervo, ou só as que "
            "trazem coordenadas geográficas.",
            "Precisa demonstrar que o conjunto examinado não foi alterado.",
        ),
        passos=(
            "Clique em <b>Nova varredura…</b> e escolha a pasta ou a "
            "unidade. Leia o aviso: se o material é objeto de apuração, "
            "marque <b>Origem em somente leitura</b>.",
            "Escolha onde gravar o índice. Ele é um arquivo só, que você "
            "reabre depois em <b>Abrir índice existente…</b>.",
            "Espere a indexação. Ela lê tudo uma vez; a partir daí a busca "
            "é imediata.",
            "Digite na linha de busca. Acento e maiúscula não importam — "
            "<i>veiculo</i> acha <i>veículo</i>. Use aspas para expressão "
            "exata, asterisco para prefixo, e <b>E</b>, <b>OU</b> e "
            "<b>NÃO</b> para combinar termos.",
            "Recorte o resultado pelos filtros da esquerda: natureza do "
            "arquivo, só o que tem texto, só o que veio de OCR, só o que "
            "traz coordenadas.",
            "As abas do alto mostram o mesmo acervo por outros ângulos: "
            "<b>Galeria</b>, <b>Duplicatas</b> e <b>Panorama</b>.",
            "Quando uma busca for relevante, clique em <b>Registrar no "
            "termo</b>. Marque os arquivos que vão aos autos com "
            "<b>Destacar para juntada</b> e gere o termo no rodapé.",
        ),
        limites=(
            "Alcança apenas os arquivos existentes e acessíveis. Não "
            "recupera arquivo apagado, não lê espaço não alocado, não abre "
            "contêiner cifrado e não examina o interior de arquivos "
            "compactados.",
            "É triagem, não perícia. Para exame pericial de mídia existe "
            "ferramenta própria — o IPED, da Polícia Federal, é gratuito.",
            "Montar um dispositivo no Windows pode alterá-lo: o sistema "
            "cria pastas próprias e a indexação do Explorer escreve nele. "
            "Em material que é objeto de apuração, use bloqueador de "
            "escrita ou trabalhe sobre cópia.",
        ),
    ),

    "ocrpdf": Guia(
        finalidade=(
            "Um PDF escaneado é uma pilha de fotografias de papel. Abre, "
            "imprime e vai aos autos como qualquer outro — mas não se pode "
            "procurar nada dentro dele, nem copiar um trecho para a peça, "
            "nem encontrá-lo pela Varredura.\n\n"
            "Esta ferramenta acrescenta a esse arquivo uma camada de texto "
            "invisível, encaixada palavra por palavra sobre a imagem. O "
            "documento continua idêntico ao original — mesma imagem, mesma "
            "qualidade —, mas passa a permitir busca, seleção e cópia."),
        quando=(
            "Um documento digitalizado precisa ser pesquisado, e é grande "
            "demais para se ler à procura de um trecho.",
            "Você quer copiar um parágrafo do escaneado para dentro da "
            "peça, sem redigitar.",
            "Um lote de digitalizações vai ser indexado pela Varredura e "
            "precisa ficar achável.",
            "Uma fotografia de documento precisa virar PDF pesquisável.",
        ),
        passos=(
            "Clique em <b>Adicionar arquivos…</b>, ou em <b>Adicionar "
            "pasta…</b> para o lote inteiro. Aceita PDF e imagem.",
            "Deixe <b>Só as páginas sem texto</b> marcado: páginas que já "
            "são digitais ficam como estão.",
            "Clique em <b>Reconhecer</b> e acompanhe o andamento página a "
            "página.",
            "Confira o resultado com <b>Ver texto reconhecido</b> antes de "
            "juntar aos autos.",
            "Gere o termo, que registra o hash do arquivo recebido e o do "
            "gerado.",
        ),
        limites=(
            "O reconhecimento é automático e erra — sobretudo em "
            "manuscrito, carimbo, documento de má qualidade e algarismo. "
            "Por isso a camada é invisível e fica atrás da imagem: quem lê "
            "continua lendo o original. Divergência resolve-se sempre em "
            "favor da imagem.",
            "Não achar um termo na busca não permite concluir que ele não "
            "está no documento.",
            "O arquivo recebido nunca é sobrescrito: o pesquisável sai em "
            "arquivo novo, ao lado.",
        ),
    ),

    "transcricao": Guia(
        finalidade=(
            "Transcreve o que foi dito num áudio ou vídeo e separa quem "
            "falou. Uma oitiva de uma hora leva um dia para ser degravada à "
            "mão, e é trabalho que ninguém quer fazer duas vezes.\n\n"
            "O reconhecimento de voz identifica os interlocutores sozinho, "
            "pela voz, e amarra cada frase a quem a disse, na ordem "
            "cronológica. Você depois dá nome a cada locutor."),
        quando=(
            "Uma oitiva, interrogatório ou reunião gravada precisa virar "
            "texto para os autos.",
            "Um áudio de aplicativo de mensagem é prova e precisa ser "
            "degravado.",
            "É preciso localizar um trecho específico numa gravação longa.",
        ),
        passos=(
            "Clique em <b>Abrir mídia…</b> e escolha o áudio ou o vídeo.",
            "Clique em <b>Transcrever</b>. Na primeira vez o programa baixa "
            "os modelos de reconhecimento; depois disso funciona sem "
            "internet.",
            "Espere. A transcrição roda nesta máquina e leva tempo "
            "proporcional à duração da gravação.",
            "Dê nome a cada locutor — <i>Declarante</i>, <i>Encarregado</i> "
            "— no lugar de <i>Locutor 1</i> e <i>Locutor 2</i>.",
            "Corrija o texto onde for preciso e gere o termo de degravação.",
        ),
        limites=(
            "O reconhecimento erra em áudio ruim, em fala sobreposta e em "
            "termo técnico ou nome próprio. Confira ouvindo antes de "
            "assinar.",
            "A separação dos interlocutores é por semelhança de voz. Vozes "
            "parecidas podem ser confundidas, e quem fala pouco pode não "
            "ganhar locutor próprio.",
            "A degravação é auxiliar: prevalece a gravação, que deve "
            "acompanhar os autos.",
            "Tudo é processado nesta máquina. O áudio não sai daqui.",
        ),
    ),

    "extracao": Guia(
        finalidade=(
            "Documenta a extração de dados feita em sistema interno, no "
            "momento em que ela acontece. É a ferramenta de quem **atende** "
            "ao pedido de auditoria, não de quem o formula.\n\n"
            "O problema que ela resolve: a corregedoria pede à área de "
            "tecnologia os registros de um sistema, a área extrai e envia "
            "pelo processo, e o servidor apurado contesta a cadeia de "
            "custódia. O resumo criptográfico prova que o arquivo não mudou "
            "depois — mas não diz de onde saiu nem com que consulta. Aqui, "
            "cada passo fica registrado, e o arquivo recebido é resumido no "
            "instante em que chega, antes de tocar qualquer pasta de "
            "trabalho."),
        quando=(
            "A área de tecnologia vai extrair dados a pedido da "
            "corregedoria e a origem precisa ficar demonstrada.",
            "Uma consulta em sistema interno vai fundamentar peça e pode "
            "ser contestada.",
            "É preciso demonstrar quais foram exatamente os parâmetros da "
            "consulta que produziu determinado arquivo.",
        ),
        passos=(
            "Preencha <b>Processo</b>, <b>Solicitação atendida</b>, "
            "<b>Operador</b>, <b>Sistema</b> e <b>Objeto da extração</b>. "
            "Sistema e objeto são obrigatórios: são eles que dizem, no "
            "termo, o que se foi buscar e onde.",
            "Deixe <b>Gravar a tela junto</b> marcado — o termo cruza o "
            "vídeo com a relação dos atos pelo tempo decorrido.",
            "Clique em <b>Iniciar diligência</b>. A partir daí tudo é "
            "registrado, e você vê na linha do tempo à direita o que está "
            "sendo anotado a seu respeito.",
            "Digite o endereço do sistema e clique em <b>Abrir</b>. "
            "Autentique-se normalmente — campo de senha nunca é registrado.",
            "Faça a consulta. O clique, o formulário submetido e seus "
            "parâmetros entram na linha do tempo sozinhos.",
            "Baixe o arquivo pelo próprio sistema. Ele é gravado na pasta "
            "da diligência e resumido em SHA-256 ao chegar.",
            "Use <b>Anotar</b> para registrar o que a tela não mostra — o "
            "total conferido, uma observação sobre o resultado.",
            "Clique em <b>Encerrar diligência</b> e depois em <b>Gerar "
            "termo</b>.",
        ),
        limites=(
            "O registro alcança os passos desta sessão e o que foi "
            "recebido em resposta. Não alcança o funcionamento interno do "
            "sistema consultado nem a correção dos dados que ele mantém.",
            "O resumo criptográfico atesta que o arquivo juntado é o mesmo "
            "que foi recebido — não atesta que o conteúdo extraído esteja "
            "correto ou completo.",
            "Campo de senha não é registrado, e valor de parâmetro de "
            "endereço cujo nome indique credencial sai como “[suprimido]”. "
            "Os demais campos, inclusive os ocultos, constam por serem os "
            "parâmetros da consulta.",
            "O navegador embutido é um Chromium sem extensões. Sistema que "
            "exija componente próprio, certificado em máquina ou navegador "
            "homologado pode não abrir aqui — nesse caso, use a Gravação "
            "de Tela.",
            "As datas e horas são as do relógio da estação, não atestadas "
            "por terceiro.",
        ),
    ),

    "espelhamento": Guia(
        finalidade=(
            "Liga um celular Android por cabo, mostra a tela dele no "
            "computador e grava a sessão inteira, com o aparelho "
            "identificado no termo — fabricante, modelo, versão do Android "
            "e número de série, lidos do próprio dispositivo.\n\n"
            "Serve à diligência em que alguém **exibe** o aparelho: o "
            "denunciante que mostra as conversas, a demonstração de como um "
            "aplicativo se comporta, o registro que o detentor apresenta. "
            "Filmar a tela do celular com uma câmera resolve mal — fica "
            "ilegível, treme, e não identifica o aparelho."),
        quando=(
            "Alguém apresenta espontaneamente o próprio celular e o que "
            "está nele precisa ir aos autos.",
            "É preciso demonstrar o comportamento de um aplicativo.",
            "Um registro exibido na tela do aparelho precisa ser "
            "documentado com identificação do dispositivo.",
        ),
        passos=(
            "Peça a quem detém o aparelho que o destrave e habilite a "
            "depuração USB, em Configurações › Opções do desenvolvedor. "
            "Sem isso nada funciona.",
            "Ligue o cabo e clique em <b>Procurar aparelho</b>. Se aparecer "
            "“aguardando autorização”, o celular está mostrando um aviso de "
            "confiança — peça que toque em Permitir e procure de novo.",
            "Preencha <b>Processo</b>, <b>Operador</b> e <b>Objeto da "
            "diligência</b>.",
            "Deixe <b>Somente observar</b> marcado. Assim o computador "
            "mostra a tela mas não toca nem digita no aparelho — quem opera "
            "o celular é o dono dele.",
            "Clique em <b>Iniciar espelhamento</b> e escolha onde gravar. A "
            "tela do celular aparece em janela própria, ao lado.",
            "Conduza a diligência. Ao terminar, clique em <b>Encerrar "
            "espelhamento</b> — o sistema aplica a faixa de identificação e "
            "calcula o SHA-256, o que leva algum tempo.",
            "Clique em <b>Gerar termo</b> e informe quem apresentou o "
            "aparelho e a que título.",
        ),
        limites=(
            "<b>Não serve para celular apreendido e bloqueado.</b> O método "
            "exige aparelho destravado e depuração habilitada por quem tem "
            "a senha. Exame de dispositivo bloqueado é perícia, e tem "
            "ferramenta própria.",
            "O método <b>altera o aparelho</b>, em três pontos que o termo "
            "declara: habilitar a depuração é mudança de configuração; "
            "autorizar a estação grava a chave do computador no celular; e "
            "o espelhamento envia ao aparelho um componente que roda "
            "enquanto dura a sessão.",
            "Só Android, versão 5.0 ou mais recente. O áudio exige Android "
            "11. Não funciona com iPhone — não há caminho aberto e "
            "confiável para isso no Windows.",
            "O registro alcança o que foi exibido na tela. Não alcança o "
            "que está guardado no aparelho e não foi mostrado, nem dado "
            "apagado, nem área protegida.",
            "Desmarcar “Somente observar” permite operar o celular pelo "
            "computador. Operar o telefone de outra pessoa é ato diverso de "
            "observar o que ela exibe — e o termo registra que o controle "
            "esteve habilitado.",
        ),
    ),

    "gravacao": Guia(
        finalidade=(
            "Registra em vídeo o que se faz no computador, com a "
            "identificação do processo, do operador e da estação impressa "
            "no próprio quadro, junto ao relógio e ao tempo decorrido.\n\n"
            "O uso que a motivou é a extração de dados em sistema interno: "
            "quando a corregedoria pede à área de tecnologia registros de "
            "auditoria e o servidor apurado contesta a cadeia de custódia, "
            "o hash do arquivo prova que ele não mudou, mas não mostra de "
            "onde saiu. O vídeo da extração mostra o sistema, a consulta, "
            "os parâmetros e o momento em que o arquivo foi gerado."),
        quando=(
            "A área de tecnologia vai extrair dados de um sistema a pedido "
            "da corregedoria, e a origem precisa ficar documentada.",
            "Uma consulta em sistema que não guarda comprovante precisa "
            "ser registrada.",
            "Uma diligência feita no computador — conferência, "
            "verificação, coleta — precisa acompanhar os autos.",
        ),
        passos=(
            "Preencha o <b>Número do processo</b>, o <b>Operador</b> e o "
            "<b>Objeto da diligência</b>. Os três saem no vídeo e no termo.",
            "Escolha a <b>Área</b> — a área de trabalho inteira é a opção "
            "mais segura, porque não deixa de fora o que estava no outro "
            "monitor.",
            "Se for narrar o que está fazendo, escolha o microfone em "
            "<b>Narração pelo microfone</b>.",
            "Clique em <b>Iniciar gravação</b> e escolha onde gravar. A "
            "janela do sistema é recolhida e fica um painel pequeno, sobre "
            "tudo, com o tempo decorrido — arraste-o se atrapalhar.",
            "Faça a diligência normalmente. Diga em voz alta o que está "
            "fazendo, se houver microfone: narração vale mais que legenda.",
            "Clique em <b>Encerrar</b> no painel. O sistema calcula o "
            "SHA-256 do vídeo e o acrescenta à lista.",
            "Clique em <b>Gerar termo</b>, complete a qualificação de quem "
            "assina e salve em PDF ou HTML.",
        ),
        limites=(
            "A faixa impressa no vídeo é para leitura, não é prova: são "
            "pixels, e qualquer um monta um vídeo com uma tarja dizendo o "
            "que quiser. O que permite aferir o arquivo é o SHA-256 do "
            "termo.",
            "A hora exibida é a do relógio da estação, não atestada por "
            "terceiro. Onde a precisão temporal for controvertida, cabe "
            "carimbo do tempo de autoridade credenciada.",
            "O registro alcança o que estava na área capturada, no período "
            "gravado. Não alcança o que ficou fora do quadro nem o que "
            "acontecia dentro dos sistemas.",
            "Com a opção “Resistir a interrupção”, uma queda de energia "
            "custa os últimos dez a quinze segundos em vez do registro "
            "inteiro — mas o arquivo fica cerca de três vezes maior.",
            "A tela pode exibir dados pessoais de terceiros. Confira o "
            "vídeo antes de juntá-lo, e use a Tarja Preta no que precisar "
            "ser preservado.",
        ),
    ),

    # ── preparo e apoio ───────────────────
    "tarja": Guia(
        finalidade=(
            "Oculta dado pessoal e sigiloso em PDF de forma irreversível. "
            "É diferente de desenhar um retângulo preto por cima: naquele "
            "caso o texto continua no arquivo, e quem selecionar e copiar a "
            "área lê tudo o que se pretendia esconder.\n\n"
            "Aqui a página é rasterizada ao salvar. O texto sob a tarja "
            "deixa de existir no arquivo — não fica apenas coberto."),
        quando=(
            "Uma peça vai ser dada a vista, ou juntada a processo que "
            "outros acessam, e contém CPF, endereço, dado bancário ou nome "
            "de terceiro não envolvido.",
            "É preciso preservar a identidade de quem denunciou.",
            "Um documento sigiloso precisa circular em versão pública.",
        ),
        passos=(
            "Clique em <b>Abrir PDF…</b>.",
            "Arraste o mouse sobre o que deve ser ocultado. "
            "<b>Desfazer última tarja</b> corrige o erro; Ctrl+Z também.",
            "Para muitas ocorrências do mesmo dado, use <b>Buscar e "
            "tarjar</b>: digite o termo e todas as ocorrências são "
            "marcadas de uma vez.",
            "Se o documento veio com trechos entre colchetes, "
            "<b>Pré-visualizar termos</b> mostra quantos são e "
            "<b>Tarjar conteúdo entre [ ]</b> marca todos.",
            "Confira página por página antes de salvar.",
            "Clique em <b>Salvar PDF tarjado</b>. O original permanece "
            "intacto.",
        ),
        limites=(
            "A rasterização torna o documento gerado uma imagem: ele deixa "
            "de ser pesquisável. É o preço de a tarja ser irreversível.",
            "Confira o resultado antes de entregar. O que não foi marcado "
            "continua legível.",
            "Metadados do PDF não são tarjados. Se houver dado sensível "
            "neles, verifique em Metadados e Hash.",
        ),
    ),

    "antiinj": Guia(
        finalidade=(
            "Procura, num PDF, texto que existe no arquivo mas não aparece "
            "para quem lê: letra de opacidade zero, corpo minúsculo, branco "
            "sobre branco, conteúdo fora da área da página e camadas "
            "ocultas.\n\n"
            "O uso que interessa à corregedoria é a tentativa de induzir a "
            "erro quem examina o documento — inclusive instruções "
            "escondidas dirigidas a sistemas automatizados de triagem. "
            "Serve também para achar dado sigiloso que ficou no arquivo "
            "sem que ninguém percebesse."),
        quando=(
            "Recebeu um PDF de origem externa que vai fundamentar decisão.",
            "Há suspeita de que o documento foi preparado para ser lido de "
            "um jeito por pessoas e de outro por máquinas.",
            "Antes de juntar aos autos um documento cuja procedência não é "
            "conhecida.",
        ),
        passos=(
            "Clique em <b>Abrir PDF…</b>. A varredura é automática.",
            "Percorra os achados na lista da esquerda; cada um mostra a "
            "página e o motivo pelo qual o texto é invisível.",
            "Se houver achado relevante, clique em <b>Relatório de "
            "constatação</b> e salve em PDF ou HTML.",
        ),
        limites=(
            "Nem todo texto invisível é má-fé: marca d'água, camada de OCR "
            "e resíduo de diagramação aparecem aqui e são legítimos. O "
            "achado é ponto de partida, não conclusão.",
            "A ausência de achado não garante que o documento seja íntegro.",
        ),
    ),

    "quadro": Guia(
        finalidade=(
            "Mural livre para enxergar a apuração antes de redigir. "
            "Anotações, imagens e marcações ligadas por vínculos, do jeito "
            "que se faria numa parede com alfinete e barbante.\n\n"
            "Serve para o momento em que há muita informação solta e "
            "nenhuma clareza sobre como as peças se conectam — quem "
            "conhece quem, o que veio antes do quê, qual prova sustenta "
            "qual afirmação."),
        quando=(
            "A apuração envolve várias pessoas e é preciso mapear as "
            "relações entre elas.",
            "Há uma cronologia a montar a partir de fatos esparsos.",
            "Antes de escrever a peça, para organizar o raciocínio.",
        ),
        passos=(
            "Clique em <b>Novo caso</b> e dê um nome.",
            "Escolha a ferramenta na barra: <b>Nota</b> (N) para anotação, "
            "<b>Imagem</b> (I) para print ou fotografia, <b>Marcação</b> "
            "(M) para destacar uma área.",
            "Duplo clique numa anotação para escrever dentro dela.",
            "Com <b>Conectar</b> (C), clique num item e depois no outro "
            "para criar o vínculo.",
            "Navegue com <b>Mover</b> (H, ou segure a barra de espaço) e "
            "<b>Enquadrar</b> (F) para ver tudo.",
            "Use <b>Exportar quadro</b> para levar a imagem do mural para "
            "a peça ou para a reunião.",
        ),
        limites=(
            "O quadro é instrumento de trabalho, não peça dos autos. O que "
            "for concluído dele precisa ser escrito e fundamentado.",
            "Os casos ficam gravados neste computador.",
        ),
    ),

    "video": Guia(
        finalidade=(
            "Prepara gravação para a juntada. Vídeo de videomonitoramento e "
            "de câmera operacional portátil chega em arquivo grande demais "
            "para o SEI, muitas vezes partido em pedaços de poucos "
            "minutos, e com horas de nada em volta do trecho que "
            "interessa.\n\n"
            "A ferramenta reduz o tamanho preservando a legibilidade da "
            "cena, recorta o trecho relevante e junta gravações "
            "fragmentadas num arquivo só."),
        quando=(
            "O vídeo excede o tamanho que o sistema de processo aceita.",
            "Só um trecho de uma gravação longa interessa à apuração.",
            "A gravação veio partida em vários arquivos sequenciais.",
        ),
        passos=(
            "Clique em <b>Adicionar vídeos…</b>. A lista mostra duração, "
            "resolução, codec e tamanho de cada um.",
            "Escolha o modo no alto: <b>Compactar</b>, <b>Fatiar</b> ou "
            "<b>Mesclar</b>.",
            "Em <b>Fatiar</b>, marque o início e o fim do trecho. Em "
            "<b>Mesclar</b>, ordene os arquivos com <b>Subir</b> e "
            "<b>Descer</b> — a ordem da lista é a ordem do resultado.",
            "Clique em <b>Processar</b> e escolha onde gravar.",
        ),
        limites=(
            "Compactar é conversão com perda: a imagem gerada tem menos "
            "qualidade que a original. Guarde a gravação recebida como "
            "está e junte a versão reduzida.",
            "Mesclar exige arquivos compatíveis entre si. Gravações de "
            "câmeras diferentes podem precisar ser convertidas antes.",
            "Recorte muda a duração e desloca as marcas de tempo. Se a "
            "hora da cena importa, registre-a no termo.",
        ),
    ),

    "conversa": Guia(
        finalidade=(
            "Reconstrói uma conversa a partir do arquivo que o próprio "
            "aplicativo exporta — o texto, ou o pacote com as mídias — e a "
            "identifica pelo resumo criptográfico desse arquivo. A "
            "corregedoria costuma receber a conversa já exportada; abri-la "
            "no Bloco de Notas resolve o prático e destrói o jurídico, "
            "porque ao fim existe um texto e não existe como demonstrar que "
            "ele corresponde ao arquivo recebido.\n\n"
            "A peça que sai daqui atesta uma coisa só, e por isso se "
            "sustenta: que a reconstrução corresponde àquele arquivo, com "
            "aquele resumo. Não atesta a autenticidade nem a completude da "
            "conversa original — e diz isso com todas as letras."),
        quando=(
            "Chegou uma exportação de conversa (WhatsApp, em texto ou no "
            "pacote .zip) e é preciso juntá-la aos autos de forma "
            "conferível.",
            "Interessa registrar quem falou, quando, e com qual resumo "
            "criptográfico de cada mídia recebida.",
        ),
        passos=(
            "Clique em <b>Abrir exportação</b> e escolha o arquivo <b>.txt</b> "
            "ou <b>.zip</b> que o aplicativo gerou em “Exportar conversa”.",
            "Confira a reconstrução na tela: participantes, período e "
            "mensagens, com as mídias resumidas quando o pacote as inclui.",
            "Preencha o procedimento e o número do processo, para o termo "
            "amarrar a peça aos autos.",
            "Clique em <b>Gerar termo</b> e exporte em PDF, em HTML para o "
            "SEI, ou copie o texto.",
        ),
        limites=(
            "A peça responde pelo arquivo a partir do momento em que ele é "
            "aberto por esta ferramenta. Nada afirma sobre a autenticidade "
            "da conversa nem sobre o que houve antes: a exportação é gerada "
            "no aparelho e é, na origem, um texto, que pode ter sido editado.",
            "As datas e horas são as do arquivo, no fuso do aparelho que "
            "exportou, que o arquivo em geral não declara.",
            "As mensagens de sistema são reconhecidas por padrão; em formato "
            "incomum, alguma pode ser classificada como mensagem comum, ou o "
            "contrário.",
            "Quando a exportação é apenas texto, as mídias não a acompanham, "
            "e a mensagem correspondente consta como referência.",
        ),
    ),

    "videoweb": Guia(
        finalidade=(
            "Obtém vídeo publicado em plataforma da internet e emite o "
            "termo que o identifica: o endereço, os dados que a "
            "plataforma publicava naquele instante, a hora qualificada da "
            "captura e o resumo criptográfico do arquivo.\n\n"
            "Serve ao material que some. Vídeo em rede social desaparece "
            "porque o autor apaga, porque a plataforma remove, porque a "
            "conta é encerrada. Quem precisa dele num procedimento tem de "
            "obtê-lo enquanto existe — e tem de poder demonstrar, depois, "
            "o que obteve, de onde e quando."),
        quando=(
            "Vídeo publicado interessa à apuração e pode ser retirado do "
            "ar a qualquer momento.",
            "É preciso juntar aos autos material audiovisual divulgado "
            "publicamente, com a origem documentada.",
            "A publicação será objeto de exame posterior e convém "
            "preservá-la como estava.",
        ),
        passos=(
            "Cole o endereço e clique em <b>Consultar</b>. A tela mostra "
            "título, canal, data, duração e disponibilidade antes de "
            "qualquer captura.",
            "Confira, na consulta, que a disponibilidade é <b>pública</b>. "
            "A ferramenta não alcança material restrito.",
            "Escolha a <b>Qualidade</b> e clique em <b>Capturar</b>.",
            "Clique em <b>Gerar termo</b>. A peça traz o endereço, os "
            "dados publicados, o momento da captura e o resumo "
            "criptográfico do arquivo obtido.",
            "Para compactar, recortar ou juntar o material, use depois a "
            "<b>Edição de Vídeo</b>, que emite termo próprio ligando o "
            "resultado a este arquivo pelo resumo.",
        ),
        limites=(
            "Esta é a única ferramenta do sistema que sai para a "
            "internet, e a única cuja peça não promete "
            "reprodutibilidade — nem poderia. Baixar o mesmo endereço "
            "noutro momento pode devolver arquivo diferente, ou nenhum: a "
            "plataforma recodifica o material e remove conteúdo. O que a "
            "peça afirma é que este arquivo, com este resumo, foi obtido "
            "deste endereço neste instante.",
            "Os dados de título, canal, data e visualizações são "
            "informados pela própria plataforma. A ferramenta os "
            "transcreve como estavam; não os certifica.",
            "As plataformas servem imagem e som em fluxos separados, e o "
            "arquivo entregue costuma ser a junção local dos dois — não a "
            "cópia byte a byte de um arquivo publicado. O termo declara "
            "isso e consigna a versão do FFmpeg que fez a junção.",
            "Só se alcança o que está publicamente acessível. Nenhuma "
            "credencial é apresentada e nenhuma restrição de acesso é "
            "contornada: vídeo privado, restrito a membros ou com "
            "verificação de idade é recusado, com a razão dita.",
            "A biblioteca de captura acompanha as mudanças das "
            "plataformas e envelhece: cópia antiga falha por motivo "
            "obscuro. A idade dela aparece no rodapé do painel, e a "
            "ferramenta a menciona quando uma captura fracassa.",
        ),
    ),

    "pdf": Guia(
        finalidade=(
            "Junta vários PDFs num só, extrai páginas para um documento "
            "novo e reduz o tamanho de digitalizações que não cabem no "
            "sistema de processo.\n\n"
            "Resolve, antes de tudo, um problema de sigilo: essas três "
            "tarefas costumam ser feitas em sítio da internet, o que "
            "significa enviar peça de procedimento para servidor de "
            "terceiro, fora do controle do órgão. Aqui nada sai da "
            "estação. E, como nas demais ferramentas do sistema, a "
            "operação fica declarada e o resultado, conferível."),
        quando=(
            "O documento digitalizado excede o tamanho que o sistema de "
            "processo aceita.",
            "Chegaram vários PDFs avulsos que precisam virar peça única.",
            "Só algumas páginas de um documento longo interessam à "
            "juntada.",
        ),
        passos=(
            "Clique em <b>Acrescentar PDFs</b>. A lista mostra páginas e "
            "tamanho de cada um, e assinala em vermelho o que não pôde "
            "ser lido.",
            "Escolha <b>Mesclar</b>, <b>Separar</b> ou <b>Comprimir</b>.",
            "Em <b>Mesclar</b>, ordene com <b>↑</b> e <b>↓</b> — a ordem "
            "da lista é a ordem do resultado. Em <b>Separar</b>, escreva "
            "as páginas, como <i>1-3, 7, 10-12</i>. Em <b>Comprimir</b>, "
            "escolha o grau.",
            "Clique em <b>Processar</b> e escolha onde gravar.",
            "Clique em <b>Gerar termo</b>. Antes de montar a peça, a "
            "ferramenta refaz a operação a partir das origens e confere "
            "se chega ao mesmo documento.",
        ),
        limites=(
            "A conferência é feita sobre o resumo do conteúdo das "
            "páginas, e não sobre os bytes do arquivo produzido: o "
            "formato PDF guarda dentro de si dados que variam a cada "
            "gravação, e refazer a mesma operação gera arquivos de "
            "resumos diferentes ainda que o conteúdo seja o mesmo.",
            "Mesclar e separar não alteram página alguma, e o termo "
            "afirma isso por conferência: cada página do resultado tem "
            "resumo idêntico ao da página de origem.",
            "Comprimir sem perda costuma ganhar pouco, ou nada, num "
            "arquivo já limpo — o ganho vem de reamostrar imagem. Nos "
            "graus com perda a redução é grande, e o custo é real: as "
            "páginas mudam, e o detalhe fino de carimbo, assinatura e "
            "letra miúda se degrada.",
            "A camada de texto sobrevive à compressão em todos os graus. "
            "Nisto a ferramenta difere da Tarja Preta, que rasteriza a "
            "página e perde o texto pesquisável.",
            "Documento protegido por senha não é aberto. A ferramenta "
            "assinala e segue com os demais, em vez de interromper tudo.",
            "O documento produzido não herda metadado algum dos "
            "originais: é composto do zero e recebe apenas as páginas.",
        ),
    ),

    "planilha": Guia(
        finalidade=(
            "Examina planilha de auditoria sem quebrar a cadeia de "
            "custódia. Abrir o arquivo no Excel e ir filtrando resolve o "
            "problema prático e destrói o jurídico: ao fim existe um "
            "resultado, e não existe como demonstrar de onde ele veio. "
            "Filtro aplicado é filtro perdido, e quem lê o relatório "
            "precisa acreditar em quem o escreveu.\n\n"
            "Aqui cada operação é declarada, e a análise inteira vira um "
            "roteiro que pode ser re-executado por terceiro sobre o "
            "arquivo original, chegando ao mesmo resultado. A peça deixa "
            "de afirmar e passa a ser conferível — que é uma garantia de "
            "outra natureza."),
        quando=(
            "Chegou planilha de auditoria e é preciso refinar os dados "
            "até o que interessa à apuração.",
            "O resultado da análise vai instruir procedimento, e será "
            "preciso demonstrar como se chegou a ele.",
            "A mesma análise terá de ser repetida no mês seguinte, sobre "
            "outra remessa dos mesmos dados.",
        ),
        passos=(
            "Clique em <b>Abrir planilha</b>. Aceita xlsx, xls, xlsb, ods "
            "e csv. O resumo criptográfico do arquivo é tomado neste "
            "momento — é daí que a cadeia passa a correr.",
            "Se a tabela não começa na primeira linha, ajuste a "
            "<b>Linha do cabeçalho</b>. Havendo mais de uma aba, escolha "
            "a que interessa.",
            "Em <b>Acrescentar</b>, monte cada operação: filtrar linhas, "
            "ordenar, escolher colunas ou remover duplicidades. Cada "
            "passo mostra quantas linhas entraram e quantas saíram.",
            "Use <b>↑</b> e <b>↓</b> para mudar a ordem. A ordem importa: "
            "filtrar antes ou depois de remover duplicidades dá "
            "resultados diferentes.",
            "Clique em <b>Salvar resultado</b> e escolha onde gravar.",
            "Clique em <b>Gerar termo de análise</b>. Antes de montar a "
            "peça, a ferramenta refaz a análise a partir do arquivo "
            "original e confere se chega ao mesmo resultado.",
            "Salve também o roteiro, em <b>Salvar roteiro</b>, e junte-o "
            "aos autos: é ele que permite a terceiro refazer a análise "
            "sem depender desta máquina.",
        ),
        limites=(
            "A ferramenta não permite editar célula, e é essa ausência "
            "que sustenta a peça: como não há outro caminho para alterar "
            "dado, a relação de passos é necessariamente completa.",
            "A conferência de reprodutibilidade é feita sobre o resumo do "
            "conteúdo — colunas e células —, e não sobre os bytes do "
            "arquivo gerado. O formato de planilha guarda a hora da "
            "gravação dentro de si, de modo que o mesmo conteúdo gravado "
            "duas vezes produz arquivos de resumos diferentes.",
            "Filtro de texto não distingue maiúsculas nem acentos, salvo "
            "se marcada a opção. A escolha vai declarada no termo, porque "
            "muda o resultado.",
            "Planilha gerada por sistema, que nunca passou pelo Excel, "
            "pode guardar a fórmula sem guardar o resultado dela. A "
            "ferramenta avisa quando é o caso — filtrar por essas colunas "
            "levaria a conclusão errada.",
            "A peça responde pelo arquivo a partir do momento em que ele "
            "foi aberto aqui. Nada afirma sobre a origem dele antes "
            "disso.",
        ),
    ),

    # ── o registro do próprio trabalho ────
    "atividades": Guia(
        finalidade=(
            "Documenta cada execução do sistema, do momento em que ele abre "
            "até o momento em que fecha: quais ferramentas foram usadas, em "
            "que ordem, por quanto tempo, o que cada uma relatou ao "
            "concluir, e a identificação completa da estação e da rede em "
            "que se trabalhou.\n\n"
            "Resolve dois problemas de naturezas diferentes. O primeiro é de "
            "prestação de contas: mostrar o que foi feito num período, sem "
            "depender de memória nem de anotação manual. O segundo é de "
            "cadeia de custódia: quando se questiona em que máquina, em que "
            "dia e por quanto tempo determinada peça foi produzida, existe "
            "registro contemporâneo ao ato, gravado enquanto ele acontecia."
        ),
        quando=(
            "Ao prestar contas do trabalho de um período — o relatório "
            "reúne o que foi feito, sessão por sessão.",
            "Quando se questiona onde e quando uma peça foi produzida.",
            "Para conferir, a qualquer momento, o que o sistema registrou a "
            "respeito do próprio uso.",
        ),
        passos=(
            "Nada precisa ser feito para registrar: o registro começa "
            "quando o sistema abre e se encerra quando ele fecha.",
            "Abra a ferramenta para ver a sessão em curso e as anteriores. "
            "A lista traz a mais recente no alto.",
            "Selecione uma sessão para ler o relatório dela, e use "
            "<b>Salvar em PDF</b> para levá-la aos autos.",
            "<b>Apagar esta sessão</b> remove o registro do disco; "
            "<b>Abrir a pasta</b> mostra onde tudo está guardado.",
        ),
        limites=(
            "O registro fica apenas nesta máquina, e nada é enviado a "
            "servidor algum. Quem opera pode lê-lo e apagá-lo por inteiro — "
            "não é um controle a que ele esteja submetido sem saber.",
            "Não são anotados o conteúdo dos arquivos examinados, o texto "
            "digitado, os endereços visitados nem nomes de investigados. "
            "Registra-se que uma ferramenta foi usada e o que ela própria "
            "informou ao concluir. O material da apuração está nos termos "
            "de cada ferramenta, que são as peças dos autos.",
            "A qualificação que aparece no relatório é a guardada em "
            "Identificação no início da sessão. Ela descreve a configuração "
            "da estação, não prova quem praticou os atos: a autoria de cada "
            "peça é a que consta do respectivo termo.",
            "Sessão encerrada à força — queda de energia, término pelo "
            "gerenciador de tarefas — gera relatório marcado como "
            "interrompido, com o que havia sido gravado até então.",
        ),
    ),
}


# ─────────────────────────────────────────
#  APRESENTAÇÃO
# ─────────────────────────────────────────

def _lista(itens, marcador: str = "•") -> str:
    """Lista simples. Não se usa <ul>: o motor de texto do Qt lhe dá um
    recuo largo e desalinhado do resto do corpo."""
    linhas = []
    for item in itens:
        linhas.append(
            f'<tr><td width="18" valign="top" '
            f'style="color:{PALETTE["gold"]};">{marcador}</td>'
            f'<td style="padding-bottom:7px;">{item}</td></tr>')
    return f'<table cellspacing="0" cellpadding="0">{"".join(linhas)}</table>'


def guia_html(meta, guia: Guia) -> str:
    """O guia em HTML, no tema escuro do sistema."""
    tinta = PALETTE["text"]
    fraco = PALETTE["text2"]
    ouro = PALETTE["gold"]

    def titulo(texto: str) -> str:
        return (f'<p style="color:{ouro}; font-size:12px; font-weight:700; '
                f'letter-spacing:0.8px; margin-top:20px; margin-bottom:6px;">'
                f"{texto}</p>")

    partes = [
        f'<div style="font-family:Segoe UI,Arial,sans-serif; '
        f'font-size:13px; color:{fraco}; line-height:160%;">',
        titulo("PARA QUE SERVE"),
    ]
    for paragrafo in guia.finalidade.split("\n\n"):
        partes.append(f'<p style="color:{tinta}; margin-bottom:9px;">'
                      f"{paragrafo}</p>")

    if guia.quando:
        partes.append(titulo("QUANDO USAR"))
        partes.append(_lista(guia.quando))

    if guia.passos:
        partes.append(titulo("COMO USAR"))
        numeradas = [
            f'<b style="color:{tinta};">{i}.</b>&nbsp; {passo}'
            for i, passo in enumerate(guia.passos, 1)]
        partes.append(_lista(numeradas, marcador="&nbsp;"))

    if guia.limites:
        partes.append(titulo("LIMITES E CUIDADOS"))
        partes.append(_lista(guia.limites, marcador="!"))

    partes.append("</div>")
    return "".join(partes)


class GuiaDialog(QDialog):
    """A janela de "Como usar" de uma ferramenta."""

    def __init__(self, meta, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Como usar — {meta.name}")
        fit_to_screen(self, 680, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(10)

        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(12)
        icone = QLabel()
        icone.setPixmap(draw_icon(meta.icon, 34, PALETTE["gold"], 2.0)
                        .pixmap(34, 34))
        icone.setFixedSize(34, 34)
        cabecalho.addWidget(icone)

        textos = QVBoxLayout()
        textos.setSpacing(1)
        nome = QLabel(meta.name)
        nome.setObjectName("heading")
        textos.addWidget(nome)
        frase = QLabel(meta.tagline)
        frase.setObjectName("subtext")
        textos.addWidget(frase)
        cabecalho.addLayout(textos)
        cabecalho.addStretch()
        layout.addLayout(cabecalho)
        layout.addWidget(hsep())

        corpo = QTextBrowser()
        corpo.setOpenExternalLinks(False)
        corpo.setStyleSheet(
            f"QTextBrowser {{ background: {PALETTE['bg']}; border: 1px solid "
            f"{PALETTE['border']}; border-radius: 6px; padding: 18px 22px; }}")
        guia = GUIAS.get(meta.key)
        if guia is None:
            # Ferramenta sem guia escrito: melhor dizer isso do que abrir
            # uma janela vazia e deixar o usuário achando que travou.
            corpo.setHtml(
                f'<p style="color:{PALETTE["text2"]}; font-family:Segoe UI;">'
                f"{_html.escape(meta.description)}</p>")
        else:
            corpo.setHtml(guia_html(meta, guia))
        layout.addWidget(corpo, 1)

        rodape = QHBoxLayout()
        if meta.online:
            aviso = QLabel("Esta ferramenta acessa a internet.")
            aviso.setObjectName("badge_online")
            rodape.addWidget(aviso)
        rodape.addStretch()
        fechar = QPushButton("Fechar")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.setDefault(True)
        fechar.clicked.connect(self.accept)
        rodape.addWidget(fechar)
        layout.addLayout(rodape)
