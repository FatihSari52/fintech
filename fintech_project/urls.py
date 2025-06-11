from django.contrib import admin
from django.urls import path
from finance import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index_view, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('market/', views.market_view, name='market'),
    path('portfolio/', views.portfolio_view, name='portfolio'),
    path('analysis/', views.analysis_view, name='analysis'),
    path('stock-predictor/', views.stock_predictor_view, name='stock_predictor'),
    path('add-to-watchlist/', views.add_to_watchlist, name='add_to_watchlist'),
    path('remove-holding/', views.remove_holding, name='remove_holding'),
    path('add-holding/', views.add_holding, name='add_holding'),
    path('trading-chart/', views.trading_chart, name='trading_chart'),
    path('get-stock-data/', views.get_stock_data, name='get_stock_data'),
    path('get-technical-indicator/', views.get_technical_indicator, name='get_technical_indicator'),
    path('add-price-alert/', views.add_price_alert, name='add_price_alert'),
    path('apply-strategy/', views.apply_strategy, name='apply_strategy'),
    path('get-market-news/', views.get_market_news, name='get_market_news'),
]
