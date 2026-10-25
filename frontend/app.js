let state = window.UdyamStore.load();
let wizardStep = 0;
let wizardAnswers = { business: '', products: '', tracking: '', next: '' };
let showAllTransactions = false;
let pendingPlan = [];
let scenarioMerchantId = '';
let backendAiMode = 'demo';
let campaignDraftSource = 'demo';
let businessInsights = [];
let inventoryRisks = [];
let trackedOutcomes = [];
let insightLoading = false;
let insightError = '';

function saveState() {
  if (window.UdyamAPI.connected()) window.UdyamStore.savePreferences();
  else window.UdyamStore.save();
}

function applyBackendRecords(records, merchantId) {
  const products = records.products.map(product => ({
    id: product.id,
    name: product.name,
    category: product.category || '',
    quantity: product.quantity,
    cost: product.cost === null ? null : Number(product.cost),
    price: product.price === null ? null : Number(product.price),
    supplierLeadTimeDays: product.supplier_lead_time_days
  }));
  const productNames = new Map(products.map(product => [product.id, product.name]));
  const sales = records.sales.map(sale => ({
    id: sale.id,
    amount: Number(sale.amount),
    date: sale.date,
    note: sale.note,
    productId: sale.product_id || undefined,
    productName: productNames.get(sale.product_id) || '',
    quantity: sale.quantity,
    unitPrice: sale.unit_price === null ? null : Number(sale.unit_price),
    costOfGoods: sale.cost_of_goods === null ? null : Number(sale.cost_of_goods),
    source: sale.source
  }));
  const expenses = records.expenses.map(expense => ({
    id: expense.id,
    amount: Number(expense.amount),
    date: expense.date,
    note: expense.note,
    category: expense.category,
    source: expense.source
  }));
  const scenarios = records.scenarios.map(item => {
    const parameters = JSON.parse(item.parameters);
    const result = JSON.parse(item.result);
    return {
      id: item.id,
      quantity: parameters.extra_stock,
      cost: Number(parameters.cost),
      price: Number(parameters.price),
      inventory: parameters.available_inventory,
      demand: parameters.demand_per_day,
      period: parameters.period,
      discount: Number(parameters.discount),
      savedAt: item.created_at.slice(0, 10),
      outcomes: {
        revenue: Number(result.proposed.revenue),
        grossProfit: Number(result.proposed.gross_profit),
        unsold: result.proposed.unsold_units
      }
    };
  });
  state.currentMerchantId = merchantId;
  state.name = records.merchant.name;
  state.category = records.merchant.category;
  state.products = products;
  state.sales = sales;
  state.expenses = expenses;
  state.transactions = [
    ...sales.map(sale => ({ ...sale, type: 'sale' })),
    ...expenses.map(expense => ({ ...expense, type: 'expense' }))
  ].sort((a, b) => b.date.localeCompare(a.date));
  state.campaigns = records.campaigns.map(campaign => ({
    id: campaign.id,
    productId: campaign.product_id || '',
    productName: productNames.get(campaign.product_id) || '',
    objective: campaign.objective,
    offer: campaign.offer,
    copy: campaign.copy,
    status: campaign.status,
    createdAt: campaign.created_at.slice(0, 10)
  }));
  state.tasks = records.tasks.map(task => ({
    id: task.id,
    title: task.title,
    goal: task.goal,
    requiresApproval: task.requires_approval,
    approved: ['approved', 'in_progress', 'completed'].includes(task.status),
    completed: task.status === 'completed',
    rejected: task.status === 'rejected',
    status: task.status
  }));
  state.scenarios = scenarios;
  businessInsights = records.insights || [];
  inventoryRisks = [];
  trackedOutcomes = records.outcomes || [];
  saveState();
  render();
}

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const money = value => new Intl.NumberFormat(state.language === 'hi' ? 'en-IN' : 'en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value);
const today = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
const total = (items, date) => items.filter(item => !date || item.date === date).reduce((sum, item) => sum + item.amount, 0);

window.addEventListener('udyam:storage-error', () => showToast('Could not save your changes on this device.'));

function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 2800);
}

function renderBusinessPulse() {
  const status = $('#pulseStatus');
  const missing = $('#pulseMissing');
  const list = $('#pulseList');
  const refresh = $('#refreshPulse');
  list.replaceChildren();
  missing.replaceChildren();
  missing.hidden = true;
  refresh.disabled = insightLoading || !window.UdyamAPI.connected();
  refresh.textContent = insightLoading ? 'Checking your records…' : 'Check for updates';
  if (!window.UdyamAPI.connected()) {
    status.textContent = 'Connect your business records in Settings to check for personalized changes and stock risks.';
    return;
  }
  if (insightError) {
    status.textContent = `Could not check your records: ${insightError}`;
    return;
  }
  if (insightLoading) {
    status.textContent = 'Checking recent sales, expenses and stock records…';
    return;
  }
  const visible = businessInsights
    .filter(item => item.status !== 'dismissed')
    .slice(0, state.mode === 'simple' ? 2 : state.mode === 'smart' ? 3 : 5);
  const unread = businessInsights.filter(item => item.status === 'unread').length;
  status.textContent = visible.length
    ? `${unread} new insight${unread === 1 ? '' : 's'} · based on ${state.sample ? 'illustrative demo records' : 'your recorded data'}`
    : state.sample
      ? 'No supported changes found in this sample. Example data is illustrative, not a forecast.'
      : 'No supported changes yet. Record sales on different days and add stock counts to unlock evidence-based insights.';
  if (businessInsights.some(item => item.evaluated_at && Date.now() - new Date(item.evaluated_at).getTime() > 86400000)) {
    const stale = document.createElement('p');
    stale.textContent = 'Some saved insights have not been checked in over a day. Select “Check for updates” to re-evaluate current records.';
    missing.append(stale);
    missing.hidden = false;
  }
  visible.forEach(insight => {
    const card = document.createElement('article');
    card.className = `pulse-card priority-${insight.priority >= 80 ? 'high' : 'normal'}`;
    const header = document.createElement('div');
    header.className = 'pulse-card-heading';
    const title = document.createElement('h3');
    title.textContent = insight.headline;
    const badge = document.createElement('span');
    badge.className = 'pulse-confidence';
    badge.textContent = `${insight.confidence} confidence · ${insight.data_quality} data`;
    header.append(title, badge);
    const observed = document.createElement('p');
    observed.textContent = insight.observed;
    const evidence = document.createElement('ul');
    insight.evidence.forEach(entry => {
      const item = document.createElement('li');
      item.textContent = entry;
      evidence.append(item);
    });
    const period = document.createElement('small');
    period.className = 'pulse-period';
    period.textContent = `Comparison: ${insight.comparison_period}`;
    const reason = document.createElement('p');
    reason.className = 'pulse-reason';
    reason.textContent = insight.why_it_matters;
    const nextAction = document.createElement('p');
    nextAction.className = 'pulse-next-action';
    nextAction.textContent = `Next: ${insight.next_action}`;
    const freshness = document.createElement('small');
    freshness.className = 'pulse-period';
    freshness.textContent = insight.is_active
      ? 'Current on the latest analysis.'
      : 'Saved from an earlier analysis; check current records before acting.';
    const actions = document.createElement('div');
    actions.className = 'pulse-actions';
    if (['inventory_risk', 'low_margin'].includes(insight.kind)) {
      const investigate = document.createElement('button');
      investigate.type = 'button';
      investigate.className = 'outline-button';
      investigate.textContent = 'Compare in Business Twin';
      investigate.addEventListener('click', () => investigateInsight(insight));
      actions.append(investigate);
    }
    if (!state.sample) {
      const track = document.createElement('button');
      track.type = 'button';
      track.className = 'outline-button';
      track.textContent = 'Track this action';
      track.addEventListener('click', () => trackInsight(insight));
      actions.append(track);
      const plan = document.createElement('button');
      plan.type = 'button';
      plan.className = 'outline-button';
      plan.textContent = 'Add next step to my plan';
      plan.addEventListener('click', () => addInsightTask(insight));
      actions.append(plan);
      const save = document.createElement('button');
      save.type = 'button';
      save.className = 'text-button';
      save.textContent = insight.status === 'saved' ? 'Saved' : 'Save';
      save.disabled = insight.status === 'saved';
      save.addEventListener('click', () => changeInsightStatus(insight, 'saved'));
      actions.append(save);
      if (insight.status === 'unread') {
        const markRead = document.createElement('button');
        markRead.type = 'button';
        markRead.className = 'text-button';
        markRead.textContent = 'Mark as read';
        markRead.addEventListener('click', () => changeInsightStatus(insight, 'read'));
        actions.append(markRead);
      }
      const dismiss = document.createElement('button');
      dismiss.type = 'button';
      dismiss.className = 'text-button';
      dismiss.textContent = 'Dismiss';
      dismiss.addEventListener('click', () => changeInsightStatus(insight, 'dismissed'));
      actions.append(dismiss);
    }
    card.append(header, observed, evidence, period, reason, nextAction, freshness, actions);
    list.append(card);
  });
  const notes = businessInsights.flatMap(item => item.evidence || []).filter(item => /needed|missing|not recorded/i.test(item));
  if (notes.length) {
    const title = document.createElement('strong');
    title.textContent = 'What would make this clearer';
    const listNotes = document.createElement('ul');
    [...new Set(notes)].slice(0, 3).forEach(text => {
      const item = document.createElement('li');
      item.textContent = text;
      listNotes.append(item);
    });
    missing.append(title, listNotes);
    missing.hidden = false;
  }
}

