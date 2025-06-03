import yfinance as yf
import pandas as pd
import numpy as np
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.views.decorators.http import require_POST
from .forms import UserRegistrationForm, UserLoginForm, StockHoldingForm, WatchlistForm
from .models import Portfolio, StockHolding, Watchlist, AnalysisHistory
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
import json
from django.views.decorators.csrf import csrf_exempt

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices, fast=12, slow=26, signal=9):
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, lower_band

def get_market_data():
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA']
    market_data = []
    
    for symbol in symbols:
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            market_data.append({
                'symbol': symbol,
                'company_name': info.get('longName', symbol),
                'price': round(info.get('currentPrice', 0), 2),
                'change': round(info.get('regularMarketChangePercent', 0), 2),
                'volume': info.get('regularMarketVolume', 0),
                'market_cap': info.get('marketCap', 0)
            })
        except:
            continue
    
    return market_data

def index_view(request):
    # Örnek piyasa verileri
    market_data = [
        {'symbol': 'AAPL', 'company_name': 'Apple Inc.', 'price': 175.50, 'change': 1.2, 'volume': '45.2M', 'market_cap': '2.8T'},
        {'symbol': 'MSFT', 'company_name': 'Microsoft Corp.', 'price': 380.25, 'change': 0.8, 'volume': '22.1M', 'market_cap': '2.8T'},
        {'symbol': 'GOOGL', 'company_name': 'Alphabet Inc.', 'price': 140.75, 'change': -0.5, 'volume': '18.5M', 'market_cap': '1.8T'},
        {'symbol': 'AMZN', 'company_name': 'Amazon.com Inc.', 'price': 175.25, 'change': 1.5, 'volume': '35.8M', 'market_cap': '1.8T'},
        {'symbol': 'META', 'company_name': 'Meta Platforms Inc.', 'price': 380.50, 'change': 2.1, 'volume': '28.3M', 'market_cap': '950B'},
    ]
    return render(request, 'finance/index.html', {'market_data': market_data})

def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Portfolio.objects.create(user=user)
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserRegistrationForm()
    return render(request, 'finance/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Geçersiz kullanıcı adı veya şifre.')
    else:
        form = UserLoginForm()
    return render(request, 'finance/login.html', {'form': form})

@login_required
def logout_view(request):
    logout(request)
    return redirect('index')

@login_required
def dashboard_view(request):
    portfolio = request.user.portfolio
    holdings = portfolio.holdings.all()
    
    # Portföy dağılımı için veri hazırlama
    distribution = {
        'labels': [holding.symbol for holding in holdings],
        'data': [float(holding.shares * holding.average_cost) for holding in holdings]
    }
    
    # Performans verisi için örnek veri
    performance = {
        'labels': [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30, 0, -1)],
        'data': [1000 + i * 10 for i in range(30)]
    }
    
    context = {
        'portfolio': {
            'total_value': sum(float(h.shares * h.average_cost) for h in holdings),
            'stock_count': holdings.count(),
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'holdings': holdings,
            'distribution': distribution,
            'performance': performance
        }
    }
    return render(request, 'finance/dashboard.html', context)

def create_portfolio_chart(holdings):
    labels = [holding.symbol for holding in holdings]
    values = [holding.current_value for holding in holdings]
    
    fig = px.pie(values=values, names=labels, title='Portföy Dağılımı')
    return fig.to_json()

def create_performance_chart(holdings):
    dates = pd.date_range(end=datetime.now(), periods=30)
    performance_data = []
    
    for holding in holdings:
        try:
            stock = yf.Ticker(holding.symbol)
            hist = stock.history(start=dates[0], end=dates[-1])
            performance_data.append({
                'symbol': holding.symbol,
                'dates': hist.index.strftime('%Y-%m-%d').tolist(),
                'prices': hist['Close'].tolist()
            })
        except:
            continue
    
    fig = go.Figure()
    for data in performance_data:
        fig.add_trace(go.Scatter(
            x=data['dates'],
            y=data['prices'],
            name=data['symbol'],
            mode='lines'
        ))
    
    fig.update_layout(
        title='Hisse Senedi Performansı',
        xaxis_title='Tarih',
        yaxis_title='Fiyat'
    )
    
    return fig.to_json()

