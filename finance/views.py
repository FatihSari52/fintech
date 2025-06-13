import yfinance as yf
import pandas as pd
import numpy as np
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.views.decorators.http import require_POST, require_http_methods
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
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
import requests
from bs4 import BeautifulSoup
import random
from django.core.cache import cache
from django.conf import settings
import time

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
    """Bollinger Bantlarını hesaplar"""
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

def get_bloomberg_news():
    try:
        url = "https://www.bloomberg.com/markets"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        print("Bloomberg haberleri alınıyor...")
        response = requests.get(url, headers=headers)
        print(f"Bloomberg yanıt kodu: {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        news_items = []
        articles = soup.find_all('article', class_='story-list-story')[:2]  # İlk 2 haber
        print(f"Bulunan Bloomberg haber sayısı: {len(articles)}")
        
        for article in articles:
            title = article.find('h3')
            if title:
                title = title.text.strip()
                link = article.find('a')['href']
                if not link.startswith('http'):
                    link = 'https://www.bloomberg.com' + link
                news_items.append({
                    'title': title,
                    'description': 'Bloomberg Markets',
                    'source': 'Bloomberg',
                    'published_at': 'Son 1 saat',
                    'url': link
                })
                print(f"Bloomberg haber eklendi: {title}")
        
        return news_items
    except Exception as e:
        print(f"Bloomberg haberleri alınırken hata: {str(e)}")
        return []

def get_cnbc_news():
    try:
        url = "https://www.cnbc.com/markets/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        print("CNBC haberleri alınıyor...")
        response = requests.get(url, headers=headers)
        print(f"CNBC yanıt kodu: {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        news_items = []
        articles = soup.find_all('div', class_='Card-titleContainer')[:2]  # İlk 2 haber
        print(f"Bulunan CNBC haber sayısı: {len(articles)}")
        
        for article in articles:
            title = article.find('a')
            if title:
                title = title.text.strip()
                link = title['href']
                if not link.startswith('http'):
                    link = 'https://www.cnbc.com' + link
                news_items.append({
                    'title': title,
                    'description': 'CNBC Markets',
                    'source': 'CNBC',
                    'published_at': 'Son 1 saat',
                    'url': link
                })
                print(f"CNBC haber eklendi: {title}")
        
        return news_items
    except Exception as e:
        print(f"CNBC haberleri alınırken hata: {str(e)}")
        return []

def get_yahoo_news():
    try:
        print("Yahoo Finance haberleri alınıyor...")
        # Popüler hisse senetleri için haberleri al
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA']
        news_items = []
        
        for symbol in symbols:
            try:
                stock = yf.Ticker(symbol)
                news = stock.news[:2]  # Her hisse için ilk 2 haber
                print(f"\n{symbol} için ham haber verisi:")
                print(news)
                
                for item in news:
                    try:
                        print(f"\nHaber öğesi anahtarları: {item.keys()}")
                        if not all(key in item for key in ['title', 'link', 'providerPublishTime']):
                            print(f"{symbol} için eksik haber verisi atlandı")
                            print(f"Mevcut anahtarlar: {list(item.keys())}")
                            continue
                            
                        news_items.append({
                            'title': item['title'],
                            'description': f"{symbol} - {item.get('publisher', 'Yahoo Finance')}",
                            'source': 'Yahoo Finance',
                            'published_at': datetime.fromtimestamp(item['providerPublishTime']).strftime('%Y-%m-%d %H:%M'),
                            'url': item['link']
                        })
                        print(f"Yahoo Finance haber eklendi: {item['title']}")
                    except Exception as e:
                        print(f"{symbol} için haber işlenirken hata: {str(e)}")
                        continue
            except Exception as e:
                print(f"{symbol} için haber alınırken hata: {str(e)}")
                continue
        
        print(f"\nToplam haber sayısı: {len(news_items)}")
        return news_items
    except Exception as e:
        print(f"Yahoo Finance haberleri alınırken hata: {str(e)}")
        return []

@login_required
def market_view(request):
    # Get market data
    market_data = get_market_data()
    
    # Get market indices
    try:
        sp500 = yf.Ticker("^GSPC")
        nasdaq = yf.Ticker("^IXIC")
        dow = yf.Ticker("^DJI")
        
        sp500_info = sp500.info
        nasdaq_info = nasdaq.info
        dow_info = dow.info
        
        context = {
            'market_data': market_data,
            'sp500_value': round(sp500_info.get('regularMarketPrice', 0), 2),
            'sp500_change': round(sp500_info.get('regularMarketChangePercent', 0), 2),
            'nasdaq_value': round(nasdaq_info.get('regularMarketPrice', 0), 2),
            'nasdaq_change': round(nasdaq_info.get('regularMarketChangePercent', 0), 2),
            'dow_value': round(dow_info.get('regularMarketPrice', 0), 2),
            'dow_change': round(dow_info.get('regularMarketChangePercent', 0), 2),
        }
    except Exception as e:
        print(f"Market indices error: {str(e)}")
        context = {
            'market_data': market_data,
            'sp500_value': 0,
            'sp500_change': 0,
            'nasdaq_value': 0,
            'nasdaq_change': 0,
            'dow_value': 0,
            'dow_change': 0,
        }
    
    return render(request, 'finance/market.html', context)

@login_required
def portfolio_view(request):
    portfolio = request.user.portfolio
    holdings = portfolio.holdings.all()
    
    # Portföy değerlerini hesapla
    total_value = 0
    total_cost = 0
    total_profit_loss = 0
    holdings_data = []
    
    for holding in holdings:
        try:
            # Güncel fiyat bilgisini al
            stock = yf.Ticker(holding.symbol)
            # Günün kapanış fiyatını al
            hist = stock.history(period='1d')
            current_price = float(hist['Close'].iloc[-1]) if not hist.empty else float(stock.info.get('currentPrice', 0))
            
            # Değerleri hesapla
            current_value = float(holding.shares) * current_price
            cost_basis = float(holding.shares) * float(holding.average_cost)
            profit_loss = current_value - cost_basis
            profit_loss_percentage = (profit_loss / cost_basis) * 100 if cost_basis > 0 else 0
            
            # Toplam değerleri güncelle
            total_value += current_value
            total_cost += cost_basis
            total_profit_loss += profit_loss
            
            # Hisse verilerini listeye ekle
            holdings_data.append({
                'symbol': holding.symbol,
                'shares': holding.shares,
                'average_cost': float(holding.average_cost),
                'purchase_date': holding.purchase_date.strftime('%Y-%m-%d'),
                'current_price': current_price,
                'current_value': current_value,
                'profit_loss': profit_loss,
                'profit_loss_percentage': profit_loss_percentage
            })
        except Exception as e:
            print(f"Hisse senedi verisi alınırken hata: {str(e)}")
            continue
    
    # Portföy dağılımı için veri hazırlama
    distribution = {
        'labels': [holding['symbol'] for holding in holdings_data],
        'data': [float(holding['current_value']) for holding in holdings_data]
    }
    
    # Performans verisi için son 30 günlük veri
    performance_data = []
    dates = pd.date_range(end=datetime.now(), periods=30)
    
    for date in dates:
        daily_value = 0
        for holding in holdings_data:
            try:
                stock = yf.Ticker(holding['symbol'])
                hist = stock.history(start=date, end=date + timedelta(days=1))
                if not hist.empty:
                    price = float(hist['Close'].iloc[0])
                    daily_value += float(holding['shares']) * price
            except:
                continue
        performance_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'value': float(daily_value)
        })
    
    performance = {
        'labels': [data['date'] for data in performance_data],
        'data': [data['value'] for data in performance_data]
    }
    
    # Günlük değişim hesaplama
    daily_change = 0
    if len(performance_data) >= 2 and performance_data[-2]['value'] > 0:
        daily_change = ((performance_data[-1]['value'] - performance_data[-2]['value']) / performance_data[-2]['value']) * 100
    
    # Portföy toplam değerini güncelle
    portfolio.total_value = total_value
    portfolio.save()
    
    context = {
        'portfolio': {
            'total_value': total_value,
            'total_cost': total_cost,
            'daily_change': daily_change,
            'total_profit_loss': total_profit_loss,
            'profit_loss_percentage': (total_profit_loss / total_cost) * 100 if total_cost > 0 else 0,
            'holdings': holdings_data,
            'distribution': distribution,
            'performance': performance
        }
    }
    return render(request, 'finance/portfolio.html', context)

