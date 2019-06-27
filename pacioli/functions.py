"""
Contains main functions for performing collection and generation of charts for posting to slack
"""
import datetime
from io import BytesIO
from calendar import monthrange
from collections import defaultdict, Counter
from typing import Tuple, Optional

import pandas as pd
from bokeh.io.export import get_screenshot_as_png

from .collect import CostManager
from .charts.create import create_daily_chart_figure, figure


SUPPORTED_IMAGE_FORMATS = (
    '.png',
)


class ImageFormatError(ValueError):
    """Exception used when an unsupported Image format is used/given"""
    pass


def datestr2datetime(date_str) -> datetime.datetime:
    """Convert YYYY-MM-DD to a python datetime object"""
    return datetime.datetime.strptime(date_str, '%Y-%m-%d')


def format_to_dataframe(aws_cost_explorer_data, target_month_start: Optional[datetime.datetime] = None) -> pd.DataFrame:
    """
    Convert the AWS Cost explorer JSON data to a pandas Dataframe
    """
    if not target_month_start:
        target_month_start = datetime.datetime.utcnow().replace(day=1)

    assert target_month_start.day == 1
    previous_month_start = (target_month_start - datetime.timedelta(days=1)).replace(day=1)
    previous_month_end_day = monthrange(previous_month_start.year, previous_month_start.month)[-1]
    last_day_of_month = monthrange(target_month_start.year, target_month_start.month)[-1]
    target_month_end = target_month_start.replace(day=last_day_of_month)

    # create monthly
    monthly_account_daily_cost_data = defaultdict(list)

    account_index = 0
    accounts = set([c['Keys'][account_index] for c in sum([record['Groups'] for record in aws_cost_explorer_data['ResultsByTime']], [])])

    account_totals = Counter()
    for record in aws_cost_explorer_data['ResultsByTime']:
        start = datestr2datetime(record['TimePeriod']['Start'])
        if start.day == 1:
            account_totals = Counter()
        monthly_account_daily_cost_data['date'].append(start.date())

        for cost_group in record['Groups']:
            account, cost_category = cost_group['Keys']
            cost = float(cost_group['Metrics']['UnblendedCost']['Amount'])
            account_totals[account] += cost
        for account in accounts:
            total = account_totals.get(account, 0.0)
            monthly_account_daily_cost_data[account].append(total)

    df = pd.DataFrame.from_dict(monthly_account_daily_cost_data)
    df.date = pd.to_datetime(df.date)

    df = df.set_index('date')
    df.sort_index(inplace=True)
    df.index = pd.to_datetime(df.index, '%Y-%m-%d')
    df = df.fillna(0.0)
    df.index.name = 'date'

    previous_month_series = df[df.index < pd.to_datetime(target_month_start.date())].sum(axis=1)
    previous_month_series.index = previous_month_series.index.shift(periods=previous_month_end_day, freq='D')
    previous_month_series = previous_month_series.rename('previous_month_total')

    df['previous_month_total'] = previous_month_series
    df['previous_month_total'].fillna(0.0)

    # remove dates not in the current target_month
    df_target_month_only = df.loc[(df.index >= target_month_start) & (df.index < target_month_end)]
    return df_target_month_only


def _get_month_starts(current_datetime: Optional[datetime.datetime] = None) -> Tuple[datetime.date, datetime.date, datetime.date]:
    """
    Calculate the `current` month start date and `previous` month start date from the given current datetime object
    """
    if not current_datetime:
        current_datetime = datetime.datetime.now()
    end_date = current_datetime.date()

    current_month_start = datetime.date(end_date.year, end_date.month, 1)
    previous_month_start = (current_month_start.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    return end_date, current_month_start, previous_month_start


def prepare_daily_chart_figure(
        current_datetime: Optional[datetime.datetime] = None,
        accountid_mapping: Optional[dict] = None) -> Tuple[figure, float, float]:
    """
    Gathers required Cost Data, and builds chart figure

    :param current_datetime: Datetime for the day to calculate the cost for
    :param accountid_mapping: If given, output will
    """
    end, current_month_start, previous_month_start = _get_month_starts(current_datetime)

    # get full data from previous month in order to compare current with previous
    manager = CostManager()
    result = manager.collect_account_basic_account_metrics(previous_month_start, end)
    current_month_df = format_to_dataframe(result)
    chart_figure, current_cost, previous_cost = create_daily_chart_figure(current_month_df, accountid_mapping)
    return chart_figure, current_cost, previous_cost


def generate_daily_chart_image(chart_figure, image_format: str = '.png') -> BytesIO:
    """
    Write the given chart to the descired image format into a BytesIO() object
    """
    if image_format not in SUPPORTED_IMAGE_FORMATS:
        raise ImageFormatError(f'"{image_format}" not in SUPPORTED_IMAGE_FORMATS: {SUPPORTED_IMAGE_FORMATS}')

    buffer = BytesIO()
    if image_format == '.png':
        image = get_screenshot_as_png(chart_figure)
        image.save(buffer, format='png')
        buffer.seek(0)
    return buffer