@login_required
def market_view(request):
    # Örnek piyasa verileri
    market_data = [
        {'symbol': 'AAPL', 'company_name': 'Apple Inc.', 'price': 175.50, 'change': 1.2, 'volume': '45.2M', 'market_cap': '2.8T'},
        {'symbol': 'MSFT', 'company_name': 'Microsoft Corp.', 'price': 380.25, 'change': 0.8, 'volume': '22.1M', 'market_cap': '2.8T'},
        {'symbol': 'GOOGL', 'company_name': 'Alphabet Inc.', 'price': 140.75, 'change': -0.5, 'volume': '18.5M', 'market_cap': '1.8T'},
        {'symbol': 'AMZN', 'company_name': 'Amazon.com Inc.', 'price': 175.25, 'change': 1.5, 'volume': '35.8M', 'market_cap': '1.8T'},
        {'symbol': 'META', 'company_name': 'Meta Platforms Inc.', 'price': 380.50, 'change': 2.1, 'volume': '28.3M', 'market_cap': '950B'},
    ]
    
    # Örnek piyasa endeksleri
    indices = {
        'sp500_value': '4,783.45',
        'sp500_change': 1.25,
        'nasdaq_value': '16,742.38',
        'nasdaq_change': 1.45,
        'dow_value': '37,305.16',
        'dow_change': -0.25
    }
    
    # Örnek piyasa haberleri
    market_news = [
        {
            'title': 'Fed Faiz Kararını Açıkladı',
            'description': 'Federal Reserve, faiz oranlarını değiştirmedi ve piyasa beklentilerini karşıladı.',
            'source': 'Bloomberg',
            'published_at': '2 saat önce',
            'url': '#'
        },
        {
            'title': 'Apple Yeni Ürünlerini Tanıttı',
            'description': 'Apple, Vision Pro başlığı ve yeni MacBook modellerini tanıttı.',
            'source': 'CNBC',
            'published_at': '5 saat önce',
            'url': '#'
        },
        {
            'title': 'Tesla Üretim Hedeflerini Açıkladı',
            'description': 'Tesla, 2024 yılı için 2 milyon araç üretim hedefini açıkladı.',
            'source': 'Reuters',
            'published_at': '8 saat önce',
            'url': '#'
        }
    ]
    
    context = {
        'market_data': market_data,
        'market_news': market_news,
        **indices
    }
    return render(request, 'finance/market.html', context)

@login_required
def portfolio_view(request):
    portfolio = request.user.portfolio
    holdings = portfolio.holdings.all()
    
    # Portföy dağılımı için veri hazırlama
    distribution = {
        'labels': [holding.symbol for holding in holdings],
        'data': [float(holding.shares * holding.average_cost) for holding in holdings]
    }
    
    # Performans verisi için örnek veri
    performance = {
        'labels': [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30, 0, -1)],
        'data': [1000 + i * 10 for i in range(30)]
    }
    
    context = {
        'portfolio': {
            'total_value': sum(float(h.shares * h.average_cost) for h in holdings),
            'daily_change': 1.5,  # Örnek değer
            'total_profit_loss': 500,  # Örnek değer
            'profit_loss_percentage': 5.0,  # Örnek değer
            'holdings': holdings,
            'distribution': distribution,
            'performance': performance
        }
    }
    return render(request, 'finance/portfolio.html', context)

