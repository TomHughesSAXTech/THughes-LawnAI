#!/usr/bin/env python3
"""
Hughes Lawn AI Control Panel
Simple GUI with start/stop buttons
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import os

class LawnAIControlPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Hughes Lawn AI Control Panel")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Set the working directory to the script's location
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Status variables
        self.is_running = tk.BooleanVar()
        self.status_text = tk.StringVar(value="System Status: Stopped")
        
        self.setup_ui()
        self.check_status()
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="Hughes Lawn AI Control Panel", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Status indicator
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=1, column=0, columnspan=2, pady=(0, 20))
        
        self.status_label = ttk.Label(status_frame, textvariable=self.status_text, 
                                     font=("Arial", 12))
        self.status_label.grid(row=0, column=0)
        
        self.status_indicator = tk.Canvas(status_frame, width=20, height=20)
        self.status_indicator.grid(row=0, column=1, padx=(10, 0))
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        self.start_button = ttk.Button(button_frame, text="🚀 Start System", 
                                      command=self.start_system, 
                                      style="Success.TButton",
                                      width=15)
        self.start_button.grid(row=0, column=0, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="🛑 Stop System", 
                                     command=self.stop_system,
                                     style="Danger.TButton", 
                                     width=15)
        self.stop_button.grid(row=0, column=1, padx=(10, 0))
        
        # Log area
        log_frame = ttk.LabelFrame(main_frame, text="Recent Activity", padding="10")
        log_frame.grid(row=3, column=0, columnspan=2, pady=(20, 0), sticky=(tk.W, tk.E))
        
        self.log_text = tk.Text(log_frame, height=8, width=50, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Refresh button
        refresh_button = ttk.Button(main_frame, text="🔄 Refresh Status", 
                                   command=self.check_status)
        refresh_button.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        
        # Configure styles
        style = ttk.Style()
        style.configure("Success.TButton", foreground="green")
        style.configure("Danger.TButton", foreground="red")
    
    def log_message(self, message):
        """Add a message to the log area"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update()
    
    def update_status_indicator(self, running):
        """Update the status indicator circle"""
        self.status_indicator.delete("all")
        color = "green" if running else "red"
        self.status_indicator.create_oval(2, 2, 18, 18, fill=color, outline=color)
    
    def check_status(self):
        """Check if the system is currently running"""
        try:
            # Check if the main Python process is running
            result = subprocess.run(
                ["pgrep", "-f", "hughes_lawn_ai.py"], 
                capture_output=True, 
                text=True, 
                cwd=self.script_dir
            )
            
            running = bool(result.stdout.strip())
            self.is_running.set(running)
            
            status = "Running" if running else "Stopped"
            self.status_text.set(f"System Status: {status}")
            self.update_status_indicator(running)
            
            # Update button states
            self.start_button.config(state=tk.DISABLED if running else tk.NORMAL)
            self.stop_button.config(state=tk.NORMAL if running else tk.DISABLED)
            
        except Exception as e:
            self.log_message(f"Error checking status: {e}")
    
    def start_system(self):
        """Start the Hughes Lawn AI system"""
        def run_start():
            try:
                self.log_message("Starting Hughes Lawn AI system...")
                self.start_button.config(state=tk.DISABLED)
                
                # Run the start script
                start_script = os.path.join(self.script_dir, "start_system.sh")
                if os.path.exists(start_script):
                    result = subprocess.run(
                        ["bash", start_script], 
                        capture_output=True, 
                        text=True, 
                        cwd=self.script_dir
                    )
                    
                    if result.returncode == 0:
                        self.log_message("✅ System started successfully!")
                    else:
                        self.log_message(f"❌ Error starting system: {result.stderr}")
                else:
                    # Fallback: try to start the Python script directly
                    subprocess.Popen(
                        ["python3", "hughes_lawn_ai.py"], 
                        cwd=self.script_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self.log_message("✅ System started successfully!")
                
                # Wait a moment then check status
                self.root.after(2000, self.check_status)
                
            except Exception as e:
                self.log_message(f"❌ Error starting system: {e}")
                self.start_button.config(state=tk.NORMAL)
        
        # Run in a separate thread to avoid blocking the UI
        threading.Thread(target=run_start, daemon=True).start()
    
    def stop_system(self):
        """Stop the Hughes Lawn AI system"""
        def run_stop():
            try:
                self.log_message("Stopping Hughes Lawn AI system...")
                self.stop_button.config(state=tk.DISABLED)
                
                # Run the stop script
                stop_script = os.path.join(self.script_dir, "stop_system.sh")
                if os.path.exists(stop_script):
                    result = subprocess.run(
                        ["bash", stop_script], 
                        capture_output=True, 
                        text=True, 
                        cwd=self.script_dir
                    )
                    
                    if result.returncode == 0:
                        self.log_message("✅ System stopped successfully!")
                    else:
                        self.log_message(f"❌ Error stopping system: {result.stderr}")
                else:
                    # Fallback: try to kill the Python process
                    subprocess.run(["pkill", "-f", "hughes_lawn_ai.py"])
                    self.log_message("✅ System stopped successfully!")
                
                # Wait a moment then check status
                self.root.after(2000, self.check_status)
                
            except Exception as e:
                self.log_message(f"❌ Error stopping system: {e}")
                self.stop_button.config(state=tk.NORMAL)
        
        # Run in a separate thread to avoid blocking the UI
        threading.Thread(target=run_stop, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = LawnAIControlPanel(root)
    root.mainloop()
