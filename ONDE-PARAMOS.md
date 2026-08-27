# Onde paramos

Situação em **27/08/2026**. Este arquivo existe para retomar o trabalho
em outra máquina sem depender de memória. Ele descreve o que está
pronto, o que está pendente e as armadilhas já medidas — para não se
gastar tempo redescobrindo o que já custou caro descobrir.

---

## 1. Estado do repositório

Ramo `main`, no GitHub, atualizado. Três commits interessam agora:

| Commit | O que é |
|---|---|
| `840841b` | **Gerou o instalador 1.7.3.** Termo de censura e termo de edição. |
| `7ce8a79` | Som do computador na gravação de tela. **Não versionado.** |
| `7b318e9` | Análise de Planilha, etapa 1. **Não versionado.** |

A versão declarada em `temis/__init__.py` continua **1.7.3**. As duas
últimas entregas ainda não têm número nem instalador.

---

## 2. A 1.7.3 está publicada. Pendente é a 1.7.4

A release **v1.7.3 foi publicada em 25/08/2026** e é a mais recente. A
versão anterior desta nota dizia que ela continuava pendente; estava
errada, e foi corrigida em 27/08/2026 conferindo a própria release.

    https://github.com/leosmdrs/sistematemis/releases/tag/v1.7.3

A etiqueta aponta para **`840841b`** — o alvo certo, o mesmo commit que
gerou aquele instalador, e não o topo do `main`. Os dois anexos estão lá:

    SistemaTemis-1.7.3-setup.exe   271,8 MB
    SHA-256  cb548de3caf60b93a1db9445dc0231bef8b85652fd8deae6675d1c90369c1bad
    versao.json                    declara esse mesmo resumo

O resumo publicado bate com o que estava anotado aqui. Não há o que
republicar nem o que corrigir na release.

**O que segue pendente é a 1.7.4**, com as duas entregas que estão no topo
do `main` e fora daquele instalador: som do computador na gravação de tela
e Análise de Planilha. Ali etiqueta, código e instalador coincidem no topo
do `main`, e por isso não há alvo a escolher. São uns quarenta minutos de
compilação. O passo a passo está em `PUBLICACAO.md`.

Continua valendo a advertência que motivou a nota anterior, agora para a
1.7.4: **`dist/` não vai para o Git**, então o instalador só existe na
máquina que o compilou. Compilar de novo não devolve o mesmo arquivo — o
instalador carrega a hora da geração, e o resumo criptográfico muda. Ou o
`.exe` viaja junto, ou quem compilar publica o resumo que a sua própria
compilação produziu.

---

## 3. Montar o ambiente na outra máquina

**Já feito em 27/08/2026, em `E:\SistemaTemis`**, com autoteste em 15 de
15 — "Instalação íntegra". O que segue vale para a próxima máquina, ou
para refazer esta.

```bash
git clone https://github.com/leosmdrs/sistematemis.git
cd sistematemis
pip install -r requirements.txt
```

**Python.** O `python` solto costuma cair no atalho da Microsoft Store,
que não executa nada — era o que havia nesta máquina, e é a mesma
armadilha que o `Abrir Sistema Temis.bat` já contornava. Instalado o
3.12.10:

```bash
winget install --id Python.Python.3.12 --scope user
```

O instalador põe o `py` e a pasta do interpretador no PATH do usuário, e
com isso o `.bat` volta a funcionar com dois cliques, pelo caminho de
reserva que ele mesmo previa.

**`vendor/` não vai no Git** (são dezenas de MB de binário de terceiro).
É preciso baixar à parte, conforme o `README.md`:

* `vendor/ffmpeg/bin/` — `ffmpeg.exe` e `ffprobe.exe`
* `vendor/scrcpy/` — scrcpy e adb

O winget resolve os dois, e confere o resumo do que baixa:

```bash
winget install --id Gyan.FFmpeg
winget install --id Genymobile.scrcpy
```

Ele extrai em `%LOCALAPPDATA%\Microsoft\WinGet\Packages\...`. De lá se
copiam `ffmpeg.exe` e `ffprobe.exe` para `vendor/ffmpeg/bin/`, e **todos**
os arquivos do scrcpy para `vendor/scrcpy/` — inclusive o `scrcpy-server`,
que não tem extensão e sem o qual o espelhamento não sobe.

