from database.mongo import db
from statsmodels.tsa.arima.model import ARIMA


def forecast_sentiment():
    collection = db["alerts"]

    history = []

    for doc in collection.find().sort("date", 1):
        history.append(doc.get("current_sentiment", 0))

    if len(history) < 5:
        print("Not enough data for forecasting.")
        return

    model = ARIMA(history, order=(1, 1, 1))
    model_fit = model.fit()

    forecast = model_fit.forecast(steps=1)
    predicted = forecast[0]

    print(f"Predicted sentiment for tomorrow: {predicted:.3f}")

    if predicted < -0.3:
        print("⚠️ Predicted future crisis risk!")

    return predicted
