"""Monta o caderno reproduzível do experimento."""

from pathlib import Path
from textwrap import dedent

import nbformat as nbf

root = Path(__file__).resolve().parents[1]
notebook = nbf.v4.new_notebook()


def markdown(text):
    return nbf.v4.new_markdown_cell(dedent(text).strip())


def code(text):
    return nbf.v4.new_code_cell(dedent(text).strip())


notebook.cells = [
    markdown("""
        # ZELA · Classificação de relatos urbanos

        **Global Solution 2026 · CitizenTech · Engenharia de Software · FIAP**

        O morador descreve um problema da rua. Um representante do bairro precisa
        identificar o tipo de serviço, revisar o relato e preparar o encaminhamento.
        Este experimento sugere a categoria a partir do texto e sinaliza casos que
        merecem conferência adicional.

        **Público** — moradores, trabalhadores do bairro e operadores da ouvidoria.

        **Escopo** — seis categorias de zeladoria. A delimitação da cidade, do bairro
        e a pesquisa com uma pessoa beneficiada serão preenchidas na etapa de campo.

        **Origem dos dados** — simulação controlada, com 180 cenários descritos em
        `data/scenarios.json`. Os resultados representam este conjunto sintético.

        **Como executar** — instale `requirements.txt`, instale o pacote com
        `python -m pip install -e . --no-deps` e execute as células na ordem.
        O repositório já inclui o modelo treinado e os resultados desta execução.
    """),
    markdown("""
        ## 1. Ambiente e reprodutibilidade

        Fixamos a semente em 42. A versão das bibliotecas está no arquivo de
        dependências e o manifesto guarda o hash SHA-256 do modelo e do dataset.
        O treino, a demonstração e a API reutilizam o mesmo pacote Python.
    """),
    code("""
        %matplotlib inline
        from pathlib import Path
        import sys
        import json
        import pandas as pd
        import matplotlib.pyplot as plt
        from IPython.display import display, Image

        ROOT = Path.cwd()
        if not (ROOT / 'pyproject.toml').exists():
            ROOT = ROOT.parent
        assert (ROOT / 'pyproject.toml').exists(), 'Abra o notebook dentro do repositório.'
        sys.path.insert(0, str(ROOT / 'src'))

        from zela_ml.dataset import build_dataset, validate_dataset
        from zela_ml.settings import CATEGORIES, REPORTS, SEED
        from zela_ml.training import train

        print(f'Semente do experimento: {SEED}')
        print(f'Categorias: {len(CATEGORIES)}')
    """),
    markdown("""
        ## 2. Dados e unidade de separação

        Cada cenário recebe variações de escrita, como retirada de acentos,
        abreviação, saudação e contexto adicional. Todas as variações permanecem na
        mesma partição. A divisão por categoria reserva 18 cenários para treino,
        6 para validação e 6 para teste.

        A unidade independente desta simulação é o cenário. Aumentar a quantidade
        de variações aumenta as linhas, mas mantém a diversidade limitada ao
        catálogo original.
    """),
    code("""
        data = build_dataset()
        validate_dataset(data)
        display(data.sample(6, random_state=SEED)[['text', 'category', 'split', 'source']])
        display(pd.crosstab(data['category'], data['split']))
        print(f'{len(data)} relatos simulados · {data.scenario.nunique()} cenários')
    """),
    code("""
        groups = {split: set(part.scenario) for split, part in data.groupby('split')}
        assert groups['train'].isdisjoint(groups['validation'])
        assert groups['train'].isdisjoint(groups['test'])
        assert groups['validation'].isdisjoint(groups['test'])
        display(data.groupby('split').agg(relatos=('id', 'size'), cenarios=('scenario', 'nunique')))
        data.assign(characters=data.text.str.len()).boxplot(column='characters', by='split')
        plt.title('Comprimento dos relatos simulados')
        plt.suptitle('')
        plt.xlabel('Partição')
        plt.ylabel('Caracteres')
        plt.tight_layout()
        plt.show()
    """),
    markdown("""
        ## 3. Preparação e modelos comparados

        O TF-IDF aprende o vocabulário somente no treino, dentro de um Pipeline.
        A normalização de caixa e acentos é aplicada pelo mesmo transformador na
        inferência. Comparamos uma referência pela frequência das classes, duas
        regressões logísticas com TF-IDF de palavras e uma combinação de palavras
        com n-gramas de caracteres.

        Caracteres ajudam a compartilhar informação entre flexões e abreviações.
        A regressão logística permite inspecionar os pesos associados à sugestão.
        A seleção usa F1 macro na validação, com desempate por log loss.

        O limite da pontuação e a margem entre as duas primeiras categorias também
        são escolhidos na validação. Para isso, usamos os 12 casos de revisão
        reservados em `data/probes.csv`. O teste fica reservado até essas decisões.
    """),
    code("""
        metrics = train()
        comparison = pd.read_csv(REPORTS / 'validation_models.csv')
        display(comparison)
        print('Modelo selecionado:', metrics['selected_model'])
        print('Política de revisão:', metrics['review_policy'])
    """),
    markdown("""
        ## 4. Avaliação no teste separado

        F1 macro dá o mesmo peso às seis categorias. A matriz de confusão mostra os
        tipos de erro, e a taxa de cenários inteiramente corretos exige acerto em
        todas as variações de cada situação. O intervalo de 95% usa 1.000
        reamostragens por cenário, preservando a correlação entre variações.
        Seu alcance é a incerteza dentro desta simulação.
    """),
    code("""
        display(pd.DataFrame({
            'referência no teste': metrics['baseline_test'],
            'modelo no teste': metrics['test'],
        }).T)
        interval = metrics['test_f1_macro_ci95']
        print(f"F1 macro: {metrics['test']['f1_macro']:.3f}")
        print(f"Intervalo por cenário: {interval['low']:.3f} a {interval['high']:.3f}")
        report = json.loads((REPORTS / 'classification_report.json').read_text())
        display(pd.DataFrame(report).T)
        display(Image(filename=str(REPORTS / 'confusion_matrix.png')))
    """),
    markdown("""
        ## 5. Análise de erros

        Inspecionamos um exemplo de cada cenário com erro. Relatos que mencionam
        vários objetos ou negam um problema podem confundir um classificador
        lexical. O CSV de erros inclui todas as variações para análise posterior.

        Os casos do teste permanecem congelados. Melhorias futuras serão escolhidas
        na validação e exigirão um novo teste independente para uma nova estimativa.
    """),
    code("""
        errors = pd.read_csv(REPORTS / 'errors.csv')
        display(errors.drop_duplicates('scenario')[['text', 'category', 'predicted', 'score']])
        print(f'{len(errors)} variações com erro em {errors.scenario.nunique()} cenários')
    """),
    markdown("""
        ## 6. Cobertura, revisão e casos difíceis

        A sugestão sempre fica disponível ao operador. O marcador de revisão sinaliza
        pontuação baixa ou pouca diferença entre as categorias mais prováveis.
        A política foi escolhida na validação para preservar a precisão, o que
        pode reduzir bastante a cobertura das sugestões com marcador favorável.

        O conjunto adicional de teste contém 12 relatos fora do escopo, vagos ou
        com vários serviços. Ele permite observar falhas que a acurácia usual
        deixa de representar. Uma pontuação elevada pode ocorrer em um relato
        inadequado. A conferência do encaminhamento continua com o operador.
    """),
    code("""
        display(pd.DataFrame([metrics['test_selective']]))
        challenge = pd.read_csv(REPORTS / 'challenge_predictions.csv')
        display(challenge[['text', 'reason', 'suggested', 'score', 'requires_review']])
        print('Resumo dos casos de desafio:', metrics['challenge_test'])
    """),
    markdown("""
        ## 7. Previsão na solução

        A mesma classe usada pelo servidor carrega o artefato versionado e retorna
        três sugestões, pontuações, motivos de revisão e os termos que contribuíram
        positivamente para a primeira categoria. Esses termos representam
        contribuições do modelo linear, com leitura parcial quando há caracteres.
        Na aplicação, a categoria sugerida aparece durante a revisão da equipe.
        O morador acompanha o estado, o protocolo e o histórico da ocorrência.
    """),
    code("""
        from zela_ml.inference import Classifier

        classifier = Classifier()
        examples = [
            'O poste da esquina está apagado e a rua fica escura à noite.',
            'A boca de lobo está entupida e a água está voltando para a rua.',
            'Quero marcar uma consulta com o dentista na próxima semana.',
        ]
        for text in examples:
            prediction = classifier.predict(text)
            display(pd.DataFrame([{
                'relato': text,
                'sugestão': prediction['label'],
                'pontuação': prediction['score'],
                'revisão': prediction['requires_review'],
                'termos': ', '.join(term['term'] for term in prediction['evidence_terms']),
            }]))
    """),
    code("""
        from secrets import token_urlsafe
        from tempfile import TemporaryDirectory
        from httpx import ASGITransport, AsyncClient
        from zela_ml.api import create_app

        password = token_urlsafe(16)
        with TemporaryDirectory() as temp:
            app = create_app(database_path=Path(temp) / 'teste.sqlite3', team_password=password)
            async with app.router.lifespan_context(app):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url='http://teste') as client:
                    denied = await client.post('/classify', json={'text': examples[0]})
                    assert denied.status_code == 401
                    login = await client.post('/api/equipe/entrar', json={'senha': password})
                    assert login.status_code == 200
                    response = await client.post('/classify', json={'text': examples[0]})
                    assert response.status_code == 200
                    display(response.json())
        print('Para testar na interface, execute: zela-ml serve --exemplo --equipe')
    """),
    markdown("""
        ## 8. Próximas decisões de campo

        O piloto deve delimitar um bairro e ouvir moradores e operadores. Os relatos
        coletados precisam de tratamento de dados pessoais, classificação revisada
        e separação por ocorrência. A avaliação futura pode comparar o tempo de
        triagem com e sem a sugestão, mantendo o mesmo conjunto de casos.

        A organização registra o protocolo recebido no canal oficial. A interface
        pública permite registrar o problema e acompanhar seu andamento. Os
        resultados do experimento ficam na Área técnica da equipe.

        **ODS propostos** — 11, pela participação na melhoria dos espaços públicos,
        e 16, pelo acompanhamento dos pedidos e da resposta institucional.

        **Referências técnicas**

        - [scikit-learn — Pipeline e vazamento de dados](https://scikit-learn.org/stable/common_pitfalls.html)
        - [scikit-learn — Métricas de classificação](https://scikit-learn.org/stable/modules/model_evaluation.html)
        - [FastAPI — Testes de integração](https://fastapi.tiangolo.com/tutorial/testing/)
        - [Prefeitura de São Paulo — SP156](https://prefeitura.sp.gov.br/web/pinheiros/w/portal-156)
    """),
]
notebook.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12"},
}
destination = root / "notebooks" / "01_classificacao_relatos.ipynb"
destination.parent.mkdir(exist_ok=True)
nbf.write(notebook, destination)
print(destination.relative_to(root))
