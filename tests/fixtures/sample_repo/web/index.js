const { fetchInvoices } = require("./api");

async function render() {
  const invoices = await fetchInvoices();
  document.title = `${invoices.length} invoices`;
}

render();
