import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from django.http import JsonResponse
from django.shortcuts import render

def index(request):
    return render(request, 'finance/index.html')

def predict_price(request):
    symbol = request.GET.get("symbol", "AAPL").strip().upper()

    try:
        # Veriyi indir
        df = yf.download(symbol, start='2000-01-01')

        if df.empty:
            return JsonResponse({"error": "Geçersiz sembol veya veri indirilemedi."}, status=400)

        # Kapanış fiyatını kullan
        df = df[['Close']].dropna().rename(columns={'Close': 'Price'})
        
        # 1 gün gecikmeli özellik
        df['Prev'] = df['Price'].shift(1)
        df = df.dropna()

        # Model için veri
        X = df[['Prev']]
        y = df['Price']

        # Modeli eğit
        model = LinearRegression()
        model.fit(X, y)

        # Tahmin (yarın için)
        last_value_scalar = df.iloc[-1]['Price'].item()  # Son fiyatın skalar değerini al
        predicted_next = model.predict(np.array([[last_value_scalar]])).item()

        # R² ve Adjusted R² hesapla
        r2 = model.score(X, y)
        n = len(y)
        k = X.shape[1]
        adjusted_r2 = 1 - (1 - r2) * ((n - 1) / (n - k - 1))

        return JsonResponse({
            "symbol": symbol,
            "last_price": round(last_value_scalar, 4),
            "predicted_next_day": round(predicted_next, 4),
            "r2": round(r2, 6),
            "adjusted_r2": round(adjusted_r2, 6),
        })

    except Exception as e:
        return JsonResponse({"error": f"Bir hata oluştu: {str(e)}"}, status=500)
