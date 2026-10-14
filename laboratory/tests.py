from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from accounts.models import User
from manage.models import Cow, Farm
from .models import Analysis, AnalysisRevision, Microorganism, Report, Sample, SampleBatch, SampleResult
from .services import create_analysis_revision


class LaboratoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("lab@example.com", name="Lab")
        self.farm = Farm.objects.create(name="Farm")
        self.other_farm = Farm.objects.create(name="Other")
        self.cow = Cow.objects.create(farm=self.farm, name="Cow", identifier="A1")
        self.batch = SampleBatch.objects.create(farm=self.farm, title="Batch", collected_at=date(2026, 10, 1), created_by=self.user)
        self.sample = Sample.objects.create(batch=self.batch, cow=self.cow, udder_quarter=Sample.UdderQuarter.COMPOSITE, sample_code="S1")
        self.analysis = Analysis.objects.create(batch=self.batch, created_by=self.user)

    def test_receipt_cannot_precede_collection(self):
        self.batch.received_at = date(2026, 9, 30)
        with self.assertRaises(ValidationError):
            self.batch.save()

    def test_receipt_on_collection_date_allowed(self):
        self.batch.received_at = self.batch.collected_at
        self.batch.save()

    def test_sample_cow_must_match_batch_farm(self):
        cow = Cow.objects.create(farm=self.other_farm, name="Other", identifier="A1")
        with self.assertRaises(ValidationError):
            Sample.objects.create(batch=self.batch, cow=cow, udder_quarter="composite", sample_code="S2")

    def test_sample_code_unique_within_batch(self):
        with self.assertRaises(ValidationError):
            Sample.objects.create(batch=self.batch, cow=self.cow, udder_quarter="left_front", sample_code="S1")

    def test_sample_quarter_unique_within_batch(self):
        with self.assertRaises(ValidationError):
            Sample.objects.create(batch=self.batch, cow=self.cow, udder_quarter="composite", sample_code="S2")

    def test_sample_code_allowed_in_another_batch(self):
        batch = SampleBatch.objects.create(farm=self.farm, title="Another", collected_at=date(2026, 10, 2), created_by=self.user)
        Sample.objects.create(batch=batch, cow=self.cow, udder_quarter="composite", sample_code="S1")

    def test_microorganisms_are_dynamic(self):
        organism = Microorganism.objects.create(name="New organism", scientific_name="Novel species")
        self.assertEqual(str(organism), "Novel species")
        self.assertEqual(str(Microorganism.objects.create(name="Provisional")), "Provisional")

    def test_positive_requires_organism(self):
        for name in ("", "   "):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                SampleResult.objects.create(sample=self.sample, result_type="positive", identified_name=name)

    def test_positive_constraint_enforced_in_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SampleResult.objects.bulk_create([SampleResult(sample=self.sample, result_type="positive")])

    def test_positive_with_catalog_organism(self):
        organism = Microorganism.objects.create(name="Organism")
        SampleResult.objects.create(sample=self.sample, result_type="positive", microorganism=organism)
        with self.assertRaises(ValidationError):
            SampleResult.objects.create(sample=self.sample, result_type="positive", microorganism=organism)

    def test_positive_with_provisional_name(self):
        result = SampleResult.objects.create(sample=self.sample, result_type="positive", identified_name=" New organism ")
        self.assertEqual(result.identified_name, "New organism")

    def test_nonpositive_without_organism(self):
        for result_type in ("negative", "inconclusive", "contaminated"):
            SampleResult.objects.create(sample=self.sample, result_type=result_type)

    def test_multiple_revisions(self):
        first = create_analysis_revision(analysis=self.analysis, created_by=self.user, summary="First")
        second = create_analysis_revision(analysis=self.analysis, created_by=self.user, summary="Second")
        self.analysis.refresh_from_db()
        self.assertEqual((first.version, second.version, self.analysis.current_version), (1, 2, 2))
        self.assertEqual(list(self.analysis.revisions.values_list("version", flat=True)), [2, 1])

    def test_existing_revision_immutable(self):
        revision = create_analysis_revision(analysis=self.analysis, created_by=self.user, summary="Original")
        revision.summary = "Modified"
        with self.assertRaises(ValidationError):
            revision.save()
        revision.refresh_from_db()
        self.assertEqual(revision.summary, "Original")

    def test_existing_revision_cannot_be_overwritten_by_new_instance(self):
        revision = create_analysis_revision(analysis=self.analysis, created_by=self.user)
        with self.assertRaises(ValidationError):
            AnalysisRevision(id=revision.pk, analysis=self.analysis, version=1, created_by=self.user).save()

    def test_direct_revision_creation_updates_current_version(self):
        AnalysisRevision.objects.create(analysis=self.analysis, version=3, created_by=self.user)
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.current_version, 3)
        revision = create_analysis_revision(analysis=self.analysis, created_by=self.user)
        self.assertEqual(revision.version, 4)

    def test_revision_version_unique(self):
        create_analysis_revision(analysis=self.analysis, created_by=self.user)
        with self.assertRaises(ValidationError):
            AnalysisRevision.objects.create(analysis=self.analysis, version=1, created_by=self.user)

    def test_revision_failure_rolls_back_version(self):
        create_analysis_revision(analysis=self.analysis, created_by=self.user)
        with self.assertRaises(IntegrityError):
            create_analysis_revision(analysis=self.analysis, created_by=self.user, summary="x", recommendations=None)
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.current_version, 1)
        self.assertEqual(self.analysis.revisions.count(), 1)
        revision = create_analysis_revision(analysis=self.analysis, created_by=self.user)
        self.assertEqual(revision.version, 2)

    def test_report_revision_must_match_batch(self):
        revision = create_analysis_revision(analysis=self.analysis, created_by=self.user)
        batch = SampleBatch.objects.create(farm=self.farm, title="Other", collected_at=date(2026, 10, 2), created_by=self.user)
        with self.assertRaises(ValidationError):
            Report.objects.create(batch=batch, analysis_revision=revision, title="Report", created_by=self.user)

    def test_multiple_analyses_and_reports_allowed(self):
        Analysis.objects.create(batch=self.batch, created_by=self.user)
        revision = create_analysis_revision(analysis=self.analysis, created_by=self.user)
        for title in ("First report", "Second report"):
            Report.objects.create(batch=self.batch, analysis_revision=revision, title=title, created_by=self.user)
        self.assertEqual(self.batch.analyses.count(), 2)
        self.assertEqual(self.batch.reports.count(), 2)

    def test_report_preserves_specific_revision(self):
        first = create_analysis_revision(analysis=self.analysis, created_by=self.user)
        report = Report.objects.create(batch=self.batch, analysis_revision=first, title="Report", created_by=self.user)
        create_analysis_revision(analysis=self.analysis, created_by=self.user)
        report.refresh_from_db()
        self.assertEqual(report.analysis_revision.version, 1)
        with self.assertRaises(ProtectedError):
            first.delete()

    def test_farm_with_history_deletion_protected(self):
        with self.assertRaises(ProtectedError):
            self.farm.delete()

    def test_batch_with_analysis_deletion_protected(self):
        with self.assertRaises(ProtectedError):
            self.batch.delete()
