import datetime
import logging
import sys
import unittest
from unittest import mock

from pacioli import settings
from pacioli.managers import ReportManager

from .utils import (
    mock_collect_groupby_linkedaccount,
    mock_collect_groupby_linkedaccount_firstdayofmonth,
    mock_collect_groupbytag_projectid,
    mock_collect_groupbytag_projectid_missing_latest,
    mock_collect_groupbytag_projectid_services__single_day,
)

logging.basicConfig(stream=sys.stdout, level=settings.LOG_LEVEL, format="%(asctime)s [%(levelname)s] (%(name)s) %(funcName)s: %(message)s")


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
        account_info = result[0]
        expected = "000000000001"
        actual = account_info.id
        self.assertEqual(actual, expected)

        expected_previous_cost = 133.9837960763  # previous_cost - sum of 10/1 ~ 10/14
        actual = account_info.previous_cost
        self.assertEqual(actual, expected_previous_cost)

        expected_current_cost = 122.09420959270001  # current_cost - sum of 11/1 ~ 11/14
        actual = account_info.current_cost
        self.assertEqual(actual, expected_current_cost)

        expected_change_percentage = round((expected_current_cost / expected_previous_cost - 1.0) * 100, 1)
        actual = account_info.percentage_change
        self.assertEqual(actual, expected_change_percentage)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupby_linkedaccount_firstdayofmonth())
    def test_generate_accounts_report__firstdayofmonth(self, *_):
        now = datetime.datetime(2022, 11, 1, tzinfo=datetime.timezone.utc)
        rm = ReportManager(generation_datetime=now)
        result = rm.generate_accounts_report()
        self.assertTrue(result)
        expected = 1
        actual = len(result)
        self.assertEqual(actual, expected)
        account_info = result[0]
        expected = "000000000001"
        actual = account_info.id
        self.assertEqual(actual, expected)

        expected_previous_cost = 28.5091132123  # previous_cost - sum of 10/1 ~ 10/2
        actual = account_info.previous_cost
        self.assertEqual(actual, expected_previous_cost)

        expected_current_cost = 20.6452918442  # current_cost - sum of 11/1 ~ 11/2
        actual = account_info.current_cost
        self.assertEqual(actual, expected_current_cost)

        expected_change_percentage = round((expected_current_cost / expected_previous_cost - 1.0) * 100, 1)
        actual = account_info.percentage_change
        self.assertEqual(actual, expected_change_percentage)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid())
    def test_generate_projectid_report(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        rm = ReportManager(generation_datetime=now)
        results = rm.generate_projectid_report()
        self.assertTrue(results)

        sample_project_id = "2daec5cf-78b5-4cdc-96be-06b7cefb6eb1"
        # get sample project_id's project_info
        sample_project_info = None
        for project_info in results:
            if project_info.id == sample_project_id:
                sample_project_info = project_info
                break
        assert sample_project_info
        expected_previous_cost = 45.67802501799999  # previous_cost - sum of 10/1 ~ 10/14
        actual = sample_project_info.previous_cost
        self.assertEqual(actual, expected_previous_cost)

        expected_current_cost = 45.6953553543  # current_cost - sum of 11/1 ~ 11/14
        actual = sample_project_info.current_cost
        self.assertEqual(actual, expected_current_cost)

        expected_change_percentage = round((expected_current_cost / expected_previous_cost - 1.0) * 100, 1)
        actual = sample_project_info.percentage_change
        self.assertEqual(actual, expected_change_percentage)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid_missing_latest())
    def test_generate_projectid_report_no_latest(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        rm = ReportManager(generation_datetime=now)
        results = rm.generate_projectid_report()
        self.assertTrue(results)

        sample_project_id = "2daec5cf-78b5-4cdc-96be-06b7cefb6eb1"
        # get sample project_id's project_info
        sample_project_info = None
        for project_info in results:
            if project_info.id == sample_project_id:
                sample_project_info = project_info
                break
        assert sample_project_info
        expected_previous_cost = 45.67802501799999  # previous_cost - sum of 10/1 ~ 10/14
        actual = sample_project_info.previous_cost
        self.assertEqual(actual, expected_previous_cost)

        expected_current_cost = 45.6953553543  # current_cost - sum of 11/1 ~ 11/14
        actual = sample_project_info.current_cost
        self.assertEqual(actual, expected_current_cost)

        expected_change_percentage = round((expected_current_cost / expected_previous_cost - 1.0) * 100, 1)
        actual = sample_project_info.percentage_change
        self.assertEqual(actual, expected_change_percentage)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid_services__single_day())
    def test_generate_projectid_itemized_report(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        rm = ReportManager(generation_datetime=now)
        result = rm.generate_projectid_itemized_report()
        self.assertTrue(result)
