"""
Server status — standalone
==========================

CPU / memory / temperature / fan + GPU monitor. Split out of the original
combined app so it runs independently of the DigestPapers config dashboard.

Routes:
    /         landing page
    /monitor  live dashboard
    /stats    JSON metrics (polled by the dashboard)

No database, no config — just host metrics.
"""

from flask import Flask, render_template, jsonify
import psutil
import subprocess

from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # allow all origins


def get_gpu_stats():
    """Return (usage%, fan%, temp°C, mem_total_MB, mem_used_MB) via nvidia-smi,
    or zeros if no NVIDIA GPU / driver is present."""
    try:
        output = subprocess.check_output([
            'nvidia-smi',
            '--query-gpu=utilization.gpu,fan.speed,temperature.gpu,memory.total,memory.used',
            '--format=csv,noheader,nounits'
        ]).decode('utf-8').strip()

        if not output or ',' not in output:
            return 0, 0, 0, 0, 0

        usage, fan, temp, mem_total, mem_used = output.split(', ')
        return int(usage), int(fan), int(temp), int(mem_total), int(mem_used)
    except Exception:
        return 0, 0, 0, 0, 0


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/monitor')
def monitor():
    return render_template('dashboard.html')


@app.route('/stats')
def stats():
    cpu_usage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    mem_usage = memory.percent
    mem_total = memory.total // (1024 * 1024)  # MB

    temps = psutil.sensors_temperatures()
    cpu_temp = temps['coretemp'][0].current if 'coretemp' in temps and temps['coretemp'] else 0

    fans = psutil.sensors_fans()
    fan_speed = 0
    if fans:
        for fan_list in fans.values():
            for fan in fan_list:
                if hasattr(fan, 'current') and fan.current > 0:
                    fan_speed = fan.current
                    break

    gpu_usage, gpu_fan, gpu_temp, gpu_mem_total, gpu_mem_used = get_gpu_stats()
    gpu_mem_usage = (gpu_mem_used / gpu_mem_total * 100) if gpu_mem_total > 0 else 0

    return jsonify({
        'cpu': cpu_usage,
        'memory': mem_usage,
        'memory_total': mem_total,
        'cpu_fan': fan_speed if fan_speed > 0 else "Firmware-controlled or not reporting",
        'cpu_temp': cpu_temp,
        'gpu': gpu_usage,
        'gpu_fan': gpu_fan,
        'gpu_temp': gpu_temp,
        'gpu_memory_usage': gpu_mem_usage,
        'gpu_memory_total': gpu_mem_total
    })


if __name__ == '__main__':
    # Own port (5001) so it can run alongside the config app (5000) on the host.
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True)
