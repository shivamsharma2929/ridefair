import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="RideFair", page_icon="🚕", layout="wide")

FILE = Path("ridefair_data.csv")

st.title("🚕 RideFair")
st.caption("Ride-hailing pricing research and simulation")

# ---------- DATA ----------
TEXT_COLS = ["Time", "Device", "Model", "OS", "Charging", "Network", "Signal",
             "Ride Type", "Route", "Traffic", "Source", "Notes"]
NUM_COLS = ["Battery", "Distance", "Demand", "Drivers", "Base Fare",
            "Fare", "Simulated Fare", "Difference"]
COLUMNS = [
    "Time", "Request Time", "Device", "Model", "OS", "Battery", "Charging",
    "Network", "Signal", "Ride Type", "Route", "Distance", "Traffic",
    "Demand", "Drivers", "Base Fare", "Simulated Fare", "Fare",
    "Difference", "Source", "Notes",
]
DEVICE_OS = {"iPhone": "iOS", "Android": "Android OS"}
NETWORKS = ["Wi-Fi 5 GHz", "Wi-Fi 2.4 GHz", "Mobile Data"]
PEAK_HOURS = {8, 9, 10, 17, 18, 19, 20}


def load_data():
    if not FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_csv(FILE)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=COLUMNS)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = "Unknown" if col in TEXT_COLS else float("nan")
    for col in NUM_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Request Time"] = df["Request Time"].where(
        df["Request Time"].notna() & (df["Request Time"] != "Unknown"),
        df["Time"],
    )
    return df[COLUMNS].reset_index(drop=True)


def save_data(df):
    tmp = FILE.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, FILE)


# ---------- PRICING MODEL (researcher-defined hypotheses) ----------
def sidebar_params():
    with st.sidebar.expander("Model assumptions (hypotheses)"):
        st.caption("All values are % adjustments you define. "
                   "These are NOT verified Uber rules.")
        p = {
            "android": st.number_input("Android device", value=-5.0, step=1.0),
            "bat_low": st.number_input("Battery ≤ 20%", value=20.0, step=1.0),
            "bat_mid": st.number_input("Battery 21–40%", value=10.0, step=1.0),
            "wifi5": st.number_input("Wi-Fi 5 GHz", value=-5.0, step=1.0),
            "wifi24": st.number_input("Wi-Fi 2.4 GHz", value=3.0, step=1.0),
            "mobile": st.number_input("Mobile data", value=8.0, step=1.0),
            "combo": st.number_input("Low battery + mobile data", value=10.0, step=1.0),
            "traffic_med": st.number_input("Medium traffic", value=10.0, step=1.0),
            "traffic_high": st.number_input("High traffic", value=20.0, step=1.0),
            "demand_step": st.number_input("Per demand level above 3", value=5.0, step=1.0),
            "driver_step": st.number_input("Per driver level below 3", value=5.0, step=1.0),
            "peak": st.number_input("Peak hour (8–10, 17–20)", value=10.0, step=1.0),
            "per_km": st.number_input("₹ per km after first km", value=12.0, step=1.0),
        }
    return p


def calculate_fare(base, device, battery, network, distance,
                   traffic, demand, drivers, hour, p):
    pct = {
        "Device": p["android"] if device == "Android" else 0,
        "Battery": p["bat_low"] if battery <= 20 else (
            p["bat_mid"] if battery <= 40 else 0),
        "Network": {"Wi-Fi 5 GHz": p["wifi5"], "Wi-Fi 2.4 GHz": p["wifi24"],
                    "Mobile Data": p["mobile"]}.get(network, 0),
        "Low battery + mobile data": (
            p["combo"] if battery <= 20 and network == "Mobile Data" else 0),
        "Traffic": {"Low": 0, "Medium": p["traffic_med"],
                    "High": p["traffic_high"]}[traffic],
        "Demand": (demand - 3) * p["demand_step"],
        "Driver availability": (3 - drivers) * p["driver_step"],
        "Peak hour": p["peak"] if hour in PEAK_HOURS else 0,
    }
    distance_fare = max(0, distance - 1) * p["per_km"]
    fare = max(0, base * (1 + sum(pct.values()) / 100) + distance_fare)

    breakdown = pd.DataFrame(
        [{"Factor": k, "Adjustment (%)": v, "Impact (₹)": round(base * v / 100, 2)}
         for k, v in pct.items()]
        + [{"Factor": "Distance addition", "Adjustment (%)": None,
            "Impact (₹)": round(distance_fare, 2)}]
    )
    return round(fare, 2), breakdown


