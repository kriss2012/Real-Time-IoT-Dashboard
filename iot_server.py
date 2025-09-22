import flask
import time
import random
import threading
import requests
import json
import os

# --- Core Flask App Setup ---
app = flask.Flask(__name__)

# --- State Persistence ---
STATE_FILE = 'iot_platform_state.json'

# --- In-Memory Device Storage ---
DEVICES = {}
DEVICE_LOCK = threading.Lock()

# --- Weather API Configuration ---
PACHORA_LAT = 20.66
PACHORA_LON = 75.35
WEATHER_API_URL = f"https://api.open-meteo.com/v1/forecast?latitude={PACHORA_LAT}&longitude={PACHORA_LON}&current=rain"

# --- Device Simulation Classes ---

class DynamicSimulatedDevice(threading.Thread):
    """A generic class to simulate any user-created IoT device with custom metrics."""
    def __init__(self, device_id, device_type, metrics, config=None):
        super().__init__()
        self.device_id = device_id
        self.device_type = device_type
        self.metrics = metrics
        self.config = config or {"alerts": {}}
        self.data_history = []
        self.latest_data_values = {metric['name']: (metric['min'] + metric['max']) / 2 for metric in metrics}
        self.status = "Online"
        self.alerts = {}
        self.running = True
        self.daemon = True

    def run(self):
        while self.running:
            current_values = {}
            self.alerts = {}
            for metric in self.metrics:
                metric_name = metric['name']
                current_val = self.latest_data_values[metric_name]
                change = (metric['max'] - metric['min']) * 0.1 * (random.random() - 0.5)
                new_val = current_val + change
                new_val = max(metric['min'] - (metric['max']-metric['min'])*0.2, min(metric['max'] + (metric['max']-metric['min'])*0.2, new_val))
                self.latest_data_values[metric_name] = new_val
                current_values[metric_name] = round(new_val, 2)

                alert_config = self.config.get('alerts', {}).get(metric_name, {})
                if alert_config.get('max') is not None and new_val > alert_config['max']:
                    self.alerts[metric_name] = f"high_alert (>{alert_config['max']})"
                elif alert_config.get('min') is not None and new_val < alert_config['min']:
                    self.alerts[metric_name] = f"low_alert (<{alert_config['min']})"

            self.status = "Alert" if self.alerts else "Online"

            with DEVICE_LOCK:
                self.data_history.append({
                    "device_id": self.device_id, "device_type": self.device_type,
                    "timestamp": time.strftime('%H:%M:%S'),
                    **current_values
                })
                if len(self.data_history) > 100: self.data_history.pop(0)

            time.sleep(random.uniform(2, 5))

    def stop(self):
        self.running = False

    def get_latest_data(self):
        if self.data_history: return self.data_history[-1]
        return {}
    
    def get_history_for_plot(self):
        history = self.data_history
        timestamps = [d['timestamp'] for d in history]
        data_points = {m['name']: [d.get(m['name']) for d in history] for m in self.metrics}
        return {'timestamps': timestamps, **data_points}
    
    def update_config(self, new_config):
        self.config = new_config

class WeatherStationDevice(threading.Thread):
    """A dedicated class for the real-time weather station device."""
    def __init__(self, device_id, device_type):
        super().__init__()
        self.device_id = device_id
        self.device_type = device_type
        self.metrics = [{'name': 'rainfall', 'unit': 'mm', 'min': 0, 'max': 10}]
        self.config = {"alerts": {}}
        self.data_history = []
        self.status = "Initializing"
        self.alerts = {}
        self.running = True
        self.daemon = True

    def _fetch_weather_data(self):
        """Helper method to fetch and process data from the weather API."""
        rainfall = -1
        try:
            response = requests.get(WEATHER_API_URL)
            if response.status_code == 200:
                weather_data = response.json()
                rainfall = weather_data.get('current', {}).get('rain', 0.0)
                self.status = "Online"
            else:
                self.status = "API Error"
        except requests.RequestException:
            self.status = "Offline"

        with DEVICE_LOCK:
            self.data_history.append({
                "device_id": self.device_id, "device_type": self.device_type,
                "timestamp": time.strftime('%H:%M:%S'),
                "rainfall": round(rainfall, 2)
            })
            if len(self.data_history) > 100: self.data_history.pop(0)

    def run(self):
        self._fetch_weather_data()  # Fetch data immediately on start
        while self.running:
            time.sleep(300)  # Wait for 5 minutes before the next update
            self._fetch_weather_data()

    def stop(self):
        self.running = False

    def get_latest_data(self):
        if self.data_history: return self.data_history[-1]
        return {}

    def get_history_for_plot(self):
        history = self.data_history
        timestamps = [d['timestamp'] for d in history]
        return {'timestamps': timestamps, 'rainfall': [d.get('rainfall') for d in history]}

    def update_config(self, new_config):
        pass # Not configurable


