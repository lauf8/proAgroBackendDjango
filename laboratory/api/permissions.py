from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsSuperUserOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and (
            request.user.is_superuser or request.method in SAFE_METHODS
        ))


class ReportAccessPermission(IsSuperUserOrReadOnly):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        return request.method in SAFE_METHODS and obj.status == "published" and obj.batch.farm.memberships.filter(user=request.user, is_active=True).exists()
