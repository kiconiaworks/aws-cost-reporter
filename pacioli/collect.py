import boto3
import json
import datetime


class CostManager:

    def __init__(self):
        self.ce_client = boto3.client('ce')

    def collect(self, start: datetime.date, end: datetime.date, granularity='DAILY'):
        response = self.ce_client.get_cost_and_usage(TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                                                     Granularity=granularity,
                                                     GroupBy=[
                                                         {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'},
                                                         {'Type': 'DIMENSION', 'Key': 'SERVICE'}
                                                     ],
                                                     Metrics=["BlendedCost", "UnblendedCost", "UsageQuantity"])
        return response
