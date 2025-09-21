import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import requests
import threading
import time

# The base URL for the IoT server API
API_BASE_URL = "http://127.0.0.1:5000"

class IoTMonitorApp:
    """The main class for the IoT Monitoring Application GUI."""
    def __init__(self, root):
        self.root = root
        self.root.title("IoT Monitoring Dashboard")
        self.root.geometry("900x600")
        
        # Style the application for a modern look
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background="#2c3e50")
        self.style.configure("TLabel", background="#2c3e50", foreground="#ecf0f1", font=("Arial", 12))
        self.style.configure("Header.TLabel", font=("Arial", 18, "bold"))
        self.style.configure("Device.TFrame", background="#34495e", borderwidth=1, relief="solid")
        
        self.devices = {}
        self.running = True
        
        # Set up the main layout of the application
        self.setup_ui()

        # Try to connect to the server right away
        if not self.fetch_initial_data():
            # If the first connection fails, don't start the polling thread
            return
        
        # Start a background thread to fetch data periodically ONLY if initial connection was successful
        self.poll_thread = threading.Thread(target=self.poll_for_data, daemon=True)
        self.poll_thread.start()
        
        # Ensure the polling stops when the window is closed
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        """Creates and arranges the widgets in the main window."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(expand=True, fill="both")

        header_label = ttk.Label(main_frame, text="IoT Device Monitor", style="Header.TLabel")
        header_label.pack(pady=10)
        
        # Add a button for adding new devices
        add_device_button = ttk.Button(main_frame, text="Add IoT Device", command=self.add_device_prompt)
        add_device_button.pack(pady=10)

        # This frame will hold the display for each device
        self.devices_frame = ttk.Frame(main_frame)
        self.devices_frame.pack(expand=True, fill="both", pady=10)

    def add_device_prompt(self):
        """Shows a dialog to get the new device's ID from the user."""
        device_id = simpledialog.askstring("Add Device", "Enter a unique ID for the new device:")
        if device_id:
            self.create_new_device(device_id)

    def create_new_device(self, device_id):
        """Sends a request to the server to create a new device."""
        try:
            response = requests.post(f"{API_BASE_URL}/devices", json={"device_id": device_id})
            if response.status_code == 201:
                messagebox.showinfo("Success", f"Device '{device_id}' added successfully.")
                self.fetch_and_update() # Refresh data to show the new device
            else:
                # Show an error message if the device couldn't be added
                error_message = response.json().get('error', 'Unknown error')
                messagebox.showerror("Error", f"Failed to add device: {error_message}")
        except requests.exceptions.ConnectionError:
            messagebox.showerror("Connection Error", "Could not connect to the IoT server.\nPlease ensure 'iot_server.py' is running.")

    def fetch_initial_data(self):
        """Fetches data for all devices when the app starts. Returns True on success, False on failure."""
        try:
            response = requests.get(f"{API_BASE_URL}/devices", timeout=3) # Add a timeout
            if response.status_code == 200:
                self.devices = response.json()
                self.update_ui()
                return True
        except requests.exceptions.ConnectionError:
            messagebox.showerror("Connection Error", "Could not connect to the IoT server.\nPlease ensure 'iot_server.py' is running and not blocked by a firewall.")
            return False
        return False
    
    def fetch_and_update(self):
        """Fetches data for all devices and updates the UI without showing an error on failure."""
        try:
            response = requests.get(f"{API_BASE_URL}/devices", timeout=3)
            if response.status_code == 200:
                self.devices = response.json()
                self.update_ui()
        except requests.exceptions.ConnectionError:
            # Silently fail here as the initial error has already been shown
            pass

    def poll_for_data(self):
        """Continuously fetches data from the server in a loop."""
        while self.running:
            self.fetch_and_update()
            time.sleep(2) # Poll every 2 seconds

    def update_ui(self):
        """Refreshes the device displays with the latest data."""
        # Clear the existing device frames
        for widget in self.devices_frame.winfo_children():
            widget.destroy()

        # Create a frame for each device with its data
        for device_id, data in self.devices.items():
            device_frame = ttk.Frame(self.devices_frame, padding="10", style="Device.TFrame")
            
            # Display device information
            id_label = ttk.Label(device_frame, text=f"Device: {device_id}", font=("Arial", 14, "bold"))
            id_label.pack(anchor="w")
            
            temp_label = ttk.Label(device_frame, text=f"  Temperature: {data['temperature']}°C")
            temp_label.pack(anchor="w", pady=2)
            
            humidity_label = ttk.Label(device_frame, text=f"  Humidity: {data['humidity']}%")
            humidity_label.pack(anchor="w", pady=2)

            device_frame.pack(pady=5, padx=10, fill="x")

    def on_closing(self):
        """Handles the application window being closed."""
        self.running = False # Stop the polling thread
        self.root.destroy()

if __name__ == "__main__":
    # To run this application:
    # 1. First, run the 'iot_server.py' script in a terminal.
    # 2. Then, run this 'iot_monitor_app.py' script in another terminal.
    
    root = tk.Tk()
    app = IoTMonitorApp(root)
    root.mainloop()

