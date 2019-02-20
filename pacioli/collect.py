"""
Key class for interfacing with and obtaining data from the AWS CostExplorer API
"""
import boto3
import datetime


class CostManager:
    """
    Class intended to manage desired CostExplorer ('ce') operations
    """

    def __init__(self):
        self.ce_client = boto3.client('ce')

    def collect_account_basic_account_metrics(self, start: datetime.date, end: datetime.date, granularity='DAILY'):
        """
        Collect basic account cost metrics
        """
        response = self.ce_client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity=granularity,
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'},
                {'Type': 'DIMENSION', 'Key': 'SERVICE'}
            ],
            Metrics=["BlendedCost", "UnblendedCost", "UsageQuantity"]
        )
        return response