@login_required
def analysis_view(request):
    symbol = request.GET.get('symbol', 'AAPL')
    cache_key = f'analysis_{symbol}'
    cached_result = cache.get(cache_key)
    
    if cached_result:
        return render(request, 'finance/analysis.html', cached_result)
    
    try:
        # Set timeout for Yahoo Finance API call
        stock = yf.Ticker(symbol)
        start_time = time.time()
        hist = stock.history(period='1y')
        
        if time.time() - start_time > 10:  # 10 second timeout
            raise Exception('Veri alımı zaman aşımına uğradı.')
        
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
        
        # Cache the results for 5 minutes
        cache.set(cache_key, context, 300)
        
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

@login_required(login_url='login')
def stock_predictor_view(request):
    symbol = request.GET.get('symbol', 'AAPL')
    searched = False
    
    if symbol:
        searched = True
        try:
            # Hisse senedi verilerini al
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # Geçmiş verileri al
            df = stock.history(period='1y')
            
            if df.empty:
                raise Exception('Hisse senedi verisi bulunamadı.')
            
            # Güncel fiyat ve değişim
            current_price = df['Close'].iloc[-1]
            daily_change = ((current_price - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
            
            # Teknik göstergeleri hesapla
            rsi = calculate_rsi(df['Close']).iloc[-1]
            macd, signal = calculate_macd(df['Close'])
            upper_band, lower_band = calculate_bollinger_bands(df['Close'])
            
            # Tahminleri hesapla
            prices = df['Close'].values.reshape(-1, 1)
            prediction_1d = predict_price(prices, 1)
            prediction_7d = predict_price(prices, 7)
            
            # Model metriklerini hesapla
            accuracy, mae, r2 = calculate_model_metrics(prices)
            
            # Grafik verilerini hazırla
            price_data = {
                'x': df.index.strftime('%Y-%m-%d').tolist(),
                'y': df['Close'].tolist(),
                'type': 'scatter',
                'mode': 'lines',
                'name': 'Fiyat'
            }
            
            context = {
                'symbol': symbol,
                'company_name': info.get('longName', symbol),
                'current_price': current_price,
                'change': daily_change,
                'rsi': round(rsi, 2),
                'macd': round(macd.iloc[-1], 2),
                'upper_band': round(upper_band.iloc[-1], 2),
                'lower_band': round(lower_band.iloc[-1], 2),
                'prediction_1d': round(prediction_1d, 2),
                'prediction_7d': round(prediction_7d, 2),
                'accuracy': round(accuracy, 2),
                'mae': round(mae, 2),
                'r2': round(r2, 2),
                'price_data': json.dumps(price_data),
                'searched': searched
            }
            
            return render(request, 'finance/stock_predictor.html', context)
            
        except Exception as e:
            messages.error(request, f"Hisse senedi verisi alınırken bir hata oluştu: {str(e)}")
            return redirect('market')
    
    return render(request, 'finance/stock_predictor.html', {'searched': searched})

def predict_price(prices, days):
    """Hisse senedi fiyatını tahmin eder"""
    try:
        # Veriyi hazırla
        df = pd.DataFrame({'Close': prices.flatten()})
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
        
        # Ortalama tahmin
        prediction = (lr_pred + rf_pred) / 2
        
        # Günlük değişim oranı
        daily_change = (df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]
        
        # Gelecek tahmin
        future_prediction = prediction * (1 + daily_change) ** days
        
        return future_prediction
        
    except Exception as e:
        print(f"Tahmin hesaplanırken hata oluştu: {str(e)}")
        return 0

def calculate_model_metrics(prices):
    """Model performans metriklerini hesaplar"""
    try:
        # Veriyi hazırla
        df = pd.DataFrame({'Close': prices.flatten()})
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
        y = df['Close'].values
        
        # Veriyi ölçeklendir
        scaler = MinMaxScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Modelleri eğit
        lr_model = LinearRegression()
        rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
        
        lr_model.fit(X_scaled[:-1], y[1:])
        rf_model.fit(X_scaled[:-1], y[1:])
        
        # Model performansı
        lr_score = lr_model.score(X_scaled[:-1], y[1:])
        rf_score = rf_model.score(X_scaled[:-1], y[1:])
        
        # Metrikleri hesapla
        accuracy = (lr_score + rf_score) / 2 * 100
        mae = np.mean(np.abs(y[1:] - lr_model.predict(X_scaled[:-1])))
        r2 = (lr_score + rf_score) / 2
        
        return accuracy, mae, r2
        
    except Exception as e:
        print(f"Model metrikleri hesaplanırken hata oluştu: {str(e)}")
        return 0, 0, 0

@login_required(login_url='login')
def trading_chart(request):
    symbol = request.GET.get('symbol', 'AAPL')  # Default to AAPL if no symbol provided
    try:
        # Hisse senedi bilgilerini al
        stock = yf.Ticker(symbol)
        info = stock.info
        
        context = {
            'symbol': symbol,
            'company_name': info.get('longName', symbol),
            'current_price': info.get('currentPrice', 0),
            'change': info.get('regularMarketChangePercent', 0),
            'volume': info.get('regularMarketVolume', 0),
            'market_cap': info.get('marketCap', 0)
        }
        return render(request, 'finance/trading_chart.html', context)
    except Exception as e:
        messages.error(request, f"Hisse senedi verisi alınırken bir hata oluştu: {str(e)}")
        return redirect('market')

@login_required(login_url='login')
@require_http_methods(["GET"])
def get_stock_data(request):
    try:
        symbol = request.GET.get('symbol', 'AAPL')
        print(f"Hisse senedi verisi alınıyor: {symbol}")

        # yfinance ile veri çek
        stock = yf.Ticker(symbol)
        df = stock.history(period='1y', interval='1d')
        
        if df.empty:
            print(f"Veri bulunamadı: {symbol}")
            return JsonResponse({'error': 'Veri bulunamadı'}, status=404)

        print(f"Ham veri satır sayısı: {len(df)}")

        # Veriyi hazırla
        candlestick_data = []
        volume_data = []

        for index, row in df.iterrows():
            try:
                timestamp = int(index.timestamp() * 1000)  # Unix timestamp (milisaniye)
                
                # Mum verisi
                candlestick_data.append({
                    'time': timestamp,
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close'])
                })

                # Hacim verisi
                volume_data.append({
                    'time': timestamp,
                    'value': float(row['Volume']),
                    'color': '#26a69a' if row['Close'] >= row['Open'] else '#ef5350'
                })
            except Exception as e:
                print(f"Satır işleme hatası: {e}")
                continue

        if not candlestick_data or not volume_data:
            print("Veri hazırlama hatası: Boş veri")
            return JsonResponse({'error': 'Veri hazırlanamadı'}, status=500)

        print(f"Hazırlanan mum verisi sayısı: {len(candlestick_data)}")
        print(f"Hazırlanan hacim verisi sayısı: {len(volume_data)}")

        response_data = {
            'candlesticks': candlestick_data,
            'volume': volume_data
        }

        return JsonResponse(response_data)

    except Exception as e:
        print(f"Genel hata: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='login')
@require_http_methods(["GET"])
def get_technical_indicator(request):
    symbol = request.GET.get('symbol', 'AAPL')
    indicator = request.GET.get('indicator')
    period = int(request.GET.get('period', 14))
    
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period='1mo')
        
        if indicator == 'sma':
            sma = SMAIndicator(close=df['Close'], window=period)
            values = sma.sma_indicator()
        elif indicator == 'ema':
            ema = EMAIndicator(close=df['Close'], window=period)
            values = ema.ema_indicator()
        elif indicator == 'macd':
            macd = MACD(close=df['Close'])
            values = macd.macd()
        elif indicator == 'rsi':
            rsi = RSIIndicator(close=df['Close'], window=period)
            values = rsi.rsi()
        elif indicator == 'stochastic':
            high_14 = df['High'].rolling(window=period).max()
            low_14 = df['Low'].rolling(window=period).min()
            k = 100 * ((df['Close'] - low_14) / (high_14 - low_14))
            values = k
        elif indicator == 'cci':
            tp = (df['High'] + df['Low'] + df['Close']) / 3
            tp_ma = tp.rolling(window=period).mean()
            tp_md = tp.rolling(window=period).apply(lambda x: pd.Series(x).mad())
            values = (tp - tp_ma) / (0.015 * tp_md)
        elif indicator == 'mfi':
            typical_price = (df['High'] + df['Low'] + df['Close']) / 3
            money_flow = typical_price * df['Volume']
            positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0)
            negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0)
            positive_mf = positive_flow.rolling(window=period).sum()
            negative_mf = negative_flow.rolling(window=period).sum()
            values = 100 - (100 / (1 + positive_mf / negative_mf))
        elif indicator == 'williams_r':
            highest_high = df['High'].rolling(window=period).max()
            lowest_low = df['Low'].rolling(window=period).min()
            values = -100 * (highest_high - df['Close']) / (highest_high - lowest_low)
        elif indicator == 'roc':
            values = ((df['Close'] - df['Close'].shift(period)) / df['Close'].shift(period)) * 100
        elif indicator == 'obv':
            values = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        elif indicator == 'ad':
            clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
            clv = clv.fillna(0)
            values = (clv * df['Volume']).cumsum()
        elif indicator == 'cmf':
            mfv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
            mfv = mfv.fillna(0)
            mfv *= df['Volume']
            values = mfv.rolling(window=period).sum() / df['Volume'].rolling(window=period).sum()
        elif indicator == 'atr':
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            values = true_range.rolling(window=period).mean()
        elif indicator == 'bollinger_bands':
            sma = df['Close'].rolling(window=period).mean()
            std = df['Close'].rolling(window=period).std()
            upper_band = sma + (std * 2)
            lower_band = sma - (std * 2)
            values = pd.DataFrame({
                'upper': upper_band,
                'middle': sma,
                'lower': lower_band
            })
        elif indicator == 'keltner_channels':
            ema = df['Close'].ewm(span=period).mean()
            atr = calculate_atr(df, period)
            upper_band = ema + (atr * 2)
            lower_band = ema - (atr * 2)
            values = pd.DataFrame({
                'upper': upper_band,
                'middle': ema,
                'lower': lower_band
            })
        elif indicator == 'donchian_channels':
            upper_band = df['High'].rolling(window=period).max()
            lower_band = df['Low'].rolling(window=period).min()
            middle_band = (upper_band + lower_band) / 2
            values = pd.DataFrame({
                'upper': upper_band,
                'middle': middle_band,
                'lower': lower_band
            })
        else:
            return JsonResponse({'error': 'Geçersiz gösterge'}, status=400)
        
        # Grafik formatına dönüştür
        if isinstance(values, pd.DataFrame):
            indicator_data = []
            for col in values.columns:
                series_data = []
                for index, value in values[col].items():
                    if pd.notna(value):
                        series_data.append({
                            'time': int(index.timestamp()),
                            'value': float(value)
                        })
                indicator_data.append({
                    'name': col,
                    'data': series_data
                })
        else:
            indicator_data = []
            for index, value in values.items():
                if pd.notna(value):
                    indicator_data.append({
                        'time': int(index.timestamp()),
                        'value': float(value)
                    })
        
        return JsonResponse({'data': indicator_data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required(login_url='login')
@require_http_methods(["GET"])
def apply_strategy(request):
    symbol = request.GET.get('symbol', 'AAPL')
    strategy = request.GET.get('strategy')
    
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period='1mo')
        
        signals = []
        
        if strategy == 'moving_average_crossover':
            # SMA 20 ve 50 kesişimi
            sma20 = df['Close'].rolling(window=20).mean()
            sma50 = df['Close'].rolling(window=50).mean()
            
            for i in range(1, len(df)):
                if sma20[i] > sma50[i] and sma20[i-1] <= sma50[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'aboveBar',
                        'color': '#26a69a',
                        'shape': 'arrowUp',
                        'text': 'Al'
                    })
                elif sma20[i] < sma50[i] and sma20[i-1] >= sma50[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'belowBar',
                        'color': '#ef5350',
                        'shape': 'arrowDown',
                        'text': 'Sat'
                    })
        
        elif strategy == 'macd_crossover':
            # MACD kesişimi
            macd = MACD(close=df['Close'])
            macd_line = macd.macd()
            signal_line = macd.macd_signal()
            
            for i in range(1, len(df)):
                if macd_line[i] > signal_line[i] and macd_line[i-1] <= signal_line[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'aboveBar',
                        'color': '#26a69a',
                        'shape': 'arrowUp',
                        'text': 'Al'
                    })
                elif macd_line[i] < signal_line[i] and macd_line[i-1] >= signal_line[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'belowBar',
                        'color': '#ef5350',
                        'shape': 'arrowDown',
                        'text': 'Sat'
                    })
        
        elif strategy == 'bollinger_breakout':
            # Bollinger Bantları kırılması
            sma = df['Close'].rolling(window=20).mean()
            std = df['Close'].rolling(window=20).std()
            upper_band = sma + (std * 2)
            lower_band = sma - (std * 2)
            
            for i in range(1, len(df)):
                if df['Close'][i] > upper_band[i] and df['Close'][i-1] <= upper_band[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'aboveBar',
                        'color': '#26a69a',
                        'shape': 'arrowUp',
                        'text': 'Al'
                    })
                elif df['Close'][i] < lower_band[i] and df['Close'][i-1] >= lower_band[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'belowBar',
                        'color': '#ef5350',
                        'shape': 'arrowDown',
                        'text': 'Sat'
                    })
        
        elif strategy == 'rsi_overbought_oversold':
            # RSI aşırı alım/satım
            rsi = RSIIndicator(close=df['Close']).rsi()
            
            for i in range(1, len(df)):
                if rsi[i] < 30 and rsi[i-1] >= 30:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'aboveBar',
                        'color': '#26a69a',
                        'shape': 'arrowUp',
                        'text': 'Al'
                    })
                elif rsi[i] > 70 and rsi[i-1] <= 70:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'belowBar',
                        'color': '#ef5350',
                        'shape': 'arrowDown',
                        'text': 'Sat'
                    })
        
        elif strategy == 'stochastic_crossover':
            # Stokastik kesişimi
            high_14 = df['High'].rolling(window=14).max()
            low_14 = df['Low'].rolling(window=14).min()
            k = 100 * ((df['Close'] - low_14) / (high_14 - low_14))
            d = k.rolling(window=3).mean()
            
            for i in range(1, len(df)):
                if k[i] > d[i] and k[i-1] <= d[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'aboveBar',
                        'color': '#26a69a',
                        'shape': 'arrowUp',
                        'text': 'Al'
                    })
                elif k[i] < d[i] and k[i-1] >= d[i-1]:
                    signals.append({
                        'time': int(df.index[i].timestamp()),
                        'position': 'belowBar',
                        'color': '#ef5350',
                        'shape': 'arrowDown',
                        'text': 'Sat'
                    })
        
        return JsonResponse({'signals': signals})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def calculate_atr(df, period):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window=period).mean()

