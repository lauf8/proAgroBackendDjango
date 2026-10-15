from datetime import date

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import FarmMembership, User
from laboratory.models import Analysis, Microorganism, Report, Sample, SampleBatch, SampleResult
from laboratory.services import create_analysis_revision
from manage.models import Cow, Farm


class LaboratoryAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin@lab.test', 'Password123!', name='Admin')
        cls.member = User.objects.create_user('member@lab.test', name='Member', is_staff=True)
        cls.farm = Farm.objects.create(name='Farm')
        cls.membership = FarmMembership.objects.create(farm=cls.farm, user=cls.member, role='owner')
        cls.records = cls.make_records(cls.farm, 'Own')
        cls.other_records = cls.make_records(Farm.objects.create(name='Other'), 'Other')

    @classmethod
    def make_records(cls, farm, label):
        cow = Cow.objects.create(farm=farm, name=label, identifier=label)
        batch = SampleBatch.objects.create(farm=farm, title=label, collected_at=date(2026, 10, 1), created_by=cls.admin)
        sample = Sample.objects.create(batch=batch, cow=cow, udder_quarter='composite', sample_code=label)
        organism = Microorganism.objects.create(name=label)
        result = SampleResult.objects.create(sample=sample, microorganism=organism, result_type='positive')
        analysis = Analysis.objects.create(batch=batch, created_by=cls.admin)
        revision = create_analysis_revision(analysis=analysis, created_by=cls.admin)
        report = Report.objects.create(batch=batch, analysis_revision=revision, title=label, created_by=cls.admin)
        return dict(zip(('microorganisms', 'sample_batches', 'samples', 'sample_results', 'analyses', 'analysis_revisions', 'reports'), (organism, batch, sample, result, analysis, revision, report)))

    def url(self, resource, record=None):
        return reverse(f'laboratory:{resource}_{"detail" if record else "list_create"}', kwargs={'pk': record.pk} if record else {})

    def test_member_scope_and_write_prohibition_for_every_model(self):
        self.client.force_authenticate(self.member)
        for resource, record in self.records.items():
            with self.subTest(resource=resource):
                response = self.client.get(self.url(resource))
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row['id'] for row in response.data['results']], [] if resource == 'reports' else [str(record.pk)])
                self.assertEqual(self.client.get(self.url(resource, record)).status_code, 404 if resource == 'reports' else 200)
                self.assertEqual(self.client.get(self.url(resource, self.other_records[resource])).status_code, 404)
                self.assertEqual(self.client.post(self.url(resource), {}, format='json').status_code, 403)
                for method in ('put', 'patch', 'delete'):
                    self.assertEqual(getattr(self.client, method)(self.url(resource, record), {}, format='json').status_code, 403)

    def test_inactive_membership_and_anonymous_access(self):
        self.membership.is_active = False
        self.membership.save()
        self.client.force_authenticate(self.member)
        for resource in self.records:
            self.assertEqual(self.client.get(self.url(resource)).data['count'], 0)
        self.client.force_authenticate(None)
        for resource in self.records:
            self.assertEqual(self.client.get(self.url(resource)).status_code, 401)

    def test_superuser_create_update_and_delete_every_model(self):
        self.client.force_authenticate(self.admin)
        payloads = {
            'microorganisms': {'name': 'New'},
            'sample_batches': {'farm': str(self.farm.pk), 'title': 'New', 'collected_at': '2026-10-02'},
            'samples': {'batch': str(self.records['sample_batches'].pk), 'cow': str(self.records['samples'].cow_id), 'udder_quarter': 'left_front', 'sample_code': 'New'},
            'sample_results': {'sample': str(self.records['samples'].pk), 'result_type': 'negative'},
            'analyses': {'batch': str(self.records['sample_batches'].pk)},
            'analysis_revisions': {'analysis': str(self.records['analyses'].pk), 'summary': 'New'},
        }
        payloads['reports'] = {'batch': str(self.records['sample_batches'].pk), 'analysis_revision': str(self.records['analysis_revisions'].pk), 'title': 'New'}
        edits = {'microorganisms': {'description': 'Edited'}, 'sample_batches': {'title': 'Edited'}, 'samples': {'notes': 'Edited'}, 'sample_results': {'notes': 'Edited'}, 'analyses': {'status': 'under_review'}, 'analysis_revisions': {'summary': 'Edited'}, 'reports': {'title': 'Edited'}}
        for resource, payload in payloads.items():
            with self.subTest(resource=resource):
                self.assertEqual(self.client.get(self.url(resource)).data['count'], 2)
                response = self.client.post(self.url(resource), payload, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                url = reverse(f'laboratory:{resource}_detail', kwargs={'pk': response.data['id']})
                edited = self.client.patch(url, edits[resource], format='json')
                self.assertEqual(edited.status_code, 200, edited.data)
                if resource == 'analysis_revisions':
                    self.assertNotEqual(edited.data['id'], response.data['id'])
                    self.assertEqual(self.client.get(url).data['summary'], 'New')
                    self.client.delete(reverse('laboratory:analysis_revisions_detail', kwargs={'pk': edited.data['id']}))
                self.assertEqual(self.client.delete(url).status_code, 405 if resource == 'reports' else 204)

    def test_validation_and_protected_deletion(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(self.url('samples', self.records['samples']), {'cow': str(self.other_records['samples'].cow_id)}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete(self.url('sample_batches', self.records['sample_batches'])).status_code, 409)
        response = self.client.patch(self.url('reports', self.records['reports']), {'analysis_revision': str(self.other_records['analysis_revisions'].pk)}, format='json')
        self.assertEqual(response.status_code, 400)
