async function loadMetrics() {
  const errorBox = document.getElementById('metrics-error');
  try {
    const response = await fetch('/model');
    if (!response.ok) throw new Error('A avaliação está indisponível. Verifique seu acesso.');
    const { metrics } = await response.json();
    document.getElementById('f1').textContent = metrics.test.f1_macro.toFixed(3).replace('.', ',');
    document.getElementById('test-scenarios').textContent = metrics.split_scenarios.test;
    document.getElementById('dataset-size').textContent = metrics.rows;
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  }
}

loadMetrics();

async function loadReviews() {
  const description = document.getElementById('review-description');
  try {
    const response = await fetch('/api/equipe/avaliacao');
    if (!response.ok) throw new Error('A avaliação das revisões está indisponível.');
    const { exemplo, modelos, correcoes } = await response.json();
    const source = exemplo ? 'Bairro de exemplo.' : 'Relatos cadastrados neste ambiente.';
    description.textContent = modelos.length
      ? `${source} A comparação usa a última categoria revisada em cada ocorrência.`
      : `${source} Ainda não há categorias revisadas pela equipe.`;
    const results = document.getElementById('review-results');
    for (const model of modelos) {
      const line = document.createElement('li');
      const version = model.modelo ? `Modelo ${model.modelo}` : 'Sem versão registrada';
      line.textContent = `${version} · ${model.revisadas} revisadas · ${model.confirmadas} confirmadas · ${model.com_sugestao - model.confirmadas} corrigidas · ${model.revisadas - model.com_sugestao} sem sugestão`;
      results.append(line);
    }
    const list = document.getElementById('correcoes-lista');
    for (const correction of correcoes) {
      const line = document.createElement('li');
      const link = document.createElement('a');
      link.href = `/#ocorrencia/${correction.id}`;
      link.textContent = correction.codigo;
      line.append(link, ` · ${correction.sugestao} → ${correction.categoria}`);
      list.append(line);
    }
    document.getElementById('correcoes').hidden = !correcoes.length;
  } catch (error) {
    description.textContent = error.message;
  }
}

loadReviews();
