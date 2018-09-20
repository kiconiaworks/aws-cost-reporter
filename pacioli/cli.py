import datetime
from .functions import prepare_daily_chart_figure, generate_daily_chart_image


if __name__ == '__main__':
    now = datetime.datetime.now()


    chart_figure = prepare_daily_chart_figure(now, accountid_mapping)
    output_filepath = generate_daily_chart_image(chart_figure)
    print(output_filepath)

