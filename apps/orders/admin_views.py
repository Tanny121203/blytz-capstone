from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required
from apps.orders.models import PaymentChannel

User = get_user_model()


class PaymentChannelForm(forms.ModelForm):
    class Meta:
        model = PaymentChannel
        fields = (
            "kind",
            "display_name",
            "account_name",
            "account_number",
            "qr_image",
            "instructions",
            "is_active",
        )

    def clean_qr_image(self):
        qr = self.cleaned_data.get("qr_image")
        if qr and hasattr(qr, "content_type"):
            if qr.content_type and not qr.content_type.startswith("image/"):
                raise ValidationError("QR must be an image file.")
        return qr


@admin_required
def payment_channel_list(request):
    channels = PaymentChannel.objects.all()
    return render(
        request,
        "orders/payment_channels_list.html",
        {"channels": channels, "empty": not channels.exists()},
    )


@admin_required
def payment_channel_create(request):
    form = PaymentChannelForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Payment channel created.")
        return redirect("payment_channel_list")
    return render(
        request,
        "orders/payment_channel_form.html",
        {"form": form, "title": "Add payment channel", "is_edit": False},
    )


@admin_required
def payment_channel_edit(request, pk):
    channel = get_object_or_404(PaymentChannel, pk=pk)
    form = PaymentChannelForm(
        request.POST or None, request.FILES or None, instance=channel
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Payment channel updated.")
        return redirect("payment_channel_list")
    return render(
        request,
        "orders/payment_channel_form.html",
        {
            "form": form,
            "title": "Edit payment channel",
            "is_edit": True,
            "channel": channel,
        },
    )


@admin_required
@require_POST
def payment_channel_deactivate(request, pk):
    channel = get_object_or_404(PaymentChannel, pk=pk)
    channel.is_active = False
    channel.save(update_fields=["is_active"])
    messages.success(request, f"{channel.display_name} deactivated.")
    return redirect("payment_channel_list")