# ---------- SIDEBAR ----------
page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "New Experiment", "Compare Conditions",
     "Experiment History", "About & Methodology"],
)
P = sidebar_params()

# ---------- DASHBOARD ----------
if page == "Dashboard":
    st.header("Research Dashboard")
    data = load_data()

    if data.empty:
        st.info("No experiments yet. Start from New Experiment.")
    else:
        f1, f2, f3 = st.columns(3)
        src = f1.multiselect("Source", sorted(data["Source"].unique()),
                             default=sorted(data["Source"].unique()))
        dev = f2.multiselect("Device", sorted(data["Device"].unique()),
                             default=sorted(data["Device"].unique()))
        ride = f3.multiselect("Ride type", sorted(data["Ride Type"].unique()),
                              default=sorted(data["Ride Type"].unique()))
        d = data[data["Source"].isin(src) & data["Device"].isin(dev)
                 & data["Ride Type"].isin(ride)].copy()
        d["Request Time"] = pd.to_datetime(d["Request Time"], errors="coerce")

        real = d[d["Source"] == "Real quote"]
        sim = d[d["Source"] == "Simulated"]
        k = st.columns(5)
        k[0].metric("Experiments", len(d))
        k[1].metric("Real quotes", len(real))
        k[2].metric("Simulations", len(sim))
        k[3].metric("Avg real fare",
                    f"₹{real['Fare'].mean():.0f}" if len(real) else "–")
        mae = real["Difference"].abs().mean()
        k[4].metric("Model error (MAE)",
                    f"₹{mae:.1f}" if pd.notna(mae) else "–")

        st.subheader("Recorded Data")
        st.dataframe(d, use_container_width=True)

        if d["Fare"].notna().any():
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Fare by Device")
                st.plotly_chart(
                    px.box(d, x="Device", y="Fare", color="Source", points="all"),
                    use_container_width=True)
            with c2:
                st.subheader("Average Fare by Network")
                g = d.groupby(["Network", "Device"], as_index=False)["Fare"].mean()
                st.plotly_chart(
                    px.bar(g, x="Network", y="Fare", color="Device",
                           barmode="group"),
                    use_container_width=True)

            st.subheader("Battery vs Fare")
            st.plotly_chart(
                px.scatter(d, x="Battery", y="Fare", color="Network",
                           symbol="Device",
                           hover_data=["Route", "Ride Type", "Source"]),
                use_container_width=True)

            trend = d.dropna(subset=["Request Time"]).sort_values("Request Time")
            if len(trend) > 1:
                st.subheader("Fare Trend Over Time")
                st.plotly_chart(
                    px.line(trend, x="Request Time", y="Fare", color="Device",
                            markers=True, hover_data=["Route", "Source"]),
                    use_container_width=True)

            paired = real.dropna(subset=["Fare", "Simulated Fare"])
            if not paired.empty:
                st.subheader("Model vs Actual (real quotes)")
                fig = px.scatter(paired, x="Simulated Fare", y="Fare",
                                 color="Device", hover_data=["Route"])
                lim = [0, max(paired["Fare"].max(), paired["Simulated Fare"].max())]
                fig.add_trace(go.Scatter(x=lim, y=lim, mode="lines",
                                         name="Perfect match",
                                         line=dict(dash="dash")))
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Points above the line: actual fare higher than the "
                           "model predicted.")

