/* Local persistence adapter. Replace this module when a backend is available. */
window.UdyamStore = (() => {
  const KEY = 'udyamai-preview-v2';
  const LEGACY_KEY = 'udyamai-preview-v1';
  let model;
  const remoteMerchantIds = new Set();

  function freshModel() {
    return {
      mode: 'simple',
      language: 'en',
      theme: 'system',
      currentMerchantId: 'personal',
      merchants: {
        personal: { id: 'personal', ...window.UdyamData.emptyMerchant() },
        ...window.UdyamData.createDemos()
      }
    };
  }

  function normalize(parsed) {
    const fresh = freshModel();
    if (!parsed || typeof parsed !== 'object') return fresh;
    fresh.mode = ['simple', 'smart', 'advanced'].includes(parsed.mode) ? parsed.mode : 'simple';
    fresh.language = parsed.language === 'hi' ? 'hi' : 'en';
    fresh.theme = ['system', 'light', 'dark'].includes(parsed.theme) ? parsed.theme : 'system';
    fresh.currentMerchantId = parsed.currentMerchantId in fresh.merchants ? parsed.currentMerchantId : 'personal';
    if (parsed.merchants && typeof parsed.merchants === 'object') {
      for (const id of ['personal', 'coconut', 'kirana']) {
        const incoming = parsed.merchants[id];
        if (!incoming || typeof incoming !== 'object') continue;
        fresh.merchants[id] = {
          ...fresh.merchants[id],
          ...incoming,
          products: Array.isArray(incoming.products) ? incoming.products : fresh.merchants[id].products,
          sales: Array.isArray(incoming.sales) ? incoming.sales : fresh.merchants[id].sales,
          expenses: Array.isArray(incoming.expenses) ? incoming.expenses : fresh.merchants[id].expenses,
          transactions: Array.isArray(incoming.transactions) ? incoming.transactions : fresh.merchants[id].transactions,
          onboarding: incoming.onboarding && typeof incoming.onboarding === 'object' ? incoming.onboarding : {},
          campaigns: Array.isArray(incoming.campaigns) ? incoming.campaigns : [],
          tasks: Array.isArray(incoming.tasks) ? incoming.tasks : [],
          scenarios: Array.isArray(incoming.scenarios) ? incoming.scenarios : []
        };
      }
    }
    return fresh;
  }

  function current() {
    return model.merchants[model.currentMerchantId];
  }

  function load() {
    try {
      const stored = localStorage.getItem(KEY);
      if (stored) model = normalize(JSON.parse(stored));
      else {
        const legacy = localStorage.getItem(LEGACY_KEY);
        if (!legacy) model = freshModel();
        else {
          const previous = JSON.parse(legacy);
          model = freshModel();
          model.mode = ['simple', 'smart', 'advanced'].includes(previous.mode) ? previous.mode : 'simple';
          model.language = previous.language === 'hi' ? 'hi' : 'en';
          model.theme = ['system', 'light', 'dark'].includes(previous.theme) ? previous.theme : 'system';
          model.merchants.personal = {
            ...model.merchants.personal,
            name: previous.businessName || '',
            category: previous.onboarding?.business || '',
            products: Array.isArray(previous.products) ? previous.products.map((product, index) => ({ id: product.id || `product-${index}`, cost: null, price: null, ...product })) : [],
            sales: Array.isArray(previous.sales) ? previous.sales.map((sale, index) => ({ id: sale.id || `sale-${index}`, ...sale })) : [],
            expenses: Array.isArray(previous.expenses) ? previous.expenses.map((expense, index) => ({ id: expense.id || `expense-${index}`, category: 'Other', ...expense })) : [],
            onboarding: previous.onboarding || {}
          };
          model.merchants.personal.transactions = [
            ...model.merchants.personal.sales.map(item => ({ ...item, type: 'sale', source: 'user' })),
            ...model.merchants.personal.expenses.map(item => ({ ...item, type: 'expense', source: 'user' }))
          ].sort((a, b) => b.date.localeCompare(a.date));
          persist();
        }
      }
    } catch (error) {
      console.error('Could not load saved UdyamAI information.', error);
      model = freshModel();
    }
    return makeView();
  }

  function persist() {
    try {
      const localModel = { ...model, merchants: { ...model.merchants } };
      remoteMerchantIds.forEach(id => delete localModel.merchants[id]);
      localModel.currentMerchantId = remoteMerchantIds.has(model.currentMerchantId) ? 'personal' : model.currentMerchantId;
      localStorage.setItem(KEY, JSON.stringify(localModel));
      localStorage.removeItem(LEGACY_KEY);
    } catch (error) {
      console.error('Could not save UdyamAI information on this device.', error);
      window.dispatchEvent(new CustomEvent('udyam:storage-error'));
    }
  }

  function persistPreferences() {
    try {
      const stored = localStorage.getItem(KEY);
      const saved = stored ? JSON.parse(stored) : freshModel();
      saved.mode = model.mode;
      saved.language = model.language;
      saved.theme = model.theme;
      saved.currentMerchantId = remoteMerchantIds.has(model.currentMerchantId) ? 'personal' : model.currentMerchantId;
      localStorage.setItem(KEY, JSON.stringify(saved));
    } catch (error) {
      console.error('Could not save UdyamAI preferences on this device.', error);
      window.dispatchEvent(new CustomEvent('udyam:storage-error'));
    }
  }

  function makeView() {
    return new Proxy(model, {
      get(target, key) {
        if (key === 'sample') return target.currentMerchantId !== 'personal';
        if (key === 'business') return current();
        if (['sales', 'expenses', 'products', 'onboarding', 'transactions', 'campaigns', 'tasks', 'scenarios', 'name', 'category'].includes(key)) return current()[key];
        return target[key];
      },
      set(target, key, value) {
        if (key === 'sample') {
          target.currentMerchantId = value ? (target.currentMerchantId === 'personal' ? 'coconut' : target.currentMerchantId) : 'personal';
          return true;
        }
        if (['sales', 'expenses', 'products', 'onboarding', 'transactions', 'campaigns', 'tasks', 'scenarios', 'name', 'category'].includes(key)) {
          current()[key] = value;
          return true;
        }
        target[key] = value;
        return true;
      }
    });
  }

  function save() {
    persist();
  }

  function savePreferences() {
    persistPreferences();
  }

  function merchant(id) {
    return model.merchants[id] || null;
  }

  function attachMerchant(id, values) {
    remoteMerchantIds.add(id);
    if (!model.merchants[id]) {
      model.merchants[id] = {
        id,
        ...window.UdyamData.emptyMerchant(),
        name: values.name || '',
        category: values.category || ''
      };
    }
    model.currentMerchantId = id;
  }

  function selectMerchant(id) {
    if (!model.merchants[id]) return false;
    model.currentMerchantId = id;
    persist();
    return true;
  }

  function recordTransaction(transaction, shouldPersist = true) {
    const item = { ...transaction, id: transaction.id || `${transaction.type}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, source: transaction.source || 'user' };
    if (item.type === 'sale') current().sales.push(item);
    if (item.type === 'expense') current().expenses.push(item);
    current().transactions.push(item);
    current().transactions.sort((a, b) => b.date.localeCompare(a.date));
    if (shouldPersist) persist();
    return item;
  }

  function updateProductStock(productId, quantityDelta, shouldPersist = true) {
    const product = current().products.find(item => item.id === productId);
    if (!product || !Number.isFinite(product.quantity)) return false;
    product.quantity = Math.max(0, product.quantity + quantityDelta);
    if (shouldPersist) persist();
    return true;
  }

  function resetPersonal() {
    remoteMerchantIds.clear();
    model.merchants.personal = { id: 'personal', ...window.UdyamData.emptyMerchant() };
    model.mode = 'simple';
    model.language = 'en';
    model.theme = 'system';
    model.currentMerchantId = 'personal';
    persist();
  }

  return { load, save, savePreferences, current, merchant, attachMerchant, selectMerchant, recordTransaction, updateProductStock, resetPersonal };
})();
