import threading
import webview
import uvicorn
import sys
import os
from main import app

# Set the working directory to the EXE location for database
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

def run_server():
    """Run the FastAPI server"""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == "__main__":
    print(f"Working directory: {os.getcwd()}")
    
    # Start server in background
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Create desktop window with your logo
    webview.create_window(
        title="HardStock - Hardware Shop System",
        url="http://127.0.0.1:8000",
        width=1280,
        height=720,
        min_size=(1024, 600),
        resizable=True,
        fullscreen=False
    )
    webview.start()