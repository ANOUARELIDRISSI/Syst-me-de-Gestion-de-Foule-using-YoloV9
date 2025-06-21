import cv2
import socket
import pickle
import struct
import threading
import time

class VideoStreamServer:
    def __init__(self, host='0.0.0.0', port=8485):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.clients = []
        self.running = False
        
    def start(self):
        self.running = True
        print(f"Video stream server started on {self.host}:{self.port}")
        print("Waiting for client connections...")
        
        # Start accepting clients in a separate thread
        accept_thread = threading.Thread(target=self.accept_clients)
        accept_thread.daemon = True
        accept_thread.start()
        
        # Start video streaming
        self.stream_video()
    
    def accept_clients(self):
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"Client connected from {addr}")
                self.clients.append(client_socket)
            except:
                break
    
    def stream_video(self):
        cap = cv2.VideoCapture(0)  # Use default camera (0)
        
        if not cap.isOpened():
            print("Error: Could not open camera")
            return
        
        print("Camera opened successfully")
        
        while self.running:
            ret, frame = cap.read()
            if not ret:
                print("Error: Could not read frame")
                break
            
            # Encode frame
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            message = pickle.dumps(buffer)
            
            # Send to all connected clients
            clients_to_remove = []
            for client in self.clients:
                try:
                    # Send message size first
                    message_size = struct.pack("L", len(message))
                    client.send(message_size + message)
                except:
                    clients_to_remove.append(client)
            
            # Remove disconnected clients
            for client in clients_to_remove:
                self.clients.remove(client)
                client.close()
                print("Client disconnected")
            
            # Show local preview (optional)
            cv2.imshow('Camera Server', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        self.stop()
    
    def stop(self):
        self.running = False
        for client in self.clients:
            client.close()
        self.server_socket.close()
        print("Server stopped")

if __name__ == "__main__":
    server = VideoStreamServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop() 