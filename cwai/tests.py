from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import Evaluation
from .views import _calculate_rows


class EmissionCalculationTests(TestCase):
    def test_direct_emissions_are_converted_and_aggregated_by_scope(self):
        totals, rows, issues = _calculate_rows([
            {"Activity": "Electricity", "CO2e Emissions": 420.5, "Scope": "2"},
            {"Activity": "Company Vehicles", "Emissions": 185.2, "Scope": "1"},
        ])
        self.assertAlmostEqual(totals["scope2"], 0.4205)
        self.assertAlmostEqual(totals["scope1"], 0.1852)
        self.assertAlmostEqual(sum(totals.values()), 0.6057)
        self.assertEqual(len(rows), 2)
        self.assertEqual(issues, [])

    def test_quantity_times_factor_and_validation(self):
        totals, rows, issues = _calculate_rows([
            {"Activity": "Purchased goods", "Quantity": 2, "Unit": "kg", "Emission factor": 1.5},
            {"Activity": "Unknown", "Quantity": -1, "Emission factor": 4},
        ])
        self.assertEqual(totals["scope3"], 0.003)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(issues), 1)

    def test_evaluation_records_are_user_scoped(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username="analyst", password="a-long-test-password")
        evaluation = Evaluation.objects.create(user=user, filename="activities.csv", expected_emission=2, total_emission=1, rows=[])
        self.assertEqual(Evaluation.objects.filter(user=user, pk=evaluation.pk).count(), 1)

    def test_upload_results_and_report_flow(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username="reporter", password="a-long-test-password")
        self.client.force_login(user)
        response = self.client.get("/home/")
        self.assertEqual(response.status_code, 200)
        upload = SimpleUploadedFile(
            "activities.csv",
            b"Activity,Emissions,Scope\nElectricity,500,2\n",
            content_type="text/csv",
        )
        response = self.client.post("/analyze/", {"excel_file": upload, "expected_emission": "1.0"})
        self.assertEqual(response.status_code, 302)
        results = self.client.get("/results/")
        self.assertEqual(results.status_code, 200)
        self.assertContains(results, "0.5")
        evaluation = Evaluation.objects.get(user=user)
        report = self.client.get(f"/reports/{evaluation.pk}.csv")
        self.assertEqual(report.status_code, 200)
        self.assertIn(b"Scope 2,0.5", report.content)
