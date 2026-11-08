import streamlit as st

from api_client.client import AdPilotApiClient
from views.ai_campaign_setup import render_ai_campaign_setup
from views.campaign_create import render_campaign_create
from views.campaign_detail import render_campaign_detail
from views.campaign_list import render_campaign_list
from views.common import show_flash
from views.dashboard import render_dashboard
from views.performance_dashboard import render_performance_dashboard

PAGES = (
    "Dashboard",
    "Performance Dashboard",
    "Campaign List",
    "Campaign Create",
    "AI Campaign Setup",
    "Campaign Detail",
)

st.set_page_config(page_title="AdPilot AI", page_icon="✈️", layout="wide")
st.title("AdPilot AI")
st.caption("Campaign Administration · Synthetic Analytics · Phase 3")


def navigate(page: str, campaign_id: str | None = None) -> None:
    st.session_state["pending_page"] = page
    if campaign_id is not None:
        st.session_state["selected_campaign_id"] = campaign_id
    st.rerun()


pending_page = st.session_state.pop("pending_page", None)
if pending_page is not None:
    st.session_state["navigation_page"] = pending_page
elif "navigation_page" not in st.session_state:
    st.session_state["navigation_page"] = "Dashboard"

selected_page = st.sidebar.radio(
    "Navigation",
    PAGES,
    key="navigation_page",
)
current_page = selected_page

st.sidebar.caption("Streamlit은 FastAPI REST API만 호출합니다.")
show_flash()
api_client = AdPilotApiClient()

if current_page == "Dashboard":
    render_dashboard(api_client)
elif current_page == "Performance Dashboard":
    render_performance_dashboard(api_client)
elif current_page == "Campaign List":
    render_campaign_list(api_client, navigate)
elif current_page == "Campaign Create":
    render_campaign_create(api_client, navigate)
elif current_page == "AI Campaign Setup":
    render_ai_campaign_setup(api_client, navigate)
else:
    render_campaign_detail(api_client, navigate)
