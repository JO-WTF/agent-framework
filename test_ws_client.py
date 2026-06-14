import asyncio
import httpx
import websockets
import json

async def main():
    session_id = "test_ws_session_1"
    
    # 1. Start chat
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"http://127.0.0.1:8000/api/chat?session_id={session_id}",
            json={"message": "hello, say hi and count to 5 slowly", "model_config": {}}
        )
        print("POST /api/chat:", res.json())
        
    # 2. Connect to WS
    uri = f"ws://127.0.0.1:8000/ws?session_id={session_id}"
    async with websockets.connect(uri) as ws:
        while True:
            try:
                msg = await ws.recv()
                payload = json.loads(msg)
                
                if "event" in payload:
                    print(f"EVENT: {payload['event'].get('type')} - {payload['event'].get('title')}")
                elif "type" in payload and payload["type"] == "stream":
                    print(f"STREAM: {payload.get('token_type')} => {repr(payload.get('content'))}")
                else:
                    print("OTHER:", list(payload.keys()))
                    
                if payload.get("event", {}).get("type") == "run_complete":
                    print("Finished!")
                    break
            except Exception as e:
                print("Error:", e)
                break

if __name__ == "__main__":
    asyncio.run(main())