function renderTrackedOutcomes() {
  const container = $('#outcomeList');
  container.replaceChildren();
  const pending = trackedOutcomes.filter(item => !item.observation_end);
  $('#outcomeFollowups').hidden = !window.UdyamAPI.connected() || pending.length === 0;
  pending.forEach(outcome => {
    const card = document.createElement('article');
    card.className = 'outcome-row';
    const text = document.createElement('span');
    text.textContent = `${outcome.recommendation} · tracking since ${outcome.observation_start}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'outline-button';
    button.textContent = 'Record what happened';
    button.addEventListener('click', () => {
      $('#outcomeId').value = outcome.id;
      $('#outcomeDate').value = today();
      $('#outcomeNotes').value = '';
      $('#outcomeComparable').checked = false;
      $('#outcomeError').hidden = true;
      openDialog('outcomeDialog');
    });
    card.append(text, button);
    container.append(card);
  });
}

async function refreshBusinessPulse() {
  if (!window.UdyamAPI.connected()) {
    showToast('Connect a merchant backend in Settings before checking business records.');
    return;
  }
  insightLoading = true;
  insightError = '';
  renderBusinessPulse();
  try {
    const result = await window.UdyamAPI.analyzeBusiness();
    businessInsights = result.insights || [];
    inventoryRisks = result.inventory_risks || [];
    render();
  } catch (error) {
    insightError = error.message;
  } finally {
    insightLoading = false;
    renderBusinessPulse();
  }
}

async function changeInsightStatus(insight, status) {
  try {
    const updated = await window.UdyamAPI.updateInsight(insight.id, status);
    businessInsights = businessInsights.map(item => item.id === insight.id ? updated : item);
    renderBusinessPulse();
    showToast(status === 'dismissed' ? 'Insight dismissed.' : status === 'read' ? 'Insight marked as read.' : 'Insight saved for later.');
  } catch (error) {
    showToast(error.message);
  }
}

async function trackInsight(insight) {
  try {
    const outcome = await window.UdyamAPI.createOutcome({
      insight_id: insight.id,
      recommendation: insight.headline,
      assumptions: insight.evidence,
      selected_action: insight.next_action,
      baseline: { observed: insight.observed, comparison_period: insight.comparison_period },
      observation_start: today()
    });
    trackedOutcomes.unshift(outcome);
    renderTrackedOutcomes();
    showToast('Action tracking started. Add the outcome later to compare fairly.');
  } catch (error) {
    showToast(error.message);
  }
}

async function addInsightTask(insight) {
  try {
    const created = await window.UdyamAPI.createTask({
      title: insight.next_action.slice(0, 180),
      goal: insight.headline
    });
    state.tasks.unshift({
      id: created.id,
      title: created.title,
      goal: created.goal,
      requiresApproval: created.requires_approval,
      approved: false,
      completed: false,
      status: created.status
    });
    render();
    showToast('A proposed next step was added to your action plan. Review it before acting.');
  } catch (error) {
    showToast(error.message);
  }
}

function investigateInsight(insight) {
  const productId = insight.entity_id;
  const risk = inventoryRisks.find(item => item.product_id === productId);
  const product = state.products.find(item => item.id === productId);
  if (!product || (insight.kind === 'inventory_risk' && !risk)) {
    showToast('Refresh the Business Pulse to load current product details first.');
    return;
  }
  $('#twinProduct').value = productId;
  if (product) {
    if (product.quantity !== null) $('#twinInventory').value = product.quantity;
    if (Number.isFinite(product.cost)) $('#twinCost').value = product.cost;
    if (Number.isFinite(product.price)) $('#twinPrice').value = product.price;
  }
  if (risk?.recent_daily_rate !== null && risk?.recent_daily_rate !== undefined) $('#twinDemand').value = Math.ceil(Number(risk.recent_daily_rate));
  if (risk?.supplier_lead_time_days !== null && risk?.supplier_lead_time_days !== undefined) $('#twinPeriod').value = Math.max(1, risk.supplier_lead_time_days);
  if (risk?.suggested_replenishment !== null && risk?.suggested_replenishment !== undefined) $('#twinQuantity').value = risk.suggested_replenishment;
  updateTwin();
  showPage('twin');
  showToast(insight.kind === 'low_margin'
    ? 'Adjust price or discount to compare. Enter your own demand assumption; no forecast is inferred.'
    : 'Review the historical sales rate and assumptions before comparing.');
}

function render() {
  document.documentElement.lang = state.language;
  if ($('#dataStorageNote')) {
    $('#dataStorageNote').textContent = window.UdyamAPI.connected()
      ? 'Backend connected · your original local records remain separate.'
      : 'Your data stays on this device';
  }
  if ($('#localDataDescription')) {
    $('#localDataDescription').textContent = window.UdyamAPI.connected()
      ? 'The connected merchant data is stored by the backend. Your pre-existing browser records remain separate and are not overwritten.'
      : 'Sales, expenses, products, drafts and preferences are saved locally on this device. Demo data is separate from your own records.';
  }
  if ($('#campaignStorageLabel')) {
    $('#campaignStorageLabel').textContent = window.UdyamAPI.connected() ? 'BACKEND SAVED DRAFTS' : 'SAVED ON THIS DEVICE';
  }
  if ($('#assistantModeNote')) {
    $('#assistantModeNote').textContent = window.UdyamAPI.connected()
      ? backendAiMode === 'live'
        ? 'Live AI credentials are configured on the backend. Replies use authorized merchant records; verify suggestions before acting. Voice input is coming soon.'
        : 'Backend demo mode is active: replies use deterministic business rules, not a live model. Voice input is coming soon.'
      : 'Helpful starting replies use what you enter here; a live AI connection is not set up in this offline preview. Voice input is coming soon.';
  }
  if ($('#autopilotLead')) {
    $('#autopilotLead').textContent = window.UdyamAPI.connected()
      ? 'Review and approve proposed checklist items. Changes are saved to the backend; no orders or messages are sent.'
      : 'Turn a goal into helpful next steps. This preview only updates your local checklist—no orders or messages are sent.';
  }
  $('#modeSelect').value = state.mode;
  $('#languageSelect').value = state.language;
  $('#settingsLanguage').value = state.language;
  $('#merchantSelect').value = state.currentMerchantId;
  $$('input[name="settingsMode"]').forEach(input => { input.checked = input.value === state.mode; });
  const hasRecords = state.sales.length > 0 || state.expenses.length > 0;
  $('#firstSteps').hidden = state.sample;
  $('#sampleNotice').hidden = !state.sample;
  $('#todayPanel').hidden = false;
  $('#sampleInsights').hidden = !state.sample;
  $('#insightsEmpty').hidden = state.sample || (state.transactions.length > 0 && state.mode !== 'simple');
  $('#insightsEmptyCopy').textContent = state.transactions.length > 0 && state.mode === 'simple'
    ? 'You have business records saved. Switch to Smart or Advanced view if you want to explore comparisons and detailed trends.'
    : 'We don’t have enough of your business information to show meaningful trends yet. Add a sale or explore clearly marked sample data to see how insights work.';
  $('#grossProfitCard').hidden = state.mode === 'simple';
  $('#historyPanel').hidden = state.transactions.length === 0 || state.mode === 'simple';
  $('#recordInsights').hidden = state.sample || state.mode === 'simple' || state.transactions.length === 0;
  $('#profileName').textContent = state.name || (state.sample ? window.UdyamStore.current().name : 'Your business');
  $('#profileCategory').textContent = state.sample ? `${state.category} · Demo` : state.category || 'Getting started';
  $('#expenseShortcut').hidden = state.mode === 'advanced';
  $('#stockShortcut').hidden = state.mode === 'advanced';
  const nextTask = state.tasks.find(task => !task.completed);
  $('#taskReminder').hidden = !nextTask;
  $('#reminderTitle').textContent = nextTask?.title || '';
  $$('.smart-metric').forEach(card => { card.hidden = state.mode === 'simple'; });
  $$('.advanced-scenario-field').forEach(field => { field.hidden = state.mode === 'simple'; });
  $$('.advanced-controls').forEach(element => { element.hidden = state.mode !== 'advanced'; });
  $('#welcomeTitle').textContent = state.sample ? `A small shop, full of possibility.` : hasRecords ? 'Welcome back to your business.' : 'A little progress, every day.';
  $('#welcomeCopy').textContent = state.sample ? 'Have a look around this example. Your own business information stays separate.' : hasRecords ? 'Here’s a simple look at what you’ve recorded.' : 'Welcome! Start with one small step. Your business information stays yours.';
  const salesToday = total(state.sales, today());
  const expensesToday = total(state.expenses, today());
  $('#salesValue').textContent = salesToday ? money(salesToday) : 'Nothing recorded yet';
  $('#salesSub').textContent = salesToday ? `${state.sales.filter(item => item.date === today()).length} sale${state.sales.filter(item => item.date === today()).length === 1 ? '' : 's'} recorded today` : 'Add a sale when you’re ready';
  $('#expenseValue').textContent = expensesToday ? money(expensesToday) : 'Nothing recorded yet';
  $('#expenseSub').textContent = expensesToday ? `${state.expenses.filter(item => item.date === today()).length} expense${state.expenses.filter(item => item.date === today()).length === 1 ? '' : 's'} recorded today` : 'You can add expenses too';
  $('#suggestionTitle').textContent = state.products.length ? `Check stock for ${state.products[0].name}` : 'Tell us a little about your shop';
  $('#suggestionSub').textContent = state.products.length ? 'A quick stock count can help with tomorrow’s plans.' : 'It helps UdyamAI give more useful suggestions.';
  renderBusinessMetrics();
  renderBusinessPulse();
  renderTrackedOutcomes();
  renderRecordedInsights();
  renderTransactions();
  renderSaleOptions();
  renderCampaigns();
  renderTasks();
  renderSavedScenarios();
  renderDemoInsights();
  renderProducts();
  renderMarginInsights();
  $$('.advanced-panel').forEach(panel => { panel.hidden = state.mode !== 'advanced'; });
  updateTwin();
  applyLanguage();
}

function renderBusinessMetrics() {
  const dailySales = state.sales.filter(item => item.date === today());
  const knownCogs = dailySales.length > 0 && dailySales.every(item => Number.isFinite(item.costOfGoods));
  $('#grossProfitValue').textContent = knownCogs
    ? money(dailySales.reduce((sum, item) => sum + item.amount - item.costOfGoods, 0))
    : 'Not enough cost details';
  $('#grossProfitSub').textContent = knownCogs
    ? 'Estimated gross profit before other shop expenses.'
    : 'Add product costs to estimate gross profit; other expenses are not included.';
}

function renderRecordedInsights() {
  const records = state.transactions.filter(item => item.date >= window.UdyamData.date(6) && item.date <= today());
  const sales = records.filter(item => item.type === 'sale');
  const expenses = records.filter(item => item.type === 'expense');
  $('#weeklySales').textContent = money(sales.reduce((sum, item) => sum + item.amount, 0));
  $('#weeklySalesNote').textContent = `${sales.length} recorded sale${sales.length === 1 ? '' : 's'} · not a forecast`;
  $('#weeklyExpenses').textContent = money(expenses.reduce((sum, item) => sum + item.amount, 0));
  const cogsComplete = sales.length > 0 && sales.every(item => Number.isFinite(item.costOfGoods));
  $('#weeklyGrossProfit').textContent = cogsComplete
    ? money(sales.reduce((sum, item) => sum + item.amount - item.costOfGoods, 0))
    : 'Not enough cost details';
  const daily = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    return { key, total: sales.filter(item => item.date === key).reduce((sum, item) => sum + item.amount, 0) };
  });
  const max = Math.max(...daily.map(item => item.total), 1);
  const chart = $('#recordBarChart');
  chart.replaceChildren();
  daily.forEach((item, index) => {
    const bar = document.createElement('span');
    bar.style.setProperty('--bar', `${Math.max(5, item.total / max * 100)}%`);
    bar.setAttribute('aria-label', `${item.key}: ${money(item.total)}`);
    const label = document.createElement('i');
    label.textContent = new Intl.DateTimeFormat(state.language === 'hi' ? 'hi-IN' : 'en-IN', { weekday: 'short' }).format(new Date(`${item.key}T12:00:00`));
    bar.append(label);
    if (index === 6) bar.classList.add('today-bar');
    chart.append(bar);
  });
}

function renderTransactions() {
  const container = $('#transactionList');
  container.replaceChildren();
  const entries = showAllTransactions ? state.transactions : state.transactions.slice(0, 5);
  entries.forEach(item => {
    const row = document.createElement('article');
    row.className = 'transaction-row';
    const detail = document.createElement('div');
    const label = document.createElement('strong');
    label.textContent = item.productName || item.note || (item.type === 'sale' ? 'Sale' : item.category || 'Expense');
    const meta = document.createElement('small');
    const category = item.type === 'sale' ? (item.quantity ? `${item.quantity} item${item.quantity === 1 ? '' : 's'} sold` : 'Sale recorded') : `${item.category || 'Other'} · expense`;
    meta.textContent = `${category} · ${item.date}${item.source === 'demo' ? ' · demo' : ''}`;
    detail.append(label, meta);
    const amount = document.createElement('strong');
    amount.className = item.type === 'sale' ? 'transaction-positive' : 'transaction-negative';
    amount.textContent = `${item.type === 'sale' ? '+' : '−'}${money(item.amount)}`;
    row.append(detail, amount);
    container.append(row);
  });
  $('#allTransactionsButton').textContent = showAllTransactions ? 'Show recent' : 'View all';
}

function renderSaleOptions() {
  const select = $('#saleProduct');
  const selected = select.value;
  select.replaceChildren(new Option('No product / enter total', ''));
  state.products.forEach(product => select.add(new Option(`${product.name}${Number.isFinite(product.price) ? ` · ${money(product.price)}` : ''}`, product.id)));
  if (state.products.some(product => product.id === selected)) select.value = selected;
  const scenarioSelect = $('#twinProduct');
  const changedMerchant = scenarioMerchantId !== state.currentMerchantId;
  const scenarioId = scenarioSelect.value;
  scenarioSelect.replaceChildren(new Option('Custom numbers', ''));
  state.products.forEach(product => scenarioSelect.add(new Option(product.name, product.id)));
  if (state.products.some(product => product.id === scenarioId)) scenarioSelect.value = scenarioId;
  else if (changedMerchant && state.products.length) scenarioSelect.value = state.products[0].id;
  if (changedMerchant && scenarioSelect.value) {
    const selectedProduct = state.products.find(product => product.id === scenarioSelect.value);
    if (selectedProduct) {
      if (Number.isFinite(selectedProduct.cost)) $('#twinCost').value = selectedProduct.cost;
      if (Number.isFinite(selectedProduct.price)) $('#twinPrice').value = selectedProduct.price;
      if (Number.isFinite(selectedProduct.quantity)) $('#twinInventory').value = selectedProduct.quantity;
    }
  }
  scenarioMerchantId = state.currentMerchantId;
}

function renderDemoInsights() {
  const demo = state.sample;
  const records = state.transactions;
  const recent = records.filter(item => item.date >= window.UdyamData.date(6));
  const sales = recent.filter(item => item.type === 'sale').reduce((sum, item) => sum + item.amount, 0);
  const expenses = recent.filter(item => item.type === 'expense').reduce((sum, item) => sum + item.amount, 0);
  const soldByProduct = new Map();
  recent.filter(item => item.type === 'sale' && item.productId).forEach(item => soldByProduct.set(item.productId, (soldByProduct.get(item.productId) || 0) + item.quantity));
  const best = [...soldByProduct.entries()].sort((a, b) => b[1] - a[1])[0];
  const product = best && state.products.find(item => item.id === best[0]);
  const root = $('#sampleInsights');
  root.querySelector('.money-card:nth-child(1) strong').textContent = money(sales);
  root.querySelector('.money-card:nth-child(1) small').textContent = `${recent.filter(item => item.type === 'sale').length} ${demo ? 'demo ' : ''}sales in the last 7 days`;
  root.querySelector('.money-card:nth-child(2) strong').textContent = money(expenses);
  root.querySelector('.money-card:nth-child(2) small').textContent = `${recent.filter(item => item.type === 'expense').length} recorded expenses`;
  root.querySelector('.money-card:nth-child(3) strong').textContent = product?.name || 'No product sales';
  root.querySelector('.money-card:nth-child(3) small').textContent = product ? `${best[1]} recorded units sold` : 'Choose a product when recording a sale';
  const dayTotals = Array.from({ length: 7 }, (_, index) => {
    const day = new Date();
    day.setDate(day.getDate() - (6 - index));
    const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
    return records.filter(item => item.type === 'sale' && item.date === key).reduce((sum, item) => sum + item.amount, 0);
  });
  const max = Math.max(...dayTotals, 1);
  $$('.bar-chart span').forEach((bar, index) => { bar.style.setProperty('--bar', `${Math.max(5, dayTotals[index] / max * 100)}%`); });
}

function applyLanguage() {
  const hi = state.language === 'hi';
  const text = (selector, value) => { const element = $(selector); if (element) element.textContent = value; };
  const navLabel = (selector, value) => {
    const button = $(selector);
    if (button && button.lastChild?.nodeType === Node.TEXT_NODE) button.lastChild.textContent = ` ${value}`;
  };
  const translations = hi ? {
    '.sidebar-label': 'आपका कारोबार',
    '.mode-label': 'आपका व्यू',
    '#todayLabel': 'आपका कारोबार, आपकी रफ़्तार से',
    '#stepsTitle': 'आप क्या करना चाहेंगे?',
    '.progress-pill': 'अभी कुछ सेट करने की ज़रूरत नहीं',
    '#todayHeading': 'आज का हिसाब',
    '#assistantTitle': 'उद्यमAI से पूछें',
    '.assistant-intro p:last-child': 'जैसे किसी मददगार दोस्त से पूछते हैं, वैसे ही लिखें।',
    '#askInput': 'अपने कारोबार के बारे में कुछ भी पूछें…',
    '.send-button': 'पूछें →',
    '.privacy-note': 'जवाब यहाँ दी गई जानकारी पर आधारित हैं; इस प्रीव्यू में लाइव AI सेवा जुड़ी नहीं है। वॉइस सुविधा जल्द आएगी।',
    '.onboarding-strip strong': 'इसे अपने कारोबार के मुताबिक बनाएँ',
    '.onboarding-strip p': 'कुछ आसान सवालों से सुझाव बेहतर होंगे। आप कोई भी सवाल छोड़ सकते हैं।',
    '#startOnboarding': 'शुरू करें →',
    '#stockTitle': 'मेरा स्टॉक',
    '#twinTitle': 'एक नया विचार आज़माएँ',
    '#insightsTitle': 'कारोबार की जानकारी',
    '#settingsTitle': 'सेटिंग्स',
    '#saleDialogTitle': 'आज की बिक्री लिखें',
    '#saleAmount': 'उदाहरण: 500',
    '#productName': 'उदाहरण: चावल',
    '#productSearch': 'उत्पाद का नाम लिखें',
    '#saleAmountLabel': 'आपने कितने रुपये कमाए?',
    '#saleNoteLabel': 'किस चीज़ की बिक्री थी?',
    '#expenseAmountLabel': 'आपने कितने रुपये खर्च किए?',
    '#expenseNoteLabel': 'किस चीज़ पर खर्च हुआ?',
    '#productNameLabel': 'आप क्या बेचते हैं?',
    '#productQuantityLabel': 'कितना स्टॉक है? (ज़रूरी नहीं)',
    '#saleSubmit': 'बिक्री सहेजें',
    '#expenseSubmit': 'खर्च सहेजें',
    '#productSubmit': 'उत्पाद सहेजें'
  } : {
    '.sidebar-label': 'YOUR BUSINESS',
    '.mode-label': 'Your view',
    '#todayLabel': 'YOUR BUSINESS, AT YOUR PACE',
    '#stepsTitle': 'What would you like to do?',
    '.progress-pill': 'No setup needed',
    '#todayHeading': 'Today’s picture',
    '#assistantTitle': 'Ask UdyamAI',
    '.assistant-intro p:last-child': 'Type the way you’d ask a helpful friend. You don’t need special words.',
    '#askInput': 'Ask anything about your business…',
    '.send-button': 'Ask →',
    '.privacy-note': 'Helpful starting replies use what you enter here; a live AI connection isn’t set up in this preview. Voice input is coming soon.',
    '.onboarding-strip strong': 'Make this feel like your business',
    '.onboarding-strip p': 'A few easy questions can help us make your suggestions more useful. Skip any question you like.',
    '#startOnboarding': 'Get started →',
    '#stockTitle': 'My stock',
    '#twinTitle': 'Try a business idea',
    '#insightsTitle': 'Business insights',
    '#settingsTitle': 'Settings',
    '#saleDialogTitle': 'Record today’s sale',
    '#saleAmount': 'e.g. 500',
    '#productName': 'e.g. Rice',
    '#productSearch': 'Type a product name',
    '#saleAmountLabel': 'How much did you earn? ₹',
    '#saleNoteLabel': 'What was it for?',
    '#expenseAmountLabel': 'How much did you spend? ₹',
    '#expenseNoteLabel': 'What was it for?',
    '#productNameLabel': 'What do you sell?',
    '#productQuantityLabel': 'How many do you have? Optional',
    '#saleSubmit': 'Save sale',
    '#expenseSubmit': 'Save expense',
    '#productSubmit': 'Save product'
  };
  Object.entries(translations).forEach(([selector, value]) => {
    const element = $(selector);
    if (!element) return;
    if (element instanceof HTMLInputElement) element.placeholder = value;
    else if (element instanceof HTMLLabelElement && $('input, select', element)) {
      const textNode = [...element.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
      if (textNode) textNode.nodeValue = `${value} `;
    }
    else if (selector === '.send-button' || selector === '#startOnboarding') element.textContent = value;
    else element.textContent = value;
  });
  navLabel('.sidebar .nav-item[data-page="home"]', hi ? 'होम' : 'Home');
  navLabel('.sidebar .nav-item[data-page="stock"]', hi ? 'मेरा स्टॉक' : 'My stock');
  navLabel('.sidebar .nav-item[data-page="twin"]', hi ? 'एक विचार आज़माएँ' : 'Try an idea');
  navLabel('.sidebar .nav-item[data-page="insights"]', hi ? 'कारोबार की जानकारी' : 'Business insights');
  navLabel('.sidebar .nav-item[data-page="settings"]', hi ? 'सेटिंग्स' : 'Settings');
  const hasRecords = state.sales.length || state.expenses.length;
  const homeTitle = state.sample ? (hi ? `${state.name} · डेमो कारोबार` : `${state.name} · demo business`) : hasRecords ? (hi ? 'आपका कारोबार फिर से स्वागत करता है।' : 'Welcome back to your business.') : (hi ? 'हर दिन थोड़ी तरक्की।' : 'A little progress, every day.');
  text('#welcomeTitle', homeTitle);
  text('#welcomeCopy', state.sample ? (hi ? `यह ${state.name} का डेमो है। आपके कारोबार की जानकारी इससे अलग और आपकी अपनी है।` : `Explore ${state.name}. Demo records are separate from your own business.`) : hasRecords ? (hi ? 'आपने जो जानकारी दर्ज की है, उसका आसान सा सार यहाँ है।' : 'Here’s a simple look at what you’ve recorded.') : (hi ? 'स्वागत है! एक छोटे कदम से शुरुआत करें। आपके कारोबार की जानकारी आपकी है।' : 'Welcome! Start with one small step. Your business information stays yours.'));
  text('#sampleButton', hi ? 'उदाहरण कारोबार देखें →' : 'Explore a sample business →');
  text('#sampleNotice strong', hi ? 'यह उदाहरण कारोबार है।' : 'Sample business is on.');
  const notice = $('#sampleNotice > span:nth-child(2)');
  if (notice.lastChild?.nodeType === Node.TEXT_NODE) notice.lastChild.textContent = hi ? ' ये उदाहरण के आँकड़े आपके कारोबार के नहीं हैं।' : ' These example numbers are not your business data.';
  text('#exitSample', hi ? 'मेरे कारोबार पर लौटें' : 'Back to my business');
  text('#firstSteps .eyebrow', hi ? 'शुरुआत करने का आसान तरीका' : 'A GOOD PLACE TO BEGIN');
  text('#todayPanel .eyebrow', hi ? 'आज का आसान हिसाब' : 'A SIMPLE DAILY CHECK-IN');
  text('#assistantPanel .eyebrow', hi ? 'जब भी मदद चाहिए' : 'HERE WHEN YOU NEED A HAND');
  text('#addExpenseButton', hi ? '＋ खर्च जोड़ें' : '＋ Add an expense');
  text('#expenseShortcut strong', hi ? 'खर्च जोड़ें' : 'Add an expense');
  text('#expenseShortcut small', hi ? 'खर्च का हिसाब रखें' : 'Keep track of money spent');
  text('#stockShortcut strong', hi ? 'स्टॉक देखें' : 'Check my stock');
  text('#stockShortcut small', hi ? 'दुकान में क्या है देखें' : 'See what’s on your shelf');
  const salesCount = state.sales.filter(item => item.date === today()).length;
  const expensesCount = state.expenses.filter(item => item.date === today()).length;
  const salesToday = total(state.sales, today());
  const expensesToday = total(state.expenses, today());
  text('#salesValue', salesToday ? money(salesToday) : hi ? 'अभी दर्ज नहीं' : 'Nothing recorded yet');
  text('#salesSub', salesCount ? (hi ? `आज ${salesCount} बिक्री दर्ज की${salesCount === 1 ? '' : 'ं'}` : `${salesCount} sale${salesCount === 1 ? '' : 's'} recorded today`) : hi ? 'तैयार हों तो बिक्री जोड़ें' : 'Add a sale when you’re ready');
  text('#expenseValue', expensesToday ? money(expensesToday) : hi ? 'अभी दर्ज नहीं' : 'Nothing recorded yet');
  text('#expenseSub', expensesCount ? (hi ? `आज ${expensesCount} खर्च दर्ज किए` : `${expensesCount} expense${expensesCount === 1 ? '' : 's'} recorded today`) : hi ? 'खर्च भी जोड़ सकते हैं' : 'You can add expenses too');
  text('#suggestionTitle', state.products.length ? (hi ? `${state.products[0].name} का स्टॉक देखें` : `Check stock for ${state.products[0].name}`) : hi ? 'अपनी दुकान के बारे में बताएँ' : 'Tell us a little about your shop');
  text('#suggestionSub', state.products.length ? (hi ? 'कल की तैयारी के लिए स्टॉक गिन लें।' : 'A quick stock count can help with tomorrow’s plans.') : hi ? 'इससे सुझाव आपके लिए ज़्यादा उपयोगी होंगे।' : 'It helps UdyamAI give more useful suggestions.');
  const helpCard = $('.help-card p');
  const helpTitle = document.createElement('strong');
  helpTitle.textContent = hi ? 'छोटे कदम भी मायने रखते हैं।' : 'Small steps count.';
  helpCard.replaceChildren(helpTitle, document.createElement('br'), document.createTextNode(hi ? 'जो पता है, वहीं से शुरू करें। जब चाहें और जानकारी जोड़ें।' : 'Start with what you know. Add more whenever you’re ready.'));
  text('.app-footer span:first-child', hi ? 'आपके कारोबार के तरीके के लिए।' : 'Made for the way you do business.');
  text('.app-footer span:last-child', hi ? 'उद्यमAI प्रीव्यू · आपकी जानकारी इसी डिवाइस पर रहती है' : 'UdyamAI preview · Your data stays on this device');
  const actionLabels = hi ? [
    ['आज की बिक्री लिखें', 'कमाए हुए पैसे दर्ज करें'],
    ['खर्च जोड़ें', 'खर्च का हिसाब रखें'],
    ['स्टॉक देखें', 'दुकान में क्या है देखें'],
    ['उद्यमAI से पूछें', 'अपने शब्दों में मदद पाएँ']
  ] : [
    ['Record today’s sale', 'Write down money you earned'],
    ['Add an expense', 'Keep track of money spent'],
    ['Check my stock', 'See what’s on your shelf'],
    ['Ask UdyamAI', 'Get help in your own words']
  ];
  $$('.action-card').forEach((card, index) => {
    const strong = $('strong', card);
    const small = $('small', card);
    if (strong) strong.textContent = actionLabels[index][0];
    if (small) small.textContent = actionLabels[index][1];
  });
  $$('.money-label').forEach((label, index) => { label.textContent = (hi ? ['कमाई', 'खर्च', 'अनुमानित सकल मुनाफ़ा', 'अगला आसान कदम'] : ['Money earned', 'Money spent', 'Estimated gross profit', 'A helpful next step'])[index] || label.textContent; });
  $$('.question-chip').forEach((chip, index) => { chip.textContent = (hi ? ['आज कितनी कमाई हुई?', 'किस उत्पाद का स्टॉक बढ़ाऊँ?', 'सबसे ज़्यादा कौन से उत्पाद बिके?', 'इस सप्ताहांत मुनाफ़ा कैसे बढ़ाऊँ?', 'मेरी दुकान के लिए त्योहार का ऑफ़र बनाएँ।'][index] : ['How much did I earn today?', 'Which product should I stock more of?', 'Which products sell the most?', 'How can I improve my profit this weekend?', 'Create a festival offer for my shop.'][index]); });
  $('#languageSelect').options[0].textContent = hi ? 'अंग्रेज़ी' : 'English';
  $('#languageSelect').options[1].textContent = 'हिन्दी';
  $('#settingsLanguage').options[0].textContent = hi ? 'अंग्रेज़ी' : 'English';
  $('#settingsLanguage').options[1].textContent = 'हिन्दी';
  $('#modeSelect').options[0].textContent = hi ? 'सरल' : 'Simple';
  $('#modeSelect').options[1].textContent = hi ? 'स्मार्ट' : 'Smart';
  $('#modeSelect').options[2].textContent = hi ? 'एडवांस्ड' : 'Advanced';
  $('#settingsTitle').textContent = hi ? 'सेटिंग्स' : 'Settings';
  $('#saleAmountLabel').textContent = translations['#saleAmountLabel'];
  $('#expenseAmountLabel').textContent = translations['#expenseAmountLabel'];
  $('#productNameLabel').textContent = translations['#productNameLabel'];
  $('#productQuantityLabel').textContent = translations['#productQuantityLabel'];
  $('#saleSubmit').textContent = translations['#saleSubmit'];
  $('#expenseSubmit').textContent = translations['#expenseSubmit'];
  $('#productSubmit').textContent = translations['#productSubmit'];
  $('#settingsTitle').textContent = hi ? 'सेटिंग्स' : 'Settings';
  $$('.mobile-nav button').forEach((button, index) => {
    const labels = hi ? ['होम', 'स्टॉक', 'आज़माएँ', 'सेटिंग्स'] : ['Home', 'Stock', 'Try an idea', 'Settings'];
    $('small', button).textContent = labels[index];
  });
}

function renderProducts() {
  if (!$('#productList')) return;
  $('#productArea').hidden = state.products.length === 0;
  $('#stockEmpty').hidden = state.products.length > 0;
  $('#productCount').textContent = `${state.products.length} product${state.products.length === 1 ? '' : 's'}`;
  $('#productSearchWrap').hidden = state.mode !== 'advanced' || state.products.length === 0;
  $('#advancedProductFields').hidden = state.mode === 'simple';
  $('#liveInsights').hidden = state.sample || state.mode === 'simple' || state.products.length === 0;
  $('#promotionTool').hidden = state.mode === 'simple';
  const list = $('#productList');
  list.replaceChildren();
  const search = $('#productSearch').value.trim().toLowerCase();
  const filteredProducts = state.products.filter(product => product.name.toLowerCase().includes(search));
  $('#noProductsFound').hidden = filteredProducts.length > 0;
  filteredProducts.forEach(product => {
    const row = document.createElement('div');
    row.className = 'product-row';
    const info = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = product.name;
    const quantity = document.createElement('small');
    quantity.textContent = `${product.quantity === null ? 'Quantity not added' : `${product.quantity} in stock`}${product.supplierLeadTimeDays === null || product.supplierLeadTimeDays === undefined ? '' : ` · delivery ${product.supplierLeadTimeDays} days`}`;
    info.append(name, quantity);
    if (state.mode !== 'simple') {
      const details = document.createElement('small');
      details.className = 'product-detail';
      details.textContent = Number.isFinite(product.cost) && Number.isFinite(product.price)
        ? `Cost ${money(product.cost)} · Price ${money(product.price)} · Gross margin ${money(product.price - product.cost)} / item`
        : 'Add a cost and selling price for a margin comparison';
      info.append(details);
    }
    row.append(info);
    const countButton = document.createElement('button');
    countButton.type = 'button';
    countButton.className = 'outline-button';
    countButton.textContent = 'Update count';
    countButton.setAttribute('aria-label', `Update ${product.name} stock count`);
    countButton.addEventListener('click', () => {
      $('#inventoryProductId').value = product.id;
      $('#inventoryQuantity').value = product.quantity ?? '';
      $('#inventoryNote').value = '';
      $('#inventoryError').hidden = true;
      openDialog('inventoryDialog');
    });
    row.append(countButton);
    list.append(row);
  });
}

function renderMarginInsights() {
  const list = $('#marginList');
  list.replaceChildren();
  state.products.forEach(product => {
    const row = document.createElement('article');
    row.className = 'margin-row';
    const details = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = product.name;
    const stock = document.createElement('small');
    stock.textContent = product.quantity === null ? 'Stock quantity not entered' : `${product.quantity} in stock`;
    details.append(name, stock);
    const margin = document.createElement('div');
    margin.className = 'margin-values';
    if (Number.isFinite(product.cost) && Number.isFinite(product.price)) {
      const amount = document.createElement('strong');
      amount.textContent = money(product.price - product.cost);
      const percent = document.createElement('small');
      percent.textContent = product.price > 0 ? `${Math.round(((product.price - product.cost) / product.price) * 100)}% gross margin` : 'Price is ₹0';
      margin.append(amount, percent);
    } else {
      const missing = document.createElement('small');
      missing.textContent = 'Add unit cost and selling price to compare margin';
      margin.append(missing);
    }
    row.append(details, margin);
    list.append(row);
  });
}

function renderCampaigns() {
  const productSelect = $('#campaignProduct');
  if (!productSelect) return;
  const selected = productSelect.value;
  productSelect.replaceChildren(new Option('Choose a product', ''));
  state.products.forEach(product => productSelect.add(new Option(product.name, product.id)));
  if (state.products.some(product => product.id === selected)) productSelect.value = selected;
  const list = $('#campaignList');
  list.replaceChildren();
  state.campaigns.forEach(campaign => {
    const card = document.createElement('article');
    card.className = 'saved-campaign';
    const title = document.createElement('strong');
    title.textContent = campaign.productName || 'Shop offer';
    const copy = document.createElement('p');
    copy.textContent = campaign.copy;
    const status = document.createElement('small');
    status.textContent = `Draft · not sent · ${campaign.createdAt}`;
    card.append(title, copy, status);
    list.append(card);
  });
}

function renderTasks() {
  const taskList = $('#taskList');
  taskList.replaceChildren();
  state.tasks.forEach(task => {
    const row = document.createElement('article');
    row.className = `task-row${task.completed ? ' task-complete' : ''}`;
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = Boolean(task.completed);
    checkbox.setAttribute('aria-label', `Mark ${task.title} complete`);
    checkbox.addEventListener('change', async () => {
      if (window.UdyamAPI.connected()) {
        if (!checkbox.checked) {
          checkbox.checked = true;
          showToast('Completed checklist items cannot be reopened in the backend yet.');
          return;
        }
        try {
          await window.UdyamAPI.updateTask(task.id, 'completed');
        } catch (error) {
          checkbox.checked = false;
          showToast(error.message);
          return;
        }
      }
      task.completed = checkbox.checked;
      task.status = task.completed ? 'completed' : task.status;
      saveState();
      render();
    });
    const details = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = task.title;
    const status = document.createElement('small');
    status.textContent = task.requiresApproval
      ? 'Checklist only · separate approval required before any purchase or message'
      : task.approved ? 'Checklist approved · no external action taken' : 'Your checklist';
    details.append(title, status);
    if (!state.sample && !task.completed && !task.approved && (task.status === undefined || task.status === 'proposed')) {
      const edit = document.createElement('button');
      edit.className = 'text-button task-edit';
      edit.type = 'button';
      edit.textContent = 'Edit';
      edit.setAttribute('aria-label', `Edit ${task.title}`);
      edit.addEventListener('click', () => editProposedTask(task, details, title, edit));
      details.append(edit);
    }
    const reject = document.createElement('button');
    reject.className = 'text-button task-remove';
    reject.type = 'button';
    reject.textContent = 'Remove';
    reject.addEventListener('click', async () => {
      if (window.UdyamAPI.connected()) {
        try {
          await window.UdyamAPI.deleteTask(task.id);
        } catch (error) {
          showToast(error.message);
          return;
        }
      }
      state.tasks = state.tasks.filter(item => item.id !== task.id);
      saveState();
      render();
    });
    row.append(checkbox, details, reject);
    taskList.append(row);
  });
}

function editProposedTask(task, details, title, editButton) {
  const form = document.createElement('form');
  form.className = 'task-edit-form';
  const input = document.createElement('input');
  input.type = 'text';
  input.maxLength = 180;
  input.value = task.title;
  input.setAttribute('aria-label', 'Edit proposed checklist item');
  const save = document.createElement('button');
  save.type = 'submit';
  save.className = 'outline-button';
  save.textContent = 'Save';
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'text-button';
  cancel.textContent = 'Cancel';
  cancel.addEventListener('click', () => {
    form.replaceWith(title);
    editButton.hidden = false;
  });
  form.append(input, save, cancel);
  title.replaceWith(form);
  editButton.hidden = true;
  input.focus();
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const nextTitle = input.value.trim();
    if (nextTitle.length < 2) {
      showToast('Use a task title with at least 2 characters.');
      input.focus();
      return;
    }
    try {
      if (window.UdyamAPI.connected()) {
        await window.UdyamAPI.updateTask(task.id, { title: nextTitle });
      }
      task.title = nextTitle;
      saveState();
      renderTasks();
    } catch (error) {
      showToast(error.message);
    }
  });
}

function renderSavedScenarios() {
  const list = $('#scenarioList');
  list.replaceChildren();
  [...state.scenarios].reverse().forEach(scenario => {
    const row = document.createElement('article');
    row.className = 'saved-scenario-row';
    const title = document.createElement('strong');
    title.textContent = `${scenario.quantity} more items · ${scenario.savedAt}`;
    const detail = document.createElement('small');
    detail.textContent = `Estimated revenue ${money(scenario.outcomes.revenue)} · gross profit ${money(scenario.outcomes.grossProfit)} · ${scenario.outcomes.unsold} left over`;
    row.append(title, detail);
    list.append(row);
  });
}

function showPage(page) {
  $$('.page-view').forEach(view => view.classList.toggle('active', view.id === `page-${page}`));
  $$('[data-page]').forEach(button => button.classList.toggle('active', button.dataset.page === page));
  const heading = $(`#page-${page} h1`);
  if (heading) heading.focus?.({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (id === 'saleDialog') {
    $('#saleDate').value = today();
    $('#saleAmount').dataset.manual = 'false';
    $('#saleAmount').value = '';
    $('#saleQuantity').value = '1';
    $('#saleProduct').value = '';
    $('#saleManualName').value = '';
    $('#saleUnitPrice').value = '';
    renderSaleOptions();
  }
  if (id === 'expenseDialog') $('#expenseDate').value = today();
  if (!dialog.open) dialog.showModal();
}

function closeDialog(id) {
  document.getElementById(id).close();
}

function formatSimpleAssistant(question) {
  return window.UdyamServices.answer(question, window.UdyamStore.current(), state.language, today());
}

function renderAssistantReply(result) {
  const reply = $('#assistantReply');
  reply.replaceChildren();
  const card = document.createElement('article');
  card.className = 'assistant-response-card';
  const heading = document.createElement('h3');
  heading.textContent = result.title;
  const message = document.createElement('p');
  message.textContent = result.message;
  card.append(heading, message);
  const evidence = [...(result.evidence || []), ...(result.observed_data || [])];
  if (evidence.length) {
    const evidenceTitle = document.createElement('strong');
    evidenceTitle.className = 'evidence-label';
    evidenceTitle.textContent = state.language === 'hi' ? 'आपके रिकॉर्ड से' : 'Based on your records';
    const list = document.createElement('ul');
    evidence.forEach(item => {
      const line = document.createElement('li');
      line.textContent = item;
      list.append(line);
    });
    card.append(evidenceTitle, list);
  }
  if (result.missing_information?.length) {
    const missingTitle = document.createElement('strong');
    missingTitle.className = 'evidence-label';
    missingTitle.textContent = state.language === 'hi' ? 'अभी क्या जानकारी नहीं है' : 'What is still missing';
    const missing = document.createElement('p');
    missing.textContent = result.missing_information.join(' ');
    card.append(missingTitle, missing);
  }
  const nextAction = result.nextAction || (result.next_action ? {
    label: result.next_action,
    page: /campaign|offer/i.test(result.next_action) ? 'campaigns' : /profit|price/i.test(result.next_action) ? 'twin' : /sale/i.test(result.next_action) ? 'home' : 'stock',
    dialog: /record.*sale/i.test(result.next_action) ? 'saleDialog' : undefined
  } : null);
  if (nextAction) {
    const action = document.createElement('button');
    action.className = 'outline-button';
    action.type = 'button';
    action.textContent = nextAction.label;
    action.addEventListener('click', () => {
      if (nextAction.dialog) openDialog(nextAction.dialog);
      else showPage(nextAction.page);
    });
    card.append(action);
  }
  reply.append(card);
  reply.hidden = false;
}

function renderSquad(question) {
  const result = window.UdyamServices.squad(question, window.UdyamStore.current(), state.language);
  const reply = $('#assistantReply');
  reply.replaceChildren();
  const heading = document.createElement('h3');
  heading.textContent = result.title;
  reply.append(heading);
  const grid = document.createElement('div');
  grid.className = 'agent-grid';
  result.agents.forEach(agent => {
    const card = document.createElement('article');
    card.className = 'agent-card';
    const name = document.createElement('strong');
    name.textContent = agent.name;
    const message = document.createElement('p');
    message.textContent = agent.message;
    const evidence = document.createElement('small');
    evidence.textContent = agent.evidence;
    card.append(name, message, evidence);
    grid.append(card);
  });
  const recommendation = document.createElement('p');
  recommendation.className = 'coordinator-recommendation';
  recommendation.textContent = `${state.language === 'hi' ? 'समन्वयक की सलाह: ' : 'Coordinator: '}${result.recommendation}`;
  const actions = document.createElement('div');
  actions.className = 'response-actions';
  [
    ['Open Business Twin', 'twin'],
    ['Draft a campaign', 'campaigns'],
    ['Create a task', 'autopilot']
  ].forEach(([label, page]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'outline-button';
    button.textContent = label;
    button.addEventListener('click', () => showPage(page));
    actions.append(button);
  });
  reply.append(grid, recommendation, actions);
  reply.hidden = false;
}

function updateTwin(remoteValues = null) {
  const input = {
    extraStock: Number($('#twinQuantity').value),
    cost: Number($('#twinCost').value),
    price: Number($('#twinPrice').value),
    availableInventory: Number($('#twinInventory').value),
    demandPerDay: Number($('#twinDemand').value),
    period: Number($('#twinPeriod').value),
    discount: Number($('#twinDiscount').value)
  };
  const values = remoteValues || window.UdyamServices.compareScenario(input);
  const baseline = values.baseline.units === undefined ? {
    ...values.baseline,
    units: values.baseline.units_sold,
    cogs: values.baseline.cost_of_goods_sold,
    unsold: values.baseline.unsold_units
  } : values.baseline;
  const proposed = values.proposed.units === undefined ? {
    ...values.proposed,
    units: values.proposed.units_sold,
    cogs: values.proposed.cost_of_goods_sold,
    unsold: values.proposed.unsold_units,
    unsoldValue: values.proposed.unsold_units * Number($('#twinCost').value)
  } : values.proposed;
  const write = (id, value) => { $(`#${id}`).textContent = value; };
  write('baselineUnits', baseline.units);
  write('baselineRevenue', money(Number(baseline.revenue)));
  write('baselineCogs', money(Number(baseline.cogs)));
  write('baselineProfit', money(Number(baseline.grossProfit ?? baseline.gross_profit)));
  write('baselineUnsold', baseline.unsold);
  write('proposedUnits', proposed.units);
  write('proposedRevenue', money(Number(proposed.revenue)));
  write('proposedCogs', money(Number(proposed.cogs)));
  write('proposedProfit', money(Number(proposed.grossProfit ?? proposed.gross_profit)));
  write('proposedUnsold', proposed.unsold);
  const selectedProduct = state.products.find(product => product.id === $('#twinProduct').value);
  $('#twinPromptQuantity').textContent = `${Math.floor(input.extraStock || 0)} more ${selectedProduct?.name || (state.language === 'hi' ? 'उत्पाद' : 'items')}`;
  write('unsoldCost', money(Number(proposed.unsoldValue ?? proposed.unsold_units * input.cost)));
  const explanation = state.language === 'hi'
    ? `इस अनुमान में ${input.period} दिन की माँग ली गई है और बिक्री उपलब्ध स्टॉक से ज़्यादा नहीं हो सकती। सकल मुनाफ़े में दुकान के दूसरे खर्च शामिल नहीं हैं। बचा हुआ माल बिक न सके तो उसका खर्च अलग रहेगा।`
    : `This estimate uses ${input.period} day${input.period === 1 ? '' : 's'} of expected demand and caps sales at available stock. Gross profit excludes other shop expenses; leftover stock still ties up ${money(values.proposed.unsoldValue)} at your entered unit cost.`;
  const serverLimitations = values.limitations?.join(' ') || '';
  write('twinExplanation', `${explanation}${serverLimitations ? ` ${serverLimitations}` : ''}`);
  $('#twinResult').dataset.baseline = JSON.stringify(baseline);
  $('#twinResult').dataset.proposed = JSON.stringify(proposed);
}

$$('[data-page]').forEach(button => button.addEventListener('click', () => showPage(button.dataset.page)));
$$('.brand').forEach(link => link.addEventListener('click', event => { event.preventDefault(); showPage('home'); }));
$('#modeSelect').addEventListener('change', event => { state.mode = event.target.value; saveState(); render(); });
$$('input[name="settingsMode"]').forEach(input => input.addEventListener('change', () => { state.mode = input.value; saveState(); render(); }));
function setLanguage(language) {
  state.language = language;
  saveState();
  render();
  showToast(language === 'hi' ? 'भाषा बदल दी गई।' : 'Language updated.');
}
$('#languageSelect').addEventListener('change', event => setLanguage(event.target.value));
$('#settingsLanguage').addEventListener('change', event => setLanguage(event.target.value));
$('#merchantSelect').addEventListener('change', event => {
  if (window.UdyamAPI.connected()) {
    window.UdyamAPI.disconnect();
    $('#backendStatus').textContent = 'Disconnected because you switched merchants. Connect again with that merchant’s token.';
    state = window.UdyamStore.load();
  }
  window.UdyamStore.selectMerchant(event.target.value);
  state = window.UdyamStore.load();
  showAllTransactions = false;
  render();
  showPage('home');
  showToast(state.sample ? `Demo business loaded: ${state.name}` : 'Your business is selected.');
});

$('#connectBackend').addEventListener('click', async () => {
  const button = $('#connectBackend');
  const status = $('#backendStatus');
  const token = $('#backendToken').value.trim();
  if (!token) {
    status.textContent = 'Enter a merchant token. The token is not saved in browser storage.';
    return;
  }
  button.disabled = true;
  status.textContent = 'Connecting and loading your merchant records…';
  try {
    const merchantId = state.currentMerchantId;
    const records = await window.UdyamAPI.connect($('#backendUrl').value.trim(), token, merchantId);
    backendAiMode = records.status.ai_mode;
    applyBackendRecords(records, merchantId);
    $('#backendToken').value = '';
    status.textContent = `Connected to ${records.merchant.name || 'your merchant'} · AI ${records.status.ai_mode} mode.`;
    showToast('Backend records loaded. New records will be saved to the server.');
  } catch (error) {
    window.UdyamAPI.disconnect();
    status.textContent = `Could not connect: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

$('#disconnectBackend').addEventListener('click', () => {
  window.UdyamAPI.disconnect();
  businessInsights = [];
  inventoryRisks = [];
  trackedOutcomes = [];
  insightError = '';
  state = window.UdyamStore.load();
  render();
  $('#backendStatus').textContent = 'Disconnected. Your original local records are unchanged.';
  showToast('Backend disconnected.');
});

$('#refreshPulse').addEventListener('click', refreshBusinessPulse);

$('#inventoryForm').addEventListener('submit', async event => {
  event.preventDefault();
  const productId = $('#inventoryProductId').value;
  const quantity = Number($('#inventoryQuantity').value);
  if (!Number.isInteger(quantity) || quantity < 0) {
    $('#inventoryError').textContent = 'Enter a whole number of items, including zero if none are left.';
    $('#inventoryError').hidden = false;
    return;
  }
  const product = state.products.find(item => item.id === productId);
  if (!product) {
    $('#inventoryError').textContent = 'This product could not be found. Refresh your records and try again.';
    $('#inventoryError').hidden = false;
    return;
  }
  if (window.UdyamAPI.connected()) {
    try {
      await window.UdyamAPI.recordInventory(productId, {
        quantity,
        note: $('#inventoryNote').value.trim()
      });
    } catch (error) {
      $('#inventoryError').textContent = error.message;
      $('#inventoryError').hidden = false;
      return;
    }
  }
  product.quantity = quantity;
  saveState();
  closeDialog('inventoryDialog');
  render();
  showToast('Stock count saved.');
});

$('#outcomeForm').addEventListener('submit', async event => {
  event.preventDefault();
  const outcomeId = $('#outcomeId').value;
  const notes = $('#outcomeNotes').value.trim();
  const observationEnd = $('#outcomeDate').value;
  if (!outcomeId || !notes || !observationEnd) {
    $('#outcomeError').textContent = 'Enter what you observed and choose an end date.';
    $('#outcomeError').hidden = false;
    return;
  }
  try {
    const updated = await window.UdyamAPI.updateOutcome(outcomeId, {
      observation_end: observationEnd,
      actual_outcome: { notes },
      fairly_comparable: $('#outcomeComparable').checked
    });
    trackedOutcomes = trackedOutcomes.map(item => item.id === updated.id ? updated : item);
    closeDialog('outcomeDialog');
    renderTrackedOutcomes();
    showToast('Observation saved. The comparison does not imply the action caused the result.');
  } catch (error) {
    $('#outcomeError').textContent = error.message;
    $('#outcomeError').hidden = false;
  }
});

$('#recordSaleButton').addEventListener('click', () => openDialog('saleDialog'));
$('#addExpenseButton').addEventListener('click', () => openDialog('expenseDialog'));
$('#expenseShortcut').addEventListener('click', () => openDialog('expenseDialog'));
$('#stockShortcut').addEventListener('click', () => showPage('stock'));
$('#openTasks').addEventListener('click', () => showPage('autopilot'));
$('#askShortcut').addEventListener('click', () => { $('#assistantPanel').scrollIntoView({ behavior: 'smooth', block: 'center' }); $('#askInput').focus({ preventScroll: true }); });
$('#insightsSale').addEventListener('click', () => openDialog('saleDialog'));
$('#addProductButton').addEventListener('click', () => openDialog('productDialog'));
$('#addProductButton2').addEventListener('click', () => openDialog('productDialog'));
$('#startOnboarding').addEventListener('click', () => { wizardStep = 0; wizardAnswers = { business: '', products: '', tracking: '', next: '' }; renderWizard(); openDialog('onboardingDialog'); });
function disconnectBeforeMerchantSwitch() {
  if (!window.UdyamAPI.connected()) return;
  window.UdyamAPI.disconnect();
  state = window.UdyamStore.load();
  $('#backendStatus').textContent = 'Disconnected because you switched merchants. Connect again with that merchant’s token.';
}
$('#sampleButton').addEventListener('click', () => { disconnectBeforeMerchantSwitch(); state.sample = true; saveState(); render(); });
$('#insightsSample').addEventListener('click', () => { disconnectBeforeMerchantSwitch(); state.sample = true; saveState(); render(); showPage('home'); });
$('#exitSample').addEventListener('click', () => { disconnectBeforeMerchantSwitch(); state.sample = false; saveState(); render(); });
$('#wizardSample').addEventListener('click', () => { disconnectBeforeMerchantSwitch(); state.sample = true; saveState(); closeDialog('onboardingDialog'); render(); });
$('#allTransactionsButton').addEventListener('click', () => { showAllTransactions = !showAllTransactions; renderTransactions(); });

$('#saleDate').value = today();
$('#expenseDate').value = today();
$('#saleProduct').addEventListener('change', () => {
  const product = state.products.find(item => item.id === $('#saleProduct').value);
  if (!product) return;
  $('#saleUnitPrice').value = Number.isFinite(product.price) ? product.price : '';
  $('#saleManualName').value = product.name;
  updateSaleTotal();
});
['saleQuantity', 'saleUnitPrice'].forEach(id => $(`#${id}`).addEventListener('input', updateSaleTotal));
$('#saleAmount').addEventListener('input', () => {
  if ($('#saleAmount').value !== '') $('#saleAmount').dataset.manual = 'true';
});

function updateSaleTotal() {
  if ($('#saleAmount').dataset.manual === 'true') return;
  const price = Number($('#saleUnitPrice').value);
  const quantity = Number($('#saleQuantity').value);
  if (Number.isFinite(price) && price >= 0 && Number.isFinite(quantity) && quantity > 0) {
    $('#saleAmount').value = (price * quantity).toFixed(2);
  }
}

$$('[data-close]').forEach(button => button.addEventListener('click', () => closeDialog(button.dataset.close)));
$$('.app-dialog').forEach(dialog => dialog.addEventListener('click', event => {
  if (event.target === dialog) dialog.close();
}));

$('#saleForm').addEventListener('submit', async event => {
  event.preventDefault();
  const quantity = Number($('#saleQuantity').value);
  const unitPrice = $('#saleUnitPrice').value === '' ? null : Number($('#saleUnitPrice').value);
  const enteredAmount = $('#saleAmount').value === '' ? null : Number($('#saleAmount').value);
  const amount = enteredAmount ?? (unitPrice === null ? NaN : quantity * unitPrice);
  const product = state.products.find(item => item.id === $('#saleProduct').value);
  if (!Number.isInteger(quantity) || quantity < 1 || !Number.isFinite(amount) || amount <= 0 || (unitPrice !== null && (!Number.isFinite(unitPrice) || unitPrice < 0))) {
    $('#saleError').textContent = state.language === 'hi' ? 'सही मात्रा और शून्य से बड़ी बिक्री राशि दर्ज करें।' : 'Enter a valid quantity and a sale amount greater than zero.';
    $('#saleError').hidden = false;
    return;
  }
  if (product && Number.isFinite(product.quantity) && quantity > product.quantity) {
    $('#saleError').textContent = state.language === 'hi' ? `आपके पास ${product.quantity} ही उपलब्ध हैं। पहले स्टॉक अपडेट करें।` : `Only ${product.quantity} are listed in stock. Update stock before recording this sale.`;
    $('#saleError').hidden = false;
    return;
  }
  const productName = product?.name || $('#saleManualName').value.trim();
  const costOfGoods = product && Number.isFinite(product.cost) ? product.cost * quantity : null;
  const manualTotal = $('#saleAmount').dataset.manual === 'true';
  const actualUnitPrice = manualTotal ? null : unitPrice ?? (product ? product.price : amount / quantity);
  let serverSale = null;
  if (window.UdyamAPI.connected()) {
    try {
      serverSale = await window.UdyamAPI.createSale({
        product_id: product?.id || null,
        amount,
        date: $('#saleDate').value,
        quantity,
        unit_price: actualUnitPrice,
        note: $('#saleNote').value.trim()
      });
    } catch (error) {
      $('#saleError').textContent = error.message;
      $('#saleError').hidden = false;
      return;
    }
  }
  window.UdyamStore.recordTransaction({
    id: serverSale?.id,
    type: 'sale',
    amount,
    quantity,
    unitPrice: actualUnitPrice,
    productId: product?.id,
    productName,
    costOfGoods,
    note: $('#saleNote').value.trim(),
    date: $('#saleDate').value,
    source: state.sample ? 'demo' : 'user'
  }, !window.UdyamAPI.connected());
  if (product) window.UdyamStore.updateProductStock(product.id, -quantity, !window.UdyamAPI.connected());
  saveState();
  event.target.reset();
  $('#saleAmount').dataset.manual = 'false';
  $('#saleDate').value = today();
  $('#saleError').hidden = true;
  closeDialog('saleDialog');
  render();
  showToast(state.language === 'hi' ? 'बिक्री दर्ज हो गई।' : 'Sale saved. Nice work!');
});

$('#expenseForm').addEventListener('submit', async event => {
  event.preventDefault();
  const amount = Number($('#expenseAmount').value);
  const date = $('#expenseDate').value;
  if (!Number.isFinite(amount) || amount <= 0 || !date) {
    $('#expenseError').textContent = state.language === 'hi' ? 'शून्य से बड़ी राशि और तारीख दर्ज करें।' : 'Enter an amount greater than zero and choose a date.';
    $('#expenseError').hidden = false;
    return;
  }
  let serverExpense = null;
  if (window.UdyamAPI.connected()) {
    try {
      serverExpense = await window.UdyamAPI.createExpense({
        amount,
        date,
        note: $('#expenseNote').value.trim(),
        category: $('#expenseCategory').value
      });
    } catch (error) {
      $('#expenseError').textContent = error.message;
      $('#expenseError').hidden = false;
      return;
    }
  }
  window.UdyamStore.recordTransaction({
    id: serverExpense?.id,
    type: 'expense',
    amount,
    note: $('#expenseNote').value.trim(),
    category: $('#expenseCategory').value,
    date,
    source: state.sample ? 'demo' : 'user'
  }, !window.UdyamAPI.connected());
  saveState();
  event.target.reset();
  $('#expenseError').hidden = true;
  closeDialog('expenseDialog');
  render();
  showToast(state.language === 'hi' ? 'खर्च दर्ज हो गया।' : 'Expense saved.');
});

$('#productForm').addEventListener('submit', async event => {
  event.preventDefault();
  const name = $('#productName').value.trim();
  if (!name) return;
  const rawQuantity = $('#productQuantity').value;
  const rawCost = $('#productCost').value;
  const rawPrice = $('#productPrice').value;
  const rawLeadTime = $('#productLeadTime').value;
  const productInput = {
    name,
    category: null,
    quantity: rawQuantity === '' ? null : Math.max(0, Number(rawQuantity)),
    cost: rawCost === '' ? null : Math.max(0, Number(rawCost)),
    price: rawPrice === '' ? null : Math.max(0, Number(rawPrice)),
    supplier_lead_time_days: rawLeadTime === '' ? null : Math.max(0, Number(rawLeadTime))
  };
  let serverProduct = null;
  if (window.UdyamAPI.connected()) {
    try {
      serverProduct = await window.UdyamAPI.createProduct(productInput);
    } catch (error) {
      showToast(error.message);
      return;
    }
  }
  state.products.push({
    id: serverProduct?.id || `product-${Date.now()}`,
    ...productInput,
    supplierLeadTimeDays: productInput.supplier_lead_time_days
  });
  $('#productSearch').value = '';
  saveState();
  event.target.reset();
  closeDialog('productDialog');
  render();
  showToast('Product added to your list.');
});

$('#productSearch').addEventListener('input', renderProducts);

$('#promotionForm').addEventListener('submit', event => {
  event.preventDefault();
  const cost = Number($('#promoCost').value);
  const regularPrice = Number($('#regularPrice').value);
  const offerPrice = Number($('#offerPrice').value);
  const regularUnits = Number($('#regularUnits').value);
  const offerUnits = Number($('#offerUnits').value);
  const regularMargin = (regularPrice - cost) * regularUnits;
  const offerMargin = (offerPrice - cost) * offerUnits;
  const difference = offerMargin - regularMargin;
  const result = $('#promotionResult');
  result.replaceChildren();
  const heading = document.createElement('strong');
  heading.textContent = difference >= 0 ? `The offer scenario is ${money(difference)} higher in gross margin` : `The offer scenario is ${money(Math.abs(difference))} lower in gross margin`;
  const detail = document.createElement('p');
  detail.textContent = `At your entered quantities: usual-price gross margin ${money(regularMargin)}; offer gross margin ${money(offerMargin)}. This comparison assumes your estimated sales quantities happen.`;
  result.append(heading, detail);
  result.hidden = false;
});

$('#askForm').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('#askInput').value.trim();
  if (!question) return;
  $('#assistantLoading').hidden = false;
  $('#askForm button[type="submit"]').disabled = true;
  $('#askInput').value = '';
  try {
    const result = window.UdyamAPI.connected()
      ? await window.UdyamAPI.ask({ question, language: state.language })
      : await new Promise(resolve => window.setTimeout(() => resolve(formatSimpleAssistant(question)), 280));
    renderAssistantReply(result);
  } catch (error) {
    showToast(error.message);
  } finally {
    $('#assistantLoading').hidden = true;
    $('#askForm button[type="submit"]').disabled = false;
  }
});
$$ ('.question-chip').forEach(button => button.addEventListener('click', () => {
  $('#askInput').value = button.textContent;
  $('#askInput').focus();
}));

$('#twinForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (window.UdyamAPI.connected()) {
    try {
      const result = await window.UdyamAPI.calculateScenario({
        available_inventory: Number($('#twinInventory').value),
        extra_stock: Number($('#twinQuantity').value),
        demand_per_day: Number($('#twinDemand').value),
        period: Number($('#twinPeriod').value),
        price: Number($('#twinPrice').value),
        cost: Number($('#twinCost').value),
        discount: Number($('#twinDiscount').value)
      });
      updateTwin(result);
    } catch (error) {
      showToast(error.message);
      return;
    }
  } else updateTwin();
  showToast('Estimate updated with your numbers.');
});
['twinQuantity', 'twinCost', 'twinPrice', 'twinInventory', 'twinDemand', 'twinPeriod', 'twinDiscount'].forEach(id => $(`#${id}`).addEventListener('input', () => updateTwin()));
$('#twinProduct').addEventListener('change', () => {
  const product = state.products.find(item => item.id === $('#twinProduct').value);
  if (product) {
    if (Number.isFinite(product.cost)) $('#twinCost').value = product.cost;
    if (Number.isFinite(product.price)) $('#twinPrice').value = product.price;
    if (Number.isFinite(product.quantity)) $('#twinInventory').value = product.quantity;
  }
  updateTwin();
});
$('#saveScenarioButton').addEventListener('click', async () => {
  const input = {
    available_inventory: Number($('#twinInventory').value),
    extra_stock: Number($('#twinQuantity').value),
    demand_per_day: Number($('#twinDemand').value),
    period: Number($('#twinPeriod').value),
    price: Number($('#twinPrice').value),
    cost: Number($('#twinCost').value),
    discount: Number($('#twinDiscount').value)
  };
  let serverScenario = null;
  if (window.UdyamAPI.connected()) {
    try {
      serverScenario = await window.UdyamAPI.saveScenario(input);
    } catch (error) {
      showToast(error.message);
      return;
    }
  }
  const proposed = serverScenario ? JSON.parse(serverScenario.result).proposed : JSON.parse($('#twinResult').dataset.proposed || '{}');
  const scenario = {
    id: serverScenario?.id || `scenario-${Date.now()}`,
    quantity: input.extra_stock,
    cost: input.cost,
    price: input.price,
    inventory: input.available_inventory,
    demand: input.demand_per_day,
    period: input.period,
    discount: input.discount,
    savedAt: serverScenario?.created_at.slice(0, 10) || today(),
    outcomes: {
      revenue: Number(proposed.revenue),
      grossProfit: Number(proposed.gross_profit ?? proposed.grossProfit),
      unsold: proposed.unsold_units ?? proposed.unsold
    }
  };
  state.scenarios.push(scenario);
  saveState();
  renderSavedScenarios();
  showToast(window.UdyamAPI.connected() ? 'Scenario saved to the backend.' : 'Scenario saved on this device.');
});

$('#squadButton').addEventListener('click', async () => {
  const question = $('#askInput').value.trim() || 'How can I improve my profit this weekend?';
  if (!window.UdyamAPI.connected()) {
    renderSquad(question);
    return;
  }
  try {
    const result = await window.UdyamAPI.askTeam({ question, language: state.language });
    renderAssistantReply(result);
  } catch (error) {
    showToast(error.message);
  }
});

async function createCampaignDraft() {
  const input = {
    objective: $('#campaignObjective').value,
    objectiveLabel: $('#campaignObjective').selectedOptions[0]?.textContent || $('#campaignObjective').value,
    productId: $('#campaignProduct').value,
    offer: $('#campaignOffer').value,
    audience: $('#campaignAudience').value,
    language: $('#campaignLanguage').value,
    tone: $('#campaignTone').value
  };
  let copy;
  let source = 'demo';
  if (window.UdyamAPI.connected()) {
    const generated = await window.UdyamAPI.generateCampaign({
      product_id: input.productId || null,
      objective: input.objectiveLabel,
      offer: input.offer,
      language: input.language,
      tone: input.tone
    });
    copy = generated.copy;
    source = generated.source;
  } else copy = window.UdyamServices.campaign(input, window.UdyamStore.current());
  $('#campaignCopy').value = copy;
  campaignDraftSource = source;
  $('#campaignSource').textContent = source === 'llm'
    ? 'AI-generated draft · review and edit before sharing. Not sent.'
    : 'Demo copy · not connected to a live AI service. Review before sharing.';
  const product = state.products.find(item => item.id === input.productId);
  $('#creativeHeadline').textContent = product?.name || (input.language === 'hi' ? 'आपकी दुकान का खास ऑफ़र' : 'A little something from your shop');
  $('#creativeOffer').textContent = input.offer || (input.language === 'hi' ? 'ऑफ़र देखने के लिए दुकान पर आएँ' : 'Visit the shop to ask about today’s offer');
  $('#campaignCopy').focus();
}

$('#campaignForm').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    await createCampaignDraft();
    showToast(state.language === 'hi' ? 'ड्राफ़्ट तैयार है। भेजा नहीं गया है।' : 'Draft ready. It has not been sent.');
  } catch (error) {
    showToast(error.message);
  }
});
$('#regenerateCampaign').addEventListener('click', async () => {
  try {
    await createCampaignDraft();
  } catch (error) {
    showToast(error.message);
  }
});
$('#copyCampaign').addEventListener('click', async () => {
  if (!$('#campaignCopy').value.trim()) {
    showToast('Create a draft before copying it.');
    return;
  }
  try {
    await navigator.clipboard.writeText($('#campaignCopy').value);
    showToast('Draft copied. It has not been sent.');
  } catch (error) {
    console.error('Could not copy the campaign draft.', error);
    showToast('Copy is unavailable here. Select the message and copy it manually.');
  }
});
$('#saveCampaign').addEventListener('click', async () => {
  const copy = $('#campaignCopy').value.trim();
  if (!copy) {
    showToast('Create or write a draft before saving it.');
    return;
  }
  const product = state.products.find(item => item.id === $('#campaignProduct').value);
  const campaignInput = {
    product_id: product?.id || null,
    objective: $('#campaignObjective').selectedOptions[0]?.textContent || $('#campaignObjective').value,
    offer: $('#campaignOffer').value,
    copy,
    status: 'draft'
  };
  let savedCampaign = null;
  if (window.UdyamAPI.connected()) {
    try {
      savedCampaign = await window.UdyamAPI.saveCampaign(campaignInput);
    } catch (error) {
      showToast(error.message);
      return;
    }
  }
  state.campaigns.unshift({
    id: savedCampaign?.id || `campaign-${Date.now()}`,
    productId: savedCampaign?.product_id || product?.id || '',
    productName: product?.name || '',
    copy: savedCampaign?.copy || copy,
    objective: savedCampaign?.objective || campaignInput.objective,
    status: 'draft',
    createdAt: savedCampaign?.created_at.slice(0, 10) || today()
  });
  saveState();
  renderCampaigns();
  showToast(window.UdyamAPI.connected() ? 'Campaign saved to the backend. Not sent.' : 'Campaign draft saved on this device. Not sent.');
});

