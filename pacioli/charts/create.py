"""
Functions for building bokeh figure objects from dataframes.
"""
import datetime
import logging
import math
from typing import Optional, Tuple, Union

import numpy as np
import pandas as pd
from bokeh.layouts import Column, Row, gridplot
from bokeh.models import ColumnDataSource, LabelSet, Legend, LegendItem
from bokeh.palettes import brewer, magma
from bokeh.plotting import figure
from bokeh.transform import cumsum

logger = logging.getLogger(__name__)


def create_daily_chart_figure(current_month_df: pd.DataFrame, accountid_mapping: Optional[dict] = None) -> Tuple[figure, float, float]:
    """
    Create a cumulative stacked line graph of given AWS accounts.
    :param current_month_df: Dataframe containing the current and previous month data
    :param accountid_mapping: AccountID to display name mapping for figure labels
    """
    # get max record date (assumes values will NOT decrease)
    accountids = [i for i in current_month_df.columns if i.isdigit()]

    # dates are same for all accounts
    # - take a sample to discover the 'last_available_date'
    sample_accountid = accountids[0]
    account_max_value = current_month_df[[sample_accountid]].max()[0]
    if np.isnan(account_max_value):
        logger.error(f"No data for sample_accountid={sample_accountid}")
    last_available_date = current_month_df[current_month_df[sample_accountid] == account_max_value].index.date[0]

    current_cost = float(current_month_df[accountids].max().sum())
    previous_cost = float(current_month_df.loc[last_available_date]["previous_month_total"])
    percentage_change = round((current_cost / previous_cost - 1.0) * 100, 1)

    source = ColumnDataSource(current_month_df)

    today = datetime.datetime.utcnow()
    previous_day = today - datetime.timedelta(days=2)
    today_display_str = today.strftime("%Y-%m-%d")
    f = figure(
        title=f"AWS Cost ({today_display_str} UTC) ${round(current_cost, 2)} ({percentage_change}%)",
        x_axis_type="datetime",
        x_axis_label="Date",
        y_axis_label="Cost ($)",
        plot_width=800,
        plot_height=350,
    )
    f.title.text_font_size = "14pt"
    f.line("date", "previous_month_total", source=source, line_color="gray", line_dash="dashed")

    def stacked(df):
        df_top = df.cumsum(axis=1)
        df_bottom = df_top.shift(axis=1)[::-1]

        df_stack = pd.concat([df_bottom, df_top], ignore_index=True)
        return df_stack

    current_month_previous_removed = current_month_df.drop(["previous_month_total"], axis=1)

    areas = stacked(current_month_previous_removed)
    areas = areas.fillna(0.0)
    number_of_areas = areas.shape[1]

    # Get colors to use for Areas in chart
    # https://bokeh.pydata.org/en/latest/docs/reference/palettes.html#brewer-palettes
    # - minimum colors is 3 for a given palette, support case where only 1, or 2 colors are needed
    palette_min_colors = 3
    if number_of_areas < palette_min_colors:
        colors = brewer["Spectral"][palette_min_colors][:number_of_areas]
    else:
        colors = brewer["Spectral"][number_of_areas]

    x2 = np.hstack((current_month_previous_removed.index[::-1], current_month_previous_removed.index))

    current_month_label_values = current_month_df[current_month_df.index == pd.to_datetime(last_available_date)].groupby(level=0).sum()
    names = []
    values = []
    dates = []

    current_month_labels = list(sorted([(v.iloc[0], k, previous_day) for k, v in current_month_label_values.items()]))
    current_month_total = sum(v for v, account, date in current_month_labels if account.isdigit())
    current_month_labels.append((current_month_total, "current_month_total", previous_day))

    accountid_display_labels = {}
    for value, name, date in current_month_labels:
        account_display_name = name
        if accountid_mapping:
            account_display_name = accountid_mapping.get(name, name)
        display_value = f"${value:>8.2f} {account_display_name}"
        accountid_display_labels[name] = display_value
        if "(Total)" in display_value:
            names.append(display_value)
            values.append(value)
            dates.append(date)

    legend_items = []
    for area, color in zip(areas, colors):
        accountid = areas[area].name
        renderer = f.patch(x2, areas[area].values, fill_color=color, alpha=0.8, line_color=None)
        label_display_text = accountid_display_labels[accountid]
        label_item = LegendItem(label=label_display_text, renderers=[renderer])
        legend_items.append(label_item)
    legend = Legend(
        items=legend_items,
        location="top_left",
        label_text_font_size="8pt",
        label_text_font="monaco",
    )
    f.add_layout(legend)

    labels_source = ColumnDataSource(data={"names": names, "values": values, "dates": dates})

    # adjust x offset
    x_offset = 5
    if last_available_date.day >= 18:
        x_offset = -150

    labels = LabelSet(
        x="dates",
        y="values",
        text="names",
        level="glyph",
        x_offset=x_offset,
        y_offset=5,
        source=labels_source,
        render_mode="canvas",
        text_font_size="14pt",
    )
    f.add_layout(labels)
    f.toolbar.logo = None
    f.toolbar_location = None
    return f, current_cost, previous_cost


def create_daily_pie_chart_figure(df: pd.DataFrame, tag_display_mapping: Optional[dict] = None) -> Union[Row, Column]:
    """
    tag/service毎のコストの円グラフを作成.
    """
    if not tag_display_mapping:
        tag_display_mapping = {}
    groupby_tag_values = set([str(x.split("/")[0]) for x in df.columns if x != "previous_month_total"])

    figures = []
    for groupby_tag_value in list(groupby_tag_values):
        df_project = df[[x for x in df.columns if x.split("/")[0] == groupby_tag_value]]
        project_total_cost = df_project.iloc[-1].sum()
        display_groupby_tag_value = tag_display_mapping.get(groupby_tag_value, groupby_tag_value)
        p = figure(
            plot_height=350,
            title=f"{display_groupby_tag_value}: ${project_total_cost:7.2f}",
            toolbar_location=None,
            tools="hover",
            tooltips="@projectid_service: @value",
        )

        df_project.columns = [x.split("/")[1] for x in df_project.columns]

        data = df_project.iloc[-1].reset_index(name="value").rename(columns={"index": "projectid_service"})
        data = data.sort_values("value", ascending=False).head(5)
        data["value"] += 0.0000001  # 0だと円グラフが作成されないためイプシロンを足す
        data["angle"] = data["value"] / data["value"].sum() * 2 * math.pi
        data["color"] = magma(len(data) + 1)[1:]

        data["projectid_service"] = [f"{row['projectid_service']}: ${row['value']:7.2f}" for _, row in data.iterrows()]

        p.wedge(
            x=0,
            y=1,
            radius=0.4,
            start_angle=cumsum("angle", include_zero=True),
            end_angle=cumsum("angle"),
            line_color="white",
            fill_color="color",
            legend="projectid_service",
            source=data,
        )

        figures.append(p)

    grid = gridplot(figures, ncols=3)

    return grid
