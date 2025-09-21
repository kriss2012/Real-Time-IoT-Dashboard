import flask
import json
import random
import time
from threading import Thread

# Create a Flask web server
app = flask.Flask(__name__)

# Dictionary to hold our simulated IoT devices
devices = {}

class SimulatedDevice(Thread):
    """A class to simulate a single IoT device generating data."""
    def __init__(self, device_id):
        super().__init__()
        self.device_id = device_id
        # Set initial stable values for temperature and humidity
        self.temperature = 22.5
        self.humidity = 45.0
        self.running = True
        self.daemon = True # Allows main thread to exit even if this thread is running

    def run(self):
        """This method runs in a separate thread and continuously updates device data."""
        while self.running:
            # Introduce slight, random fluctuations to the sensor data
            temp_change = (random.random() - 0.5) * 0.5
            self.temperature += temp_change
            # Ensure temperature stays within a realistic range
            self.temperature = max(18, min(32, self.temperature))

            humidity_change = (random.random() - 0.5) * 2
            self.humidity += humidity_change
            # Ensure humidity stays within a realistic range
            self.humidity = max(30, min(70, self.humidity))
            
            # Pause for a couple of seconds before the next reading
            time.sleep(2)

    def stop(self):
        """Stops the data simulation for this device."""
        self.running = False

    def get_data(self):
        """Returns the current sensor data for the device."""
        return {
            "device_id": self.device_id,
            "temperature": round(self.temperature, 2),
            "humidity": round(self.humidity, 2),
            "timestamp": time.time()
        }

@app.route('/devices', methods=['GET'])
def get_all_devices():
    """API endpoint to get data from all active devices."""
    all_data = {device_id: device.get_data() for device_id, device in devices.items()}
    return flask.jsonify(all_data)

@app.route('/devices/<device_id>', methods=['GET'])
def get_device_data(device_id):
    """API endpoint to get data from a specific device."""
    device = devices.get(device_id)
    if device:
        return flask.jsonify(device.get_data())
    return flask.jsonify({"error": "Device not found"}), 404

@app.route('/devices', methods=['POST'])
def add_device():
    """API endpoint to add a new simulated device."""
    # The device ID is expected in the JSON payload of the request
    if not flask.request.is_json:
        return flask.jsonify({"error": "Invalid request, expected JSON"}), 400
        
    data = flask.request.get_json()
    device_id = data.get('device_id')

    if not device_id:
        return flask.jsonify({"error": "Device ID is required"}), 400

    if device_id in devices:
        return flask.jsonify({"error": "Device already exists"}), 409

    # Create and start a new simulated device
    new_device = SimulatedDevice(device_id)
    new_device.start()
    devices[device_id] = new_device
    
    # Return a success message along with the new device's data
    return flask.jsonify(new_device.get_data()), 201

def run_server():
    """Runs the Flask server."""
    # By default, start with one simulated device
    initial_device = SimulatedDevice("living_room_sensor")
    initial_device.start()
    devices["living_room_sensor"] = initial_device
    # Start the Flask web server
    app.run(port=5000, debug=False)

if __name__ == '__main__':
    # Start the server in a separate thread to keep the main thread free
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    # Keep the main script alive to allow threads to run
    while True:
        time.sleep(1)
