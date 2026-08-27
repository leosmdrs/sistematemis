# Normas técnicas observadas

Este arquivo diz **em que medida** o Sistema Têmis observa as duas normas
que orientam o tratamento de evidência digital, e — o que importa tanto
quanto — **o que ele não cobre**.

Declarar conformidade em bloco seria fácil e seria falso. Norma não se
atende por adesão: atende-se princípio por princípio, e quem for
contestar a peça vai procurar exatamente o princípio que ela deixou de
fora. Melhor que esteja escrito aqui do que descoberto no processo.

---

## ABNT NBR ISO/IEC 27037

*Diretrizes para identificação, coleta, aquisição e preservação de
evidência digital.* É a norma internacional da matéria, adotada no Brasil
pela ABNT.

Ela firma quatro princípios para o tratamento da evidência. O que o
sistema faz quanto a cada um:

| Princípio | Como o sistema atende |
|---|---|
| **Auditabilidade** — um avaliador independente deve poder avaliar as atividades realizadas | Toda peça declara com o que foi produzida: versão do sistema, do sistema operacional e de cada componente que executou a operação, mais o resumo criptográfico do próprio executável. O código-fonte é público, sob AGPL-3.0. |
| **Repetibilidade** — mesmo resultado, mesmo procedimento, mesmas condições | O Relatório de Atividades registra cada ação da sessão, encadeada por resumo. As operações da Análise de Planilha, da Tarja Preta e da Edição de Vídeo são determinísticas e declaradas. |
| **Reprodutibilidade** — mesmo resultado, mesmo procedimento, **em outro ambiente** | Três ferramentas produzem roteiro re-executável, salvo em arquivo próprio: quem tiver o original e o roteiro obtém o mesmo resultado noutra estação. A peça informa se a re-execução reproduziu. |
| **Justificabilidade** — demonstrar que o método escolhido era adequado | Cada termo traz suas ressalvas: o que a operação faz, o que não faz, e o que a peça não está afirmando. As escolhas que mudam resultado vão declaradas, e não implícitas. |

Outros pontos da norma, e a correspondência:

- **Minimizar a manipulação do original.** Nenhuma ferramenta grava sobre
  o arquivo de entrada; o resultado é sempre arquivo novo, em separado. A
  Varredura indexa o dispositivo uma vez e não volta a tocá-lo, de modo
  que ele possa ser lacrado.
- **Documentar toda alteração.** Onde há alteração — censura, edição,
  análise —, ela é operação declarada, e o termo relaciona todas.
- **Identificar quem manuseou.** A identificação do operador acompanha as
  peças, e o Relatório de Atividades registra a estação, o usuário do
  sistema operacional e o equipamento.

**O que não é coberto.** A norma trata também da coleta em campo:
isolamento do local, aquisição de mídia física, aquisição de dados
voláteis, acondicionamento e transporte. O Têmis não faz nada disso — é
ferramenta de gabinete, que trabalha sobre material já recebido. A
delimitação está impressa nas próprias peças, que declaram responder pelo
material a partir do momento em que ele foi aberto pela ferramenta.

---

## RFC 3227 — IETF, BCP 55

*Guidelines for Evidence Collection and Archiving.* Diretriz de melhores
práticas do IETF, de 2002, e ainda a referência corrente para coleta e
arquivamento.

| Diretriz | Como o sistema atende |
|---|---|
| **Transparência do método** — os métodos devem poder ser examinados por peritos independentes | Código-fonte público, e cada peça nomeia as versões que executaram a operação. |
| **Registrar o que se fez** — documentar cada passo, com horário | Relatório de Atividades, gravado enquanto a sessão corre e encadeado por resumo. Cada peça carimba o instante em que os resumos foram tomados, com fuso. |
| **Desvio do relógio** — a diretriz manda registrar o relógio e o seu desvio | As peças declaram o fuso e o **estado de sincronização** do relógio da estação, apurado junto ao sistema operacional, e advertem que não constituem carimbo de tempo certificado. |
| **Cadeia de custódia** — descrever onde a evidência foi encontrada, como foi manuseada e tudo o que lhe aconteceu | O termo de juntada registra de quem, por que meio e quando o material foi recebido; os termos derivados identificam original e produzido pelos resumos; a conferência de integridade confronta o resumo declarado na entrega. |
| **Arquivamento** — preservar a evidência de alteração e registrar quem teve acesso | O original nunca é alterado. Cada peça produzida é identificada por resumo criptográfico, o que torna qualquer alteração posterior detectável. |
| **Não confiar em programa da máquina sob exame** | A leitura é feita pelos componentes que acompanham o instalador, e não por programas do material examinado. |

**O que não é coberto.** A diretriz abre com a **ordem de volatilidade** —
memória, tabelas de rotas, processos, disco — e trata de aquisição em
máquina ligada. O Têmis não faz aquisição de dados voláteis nem cópia
forense de mídia física; para isso existem ferramentas próprias, e usá-lo
no lugar delas seria empregá-lo fora do que ele se propõe.

---

## Por que isto está escrito

O Superior Tribunal de Justiça passou a exigir que a integridade da prova
digital seja **demonstrada**, e não presumida pela fé pública de quem a
colheu, e que o hash venha acompanhado de software confiável e auditável.

Uma ferramenta que se limitasse a afirmar conformidade normativa
repetiria, num outro nível, exatamente a presunção que os tribunais
recusaram. O que se pode oferecer é o mapeamento acima — verificável
contra o código, que é público — e a delimitação honesta do que fica de
fora.
