"""Daily patient grouping and existing invoice reconciliation."""
import os
import sys
from pathlib import Path
from datetime import date, datetime
import unittest
import ast
from fastapi import HTTPException

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@127.0.0.1:1/emr_test')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.models
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models.patient import Patient, Appointment, AppointmentTypeConfig
from app.models.lab_result import LabResult, LabCatalog
from app.models.clinical import Invoice, InvoiceItem
from app.services.daily_billing import daily_suggestions


class DailyBillingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.day = date(2026, 10, 3)
        self.db.add_all([Patient(id=1, first_name='Test', last_name='Patient'),
            AppointmentTypeConfig(id=1, name='General', rate=300),
            Appointment(id=1, patient_id=1, appointment_type_id=1, status='Completed', appointment_time=datetime(2026, 10, 3, 10)),
            LabCatalog(id=1, name='CBC', price=200),
            LabResult(patient_id=1, catalog_id=1, test_name='CBC', status='Pending', ordered_date=datetime(2026, 10, 3, 11))])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def bill(self, names, status='Pending', **kwargs):
        invoice = Invoice(patient_id=1, amount=300, status=status, created_at=datetime(2026, 10, 3, 12), **kwargs)
        invoice.items = [InvoiceItem(service_name=n, quantity=1, unit_price=300) for n in names]
        self.db.add(invoice)
        self.db.commit()

    def test_consultation_and_labs_group_into_one_patient_day(self):
        rows = daily_suggestions(self.db, self.day)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['total_amount'], 500)
        self.assertEqual(len(rows[0]['items']), 2)
        self.assertEqual(daily_suggestions(self.db, date(2026, 10, 4)), [])

    def test_existing_consultation_bill_leaves_only_lab(self):
        self.bill(['Consultation (General)'])
        row = daily_suggestions(self.db, self.day)[0]
        self.assertEqual(row['total_amount'], 200)
        self.assertEqual(row['status'], 'Partially billed')
        self.assertEqual(row['unbilled_items'][0]['service_name'], 'Lab Test: CBC')

    def test_paid_and_pending_invoices_both_count(self):
        self.bill(['Consultation (General)'], status='Paid')
        self.bill(['Lab Test: CBC'])
        row = daily_suggestions(self.db, self.day)[0]
        self.assertEqual(row['status'], 'Already billed')
        self.assertEqual(row['total_amount'], 0)

    def test_cancelled_invoice_does_not_hide_services(self):
        self.bill(['Consultation (General)'], status='Cancelled')
        self.assertEqual(daily_suggestions(self.db, self.day)[0]['total_amount'], 500)

    def test_legacy_bill_without_items_requires_review(self):
        self.bill([])
        self.assertTrue(daily_suggestions(self.db, self.day)[0]['needs_review'])

    def test_service_date_reconciles_bill_created_later(self):
        self.bill(['Consultation (General)', 'Lab Test: CBC'], service_date=self.day)
        self.db.query(Invoice).update({'created_at': datetime(2026, 10, 5, 12)})
        self.db.commit()
        self.assertEqual(daily_suggestions(self.db, self.day)[0]['total_amount'], 0)

    def test_scheduled_and_cancelled_consultations_are_excluded(self):
        self.db.query(Appointment).update({'status': 'Scheduled'})
        self.db.commit()
        self.assertEqual(daily_suggestions(self.db, self.day)[0]['total_amount'], 200)

    def test_generate_rechecks_and_rejects_duplicate_bill(self):
        path = Path(__file__).resolve().parents[1] / 'app/api/billing.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        node = next(n for n in tree.body if getattr(n, 'name', '') == 'create_daily_suggestion_invoice')
        node.decorator_list = []
        # Evaluate the endpoint body without app authentication setup.
        node.args.defaults = []
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
        namespace = {'Invoice': Invoice, 'InvoiceItem': InvoiceItem, 'HTTPException': HTTPException}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        generate = namespace['create_daily_suggestion_invoice']
        invoice = generate(1, self.day, self.db)
        self.assertEqual(invoice.amount, 500)
        self.assertEqual(len(invoice.items), 2)
        with self.assertRaises(HTTPException) as error:
            generate(1, self.day, self.db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.query(Invoice).count(), 1)

if __name__ == '__main__':
    unittest.main()
