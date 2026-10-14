from django.contrib.auth import get_user_model
from django.db import transaction

from accounts.models import FarmMembership
from manage.models import Farm


@transaction.atomic
def create_farm_with_owner(farm_data, owner_data):
    User = get_user_model()
    owner = User.objects.create_user(
        name=owner_data["name"],
        email=User.objects.normalize_email(owner_data["email"]).lower(),
        password=owner_data["password"],
        is_superuser=False,
        is_staff=False,
    )
    allowed_fields = ("name", "owner_name", "city", "state", "phone", "notes")
    farm = Farm.objects.create(
        **{key: value for key, value in farm_data.items() if key in allowed_fields},
        is_active=True,
    )
    FarmMembership.objects.create(
        farm=farm,
        user=owner,
        role=FarmMembership.Role.OWNER,
        is_active=True,
    )
    return farm
