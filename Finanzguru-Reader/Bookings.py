# %%
import json
import pandas as pd
import numpy as np

# Dev setting
file_path = "/Users/adrian/Cloud/2024-03-20_Finanzguru-Export-DSGVO.json"
bookings = json.load(open(file_path))
bookings = bookings["analysis"]["bookings"]

# Flatten the list of dictionaries into a DataFrame
df = pd.json_normalize(bookings)

# Set cells that contain empty lists or dictionaries to ""
df = df.applymap(lambda x: "" if isinstance(x, (list, dict)) and len(x) == 0 else x)

# Remove unnecessary columns
pd.set_option("display.max_columns", None)
df.dropna(thresh=0.1 * len(df), axis=1, inplace=True)
df.drop(columns="id", inplace=True)
# drop columns with only one unique value
df = df.loc[:, df.nunique() != 1]

# Convert the date columns to datetime
# if colname contains "date" or "time"
date_cols = [
    col for col in df.columns if ("date" in col.lower() or "time" in col.lower())
]
for col in date_cols:
    df[col] = df[col][:24]
    df[col] = pd.to_datetime(df[col])

# convert numeric columns to float
numeric_cols = df.select_dtypes(include=[np.number]).columns
for col in numeric_cols:
    df[col] = df[col].astype(float)
    
# convert text columns to string
text_cols = df.select_dtypes(include=[object]).columns
for col in text_cols:
    df[col] = df[col].astype(str)
    
# Get columns that contain "analysis"
analysis_cols = [col for col in text_cols if "analysis" in col.lower()]
# replace underscores with spaces and make contents title case
df[analysis_cols] = df[analysis_cols].replace("_", " ", regex=True)
df[analysis_cols] = df[analysis_cols].apply(lambda x: x.str.title())


display(df)



# %%

import matplotlib.pyplot as plt
import seaborn as sns
# Group by mainCategory and sum the amounts for income
df_income = df[df['amount'] > 0]
df_income_grouped = df_income.groupby("analysisCat.mainCategory")["amount"].sum()
df_income_grouped = df_income_grouped[df_income_grouped / df_income_grouped.sum() > 0.01]
df_income_grouped = df_income_grouped.sort_values(ascending=False)

# Group by mainCategory and sum the amounts for expenses
df_expenses = df[df['amount'] < 0]
df_expenses_grouped = df_expenses.groupby("analysisCat.mainCategory")["amount"].apply(lambda x: np.abs(x).sum())
df_expenses_grouped = df_expenses_grouped[df_expenses_grouped / df_expenses_grouped.sum() > 0.01]
df_expenses_grouped = df_expenses_grouped.sort_values(ascending=False)

# Create a figure with two subplots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))

# Plot the pie chart for income
sns.set_palette("pastel")
sns.set_context("talk")
wedges1, texts1, autotexts1 = ax1.pie(df_income_grouped, autopct="%1.1f%%")
ax1.axis("equal")
ax1.set_title("Sum of Income by Main Category")
ax1.legend(wedges1, df_income_grouped.index, title="Categories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))

# Plot the pie chart for expenses
sns.set_palette("pastel")
sns.set_context("talk")
wedges2, texts2, autotexts2 = ax2.pie(df_expenses_grouped, autopct="%1.1f%%")
ax2.axis("equal")
ax2.set_title("Sum of Expenses by Main Category")
ax2.legend(wedges2, df_expenses_grouped.index, title="Categories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))

# Adjust subplot parameters to give specified padding
plt.tight_layout()

# Display the plots
plt.show()

# %%

# For the largest two categories of df_expenses_grouped, plot a pie chart of analysisCat.subCategory
# Get the two largest categories
largest_categories = df_expenses_grouped.index[:2]

# Create a figure with two subplots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))

# Plot the pie chart for the first largest category
df_expenses_cat1 = df_expenses[df_expenses["analysisCat.mainCategory"] == largest_categories[0]]
df_expenses_cat1_grouped = df_expenses_cat1.groupby("analysisCat.subCategory")["amount"].apply(lambda x: np.abs(x).sum())
df_expenses_cat1_grouped = df_expenses_cat1_grouped[df_expenses_cat1_grouped / df_expenses_cat1_grouped.sum() > 0.01]
df_expenses_cat1_grouped = df_expenses_cat1_grouped.sort_values(ascending=False)
sns.set_palette("pastel")
sns.set_context("talk")
wedges1, texts1, autotexts1 = ax1.pie(df_expenses_cat1_grouped, autopct="%1.1f%%")
ax1.axis("equal")
ax1.set_title(f"Sum of Expenses by Subcategory for {largest_categories[0]}")
ax1.legend(wedges1, df_expenses_cat1_grouped.index, title="Subcategories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))

# Plot the pie chart for the second largest category
df_expenses_cat2 = df_expenses[df_expenses["analysisCat.mainCategory"] == largest_categories[1]]
df_expenses_cat2_grouped = df_expenses_cat2.groupby("analysisCat.subCategory")["amount"].apply(lambda x: np.abs(x).sum())
df_expenses_cat2_grouped = df_expenses_cat2_grouped[df_expenses_cat2_grouped / df_expenses_cat2_grouped.sum() > 0.01]
df_expenses_cat2_grouped = df_expenses_cat2_grouped.sort_values(ascending=False)
sns.set_palette("pastel")
sns.set_context("talk")
wedges2, texts2, autotexts2 = ax2.pie(df_expenses_cat2_grouped, autopct="%1.1f%%")
ax2.axis("equal")
ax2.set_title(f"Sum of Expenses by Subcategory for {largest_categories[1]}")
ax2.legend(wedges2, df_expenses_cat2_grouped.index, title="Subcategories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))

# Adjust subplot parameters to give specified padding
plt.tight_layout()

# Display the plots
plt.show()

# %%
