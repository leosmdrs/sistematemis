# Acesso à rede pelo Sistema Têmis

Documento de resposta ao questionamento da DTIC sobre tráfego de rede,
para instrução do processo de autorização de uso nas estações da PRF.

Versão a que se refere: **1.15.0**.
Código-fonte: <https://github.com/leosmdrs/sistematemis> (AGPL-3.0).

Tudo o que segue é verificável no código-fonte, nos pontos indicados.

---

## 1. Declaração

**O Sistema Têmis não envia a serviço externo algum os documentos,
arquivos, planilhas, vídeos, áudios ou dados que processa.**

Todo o processamento — extração de metadados, cálculo de resumos
criptográficos, censura de documentos, reconhecimento óptico,
transcrição de áudio, análise de planilha, operações em PDF, edição de
vídeo, indexação de acervo — ocorre inteiramente na estação. Não há
serviço de nuvem, não há API de terceiro que receba conteúdo, não há
envio de amostras, não há telemetria de uso.

Das dezessete ferramentas do sistema, **catorze não acessam a rede em
hipótese alguma**. As três que acessam estão assinaladas na própria
interface e no README, e o que elas acessam é descrito no item 3.

Existe ainda a verificação de atualização do próprio programa, e o
download, por solicitação expressa do operador, dos modelos de
reconhecimento de fala. Ambos são descritos adiante.

**Em nenhum desses casos trafega conteúdo de arquivo do usuário.** O
tráfego é de entrada — o sistema busca; não remete.

---

## 2. O que nunca sai da estação

| | |
|---|---|
| Documentos e arquivos processados | nunca saem |
| Conteúdo de planilhas, PDFs, vídeos, áudios | nunca sai |
| Texto transcrito ou reconhecido por OCR | nunca sai |
| Peças e termos produzidos | nunca saem |
| Resumos criptográficos calculados | nunca saem |
| Nome do usuário, matrícula, lotação, órgão | nunca saem |
| Número de procedimento (IPS/PAD) | nunca sai |
| Registro de atividades da sessão | nunca sai — fica em `Documentos\Sistema Têmis\Sessões` |
| Identificação da estação, da rede ou do domínio | nunca sai |
| Estatística de uso, telemetria, relatório de erro | não existe |

O sistema **não possui** mecanismo de envio de dados. Não há código de
upload, de API externa, de envio de relatório ou de coleta de uso.

---

## 3. Endereços acessados

### 3.1 Verificação de atualização

| | |
|---|---|
| **Endereço** | `https://github.com/leosmdrs/sistematemis/releases/latest/download/versao.json` |
| **Host** | `github.com` (pode redirecionar para `objects.githubusercontent.com`) |
| **Quando** | uma vez, na abertura do programa |
| **Método** | GET |
| **O que é enviado** | apenas o cabeçalho `User-Agent: SistemaTemis-atualizador` |
| **O que é recebido** | arquivo JSON de até 64 KB com o número da versão mais recente, o endereço do instalador e o resumo SHA-256 dele |
| **Código** | `temis/atualizacao.py` |

O cabeçalho é fixo: **não leva versão instalada, nome de máquina, nome
de usuário, domínio nem identificador algum**. A consulta tem limite de
6 segundos e, falhando, o programa abre normalmente — atualizar é
acessório.

O download do instalador novo, quando há atualização, só ocorre se o
operador clicar para atualizar, e o arquivo baixado é conferido pelo
resumo SHA-256 declarado no manifesto antes de ser executado.

### 3.2 Modelos de reconhecimento de fala e de separação de locutores

Usados pela ferramenta **Degravação**. São baixados **uma única vez**,
por ação expressa do operador, e ficam na estação. Depois disso a
transcrição roda sem rede.

| | |
|---|---|
| **Hosts** | `huggingface.co` e `cdn-lfs.huggingface.co` (modelos de fala) |
| | `github.com` e `objects.githubusercontent.com` (modelos de locutor) |
| **Endereços** | `https://huggingface.co/Systran/faster-whisper-<modelo>` |
| | `https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2` |
| | `https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_small.onnx` |
| **O que é enviado** | o nome do modelo pedido e o cabeçalho `User-Agent` descrito no item 4 |
| **O que é recebido** | os arquivos do modelo (centenas de MB no primeiro caso, 46 MB no segundo) |
| **Código** | `temis/tools/transcricao_core.py` |

