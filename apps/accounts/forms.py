from allauth.account.forms import SignupForm
from allauth.account.models import EmailAddress
from django import forms
from django.core.exceptions import ValidationError

from .models import User


class BlytzSignupForm(SignupForm):
    phone = forms.CharField(
        max_length=32,
        required=False,
        label="Phone",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Optional",
                "autocomplete": "tel",
            }
        ),
    )

    def save(self, request):
        user = super().save(request)
        user.phone = self.cleaned_data.get("phone", "")
        user.role = User.Role.CUSTOMER
        user.save(update_fields=["phone", "role"])
        return user


class ProfileForm(forms.ModelForm):
    email = forms.EmailField(label="Email")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone")
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
        }

    field_order = ("first_name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["email"].initial = self.instance.email

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        exists = (
            User.objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if exists:
            raise ValidationError("That email is already in use.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            EmailAddress.objects.filter(user=user, primary=True).update(email=user.email)
            EmailAddress.objects.get_or_create(
                user=user,
                email=user.email,
                defaults={"primary": True, "verified": True},
            )
        return user