$('#goalForm').addEventListener('submit', async event => {
  event.preventDefault();
  const goal = $('#goalInput').value.trim();
  if (!goal) return;
  if (window.UdyamAPI.connected()) {
    try {
      const tasks = await window.UdyamAPI.createTaskPlan({ title: `Prepare: ${goal}`, goal });
      pendingPlan = tasks.map(task => ({
        id: task.id, title: task.title, requiresApproval: true, completed: false,
        approved: false, goal: task.goal, status: task.status
      }));
    } catch (error) {
      showToast(error.message);
      return;
    }
  } else {
    pendingPlan = window.UdyamServices.taskSuggestions(goal, window.UdyamStore.current(), state.language)
      .map(({ approval, ...task }, index) => ({ ...task, requiresApproval: approval, id: `task-${Date.now()}-${index}`, completed: false, approved: false, goal }));
  }
  $('#planTitle').textContent = goal;
  $('#planCard').hidden = false;
  renderSuggestedTasks();
});

function renderSuggestedTasks() {
  const container = $('#planTaskList');
  container.replaceChildren();
  pendingPlan.forEach(task => {
    const row = document.createElement('article');
    row.className = 'task-row';
    const check = document.createElement('span');
    check.className = 'task-check';
    check.textContent = '○';
    const title = document.createElement('strong');
    title.textContent = task.title;
    const approval = document.createElement('small');
    approval.textContent = task.requiresApproval ? 'Needs your separate approval before buying or contacting anyone' : 'No outside action';
    row.append(check, title, approval);
    container.append(row);
  });
}

