# Sistema Têmis

Um único programa instalável reunindo instrumentos de apoio à atividade de
apuração e controle interno: tarjamento de documentos, integridade de
arquivos, detecção de conteúdo oculto, extração de metadados, registro de
conteúdo publicado na internet, degravação de oitivas, organização de
evidências e montagem da Informação de juízo de admissibilidade.

Os arquivos não saem da máquina: nenhum documento, hash ou metadado é
enviado a servidor algum. Os acessos à rede são dois, ambos visíveis: a
verificação de atualização ao abrir — que lê um arquivo de versão, sem
enviar identificação do usuário ou da estação, e pode ser desligada em
**Sobre** — e a Constatação Web, que por definição acessa a página que se
quer constatar.

## Autoria e vínculo

Escrito por **Leonardo Medeiros**, Policial Rodoviário Federal, por
iniciativa e conta próprias. **Não é um produto oficial da Polícia
Rodoviária Federal**, que não o encomendou, não o custeia e não o mantém.

O programa produz documentos destinados a procedimentos correcionais e por
isso os apresenta no formato dessas peças, com o timbre que elas levam. O
uso é responsabilidade de quem assina o documento produzido.

## Licença

**AGPL-3.0-or-later** — veja [LICENSE](LICENSE).

A licença não é escolha estética: é a mais restritiva entre as dos
componentes que o instalador distribui. O PyQt6 é GPL-3.0, o PyMuPDF é
AGPL-3.0 e o FFmpeg empacotado foi compilado com `--enable-gpl`. Licenciar
o conjunto de forma permissiva declararia a quem recebe uma condição que
não corresponde à realidade. Os componentes e a origem do código-fonte de
cada um estão em [TERCEIROS.md](TERCEIROS.md).

---

## Instalação

