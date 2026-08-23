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
            "Clique em <b>Gerar termo</b>, complete a abertura e salve em "
            "PDF ou HTML.",
        ),
        limites=(
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
