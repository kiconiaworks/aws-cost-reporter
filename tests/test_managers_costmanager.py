import datetime
import unittest
from unittest import mock

from pacioli.managers import CostManager

from .utils import (
    mock_collect_groupby_linkedaccount,
    mock_collect_groupby_resoucetype,
    mock_collect_groupbytag_projectid,
    mock_collect_groupbytag_projectid_services,
)


class CostManagerTestCase(unittest.TestCase):
    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid())
    def test_get_projectid_totals(self, *_):
        cm = CostManager()
        start = datetime.datetime.now()
        end = datetime.datetime.now()
        result = cm.get_projectid_totals(start, end)
        self.assertTrue(result)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupby_resoucetype())
    def test_get_period_total_tax(self, *_):
        cm = CostManager()
        start = datetime.datetime.now()
        end = datetime.datetime.now()
        result = cm.get_period_total_tax(start, end)
        self.assertTrue(result)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid_services())
    def test_get_projectid_itemized_totals(self, *_):
        cm = CostManager()
        start = datetime.datetime.now()
        end = datetime.datetime.now()
        result = cm.get_projectid_itemized_totals(start, end)
        self.assertTrue(result)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupby_linkedaccount())
    def test_get_account_totals(self, *_):
        cm = CostManager()
        start = datetime.datetime.now()
        end = datetime.datetime.now()
        result = cm.get_account_totals(start, end)
        self.assertTrue(result)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupby_linkedaccount())
    def test_get_change_in_accounts(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        cm = CostManager()
        result = cm.get_change_in_accounts(now=now)
        self.assertTrue(result)

    @mock.patch("pacioli.aws.CE_CLIENT.get_cost_and_usage", return_value=mock_collect_groupbytag_projectid())
    def test_get_change_in_projects(self, *_):
        now = datetime.datetime(2022, 11, 15, tzinfo=datetime.timezone.utc)
        cm = CostManager()
        result = cm.get_change_in_projects(now=now)
        self.assertTrue(result)
