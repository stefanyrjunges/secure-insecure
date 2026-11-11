// Read the notice as plain text from the query string
const notice = new URLSearchParams(window.location.search).get("notice");

// The notice comes from the URL, so textContent shows markup as text instead of running injected code
document.getElementById("search-notice").textContent = notice || "";
