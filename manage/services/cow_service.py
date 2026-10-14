from django.db import transaction

from manage.models import Cow


COW_FIELDS = ("name", "identifier", "birth_date", "breed", "status", "notes")


@transaction.atomic
def create_cow(*, farm, cow_data):
    return Cow.objects.create(
        farm=farm,
        **{field: value for field, value in cow_data.items() if field in COW_FIELDS},
    )


@transaction.atomic
def update_cow(*, cow, cow_data):
    fields = {field: value for field, value in cow_data.items() if field in COW_FIELDS}
    for field, value in fields.items():
        setattr(cow, field, value)
    cow.save(update_fields=[*fields, "updated_at"])
    return cow


@transaction.atomic
def delete_cow(*, cow):
    cow.delete()