@login_required
def analysis_view(request):
    symbol = request.GET.get('symbol', 'AAPL')
    
    try:
        # Hisse senedi verilerini al
        stock = yf.Ticker(symbol)
        hist = stock.history(period='1y')
        
        if hist.empty:
            raise Exception('Hisse senedi verisi bulunamadı.')
        
        # Teknik göstergeleri hesapla
        # RSI
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
        exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        
        # Bollinger Bantları
        sma = hist['Close'].rolling(window=20).mean()
        std = hist['Close'].rolling(window=20).std()
        upper_band = sma + (std * 2)
        lower_band = sma - (std * 2)
        
        # Veri hazırlama
        df = pd.DataFrame({
            'Close': hist['Close'],
            'RSI': rsi,
            'MACD': macd,
            'Signal': signal,
            'Upper': upper_band,
            'Lower': lower_band
        })
        df = df.fillna(method='ffill')
        
        # Son değerler
        current_price = df['Close'].iloc[-1]
        daily_change = ((current_price - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
        volume = hist['Volume'].iloc[-1]
        
        # Tahmin için veri hazırlama
        X = df[['RSI', 'MACD', 'Signal']].values
        y = df['Close'].values
        
        # Veriyi ölçeklendir
        scaler = MinMaxScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Modelleri eğit
        lr_model = LinearRegression()
        rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
        
        lr_model.fit(X_scaled[:-1], y[1:])
        rf_model.fit(X_scaled[:-1], y[1:])
        
        # Tahminler
        last_data = X_scaled[-1].reshape(1, -1)
        lr_pred = lr_model.predict(last_data)[0]
        rf_pred = rf_model.predict(last_data)[0]
        
        # Alım/satım sinyalleri
        signals = [
            {
                'name': 'RSI',
                'description': 'Aşırı alım/satım göstergesi',
                'signal': 'BUY' if rsi.iloc[-1] < 30 else 'SELL' if rsi.iloc[-1] > 70 else 'NEUTRAL'
            },
            {
                'name': 'MACD',
                'description': 'Trend göstergesi',
                'signal': 'BUY' if macd.iloc[-1] > signal.iloc[-1] else 'SELL'
            },
            {
                'name': 'Bollinger Bantları',
                'description': 'Fiyat volatilitesi',
                'signal': 'BUY' if current_price < lower_band.iloc[-1] else 'SELL' if current_price > upper_band.iloc[-1] else 'NEUTRAL'
            }
        ]
        
        # Model performansı
        lr_score = lr_model.score(X_scaled[:-1], y[1:])
        rf_score = rf_model.score(X_scaled[:-1], y[1:])
        
        # Fiyat grafiği için veri
        price_data = {
            'x': df.index.strftime('%Y-%m-%d').tolist(),
            'y': df['Close'].tolist(),
            'type': 'scatter',
            'mode': 'lines',
            'name': 'Fiyat'
        }
        
        context = {
            'symbol': symbol,
            'current_price': current_price,
            'daily_change': daily_change,
            'volume': volume,
            'prediction_1d': round((lr_pred + rf_pred) / 2, 2),
            'prediction_7d': round((lr_pred + rf_pred) / 2 * 1.05, 2),
            'prediction_30d': round((lr_pred + rf_pred) / 2 * 1.15, 2),
            'rsi': round(rsi.iloc[-1], 2),
            'macd': round(macd.iloc[-1], 2),
            'bb_position': round((current_price - lower_band.iloc[-1]) / (upper_band.iloc[-1] - lower_band.iloc[-1]) * 100, 2),
            'signals': signals,
            'accuracy': round((lr_score + rf_score) / 2 * 100, 2),
            'mae': round(np.mean(np.abs(y[1:] - lr_model.predict(X_scaled[:-1]))), 2),
            'r2': round((lr_score + rf_score) / 2, 2),
            'price_data': json.dumps(price_data)
        }
        
        return render(request, 'finance/analysis.html', context)
        
    except Exception as e:
        messages.error(request, str(e))
        return redirect('market')

@login_required
@require_POST
def add_to_watchlist(request):
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol')
        
        if not symbol:
            return JsonResponse({'success': False, 'error': 'Hisse senedi sembolü gerekli.'})
        
        watchlist, created = Watchlist.objects.get_or_create(
            user=request.user,
            name='Varsayılan'
        )
        
        if symbol not in watchlist.symbols:
            watchlist.symbols.append(symbol)
            watchlist.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def remove_holding(request):
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol')
        
        if not symbol:
            return JsonResponse({'success': False, 'error': 'Hisse senedi sembolü gerekli.'})
        
        holding = StockHolding.objects.filter(
            portfolio=request.user.portfolio,
            symbol=symbol
        ).first()
        
        if holding:
            holding.delete()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Hisse senedi bulunamadı.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def prediction_search_view(request):
    symbol = request.GET.get('symbol', '').upper()
    context = {'searched': False}
    if symbol:
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period='1y')
            if hist.empty:
                messages.error(request, 'Hisse senedi verisi bulunamadı.')
            else:
                # Teknik göstergeler
                rsi = calculate_rsi(hist['Close'])
                macd, signal = calculate_macd(hist['Close'])
                upper_band, lower_band = calculate_bollinger_bands(hist['Close'])
                df = pd.DataFrame({
                    'Close': hist['Close'],
                    'RSI': rsi,
                    'MACD': macd,
                    'Signal': signal,
                    'Upper': upper_band,
                    'Lower': lower_band
                }).fillna(method='ffill')
                # Model
                X = df[['RSI', 'MACD', 'Signal']].values
                y = df['Close'].values
                scaler = MinMaxScaler()
                X_scaled = scaler.fit_transform(X)
                lr_model = LinearRegression()
                rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
                lr_model.fit(X_scaled[:-1], y[1:])
                rf_model.fit(X_scaled[:-1], y[1:])
                last_data = X_scaled[-1].reshape(1, -1)
                lr_pred = lr_model.predict(last_data)[0]
                rf_pred = rf_model.predict(last_data)[0]
                # Grafik verisi
                price_data = {
                    'x': df.index.strftime('%Y-%m-%d').tolist(),
                    'y': df['Close'].tolist(),
                    'type': 'scatter',
                    'mode': 'lines',
                    'name': 'Fiyat'
                }
                # Sonuçları context'e ekle
                context.update({
                    'searched': True,
                    'symbol': symbol,
                    'current_price': df['Close'].iloc[-1],
                    'prediction_1d': round((lr_pred + rf_pred) / 2, 2),
                    'rsi': round(rsi.iloc[-1], 2),
                    'macd': round(macd.iloc[-1], 2),
                    'upper_band': round(upper_band.iloc[-1], 2),
                    'lower_band': round(lower_band.iloc[-1], 2),
                    'price_data': json.dumps(price_data)
                })
        except Exception as e:
            messages.error(request, f'Hata: {str(e)}')
    return render(request, 'finance/prediction_search.html', context)

@login_required
def stock_predictor_view(request):
    symbol = request.GET.get('symbol', '').upper()
    searched = False
    context = {
        'symbol': symbol,
        'searched': searched
    }
    
    if symbol:
        try:
            # Hisse senedi verilerini al
            stock = yf.Ticker(symbol)
            hist = stock.history(period='1y')
            
            if hist.empty:
                messages.error(request, f"{symbol} için veri bulunamadı.")
                return render(request, 'finance/stock_predictor.html', context)
            
            # Teknik göstergeleri hesapla
            close_prices = hist['Close'].values
            rsi = calculate_rsi(close_prices)
            macd, signal = calculate_macd(close_prices)
            upper_band, lower_band = calculate_bollinger_bands(close_prices)
            
            # Tahminleri hesapla
            prediction_1d = predict_price(close_prices, 1)
            prediction_7d = predict_price(close_prices, 7)
            prediction_30d = predict_price(close_prices, 30)
            
            # Model performans metriklerini hesapla
            accuracy, r2, mae = calculate_model_metrics(close_prices)
            
            # Alım/satım sinyallerini oluştur
            signals = [
                {
                    'name': 'RSI',
                    'signal': 'BUY' if rsi < 30 else 'SELL' if rsi > 70 else 'HOLD',
                    'description': f'RSI değeri: {rsi:.2f}'
                },
                {
                    'name': 'MACD',
                    'signal': 'BUY' if macd[-1] > signal[-1] else 'SELL',
                    'description': f'MACD: {macd[-1]:.2f}, Sinyal: {signal[-1]:.2f}'
                },
                {
                    'name': 'Bollinger Bands',
                    'signal': 'BUY' if close_prices[-1] < lower_band[-1] else 'SELL' if close_prices[-1] > upper_band[-1] else 'HOLD',
                    'description': f'Fiyat: {close_prices[-1]:.2f}, Üst Bant: {upper_band[-1]:.2f}, Alt Bant: {lower_band[-1]:.2f}'
                }
            ]
            
            # Grafik verilerini hazırla
            price_data = {
                'x': hist.index.strftime('%Y-%m-%d').tolist(),
                'y': hist['Close'].tolist(),
                'type': 'scatter',
                'mode': 'lines',
                'name': 'Fiyat'
            }
            
            # Tahmin tarihini hesapla
            last_date = hist.index[-1]
            prediction_date = (last_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            
            context.update({
                'searched': True,
                'current_price': close_prices[-1],
                'rsi': rsi,
                'macd': macd[-1],
                'upper_band': upper_band[-1],
                'lower_band': lower_band[-1],
                'prediction_1d': prediction_1d,
                'prediction_7d': prediction_7d,
                'prediction_30d': prediction_30d,
                'accuracy': accuracy,
                'r2': r2,
                'mae': mae,
                'signals': signals,
                'price_data': price_data,
                'prediction_date': prediction_date
            })
            
        except Exception as e:
            messages.error(request, f"Analiz sırasında bir hata oluştu: {str(e)}")
    
    return render(request, 'finance/stock_predictor.html', context)

def predict_price(prices, days):
    """Hisse senedi fiyatını tahmin eder"""
    try:
        # Veriyi hazırla
        df = pd.DataFrame({'Close': prices})
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['RSI'] = calculate_rsi(df['Close'])
        macd, signal = calculate_macd(df['Close'])
        df['MACD'] = macd
        df['Signal'] = signal
        
        # NaN değerleri temizle
        df = df.dropna()
        
        # Özellikler ve hedef değişken
        features = ['Close', 'MA5', 'MA20', 'RSI', 'MACD', 'Signal']
        X = df[features].values
        y = df['Close'].shift(-1).dropna().values
        X = X[:-1]
        
        # Veriyi ölçeklendir
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Modelleri eğit
        lr_model = LinearRegression()
        rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
        
        lr_model.fit(X_scaled, y)
        rf_model.fit(X_scaled, y)
        
        # Son veriyi kullanarak tahmin yap
        last_data = X_scaled[-1].reshape(1, -1)
        lr_pred = lr_model.predict(last_data)[0]
        rf_pred = rf_model.predict(last_data)[0]
        
        # Tahminleri birleştir
        prediction = (lr_pred + rf_pred) / 2
        
        # Günlük değişim oranını hesapla
        daily_change = (prediction - prices[-1]) / prices[-1]
        
        # İstenen gün sayısına göre tahmini hesapla
        final_prediction = prices[-1] * (1 + daily_change * days)
        
        return round(final_prediction, 2)
    except Exception as e:
        print(f"Tahmin hatası: {str(e)}")
        return prices[-1]

def calculate_model_metrics(prices):
    """Model performans metriklerini hesaplar"""
    try:
        # Veriyi hazırla
        df = pd.DataFrame({'Close': prices})
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['RSI'] = calculate_rsi(df['Close'])
        macd, signal = calculate_macd(df['Close'])
        df['MACD'] = macd
        df['Signal'] = signal
        
        # NaN değerleri temizle
        df = df.dropna()
        
        # Özellikler ve hedef değişken
        features = ['Close', 'MA5', 'MA20', 'RSI', 'MACD', 'Signal']
        X = df[features].values
        y = df['Close'].shift(-1).dropna().values
        X = X[:-1]
        
        # Veriyi ölçeklendir
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Modelleri eğit
        lr_model = LinearRegression()
        rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
        
        lr_model.fit(X_scaled, y)
        rf_model.fit(X_scaled, y)
        
        # Model performans metriklerini hesapla
        lr_score = lr_model.score(X_scaled, y)
        rf_score = rf_model.score(X_scaled, y)
        
        # Ortalama doğruluk
        accuracy = round((lr_score + rf_score) / 2 * 100, 2)
        
        # R² skoru
        r2 = round((lr_score + rf_score) / 2, 2)
        
        # Ortalama mutlak hata
        lr_pred = lr_model.predict(X_scaled)
        rf_pred = rf_model.predict(X_scaled)
        mae = round(np.mean(np.abs(y - (lr_pred + rf_pred) / 2)), 2)
        
        return accuracy, r2, mae
    except Exception as e:
        print(f"Metrik hesaplama hatası: {str(e)}")
        return 0, 0, 0
