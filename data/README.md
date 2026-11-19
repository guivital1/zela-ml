# Dados de zeladoria

A base foi construída para simular a triagem de uma ouvidoria de bairro. `scenarios.json` contém 30 situações por categoria, totalizando 180. `zela-ml dataset` transforma cada situação em até cinco versões e remove repetições exatas dentro da família. Entre as variações estão ausência de acentos, abreviações, saudações e frases de contexto. O catálogo usa locais genéricos e descrições fictícias.

`reports.csv` é o conjunto efetivamente usado. Suas colunas são `id`, `scenario`, `text`, `category`, `split` e `source`. Somente `text` é entrada do classificador. `category` é o rótulo. `scenario` permite manter juntas as variações da mesma situação. A divisão com semente 42 reserva 108 cenários para treino, 36 para validação e 36 para teste. A base tem 488, 162 e 160 linhas nessas partições.

`probes.csv` contém 24 casos adicionais, divididos entre validação e teste. Há pedidos fora da taxonomia, descrições insuficientes, serviços privados e relatos com dois problemas. O resultado esperado é revisão humana. Somente os casos de validação participam da escolha dos limites. As 12 previsões de teste estão em `reports/challenge_predictions.csv`.

As categorias descrevem a taxonomia interna do ZELA. Encaminhar um pedido exige que o operador confirme o tipo de serviço e o canal adequado no município.