$('#approvePlan').addEventListener('click', async () => {
  if (!pendingPlan.length) return;
  const approvedTasks = [];
  if (window.UdyamAPI.connected()) {
    try {
      for (const task of pendingPlan) {
        const approved = await window.UdyamAPI.updateTask(task.id, 'approved');
        approvedTasks.push({
          id: approved.id, title: approved.title, goal: approved.goal,
          requiresApproval: approved.requires_approval, approved: true,
          completed: false, status: approved.status
        });
      }
    } catch (error) {
      if (approvedTasks.length) state.tasks.push(...approvedTasks);
      saveState();
      render();
      showToast(`Some checklist items were saved, but approval failed: ${error.message}`);
      return;
    }
  } else approvedTasks.push(...pendingPlan.map(task => ({ ...task, approved: true, completed: false })));
  state.tasks.push(...approvedTasks);
  saveState();
  pendingPlan = [];
  $('#planCard').hidden = true;
  render();
  showToast('Checklist saved. No purchases or messages were made.');
});
$('#rejectPlan').addEventListener('click', () => {
  if (window.UdyamAPI.connected()) {
    Promise.all(pendingPlan.map(task => window.UdyamAPI.updateTask(task.id, 'rejected')))
      .catch(error => showToast(error.message));
  }
  pendingPlan = [];
  $('#planCard').hidden = true;
  showToast('Suggested checklist cleared.');
});

