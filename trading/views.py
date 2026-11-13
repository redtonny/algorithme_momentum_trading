from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from portfolio.models import Portfolio
from portfolio.models import PerformanceMetric, Position, Trade
from trading.forms import PortfolioForm
from trading.models import MomentumScore, RebalanceEvent, Stock, TradingSignal
from trading.services.strategy_engine import MomentumTradingStrategy
from trading.services.momentum_calculator import MomentumCalculator


def dashboard(request):
	latest_score = MomentumScore.objects.order_by("-calculation_date").first()
	latest_date = latest_score.calculation_date if latest_score else None
	top_scores = MomentumScore.objects.none()
	if latest_date:
		top_scores = (
			MomentumScore.objects.filter(calculation_date=latest_date)
			.select_related("stock")
			.order_by("rank", "-momentum_score")[:5]
		)

	context = {
		"active_stock_count": Stock.objects.filter(is_active=True).count(),
		"portfolio_count": Portfolio.objects.filter(is_active=True).count(),
		"latest_score_date": latest_date,
		"top_scores": top_scores,
		"latest_signals": TradingSignal.objects.select_related("stock")[:6],
		"latest_rebalance": RebalanceEvent.objects.order_by("-date").first(),
	}
	return render(request, "trading/dashboard.html", context)


def momentum_scores(request):
	latest_score = MomentumScore.objects.order_by("-calculation_date").first()
	selected_date = latest_score.calculation_date if latest_score else None
	date_filter = request.GET.get("date", "")
	if date_filter:
		try:
			selected_date = date.fromisoformat(date_filter)
		except ValueError:
			messages.error(request, "La date demandée n’est pas valide.")

	scores = MomentumScore.objects.none()
	if selected_date:
		scores = (
			MomentumScore.objects.filter(calculation_date=selected_date)
			.select_related("stock")
			.order_by("rank", "-momentum_score")
		)
	top_scores = scores.order_by("-momentum_score", "stock__ticker")[:10]
	bottom_scores = scores.order_by("momentum_score", "stock__ticker")[:10]
	return render(
		request,
		"trading/momentum_scores.html",
		{
			"scores": scores,
			"top_scores": top_scores,
			"bottom_scores": bottom_scores,
			"selected_date": selected_date,
		},
	)


def trading_signals(request):
	selected_type = request.GET.get("type", "")
	selected_portfolio = request.GET.get("portfolio", "")
	if request.method == "POST":
		portfolio = Portfolio.objects.filter(
			pk=request.POST.get("portfolio"), is_active=True
		).first()
		if portfolio is None:
			messages.error(request, "Sélectionne un portefeuille actif.")
		else:
			tickers = list(
				dict.fromkeys(
					ticker.strip().upper()
					for ticker in request.POST.get("tickers", "").split(",")
					if ticker.strip()
				)
			)
			invalid_tickers = [
				ticker for ticker in tickers
				if len(ticker) > 10
				or not ticker.replace(".", "").replace("-", "").isalnum()
			]
			if invalid_tickers:
				messages.error(
					request,
					"Ticker(s) invalide(s) : " + ", ".join(invalid_tickers),
				)
			else:
				if tickers:
					stocks = []
					for ticker in tickers:
						stock, _ = Stock.objects.get_or_create(
							ticker=ticker,
							defaults={"name": ticker, "is_active": True},
						)
						if not stock.is_active:
							stock.is_active = True
							stock.save(update_fields=["is_active"])
						stocks.append(stock)
				else:
					stocks = list(Stock.objects.filter(is_active=True))

				if not stocks:
					messages.error(
						request,
						"Aucun titre actif. Saisis des tickers, par exemple AAPL, MSFT, NVDA.",
					)
				else:
					calculation_date = date.today()
					try:
						scores = MomentumCalculator().calculate_momentum_scores_bulk(
							stock_list=stocks,
							calculation_date=calculation_date,
						)
						if not scores:
							raise ValueError("Aucun score momentum n’a pu être calculé.")
						buys, sells = MomentumTradingStrategy.generate_signals_from_scores(
							portfolio, calculation_date
						)
					except Exception:
						messages.error(
							request,
							"Le calcul a échoué. Vérifie la configuration Massive et les tickers.",
						)
					else:
						messages.success(
							request,
							f"Calcul terminé : {len(scores)} score(s), "
							f"{len(buys)} achat(s), {len(sells)} vente(s). "
							"Aucun ordre n’a été envoyé.",
						)
						return redirect(f"{request.path}?portfolio={portfolio.pk}")

	signals = TradingSignal.objects.select_related(
		"stock", "momemtum_score", "portfolio"
	)
	if selected_portfolio:
		signals = signals.filter(portfolio_id=selected_portfolio)
	if selected_type in {choice[0] for choice in TradingSignal.SIGNAL_TYPES}:
		signals = signals.filter(signal_type=selected_type)
	return render(
		request,
		"trading/trading_signals.html",
		{
			"signals": signals,
			"selected_type": selected_type,
			"selected_portfolio": selected_portfolio,
			"portfolios": Portfolio.objects.filter(is_active=True),
			"latest_score_date": MomentumScore.objects.order_by(
				"-calculation_date"
			).values_list("calculation_date", flat=True).first(),
		},
	)


def portfolio_list(request):
	portfolios = Portfolio.objects.filter(is_active=True).prefetch_related("positions")
	return render(request, "trading/portfolio_list.html", {"portfolios": portfolios})


def portfolio_detail(request, portfolio_id):
	portfolio = get_object_or_404(Portfolio, pk=portfolio_id)
	positions = Position.objects.filter(portfolio=portfolio).select_related("stock")
	trades = Trade.objects.filter(portfolio=portfolio).select_related("stock")[:8]
	latest_performance = PerformanceMetric.objects.filter(portfolio=portfolio).first()
	return render(
		request,
		"trading/portfolio_detail.html",
		{
			"portfolio": portfolio,
			"positions": positions,
			"trades": trades,
			"latest_performance": latest_performance,
		},
	)


def create_portfolio(request):
	form = PortfolioForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "Le portefeuille a été créé.")
		return redirect("trading:portfolio_list")
	return render(request, "trading/create_portfolio.html", {"form": form})


def delete_portfolio(request, portfolio_id):
	portfolio = get_object_or_404(Portfolio, pk=portfolio_id)
	if request.method == "POST":
		portfolio.delete()
		messages.success(request, "Le portefeuille a été supprimé.")
		return redirect("trading:portfolio_list")
	return render(
		request, "trading/delete_portfolio.html", {"portfolio": portfolio}
	)


def snaptrade_success(request):
	return render(request, "trading/snaptrade_success.html")
