const token = sessionStorage.getItem("dzmm-admin-token") || prompt("Admin token");
if (token) sessionStorage.setItem("dzmm-admin-token", token);

const headers = {"X-Admin-Token": token || ""};
const result = document.querySelector("#result");

async function refresh() {
  const response = await fetch("/api/status", {headers});
  if (!response.ok) {
    result.textContent = `Status unavailable (${response.status})`;
    return;
  }
  const status = await response.json();
  document.querySelector("#state").textContent = status.state ?? "unknown";
  document.querySelector("#last-heartbeat").textContent = status.last_heartbeat ?? "never";
  document.querySelector("#queue-counts").textContent = JSON.stringify(status.queue_counts ?? {});
}

for (const button of document.querySelectorAll("button[data-action]")) {
  button.addEventListener("click", async () => {
    const response = await fetch(button.dataset.action, {method: "POST", headers});
    result.textContent = response.ok ? "Command accepted" : `Command rejected (${response.status})`;
    await refresh();
  });
}

refresh();
