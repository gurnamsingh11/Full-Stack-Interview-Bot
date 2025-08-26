import asyncio
import base64
import json
import traceback
from voice_assistant.config import MODEL, GEMINI_API_KEY, prompt
import websockets
import pyaudio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# ==== FastAPI app ====
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== Gemini Live ====
HOST = "generativelanguage.googleapis.com"
URI = (
    f"wss://{HOST}/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    f"?key={GEMINI_API_KEY}"
)

# ==== Audio constants ====
FORMAT = pyaudio.paInt16
RECEIVE_SAMPLE_RATE = 24000
SEND_SAMPLE_RATE = 16000
CHUNK_SIZE = 512
CHANNELS = 1


@app.websocket("/interview")
async def interview_endpoint(ws: WebSocket):
    await ws.accept()
    print("UI connected")
    gem_ws = None

    try:
        # 1. Get JD and CR
        init_msg = await ws.receive_json()
        jd = init_msg.get("jd", "")
        cr = init_msg.get("cr", "")

        # 2. Connect to Gemini Live
        gem_ws = await websockets.connect(URI)

        setup_msg = {
            "setup": {
                "model": f"models/{MODEL}",
                "system_instruction": {"parts": [{"text": prompt(jd, cr)}]},
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {"voice_name": "Puck"}
                        }
                    },
                },
            }
        }
        await gem_ws.send(json.dumps(setup_msg))

        # Start Gemini interview
        start_msg = {
            "client_content": {
                "turns": [
                    {"role": "user", "parts": [{"text": "Please begin the interview."}]}
                ],
                "turn_complete": True,
            }
        }
        await gem_ws.send(json.dumps(start_msg))

        # ==== Relay UI -> Gemini ====
        async def forward_ui_audio():
            try:
                while True:
                    msg = await ws.receive_json()
                    if "audio" in msg:
                        chunk = msg["audio"]
                        gem_msg = {
                            "realtime_input": {
                                "media_chunks": [{"data": chunk, "mime_type": "audio/pcm"}]
                            }
                        }
                        await gem_ws.send(json.dumps(gem_msg))
                    elif "control" in msg and msg["control"] == "interrupt":
                        # Optionally handle interrupt
                        await gem_ws.send(json.dumps({"client_content": {"interrupt": True}}))
            except WebSocketDisconnect:
                print("UI disconnected")
            except Exception as e:
                print(f"Error forward_ui_audio: {e}")
            finally:
                if gem_ws:
                    await gem_ws.close()

        # ==== Relay Gemini -> UI ====
        async def relay_gemini():
            try:
                async for raw in gem_ws:
                    resp = json.loads(raw)
                    sc = resp.get("serverContent", {})

                    if "modelTurn" in sc:
                        for part in sc["modelTurn"].get("parts", []):
                            if "inlineData" in part:
                                b64data = part["inlineData"]["data"]
                                await ws.send_json({"type": "audio", "data": b64data})
                            if "text" in part:
                                await ws.send_json(
                                    {"type": "transcript", "role": "model", "text": part["text"]}
                                )

                    if "inputTranscription" in sc:
                        await ws.send_json(
                            {"type": "transcript", "role": "user", "text": sc["inputTranscription"]["text"]}
                        )
            except Exception as e:
                print(f"Error relay_gemini: {e}")
            finally:
                try:
                    await ws.close()
                except:
                    pass
                if gem_ws and not gem_ws.closed:
                    await gem_ws.close()
                print("Relay Gemini task closed")

        # ==== Run both tasks ====
        async with asyncio.TaskGroup() as tg:
            tg.create_task(forward_ui_audio())
            tg.create_task(relay_gemini())

    except Exception as e:
        print(f"Error in interview endpoint: {e}")
        traceback.print_exc()
    finally:
        if gem_ws and not gem_ws.closed:
            await gem_ws.close()
        print("Interview session closed")
