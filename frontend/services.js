/* Deterministic business calculations and local mock assistant services. */
window.UdyamServices = (() => {
  const clampNonNegative = value => Number.isFinite(value) ? Math.max(0, value) : 0;

  /**
   * Caps units sold at available stock. Gross profit uses COGS for sold units;
   * leftover stock is shown separately and is not subtracted from gross profit.
   * @param {{inventory:number,demandPerDay:number,period:number,price:number,cost:number,discount:number}} input
   */
  function project(input) {
    const inventory = Math.floor(clampNonNegative(input.inventory));
    const period = Number.isFinite(input.period) ? Math.min(90, Math.max(1, input.period)) : 1;
    const forecastDemand = Math.floor(clampNonNegative(input.demandPerDay) * period);
    const units = Math.min(inventory, forecastDemand);
    const price = clampNonNegative(input.price) * (1 - Math.min(100, clampNonNegative(input.discount)) / 100);
    const revenue = units * price;
    const cogs = units * clampNonNegative(input.cost);
    return { inventory, units, revenue, cogs, grossProfit: revenue - cogs, unsold: inventory - units, unsoldValue: (inventory - units) * clampNonNegative(input.cost) };
  }

  function compareScenario(input) {
    const baseline = project({ ...input, inventory: input.availableInventory, discount: 0 });
    const proposed = project({ ...input, inventory: input.availableInventory + input.extraStock, discount: input.discount });
    return { baseline, proposed, addedStockCost: clampNonNegative(input.extraStock) * clampNonNegative(input.cost) };
  }

  function weekTotals(merchant, endDate) {
    const end = new Date(`${endDate}T12:00:00`);
    const start = new Date(end);
    start.setDate(start.getDate() - 6);
    const startKey = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
    const sales = merchant.sales.filter(item => item.date >= startKey && item.date <= endDate);
    const expenses = merchant.expenses.filter(item => item.date >= startKey && item.date <= endDate);
    return { sales: sales.reduce((sum, item) => sum + item.amount, 0), expenses: expenses.reduce((sum, item) => sum + item.amount, 0), saleCount: sales.length };
  }

  function answer(question, merchant, language, currentDate) {
    const query = question.toLowerCase();
    const hi = language === 'hi';
    const daySales = merchant.sales.filter(item => item.date === currentDate);
    const todayRevenue = daySales.reduce((sum, item) => sum + item.amount, 0);
    const todayCogsKnown = daySales.length > 0 && daySales.every(item => Number.isFinite(item.costOfGoods));
    const todayGross = todayCogsKnown ? todayRevenue - daySales.reduce((sum, item) => sum + item.costOfGoods, 0) : null;
    const weekly = weekTotals(merchant, currentDate);
    const action = { label: hi ? 'आज की बिक्री दर्ज करें' : 'Record a sale', page: 'home', dialog: 'saleDialog' };
    let title;
    let message;
    let evidence = [];
    let nextAction = action;

    if (/earn|kamai|sale|sales|कमाई|बिक्री/.test(query)) {
      title = hi ? 'आज की बिक्री' : 'Today’s sales';
      message = daySales.length
        ? (hi ? `आज ${todayRevenue.toLocaleString('en-IN')} रुपये की बिक्री दर्ज है।` : `${new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(todayRevenue)} in sales recorded today.`)
        : (hi ? 'आज की बिक्री अभी दर्ज नहीं है। आप कुल राशि लिखकर शुरुआत कर सकते हैं।' : 'No sales have been recorded today yet. You can start with just a total amount.');
      evidence = daySales.length ? [`${daySales.length} recorded sale${daySales.length === 1 ? '' : 's'} · ${currentDate}`, todayGross === null ? 'Cost details are incomplete, so gross profit is not shown.' : `Estimated gross profit before other expenses: ${new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(todayGross)}`] : ['Based on records entered on this device.'];
    } else if (/profit|weekend|margin|improve/.test(query)) {
      title = hi ? 'इस हफ़्ते की तस्वीर' : 'A look at this week';
      message = weekly.saleCount
        ? (hi ? `इस हफ़्ते ${weekly.saleCount} बिक्री दर्ज हैं। कीमत और लागत की जानकारी वाले उत्पाद देखें, फिर किसी ऑफ़र को भेजने से पहले आज़माएँ।` : `${weekly.saleCount} sales are recorded this week. Check product costs and margins, then compare a promotion before sharing it.`)
        : (hi ? 'अभी इस हफ़्ते की बिक्री दर्ज नहीं है। पहले बिक्री और उत्पाद लागत जोड़ें; फिर मुनाफ़े के बारे में उपयोगी तुलना कर सकेंगे।' : 'There are no sales recorded this week yet. Add a few sales and product costs before comparing profit ideas.');
      evidence = [`${weekly.saleCount} sales · ${new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(weekly.sales)} revenue this week`, `${merchant.products.length} products on the current list`];
      nextAction = { label: hi ? 'ऑफ़र की तुलना करें' : 'Compare an offer', page: 'twin' };
    } else if (/stock|buy|order|replenish|खरीद|स्टॉक|मंगव/.test(query)) {
      const ranked = [...merchant.products].sort((a, b) => (a.quantity ?? Infinity) - (b.quantity ?? Infinity));
      const item = ranked[0];
      title = hi ? 'स्टॉक की अगली जाँच' : 'A stock check to start with';
      message = item
        ? (hi ? `${item.name} की मात्रा ${item.quantity === null ? 'दर्ज नहीं है' : `${item.quantity} है`}। अभी बिक्री इतिहास से भरोसेमंद ऑर्डर मात्रा नहीं निकाली जा सकती। पहले स्टॉक गिनें और हाल की बिक्री देखें।` : `${item.name} is ${item.quantity === null ? 'not counted yet' : `at ${item.quantity} in stock`}. There is not enough history to recommend a reliable order quantity. Count your stock and review recent sales first.`)
        : (hi ? 'अभी कोई उत्पाद सूची में नहीं है। एक उत्पाद जोड़ें या पहले कारोबार के बारे में बताएँ।' : 'There are no products on the list yet. Add one when you are ready; this preview will not guess an order quantity.');
      evidence = [item ? `Lowest listed stock: ${item.name} · ${item.quantity ?? 'not counted'}` : 'No stock records have been entered.'];
      nextAction = { label: hi ? 'स्टॉक देखें' : 'Check stock', page: 'stock' };
    } else if (/product|sell the most|top item|popular|बिके|उत्पाद/.test(query)) {
      const totals = new Map();
      merchant.sales.forEach(sale => {
        if (sale.productId && sale.quantity) totals.set(sale.productId, (totals.get(sale.productId) || 0) + sale.quantity);
      });
      const best = merchant.products.map(product => ({ product, quantity: totals.get(product.id) || 0 })).sort((a, b) => b.quantity - a.quantity)[0];
      title = hi ? 'उत्पादों की बिक्री' : 'Product sales';
      message = best && best.quantity
        ? (hi ? `${best.name} सबसे ज़्यादा दर्ज मात्रा में बिका: ${best.quantity} इकाई। यह बिक्री रिकॉर्ड पर आधारित है।` : `${best.name} has the most recorded units sold: ${best.quantity}. This is based only on sales linked to a product.`)
        : (hi ? 'अभी किसी उत्पाद से जुड़ी बिक्री दर्ज नहीं है। बिक्री दर्ज करते समय उत्पाद चुनें, फिर तुलना यहाँ दिखेगी।' : 'No sales are linked to products yet. Choose a product when recording a sale to compare item performance.');
      evidence = best && best.quantity ? [`${best.quantity} units linked to ${best.product.name}`] : ['No product-level sales evidence yet.'];
      nextAction = { label: hi ? 'उत्पाद देखें' : 'View products', page: 'stock' };
    } else if (/offer|festival|diwali|campaign|discount|ऑफर|दिवाली/.test(query)) {
      title = hi ? 'ऑफ़र का ड्राफ़्ट' : 'Draft a shop offer';
      message = hi ? 'उत्पाद, छूट और संदेश का लहजा चुनें। ड्राफ़्ट आप जाँचेंगे; यहाँ से ग्राहकों को संदेश नहीं भेजा जाएगा।' : 'Choose a product, offer and tone. You can review the draft; this preview does not message customers.';
      evidence = ['Draft content stays on this device until you decide what to do with it.'];
      nextAction = { label: hi ? 'अभियान बनाएँ' : 'Open Campaign Studio', page: 'campaigns' };
    } else if (/plan|prepare|task|diwali|तैयारी/.test(query)) {
      title = hi ? 'एक आसान कार्य योजना' : 'A small action plan';
      message = hi ? 'स्टॉक जाँचें, बिक्री के लिए ज़रूरी सामान देखें, एक ऑफ़र की तुलना करें और संदेश साझा करने से पहले उसकी समीक्षा करें।' : 'Check your stock, identify anything you need to replenish, compare an offer, and review any message before you share it.';
      evidence = ['Nothing is purchased or sent automatically.'];
      nextAction = { label: hi ? 'योजना बनाएँ' : 'Create a checklist', page: 'autopilot' };
    } else if (/price|what if|scenario|कीमत/.test(query)) {
      title = hi ? 'बदलाव का अनुमान लगाएँ' : 'Compare a change';
      message = hi ? 'बिज़नेस ट्विन में कीमत, लागत, माँग और उपलब्ध स्टॉक बदलकर अनुमान देखें।' : 'Adjust price, cost, expected demand and available inventory in the Business Twin to see an estimate.';
      evidence = ['Units sold are capped at available stock. Gross profit excludes other shop expenses.'];
      nextAction = { label: hi ? 'बिज़नेस ट्विन खोलें' : 'Open Business Twin', page: 'twin' };
    } else {
      title = hi ? 'मैं इसमें मदद कर सकता हूँ' : 'A few ways I can help';
      message = hi ? 'आज की बिक्री, कम स्टॉक, सबसे ज़्यादा बिकने वाले उत्पाद, ऑफ़र या किसी तैयारी के बारे में पूछें।' : 'Ask about today’s sales, low stock, best-selling items, an offer, or getting ready for a busy day.';
      evidence = ['Answers use the records and assumptions currently saved on this device.'];
    }
    return { title, message, evidence, nextAction };
  }

  function squad(question, merchant, language) {
    const hi = language === 'hi';
    const stock = merchant.products.length;
    const knownMargins = merchant.products.filter(product => Number.isFinite(product.cost) && Number.isFinite(product.price));
    const recentSales = merchant.sales.filter(sale => sale.date >= window.UdyamData.date(6)).length;
    return {
      title: hi ? 'टीम की सलाह · आपके डेटा के आधार पर' : 'A team view · based on your records',
      agents: [
        { name: hi ? 'विकास' : 'Growth', message: recentSales ? (hi ? `पिछले 7 दिनों में ${recentSales} बिक्री दर्ज है; इससे ऑफ़र के अवसर समझने में मदद मिल सकती है।` : `${recentSales} sales recorded in the last 7 days can reveal a useful offer opportunity.`) : (hi ? 'विकास का अवसर समझने के लिए कुछ बिक्री दर्ज करें।' : 'Add some sales before estimating a growth opportunity.'), evidence: hi ? `${recentSales} हाल की बिक्री` : `${recentSales} recent sales` },
        { name: hi ? 'स्टॉक' : 'Inventory', message: stock ? (hi ? `${stock} उत्पाद सूची में हैं। ज़्यादा उपलब्धता का वादा करने से पहले मात्रा जाँचें।` : `${stock} products are listed. Check quantities before promising extra availability.`) : (hi ? 'कोई उत्पाद सूची में नहीं है; उपलब्ध स्टॉक की पुष्टि नहीं हो सकती।' : 'No products are listed; the team cannot verify stock.'), evidence: hi ? `${stock} सूचीबद्ध उत्पाद` : `${stock} listed products` },
        { name: hi ? 'मुनाफ़ा' : 'Profit', message: knownMargins.length ? (hi ? `${knownMargins.length} उत्पादों की कीमत और लागत दर्ज है; छूट से सकल मुनाफ़ा कम हो सकता है।` : `${knownMargins.length} products have entered prices and costs; discounts can reduce gross margin.`) : (hi ? 'उत्पाद लागत उपलब्ध नहीं है, इसलिए मुनाफ़े की भरोसेमंद तुलना नहीं हो सकती।' : 'Product costs are missing, so a reliable margin comparison is not available.'), evidence: hi ? `${stock} में से ${knownMargins.length} उत्पादों की कीमत और लागत दर्ज` : `${knownMargins.length} of ${stock} products have cost and price` },
        { name: hi ? 'मार्केटिंग' : 'Marketing', message: hi ? 'छोटा और साफ़ ऑफ़र ग्राहकों को समझने में आसान हो सकता है। संदेश भेजने से पहले ड्राफ़्ट जाँचें।' : 'A small, clearly explained offer may be easier for customers to understand. Draft and review the message before sharing.', evidence: hi ? 'कोई ग्राहक सूची या संदेश सेवा इस्तेमाल नहीं होती।' : 'No customer list or messaging connection is used.' }
      ],
      recommendation: recentSales && knownMargins.length
        ? (hi ? 'ऑफ़र साझा करने से पहले उसे दर्ज की गई उत्पाद लागत और मुनाफ़े से तुलना करें।' : 'Compare an offer against your known product margin before you share it.')
        : (hi ? 'पहले हाल की बिक्री और उत्पाद लागत जोड़ें। फिर बिज़नेस ट्विन में ऑफ़र की तुलना करें।' : 'First add recent sales and product cost details. Then compare an offer using the Business Twin.'),
      question
    };
  }

  function campaign(input, merchant) {
    const product = merchant.products.find(item => item.id === input.productId);
    const productName = product?.name || merchant.products[0]?.name || (input.language === 'hi' ? 'हमारे सामान' : 'our shop');
    const offer = input.offer.trim() || (input.objective === 'thank_customers' ? 'A little thank-you treat' : 'Ask us about today’s offer');
    const hi = input.language === 'hi';
    const greeting = input.tone === 'festive' ? (hi ? 'त्योहार की ढेरों शुभकामनाएँ!' : 'A little festive cheer for you!') : input.tone === 'simple' ? (hi ? 'नमस्ते!' : 'Hello!') : (hi ? 'नमस्ते जी!' : 'Hello there!');
    const audience = input.audience.trim();
    const purpose = input.objective === 'thank_customers'
      ? (hi ? 'हमारे साथ जुड़े रहने के लिए धन्यवाद।' : 'Thank you for being part of our shop.')
      : input.objective === 'new_product'
        ? (hi ? 'कुछ नया देखने के लिए आइए।' : 'Come by and discover something new.')
        : input.objective === 'clear_stock'
          ? (hi ? 'सीमित स्टॉक पर यह खास ऑफ़र उपलब्ध है।' : 'This offer is available on selected stock while it lasts.')
          : '';
    const audienceLine = audience ? (hi ? `${audience} के लिए एक छोटा सा संदेश:` : `A little note for ${audience.toLowerCase()}:`) : '';
    return [greeting, audienceLine, purpose, hi ? `${productName} पर हमारे पास आपके लिए कुछ खास है: ${offer}।` : `We have something special for you on ${productName}: ${offer}.`, hi ? 'पास की दुकान पर आइए। यह संदेश सिर्फ़ एक ड्राफ़्ट है—भेजने से पहले जाँच लें।' : 'Drop by your local shop. This is a draft only—please review before sharing.'].filter(Boolean).join('\n');
  }

  function taskSuggestions(goal, merchant, language) {
    const hi = language === 'hi';
    return [
      { title: hi ? 'मौजूदा स्टॉक गिनें' : 'Review current inventory', approval: false },
      { title: merchant.products.length ? (hi ? 'किन उत्पादों का स्टॉक बढ़ाना है, पहचानें' : 'Identify products to consider replenishing') : (hi ? 'पहले उत्पाद सूची जोड़ें' : 'Add your first products'), approval: false },
      { title: hi ? 'ऑफ़र के अनुमानों की तुलना करें' : 'Compare a promotional scenario', approval: false },
      { title: hi ? 'ग्राहकों के लिए संदेश का ड्राफ़्ट बनाएँ' : 'Prepare a marketing message draft', approval: false },
      { title: hi ? 'किसी भी खरीद से पहले अपनी मंज़ूरी दें' : 'Approve any purchase before placing an order', approval: true },
      { title: hi ? 'ग्राहकों को संदेश भेजने से पहले मंज़ूरी दें' : 'Approve any customer message before sharing', approval: true }
    ];
  }

  return { project, compareScenario, answer, squad, campaign, taskSuggestions, weekTotals };
})();
