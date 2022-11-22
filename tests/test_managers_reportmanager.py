import datetime
import unittest
from unittest import mock

from pacioli.managers import ReportManager

from .utils import mock_collect_groupby_linkedaccount, mock_collect_groupbytag_projectid, mock_collect_groupbytag_projectid_services__single_day


class ReportManagerTestCase(unittest.TestCase):
    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupby_linkedaccount())
    def test_generate_accounts_report(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        rm = ReportManager(generation_datetime=now)
        result = rm.generate_accounts_report()
        self.assertTrue(result)
        expected = 1
        actual = len(result)
        self.assertEqual(actual, expected)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid())
    def test_generate_projectid_report(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        rm = ReportManager(generation_datetime=now)
        result = rm.generate_projectid_report()
        self.assertTrue(result)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid_services__single_day())
    def test_generate_projectid_itemized_report(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        rm = ReportManager(generation_datetime=now)
        result = rm.generate_projectid_itemized_report()
        self.assertTrue(result)