# --- HTML & Frontend Code ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Echo Gears - IoT Monitoring Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.plot.ly/plotly-2.12.1.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Roboto', sans-serif; background-color: #111827; }
        .card { background-color: #1f2937; border: 1px solid #374151; transition: all 0.3s ease; }
        .card:hover { transform: translateY(-5px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2); }
        .card.alert-border { border-color: #EF4444; box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
        .modal-backdrop { background-color: rgba(0,0,0,0.75); backdrop-filter: blur(5px); }
        .modal-content { background-color: #1f2937; max-height: 90vh; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; }
        .status-online { background-color: #10B981; } .status-alert { background-color: #EF4444; animation: pulse 1.5s infinite; }
        .status-offline, .status-api-error, .status-initializing { background-color: #F59E0B; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body class="text-gray-200">
    <!-- Main Content -->
    <div class="container mx-auto p-4 md:p-8">
        <header class="flex flex-wrap justify-between items-center mb-12">
            <div class="text-center md:text-left mb-4 md:mb-0">
                <h1 class="text-4xl md:text-5xl font-bold text-white"><span class="text-cyan-400">Echo</span><span class="text-gray-400">Gears</span></h1>
                <p class="text-gray-400 mt-2">Dynamic IoT Device Monitoring Platform</p>
            </div>
            <button id="add-device-btn" class="bg-cyan-500 hover:bg-cyan-600 text-white font-bold py-2 px-6 rounded-lg transition-colors">Add New Device</button>
        </header>
        <main id="device-grid" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-8"></main>
    </div>

    <!-- Add Device Modal -->
    <div id="add-device-modal" class="fixed inset-0 z-50 hidden items-center justify-center modal-backdrop">
        <div class="modal-content w-full max-w-lg p-6 rounded-lg shadow-xl overflow-y-auto">
            <h2 class="text-2xl font-bold mb-6">Add New IoT Device</h2>
            <div class="space-y-4">
                <input type="text" id="new-device-id" placeholder="Device ID (e.g., WAREHOUSE-A)" class="w-full bg-gray-700 p-2 rounded border border-gray-600 focus:outline-none focus:border-cyan-500">
                <input type="text" id="new-device-type" placeholder="Device Type (e.g., Environment Sensor)" class="w-full bg-gray-700 p-2 rounded border border-gray-600 focus:outline-none focus:border-cyan-500">
            </div>
            <h3 class="font-bold mt-6 mb-2">Metrics to Monitor</h3>
            <div id="new-metrics-container" class="space-y-2"></div>
            <button id="add-metric-btn" class="text-sm text-cyan-400 hover:text-cyan-300 mt-2">+ Add Metric</button>
            <div class="flex justify-end gap-4 mt-8">
                <button id="cancel-add-device-btn" class="bg-gray-600 hover:bg-gray-700 text-white py-2 px-4 rounded">Cancel</button>
                <button id="confirm-add-device-btn" class="bg-cyan-500 hover:bg-cyan-600 text-white py-2 px-4 rounded">Create Device</button>
            </div>
        </div>
    </div>
    
    <!-- Config Modal -->
    <div id="config-modal" class="fixed inset-0 z-50 hidden items-center justify-center modal-backdrop">
        <div class="modal-content w-full max-w-lg p-6 rounded-lg shadow-xl overflow-y-auto">
            <h2 class="text-2xl font-bold mb-6">Configure: <span id="config-device-id" class="text-cyan-400"></span></h2>
            <h3 class="font-bold mb-4">Alert Thresholds</h3>
            <div id="alert-config-container" class="space-y-4"></div>
            <div class="flex justify-end gap-4 mt-8">
                <button id="cancel-config-btn" class="bg-gray-600 hover:bg-gray-700 text-white py-2 px-4 rounded">Cancel</button>
                <button id="save-config-btn" class="bg-cyan-500 hover:bg-cyan-600 text-white py-2 px-4 rounded">Save Changes</button>
            </div>
        </div>
    </div>

<script>
    // --- State & UI Elements ---
    let currentConfigDeviceId = null;
    const modals = {
        add: document.getElementById('add-device-modal'),
        config: document.getElementById('config-modal')
    };

    // --- Core Functions ---
    async function apiCall(endpoint, method = 'GET', body = null) {
        const options = {
            method,
            headers: {'Content-Type': 'application/json'}
        };
        if (body) options.body = JSON.stringify(body);
        try {
            const response = await fetch(endpoint, options);
            if (!response.ok) {
                const errorData = await response.json();
                alert(`Error: ${errorData.error}`);
                return null;
            }
            return response.json();
        } catch (err) {
            alert('Network error. Is the server running?');
            return null;
        }
    }

    function createCardHTML(device) {
        let metricsHTML = '';
        for (const metric of device.metrics) {
            metricsHTML += `
                <div id="metric-container-${device.device_id}-${metric.name}" class="flex justify-between items-baseline p-2 rounded">
                    <span class="text-gray-400 capitalize">${metric.name.replace(/_/g, ' ')}:</span>
                    <span id="metric-${device.device_id}-${metric.name}" class="text-2xl font-bold text-white">-- ${metric.unit}</span>
                </div>`;
        }

        return `
            <div class="flex justify-between items-start">
                <div>
                    <h2 class="text-xl font-bold text-cyan-400 uppercase">${device.device_id.replace(/_/g, ' ')}</h2>
                    <p class="text-sm text-gray-500">${device.device_type}</p>
                </div>
                <div class="flex items-center gap-4">
                    <div class="flex items-center gap-2">
                        <div id="status-dot-${device.device_id}" class="status-dot"></div>
                        <span id="status-text-${device.device_id}" class="text-sm">--</span>
                    </div>
                    <button class="config-btn" data-device-id="${device.device_id}">⚙️</button>
                    <button class="delete-btn" data-device-id="${device.device_id}">🗑️</button>
                </div>
            </div>
            <div id="metrics-${device.device_id}" class="space-y-1 my-4">${metricsHTML}</div>
            <div id="plot-${device.device_id}" class="plot-container flex-grow min-h-[300px]"></div>
        `;
    }

    function initializeDashboard(devices) {
        const grid = document.getElementById('device-grid');
        devices.forEach(device => {
            if (!document.getElementById(`card-${device.device_id}`)) {
                const card = document.createElement('div');
                card.className = 'card rounded-lg p-6 shadow-lg flex flex-col';
                card.id = `card-${device.device_id}`;
                card.innerHTML = createCardHTML(device);
                grid.appendChild(card);
                Plotly.newPlot(`plot-${device.device_id}`, [], getPlotLayout(), {responsive: true});
            }
        });
    }

    function updateUI(devices) {
        const grid = document.getElementById('device-grid');
        const currentCardIds = Array.from(grid.children).map(c => c.id);
        const deviceIds = devices.map(d => `card-${d.device_id}`);

        currentCardIds.filter(id => !deviceIds.includes(id)).forEach(id => document.getElementById(id).remove());
        
        devices.forEach(device => {
            let card = document.getElementById(`card-${device.device_id}`);
            if (!card) {
                initializeDashboard([device]);
                card = document.getElementById(`card-${device.device_id}`);
            }

            const statusDot = document.getElementById(`status-dot-${device.device_id}`);
            const statusText = document.getElementById(`status-text-${device.device_id}`);
            statusDot.className = `status-dot status-${device.status.toLowerCase().replace(' ', '-')}`;
            statusText.textContent = device.status;
            card.classList.toggle('alert-border', device.status === 'Alert');
            
            for (const metric of device.metrics) {
                const metricValEl = document.getElementById(`metric-${device.device_id}-${metric.name}`);
                const metricContainerEl = document.getElementById(`metric-container-${device.device_id}-${metric.name}`);
                if (metricValEl && device.latest_data) {
                    metricValEl.textContent = `${device.latest_data[metric.name] || '--'} ${metric.unit}`;
                }
                if (metricContainerEl) {
                    const isAlert = device.alerts && device.alerts[metric.name];
                    metricContainerEl.style.backgroundColor = isAlert ? 'rgba(239, 68, 68, 0.2)' : 'transparent';
                }
            }
            
            updatePlot(device);
        });
    }
    
    function updatePlot(device) {
        const history = device.history;
        const dataKeys = Object.keys(history).filter(k => k !== 'timestamps');
        const plotDiv = document.getElementById(`plot-${device.device_id}`);
        if (!plotDiv) return;

        let traces = [];
        dataKeys.forEach((key, index) => {
            traces.push({
                x: history.timestamps,
                y: history[key],
                name: key.replace('_', ' '),
                type: 'scatter',
                mode: 'lines',
                line: {width: 2}
            });
        });
        
        Plotly.react(plotDiv, traces, getPlotLayout(device.device_type), {responsive: true});
    }

    function getPlotLayout(title = 'Real-Time Data') {
        return {
            title: { text: title, font: { color: '#E5E7EB', size: 14 } },
            autosize: true, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
            margin: { l: 40, r: 20, b: 40, t: 40, pad: 4 }, font: { color: '#9CA3AF' },
            xaxis: { gridcolor: '#374151' }, yaxis: { gridcolor: '#374151' },
            legend: { x: 0.01, y: 0.99, bgcolor: 'rgba(0,0,0,0.3)' }
        };
    }

    // --- Modal Logic & Event Handlers ---
    function openModal(modal) { modal.classList.remove('hidden'); modal.classList.add('flex'); }
    function closeModal(modal) { modal.classList.add('hidden'); modal.classList.remove('flex'); }

    function renderMetricInput(index) {
        return `
            <div class="metric-group grid grid-cols-4 gap-2 items-center">
                <input type="text" placeholder="Metric Name" class="metric-name col-span-2 w-full bg-gray-800 p-2 rounded border border-gray-600">
                <input type="text" placeholder="Unit" class="metric-unit w-full bg-gray-800 p-2 rounded border border-gray-600">
                <div class="col-span-1 grid grid-cols-2 gap-1">
                    <input type="number" placeholder="Min" class="metric-min w-full bg-gray-800 p-2 rounded border border-gray-600">
                    <input type="number" placeholder="Max" class="metric-max w-full bg-gray-800 p-2 rounded border border-gray-600">
                </div>
            </div>`;
    }
    
    document.getElementById('add-device-btn').addEventListener('click', () => {
        document.getElementById('new-device-id').value = '';
        document.getElementById('new-device-type').value = '';
        document.getElementById('new-metrics-container').innerHTML = renderMetricInput(0);
        openModal(modals.add);
    });
    document.getElementById('add-metric-btn').addEventListener('click', () => {
        const container = document.getElementById('new-metrics-container');
        container.insertAdjacentHTML('beforeend', renderMetricInput(container.children.length));
    });
    document.getElementById('cancel-add-device-btn').addEventListener('click', () => closeModal(modals.add));
    document.getElementById('confirm-add-device-btn').addEventListener('click', async () => {
        const deviceId = document.getElementById('new-device-id').value.trim();
        const deviceType = document.getElementById('new-device-type').value.trim();
        if (!deviceId || !deviceType) { return alert('Device ID and Type are required.'); }

        const metrics = [];
        document.querySelectorAll('.metric-group').forEach(group => {
            const name = group.querySelector('.metric-name').value.trim().toLowerCase().replace(/\\s/g, '_');
            const unit = group.querySelector('.metric-unit').value.trim();
            const min = parseFloat(group.querySelector('.metric-min').value);
            const max = parseFloat(group.querySelector('.metric-max').value);
            if (name && unit && !isNaN(min) && !isNaN(max)) {
                metrics.push({name, unit, min, max});
            }
        });

        if (metrics.length === 0) { return alert('At least one valid metric is required.'); }

        const result = await apiCall('/api/devices', 'POST', { device_id: deviceId, device_type: deviceType, metrics });
        if (result) { closeModal(modals.add); fetchData(); }
    });

    document.getElementById('device-grid').addEventListener('click', async (e) => {
        const deviceId = e.target.closest('button')?.dataset.deviceId;
        if (!deviceId) return;

        if (e.target.closest('.delete-btn')) {
            if (confirm(`Are you sure you want to delete device "${deviceId}"?`)) {
                await apiCall(`/api/devices/${deviceId}`, 'DELETE');
                fetchData();
            }
        } else if (e.target.closest('.config-btn')) {
            const device = await apiCall(`/api/devices/${deviceId}`);
            if (!device) return;
            currentConfigDeviceId = deviceId;
            const container = document.getElementById('alert-config-container');
            container.innerHTML = '';
            device.metrics.forEach(metric => {
                const alertConf = device.config.alerts[metric.name] || {};
                container.innerHTML += `
                    <div class="metric-alert-group grid grid-cols-3 gap-4 items-center">
                        <label class="font-bold capitalize">${metric.name.replace('_',' ')}</label>
                        <input type="number" placeholder="Min Alert" data-metric-name="${metric.name}" class="alert-min w-full bg-gray-800 p-2 rounded border border-gray-600" value="${alertConf.min || ''}">
                        <input type="number" placeholder="Max Alert" data-metric-name="${metric.name}" class="alert-max w-full bg-gray-800 p-2 rounded border border-gray-600" value="${alertConf.max || ''}">
                    </div>`;
            });
            document.getElementById('config-device-id').textContent = deviceId.toUpperCase();
            openModal(modals.config);
        }
    });
    
    document.getElementById('cancel-config-btn').addEventListener('click', () => closeModal(modals.config));
    document.getElementById('save-config-btn').addEventListener('click', async () => {
        const newConfig = { alerts: {} };
        document.querySelectorAll('.metric-alert-group').forEach(group => {
            const metricName = group.querySelector('.alert-min').dataset.metricName;
            const min = parseFloat(group.querySelector('.alert-min').value);
            const max = parseFloat(group.querySelector('.alert-max').value);
            const alertConf = {};
            if (!isNaN(min)) alertConf.min = min;
            if (!isNaN(max)) alertConf.max = max;
            if (Object.keys(alertConf).length > 0) newConfig.alerts[metricName] = alertConf;
        });
        
        await apiCall(`/api/devices/${currentConfigDeviceId}/config`, 'POST', newConfig);
        closeModal(modals.config);
        fetchData();
    });

    async function fetchData() {
        const devices = await apiCall('/api/devices');
        if (devices) {
            if (document.getElementById('device-grid').children.length !== devices.length) {
                initializeDashboard(devices);
            }
            updateUI(devices);
        }
    }
    
    document.addEventListener('DOMContentLoaded', () => {
        fetchData();
        setInterval(fetchData, 3000);
    });
</script>
</body>
</html>
"""

# --- Backend API Endpoints ---
def save_state():
    state = {}
    with DEVICE_LOCK:
        for device_id, device_obj in DEVICES.items():
            if isinstance(device_obj, DynamicSimulatedDevice):
                 state[device_id] = { "device_type": device_obj.device_type, "metrics": device_obj.metrics, "config": device_obj.config }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def load_state():
    if not os.path.exists(STATE_FILE): return
    with open(STATE_FILE, 'r') as f:
        try:
            state = json.load(f)
            for device_id, device_info in state.items():
                start_dynamic_device(device_id, device_info['device_type'], device_info['metrics'], device_info.get('config'))
        except json.JSONDecodeError: print("Could not load state file, it might be corrupted.")

@app.route('/')
def index(): return HTML_TEMPLATE

@app.route('/api/devices', methods=['GET'])
def get_all_devices():
    response_data = []
    with DEVICE_LOCK:
        for device_id, device in DEVICES.items():
            if device.data_history:
                response_data.append({
                    "device_id": device.device_id, "device_type": device.device_type,
                    "metrics": getattr(device, 'metrics', []), "config": getattr(device, 'config', {}),
                    "latest_data": device.get_latest_data(), "history": device.get_history_for_plot(),
                    "status": getattr(device, 'status', 'Unknown'), "alerts": getattr(device, 'alerts', {})
                })
    return flask.jsonify(sorted(response_data, key=lambda x: x['device_id']))

@app.route('/api/devices/<device_id>', methods=['GET'])
def get_device(device_id):
    with DEVICE_LOCK:
        device = DEVICES.get(device_id.lower())
        if device:
            return flask.jsonify({ "device_id": device.device_id, "device_type": device.device_type, "metrics": getattr(device, 'metrics', []), "config": getattr(device, 'config', {}), })
    return flask.jsonify({"error": "Device not found"}), 404

@app.route('/api/devices', methods=['POST'])
def add_device():
    data = flask.request.get_json()
    device_id = data.get('device_id').strip().lower()
    if not device_id or not data.get('metrics'): return flask.jsonify({"error": "Device ID and at least one metric are required"}), 400
    with DEVICE_LOCK:
        if device_id in DEVICES: return flask.jsonify({"error": "Device ID already exists"}), 409
        start_dynamic_device(device_id, data['device_type'], data['metrics'])
    save_state()
    return flask.jsonify({"message": "Device added successfully"}), 201

@app.route('/api/devices/<device_id>', methods=['DELETE'])
def delete_device(device_id):
    device_id = device_id.lower()
    if device_id == "pachora-weather": return flask.jsonify({"error": "The weather station is a permanent device and cannot be deleted."}), 403
    with DEVICE_LOCK:
        if device_id in DEVICES:
            DEVICES[device_id].stop()
            del DEVICES[device_id]
            save_state()
            return flask.jsonify({"message": "Device deleted"}), 200
    return flask.jsonify({"error": "Device not found"}), 404

@app.route('/api/devices/<device_id>/config', methods=['POST'])
def configure_device(device_id):
    device_id = device_id.lower()
    if device_id == "pachora-weather": return flask.jsonify({"error": "The weather station is not configurable."}), 403
    data = flask.request.get_json()
    with DEVICE_LOCK:
        if device_id in DEVICES:
            DEVICES[device_id].update_config(data)
            save_state()
            return flask.jsonify({"message": "Configuration updated"}), 200
    return flask.jsonify({"error": "Device not found"}), 404

# --- Main Application Logic ---
def start_dynamic_device(device_id, device_type, metrics, config=None):
    device = DynamicSimulatedDevice(device_id.lower(), device_type, metrics, config)
    device.start()
    DEVICES[device_id.lower()] = device

def start_weather_station(device_id, device_type):
    device = WeatherStationDevice(device_id.lower(), device_type)
    device.start()
    DEVICES[device_id.lower()] = device

if __name__ == '__main__':
    load_state()

    if "pachora-weather" not in DEVICES:
        start_weather_station("PACHORA-WEATHER", "Real-Time Weather Station")

    if not any(isinstance(d, DynamicSimulatedDevice) for d in DEVICES.values()):
        print("No saved dynamic devices found. Creating default set.")
        start_dynamic_device("SERVER-RACK-01", "Server Room Sensor", [
            {'name': 'temperature', 'unit': '°C', 'min': 20, 'max': 45},
            {'name': 'cpu_load', 'unit': '%', 'min': 10, 'max': 99}
        ])
        start_dynamic_device("GREENHOUSE-MAIN", "Environment Sensor", [
            {'name': 'humidity', 'unit': '%', 'min': 40, 'max': 90},
            {'name': 'soil_moisture', 'unit': '%', 'min': 10, 'max': 80}
        ])
        start_dynamic_device("KITCHEN-FRIDGE", "Smart Appliance", [
            {'name': 'temperature', 'unit': '°C', 'min': 1, 'max': 8},
            {'name': 'power_usage', 'unit': 'W', 'min': 20, 'max': 150}
        ])

    app.run(host='0.0.0.0', port=5000, debug=True)


