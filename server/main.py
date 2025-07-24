from fastapi import FastAPI, Depends, Query, Request, HTTPException
import httpx
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_session, engine, Base
from models import WeatherRecord
from datetime import datetime
from fastapi.responses import JSONResponse
import asyncio
import asyncpg
import redis
import json
from motor.motor_asyncio import AsyncIOMotorClient
import os

print("TEST")

redis_client = redis.StrictRedis(host='redis', port=6379, db=0, decode_responses=True)

app = FastAPI()

mongo_client = AsyncIOMotorClient("mongodb://mongo:27017")
mongo_db = mongo_client["mydatabase"]
mongo_collection = mongo_db["user_actions"]

async def transfer_redis_to_mongo():
    while True:
        entries = redis_client.lrange("user_actions", 0, -1)
        if entries:
            documents = [json.loads(e) for e in entries]
            await mongo_collection.insert_many(documents)
            redis_client.delete("user_actions")
            print(f"Przeniesiono {len(documents)} wpisów z Redis do MongoDB")
        else:
            print("Brak nowych wpisów w Redis")
        await asyncio.sleep(30)

@app.middleware("http")
async def log_user_action(request: Request, call_next):
    method = request.method
    path = request.url.path
    query = dict(request.query_params)
    timestamp = datetime.utcnow().isoformat()

    action = {
        "method": method,
        "path": path,
        "query": query,
        "timestamp": timestamp
    }
    redis_client.rpush("user_actions", json.dumps(action))
    response = await call_next(request)
    return response

@app.get("/logs")
def get_logs():
    entries = redis_client.lrange("user_actions", 0, -1)
    return [json.loads(e) for e in entries]

CITIES = {
    "warszawa": (52.23, 21.01),
    "krakow": (50.06, 19.94),
    "gdansk": (54.35, 18.65),
    "wroclaw": (51.11, 17.03),
    "poznan": (52.41, 16.93),
    "szczecin": (53.43, 14.55),
    "bydgoszcz": (53.12, 18.01),
    "lublin": (51.25, 22.57),
    "bialystok": (53.13, 23.15),
    "katowice": (50.26, 19.02),
    "lodz": (51.77, 19.46),
    "torun": (53.01, 18.60),
    "kielce": (50.87, 20.63),
    "rzeszow": (50.04, 22.00),
    "opole": (50.67, 17.93),
    "zielona_gora": (51.94, 15.50),
    "gorzow_wlkp": (52.73, 15.24),
    "olsztyn": (53.78, 20.48),
    "radom": (51.40, 21.15),
    "plock": (52.55, 19.70),
    "elblag": (54.16, 19.40),
    "tarnow": (50.01, 20.99),
    "chorzow": (50.30, 18.95),
    "gliwice": (50.30, 18.67),
    "zabrze": (50.30, 18.78),
    "rybnik": (50.10, 18.55),
    "walbrzych": (50.77, 16.28),
    "legnica": (51.21, 16.16),
    "pila": (53.15, 16.74),
    "suwalki": (54.10, 22.93),
    "siedlce": (52.17, 22.29),
    "piotrkow_tryb": (51.40, 19.70),
    "nowy_sacz": (49.62, 20.69),
    "przemysl": (49.78, 22.77),
    "zamosc": (50.72, 23.25),
    "chelm": (51.14, 23.47),
    "koszalin": (54.19, 16.18),
    "slupsk": (54.46, 17.03),
    "grudziadz": (53.48, 18.75),
    "jaworzno": (50.20, 19.27),
    "tarnobrzeg": (50.58, 21.68),
    "ostrow_wlkp": (51.65, 17.81),
    "konin": (52.22, 18.26),
    "leszno": (51.84, 16.57),
    "stargard": (53.34, 15.05),
    "lubin": (51.40, 16.20),
    "mielec": (50.28, 21.42),
    "pabianice": (51.66, 19.35),
    "glogow": (51.66, 16.08),
    "ostroleka": (53.09, 21.56),
    "siemianowice_sl": (50.31, 19.03),
    "swidnica": (50.84, 16.49),
    "skierniewice": (51.97, 20.15),
    "bedzin": (50.33, 19.13),
    "pulawy": (51.42, 21.97),
    "starachowice": (51.05, 21.08),
    "nowy_targ": (49.48, 20.03),
    "radomsko": (51.07, 19.45),
    "wloclawek": (52.65, 19.07),
    "lubartow": (51.46, 22.61),
    "lomza": (53.18, 22.07),
    "klodzko": (50.43, 16.65),
    "biala_podlaska": (52.03, 23.13),
    "pruszkow": (52.17, 20.80),
    "jaslo": (49.75, 21.47),
    "dzierzoniow": (50.73, 16.65),
    "bielsk_podlaski": (52.77, 23.19),
}