Baixe o instalador mais recente em
[Releases](https://github.com/leosmdrs/sistematemis/releases).

O instalador ainda não é assinado, então o Windows avisa: em **“O Windows
protegeu o seu PC”**, clique em *Mais informações* → *Executar assim
mesmo*.

Em estações com **Smart App Control** ligado, a instalação pode ser
recusada de saída. O recurso não tem lista de exceções: ele libera um
programa por assinatura de autoridade certificadora reconhecida ou por
reputação acumulada. Na prática, tentar de novo alguns minutos depois
costuma funcionar, porque a avaliação de reputação é assíncrona. Para
saber se a estação tem o recurso ligado:

```
reg query "HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy" /v VerifiedAndReputablePolicyState
```

Se o instalador não abrir e você quiser conferir se o que foi instalado
está íntegro, o executável aceita:

```
SistemaTemis.exe --autoteste
```

Das versões seguintes em diante o próprio sistema avisa quando houver
atualização, pede autorização, baixa e confere o SHA-256 antes de
instalar.

---

## Ferramentas

**Dezesseis ferramentas**, todas disponíveis. A ordem abaixo é a do
portal, disposta por etapa do trabalho e não em ordem alfabética: na
primeira, a peça e o preparo do documento que a instrui; na segunda, o
registro da prova onde ela está; na terceira, o exame do material e o
registro do próprio trabalho.

| Ferramenta | O que faz |
|---|---|
| **Encarregado de IPS** | Monta a Informação da Investigação Preliminar Sumária parte por parte, com o roteiro do que entra em cada uma e o respaldo normativo à mão — art. 92 da IN PRF nº 127/2024. Exporta HTML já diagramado para importar no SEI, e PDF. |
| **Tarja Preta** | Tarjamento irreversível de PDFs — a página é rasterizada ao salvar, então o texto sob a tarja sai do arquivo, e não fica apenas coberto. Tarja manual, tarja por seleção de texto, marcação por sinal à escolha (`[ ]`, `{ }` ou `( )`) e busca automática de CPF, CNPJ, RG, telefone e e-mail. |
| **Anti-Injection** | Detecção de texto oculto em PDFs — opacidade zero, corpo minúsculo, branco sobre branco, conteúdo fora da área da página e camadas ocultas —, usado para induzir a erro quem lê o documento, humano ou assistente de IA. Modos Normal / Revelar / Raio-X e relatório de constatação. |
| **Metadados e Hash** | SHA-256 dos arquivos e o que eles informam sobre si: autor, programa que gerou, datas, equipamento de origem e, quando o aparelho as gravou, as coordenadas da captura. Emite termo único de juntada e metadados, com coluna de nº SEI. |
| **PDF Pesquisável** | Acrescenta camada de texto invisível a PDFs escaneados e a fotos de documentos, encaixada palavra por palavra sobre a imagem. O documento fica igual ao original, mas passa a permitir busca, seleção e cópia — e a ser encontrado pela Varredura. |
| **Constatação Web** | **Acessa a rede.** Abre o endereço num navegador dedicado, sem extensões e sem sessão anterior, e registra o que foi exibido: a página inteira em PDF, o código-fonte, a tela, o IP do servidor e o certificado que ele apresentou — cada peça com o seu SHA-256. |
| **Extração Registrada** | **Acessa a rede.** Abre o sistema num navegador instrumentado e registra cada passo da extração: endereços, cliques, consultas com seus parâmetros e arquivos recebidos — cada um resumido no instante em que chega, antes de tocar qualquer pasta de trabalho. Grava a tela ao mesmo tempo. |
| **Gravação de Tela** | Registra a diligência feita no computador, com a identificação do processo, do operador e da estação impressa no próprio vídeo, junto ao relógio e ao tempo decorrido. Grava também, em faixa própria e à escolha de quem opera, o som que o computador reproduz. |
| **Espelhamento de Celular** | Liga um Android por cabo USB, espelha a tela e grava a sessão em resolução nativa, com fabricante, modelo, versão do Android e número de série lidos do próprio aparelho. Por padrão não repassa toque nem digitação: observa. |
| **Varredura** | Indexa um pendrive, um cartão ou uma pasta inteira: SHA-256 de cada arquivo e o texto que houver, inclusive o de páginas digitalizadas, por reconhecimento óptico. A busca passa a ser instantânea e não toca mais no dispositivo, que pode ser lacrado. Aponta os duplicados. |
| **Quadro de Evidências** | Mural de vínculos da investigação: anotações, imagens e marcações conectadas, organizadas por caso. Serve para enxergar as relações entre pessoas, fatos e provas antes de redigir a peça. |
| **Edição de Vídeo** | Compactar, fatiar e mesclar gravações para a juntada aos autos. Trabalha com videomonitoramento, câmeras corporais e vídeos anexados pelas partes. |
| **Degravação** | Transcreve áudio e vídeo com reconhecimento de fala executado na própria máquina; nenhum trecho é enviado a serviço externo. Separa automaticamente quem fala, na cronologia da gravação, e basta nomear cada voz uma vez. |
| **Reconstruir Conversa** | Reconstrói a conversa exportada de um aplicativo (texto ou pacote com mídias) num documento conferível, identificado pelo resumo criptográfico do arquivo de origem; as mídias do pacote são resumidas em SHA-256. Atesta que a reconstrução corresponde ao arquivo — não a autenticidade da conversa. |
| **Análise de Planilha** | Filtrar, ordenar, escolher colunas, remover duplicidades, acrescentar coluna calculada, agrupar e resumir, marcar linhas com justificativa e cruzar com outra planilha — registrando cada passo. Produz o resultado e um termo com o roteiro completo, que terceiro re-executa sobre o original para conferir. |
| **Relatório de Atividades** | Documenta cada execução do sistema, do abrir ao fechar, sem que ninguém precise ligá-la: ferramentas usadas e por quanto tempo, o que cada uma relatou ao concluir, e a identificação da estação e da rede. Grava enquanto a sessão corre. Fica só nesta máquina. |

Duas acessam a rede, e estão marcadas acima. As outras catorze leem e
processam tudo na própria estação. Fora delas, o sistema só sai à rede
para conferir se há versão nova, sem enviar identificação — e isso se
desliga em **Sobre**.

### Heurísticas do Anti-Injection

| Código | Detecta | Severidade base |
|---|---|---|
| **H1** | opacidade zero ou quase | Atenção |
| **H2** | corpo abaixo de 1,5 pt | Atenção |
| **H3** | trecho fora da área da página | Baixa |
| **H4** | cor praticamente branca sem fundo escuro atrás | Atenção |
| **H5** | conteúdo em camada (OCG) desligada | Baixa |
| **H6** | modo de renderização invisível (`Tr 3`) | Atenção |

### Gerador de Hash — diferenças em relação à extensão original

O texto do Termo de Juntada é o mesmo, mas a versão desktop corrige
limitações que o navegador impunha:

- **Hash em blocos de 1 MiB.** O original fazia `file.arrayBuffer()`, ou
  seja, carregava o arquivo inteiro na memória — inviável para vídeos de
  câmera corporal. Aqui um arquivo de qualquer tamanho é lido em blocos,
  com percentual por arquivo e cancelamento.
- **Nº SEI persistido.** No original o valor digitado nunca voltava ao
  modelo e se perdia ao recarregar a página; aqui entra no termo. Também
  pode ser digitado direto na célula da tabela do termo.
- **Termo editável com verificação de integridade.** O documento pode ser
  ajustado antes de exportar, e o PDF sai do que está na tela — o
  `QTextDocument` é clonado, não remontado a partir dos dados, senão as
  edições seriam descartadas em silêncio. Como a coluna de hash também
  fica editável, antes de exportar cada hash é reprocurado no texto
  (ignorando espaços, porque a célula quebra o valor em várias linhas); se
  algum não conferir, o usuário é avisado de que o termo não comprovará a
  integridade daquele arquivo.
- **PDF de verdade** via `QPdfWriter`, em vez de depender de
  “Imprimir → Salvar como PDF” do navegador.
- **Arrastar e soltar** arquivos, ausente no original.
- **Faixa de GB** em tamanhos (o original parava em MB).
- **Concordância no dia 1.** O original gerava “Aos 1 dias do mês de…”;
  agora sai “Ao 1º dia do mês de…”.

### Calculadora ePAD — retirada em agosto de 2026

Exibia a calculadora de dosimetria da CGU dentro do programa, numa página
incorporada. Saiu porque dependia do QtWebEngine — um Chromium inteiro,
cerca de 350 MB entre a biblioteca, os recursos e o QtQuick/QtQml de que
depende. Era mais da metade do instalador, e pesaria em toda atualização.

O código está preservado em `desativado/calculadora.py`, com as instruções
para trazê-lo de volta. A calculadora continua acessível pelo navegador,
em `epad.cgu.gov.br`.

Efeito colateral à época: sem ela, nenhuma ferramenta acessava a rede.

**Isso não vale mais, e este parágrafo afirmou o contrário por tempo
demais.** O QtWebEngine voltou na 1.1.0, com a Constatação Web, e desde
a 1.4.0 são duas as ferramentas que acessam a rede — ela e a Extração
Registrada. A frase de privacidade do portal é montada a partir do
registro de ferramentas e se ajustou sozinha às duas; quem não se
ajustava era o texto aqui.

### Edição de Vídeo — FFmpeg empacotado

A ferramenta depende do FFmpeg, que **vai dentro do instalador** (pasta
`ffmpeg`, ao lado do programa). As estações onde o Têmis roda não têm como
instalar pré-requisitos, então exigir um FFmpeg no PATH inviabilizaria a
ferramenta na prática.

Para montar o ambiente de desenvolvimento, baixar a build oficial do FFmpeg
para Windows e colocar `ffmpeg.exe` e `ffprobe.exe` em
`vendor/ffmpeg/bin/`. Os dois somam **~196 MB** e não são versionados.
`video_core.localizar()` procura, nesta ordem: dentro do executável
empacotado, ao lado do executável instalado, em `vendor/` e só então no
PATH — de modo que o mesmo código funciona instalado e a partir do fonte.

Três operações:

- **Compactar** — recodifica em H.264 (CRF 20/26/32), com redução opcional
  de resolução. A trilha de áudio é **copiada** quando já é AAC/MP3, e não
  recodificada: forçar 128 kbps sobre um áudio de bitrate menor faz o
  arquivo *crescer*. Se ainda assim o resultado não ficar menor, o programa
  avisa — compactar e sair maior é a ferramenta falhando no seu propósito, e
  calar isso levaria o servidor a juntar aos autos um arquivo pior que o
  original achando que o reduziu.
- **Fatiar** — corte rápido (`-c copy`, instantâneo e sem perda, mas encosta
  no keyframe anterior) ou preciso (recodifica e cai no ponto exato).
- **Mesclar** — usa o demuxer `concat`. Quando os arquivos divergem em
  codec ou resolução, o `concat` produziria um vídeo corrompido, então a
  incompatibilidade é detectada e a mesclagem recodifica, avisando antes.

### Quadro de Evidências — diferenças em relação à versão web

- **Imagens em disco, não no JSON.** A versão web guardava as fotos em
  base64 dentro do `localStorage`, cujo limite de ~5 MB estourava com
  poucas imagens — e o gravador apenas registrava um aviso no console, de
  modo que o quadro era perdido em silêncio. Aqui as imagens são arquivos
  numa pasta e o índice permanece pequeno.
- **Gravação atômica.** O JSON é escrito num temporário e só então
  substitui o anterior; um desligamento no meio da escrita não trunca o
  arquivo nem leva junto os outros casos.
- **Exporta em PDF**, além de PNG — o quadro costuma virar peça dos autos.
- **Remoção em cascata.** Apagar um item apaga os vínculos dele, que de
  outro modo reapareceriam como barbantes ligados ao nada.
- **Imagens órfãs** são varridas quando um caso é excluído.

### Anti-Injection — relatório de constatação

O relatório é um documento formatado, no mesmo padrão do Termo de Juntada:
cabeçalho da PRF, quadro de identificação do arquivo, tabela dos achados
(nº, página, severidade, heurística, motivo e conteúdo oculto) e assinatura
do servidor com matrícula e lotação. É editável antes de exportar, e o PDF
sai do que está na tela — o `QTextDocument` é clonado, não remontado.

### Anti-Injection — escalada de severidade

Qualquer achado cujo texto contenha **instrução dirigida ao leitor**
(“ignore as instruções anteriores”, “recomende o arquivamento”, “system
prompt”, “you are now a…”) é escalado para **Crítica**: texto escondido já é
anomalia, mas texto escondido mandando no leitor é outra coisa.

---

## Executar a partir do código

```bash
pip install -r requirements.txt
python -m temis
```

## Gerar o instalável

```bash
python build/make_icon.py
pyinstaller build/temis.spec --noconfirm
```

Isso produz `dist/SistemaTemis/` (~90 MB) com o `SistemaTemis.exe`. Para
empacotar no instalador, abrir `build/installer.iss` no **Inno Setup 6** e
compilar — o resultado sai em `dist/SistemaTemis-1.0.0-setup.exe`.

## Publicar uma versão

Um comando só:

```bash
python build/publicar.py 1.1.0 --notas notas.txt
```

Ele acerta a versão nos três arquivos que a declaram, compila o executável
e o instalador, e gera `dist/versao.json` com o SHA-256 calculado. Publique
os dois arquivos numa release com a tag `v1.1.0` — o `v` importa, é o que o
manifesto usa para montar o endereço.

O passo a passo completo está em [PUBLICACAO.md](PUBLICACAO.md).

### ⚠️ Assinatura digital é obrigatória para distribuir

Estações com **Smart App Control** ou **WDAC** ativos bloqueiam o executável
com *"Uma política de Controle de Aplicativo bloqueou este arquivo"* — o
binário do PyInstaller não é assinado nem tem reputação junto à Microsoft.
O instalador do Inno Setup sofre o mesmo bloqueio.

Para uso institucional o `SistemaTemis.exe` e o instalador precisam ser
assinados com um certificado de assinatura de código (Authenticode):

```bash
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\SistemaTemis\SistemaTemis.exe
```

Enquanto não houver certificado, rodar pelo código-fonte (`python -m temis`)
funciona normalmente, porque o interpretador Python já é um binário confiável.

---

## Arquitetura

```
run_temis.py        entrada do executável empacotado (import absoluto)
temis/
├── theme.py        paleta PRF (azul-marinho + dourado) e folha de estilo
├── icons.py        marca da balança e ícones, desenhados vetorialmente
├── widgets.py      componentes compartilhados
├── shell.py        casco: trilha lateral, tela inicial, barra de status
├── __main__.py     entrada de `python -m temis`
└── tools/
    ├── base.py     contrato ToolPage / ToolMeta
    ├── __init__.py registro das ferramentas
    └── ...         uma ferramenta por módulo
```

O `run_temis.py` existe porque o PyInstaller executa o arquivo de entrada
como script solto, sem pacote pai. Apontá-lo para `temis/__main__.py` faz o
executável morrer com *"attempted relative import with no known parent
package"* — o arquivo da raiz importa o pacote de forma absoluta e resolve
isso, sem prejudicar o `python -m temis`.

**Para acrescentar uma ferramenta:** criar o módulo com uma subclasse de
`ToolPage` (expondo `meta: ToolMeta` e emitindo `status_msg`), importá-la em
`tools/__init__.py` e trocar `None` pela classe no `REGISTRY`. O casco monta
o portal sozinho — não há nada a alterar nele.

### Convenção de layout

Toda ferramenta usa `SidebarPanel` e, se exibir páginas, `ViewerToolbar`:

```
┌─────────────┬──────────────────────────┐
│  PAINEL     │  barra de visualização   │
│  LATERAL    ├──────────────────────────┤
│  (esquerda) │                          │
│  cabeçalho  │  conteúdo                │
│  corpo      │                          │
│  rodapé     │                          │
└─────────────┴──────────────────────────┘
```

- **cabeçalho** — ação de entrada (abrir/selecionar arquivo), em **dourado**
- **corpo** — controles da ferramenta, rolável
- **rodapé** — ação de saída (salvar/gerar/emitir), em **verde**
- **barra** — navegação de páginas, zoom e modos de visualização

Esses componentes vivem em `widgets.py` justamente para que a padronização
seja estrutural. Quando cada ferramenta montava a própria barra, elas
divergiram sozinhas: o painel ficou à esquerda numa e à direita em duas, os
botões de página eram texto numa e ícone noutra, e a mesma ação aparecia em
cores diferentes. Uma implementação só torna isso impossível.

Nenhum ícone vem de arquivo de imagem: todos são desenhados com `QPainter`
em `icons.py`. Emojis e caracteres como `＋` ou `⬛` viram um quadrado vazio
quando a fonte do sistema não os possui, e o `.ico` do instalador é derivado
do mesmo código da marca — assim ícone e interface nunca saem de sincronia.

---

## Notas de implementação

**Coordenadas da tarja.** O canvas do visualizador tem exatamente o tamanho
do *pixmap* renderizado, e a conversão tela↔PDF é só uma divisão pela escala.
Estimar um deslocamento de centralização à parte dessincroniza do
centramento nativo do `QLabel`: a tarja desenhada deixa de coincidir com o
trecho real e o erro se propaga para o arquivo salvo.

**Roda do mouse em combos.** `NoScrollComboBox` repassa o evento ao painel
rolável. Sem isso, rolar a lateral sobre um combo fechado trocava
silenciosamente o valor — inclusive o escopo de um tarjamento.

**Camadas ocultas (H5).** Quando um OCG está desligado, o MuPDF não devolve
o texto dele — nem em `get_texttrace()`, nem em `get_text()`. Para enxergar
esse conteúdo, `analyze_document()` registra o que cada página exibe no
estado original, liga as camadas com `set_layer_ui_config(n, action=1)`,
extrai de novo e trata como oculto o que só apareceu na segunda passada. O
estado é restaurado ao final.

**Ordem na folha de estilo.** `QMainWindow, QDialog, QMessageBox` precisa
vir depois de `QWidget` em `theme.py`: os seletores têm a mesma
especificidade e, no empate, o Qt aplica a última regra. Com a ordem
invertida, o `background: transparent` do `QWidget` vencia e todos os
diálogos abriam claros, com texto claro por cima.
