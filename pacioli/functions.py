"""
Contains main functions for performing collection and generation of charts for posting to slack
"""
import datetime
from io import BytesIO
from calendar import monthrange
from typing import Tuple, Optional

import pandas as pd
from bokeh.io.export import get_screenshot_as_png

from .collect import CostManager
from .charts.create import create_daily_chart_figure, create_cost_ratio_pi_chart, figure


SUPPORTED_IMAGE_FORMATS = (
    '.png',
)


class ImageFormatError(ValueError):
    """Exception used when an unsupported Image format is used/given"""
    pass


def datestr2datetime(date_str) -> datetime.datetime:
    """Convert YYYY-MM-DD to a python datetime object"""
    return datetime.datetime.strptime(date_str, '%Y-%m-%d')


def format_to_dataframe(aws_cost_explorer_data: dict) -> pd.DataFrame:
    aws_cost_explorer_data_result = {
        'date': [],
        'group1': [],
        'group2': [],
        'cost': [],
    }
    for record in aws_cost_explorer_data['ResultsByTime']:
        start = datestr2datetime(record['TimePeriod']['Start'])

        for cost_group in record['Groups']:
            group1, group2 = cost_group['Keys']
            cost = float(cost_group['Metrics']['UnblendedCost']['Amount'])

            aws_cost_explorer_data_result['date'].append(start.date())
            aws_cost_explorer_data_result['group1'].append(group1)
            aws_cost_explorer_data_result['group2'].append(group2)
            aws_cost_explorer_data_result['cost'].append(cost)

    df = pd.DataFrame.from_dict(aws_cost_explorer_data_result)
    df.date = pd.to_datetime(df.date)

    return df


def group_by_cost_cumsum(df: pd.DataFrame) -> pd.DataFrame:
    def groupby_total(group_df):
        return group_df.groupby(['group1', 'group2']).sum()

    def groupby_separate_columns(group_df):
        columns = []
        for _, row in group_df.iterrows():
            assert row["group1"] or row["group2"], "group1, group2両方値が入っていません"

            if row["group1"] and row["group2"]:
                columns.append(f"{row['group1']}/{row['group2']}")
            elif row["group1"] and (not row["group2"]):
                columns.append(row['group1'])
            elif (not row["group1"]) and row["group2"]:
                columns.append(row['group2'])
        costs = [row['cost'] for _, row in group_df.iterrows()]

        s = pd.Series({key: value for key, value in zip(columns, costs)})

        return pd.DataFrame(s).T

    df["date"] = pd.to_datetime(df["date"])

    df = df.groupby('date').apply(groupby_total)
    df = df.reset_index()
    df = df.groupby('date').apply(groupby_separate_columns)
    df = df.reset_index().drop(columns=["level_1"])

    df["Month"] = df["date"].apply(lambda x: x.month)
    df = df.set_index('date')
    df.sort_index(inplace=True)
    df = df.fillna(0.0)
    df.index.name = 'date'

    return df.groupby('Month').cumsum()


def add_previous_month_cost_diff(df: pd.DataFrame,
                                 target_month_start: Optional[datetime.datetime] = None) -> pd.DataFrame:
    if not target_month_start:
        target_month_start = datetime.datetime.utcnow().replace(day=1)

    assert target_month_start.day == 1
    previous_month_start = (target_month_start - datetime.timedelta(days=1)).replace(day=1)
    previous_month_end_day = monthrange(previous_month_start.year, previous_month_start.month)[-1]
    last_day_of_month = monthrange(target_month_start.year, target_month_start.month)[-1]
    target_month_end = target_month_start.replace(day=last_day_of_month)

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

    df = format_to_dataframe(result)
    df["group2"] = ""  # Accountのみで集計する
    df = group_by_cost_cumsum(df)
    df = add_previous_month_cost_diff(df)

    chart_figure, current_cost, previous_cost = create_daily_chart_figure(df, accountid_mapping)
    return chart_figure, current_cost, previous_cost


def prepare_daily_pie_chart_figure(current_datetime: Optional[datetime.datetime] = None) -> figure:
    """
    Gathers required Cost Data, and builds chart figure

    :param current_datetime: Datetime for the day to calculate the cost for
    """
    end, current_month_start, previous_month_start = _get_month_starts(current_datetime)

    # get full data from previous month in order to compare current with previous
    manager = CostManager()
    result = manager.collect_account_group_account_project(previous_month_start, end)

    df = format_to_dataframe(result)
    df.loc[df["group1"] == "ProjectId$", "group1"] = "nothing_project_tag"
    df = group_by_cost_cumsum(df)
    df = add_previous_month_cost_diff(df)

    chart_figure = create_cost_ratio_pi_chart(df)
    return chart_figure


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
