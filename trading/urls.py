from django.urls import path

from trading import views

app_name = "trading"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("scores/", views.momentum_scores, name="momentum_scores"),
    path("signals/", views.trading_signals, name="trading_signals"),
    path("portfolios/", views.portfolio_list, name="portfolio_list"),
    path("portfolios/create/", views.create_portfolio, name="create_portfolio"),
    path(
        "portfolios/<int:portfolio_id>/",
        views.portfolio_detail,
        name="portfolio_detail",
    ),
    path(
        "portfolios/<int:portfolio_id>/delete/",
        views.delete_portfolio,
        name="delete_portfolio",
    ),
    path("snaptrade/success/", views.snaptrade_success, name="snaptrade_success"),
]