# ---------- NEW EXPERIMENT ----------
elif page == "New Experiment":
    st.header("Record or Simulate a Ride Quote")
    left, right = st.columns([3, 1])

    with left:
        st.subheader("Device conditions")
        c1, c2, c3 = st.columns(3)
        with c1:
            device = st.selectbox("Device", list(DEVICE_OS))
            model = st.text_input("Device model", "Not recorded")
            st.text_input("Operating system", DEVICE_OS[device], disabled=True)
        with c2:
            battery = st.slider("Battery level (%)", 1, 100, 50)
            charging = st.selectbox("Charging", ["No", "Yes", "Unknown"])
            network = st.selectbox("Network", NETWORKS)
        with c3:
            signal = st.selectbox("Signal strength",
                                  ["Weak", "Medium", "Strong", "Unknown"])
            source = st.selectbox("Data source", ["Real quote", "Simulated"])
            route = st.text_input("Route ID", "Route-01")

        st.subheader("Ride conditions")
        c4, c5, c6 = st.columns(3)
        with c4:
            ride = st.selectbox("Ride type",
                                ["Uber Go", "Uber Auto", "Uber Premier", "Other"])
            distance = st.number_input("Distance (km)", min_value=0.1, value=5.0)
            req_date = st.date_input("Request date", datetime.now().date())
        with c5:
            traffic = st.selectbox("Traffic", ["Low", "Medium", "High"])
            demand = st.slider("Demand (1 low – 5 high)", 1, 5, 3)
            req_time = st.time_input("Request time", datetime.now().time())
        with c6:
            drivers = st.slider("Driver availability (1 low – 5 high)", 1, 5, 3)
            base = st.number_input("Base fare (₹)", min_value=1.0, value=100.0)

        quoted = 0.0
        if source == "Real quote":
            quoted = st.number_input("Actual quoted fare (₹) — required",
                                     min_value=0.0, value=0.0)
        notes = st.text_area("Notes / observations")

    request_dt = datetime.combine(req_date, req_time)
    predicted, breakdown = calculate_fare(
        base, device, battery, network, distance, traffic,
        demand, drivers, request_dt.hour, P)

    with right:
        st.subheader("Live simulation")
        st.metric("Simulated fare", f"₹{predicted:.2f}",
                  delta=f"{predicted - base:+.2f} vs base")
        if source == "Real quote" and quoted > 0:
            st.metric("Actual quote", f"₹{quoted:.2f}",
                      delta=f"{quoted - predicted:+.2f} vs model")

    st.write("Model adjustment breakdown")
    st.dataframe(breakdown, use_container_width=True, hide_index=True)

    if st.button("Save Experiment", type="primary"):
        if source == "Real quote" and quoted <= 0:
            st.error("A real quote needs the actual fare. Enter it, or switch "
                     "the source to Simulated.")
        else:
            is_real = source == "Real quote"
            fare = quoted if is_real else predicted
            row = pd.DataFrame([{
                "Time": datetime.now().isoformat(timespec="seconds"),
                "Request Time": request_dt.isoformat(timespec="seconds"),
                "Device": device, "Model": model, "OS": DEVICE_OS[device],
                "Battery": battery, "Charging": charging, "Network": network,
                "Signal": signal, "Ride Type": ride, "Route": route,
                "Distance": distance, "Traffic": traffic, "Demand": demand,
                "Drivers": drivers, "Base Fare": base,
                "Simulated Fare": predicted, "Fare": fare,
                "Difference": round(quoted - predicted, 2) if is_real else float("nan"),
                "Source": source, "Notes": notes,
            }])
            save_data(pd.concat([load_data(), row], ignore_index=True))
            st.success("Experiment saved.")

