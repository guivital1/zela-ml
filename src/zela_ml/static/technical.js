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
