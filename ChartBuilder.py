import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from colorama import Fore, init
from polars import DataFrame
import argparse
import re
from datetime import date
from pathlib import Path

data_duration: DataFrame #TODO: Let's not have this be a global.

def get_args():
	"""Parses command line arguments."""
	parser = argparse.ArgumentParser(description='Creates charts from an excel spreadsheet.')
	parser.add_argument("path", type=str, default="stats.xlsx", nargs="?",
						help="path to excel spreadsheet")  # Added nargs="?" so default works
	parser.add_argument("-d", "--duration", type=int, default=90,
						help="time range (in days from today) to show in charts.")

	return parser.parse_args()


def get_daterange(data: DataFrame) -> str:
	first = data.filter(pl.col("Date") == pl.col("Date").min())["Date"][0].strftime("%m/%d/%y")
	last = data.filter(pl.col("Date") == pl.col("Date").max())["Date"][0].strftime("%m/%d/%y")
	return f"{first} - {last}"


def get_plots(data: DataFrame, columnA: str, title: str = None, columnB: str = None, trend: bool = False):
	title = columnA if title is None else title

	fig, ax = plt.subplots(figsize=(22, 8))

	# Build plots
	if data.get_column(columnA).is_empty(): raise Exception(f"{columnA} not found")
	plotA = sns.barplot(x="Short Program", y=columnA, data=data.to_pandas(), ax=ax)

	if trend:
		trendplot = sns.regplot(data=data.to_pandas(), x=np.arange(len(data)), order=3, y=columnA, scatter=False,
								ax=ax, color='orange', label='Trend')
	if columnB:
		if data.get_column(columnB).is_empty(): raise Exception(f"{columnB} not found")
		plotB = sns.barplot(x="Short Program", y=columnB, data=data.to_pandas(), ax=ax)
		plotB.legend(handles=plotB.containers, labels=[columnA, columnB])

	fig.canvas.manager.set_window_title(f"Chart {title}")

	# Set up labels
	ax.set_ylabel("Totals")
	ax.set_xlabel("Program Name")
	ax.set_title(f"{title} ({data.height} programs from {get_daterange(data)})")

	# Create Axis labels
	for container in ax.containers:
		# noinspection PyTypeChecker
		ax.bar_label(container)

	# Rotate tick marks depending on how dense the chart is
	r = 45 if data.height > 20 else 0
	r = 90 if data.height > 40 else r
	ax.set_xticklabels(ax.get_xticklabels(), rotation=r)

	# Clean up the layout right before displaying
	plt.tight_layout(pad=5.0)


def main(args):
	excel_path = Path(args.path)
	date_range = args.duration

	if not excel_path.exists():
		print(Fore.RED + f"Excel file not found: {excel_path}")
		exit(1)

	# Read Excel
	data_full = pl.read_excel(source=excel_path, sheet_name="Data",
							  engine="openpyxl", infer_schema_length=1000)

	# Filter for time period: 3 full months back from the start of the current month
	today = date.today()
	start_of_this_month = date(today.year, today.month, 1)
	# Subtract 3 months, handling year rollover
	month = start_of_this_month.month - 3
	year = start_of_this_month.year
	while month <= 0:
		month += 12
		year -= 1
	range_start = date(year, month, 1)

	friendly_data = data_full.filter(
		(pl.col("Date") >= range_start) & (pl.col("Date") < start_of_this_month)
	)

	# Create some display-friendly versions of columns
	friendly_data = friendly_data.with_columns(pl.Series(name="Long Program", values=friendly_data["Participants"] +
														"\n" + friendly_data["Date"].dt.to_string("(%m/%d/%y)")))
	friendly_data = friendly_data.with_columns(pl.Series(name="Friendly Date",
														 values=friendly_data["Date"].dt.to_string("%m/%d/%y")))

	friendly_data = friendly_data.with_columns(pl.Series(name="Connections", values=friendly_data["Total Viewers"]))

	newnames = []
	dates = friendly_data["Friendly Date"].to_list()
	for i, n in enumerate(friendly_data["Participants"].to_list()):
		if not n: newnames.append("")
		found = re.search(r'[A-Za-z]+,', n)
		if found: newnames.append(found.group(0).removesuffix(",") + f" ({dates[i]})")
	friendly_data = friendly_data.with_columns(pl.Series(name="Short Program", values=newnames))

	# Set up SNS themes/colors
	sns.set_style("white")

	# Get live attendance chart
	sns.set_palette("pastel")
	# fig, ax = plt.subplots(figsize=(22, 8))
	get_plots(friendly_data, columnA="Registrations", columnB="Connections",
			  title=f"Live Audience ({get_daterange(friendly_data)})",
			  trend=False)
	plt.tight_layout(pad=5.0)
	plt.show()

	# Get podcast chart
	sns.set_palette("icefire")
	# fig, ax = plt.subplots(figsize=(22, 8))
	get_plots(friendly_data, "Podcast Attendance",
			  title=f"Podcast Viewers ({get_daterange(friendly_data)})",
			  trend=False)
	plt.tight_layout(pad=5.0)
	plt.show()

	# Get YouTube episode viewership chart
	sns.set_palette("tab20b_r")
	# fig, ax = plt.subplots(figsize=(22, 8))
	get_plots(friendly_data, "YouTube Episode Viewers",
			  f"Episode Viewership (YouTube) ({get_daterange(friendly_data)})",
			  trend=False)
	plt.tight_layout(pad=5.0)
	plt.show()

	# Get Gib videos chart
	sns.set_palette("pastel")
	# fig, ax = plt.subplots(figsize=(22, 8))
	get_plots(friendly_data, "Total Gib Viewers",
			  f"Gib Video Viewership (YouTube) ({get_daterange(friendly_data)})",
			  trend=False)
	plt.tight_layout(pad=5.0)
	plt.show()


if __name__ == "__main__":
	try:
		init(autoreset=True)  # Set up colorama text colors
		main(get_args())
	except KeyboardInterrupt:
		print(Fore.RED + "Operation cancelled by user.")
		exit(1)
