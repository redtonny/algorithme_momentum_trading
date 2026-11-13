from django import forms

from portfolio.models import Portfolio


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ("name", "description", "initial_cash")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex. Long terme"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "initial_cash": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
        }

    def save(self, commit=True):
        portfolio = super().save(commit=False)
        portfolio.current_cash = portfolio.initial_cash
        portfolio.total_value = portfolio.initial_cash
        if commit:
            portfolio.save()
            self.save_m2m()
        return portfolio