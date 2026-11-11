const form = document.querySelector('#report-form');
const input = document.querySelector('#report');
const submit = document.querySelector('#submit');
const result = document.querySelector('#result');
const placeholder = document.querySelector('#result-placeholder');
const errorBox = document.querySelector('#error');
let controller;

const percentage = value => new Intl.NumberFormat('pt-BR', {
  style: 'percent', maximumFractionDigits: 1
}).format(value);

function resetResult() {
  controller?.abort();
  submit.disabled = false;
  submit.textContent = 'Analisar relato';
  result.hidden = true;
  placeholder.hidden = false;
  placeholder.textContent = 'Analise um relato para ver as categorias sugeridas.';
  errorBox.hidden = true;
  document.querySelector('#counter').textContent = `${input.value.length} / 2.000`;
}

input.addEventListener('input', resetResult);
document.querySelector('#examples').addEventListener('click', event => {
  const example = event.target.closest('button[data-text]');
  if (example) {
    input.value = example.dataset.text;
    resetResult();
    input.focus();
  }
});

function showResult(data) {
  const status = document.querySelector('#review-status');
  status.textContent = data.requires_review ? 'Revisão necessária' : 'Sugestão disponível';
  status.classList.toggle('review', data.requires_review);
  document.querySelector('#category').textContent = data.requires_review
    ? 'Confirme a categoria' : data.label;
  document.querySelector('#result-note').textContent = data.requires_review
    ? data.review_reasons.join(' ')
    : 'Confira a descrição e confirme a categoria durante a triagem.';
  const suggestions = document.querySelector('#suggestions');
  suggestions.replaceChildren();
  for (const suggestion of data.suggestions) {
    const row = document.createElement('div');
    row.className = 'suggestion';
    const label = document.createElement('div');
    label.className = 'suggestion-label';
    const name = document.createElement('span');
    name.textContent = suggestion.label;
    const score = document.createElement('span');
    score.textContent = percentage(suggestion.score);
    label.append(name, score);
    const bar = document.createElement('div');
    bar.className = 'bar';
    const fill = document.createElement('span');
    fill.style.width = `${suggestion.score * 100}%`;
    bar.append(fill);
    row.append(label, bar);
    suggestions.append(row);
  }
  const evidence = document.querySelector('#evidence');
  evidence.replaceChildren();
  for (const item of data.evidence_terms) {
    const term = document.createElement('span');
    term.textContent = item.term;
    evidence.append(term);
  }
  if (!data.evidence_terms.length) evidence.textContent = 'Poucos termos informativos neste relato.';
  result.hidden = false;
  placeholder.hidden = true;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  resetResult();
  const current = new AbortController();
  controller = current;
  submit.disabled = true;
  submit.textContent = 'Analisando…';
  placeholder.textContent = 'Analisando relato…';
  try {
    const response = await fetch('/classify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: input.value }), signal: current.signal
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string'
        ? data.detail : 'Revise a descrição. Inclua pelo menos 8 letras e 12 caracteres.');
    }
    if (!current.signal.aborted) showResult(data);
  } catch (error) {
    if (error.name !== 'AbortError' && !current.signal.aborted) {
      errorBox.textContent = error.message === 'Failed to fetch'
        ? 'A conexão com o modelo falhou. Verifique o servidor e tente novamente.'
        : error.message;
      errorBox.hidden = false;
      placeholder.textContent = 'A análise está disponível após corrigir o relato.';
    }
  } finally {
    if (controller === current) {
      submit.disabled = false;
      submit.textContent = 'Analisar relato';
    }
  }
});

async function loadMetrics() {
  try {
    const response = await fetch('/model');
    if (!response.ok) throw new Error('Modelo indisponível');
    const { metrics } = await response.json();
    document.querySelector('#f1').textContent = percentage(metrics.test.f1_macro);
    document.querySelector('#test-scenarios').textContent = metrics.split_scenarios.test;
    document.querySelector('#dataset-size').textContent = metrics.rows;
  } catch {
    document.querySelector('#f1').textContent = 'Indisponível';
  }
}

loadMetrics();

const views = document.querySelectorAll('[data-screen]');
const links = document.querySelectorAll('[data-nav]');

function showScreen() {
  const screen = location.hash === '#avaliacao' ? 'avaliacao' : 'triagem';
  for (const view of views) view.hidden = view.dataset.screen !== screen;
  for (const link of links) {
    if (link.dataset.nav === screen) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

window.addEventListener('hashchange', () => {
  showScreen();
  window.scrollTo(0, 0);
});
showScreen();

const dialog = document.querySelector('#search-dialog');
const query = document.querySelector('#search-query');
const searchResults = document.querySelector('#search-results');
const scenarios = Array.from(document.querySelectorAll('#examples [data-text]'));
const actions = [
  { title: 'Triagem', screen: 'triagem' },
  { title: 'Avaliação', screen: 'avaliacao' },
  ...scenarios.map(button => ({ title: button.textContent, screen: 'triagem', text: button.dataset.text }))
];
const simplify = text => text.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/\p{M}/gu, '');

function renderSearch() {
  const search = simplify(query.value.trim());
  const matches = actions.filter(action => simplify(action.title).includes(search));
  searchResults.replaceChildren();
  for (const action of matches) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = action.title;
    button.addEventListener('click', () => {
      dialog.close();
      location.hash = action.screen;
      showScreen();
      if (action.text) {
        input.value = action.text;
        resetResult();
        input.focus();
      }
    });
    searchResults.append(button);
  }
  if (!matches.length) searchResults.textContent = 'Nenhum resultado para essa busca.';
}

function openSearch() {
  query.value = '';
  renderSearch();
  dialog.showModal();
  query.focus();
}

query.addEventListener('input', renderSearch);
document.querySelector('#quick-search').addEventListener('click', openSearch);
document.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && !dialog.open) {
    event.preventDefault();
    openSearch();
  }
});
