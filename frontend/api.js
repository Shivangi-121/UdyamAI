/* Optional backend client. Credentials stay in memory and are never written to browser storage. */
window.UdyamAPI = (() => {
  let connection = null;

  function merchantPath(suffix = '') {
    if (!connection) throw new Error('Connect to the backend first.');
    return `/api/merchants/${encodeURIComponent(connection.merchantId)}${suffix}`;
  }

  async function request(path, options = {}) {
    if (!connection) throw new Error('Connect to the backend first.');
    let response;
    try {
      response = await fetch(`${connection.baseUrl}${path}`, {
        ...options,
        headers: {
          Authorization: `Bearer ${connection.token}`,
          'Content-Type': 'application/json',
          ...options.headers
        }
      });
    } catch (error) {
      throw new Error('Could not reach the backend. Check that it is running and retry.');
    }
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

  async function connect(baseUrl, token, merchantId) {
    connection = { baseUrl: baseUrl.replace(/\/+$/, ''), token, merchantId };
    try {
      let health;
      try {
        health = await fetch(`${connection.baseUrl}/api/health`);
      } catch (error) {
        throw new Error('Could not reach the backend. Check that it is running and retry.');
      }
      if (!health.ok) throw new Error(`Backend health check failed (${health.status}).`);
      const status = await health.json();
      const [merchant, products, sales, expenses, campaigns, tasks, scenarios] = await Promise.all([
        request(merchantPath()),
        request(merchantPath('/products')),
        request(merchantPath('/sales')),
        request(merchantPath('/expenses')),
        request(merchantPath('/campaigns')),
        request(merchantPath('/tasks')),
        request(merchantPath('/scenarios'))
      ]);
      return { status, merchant, products, sales, expenses, campaigns, tasks, scenarios };
    } catch (error) {
      connection = null;
      throw error;
    }
  }

  function disconnect() {
    connection = null;
  }

  function connected() {
    return Boolean(connection);
  }

  const json = value => ({ method: 'POST', body: JSON.stringify(value) });
  const patch = value => ({ method: 'PATCH', body: JSON.stringify(value) });

  return {
    connect,
    disconnect,
    connected,
    updateMerchant: payload => request(merchantPath(), patch(payload)),
    createProduct: payload => request(merchantPath('/products'), json(payload)),
    createSale: payload => request(merchantPath('/sales'), json(payload)),
    createExpense: payload => request(merchantPath('/expenses'), json(payload)),
    calculateScenario: payload => request(merchantPath('/scenarios/calculate'), json(payload)),
    saveScenario: payload => request(merchantPath('/scenarios'), json(payload)),
    generateCampaign: payload => request(merchantPath('/campaigns/generate'), json(payload)),
    saveCampaign: payload => request(merchantPath('/campaigns'), json(payload)),
    createTask: payload => request(merchantPath('/tasks'), json(payload)),
    createTaskPlan: payload => request(merchantPath('/tasks/plan'), json(payload)),
    updateTask: (taskId, status) => request(merchantPath(`/tasks/${encodeURIComponent(taskId)}`), patch({ status })),
    deleteTask: taskId => request(merchantPath(`/tasks/${encodeURIComponent(taskId)}`), { method: 'DELETE' }),
    ask: payload => request(merchantPath('/assistant'), json(payload)),
    askTeam: payload => request(merchantPath('/assistant/team'), json(payload))
  };
})();
