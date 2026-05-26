import uuid
import pytest
from src.agents.ceo_agent import CEOAgent
from src.agents.secretariat_agent import SecretariatAgent
from src.agents.communications_agent import CommunicationsAgent
from src.agents.innovation_agent import InnovationAgent
from src.agents.implementation_agent import ImplementationAgent
from src.agents.research_agent import ResearchAgent
from src.agents.oversight_agent import OversightAgent
from src.agents.hr_agent import HRAgent


AGENT_FOLDER = "agents/test"


def test_ceo_agent_creation():
    agent = CEOAgent(
        agent_id=uuid.uuid4(), name="CEO", department_name="CEO办公室",
        folder_path=AGENT_FOLDER,
    )
    assert agent.name == "CEO"
    assert agent.role == "CEO"
    assert agent.tier == 0
    caps = agent.get_capabilities()
    assert "task_decomposition" in caps
    assert "strategic_decision" in caps


def test_secretariat_agent_creation():
    agent = SecretariatAgent(
        agent_id=uuid.uuid4(), name="秘书", department_name="秘书科",
        folder_path=AGENT_FOLDER,
    )
    assert agent.role == "秘书科"
    assert agent.tier == 2
    assert "minutes_generation" in agent.get_capabilities()
    assert "meeting_attendance" in agent.get_capabilities()


def test_communications_agent_creation():
    agent = CommunicationsAgent(
        agent_id=uuid.uuid4(), name="通讯", department_name="通讯科",
        folder_path=AGENT_FOLDER,
    )
    assert agent.role == "通讯科"
    assert "email_composition" in agent.get_capabilities()
    assert "daily_briefing" in agent.get_capabilities()


def test_innovation_agent_creation():
    agent = InnovationAgent(
        agent_id=uuid.uuid4(), name="创意Agent", department_name="创意中心",
        folder_path=AGENT_FOLDER,
    )
    assert agent.tier == 2
    assert "idea_generation" in agent.get_capabilities()
    assert "opportunity_discovery" in agent.get_capabilities()


def test_implementation_agent_creation():
    agent = ImplementationAgent(
        agent_id=uuid.uuid4(), name="实现Agent", department_name="实现中心",
        folder_path=AGENT_FOLDER,
    )
    assert agent.tier == 2
    assert agent.temperature == 0.3
    assert "code_generation" in agent.get_capabilities()
    assert "code_review" in agent.get_capabilities()


def test_research_agent_creation():
    agent = ResearchAgent(
        agent_id=uuid.uuid4(), name="研究Agent", department_name="研究中心",
        folder_path=AGENT_FOLDER,
    )
    assert "market_research" in agent.get_capabilities()
    assert "trend_analysis" in agent.get_capabilities()


def test_oversight_agent_creation():
    agent = OversightAgent(
        agent_id=uuid.uuid4(), name="监察Agent", department_name="改进中心",
        folder_path=AGENT_FOLDER,
    )
    assert "runtime_analysis" in agent.get_capabilities()
    assert "root_cause_analysis" in agent.get_capabilities()
    assert "improvement_proposal" in agent.get_capabilities()


def test_hr_agent_creation():
    agent = HRAgent(
        agent_id=uuid.uuid4(), name="HR Agent", department_name="人力资源部门",
        folder_path=AGENT_FOLDER,
    )
    assert agent.tier == 1
    assert "recruitment_review" in agent.get_capabilities()
    assert "workload_analysis" in agent.get_capabilities()
    assert "cost_estimation" in agent.get_capabilities()


def test_agent_context_has_meta_instruction():
    agent = CEOAgent(
        agent_id=uuid.uuid4(), name="CEO", department_name="CEO办公室",
        folder_path=AGENT_FOLDER,
    )
    ctx = agent.get_context()
    assert ctx.agent_name == "CEO"
    assert ctx.tier == 0


def test_all_agents_have_distinct_roles():
    agents = [
        CEOAgent(uuid.uuid4(), "CEO", "CEO办公室", AGENT_FOLDER),
        SecretariatAgent(uuid.uuid4(), "秘书", "秘书科", AGENT_FOLDER),
        CommunicationsAgent(uuid.uuid4(), "通讯", "通讯科", AGENT_FOLDER),
        InnovationAgent(uuid.uuid4(), "创意", "创意中心", AGENT_FOLDER),
        ImplementationAgent(uuid.uuid4(), "实现", "实现中心", AGENT_FOLDER),
        ResearchAgent(uuid.uuid4(), "研究", "研究中心", AGENT_FOLDER),
        OversightAgent(uuid.uuid4(), "监察", "改进中心", AGENT_FOLDER),
        HRAgent(uuid.uuid4(), "HR", "人力资源部门", AGENT_FOLDER),
    ]
    roles = [a.role for a in agents]
    assert len(roles) == len(set(roles))


@pytest.mark.asyncio
async def test_daily_briefing_pipeline(db_session):
    from datetime import date
    from src.models.organization import Department, Agent
    from src.models.daily_briefing import DailyBriefing

    dept = Department(name="简报测试部门", org_path="/brief", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    agent = Agent(name="简报Agent", role="测试", department_id=dept.id, agent_folder_path="agents/brief/test")
    db_session.add(agent)
    await db_session.flush()

    today = date.today()
    briefing = DailyBriefing(
        briefing_date=today,
        generated_by=agent.id,
        content="# 测试简报\n\n内容",
        status="draft",
    )
    db_session.add(briefing)
    await db_session.flush()

    assert briefing.briefing_date == today
    assert briefing.status == "draft"
    assert "测试简报" in briefing.content
    assert briefing.generated_by == agent.id
