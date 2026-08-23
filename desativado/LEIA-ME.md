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
