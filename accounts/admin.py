from django.contrib import admin
from .models import FarmMembership, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "name")
    list_filter = ("is_active", "is_staff", "is_superuser")
    exclude = ("password",)
    readonly_fields = ("id", "last_login", "created_at", "updated_at")
    filter_horizontal = ("groups", "user_permissions")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)


@admin.register(FarmMembership)
class FarmMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "farm", "role", "is_active")
    search_fields = ("user__email", "farm__name")
    list_filter = ("role", "is_active", "farm")
