from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import ActivationCode, Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fk_name = "user"
    raw_id_fields = ("teacher",)


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]


@admin.register(ActivationCode)
class ActivationCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "is_active", "is_used", "used_at", "used_by", "created_at")
    list_filter = ("is_active", "is_used")
    search_fields = ("code", "note")
    readonly_fields = ("used_at", "used_by", "created_at")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "display_name", "teacher")
    list_filter = ("role",)
    search_fields = ("user__username", "display_name")
    raw_id_fields = ("teacher",)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