@login_required(login_url='login')
@require_http_methods(["POST"])
def add_price_alert(request):
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol')
        price = float(data.get('price'))
        condition = data.get('condition')
        
        # Burada alarmı veritabanına kaydedebilirsiniz
        # Şimdilik sadece başarılı yanıt dönüyoruz
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def add_holding(request):
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol')
        shares = data.get('shares')
        average_cost = data.get('average_cost')
        purchase_date = data.get('purchase_date')
        
        if not all([symbol, shares, average_cost, purchase_date]):
            return JsonResponse({'success': False, 'error': 'Tüm alanlar gereklidir.'})
        
        # Hisse senedinin geçerli olup olmadığını kontrol et
        stock = yf.Ticker(symbol)
        info = stock.info
        if not info:
            return JsonResponse({'success': False, 'error': 'Geçersiz hisse senedi sembolü.'})
        
        # Portföye ekle
        holding = StockHolding.objects.create(
            portfolio=request.user.portfolio,
            symbol=symbol.upper(),
            shares=int(shares),
            average_cost=float(average_cost),
            purchase_date=purchase_date
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        print(f"Hisse senedi eklenirken hata: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["GET"])
def get_market_news(request):
    try:
        print("Piyasa haberleri isteği alındı")
        # Yahoo Finance haberlerini al
        market_news = get_yahoo_news()
        print(f"Toplam haber sayısı: {len(market_news)}")
        
        return JsonResponse({
            'success': True,
            'news': market_news
        })
    except Exception as e:
        print(f"Piyasa haberleri alınırken hata: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
