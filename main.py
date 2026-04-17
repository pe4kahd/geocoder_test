import asyncio
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
load_dotenv()
API_KEYS = {
    "pelias": os.getenv('PELIAS_KEY'),
    "yandex": os.getenv('YANDEX_KEY')
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9"
}


async def get_coords(client, url, params, source):
    try:
        if source == "photon":
            if "q" in params:
                clean_q = params["q"].replace(",", " ")
                params["q"] = " ".join(clean_q.split())

            params["lang"] = "default"

        resp = await client.get(url, params=params, headers=HEADERS, timeout=5.0)

        if resp.status_code != 200:
            print(f"DEBUG: {source} returned {resp.status_code}. Body: {resp.text}")
            return None

        data = resp.json()

        if source == "nominatim" and isinstance(data, list) and len(data) > 0:
            return {
                "name": "Nominatim",
                "coords": [float(data[0]['lat']), float(data[0]['lon'])],
                "color": "blue"
            }

        if source in ["photon", "pelias"] and data.get('features'):
            if len(data['features']) > 0:
                c = data['features'][0]['geometry']['coordinates']
                return {
                    "name": source.capitalize(),
                    "coords": [c[1], c[0]],
                    "color": "green" if source == "photon" else "red"
                }

        if source == "yandex":
            fm = data['response']['GeoObjectCollection']['featureMember']
            if fm:
                pos = fm[0]['GeoObject']['Point']['pos']
                lon, lat = pos.split(" ")
                return {"name": "Yandex", "coords": [float(lat), float(lon)], "color": "#f1c40f"}

    except Exception as e:
        print(f"ERROR: {source} failed: {e}")
    return None


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Главная страница с картой"""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Geocode Compare Lab"}
    )


@app.get("/search")
async def search(address: str):
    """API эндпоинт для поиска по всем сервисам сразу"""
    if not address or len(address.strip()) < 2:
        return []

    async with httpx.AsyncClient() as client:
        tasks = [
            get_coords(client, "https://nominatim.openstreetmap.org/search",
                       {"q": address, "format": "json", "limit": 1}, "nominatim"),
            get_coords(client, "https://photon.komoot.io/api/",
                       {"q": address, "limit": 1}, "photon"),
            get_coords(client, "https://api.geocode.earth/v1/search",
                       {"api_key": API_KEYS["pelias"], "text": address, "size": 1}, "pelias"),
            get_coords(client, "https://geocode-maps.yandex.ru/1.x/",
                       {"apikey": API_KEYS["yandex"], "geocode": address, "format": "json", "results": 1}, "yandex")
        ]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)