import streamlit as st

from api_client.client import AdPilotApiClient

st.set_page_config(page_title="AdPilot AI", page_icon="✈️", layout="wide")
st.title("AdPilot AI")
st.caption("AI 기반 광고 캠페인 운영 플랫폼 — Phase 0")

st.info("현재는 프로젝트 초기화 단계입니다. 캠페인 및 분석 기능은 다음 Phase에서 제공됩니다.")

try:
    health = AdPilotApiClient().health()
    st.success(f"Backend connected · {health['service']} v{health['version']}")
    st.json(health)
except Exception as exc:
    st.error("Backend에 연결할 수 없습니다. API 서버 실행 상태를 확인하세요.")
    st.code(str(exc))
