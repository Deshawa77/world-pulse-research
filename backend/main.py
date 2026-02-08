from fastapi import FastAPI
from pymongo import MongoClient
from processing.ai_summary import generate_summary
from processing.global_risk import compute_global_risk

app = FastAPI(title="World Pulse API")
db = MongoClient("mongodb://localhost:27017/")["world_pulse"]

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "World Pulse backend running"
    }

# News
@app.get("/news")
def get_news():
    return list(db.news.find({}, {"_id": 0}).limit(10))


# GDELT
@app.get("/gdelt")
def get_gdelt():
    return list(db.gdelt.find({}, {"_id": 0}).limit(10))


#  Wikipedia
@app.get("/wiki")
def get_wiki():
    return list(db.wiki.find({}, {"_id": 0}).limit(10))


#  Google Trends
@app.get("/trends")
def get_trends():
    return list(db.trends.find({}, {"_id": 0}).limit(10))


#  Earthquakes (USGS)
@app.get("/earthquakes")
def get_earthquakes():
    return list(db.earthquakes.find({}, {"_id": 0}).limit(10))


#  Weather
@app.get("/weather")
def get_weather():
    return list(db.weather.find({}, {"_id": 0}).limit(10))


#  Crypto
@app.get("/crypto")
def get_crypto():
    return list(db.crypto.find({}, {"_id": 0}).limit(10))


#  Economics (FRED + Frankfurter)
@app.get("/economics")
def get_economics():
    return list(db.economics.find({}, {"_id": 0}).limit(10))


#  Health (WHO)
@app.get("/health")
def get_health():
    return list(db.health.find({}, {"_id": 0}).limit(10))


#  Stocks (Twelve Data)
@app.get("/stocks")
def get_stocks():
    return list(db.stocks.find({}, {"_id": 0}).limit(10))


#  World Bank
@app.get("/worldbank")
def get_worldbank():
    return list(db.worldbank.find({}, {"_id": 0}).limit(10))

@app.get("/risk_score")
def risk_score():
    score = compute_global_risk()
    return {"risk_score": score}

@app.get("/summary")
def summary():
    summary_text = generate_summary()
    return {"summary": summary_text}