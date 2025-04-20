from fastapi import FastAPI, Request, Response
import httpx
import uvicorn
import json
import base64
import os
import hashlib
import random
import string

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
    # 把所有参数按key排序， kv对组成字符串后 sha256
    items = sorted(params.items())
    s = "&".join(f"{k}={json.dumps(v, sort_keys=True, ensure_ascii=False)}" for k, v in items)
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def random_string(n=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

@app.get("/txt2img")
async def txt2img(request: Request):
    # 把query全部转payload
    payload = {}
    for key, value in request.query_params.multi_items():
        payload[key] = parse_value(value)
    cache_bypass = False

    # 支持强制刷新, 比如?force=1，或者?seed=random
    if payload.get("force", None):
        cache_bypass = True
        payload.pop("force")  # 移除force, 不下发给后端
        # 塞一个特殊seed防止同样prompt重复
        payload["seed"] = random.randint(100000, 99999999)
    elif payload.get("seed", "") == "random":
        payload["seed"] = random.randint(100000, 99999999)
        cache_bypass = True   # seed变化，一定不会命中

    # 用处理后的payload算hash
    hashkey = hash_params(payload)
    cache_path = os.path.join(CACHE_DIR, f"{hashkey}.png")
    if os.path.exists(cache_path) and not cache_bypass:
        with open(cache_path, "rb") as f:
            image_data = f.read()
        return Response(content=image_data, media_type="image/png")

    # 不存在或要刷新才继续生成
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8123)
