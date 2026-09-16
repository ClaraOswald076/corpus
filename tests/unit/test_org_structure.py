import pytest
from src.models.organization import Department, Agent
from src.services.org_structure import OrgStructureService, DepartmentCreate, OrgTier, DeptType
from src.core.exceptions import OrganizationConstraintError


@pytest.mark.asyncio
async def test_create_t0_department(db_session):
    svc = OrgStructureService(db_session)
    dept = await svc.create_department(DepartmentCreate(
        name="TestCEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    assert dept.tier == 0
    assert dept.dept_type == "ceo_office"
    assert dept.org_path == "/testceo"


@pytest.mark.asyncio
async def test_create_t1_under_t0(db_session):
    svc = OrgStructureService(db_session)
    ceo = await svc.create_department(DepartmentCreate(
        name="CEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    dept = await svc.create_department(DepartmentCreate(
        name="产品部", tier=OrgTier.T1, dept_type=DeptType.DEPARTMENT, parent_id=ceo.id,
    ))
    assert dept.tier == 1
    assert dept.parent_id == ceo.id
    assert dept.org_path == "/ceo/产品部".lower()


@pytest.mark.asyncio
async def test_create_t2_under_t1(db_session):
    svc = OrgStructureService(db_session)
    ceo = await svc.create_department(DepartmentCreate(
        name="CEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    dept = await svc.create_department(DepartmentCreate(
        name="产品部", tier=OrgTier.T1, dept_type=DeptType.DEPARTMENT, parent_id=ceo.id,
    ))
    center = await svc.create_department(DepartmentCreate(
        name="创意中心", tier=OrgTier.T2, dept_type=DeptType.CENTER, parent_id=dept.id,
    ))
    assert center.tier == 2
    assert center.parent_id == dept.id


@pytest.mark.asyncio
async def test_t1_cannot_be_created_without_parent(db_session):
    svc = OrgStructureService(db_session)
    with pytest.raises(OrganizationConstraintError):
        await svc.create_department(DepartmentCreate(
            name="孤儿部门", tier=OrgTier.T1, dept_type=DeptType.DEPARTMENT,
        ))


@pytest.mark.asyncio
async def test_t2_parent_must_be_t1(db_session):
    svc = OrgStructureService(db_session)
    ceo = await svc.create_department(DepartmentCreate(
        name="CEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    with pytest.raises(OrganizationConstraintError):
        await svc.create_department(DepartmentCreate(
            name="跳过T1", tier=OrgTier.T2, dept_type=DeptType.CENTER, parent_id=ceo.id,
        ))


@pytest.mark.asyncio
async def test_t0_cannot_have_parent(db_session):
    svc = OrgStructureService(db_session)
    ceo1 = await svc.create_department(DepartmentCreate(
        name="CEO1", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    with pytest.raises(OrganizationConstraintError):
        await svc.create_department(DepartmentCreate(
            name="CEO2", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE, parent_id=ceo1.id,
        ))


@pytest.mark.asyncio
async def test_get_org_tree(db_session):
    svc = OrgStructureService(db_session)
    ceo = await svc.create_department(DepartmentCreate(
        name="CEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    dept = await svc.create_department(DepartmentCreate(
        name="产品部", tier=OrgTier.T1, dept_type=DeptType.DEPARTMENT, parent_id=ceo.id,
    ))
    await svc.create_department(DepartmentCreate(
        name="创意中心", tier=OrgTier.T2, dept_type=DeptType.CENTER, parent_id=dept.id,
    ))

    tree = await svc.get_org_tree()
    assert len(tree) == 1
    assert tree[0]["name"] == "CEO"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["name"] == "产品部"
    assert len(tree[0]["children"][0]["children"]) == 1
    assert tree[0]["children"][0]["children"][0]["name"] == "创意中心"


@pytest.mark.asyncio
async def test_delete_empty_department(db_session):
    svc = OrgStructureService(db_session)
    ceo = await svc.create_department(DepartmentCreate(
        name="CEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    dept = await svc.create_department(DepartmentCreate(
        name="产品部", tier=OrgTier.T1, dept_type=DeptType.DEPARTMENT, parent_id=ceo.id,
    ))
    await svc.delete_department(dept.id)
    depts = await svc.list_departments()
    assert len(depts) == 1


@pytest.mark.asyncio
async def test_cannot_delete_department_with_children(db_session):
    svc = OrgStructureService(db_session)
    ceo = await svc.create_department(DepartmentCreate(
        name="CEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    dept = await svc.create_department(DepartmentCreate(
        name="产品部", tier=OrgTier.T1, dept_type=DeptType.DEPARTMENT, parent_id=ceo.id,
    ))
    await svc.create_department(DepartmentCreate(
        name="创意中心", tier=OrgTier.T2, dept_type=DeptType.CENTER, parent_id=dept.id,
    ))
    with pytest.raises(OrganizationConstraintError):
        await svc.delete_department(dept.id)


@pytest.mark.asyncio
async def test_cannot_delete_department_with_agents(db_session):
    svc = OrgStructureService(db_session)
    ceo = await svc.create_department(DepartmentCreate(
        name="CEO", tier=OrgTier.T0, dept_type=DeptType.CEO_OFFICE,
    ))
    dept = await svc.create_department(DepartmentCreate(
        name="产品部", tier=OrgTier.T1, dept_type=DeptType.DEPARTMENT, parent_id=ceo.id,
    ))
    db_session.add(Agent(name="产品Agent", role="执行者", department_id=dept.id, agent_folder_path="agents/pd/a"))
    await db_session.flush()

    # 辖下有人必须明确拒绝，而不是 IntegrityError 穿透成 500/内部报文
    with pytest.raises(OrganizationConstraintError, match="请先转移或删除"):
        await svc.delete_department(dept.id)
    assert await svc.get_department(dept.id) is not None


@pytest.mark.asyncio
async def test_permission_matrix(db_session):
    svc = OrgStructureService(db_session)
    t0_perms = svc.get_effective_permissions(0)
    t1_perms = svc.get_effective_permissions(1)
    t2_perms = svc.get_effective_permissions(2)

    assert t0_perms["can_escalate_to_user"] is True
    assert t1_perms["can_escalate_to_user"] is False
    assert t2_perms["can_decompose_task"] is False
    assert t0_perms["can_create_department"] is True
