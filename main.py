from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
import os

app = FastAPI()

# Вставляем данные из Шага 1 (на сервере их лучше скрыть в переменные окружения)
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "https://supabase.co"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/stations")
async def get_stations():
    # Получаем все заправки из таблицы Supabase
    response = supabase.table("stations").select("*").execute()
    return response.data

@app.post("/api/add_update")
async def add_update(
    user_id: str = Form(...),
    lat: float = Form(...),
    lng: float = Form(...),
    name: str = Form(...),
    fuel_type: str = Form(...),
    price: float = Form(...),
    queue: str = Form(...),
    canister: str = Form(...),
    photo: UploadFile = File(...)
):
    if not photo.filename:
        raise HTTPException(status_code=400, detail="Фото обязательно")
    
    # 1. Загружаем фото в облачное хранилище Supabase
    file_bytes = await photo.read()
    file_path = f"updates/{user_id}_{photo.filename}"
    
    try:
        supabase.storage.from_("fuel-photos").upload(file_path, file_bytes)
        # Получаем публичную ссылку на фото
        photo_url = supabase.storage.from_("fuel-photos").get_public_url(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")

    # 2. Проверяем, есть ли заправка по координатам
    station_res = supabase.table("stations").select("*").eq("lat", lat).eq("lng", lng).execute()
    
    # Структура обновления
    update_data = {
        "user_id": user_id,
        "fuel_type": fuel_type,
        "price": price,
        "queue": queue,
        "canister": canister,
        "photo_url": photo_url,
        "likes": 0,
        "dislikes": 0
    }

    if station_res.data:
        # Если заправка есть, добавляем обновление в список (в БД это поле типа JSONB)
        station = station_res.data[0]
        current_updates = station.get("updates", [])
        current_updates.insert(0, update_data)
        supabase.table("stations").update({"updates": current_updates}).eq("id", station["id"]).execute()
    else:
        # Если заправки нет, создаем новую запись
        new_station = {
            "name": name,
            "lat": lat,
            "lng": lng,
            "updates": [update_data]
        }
        supabase.table("stations").insert(new_station).execute()

    # 3. Увеличиваем счетчик активности пользователя
    user_res = supabase.table("user_activity").select("*").eq("user_id", user_id).execute()
    count = 1
    if user_res.data:
        count = user_res.data[0]["count"] + 1
        supabase.table("user_activity").update({"count": count}).eq("user_id", user_id).execute()
    else:
        supabase.table("user_activity").insert({"user_id": user_id, "count": 1}).execute()
    
    return {"status": "success", "updates_count": count}

# В Supabase таблицы создаются через их панель управления. В ней нужно создать:
# 1. Таблицу "stations" (id, name, lat, lng, updates)
# 2. Таблицу "user_activity" (user_id, count)