Nenhum áudio, nenhum trecho de áudio e nenhum resultado de transcrição
trafega. O que se busca é o modelo; o que se transcreve fica na máquina.

Os repositórios escolhidos não exigem cadastro nem token de acesso.

### 3.3 Constatação Web

Ferramenta destinada a documentar conteúdo publicado na internet. Por
natureza, acessa o endereço que o operador determina.

| | |
|---|---|
| **Endereço** | **o que o operador digitar** — não há lista fixa |
| **O que é enviado** | a requisição HTTP comum de um navegador ao endereço informado |
| **Código** | `temis/tools/constatacao.py` |

O navegador embutido é configurado para cada diligência **sem extensão,
sem sessão anterior, sem cookie persistente e com cache apenas em
memória** (ajustes `NoPersistentCookies` e `MemoryHttpCache`, em
`temis/tools/constatacao.py`). Não há
sincronização com conta alguma, nem reaproveitamento de credenciais do
navegador do usuário.

Além do endereço informado, a ferramenta faz **duas consultas
acessórias**, para qualificar a prova:

| | |
|---|---|
| **Certificado TLS** | conexão direta ao próprio host consultado, porta 443, para registrar o certificado apresentado. Nada além do handshake. |
| **Registro do domínio (RDAP)** | `https://data.iana.org/rdap/dns.json` para descobrir o servidor autoritativo da terminação, e depois o servidor RDAP do registro competente (por exemplo `rdap.registro.br` para `.br`). |

**Cabe destacar, para a análise da DTIC:** a consulta RDAP transmite ao
registro competente **o nome do domínio que está sendo verificado**. É o
único ponto do sistema em que um dado da diligência — e apenas este —
chega a terceiro. A consulta é feita diretamente à fonte autoritativa,
sem intermediário, justamente para não haver mais uma parte no caminho
da prova. Não acompanha identificação do consulente, do procedimento ou
do órgão.

A ferramenta funciona sem essa consulta: falhando o RDAP, a peça é
emitida registrando que o dado não foi obtido.

### 3.4 Extração Registrada

Ferramenta destinada a documentar extração de dados em sistema
institucional. Acessa o sistema que o operador abrir — tipicamente um
sistema da própria PRF ou de órgão parceiro.

| | |
|---|---|
| **Endereço** | **o que o operador determinar** |
| **O que é enviado** | o que o operador fizer: autenticação no sistema, consultas e parâmetros que ele mesmo preencher |
| **Código** | `temis/tools/extracao.py` |

O navegador tem a mesma configuração isolada da Constatação Web, pelos
mesmos ajustes (`temis/tools/extracao.py`): sem extensão, sem cookie
persistente, cache em memória.

As credenciais que o operador usar são digitadas por ele no sistema de
destino, como em qualquer navegador. **O Sistema Têmis não as armazena,
não as transmite a lugar nenhum e não as registra na peça.**

### 3.5 Vídeo da Internet

Ferramenta destinada a preservar vídeo publicado, antes que seja
removido.

| | |
|---|---|
| **Endereço** | **o que o operador colar**, e os servidores de distribuição da própria plataforma |
| **O que é enviado** | a requisição de consulta e de download ao endereço informado |
| **O que é recebido** | os dados públicos da publicação e o arquivo de vídeo |
| **Código** | `temis/tools/videoweb.py`, `temis/tools/videoweb_core.py` |

Alcança **somente conteúdo publicamente acessível**. Nenhuma credencial
é apresentada a plataforma alguma. Vídeo privado, restrito a membros ou
sujeito a verificação de idade é recusado, e a razão é informada ao
operador.

A biblioteca de captura (`yt-dlp`) **não possui, no caminho utilizado,
rotina de atualização automática nem envio de uso**: o atualizador dela
só é instanciado pela interface de linha de comando, que o sistema não
emprega (conferido em `yt_dlp/YoutubeDL.py` — os símbolos importados do
módulo de atualização são usados apenas para montar rótulo de versão a
partir de dados locais).

---

## 4. O que vai nos cabeçalhos

Nenhuma requisição do sistema carrega identificação de usuário, de
estação ou de órgão. Os cabeçalhos são fixos:

| Função | `User-Agent` |
|---|---|
| Verificação de atualização | `SistemaTemis-atualizador` |
| Consulta RDAP | `SistemaTemis/RDAP` |
| Modelos de locutor | `Temis` |
| Modelos de fala | `unknown/None; hf_hub/<versão>; python/<versão>; origin/SistemaTemis` |

