import datetime
from calendar import monthrange
from collections import defaultdict, Counter

import pandas as pd
from bokeh.io import export_png, export_svgs

from .collect import CostManager
from .charts.create import create_daily_chart_image


SUPPORTED_IMAGE_FORMATS = (
    '.png',
    '.svg',
)


class ImageFormatError(ValueError):
    pass


def datestr2datetime(date_str):
    return datetime.datetime.strptime(date_str, '%Y-%m-%d')


def format_to_dataframe(aws_cost_explorer_data, target_month_start: datetime.date=None):
    if not target_month_start:
        target_month_start = datetime.datetime.utcnow().replace(day=1)

    assert target_month_start.day == 1
    previous_month_start = (target_month_start - datetime.timedelta(days=1)).replace(day=1)
    last_day_of_month = monthrange(target_month_start.year, target_month_start.month)[-1]
    target_month_end = target_month_start.replace(day=last_day_of_month)

    # create monthly
    monthly_account_daily_cost_data = defaultdict(list)

    account_index = 0
    accounts = set([c['Keys'][account_index] for c in sum([record['Groups'] for record in aws_cost_explorer_data['ResultsByTime']], [])])

    account_totals = Counter()
    for record in aws_cost_explorer_data['ResultsByTime']:
        start = datestr2datetime(record['TimePeriod']['Start'])
        end = datestr2datetime(record['TimePeriod']['End'])
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
    df = df.fillna(0.0)
    ix = pd.DatetimeIndex(start=previous_month_start.date(), end=target_month_end.date(), freq='D')
    df = df.reindex(ix)

    df[df.index < pd.to_datetime(target_month_start.date())].sum(axis=1)
    previous_month_df = df[df.index < pd.to_datetime(target_month_start.date())].sum(axis=1)
    previous_month_df.index = previous_month_df.index + pd.DateOffset(months=1)
    previous_month_df = previous_month_df.rename('previous_month_cost')

    df = pd.concat([df, previous_month_df])
    df['previous_month_total'] = df[0]
    df = df.drop([0], axis=1)
    df.index.name = 'date'
    return df


def prepare_daily_chart_figure(current_datetime: datetime.datetime=None, accountid_mapping: dict=None):
    if not current_datetime:
        current_datetime = datetime.datetime.now()
    end = current_datetime.date()

    current_month_start = datetime.date(end.year, end.month, 1)
    previous_month_start = (current_month_start.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)

    # get full data from previous month in order to compare current with previous
    manager = CostManager()
    result = manager.collect(previous_month_start, end)
    df = format_to_dataframe(result)
    current_month_df = df[df.index >= pd.to_datetime(current_month_start)]
    chart_figure = create_daily_chart_image(current_month_df, accountid_mapping)
    return chart_figure


def generate_daily_chart_image(chart_figure, filename=None, image_format: str='.png'):
    if image_format not in SUPPORTED_IMAGE_FORMATS:
        raise ImageFormatError(f'"{image_format}" not in SUPPORTED_IMAGE_FORMATS: {SUPPORTED_IMAGE_FORMATS}')

    if not filename:
        filename = 'output.png'

    if image_format == '.png':
        export_png(chart_figure, filename)
    elif image_format == '.svg':
        export_svgs(chart_figure, filename)
    return filename