@app.on_event("startup")
async def startup():
    asyncio.create_task(transfer_redis_to_mongo())
    for attempt in range(50):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("Połączono z bazą danych.")
            break
        except asyncpg.InvalidPasswordError:
            print("Nieprawidłowe hasło.")
        except Exception as e:
            print(f"Próba {attempt+1}/50 nieudana: {e}")
            await asyncio.sleep(2)

@app.get("/weather", response_class=JSONResponse)
async def get_weather(city: str = Query("warszawa"), session: AsyncSession = Depends(get_session)):
    coords = CITIES.get(city.lower())
    if not coords:
        raise HTTPException(status_code=404, detail="Miasto nieobsługiwane")

    url = f"http://api.open-meteo.com/v1/forecast?latitude={coords[0]}&longitude={coords[1]}&current_weather=true"

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia z API pogodowym: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e.response.status_code} - {e.response.text}")

    current = data.get("current_weather", {})

    record = WeatherRecord(
        city=city.capitalize(),
        temperature=current.get("temperature"),
        windspeed=current.get("windspeed"),
        time=datetime.fromisoformat(current.get("time")),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return JSONResponse(content={
        "city": record.city,
        "temperature": record.temperature,
        "windspeed": record.windspeed,
        "time": record.time.isoformat()
    })

@app.get("/history", response_class=JSONResponse)
async def get_history(city: str = Query("warszawa"), session: AsyncSession = Depends(get_session)):
    stmt = select(WeatherRecord).where(WeatherRecord.city.ilike(city)).order_by(WeatherRecord.time.desc()).limit(10)
    result = await session.execute(stmt)
    records = result.scalars().all()
    return JSONResponse(content=[
        {
            "city": r.city,
            "temperature": r.temperature,
            "windspeed": r.windspeed,
            "time": r.time.isoformat()
        }
        for r in records
    ])

@app.get("/view", response_class=JSONResponse)
async def view_history(city: str = "warszawa", session: AsyncSession = Depends(get_session)):
    stmt = select(WeatherRecord).where(WeatherRecord.city.ilike(city)).order_by(WeatherRecord.time.desc()).limit(10)
    result = await session.execute(stmt)
    records = result.scalars().all()
    return JSONResponse(content={
        "city": city.capitalize(),
        "records": [
            {
                "city": r.city,
                "temperature": r.temperature,
                "windspeed": r.windspeed,
                "time": r.time.isoformat()
            }
            for r in records
        ]
    })

@app.get("/ping", response_class=JSONResponse)
async def ping():
    return JSONResponse({"status": "ok"})

@app.get("/weather/geo", response_class=JSONResponse)
async def get_weather_by_coords(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    session: AsyncSession = Depends(get_session)
):
    url = (
        f"http://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}&current_weather=true"
    )

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e}")

    current = data.get("current_weather", {})
    record = WeatherRecord(
        city="Custom Location",
        temperature=current.get("temperature"),
        windspeed=current.get("windspeed"),
        time=datetime.fromisoformat(current.get("time")),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return JSONResponse(content={
        "city": record.city,
        "latitude": latitude,
        "longitude": longitude,
        "temperature": record.temperature,
        "windspeed": record.windspeed,
        "time": record.time.isoformat()
    })

@app.get("/forecast", response_class=JSONResponse)
async def get_forecast(
    city: str = Query("warszawa"),
    days: int = Query(3, ge=1, le=16)
):
    coords = CITIES.get(city.lower())
    if not coords:
        raise HTTPException(status_code=404, detail="Miasto nieobsługiwane")

    url = (
        f"http://api.open-meteo.com/v1/forecast?"
        f"latitude={coords[0]}&longitude={coords[1]}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe/Warsaw"
        f"&forecast_days={days}"
    )

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia z API pogodowym: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e.response.status_code} - {e.response.text}")

    daily = data.get("daily", {})

    return JSONResponse(content={
        "city": city.capitalize(),
        "forecast": daily,
    })