O último é montado pela biblioteca de download e informa apenas as
versões da própria biblioteca e do interpretador.

**Quanto à parcela final (`origin/…`).** Ela é fixa em `SistemaTemis`
**a partir da versão 1.15.0** (`temis/__main__.py`, função
`_calar_telemetria`). Até a 1.14.2, inclusive, era lida da variável de
ambiente `HF_HUB_USER_AGENT_ORIGIN` da estação — de modo que uma
variável de ambiente poderia fazer chegar texto arbitrário a esse
cabeçalho. Não houve, por esse caminho, envio de dado do usuário, e a
variável não existe numa instalação comum do Windows; ainda assim, o
valor deixou de depender do ambiente da máquina.

O cabeçalho só é emitido no download dos modelos de fala, descrito no
item 3.2 — isto é, apenas quando o operador manda instalar a Degravação.

Como em qualquer acesso à rede, o endereço IP da estação é visível ao
servidor contatado. Isso é inerente ao protocolo e não decorre de
qualquer envio feito pelo sistema.

---

## 5. Telemetria

**Não existe telemetria no Sistema Têmis.** Não há coleta de uso, de
erro, de desempenho nem de qualquer outra natureza.

Quanto às bibliotecas de terceiro, foi conferido no código-fonte que
**nenhuma envia telemetria no caminho utilizado pelo sistema**:

* a biblioteca de download de modelos (`huggingface_hub`) define a
  função de telemetria mas não a invoca em nenhum ponto do seu próprio
  código — apenas a expõe para quem queira usá-la, e o Sistema Têmis não
  usa;
* o baixador de vídeo (`yt-dlp`) só instancia o seu atualizador pela
  interface de linha de comando, que o sistema não emprega.

Ainda assim, por precaução e para que a afirmação não dependa de
reexaminar o código de cada versão nova das dependências, o programa
passa a **desligar explicitamente a telemetria na própria
inicialização**, antes de qualquer outra coisa (`temis/__main__.py`,
função `_calar_telemetria`):

```
HF_HUB_DISABLE_TELEMETRY = 1
DISABLE_TELEMETRY        = 1
DO_NOT_TRACK             = 1
```

**Esta medida vigora a partir da versão 1.15.0.** Para as versões
anteriores vale a conferência de código descrita acima — que é, em
qualquer caso, o que sustenta a afirmação; as variáveis são reforço.

---

## 6. Resumo para regra de firewall

Caso a DTIC opte por restringir a saída das estações, estes são os
únicos hosts de que o sistema precisa para funções próprias:

| Host | Para quê | Bloqueando, o que acontece |
|---|---|---|
| `github.com` | verificação de atualização e modelos de locutor | o programa abre e funciona; não avisa de versão nova, e a separação de locutores fica indisponível |
| `objects.githubusercontent.com` | entrega dos arquivos acima | idem |
| `huggingface.co`, `cdn-lfs.huggingface.co` | modelos de reconhecimento de fala | a Degravação fica indisponível até que os modelos sejam instalados por outro meio |
| `data.iana.org` | descoberta do servidor RDAP | a Constatação Web funciona; a peça registra que o dado do domínio não foi obtido |

**Todos os demais acessos são a endereços determinados pelo operador**,
nas três ferramentas assinaladas, e não a destinos fixos do sistema.

Bloqueando a saída inteira, as catorze ferramentas restantes continuam
funcionando integralmente, e a Degravação também, desde que os modelos
já tenham sido instalados.

---

## 7. Como conferir

1. **Código-fonte aberto**, sob AGPL-3.0, em
   <https://github.com/leosmdrs/sistematemis>. Os pontos citados neste
   documento estão indicados por arquivo.
2. **Levantamento independente**: os únicos pontos do programa capazes
   de abrir conexão são os cinco listados no item 3. Podem ser
   localizados por busca em `temis/` pelos termos `urlopen`,
   `urllib.request`, `socket.create_connection` e `snapshot_download`.
3. **Autoteste embutido**: executando `SistemaTemis.exe --autoteste` num
   terminal, o programa relaciona seus componentes e grava o resultado
   em `%LOCALAPPDATA%\SistemaTemis\autoteste.txt`.
4. **Observação de tráfego**: a instalação pode ser submetida a captura
   de rede numa estação de teste. Fora da verificação de atualização na
   abertura, nenhuma conexão parte do sistema sem ação do operador.

---

*Documento preparado em 16/10/2026, referente à versão 1.15.0.*
