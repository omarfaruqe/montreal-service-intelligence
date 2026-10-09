import os
from datetime import date, datetime, time, timedelta

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="Montréal Service Intelligence",
    page_icon="🏙️",
    layout="wide",
)

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


@st.cache_data(ttl=300, max_entries=100, show_spinner=False)
def fetch_data(path, params):
    response = requests.get(
        f"{API_BASE_URL}{path}",
        params=params,
        timeout=(5, 120),
    )
    response.raise_for_status()
    return response.json()


def download_table(frame, filename, key):
    st.download_button(
        "Download CSV",
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


st.title("Montréal Municipal Service Intelligence")
st.caption(
    "Explore Montréal 311 records by borough, service category "
    "and creation month."
)

nature_options = {
    "Service requests": "Requete",
    "Information enquiries": "Information",
    "Comments": "Commentaire",
    "Complaints": "Plainte",
    "All record types": "all",
}

with st.sidebar:
    st.header("Filters")

    with st.form("filters"):
        selected_nature = st.selectbox(
            "Record type",
            list(nature_options),
        )

        borough_filter = st.text_input(
            "Borough — exact name",
            placeholder="Ville-Marie",
        )

        category_filter = st.text_input(
            "Category — exact name",
            placeholder="Nid-de-poule",
        )

        use_dates = st.checkbox("Filter by creation date")

        start_date = st.date_input(
            "From",
            value=date(2023, 1, 1),
        )

        end_date = st.date_input(
            "Through",
            value=date.today(),
        )

        top_limit = st.slider(
            "Number of top categories",
            min_value=5,
            max_value=30,
            value=10,
        )

        st.form_submit_button("Apply filters")

    if st.button("Refresh data"):
        fetch_data.clear()

    st.caption(
        "Matching responses are cached for up to five minutes. "
        "Refresh data to reload them."
    )

params = {"nature": nature_options[selected_nature]}

if borough_filter.strip():
    params["borough"] = borough_filter.strip()

if category_filter.strip():
    params["category"] = category_filter.strip()

if use_dates:
    if start_date > end_date:
        st.error("The start date must be on or before the end date.")
        st.stop()

    if end_date == date.max:
        st.error("Choose an end date earlier than December 31, 9999.")
        st.stop()

    params["created_from"] = datetime.combine(
        start_date, time.min
    ).isoformat()

    # The API end boundary is exclusive.
    # Using the following midnight includes the selected end day.
    params["created_before"] = datetime.combine(
        end_date + timedelta(days=1), time.min
    ).isoformat()

try:
    with st.spinner("Loading analytics from the API..."):
        borough_rows = fetch_data(
            "/api/analytics/boroughs",
            params,
        )

        category_rows = fetch_data(
            "/api/analytics/categories",
            {**params, "limit": top_limit},
        )

        monthly_rows = fetch_data(
            "/api/analytics/monthly",
            params,
        )

except requests.exceptions.Timeout:
    st.error(
        "The API request timed out. A large aggregation may take "
        "longer to complete. Try a narrower date range."
    )
    st.stop()

except requests.exceptions.ConnectionError:
    st.error(
        "Cannot connect to the API. Start FastAPI on port 8000 "
        "and make sure PostgreSQL is running."
    )
    st.stop()

except requests.exceptions.HTTPError as error:
    status = error.response.status_code
    st.error(
        f"The API returned HTTP {status}. "
        "Check the terminal running Uvicorn for details."
    )
    st.stop()

except ValueError:
    st.error("The API returned a response that was not valid JSON.")
    st.stop()

boroughs = pd.DataFrame(
    borough_rows,
    columns=["borough", "records"],
)

categories = pd.DataFrame(
    category_rows,
    columns=["category", "records"],
)

monthly = pd.DataFrame(
    monthly_rows,
    columns=["month", "records"],
)

total_records = int(boroughs["records"].sum())

missing_boroughs = int(
    boroughs.loc[boroughs["borough"].isna(), "records"].sum()
)

known_boroughs = int(boroughs["borough"].notna().sum())

st.subheader(selected_nature)

metric_1, metric_2, metric_3 = st.columns(3)

metric_1.metric("Matching records", f"{total_records:,}")
metric_2.metric("Borough values represented", known_boroughs)
metric_3.metric("Records without a borough", f"{missing_boroughs:,}")

if total_records == 0:
    st.info(
        "No records match these filters. Check exact borough "
        "and category spelling, or broaden the date range."
    )
    st.stop()

boroughs["borough"] = boroughs["borough"].fillna("Not provided")

borough_tab, category_tab, monthly_tab = st.tabs(
    ["Boroughs", "Top categories", "Monthly trend"]
)

with borough_tab:
    st.subheader("Records by borough")

    st.bar_chart(
        boroughs,
        x="borough",
        y="records",
        horizontal=True,
        sort="-records",
    )

    st.dataframe(boroughs, hide_index=True)

    download_table(
        boroughs,
        "montreal_borough_counts.csv",
        "borough_download",
    )

    st.caption(
        "'Not provided' represents records with a missing borough. "
        "Counts use the source ARRONDISSEMENT field."
    )

with category_tab:
    st.subheader(f"Top {top_limit} categories")

    st.bar_chart(
        categories,
        x="category",
        y="records",
        horizontal=True,
        sort="-records",
    )

    st.dataframe(categories, hide_index=True)

    download_table(
        categories,
        "montreal_top_categories.csv",
        "category_download",
    )

    st.caption(
        "This table contains only the leading categories. "
        "Its counts may not sum to the matching-record total."
    )

with monthly_tab:
    st.subheader("Records by creation month")

    monthly["month"] = pd.to_datetime(monthly["month"])
    monthly = monthly.sort_values("month")

    # Represent missing months as gaps rather than assuming zero.
    chart_data = monthly.set_index("month")[["records"]]
    complete_months = pd.date_range(
        chart_data.index.min(),
        chart_data.index.max(),
        freq="MS",
    )
    chart_data = chart_data.reindex(complete_months)
    chart_data.index.name = "month"

    st.line_chart(chart_data)

    monthly["month"] = monthly["month"].dt.strftime("%Y-%m")
    st.dataframe(monthly, hide_index=True)

    download_table(
        monthly,
        "montreal_monthly_counts.csv",
        "monthly_download",
    )

    st.caption(
        "Months with no returned records are shown as gaps. "
        "Months at date-filter boundaries or dataset boundaries "
        "may be incomplete."
    )

st.info(
    "These are record counts, not population-adjusted rates. "
    "The last status timestamp does not establish resolution time."
)