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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()

    end = datetime.datetime.now().date()
    current_month_start = datetime.date(end.year, end.month, 1)
    previous_month_start = (current_month_start.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    manager = CostManager()
    print(f'Collected data for: {previous_month_start} - {end}')
    r = manager.collect(previous_month_start, end)
    filename = f'cost-manager-collect.{end.strftime("%Y%m%d%H")}.json'
    print(f'Writing ({filename})...')
    with open(filename, 'w', encoding='utf8') as json_out:
        json_out.write(json.dumps(r, indent=4))
    print('Done!')
