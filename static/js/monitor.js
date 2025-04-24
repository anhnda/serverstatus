async function fetchStats() {
    const res = await fetch('/api/stats');
    const data = await res.json();

    const cpu = Math.round(data.cpu);
    const ram = Math.round(data.ram);
    const gpu = data.gpu !== null ? Math.round(data.gpu) : null;

    document.getElementById("cpu-bar").style.width = `${cpu}%`;
    document.getElementById("cpu-bar").innerText = `${cpu}%`;

    document.getElementById("ram-bar").style.width = `${ram}%`;
    document.getElementById("ram-bar").innerText = `${ram}%`;

    if (gpu !== null) {
        document.getElementById("gpu-bar").style.width = `${gpu}%`;
        document.getElementById("gpu-bar").innerText = `${gpu}%`;
    } else {
        document.getElementById("gpu-bar").style.width = "100%";
        document.getElementById("gpu-bar").innerText = "N/A";
        document.getElementById("gpu-bar").classList.replace("bg-warning", "bg-secondary");
    }

    document.getElementById("power-status").innerText = data.power ? "Plugged In" : "On Battery";
}

setInterval(fetchStats, 2000);
fetchStats();
