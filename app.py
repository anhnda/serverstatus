from flask import Flask, render_template, jsonify
import psutil
import subprocess

app = Flask(__name__)

def get_gpu_stats():
    try:
        output = subprocess.check_output([
            'nvidia-smi',
            '--query-gpu=utilization.gpu,fan.speed',
            '--format=csv,noheader,nounits'
        ]).decode('utf-8').strip()
        usage, fan = output.split(', ')
        return int(usage), int(fan)
    except Exception:
        return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/stats')
def stats():
    cpu_usage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    mem_usage = memory.percent
    temps = psutil.sensors_temperatures()
    cpu_temp = temps['coretemp'][0].current if 'coretemp' in temps and temps['coretemp'] else 0

    fans = psutil.sensors_fans()
    fan_speed = fans['cpu_fan'][0].current if 'cpu_fan' in fans and fans['cpu_fan'] else 0
    gpu_usage, gpu_fan = get_gpu_stats()

    return jsonify({
        'cpu': cpu_usage,
        'memory': mem_usage,
        'cpu_fan': fan_speed,
        'cpu_temp': cpu_temp,
        'gpu': gpu_usage or 0,
        'gpu_fan': gpu_fan or 0
    })

if __name__ == '__main__':
    app.run(debug=True)
