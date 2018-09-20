import datetime
import pandas as pd
import numpy as np
from bokeh.models import ColumnDataSource, Legend, LegendItem, LabelSet
from bokeh.plotting import figure
from bokeh.palettes import brewer


def create_daily_chart_image(current_month_df: pd.DataFrame, accountid_mapping: dict=None) -> figure:
    # get max record date (assumes values will NOT decrease)
    accountids = [i for i in current_month_df.columns if i.isdigit()]
    sample_accountid = accountids[0]
    last_available_date = current_month_df[current_month_df[sample_accountid] == current_month_df[sample_accountid].max()].index.date[0]

    source = ColumnDataSource(current_month_df)

    today = datetime.datetime.utcnow()
    previous_day = today - datetime.timedelta(days=2)
    today_display_str = today.strftime('%Y-%m-%d')
    f = figure(
        title=f'AWS Cost ({today_display_str} UTC)',
        x_axis_type="datetime",
        x_axis_label='Date',
        y_axis_label='Cost ($)',
        plot_width=800,
        plot_height=350
    )
    f.title.text_font_size = '14pt'
    f.line('date', 'previous_month_total',
           source=source,
           line_color='gray',
           line_dash='dashed')

    def stacked(df):
        df_top = df.cumsum(axis=1)
        df_bottom = df_top.shift(axis=1)[::-1]

        df_stack = pd.concat([df_bottom, df_top], ignore_index=True)
        return df_stack

    current_month_previous_removed = current_month_df.drop(['previous_month_total'], axis=1)
    areas = stacked(current_month_previous_removed)
    areas = areas.fillna(0.0)
    number_of_areas = areas.shape[1]
    colors = brewer['Spectral'][number_of_areas]

    x2 = np.hstack(
        (current_month_previous_removed.index[::-1],
         current_month_previous_removed.index)
    )

    current_month_label_values = current_month_df[current_month_df.index == pd.to_datetime(last_available_date)].groupby(level=0).sum()
    names = []
    values = []
    dates = []

    current_month_labels = list(sorted([(v.iloc[0], k, previous_day) for k, v in current_month_label_values.items()]))
    current_month_total = sum(v for v, account, date in current_month_labels if account.isdigit())
    current_month_labels.append((current_month_total, 'current_month_total', previous_day))
    accountid_display_labels = {}
    for value, name, date in current_month_labels:
        account_display_name = name
        if accountid_mapping:
            account_display_name = accountid_mapping[name]
        display_value = f'${value:>8.2f} {account_display_name}'
        accountid_display_labels[name] = display_value
        if '(Total)' in display_value:
            names.append(display_value)
            values.append(value)
            dates.append(date)

    legend_items = []
    for area, color in zip(areas, colors):
        accountid = areas[area].name
        renderer = f.patch(
            x2,
            areas[area].values,
            fill_color=color,
            alpha=0.8,
            line_color=None
        )
        label_display_text = accountid_display_labels[accountid]
        label_item = LegendItem(
            label=label_display_text,
            renderers=[renderer]
        )
        legend_items.append(label_item)
    legend = Legend(
        items=legend_items,
        location='top_left',
        label_text_font_size='8pt',
        label_text_font='monaco',
    )
    f.add_layout(legend)

    labels_source = ColumnDataSource(data={
        'names': names,
        'values': values,
        'dates': dates
    })

    labels = LabelSet(
        x='dates',
        y='values',
        text='names',
        level='glyph',
        x_offset=5,
        y_offset=5,
        source=labels_source,
        render_mode='canvas',
        text_font_size='14pt',
    )
    f.add_layout(labels)
    f.toolbar.logo = None
    f.toolbar_location = None
    return f
