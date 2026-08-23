# Módulos desativados

## calculadora.py — Calculadora ePAD

Exibia a calculadora de dosimetria da CGU dentro do sistema, numa
página incorporada. Foi retirada em agosto de 2026 porque exigia o
QtWebEngine — um navegador Chromium inteiro, cerca de 350 MB, que
respondia por mais da metade do tamanho do instalador e por todo o
peso de cada atualização.

O código está aqui inteiro. Para voltar atrás:

1. mover `calculadora.py` de volta para `temis/tools/`;
2. reimportar e reinscrever `CalculadoraTool` em `temis/tools/__init__.py`;
3. tirar `PyQt6.QtWebEngineWidgets` e afins da lista `excludes` em
   `build/temis.spec`;
4. restaurar `_preparar_webengine()` em `temis/__main__.py` — o
   QtWebEngine precisa do atributo `AA_ShareOpenGLContexts` ligado
   antes de existir QApplication;
5. reinstalar `PyQt6-WebEngine`.

A calculadora continua acessível pelo navegador, no endereço
https://epad.cgu.gov.br/publico/calculadora/calc.html?tipo=pad


## hash.py — Gerador de Hash

Ferramenta separada que calculava o SHA-256 de arquivos e montava o Termo
de Juntada. Foi fundida ao Extrator de Metadados em agosto de 2026, dando
origem a **Metadados e Hash**.

O motivo foi duplicação real: as duas ferramentas recebiam uma lista de
arquivos e calculavam o mesmo hash — o extrator de metadados já importava
`sha256_file` daqui. Na prática o encarregado fazia o mesmo trabalho duas
vezes, em duas telas, para juntar os mesmos arquivos.

O que sobreviveu, e continua em uso:

- `temis/tools/hash_core.py` — inteiro. `sha256_file`, `format_size` e
  sobretudo `build_intro`, que redige a abertura do termo ("Ao 1º dia do
  mês de…"). A ferramenta nova chama essa mesma função, para que a
  redação do termo não se bifurque em duas versões.

O que se perdeu: a tabela editável de seis colunas, em que o nº SEI era
digitado célula a célula. Na ferramenta nova o nº SEI é um campo abaixo da
lista, preenchido para o arquivo selecionado.