# ---------- COMPARE CONDITIONS ----------
elif page == "Compare Conditions":
    st.header("Compare Device and Network Conditions")
    st.write("Model output for the same inputs across every device/network "
             "combination. Hypothetical, not real Uber fares.")

    c1, c2, c3 = st.columns(3)
    base = c1.number_input("Base fare (₹)", min_value=1.0, value=100.0)
    distance = c2.number_input("Distance (km)", min_value=0.1, value=5.0)
    battery = c3.slider("Battery level (%)", 1, 100, 15)
    c4, c5, c6, c7 = st.columns(4)
    traffic = c4.selectbox("Traffic", ["Low", "Medium", "High"])
    demand = c5.slider("Demand", 1, 5, 3)
    drivers = c6.slider("Driver availability", 1, 5, 3)
    hour = c7.slider("Hour of day", 0, 23, 12)

    rows = []
    for dv in DEVICE_OS:
        for nw in NETWORKS:
            fare, _ = calculate_fare(base, dv, battery, nw, distance, traffic,
                                     demand, drivers, hour, P)
            rows.append({"Device": dv, "Network": nw, "Simulated Fare (₹)": fare})
    comp = pd.DataFrame(rows)
    ref = comp["Simulated Fare (₹)"].min()
    comp["Above cheapest (₹)"] = (comp["Simulated Fare (₹)"] - ref).round(2)
    comp["Above cheapest (%)"] = (
        (comp["Simulated Fare (₹)"] / ref - 1) * 100).round(1)

    st.dataframe(comp, use_container_width=True, hide_index=True)
    st.plotly_chart(
        px.bar(comp, x="Network", y="Simulated Fare (₹)", color="Device",
               barmode="group", title="Hypothetical Fare Comparison"),
        use_container_width=True)

    st.subheader("Fare across battery levels")
    sweep = []
    for lvl in range(5, 101, 5):
        for dv in DEVICE_OS:
            for nw in NETWORKS:
                f, _ = calculate_fare(base, dv, lvl, nw, distance, traffic,
                                      demand, drivers, hour, P)
                sweep.append({"Battery (%)": lvl, "Series": f"{dv} · {nw}",
                              "Fare (₹)": f})
    st.plotly_chart(
        px.line(pd.DataFrame(sweep), x="Battery (%)", y="Fare (₹)",
                color="Series"),
        use_container_width=True)

# ---------- HISTORY ----------
elif page == "Experiment History":
    st.header("Experiment History")
    data = load_data()

    if data.empty:
        st.info("No records saved yet.")
    else:
        f1, f2, f3 = st.columns(3)
        sources = f1.multiselect("Source", sorted(data["Source"].unique()),
                                 default=sorted(data["Source"].unique()))
        devices = f2.multiselect("Device", sorted(data["Device"].unique()),
                                 default=sorted(data["Device"].unique()))
        search = f3.text_input("Search route ID or notes")

        filtered = data[data["Source"].isin(sources) & data["Device"].isin(devices)]
        if search:
            mask = (filtered["Route"].astype(str).str.contains(search, case=False, na=False)
                    | filtered["Notes"].astype(str).str.contains(search, case=False, na=False))
            filtered = filtered[mask]

        st.dataframe(filtered, use_container_width=True)
        st.download_button(
            "Export filtered CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="ridefair_export.csv", mime="text/csv")

        with st.expander("Delete records"):
            to_delete = st.multiselect(
                "Select records",
                filtered.index.tolist(),
                format_func=lambda i: f"{i}: {data.at[i, 'Route']} · "
                                      f"{data.at[i, 'Device']} · ₹{data.at[i, 'Fare']}")
            if to_delete and st.button("Delete selected"):
                save_data(data.drop(index=to_delete))
                st.success(f"Deleted {len(to_delete)} record(s). Reload the page.")

# ---------- METHODOLOGY ----------
elif page == "About & Methodology":
    st.header("About RideFair")
    st.write("""
    RideFair is an independent project to study ride-hailing quote differences.

    It contains a configurable hypothetical pricing model and a tool for
    recording real quotes. The model's device, battery, network and peak-hour
    effects are researcher-defined assumptions (editable in the sidebar), not
    verified Uber behavior.

    For a fair experiment, keep route, ride type, request time, account
    conditions and promotions as consistent as possible. Repeat measurements
    and distinguish real observations from simulations.

    A correlation does not establish that a phone or battery level caused
    a price change. Do not label simulated values as real Uber fares.
    """)