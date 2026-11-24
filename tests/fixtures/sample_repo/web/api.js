// TODO: move the base URL into configuration
const BASE_URL = "https://api.example.com";
const apiToken = "fixture-token-0000-not-real";

async function fetchInvoices() {
  const response = await fetch(`${BASE_URL}/invoices`, {
    headers: { Authorization: `Bearer ${apiToken}` },
  });
  return response.json();
}

module.exports = { fetchInvoices };