const wizardQuestions = [
  { title: 'What kind of business do you run?', label: 'Choose what feels closest.', choices: ['Street vendor', 'Kirana or general store', 'Food stall or small eatery', 'Clothing or accessories shop', 'Home-based business', 'Other'] },
  { title: 'What do you sell?', label: 'A few words are plenty.', input: 'For example, fruit, snacks or clothes', field: 'products' },
  { title: 'How do you usually keep track of sales?', label: 'There is no wrong answer.', choices: ['I keep it in my head', 'I write it in a notebook', 'I use my phone or an app', 'I’m just getting started', 'Something else'] },
  { title: 'What would you like to do next?', label: 'You can always come back to this later.', choices: ['Add a product', 'Record my first sale', 'I’ll do this later'] }
];

function renderWizard() {
  const question = wizardQuestions[wizardStep];
  const hi = state.language === 'hi';
  const hindiTitles = ['आप किस तरह का कारोबार करते हैं?', 'आप क्या बेचते हैं?', 'बिक्री का हिसाब आप कैसे रखते हैं?', 'अब आप क्या करना चाहेंगे?'];
  const hindiLabels = ['जो सबसे सही लगे, उसे चुनें।', 'कुछ शब्द काफ़ी हैं।', 'कोई जवाब गलत नहीं है।', 'आप यह काम बाद में भी कर सकते हैं।'];
  const hindiChoices = [
    ['सड़क किनारे दुकान', 'किराना या जनरल स्टोर', 'खाने का ठेला या छोटा रेस्टोरेंट', 'कपड़े या एक्सेसरीज़ की दुकान', 'घर से कारोबार', 'अन्य'],
    [],
    ['मुझे याद रहता है', 'मैं कॉपी में लिखता हूँ', 'मैं फ़ोन या ऐप इस्तेमाल करता हूँ', 'मैं अभी शुरुआत कर रहा हूँ', 'कुछ और'],
    ['एक उत्पाद जोड़ें', 'पहली बिक्री दर्ज करें', 'मैं यह बाद में करूँगा']
  ];
  $('#wizardStepLabel').textContent = `${hi ? 'कुछ आसान सवाल' : 'A FEW EASY QUESTIONS'} · ${wizardStep + 1} ${hi ? 'में से' : 'OF'} 4`;
  $('#wizardQuestion').textContent = hi ? hindiTitles[wizardStep] : question.title;
  $('#wizardProgressBar').style.width = `${((wizardStep + 1) / 4) * 100}%`;
  const choices = $('#wizardChoices');
  choices.replaceChildren();
  $('#wizardInput').hidden = !question.input;
  $('#wizardTextLabel').hidden = !question.input;
  $('#wizardInput').placeholder = question.input ? (hi ? 'उदाहरण: फल, नाश्ता या कपड़े' : question.input) : '';
  $('#wizardInput').value = wizardAnswers[question.field] || '';
  $('#wizardTextLabel').textContent = hi ? hindiLabels[wizardStep] : question.label;
  $('#skipWizard').textContent = hi ? 'अभी छोड़ें' : 'Skip for now';
  $('#wizardBack').textContent = hi ? 'पीछे' : 'Back';
  $('#wizardBack').disabled = wizardStep === 0;
  $('#wizardSample').textContent = hi ? 'या उदाहरण कारोबार देखें' : 'Or explore a sample business';
  if (question.choices) {
    const values = wizardStep === 0 ? ['street vendor', 'kirana or general store', 'food stall or small eatery', 'clothing or accessories shop', 'home-based business', 'other'] : wizardStep === 2 ? ['I keep it in my head', 'I write it in a notebook', 'I use my phone or an app', 'I’m just getting started', 'Something else'] : ['product', 'sale', 'later'];
    question.choices.forEach((label, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'wizard-choice';
      button.textContent = hi ? hindiChoices[wizardStep][index] : label;
      const selectedValue = wizardStep === 0 ? wizardAnswers.business : wizardStep === 2 ? wizardAnswers.tracking : wizardAnswers.next;
      if (selectedValue === values[index]) button.classList.add('selected');
      button.addEventListener('click', () => {
        if (wizardStep === 0) wizardAnswers.business = values[index];
        else if (wizardStep === 2) wizardAnswers.tracking = values[index];
        else wizardAnswers.next = values[index];
        renderWizard();
      });
      choices.append(button);
    });
  }
  $('#wizardNext').textContent = wizardStep === 3 ? (hi ? 'पूरा करें' : 'Finish') : (hi ? 'आगे →' : 'Next →');
  $('#wizardError').hidden = true;
}

