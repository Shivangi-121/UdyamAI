/* Optional backend client. Credentials stay in memory and are never written to browser storage. */
window.UdyamAPI = (() => {
  const DEMO_STORAGE_KEY = 'udyamai-demo-state-v1';
  let connection = null;
  let profile = null;
  let demoProfile = null;
  let refreshPromise = null;

  function normalizedEmail(email) {
    const normalized = String(email || '').trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
      throw new Error('Enter a valid email address.');
    }
    return normalized;
  }

  function readDemoState() {
    try {
      const stored = localStorage.getItem(DEMO_STORAGE_KEY);
      if (!stored) return { profiles: [], activeEmail: null };
      const state = JSON.parse(stored);
      if (
        !state ||
        !Array.isArray(state.profiles) ||
        state.profiles.some(item => !item || typeof item.email !== 'string') ||
        (state.activeEmail !== null && typeof state.activeEmail !== 'string')
      ) {
        throw new Error('Saved demo account data is invalid.');
      }
      return state;
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error('Saved demo account data could not be read. Clear this site’s local data and try again.');
      }
      if (error instanceof DOMException) {
        throw new Error('Browser storage is unavailable. Enable site storage to use demo sign-in.');
      }
      throw error;
    }
  }

  function createDemoProfile(email, fullName = '', businessName = '') {
    return {
      id: `demo-${encodeURIComponent(email)}`,
      email,
      full_name: fullName,
      merchant_id: 'personal',
      business_name: businessName,
      business_category: '',
      business_model: null,
      sales_channels: [],
      business_stage: null,
      sales_tracking: null,
      business_size: null,
      currency: 'INR',
      business_location: null,
      goals: [],
      preferred_language: 'en',
      response_detail: 'balanced',
      interaction_mode: 'both',
      theme: 'system',
      notifications: {},
      onboarding_step: 0,
      onboarding_answers: {},
      onboarding_completed: false
    };
  }

  function persistDemoProfile(nextProfile) {
    try {
      const state = readDemoState();
      const existingIndex = state.profiles.findIndex(item => item.email === nextProfile.email);
      if (existingIndex >= 0) state.profiles[existingIndex] = nextProfile;
      else state.profiles.push(nextProfile);
      state.activeEmail = nextProfile.email;
      localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(state));
      demoProfile = nextProfile;
      profile = nextProfile;
    } catch (error) {
      if (error instanceof DOMException) {
        throw new Error('Browser storage is unavailable or full. Enable site storage and try again.');
      }
      throw error;
    }
  }

  function registerDemoAccount(payload) {
    const email = normalizedEmail(payload.email);
    const state = readDemoState();
    if (state.profiles.some(item => item.email === email)) {
      throw new Error('A demo profile with this email already exists on this device. Sign in instead.');
    }
    const nextProfile = createDemoProfile(
      email,
      String(payload.full_name || '').trim(),
      String(payload.business_name || '').trim()
    );
    persistDemoProfile(nextProfile);
    return nextProfile;
  }

  function signInDemoAccount(email) {
    const normalized = normalizedEmail(email);
    const savedProfile = readDemoState().profiles.find(item => item.email === normalized);
    if (!savedProfile) {
      throw new Error('No demo profile for this email exists on this device. Create an account first.');
    }
    persistDemoProfile(savedProfile);
    return savedProfile;
  }

  function restoreDemoSession() {
    try {
      const state = readDemoState();
      if (!state.activeEmail) return null;
      const savedProfile = state.profiles.find(item => item.email === state.activeEmail);
      if (!savedProfile) {
        throw new Error('The saved demo session is invalid. Sign in again.');
      }
      demoProfile = savedProfile;
      profile = savedProfile;
      return savedProfile;
    } catch (error) {
      if (error instanceof DOMException) {
        throw new Error('Browser storage is unavailable. Enable site storage to restore your demo session.');
      }
      throw error;
    }
  }

  function merchantPath(suffix = '') {
    if (!connection) throw new Error('Connect to the backend first.');
    return `/api/merchants/${encodeURIComponent(connection.merchantId)}${suffix}`;
  }

  function csrfToken() {
    const cookie = document.cookie.split('; ').find(item => item.startsWith('udyamai_csrf='));
    return cookie ? decodeURIComponent(cookie.slice('udyamai_csrf='.length)) : '';
  }

  async function sendRequest(baseUrl, path, options = {}, token = '') {
    let response;
    const headers = { ...options.headers };
    if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    if (token) headers.Authorization = `Bearer ${token}`;
    if (path === '/api/auth/session') {
      headers['X-CSRF-Token'] = csrfToken();
    }
    try {
      response = await fetch(`${baseUrl}${path}`, {
        ...options,
        headers,
        credentials: 'include'
      });
    } catch (error) {
      throw new Error('Could not reach the backend. Check that it is running and retry.');
    }
    return response;
  }

  async function parseResponse(response) {
    if (!response.ok) {
      let message = `Backend request failed (${response.status}).`;
      try {
        const body = await response.json();
        message = body.message || body.detail || message;
      } catch (error) {
        console.error('Could not read backend error response.', error);
      }
      throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
  }

  async function request(path, options = {}) {
    if (!connection) throw new Error('Connect to the backend first.');
    let response = await sendRequest(connection.baseUrl, path, options, connection.token);
    if (response.status === 401 && connection.account) {
      try {
        const refreshed = await refreshAccountSession(connection.baseUrl);
        response = await sendRequest(connection.baseUrl, path, options, refreshed.access_token);
      } catch (error) {
        connection = null;
        profile = null;
        window.dispatchEvent(new CustomEvent('udyamai:session-expired'));
        throw error;
      }
    }
    return parseResponse(response);
  }

  async function authRequest(baseUrl, path, options = {}) {
    return parseResponse(await sendRequest(baseUrl.replace(/\/+$/, ''), path, options));
  }

  async function loadRecords() {
    const [health, merchant, products, sales, expenses, campaigns, tasks, scenarios, insights, outcomes] = await Promise.all([
      fetch(`${connection.baseUrl}/api/health`, { credentials: 'include' }).then(async response => {
        if (!response.ok) throw new Error(`Backend health check failed (${response.status}).`);
        return response.json();
      }),
      request(merchantPath()),
      request(merchantPath('/products')),
      request(merchantPath('/sales')),
      request(merchantPath('/expenses')),
      request(merchantPath('/campaigns')),
      request(merchantPath('/tasks')),
      request(merchantPath('/scenarios')),
      request(merchantPath('/insights')),
      request(merchantPath('/outcomes'))
    ]);
    return { status: health, merchant, products, sales, expenses, campaigns, tasks, scenarios, insights, outcomes };
  }

  async function connect(baseUrl, token, merchantId) {
    connection = { baseUrl: baseUrl.replace(/\/+$/, ''), token, merchantId, account: false };
    profile = null;
    try {
      return await loadRecords();
    } catch (error) {
      connection = null;
      throw error;
    }
  }

  async function activateAccount(baseUrl, authResponse) {
    profile = authResponse.profile;
    connection = {
      baseUrl: baseUrl.replace(/\/+$/, ''),
      token: authResponse.access_token,
      merchantId: authResponse.profile.merchant_id,
      account: true
    };
    try {
      return { ...(await loadRecords()), profile };
    } catch (error) {
      connection = null;
      profile = null;
      throw error;
    }
  }

  async function signIn(baseUrl, email, password) {
    const authResponse = await authRequest(baseUrl, '/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    return activateAccount(baseUrl, authResponse);
  }

  async function register(baseUrl, payload) {
    const authResponse = await authRequest(baseUrl, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    return activateAccount(baseUrl, authResponse);
  }

  async function refreshAccountSession(baseUrl) {
    if (!refreshPromise) {
      refreshPromise = authRequest(baseUrl, '/api/auth/session', { method: 'POST' })
        .then(authResponse => {
          profile = authResponse.profile;
          if (connection) connection.token = authResponse.access_token;
          return authResponse;
        })
        .finally(() => { refreshPromise = null; });
    }
    return refreshPromise;
  }

  async function restoreSession(baseUrl) {
    const authResponse = await authRequest(baseUrl, '/api/auth/session', { method: 'POST' });
    return activateAccount(baseUrl, authResponse);
  }

  async function signOut() {
    if (connection?.account) {
      try {
        await authRequest(connection.baseUrl, '/api/auth/session', { method: 'DELETE' });
      } finally {
        connection = null;
        profile = null;
      }
    } else {
      connection = null;
    }
    if (demoProfile) {
      try {
        const state = readDemoState();
        state.activeEmail = null;
        localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(state));
      } catch {
        throw new Error('Could not clear the demo session from browser storage.');
      }
      demoProfile = null;
      profile = null;
    }
  }

  function disconnect() {
    connection = null;
    profile = null;
  }

  function connected() {
    return Boolean(connection);
  }
  function authenticated() {
    return Boolean(demoProfile || connection?.account);
  }

  const json = value => ({ method: 'POST', body: JSON.stringify(value) });
  const patch = value => ({ method: 'PATCH', body: JSON.stringify(value) });

  function askVoice({ audio, language, context, speechEnabled }) {
    const body = new FormData();
    body.append('audio', audio, audio.name || 'recording.webm');
    body.append('language', language || 'auto');
    body.append('context_json', JSON.stringify(context || []));
    body.append('speech_enabled', String(Boolean(speechEnabled)));
    return request(merchantPath('/assistant/voice'), { method: 'POST', body });
  }

  async function downloadCsv(path, fallbackName) {
    if (!connection) throw new Error('Connect to the backend first.');
    let response = await sendRequest(connection.baseUrl, path, {}, connection.token);
    if (response.status === 401 && connection.account) {
      try {
        const refreshed = await refreshAccountSession(connection.baseUrl);
        response = await sendRequest(connection.baseUrl, path, {}, refreshed.access_token);
      } catch (error) {
        connection = null;
        profile = null;
        window.dispatchEvent(new CustomEvent('udyamai:session-expired'));
        throw error;
      }
    }
    if (!response.ok) {
      await parseResponse(response);
      return;
    }
    const disposition = response.headers.get('Content-Disposition') || '';
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] || fallbackName;
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function previewImport(file, recordType, mapping = null) {
    const body = new FormData();
    body.append('file', file, file.name);
    body.append('record_type', recordType);
    if (mapping) body.append('mapping_json', JSON.stringify(mapping));
    return request(merchantPath('/imports/preview'), { method: 'POST', body });
  }

  async function confirmImport(file, recordType, mapping, digest) {
    const body = new FormData();
    body.append('file', file, file.name);
    body.append('record_type', recordType);
    body.append('mapping_json', JSON.stringify(mapping));
    body.append('expected_digest', digest);
    body.append('confirmed', 'true');
    return request(merchantPath('/imports/confirm'), { method: 'POST', body });
  }

  return {
    connect,
    signInDemoAccount,
    registerDemoAccount,
    restoreDemoSession,
    restoreSession,
    signOut,
    disconnect,
    connected,
    authenticated,
    profile: () => demoProfile || profile,
    loadRecords,
    analytics: (startDate, endDate) => request(
      merchantPath(`/analytics?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`)
    ),
    previewImport,
    confirmImport,
    downloadTemplate: recordType => downloadCsv(
      merchantPath(`/imports/templates/${encodeURIComponent(recordType)}`),
      `${recordType}-template.csv`
    ),
    exportCsv: (recordType, startDate, endDate) => {
      const query = recordType === 'products'
        ? ''
        : `?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`;
      return downloadCsv(
        merchantPath(`/exports/${encodeURIComponent(recordType)}${query}`),
        `${recordType}.csv`
      );
    },
    updateProfile: payload => {
      if (!demoProfile) return request('/api/auth/profile', patch(payload));
      const updatedProfile = { ...demoProfile, ...payload };
      persistDemoProfile(updatedProfile);
      return Promise.resolve(updatedProfile);
    },
    requestPasswordReset: (baseUrl, email) => authRequest(baseUrl, '/api/auth/password-reset/request', json({ email })),
    completePasswordReset: (baseUrl, token, password) => authRequest(baseUrl, '/api/auth/password-reset/complete', json({ token, password })),
    updateMerchant: payload => request(merchantPath(), patch(payload)),
    createProduct: payload => request(merchantPath('/products'), json(payload)),
    recordInventory: (productId, payload) => request(merchantPath(`/products/${encodeURIComponent(productId)}/inventory`), json(payload)),
    createSale: payload => request(merchantPath('/sales'), json(payload)),
    createExpense: payload => request(merchantPath('/expenses'), json(payload)),
    calculateScenario: payload => request(merchantPath('/scenarios/calculate'), json(payload)),
    saveScenario: payload => request(merchantPath('/scenarios'), json(payload)),
    generateCampaign: payload => request(merchantPath('/campaigns/generate'), json(payload)),
    saveCampaign: payload => request(merchantPath('/campaigns'), json(payload)),
    createTask: payload => request(merchantPath('/tasks'), json(payload)),
    createTaskPlan: payload => request(merchantPath('/tasks/plan'), json(payload)),
    updateTask: (taskId, update) => request(
      merchantPath(`/tasks/${encodeURIComponent(taskId)}`),
      patch(typeof update === 'string' ? { status: update } : update)
    ),
    deleteTask: taskId => request(merchantPath(`/tasks/${encodeURIComponent(taskId)}`), { method: 'DELETE' }),
    analyzeBusiness: () => request(merchantPath('/intelligence/analyze'), { method: 'POST' }),
    updateInsight: (insightId, status) => request(merchantPath(`/insights/${encodeURIComponent(insightId)}`), patch({ status })),
    createOutcome: payload => request(merchantPath('/outcomes'), json(payload)),
    updateOutcome: (outcomeId, payload) => request(merchantPath(`/outcomes/${encodeURIComponent(outcomeId)}`), patch(payload)),
    ask: payload => request(merchantPath('/assistant'), json(payload)),
    askVoice,
    askTeam: payload => request(merchantPath('/assistant/team'), json(payload))
  };
})();
