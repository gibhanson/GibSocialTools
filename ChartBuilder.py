import seaborn as sns
import matplotlib.pyplot as plt
import polars as pl
from polars import DataFrame
import re
import numpy as np


def get_daterange(data: DataFrame) -> str:
	first = data_duration.filter(pl.col("Date") == pl.col("Date").min())["Date"][0].strftime("%m/%d/%y")
	last = data_duration.filter(pl.col("Date") == pl.col("Date").max())["Date"][0].strftime("%m/%d/%y")
	return f"{first} - {last}"


def get_plots(data: DataFrame, columnA: str, title: str = None, columnB: str = None, trend:bool = False):

	title = columnA if title is None else title

	# Build plots
	if data.get_column(columnA).is_empty(): raise Exception(f"{columnA} not found")
	plotA = sns.barplot(x="Short Program", y=columnA, data=data.to_pandas(), ax=ax)

	if trend:
		trendplot = sns.regplot(data=data.to_pandas(), x=np.arange(len(data)), order=3, y=columnA, scatter=False, ax=ax,
								color='orange', label='Trend')
	if columnB:
		if data.get_column(columnB).is_empty(): raise Exception(f"{columnB} not found")
		plotB = sns.barplot(x="Short Program", y=columnB, data=data.to_pandas(), ax=ax)
		plotB.legend(handles=plotB.containers, labels=[columnA, columnB])

	fig.canvas.manager.set_window_title(f"Chart {title}") #Set window title

	# Set up labels
	ax.set_ylabel("Totals")
	ax.set_xlabel("Program Name")
	ax.set_title(f"{title} ({data.height} programs from {get_daterange(data)})")

	#Create Axis labels
	for container in ax.containers:
		# noinspection PyTypeChecker
		ax.bar_label(container)

	# Rotate tick marks depending on how dense the chart is
	r = 45 if data.height > 20 else 0
	r = 90 if data.height > 40 else r
	ax.set_xticklabels(ax.get_xticklabels(), rotation=r)



# Set up SNS themes/colors
sns.set_style("white")

# Read Excel
data_full = pl.read_excel(source="H:/Dropbox/CREATIVE/FREELANCE/JUDJ/STATS/Stats.xlsx", sheet_name="Data",
						  engine="openpyxl", infer_schema_length=1000)

# Filter for time period
data_duration = data_full.filter(pl.col("Date") >= pl.col("Date").max() - pl.duration(days=360))

# Create some interface-friendly versions of columns
data_duration = data_duration.with_columns(pl.Series(name = "Long Program", values = data_duration["Participants"] +
													 "\n" + data_duration["Date"].dt.to_string("(%m/%d/%y)")))
data_duration = data_duration.with_columns(pl.Series(name = "Friendly Date",
													 values = data_duration["Date"].dt.to_string("%m/%d/%y")))
newnames = []
dates = data_duration["Friendly Date"].to_list()
for i, n in enumerate(data_duration["Participants"].to_list()):
	if not n: newnames.append("")
	found = re.search(r'[A-Za-z]+,', n)
	if found: newnames.append(found.group(0).removesuffix(",") + f" ({dates[i]})")
data_duration = data_duration.with_columns(pl.Series(name="Short Program", values=newnames))

# Get live attendance chart
sns.set_palette("pastel")
fig, ax = plt.subplots(figsize=(22, 8))
get_plots(data_duration, columnA="Total Viewers", title="Total Viewers (Live Program)", trend=False)
plt.tight_layout(pad=5.0)
plt.show()

# Get total viewers and registrations chart
sns.set_palette("pastel")
fig, ax = plt.subplots(figsize=(22, 8))
get_plots(data_duration, columnA="Registrations", columnB="Total Viewers", title="Total Viewers vs Registrations (Live Program)", trend=False)
plt.tight_layout(pad=5.0)
plt.show()

# Get podcast chart
sns.set_palette("icefire")
fig, ax = plt.subplots(figsize=(22, 8))
get_plots(data_duration, "Podcast Viewers", trend=True)
plt.tight_layout(pad=5.0)
plt.show()

# Get YouTube episode viewership chart
sns.set_palette("tab20b_r")
fig, ax = plt.subplots(figsize=(22, 8))
get_plots(data_duration, "YouTube Episode Viewers", "Episode Viewership (YouTube)", trend=True)
plt.tight_layout(pad=5.0)
plt.show()

# Get Gib videos chart
sns.set_palette("pastel")
fig, ax = plt.subplots(figsize=(22, 8))
get_plots(data_duration, "Total Gib Viewers", "Gib Video Viewership (YouTube)", trend=True)
plt.tight_layout(pad=5.0)
plt.show()