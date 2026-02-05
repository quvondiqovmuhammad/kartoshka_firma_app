# operations/forms.py

from django import forms
from .models import MenuItem

class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ['name', 'produkt_type', 'beschreibung', 'verfügbar']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'produkt_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
