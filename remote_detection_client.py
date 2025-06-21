import cv2
import socket
import pickle
import struct
import numpy as np
from ultralytics import YOLO
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import os
import shutil

class RemoteDetectionClient:
    def __init__(self, server_ip='localhost', server_port=8485):
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = False
        self.frame = None
        
        # Load YOLO model
        self.model = YOLO('yolov8n.pt')
        
        # Create dangerous_persons folder
        self.setup_folders()
        
        # Initialize UI
        self.setup_ui()
        
    def setup_folders(self):
        """Delete and recreate dangerous_persons folder"""
        if os.path.exists('dangerous_persons'):
            shutil.rmtree('dangerous_persons')
        os.makedirs('dangerous_persons', exist_ok=True)
        
    def setup_ui(self):
        self.root = tk.Tk()
        self.root.title("Remote Crowd Management System")
        self.root.geometry("1200x800")
        
        # Configure grid weights for responsive design
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        
        # Create main frame
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        
        # Header with logo
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Try to load and display logo
        try:
            logo_img = Image.open("logo.jpg")
            logo_img = logo_img.resize((100, 50), Image.Resampling.LANCZOS)
            logo_photo = ImageTk.PhotoImage(logo_img)
            logo_label = ttk.Label(header_frame, image=logo_photo)
            logo_label.image = logo_photo
            logo_label.pack(side="left", padx=(0, 10))
        except:
            pass
        
        title_label = ttk.Label(header_frame, text="Remote Crowd Management System", 
                               font=("Arial", 16, "bold"))
        title_label.pack(side="left")
        
        # Control panel
        control_frame = ttk.LabelFrame(main_frame, text="Controls", padding=10)
        control_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        
        # Connection controls
        ttk.Label(control_frame, text="Server IP:").grid(row=0, column=0, sticky="w", pady=2)
        self.ip_var = tk.StringVar(value=self.server_ip)
        ip_entry = ttk.Entry(control_frame, textvariable=self.ip_var, width=15)
        ip_entry.grid(row=1, column=0, sticky="ew", pady=2)
        
        ttk.Label(control_frame, text="Port:").grid(row=2, column=0, sticky="w", pady=2)
        self.port_var = tk.StringVar(value=str(self.server_port))
        port_entry = ttk.Entry(control_frame, textvariable=self.port_var, width=15)
        port_entry.grid(row=3, column=0, sticky="ew", pady=2)
        
        # Buttons
        self.connect_btn = ttk.Button(control_frame, text="Connect", command=self.connect_to_server)
        self.connect_btn.grid(row=4, column=0, sticky="ew", pady=10)
        
        self.disconnect_btn = ttk.Button(control_frame, text="Disconnect", command=self.disconnect_from_server, state="disabled")
        self.disconnect_btn.grid(row=5, column=0, sticky="ew", pady=5)
        
        # Status
        self.status_var = tk.StringVar(value="Disconnected")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, foreground="red")
        status_label.grid(row=6, column=0, sticky="w", pady=10)
        
        # Statistics
        stats_frame = ttk.LabelFrame(control_frame, text="Statistics", padding=5)
        stats_frame.grid(row=7, column=0, sticky="ew", pady=10)
        
        self.person_count_var = tk.StringVar(value="People: 0")
        ttk.Label(stats_frame, textvariable=self.person_count_var).grid(row=0, column=0, sticky="w")
        
        self.security_count_var = tk.StringVar(value="Security: 0")
        ttk.Label(stats_frame, textvariable=self.security_count_var).grid(row=1, column=0, sticky="w")
        
        self.danger_count_var = tk.StringVar(value="Dangerous: 0")
        ttk.Label(stats_frame, textvariable=self.danger_count_var).grid(row=2, column=0, sticky="w")
        
        # Video display
        video_frame = ttk.LabelFrame(main_frame, text="Remote Camera Feed", padding=10)
        video_frame.grid(row=1, column=1, sticky="nsew")
        video_frame.grid_rowconfigure(0, weight=1)
        video_frame.grid_columnconfigure(0, weight=1)
        
        self.video_label = ttk.Label(video_frame, text="Waiting for connection...")
        self.video_label.grid(row=0, column=0, sticky="nsew")
        
        # Configure control frame grid
        control_frame.grid_columnconfigure(0, weight=1)
        
    def connect_to_server(self):
        try:
            self.server_ip = self.ip_var.get()
            self.server_port = int(self.port_var.get())
            
            self.client_socket.connect((self.server_ip, self.server_port))
            self.running = True
            self.status_var.set("Connected")
            
            # Update button states
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            
            # Start receiving video
            self.receive_thread = threading.Thread(target=self.receive_video)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            
        except Exception as e:
            self.status_var.set(f"Connection failed: {str(e)}")
    
    def disconnect_from_server(self):
        self.running = False
        try:
            self.client_socket.close()
        except:
            pass
        
        self.status_var.set("Disconnected")
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.video_label.config(text="Disconnected")
    
    def receive_video(self):
        data = b""
        payload_size = struct.calcsize("L")
        
        while self.running:
            try:
                # Receive message size
                while len(data) < payload_size:
                    data += self.client_socket.recv(4096)
                
                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("L", packed_msg_size)[0]
                
                # Receive message data
                while len(data) < msg_size:
                    data += self.client_socket.recv(4096)
                
                frame_data = data[:msg_size]
                data = data[msg_size:]
                
                # Decode frame
                frame = pickle.loads(frame_data)
                frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)
                
                # Process frame with YOLO
                processed_frame = self.process_frame(frame)
                
                # Update UI
                self.update_video_display(processed_frame)
                
            except Exception as e:
                print(f"Error receiving video: {e}")
                break
        
        self.disconnect_from_server()
    
    def process_frame(self, frame):
        # Run YOLO detection
        results = self.model(frame, verbose=False)
        
        person_count = 0
        security_count = 0
        danger_count = 0
        
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    # Get box coordinates
                    x1, y1, x2, y2 = box.xyxy[0]
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    
                    # Get confidence and class
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    class_name = self.model.names[cls]
                    
                    if conf > 0.5:  # Confidence threshold
                        if class_name == 'person':
                            person_count += 1
                            
                            # Check for security staff (black clothing)
                            roi = frame[y1:y2, x1:x2]
                            if roi.size > 0:
                                # Convert to HSV and check for black clothing
                                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                                lower_black = np.array([0, 0, 0])
                                upper_black = np.array([180, 255, 30])
                                black_mask = cv2.inRange(hsv, lower_black, upper_black)
                                black_ratio = np.sum(black_mask > 0) / black_mask.size
                                
                                if black_ratio > 0.3:  # If more than 30% is black
                                    security_count += 1
                                    color = (0, 255, 0)  # Green for security
                                    label = f"Security Staff ({conf:.2f})"
                                else:
                                    color = (255, 0, 0)  # Red for regular person
                                    label = f"Person ({conf:.2f})"
                                
                                # Draw bounding box
                                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                                cv2.putText(frame, label, (x1, y1-10), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
                        elif class_name in ['knife', 'bottle', 'gun']:
                            danger_count += 1
                            color = (0, 0, 255)  # Red for dangerous objects
                            label = f"Dangerous: {class_name} ({conf:.2f})"
                            
                            # Draw bounding box
                            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                            cv2.putText(frame, label, (x1, y1-10), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                            
                            # Save dangerous person image
                            timestamp = time.strftime("%Y%m%d_%H%M%S_%f")[:-3]
                            filename = f"dangerous_persons/danger_{class_name}_{timestamp}_frame.jpg"
                            cv2.imwrite(filename, frame)
        
        # Update statistics
        self.person_count_var.set(f"People: {person_count}")
        self.security_count_var.set(f"Security: {security_count}")
        self.danger_count_var.set(f"Dangerous: {danger_count}")
        
        return frame
    
    def update_video_display(self, frame):
        # Resize frame to fit display
        height, width = frame.shape[:2]
        max_width = 800
        max_height = 600
        
        if width > max_width or height > max_height:
            scale = min(max_width/width, max_height/height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            frame = cv2.resize(frame, (new_width, new_height))
        
        # Convert to PIL Image
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        photo = ImageTk.PhotoImage(pil_image)
        
        # Update label
        self.video_label.config(image=photo, text="")
        self.video_label.image = photo
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    client = RemoteDetectionClient()
    client.run() 