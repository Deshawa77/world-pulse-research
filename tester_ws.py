# tester_ws_client.py
import websocket
import json
import time

API_KEY = "super_secure_api_key"
URL = "ws://localhost:8080/ws/risk"

def on_message(ws, message):
    print("Received:", message)

def on_error(ws, error):
    print("Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("Closed")

def on_open(ws):
    print("Connected to WebSocket!")

if __name__ == "__main__":
    headers = [f"x-api-key: {API_KEY}"]
    ws = websocket.WebSocketApp(
        URL,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()
