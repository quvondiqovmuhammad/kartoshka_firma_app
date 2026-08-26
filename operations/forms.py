from django import forms
from .models import MenuItem, FactorySettings

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


class FactorySettingsForm(forms.ModelForm):
    class Meta:
        model = FactorySettings
        fields = [
            'palettes_per_hour',
            'kg_per_palette',
            'buro_working_start',
            'buro_working_end',
            'production_working_start',
            'production_working_end',
            'next_day_cutoff_time',
        ]
        widgets = {
            'palettes_per_hour': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'min': '0.1',
                'step': 'any',
                'placeholder': 'z.B. 2.0'
            }),
            'kg_per_palette': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'min': '1',
                'step': 'any',
                'placeholder': 'z.B. 625.0'
            }),
            'buro_working_start': forms.TimeInput(attrs={
                'class': 'form-control form-control-lg',
                'type': 'time'
            }),
            'buro_working_end': forms.TimeInput(attrs={
                'class': 'form-control form-control-lg',
                'type': 'time'
            }),
            'production_working_start': forms.TimeInput(attrs={
                'class': 'form-control form-control-lg',
                'type': 'time'
            }),
            'production_working_end': forms.TimeInput(attrs={
                'class': 'form-control form-control-lg',
                'type': 'time'
            }),
            'next_day_cutoff_time': forms.TimeInput(attrs={
                'class': 'form-control form-control-lg',
                'type': 'time'
            }),
        }
        labels = {
            'palettes_per_hour': 'Paletten pro Stunde (Pal/h)',
            'kg_per_palette': 'Gewicht pro Palette (kg)',
            'buro_working_start': 'Büro Arbeitsbeginn',
            'buro_working_end': 'Büro Arbeitsende',
            'production_working_start': 'Produktion Arbeitsbeginn',
            'production_working_end': 'Produktion Arbeitsende',
            'next_day_cutoff_time': 'Cut-off-Zeit für Folgetag (Bestellgrenze)',
        }

    def clean_palettes_per_hour(self):
        val = self.cleaned_data.get('palettes_per_hour')
        if val is None or val <= 0:
            raise forms.ValidationError("Die Anzahl der Paletten pro Stunde muss größer als 0 sein.")
        return val

    def clean_kg_per_palette(self):
        val = self.cleaned_data.get('kg_per_palette')
        if val is None or val <= 0:
            raise forms.ValidationError("Das Gewicht pro Palette muss größer als 0 sein.")
        return val