**Copiar para `vendor/` é obrigatório, não é capricho.** O FFmpeg tem o
PATH como último recurso em `video_core.localizar()`, mas o scrcpy não
tem nenhum: `espelhamento_core.adb_path()` só olha `vendor/scrcpy/`.
Instalado, no PATH e fora dali, o Espelhamento continua se declarando
indisponível. É também de `vendor/` que o `build/temis.spec` lê na hora
de empacotar, então o mesmo gesto serve à execução e à compilação.

Uma medida a rever antes de compilar: o `README.md` diz que `ffmpeg.exe`
e `ffprobe.exe` somam ~196 MB. Na build **9.0.1 full** somam **424 MB**, e
isso vai inteiro para dentro do instalador. Se pesar, a build *essentials*
do mesmo autor atende ao Compactar e ao Fatiar.

Depois, a conferência que vale por todas:

```bash
python run_temis.py --autoteste
```

Ele verifica as quinze ferramentas, os binários, os modelos de voz, o
OCR do Windows, a captura de som, a leitura de planilha, o cabeçalho das
peças e a geometria do portal. Tudo verde = a instalação está inteira.

---

## 4. O que ficou pronto desde o instalador 1.7.3

### Som do computador (`7ce8a79`)

As duas ferramentas que gravam tela — **Gravação de Tela** e **Extração
Registrada** — passaram a oferecer duas fontes de som escolhidas em
separado: o que a máquina reproduz e o que se fala na sala. Nenhuma, uma
ou as duas.

Entram como **faixas distintas**, não misturadas: misturar apagaria a
distinção entre o que o computador tocou e o que foi dito, e é essa
distinção que tem valor na peça.

O termo passou a declarar a fonte de cada faixa e, sobretudo, **o que não
foi registrado** — gravando só com microfone, a peça afirma
expressamente que o som do computador não foi captado.

Testado nas quatro combinações: 0, 1, 1 e 2 faixas de áudio, com sinal
real (pico 0,50) e sem sobra de arquivo temporário.

### Análise de Planilha, etapa 1 (`7b318e9`)

Ferramenta nova, a décima quinta. Módulos `temis/tools/planilha_core.py`
(a lógica) e `temis/tools/planilha.py` (a tela).

Pronto e provado: abrir (xlsx, xlsm, xlsb, xls, ods, csv), **filtrar**
(catorze condições), **ordenar**, **escolher e reordenar colunas**,
**remover duplicidades**, gravar o resultado, salvar e reabrir o
roteiro, e o **termo de análise** com o roteiro completo e a conferência
de reprodutibilidade.

O princípio está escrito no cabeçalho de `planilha_core.py` e precisa ser
respeitado em qualquer acréscimo: **não pode existir maneira de alterar
dado que não seja uma operação declarada.** É a ausência de edição de
célula que permite ao termo afirmar que a relação de passos é completa.

---

## 5. O que falta

### 5.1 Análise de Planilha — etapa 2 (combinado com o usuário)

Ele confirmou que usa as quatro famílias de operação. Faltam duas e
meia:

* **Cruzar com outra planilha** (o PROCV). Em auditoria costuma ser o
  passo que produz o achado. O termo passa a citar **duas origens com
  hash** — `derivado_core.Derivacao` já aceita lista de origens, e
  `derivado.medir()` também; é só passar as duas.
* **Agrupar e somar/contar** (a tabela dinâmica). Gera o quadro-resumo
  que vai na peça.
* **Coluna derivada** — juntar texto, extrair parte, diferença entre
  datas.
* **Marcação de linhas** com justificativa registrada. Atenção: isto tem
  de ser uma operação declarada, com a justificativa dentro dela, e não
  uma digitação em célula.

**Onde mexer**, para cada operação nova:

1. Uma subclasse de `Operacao` em `planilha_core.py`, com os quatro
   métodos: `aplicar`, `descrever`, `dados` e `de_dados`.
2. A entrada correspondente no dicionário `TIPOS`, no fim da seção de
   operações — **sem isso o roteiro grava e não relê**.
3. Uma página nova em `DialogoOperacao`, e a entrada em `FAMILIAS`, em
   `planilha.py`.

### 5.2 Decisões pendentes do usuário

