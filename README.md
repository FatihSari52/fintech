# Fintech Projesi

Bu proje, hisse senedi analizi ve tahmin yapabilen bir web uygulamasıdır.

## Özellikler

- Hisse senedi fiyat analizi
- Teknik göstergeler (RSI, MACD, Bollinger Bantları)
- Fiyat tahminleri (1, 7 ve 30 günlük)
- Portföy yönetimi
- Piyasa takibi

## Kurulum

1. Python 3.13 veya üstü sürümü yükleyin
2. Sanal ortam oluşturun:
   ```bash
   python -m venv venv
   ```
3. Sanal ortamı aktifleştirin:
   ```bash
   # Windows
   .\venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```
4. Gerekli paketleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
5. Veritabanı migrasyonlarını yapın:
   ```bash
   python manage.py migrate
   ```
6. Sunucuyu başlatın:
   ```bash
   python manage.py runserver
   ```

## Kullanım

1. http://127.0.0.1:8000/ adresine gidin
2. Hisse senedi sembolü girin (örn: AAPL, MSFT, GOOGL)
3. Analiz sonuçlarını görüntüleyin

## Teknolojiler

- Django
- Python
- NumPy
- Pandas
- yfinance
- scikit-learn
- Plotly 