$('#wizardNext').addEventListener('click', async () => {
  const question = wizardQuestions[wizardStep];
  if (question.field) wizardAnswers[question.field] = $('#wizardInput').value.trim();
  const answer = wizardStep === 0 ? wizardAnswers.business : wizardStep === 2 ? wizardAnswers.tracking : wizardStep === 3 ? wizardAnswers.next : wizardAnswers.products;
  if (!answer && wizardStep < 3) {
    $('#wizardError').textContent = state.language === 'hi' ? 'जवाब चुनें या इस सवाल को छोड़ दें।' : 'Choose an answer or skip this question.';
    $('#wizardError').hidden = false;
    return;
  }
  if (wizardStep < 3) {
    wizardStep += 1;
    renderWizard();
    return;
  }
  const merchantName = state.name || (wizardAnswers.business ? `${wizardAnswers.business} business` : '');
  if (window.UdyamAPI.connected()) {
    try {
      await window.UdyamAPI.updateMerchant({ name: merchantName, category: wizardAnswers.business });
    } catch (error) {
      showToast(error.message);
      return;
    }
  }
  state.onboarding = { ...wizardAnswers };
  state.category = wizardAnswers.business;
  state.name = merchantName;
  saveState();
  closeDialog('onboardingDialog');
  showToast('Thanks! You can add a product or sale whenever you’re ready.');
  if (wizardAnswers.next === 'product') {
    openDialog('productDialog');
    $('#productName').value = wizardAnswers.products.split(',')[0].trim();
  }
  if (wizardAnswers.next === 'sale') {
    openDialog('saleDialog');
    $('#saleManualName').value = wizardAnswers.products.split(',')[0].trim();
  }
});

$('#wizardBack').addEventListener('click', () => {
  if (wizardStep > 0) {
    if (wizardQuestions[wizardStep].field) wizardAnswers[wizardQuestions[wizardStep].field] = $('#wizardInput').value.trim();
    wizardStep -= 1;
    renderWizard();
  }
});

$('#skipWizard').addEventListener('click', () => {
  if (wizardStep < 3) { wizardStep += 1; renderWizard(); }
  else {
    state.onboarding = { ...wizardAnswers };
    state.category = wizardAnswers.business;
    saveState();
    closeDialog('onboardingDialog');
    showToast(state.language === 'hi' ? 'कोई बात नहीं। आप कभी भी वापस आ सकते हैं।' : 'No problem. You can come back any time.');
  }
});

$('#resetButton').addEventListener('click', () => {
  if (!window.confirm('Clear sales, expenses, products and preferences saved on this device? This cannot be undone.')) return;
  window.UdyamAPI.disconnect();
  window.UdyamStore.resetPersonal();
  state = window.UdyamStore.load();
  render();
  showToast('Your saved information has been cleared.');
});

render();
