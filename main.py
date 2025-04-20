from fastapi import FastAPI, Request, Response
import httpx
import uvicorn
import json
import base64
import os
import hashlib
import random
import string
from urllib.parse import unquote

app = FastAPI()
UPSTREAM_URL = "http://localhost:17864/sdapi/v1/txt2img"
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def parse_value(val):
    try:
        return json.loads(val)
    except Exception:
        return val

def hash_params(params):
    items = sorted(params.items())
    s = "&".join(f"{k}={json.dumps(v, sort_keys=True, ensure_ascii=False)}" for k, v in items)
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def get_payload_from_query(request, overescape=False):
    payload = {}
    for key, value in request.query_params.multi_items():
        fixed_value = unquote(value) if overescape else value
        payload[key] = parse_value(fixed_value)
    return payload

async def handle_txt2img(payload):
    cache_bypass = False

    if payload.get("force", None):
        cache_bypass = True
        payload.pop("force")
        payload["seed"] = random.randint(100000, 99999999)
    elif payload.get("seed", "") == "random":
        payload["seed"] = random.randint(100000, 99999999)
        cache_bypass = True

    hashkey = hash_params(payload)
    cache_path = os.path.join(CACHE_DIR, f"{hashkey}.png")

    if os.path.exists(cache_path) and not cache_bypass:
        with open(cache_path, "rb") as f:
            image_data = f.read()
        return Response(content=image_data, media_type="image/png")

    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(UPSTREAM_URL, json=payload)
        r.raise_for_status()
        data = r.json()
        if "images" not in data or not data["images"]:
            return Response(content="No image returned", status_code=500)
        image_data = base64.b64decode(data["images"][0].split(",",1)[-1])
        with open(cache_path, "wb") as f:
            f.write(image_data)
        return Response(content=image_data, media_type="image/png")

@app.get("/txt2img")
async def txt2img(request: Request):
    payload = get_payload_from_query(request, overescape=False)
    return await handle_txt2img(payload)

@app.get("/newtxt2img")
async def txt2img_overescape(request: Request):
    payload = get_payload_from_query(request, overescape=True)
    return await handle_txt2img(payload)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8123)
