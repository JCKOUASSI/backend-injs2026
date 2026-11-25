"""Administration Django (Unfold) — utilisateurs et extensions."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from unfold.admin import ModelAdmin
from unfold.forms import UserChangeForm, UserCreationForm

from apps.formations.admin import ResponsabiliteUpInline


class UserAdmin(DjangoUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    inlines = [ResponsabiliteUpInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
