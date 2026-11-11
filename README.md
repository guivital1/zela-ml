# ZELA · Machine Learning

<img src="src/zela_ml/static/logo.jpg" width="76" height="76" alt="Logo do ZELA">

O ZELA ajuda moradores e trabalhadores a registrar problemas de uma rua e acompanhar o que foi feito. Uma pessoa descreve o problema, informa o local e pode anexar uma foto. Quando o endereço já tem uma ocorrência aberta, ela pode confirmar o relato existente. A equipe revisa os pedidos, encaminha pelo canal do município e registra o protocolo e a resolução.

**Global Solution 2026 · CitizenTech · Engenharia de Software · FIAP**

Guilherme Vital Rodrigues

## Executar

Use Python 3.12 e execute na raiz do repositório.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
zela-ml serve --exemplo --equipe
```

No Windows, crie o ambiente com `py -3.12 -m venv .venv` e ative com `.venv\Scripts\Activate.ps1` no PowerShell. O modelo treinado já está em `artifacts/`.

Ao iniciar com `--equipe`, defina uma senha de pelo menos 12 caracteres no terminal. Abra o [ZELA](http://127.0.0.1:8000/) e registre um relato. Em **Acompanhando**, aparecem os pedidos registrados ou confirmados neste navegador. Entre em **Área da equipe** para revisar pedidos e acessar a avaliação do modelo, o notebook e a documentação da API.

O modo `--exemplo` usa três ocorrências fictícias em um banco separado. Para começar com uma base vazia, use `zela-ml serve --equipe`. O ZELA local escuta em `127.0.0.1`. Cada sessão da equipe expira em oito horas ou ao reiniciar o servidor. Esta versão usa uma senha compartilhada para a equipe local.

```sh
zela-ml predict "O poste da esquina não acende e a rua fica escura à noite."
python scripts/check.py
```

## Acompanhamento e cópia dos dados

- O cidadão pode registrar, confirmar e acompanhar uma ocorrência. O reconhecimento do navegador funciona por um identificador local. Rua, número e bairro ajudam a encontrar ocorrências abertas no mesmo endereço.
- Quando a equipe marca um caso como resolvido, o morador pode confirmar o reparo ou relatar que o problema continua. Nesse caso, a ocorrência volta para a fila com a observação ou foto, o protocolo anterior e o histórico.
- A fila da equipe mostra os casos para revisar, os encaminhados e os resolvidos. A equipe pode salvar a categoria separadamente, copiar o pedido para o canal oficial e registrar o protocolo recebido.
- Com o protocolo registrado, a equipe pode incluir a resposta da prefeitura, a data em que a recebeu e o próximo passo. O morador vê o retorno no andamento e pode copiar o link direto da ocorrência.
- A Área técnica compara as sugestões do modelo com as categorias revisadas no ambiente atual. A equipe pode consultar correções recentes. Esses dados servem para avaliação do piloto.
- O ZELA guarda o relato e a foto no SQLite. Para copiar os dados, execute `zela-ml backup instance/copia.sqlite3`. Acrescente `--exemplo` para copiar o banco fictício.
- Para recuperar os dados, pare o servidor, preserve uma cópia do banco atual e use uma cópia válida no lugar de `instance/zela.sqlite3` ou `instance/zela-exemplo.sqlite3`, conforme o ambiente. Reinicie e confira uma ocorrência e seu histórico. Arquivos do banco e cópias ficam fora do Git.

## Experimento

As seis categorias são iluminação pública, limpeza urbana, pavimentação, drenagem, acessibilidade e áreas verdes. O dataset contém **810 relatos simulados de 180 cenários**. Cada cenário e suas variações pertencem à mesma partição. O modelo foi escolhido na validação pelo F1 macro e avaliado em 160 relatos de 36 cenários separados.

| Indicador no teste sintético | Resultado |
| --- | ---: |
| F1 macro do modelo | **0,830** |
| F1 macro da referência pela frequência | 0,051 |
| Acurácia | 83,75% |
| Cenários com todas as variações classificadas corretamente | 29 de 36 |
| Intervalo de 95% para F1 macro, com reamostragem por cenário | 0,685 a 0,939 |
| Relatos com pontuação e margem acima dos limites de revisão | 18 de 160 |
| Casos ambíguos ou fora do escopo sinalizados para revisão | 11 de 12 |

O modelo selecionado combina TF-IDF de palavras e caracteres com regressão logística. A política de revisão priorizou precisão na validação. No teste, todos os 18 relatos que passaram pelos limites receberam a categoria correta, mas a cobertura foi baixa. Entre os casos de desafio, o modelo deixou passar um relato que misturava alagamento e galhos quebrados. O operador confere o encaminhamento mesmo quando a sugestão está acima do limite.

Os números descrevem a simulação. A validação com relatos de campo e a estimativa do efeito sobre o tempo de triagem ficam para o piloto.

![Matriz de confusão do conjunto de teste](reports/confusion_matrix.png)

## Reproduzir e integrar

- [Notebook executado](notebooks/01_classificacao_relatos.ipynb) com análise da base, comparação, matriz, casos de erro e chamada à API. No editor, selecione o Python de `.venv` e execute as células em ordem.
- [Origem e estrutura da base](data/README.md), [métricas em JSON](reports/metrics.json) e [erros do teste](reports/errors.csv).
- `zela-ml dataset` recria o CSV. `zela-ml train` treina o modelo e atualiza os resultados e o manifesto de integridade. Use o artefato do repositório ou do próprio treino.
- A documentação em `/docs`, a avaliação em `/model` e a classificação em `POST /classify` exigem uma sessão da equipe. `POST /classify` recebe `{"text": "..."}` e devolve as categorias, pontuações, termos associados e `requires_review`. O cidadão usa as rotas de ocorrência, e a sugestão de categoria aparece na revisão da equipe.

Para demonstrar uma versão, use o commit revisado com seu respectivo artefato e manifesto. O retorno a uma versão anterior usa o conjunto desses arquivos do commit escolhido. [Fluxo de desenvolvimento](CONTRIBUTING.md) · [Roteiro da apresentação](docs/apresentacao.md).
