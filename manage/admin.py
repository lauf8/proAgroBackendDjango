from django.contrib import admin
from .models import Cow, Farm, MilkingLineGroup, MilkingLineItem


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ("name", "owner_name", "city", "state", "is_active")
    search_fields = ("name", "owner_name", "city")
    list_filter = ("is_active", "state")


@admin.register(Cow)
class CowAdmin(admin.ModelAdmin):
    list_display = ("identifier", "name", "farm", "status")
    search_fields = ("identifier", "name", "farm__name")
    list_filter = ("status", "farm")


@admin.register(MilkingLineGroup)
class MilkingLineGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "farm", "position", "is_active")
    search_fields = ("name", "farm__name")
    list_filter = ("is_active", "farm")


@admin.register(MilkingLineItem)
class MilkingLineItemAdmin(admin.ModelAdmin):
    list_display = ("group", "cow", "position")
    search_fields = ("group__name", "cow__identifier", "cow__name")
    list_filter = ("group__farm",)
