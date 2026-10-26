/* Shared prototype data and JSDoc contracts; this file contains no UI logic. */
window.UdyamData = (() => {
  const date = offset => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    const businessDay = new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day) - offset));
    return businessDay.toISOString().slice(0, 10);
  };

  /** @typedef {{id:string,name:string,quantity:number|null,cost:number|null,price:number|null,category?:string}} Product */
  /** @typedef {{id:string,amount:number,date:string,note:string,productId?:string,quantity?:number,unitPrice?:number,source?:string}} Sale */
  /** @typedef {{id:string,amount:number,date:string,note:string,category:string,source?:string}} Expense */
  /** @typedef {{id:string,type:string,amount:number,date:string,note:string,source:string,productId?:string,quantity?:number,unitPrice?:number,category?:string}} Transaction */
  /** @typedef {{quantity:number,cost:number,price:number,demand:number,inventory:number,discount:number,period:number}} Scenario */
  /** @typedef {{id:string,name:string,category:string,products:Product[],sales:Sale[],expenses:Expense[],onboarding:object,transactions:Transaction[],campaigns:object[],tasks:object[],scenarios:Scenario[]}} MerchantData */

  /** @returns {MerchantData} */
  function emptyMerchant() {
    return { name: '', category: '', products: [], sales: [], expenses: [], onboarding: {}, transactions: [], campaigns: [], tasks: [], scenarios: [] };
  }

  /** @returns {Record<string, MerchantData>} */
  function createDemos() {
    const coconuts = [
      { id: 'coconut', name: 'Fresh coconuts', quantity: 32, cost: 20, price: 35, category: 'Fresh produce' },
      { id: 'water', name: 'Coconut water', quantity: 18, cost: 8, price: 25, category: 'Drinks' },
      { id: 'lime', name: 'Limes', quantity: 45, cost: 2, price: 5, category: 'Fresh produce' }
    ];
    const kirana = [
      { id: 'rice', name: 'Basmati rice (1 kg)', quantity: 28, cost: 72, price: 92, category: 'Staples' },
      { id: 'dal', name: 'Toor dal (1 kg)', quantity: 21, cost: 96, price: 120, category: 'Staples' },
      { id: 'oil', name: 'Cooking oil (1 L)', quantity: 14, cost: 118, price: 145, category: 'Groceries' },
      { id: 'tea', name: 'Tea (250 g)', quantity: 36, cost: 54, price: 70, category: 'Beverages' },
      { id: 'soap', name: 'Bathing soap', quantity: 8, cost: 26, price: 35, category: 'Household' }
    ];
    const demo = (id, name, category, products, salesPlan, costs) => {
      const sales = salesPlan.map(([offset, productIndex, quantity]) => {
        const product = products[productIndex];
        return {
          id: `${id}-sale-${offset}-${productIndex}`,
          productId: product.id,
          amount: quantity * product.price,
          quantity,
          unitPrice: product.price,
          date: date(offset),
          note: `${product.name} · ${quantity} sold`,
          source: 'demo',
          costOfGoods: quantity * product.cost
        };
      });
      const expenses = costs.map(([offset, amount, note, expenseCategory]) => ({
        id: `${id}-expense-${offset}`,
        amount,
        date: date(offset),
        note,
        category: expenseCategory,
        source: 'demo'
      }));
      const transactions = [...sales.map(sale => ({ ...sale, type: 'sale' })), ...expenses.map(expense => ({ ...expense, type: 'expense' }))]
        .sort((a, b) => b.date.localeCompare(a.date));
      return {
        id, name, category, products, sales, expenses, transactions,
        onboarding: { business: category, products: products.map(product => product.name).join(', '), tracking: 'I write it in a notebook', next: 'later' },
        campaigns: [], tasks: [], scenarios: []
      };
    };
    return {
      coconut: demo('coconut', 'Raju’s Coconut Cart', 'Street vendor', coconuts,
        [[0, 0, 12], [0, 1, 8], [1, 0, 10], [1, 2, 16], [2, 0, 9], [2, 1, 7], [3, 0, 14], [4, 1, 10], [5, 0, 11], [6, 2, 20], [7, 0, 8], [8, 1, 9], [9, 0, 13]],
        [[0, 180, 'Fresh stock', 'Stock'], [2, 80, 'Cart and ice', 'Supplies'], [5, 150, 'Morning produce', 'Stock']]),
      kirana: demo('kirana', 'Shanti General Store', 'Kirana store', kirana,
        [[0, 0, 3], [0, 1, 2], [0, 3, 4], [1, 2, 2], [1, 4, 3], [2, 0, 5], [2, 3, 6], [3, 1, 4], [3, 2, 2], [4, 0, 3], [4, 4, 5], [5, 3, 7], [6, 1, 3], [7, 2, 4], [8, 0, 4], [9, 3, 8], [10, 4, 4], [11, 1, 5], [12, 2, 3], [13, 0, 6]],
        [[0, 680, 'Weekly supplier delivery', 'Stock'], [1, 120, 'Delivery and packing', 'Supplies'], [3, 210, 'Electricity bill', 'Utilities'], [6, 450, 'Staple restock', 'Stock'], [10, 95, 'Shop supplies', 'Supplies']])
    };
  }

  return { emptyMerchant, createDemos, date };
})();
