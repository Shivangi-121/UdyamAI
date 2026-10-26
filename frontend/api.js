/* Optional backend client. Credentials stay in memory and are never written to browser storage. */
window.UdyamAPI = (() => {
  let connection = null;
  let profile = null;
  let refreshPromise = null;

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
    return Boolean(connection?.account);
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

  return {
    connect,
    signIn,
    register,
    restoreSession,
    signOut,
    disconnect,
    connected,
    authenticated,
    profile: () => profile,
    updateProfile: payload => request('/api/auth/profile', patch(payload)),
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