@app.get("/forecast/geo", response_class=JSONResponse)
async def get_forecast_geo(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    days: int = Query(3, ge=1, le=16)
):
    url = (
        f"http://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe/Warsaw"
        f"&forecast_days={days}"
    )

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia z API pogodowym: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e.response.status_code} - {e.response.text}")

    daily = data.get("daily", {})

    return JSONResponse(content={
        "latitude": latitude,
        "longitude": longitude,
        "forecast": daily
    })

@app.get("/forecast/hourly/geo", response_class=JSONResponse)
async def get_hourly_forecast_geo(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    hours: int = Query(12, ge=1, le=48)
):
    url = (
        f"http://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}"
        f"&hourly=temperature_2m,windspeed_10m,precipitation"
        f"&timezone=Europe/Warsaw"
    )

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia z API pogodowym: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e.response.status_code} - {e.response.text}")

    hourly_data = {}
    for key, values in data.get("hourly", {}).items():
        hourly_data[key] = values[:hours]

    return JSONResponse(content={
        "latitude": latitude,
        "longitude": longitude,
        "hourly_forecast": hourly_data
    })

@app.get("/forecast/hourly", response_class=JSONResponse)
async def get_hourly_forecast_city(
    city: str = Query(...),
    hours: int = Query(12, ge=1, le=48)
):
    coords = CITIES.get(city.lower())
    if not coords:
        raise HTTPException(status_code=404, detail="Miasto nieobsługiwane")
    latitude, longitude = coords

    url = (
        f"http://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}"
        f"&hourly=temperature_2m,windspeed_10m,precipitation"
        f"&timezone=Europe/Warsaw"
    )

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia z API pogodowym: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e.response.status_code} - {e.response.text}")

    hourly_data = {}
    for key, values in data.get("hourly", {}).items():
        hourly_data[key] = values[:hours]

    return JSONResponse(content={
        "city": city.capitalize(),
        "hourly_forecast": hourly_data
    })

@app.get("/history-range", response_class=JSONResponse)
async def get_weather_history_range(
    city: str = Query(..., description="Nazwa miasta, np. warszawa"),
    start_date: str = Query(..., description="Początkowa data w formacie YYYY-MM-DD"),
    end_date: str = Query(..., description="Końcowa data w formacie YYYY-MM-DD")
):
    coords = CITIES.get(city.lower())
    if not coords:
        raise HTTPException(status_code=404, detail="Miasto nieobsługiwane")

    latitude, longitude = coords

    url = (
        f"http://archive-api.open-meteo.com/v1/archive?"
        f"latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&start_date={start_date}&end_date={end_date}"
        f"&timezone=Europe/Warsaw"
    )

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia z API pogodowym: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e.response.status_code} - {e.response.text}")

    daily = data.get("daily", {})

    return JSONResponse(content={
        "city": city.capitalize(),
        "start_date": start_date,
        "end_date": end_date,
        "history": daily
    })

@app.get("/history-range/geo", response_class=JSONResponse)
async def get_weather_history_range_geo(
    latitude: float = Query(..., ge=-90, le=90, description="Szerokość geograficzna"),
    longitude: float = Query(..., ge=-180, le=180, description="Długość geograficzna"),
    start_date: str = Query(..., description="Początkowa data w formacie YYYY-MM-DD"),
    end_date: str = Query(..., description="Końcowa data w formacie YYYY-MM-DD")
):
    url = (
        f"http://archive-api.open-meteo.com/v1/archive?"
        f"latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&start_date={start_date}&end_date={end_date}"
        f"&timezone=Europe/Warsaw"
    )

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            res.raise_for_status()
            data = res.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Błąd połączenia z API pogodowym: {e}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Błąd API pogodowego: {e.response.status_code} - {e.response.text}")

    daily = data.get("daily", {})

    return JSONResponse(content={
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "history": daily
    })
