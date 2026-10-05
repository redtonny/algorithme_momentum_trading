from django.contrib import admin
from portfolio.models import Portfolio, Position, Trade, PerformanceMetric

@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display=('name', 'total_value', 'current_cash','is_active', 'created_at')
    list_filter=('is_active', 'created_at')
    search_fields=('name', 'description',)
    readonly_fields= ('created_at', 'update_at')

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display=(
        'portfolio',
        'stock',
        'quantity',
        'average_cost',
        'current_value',
        'unrealized_pnl'
    )
    list_filter=('portfolio', 'last_update')
    search_fields=('portfolio__name', 'stock__ticker',)
    readonly_fields=('created_at', 'last_update')

@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
     list_display=(
            'portfolio',
            'stock',
            'trade_type',
            'quantity',
            'price',
            'status',
            'created_at'
        )
     list_filter=('trade_type', 'status', 'created_at', 'portfolio')
     search_fields=('portfolio__name', 'stock__ticker',)
     readonly_fields=('created_at', 'filled_at')
     date_hierarchy= 'created_at'
     
     
@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
     list_display=(
                'portfolio',
                'date',
                'total_value',
                'daily_return',
                'cumulative_return'
            )
     list_filter=('portfolio', 'date')
     search_fields=('portfolio__name',)
     readonly_fields=('created_at',)