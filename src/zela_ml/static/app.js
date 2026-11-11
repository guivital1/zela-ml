const element = id => document.getElementById(id);
const views = document.querySelectorAll('[data-screen]');
const links = document.querySelectorAll('[data-nav]');
const formatDate = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium', timeStyle: 'short' });
const simplify = text => text.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/\p{M}/gu, '');

let categories = {};
let team = false;
let items = [];
let filter = '';
let detail;
let revision = 0;
let reportKey;
let savingReport = false;
let nextMessage = '';
let queueFilter = 'revisao';
let queueItems = [];

class RequestError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : 'Confira os campos e tente novamente.');
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, method = 'GET', payload) {
  const options = { method, headers: {} };
  if (payload !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(payload);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error('Não foi possível se conectar. Tente novamente.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new RequestError(response.status, data?.detail || 'Não foi possível concluir a ação. Tente novamente.');
  if (data === null) throw new Error('Não foi possível carregar as informações. Tente novamente.');
  return data;
}

function message(id, text = '') {
  const node = element(id);
  node.textContent = text;
  node.hidden = !text;
}

function screen(name, active) {
  for (const view of views) view.hidden = view.dataset.screen !== name;
  for (const link of links) {
    if (link.dataset.nav === active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

function showCategories(select, selected = '') {
  const options = [new Option('Escolha uma opção', '')];
  for (const [key, label] of Object.entries(categories)) {
    options.push(new Option(label, key));
  }
  select.replaceChildren(...options);
  select.value = selected;
}

function plural(count, single, multiple) {
  return `${count} ${count === 1 ? single : multiple}`;
}

function badge(node, item) {
  node.className = `status ${item.estado}`;
  node.textContent = item.situacao;
}

function card(item, queue = false) {
  const node = element('ocorrencia-card').content.firstElementChild.cloneNode(true);
  node.href = `#ocorrencia/${item.id}`;
  const field = name => node.querySelector(`[data-item="${name}"]`);
  field('tipo').textContent = item.tipo;
  field('local').textContent = item.local;
  field('descricao').textContent = item.descricao;
  field('codigo').textContent = item.codigo;
  const days = Math.max(0, Math.floor((Date.now() - Date.parse(item.criado_em)) / 86400000));
  field('confirmacoes').textContent = queue && item.estado !== 'resolvida'
    ? (days ? `Aberta há ${plural(days, 'dia', 'dias')}` : 'Aberta hoje')
    : plural(item.confirmacoes, 'confirmação', 'confirmações');
  badge(field('estado'), item);
  return node;
}

function showCards(target, records, empty, queue = false) {
  target.replaceChildren(...records.map(item => card(item, queue)));
  if (!records.length) {
    const note = document.createElement('p');
    note.className = 'placeholder';
    note.textContent = empty;
    target.append(note);
  }
}

function drawQueue() {
  const visible = queueItems.filter(item => (
    queueFilter === 'revisao'
      ? item.estado === 'registrada' || item.estado === 'reaberta'
      : item.estado === queueFilter
  ));
  if (queueFilter === 'revisao') {
    visible.sort((a, b) => Number(b.estado === 'reaberta') - Number(a.estado === 'reaberta') ||
      a.criado_em.localeCompare(b.criado_em) || a.id - b.id);
  }
  showCards(element('equipe-lista'), visible, 'Nenhuma ocorrência nesta etapa.', true);
}

function drawList() {
  const query = simplify(element('busca').value.trim());
  const visible = items.filter(item => (
    (!filter || item.estado === filter) &&
    simplify(`${item.local} ${item.codigo} ${item.tipo} ${item.descricao}`).includes(query)
  ));
  element('contagem').textContent = plural(visible.length, 'ocorrência', 'ocorrências');
  const empty = query || filter ? 'Nenhuma ocorrência combina com a busca.'
    : location.hash === '#acompanhando' ? 'Os relatos que você registrar ou confirmar aparecem aqui.'
    : 'Ainda não há ocorrências. Use Novo relato para registrar a primeira.';
  showCards(element('lista'), visible, empty);
}

async function loadList(mine) {
  const data = await request(`/api/ocorrencias${mine ? '?minhas=true' : ''}`);
  categories = data.categorias;
  element('demo-label').hidden = !data.exemplo;
  return data.ocorrencias;
}

function showDetail(item) {
  detail = item;
  element('detalhe-voltar').href = team ? '#equipe' : '#ocorrencias';
  element('detalhe-voltar').textContent = team ? '← Fila da equipe' : '← Ocorrências';
  element('detalhe-titulo').textContent = item.tipo === 'A identificar' ? 'Ocorrência' : item.tipo;
  element('detalhe-codigo').textContent = item.codigo;
  element('detalhe-local').textContent = item.local;
  element('detalhe-descricao').textContent = item.descricao;
  element('detalhe-confirmacoes').textContent = plural(item.confirmacoes, 'confirmação', 'confirmações');
  badge(element('detalhe-estado'), item);

  const photo = element('detalhe-foto');
  photo.hidden = !item.tem_foto;
  if (item.tem_foto) photo.src = `/api/ocorrencias/${item.id}/foto`;
  else photo.removeAttribute('src');

  element('confirmar').hidden = Boolean(item.confirmou) || item.estado === 'resolvida';
  element('detalhe-acompanhando').hidden = !item.confirmou;
  message('detalhe-protocolo', item.protocolo ? `Protocolo ${item.protocolo}` : '');

  const timeline = element('historico');
  timeline.replaceChildren();
  for (const event of item.historico.slice().reverse()) {
    const entry = document.createElement('li');
    const title = document.createElement('strong');
    const date = document.createElement('time');
    title.textContent = event.situacao;
    date.dateTime = event.criado_em;
    date.textContent = formatDate.format(new Date(event.criado_em));
    entry.append(title, date);
    if (event.nota) {
      const note = document.createElement('p');
      note.textContent = event.nota;
      entry.append(note);
    }
    if (event.protocolo && event.protocolo !== item.protocolo) {
      const protocol = document.createElement('p');
      protocol.textContent = `Protocolo ${event.protocolo}`;
      entry.append(protocol);
    }
    if (event.tem_foto) {
      const picture = document.createElement('img');
      picture.className = 'report-photo';
      picture.alt = 'Foto enviada no retorno sobre o reparo';
      picture.loading = 'lazy';
      picture.src = `/api/ocorrencias/${item.id}/retornos/${event.id}/foto`;
      entry.append(picture);
    }
    timeline.append(entry);
  }

  element('retorno').hidden = team || !item.fechamento || item.retorno_enviado;
  element('retorno-form').hidden = true;
  element('retorno-form').reset();
  element('ainda-acontece').setAttribute('aria-expanded', 'false');
  message('retorno-erro');

  const update = element('andamento-form');
  update.hidden = !team;
  if (!update.hidden) {
    update.reset();
    const stage = element('mudanca-andamento');
    stage.hidden = item.estado === 'resolvida';
    stage.disabled = stage.hidden;
    showCategories(element('equipe-categoria'), item.categoria || item.sugestao || '');
    const states = [new Option('Resolvida', 'resolvida')];
    if (item.estado === 'registrada' || item.estado === 'reaberta') {
      states.unshift(new Option('Encaminhada', 'encaminhada'));
    }
    element('novo-estado').replaceChildren(...states);
    element('protocolo').value = item.estado === 'reaberta' ? item.protocolo || '' : '';
    message('sugestao', item.sugestao
      ? `Sugestão do modelo: ${categories[item.sugestao]}.` : '');
    element('revisar-categoria').textContent = item.categoria_revisada
      ? 'Salvar categoria' : 'Confirmar categoria';
    adjustUpdate();
  }
}

function adjustUpdate() {
  const forwarded = element('novo-estado').value === 'encaminhada';
  element('protocolo-campo').hidden = !forwarded;
  element('protocolo').required = forwarded;
  element('protocolo').disabled = !forwarded;
  element('nota').required = !forwarded;
}

async function route() {
  const current = ++revision;
  const hash = location.hash.slice(1);
  const detailId = /^ocorrencia\/(\d+)$/.exec(hash)?.[1];
  message('falha');
  message('mensagem', nextMessage);
  nextMessage = '';
  try {
    if (hash === 'novo') {
      if (!Object.keys(categories).length) await loadList(false);
      if (current !== revision) return;
      const category = element('categoria');
      showCategories(category, category.value);
      screen('novo', 'ocorrencias');
      return;
    }

    if (hash === 'equipe') {
      screen('equipe', 'equipe');
      element('equipe-painel').hidden = true;
      element('entrar-form').hidden = true;
      const session = await request('/api/equipe');
      if (current !== revision) return;
      team = session.autorizado;
      element('entrar-form').hidden = team;
      if (team) {
        const records = await loadList(false);
        if (current !== revision) return;
        element('equipe-painel').hidden = false;
        queueItems = records;
        drawQueue();
      }
      return;
    }

    if (detailId) {
      const records = await Promise.all([
        request(`/api/ocorrencias/${detailId}`), request('/api/equipe'),
        Object.keys(categories).length ? null : loadList(false),
      ]);
      if (current !== revision) return;
      team = records[1].autorizado;
      message('detalhe-erro');
      message('andamento-erro');
      showDetail(records[0]);
      screen('detalhe', team ? 'equipe' : 'ocorrencias');
      return;
    }

    const mine = hash === 'acompanhando';
    screen('lista', mine ? 'acompanhando' : 'ocorrencias');
    element('lista-titulo').textContent = mine ? 'Acompanhando' : 'Ocorrências do bairro';
    element('lista-legenda').textContent = mine
      ? 'Veja o andamento dos relatos que você registrou ou confirmou neste navegador.'
      : 'Veja o que precisa de atenção e acompanhe o andamento.';
    showCards(element('lista'), [], 'Carregando ocorrências…');
    element('contagem').textContent = '';
    const records = await loadList(mine);
    if (current !== revision) return;
    items = records;
    drawList();
  } catch (error) {
    if (current === revision) message('falha', error.message);
  }
}

function navigate(hash, feedback = '') {
  nextMessage = feedback;
  if (location.hash === hash) route();
  else location.hash = hash;
}

element('filtros').addEventListener('click', event => {
  const button = event.target.closest('[data-filter]');
  if (!button) return;
  filter = button.dataset.filter;
  for (const item of element('filtros').querySelectorAll('button')) {
    item.setAttribute('aria-pressed', String(item === button));
  }
  drawList();
});

element('equipe-filtros').addEventListener('click', event => {
  const button = event.target.closest('[data-queue]');
  if (!button) return;
  queueFilter = button.dataset.queue;
  for (const item of element('equipe-filtros').querySelectorAll('button')) {
    item.setAttribute('aria-pressed', String(item === button));
  }
  drawQueue();
});

element('busca').addEventListener('input', () => {
  if (!document.querySelector('[data-screen="lista"]').hidden) drawList();
});
element('busca-form').addEventListener('submit', event => {
  event.preventDefault();
  if (document.querySelector('[data-screen="lista"]').hidden) navigate('#ocorrencias');
  else drawList();
});

function readPhoto(id = 'foto') {
  const file = element(id).files[0];
  if (!file) return Promise.resolve(null);
  if (file.size > 2 * 1024 * 1024) return Promise.reject(new Error('Escolha uma foto de até 2 MB.'));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = () => reject(new Error('Não foi possível abrir a foto. Escolha outra.'));
    reader.readAsDataURL(file);
  });
}

const report = element('relato-form');
report.addEventListener('input', () => {
  if (!savingReport) reportKey = undefined;
  element('duplicatas').hidden = true;
  message('relato-erro');
});

async function saveReport(separate = false) {
  if (savingReport || !report.reportValidity()) return;
  savingReport = true;
  const submit = report.querySelector('button[type="submit"]');
  submit.disabled = true;
  const separateButton = element('outro-problema');
  separateButton.disabled = true;
  message('relato-erro');
  try {
    reportKey ??= crypto.randomUUID();
    const payload = {
      pedido: reportKey,
      rua: element('local').value,
      numero: element('numero').value,
      bairro: element('bairro').value,
      descricao: element('descricao').value,
      categoria: element('categoria').value || null,
      outro_problema: separate,
    };
    payload.foto = await readPhoto();
    const item = await request('/api/ocorrencias', 'POST', payload);
    report.reset();
    reportKey = undefined;
    element('duplicatas').hidden = true;
    navigate(`#ocorrencia/${item.id}`, 'Relato registrado. Acompanhe o andamento nesta página.');
  } catch (error) {
    const matches = error.detail?.ocorrencias;
    if (error.status === 409 && matches?.length) {
      showCards(element('duplicatas-lista'), matches, '');
      element('duplicatas').hidden = false;
      element('duplicatas').scrollIntoView({ block: 'nearest' });
    } else {
      message('relato-erro', error.message);
    }
  } finally {
    savingReport = false;
    submit.disabled = false;
    separateButton.disabled = false;
  }
}

report.addEventListener('submit', event => {
  event.preventDefault();
  saveReport();
});
element('outro-problema').addEventListener('click', () => saveReport(true));

element('confirmar').addEventListener('click', async event => {
  const id = detail.id;
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const item = await request(`/api/ocorrencias/${id}/confirmar`, 'POST');
    if (detail.id === id) showDetail(item);
    message('mensagem', 'Confirmação registrada. A ocorrência aparece em Acompanhando.');
  } catch (error) {
    message('detalhe-erro', error.message);
  } finally {
    button.disabled = false;
  }
});

element('novo-estado').addEventListener('change', adjustUpdate);

element('ainda-acontece').addEventListener('click', () => {
  const form = element('retorno-form');
  form.hidden = !form.hidden;
  element('ainda-acontece').setAttribute('aria-expanded', String(!form.hidden));
  if (!form.hidden) element('retorno-nota').focus();
});

async function sendFeedback(repaired) {
  const item = detail;
  const buttons = element('retorno').querySelectorAll('button');
  for (const button of buttons) button.disabled = true;
  message('retorno-erro');
  try {
    const updated = await request(`/api/ocorrencias/${item.id}/retorno`, 'POST', {
      fechamento: item.fechamento,
      resolvido: repaired,
      nota: repaired ? null : element('retorno-nota').value.trim(),
      foto: repaired ? null : await readPhoto('retorno-foto'),
    });
    if (detail.id === item.id) showDetail(updated);
    message('mensagem', repaired ? 'Reparo confirmado.' : 'A ocorrência voltou para a equipe.');
  } catch (error) {
    message('retorno-erro', error.message);
  } finally {
    for (const button of buttons) button.disabled = false;
  }
}

element('reparo-confirmado').addEventListener('click', () => sendFeedback(true));
element('retorno-form').addEventListener('submit', event => {
  event.preventDefault();
  sendFeedback(false);
});

element('revisar-categoria').addEventListener('click', async event => {
  const button = event.currentTarget;
  const category = element('equipe-categoria');
  if (!category.reportValidity()) return;
  button.disabled = true;
  message('andamento-erro');
  try {
    const updated = await request(`/api/equipe/ocorrencias/${detail.id}/categoria`, 'PATCH', {
      categoria: category.value,
      versao: detail.versao,
    });
    if (detail.id === updated.id) showDetail(updated);
    message('mensagem', 'Categoria revisada e salva.');
  } catch (error) {
    if (error.status === 401) navigate('#equipe');
    else message('andamento-erro', error.message);
  } finally {
    button.disabled = false;
  }
});

element('copiar').addEventListener('click', async () => {
  const category = categories[element('equipe-categoria').value] || detail.tipo;
  const text = `Solicitação de zeladoria: ${category}\nLocal: ${detail.local}\n${detail.descricao}`;
  try {
    await navigator.clipboard.writeText(text);
    message('mensagem', 'Pedido copiado para encaminhar pelo canal do município.');
  } catch {
    message('andamento-erro', 'O navegador não permitiu copiar. Use a descrição e o endereço acima.');
  }
});

element('andamento-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  message('andamento-erro');
  try {
    const updated = await request(`/api/equipe/ocorrencias/${detail.id}`, 'PATCH', {
      estado_anterior: detail.estado,
      versao: detail.versao,
      estado: element('novo-estado').value,
      categoria: element('equipe-categoria').value,
      protocolo: element('protocolo').value || null,
      nota: element('nota').value || null,
    });
    if (detail.id === updated.id) showDetail(updated);
    message('mensagem', 'Andamento atualizado.');
  } catch (error) {
    if (error.status === 401) navigate('#equipe');
    else message('andamento-erro', error.message);
  } finally {
    button.disabled = false;
  }
});

element('entrar-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  message('entrar-erro');
  try {
    await request('/api/equipe/entrar', 'POST', { senha: element('senha').value });
    element('senha').value = '';
    await route();
  } catch (error) {
    message('entrar-erro', error.message);
  } finally {
    button.disabled = false;
  }
});
element('sair').addEventListener('click', async () => {
  try {
    await request('/api/equipe/sair', 'POST');
    team = false;
    await route();
  } catch (error) {
    message('falha', error.message);
  }
});

window.addEventListener('hashchange', () => {
  window.scrollTo(0, 0);
  route();
});
route();