* **Termo como primeira página do documento produzido.** Ele perguntou
  se o termo poderia ser gerado dentro do próprio arquivo, na primeira
  página. Foram apresentadas três opções; a recomendação foi a **C**
  (deixar escolher), com a **A** (termo em separado) como padrão. Não
  respondeu ainda. O obstáculo real é a autorreferência: o termo não
  pode citar o resumo criptográfico do arquivo que o contém.
* **Certificado digital** para o aviso de "editor desconhecido" do
  Windows. Ele disse "depois eu decido". O caminho recomendado foi pela
  DTIC, por política de grupo. Ver `ASSINATURA.md`.
* **Qual ferramenta construir depois.** A sugestão foi a calculadora de
  prazos prescricionais.

### 5.3 Testes que só podem ser feitos com material real

* **Espelhamento de Celular** com aparelho Android de verdade.
* **Extração Registrada** contra um sistema real da PRF.
* **Análise de Planilha** com uma planilha de auditoria de verdade — as
  provas até aqui usaram planilha fabricada, ainda que com as armadilhas
  de uma real.

### 5.4 Lacuna conhecida do projeto

**Não há suíte de testes no repositório.** As provas de cada entrega
foram escritas como scripts avulsos, fora da árvore do projeto, e não
viajam com ele. O que viaja e é permanente é o `--autoteste`, que cobre
integridade da instalação — não o comportamento das ferramentas.

Vale considerar trazer as provas para dentro do repositório, numa pasta
`provas/`, para que uma alteração futura não desfaça em silêncio o que
já foi conferido.

---

## 6. Armadilhas já medidas — não refazer o caminho

Cada uma destas custou tempo para ser encontrada. Estão aqui para não
serem encontradas de novo.

**O resumo de um `.xlsx` não se repete.** Gravar duas vezes o mesmo
conteúdo dá arquivos com resumos criptográficos diferentes: o formato é
um zip e guarda a hora da gravação dentro. Por isso a conferência de
reprodutibilidade é sobre `Tabela.resumo()`, que é do conteúdo.

**Qt sem `QApplication` não levanta exceção: derruba o processo.**
Qualquer script que chame `cabecalho_html()`, desenhe ícone ou monte
ferramenta precisa criar a aplicação antes — e importar
`PyQt6.QtWebEngineCore` antes dela.

**`perfil.aplicar(self)` vai no fim do construtor.** Preencher um campo
dispara `textChanged`, que remonta a prévia; chamado antes de a prévia
existir, o programa encerra sem mensagem.

**Acrescentar ferramenta pode desarranjar o portal.** Aconteceu com a
décima quinta: oito sobreposições na tela de catorze polegadas. O
`--autoteste` acusa; o ajuste é o tamanho do ladrilho em `shell.py` e o
comprimento das frases (`tagline`), que não devem passar de ~44
caracteres.

**Alterar formato enquanto se percorre fragmentos de `QTextDocument`
invalida o iterador** e derruba o programa. Coletar as posições
primeiro, alterar depois.

**`gdigrab` com dois monitores devolve dimensão ímpar**, e o libx264
recusa. Daí o filtro de corte para dimensão par na Gravação de Tela.

**Credencial colada no chat não se usa, nunca.** A release se publica
pelo navegador, pelo link acima. Foi assim em todas as anteriores.

**Arquivo de caso real não entra no repositório.** Já houve uma captura
de tela de caso real que quase foi commitada por um `git add -A`. O
`.gitignore` hoje barra `*.pdf`, `*.png` e `*.jpg` fora de
`temis/**/*.png` — conferir antes de cada `push` mesmo assim.

---

## 7. Sobre as bibliotecas novas

Três entraram recentemente e estão declaradas em `requirements.txt`,
`build/temis.spec` (em `hiddenimports`, porque o empacotador não as
descobre sozinho) e `TERCEIROS.md`:

| Biblioteca | Para quê | Licença |
|---|---|---|
| `soundcard` | captura do som que o Windows reproduz | BSD-3 |
| `python-calamine` | leitura rápida de planilha (15 s contra 133 s) | MIT |
| `openpyxl` | gravação do resultado da análise | MIT |

**Sem pandas, deliberadamente.** Somaria uns 35 MB e converteria tipo por
conta própria — que é exatamente o estrago que a Análise de Planilha
existe para evitar.
