const notice = new URLSearchParams(window.location.search).get("notice");
document.getElementById("search-notice").textContent = notice || "";
