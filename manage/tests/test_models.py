from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from manage.models import Cow, Farm, MilkingLineGroup, MilkingLineItem


class ManagementTests(TestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name="Farm")
        self.other_farm = Farm.objects.create(name="Other")
        self.cow = Cow.objects.create(farm=self.farm, identifier="A1", name="Cow")
        self.group = MilkingLineGroup.objects.create(farm=self.farm, name="Group")

    def test_cow_identifier_unique_within_farm(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cow.objects.create(farm=self.farm, identifier="A1", name="Other cow")

    def test_cow_identifier_allowed_in_other_farm(self):
        cow = Cow.objects.create(farm=self.other_farm, identifier="A1", name="Other cow")
        self.assertNotEqual(cow.pk, self.cow.pk)

    def test_milking_item_same_farm(self):
        item = MilkingLineItem.objects.create(group=self.group, cow=self.cow)
        self.assertEqual(item.group.farm_id, item.cow.farm_id)

    def test_milking_item_different_farms(self):
        self.group.farm = self.other_farm
        self.group.save()
        with self.assertRaises(ValidationError):
            MilkingLineItem.objects.create(group=self.group, cow=self.cow)

    def test_group_name_and_position_unique(self):
        for values in ({"name": "Group", "position": 1}, {"name": "Other", "position": 0}):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                MilkingLineGroup.objects.create(farm=self.farm, **values)

    def test_item_cow_and_position_unique(self):
        MilkingLineItem.objects.create(group=self.group, cow=self.cow)
        other = Cow.objects.create(farm=self.farm, name="Other", identifier="A2")
        for cow, position in ((self.cow, 1), (other, 0)):
            with self.subTest(position=position), self.assertRaises(ValidationError):
                MilkingLineItem.objects.create(group=self.group, cow=cow, position=position)

    def test_farm_deletion_protected(self):
        with self.assertRaises(ProtectedError):
            self.farm.delete()
