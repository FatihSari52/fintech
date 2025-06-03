from django.urls import path
from . import views

urlpatterns = [
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
] 