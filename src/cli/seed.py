import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import async_session_factory, init_db
from src.models.organization import Department, Agent
from src.services.agent_lifecycle import AgentLifecycleService, AgentCreate


async def seed_default_org():
    await init_db()

    async with async_session_factory() as session:
        # T0: CEO办公室
        ceo_office = Department(
            name="CEO办公室",
            description="最高决策层",
            org_path="/ceo_office",
            tier=0,
            dept_type="ceo_office",
            dept_code="CEO-OFFICE",
        )
        session.add(ceo_office)
        await session.flush()

        # T2 units under CEO Office
        secretariat = Department(
            name="秘书科",
            description="协调会议、生成纪要",
            parent_id=ceo_office.id,
            org_path="/ceo_office/secretariat",
            tier=2,
            dept_type="office",
            dept_code="SECRETARIAT",
        )
        communications = Department(
            name="通讯科",
            description="邮件汇报、每日简报",
            parent_id=ceo_office.id,
            org_path="/ceo_office/communications",
            tier=2,
            dept_type="office",
            dept_code="COMMUNICATIONS",
        )
        session.add_all([secretariat, communications])
        await session.flush()

        # T1: Departments
        product_dept = Department(
            name="产品部门",
            description="产品研发与创新",
            parent_id=ceo_office.id,
            org_path="/ceo_office/product_department",
            tier=1,
            dept_type="department",
            dept_code="PRODUCT-DEPT",
        )
        oversight_dept = Department(
            name="监察部门",
            description="监察、合规与改进",
            parent_id=ceo_office.id,
            org_path="/ceo_office/oversight_department",
            tier=1,
            dept_type="department",
            dept_code="OVERSIGHT-DEPT",
        )
        hr_dept = Department(
            name="人力资源部门",
            description="招聘、培训与绩效管理",
            parent_id=ceo_office.id,
            org_path="/ceo_office/hr_department",
            tier=1,
            dept_type="department",
            dept_code="HR-DEPT",
        )
        session.add_all([product_dept, oversight_dept, hr_dept])
        await session.flush()

        # T2: Centers under departments
        centers = [
            Department(name="创意中心", description="商机发现、创意生成", parent_id=product_dept.id, org_path="/ceo_office/product_department/innovation_center", tier=2, dept_type="center", dept_code="INNOVATION-CENTER"),
            Department(name="实现中心", description="代码-测试-运维", parent_id=product_dept.id, org_path="/ceo_office/product_department/implementation_center", tier=2, dept_type="center", dept_code="IMPL-CENTER"),
            Department(name="研究中心", description="股市分析、新闻分析", parent_id=product_dept.id, org_path="/ceo_office/product_department/research_center", tier=2, dept_type="center", dept_code="RESEARCH-CENTER"),
            Department(name="改进中心", description="运行时数据分析、提出改进", parent_id=oversight_dept.id, org_path="/ceo_office/oversight_department/improvement_center", tier=2, dept_type="center", dept_code="IMPROVE-CENTER"),
            Department(name="招聘中心", description="招聘流程执行、soul.md模板管理", parent_id=hr_dept.id, org_path="/ceo_office/hr_department/recruitment_center", tier=2, dept_type="center", dept_code="RECRUIT-CENTER"),
        ]
        session.add_all(centers)
        await session.flush()

        await session.commit()
        print("[OK] 默认组织架构已创建")
        print("  T0: CEO办公室")
        print("  T1: 产品部门, 监察部门, 人力资源部门")
        print("  T2: 秘书科, 通讯科, 创意中心, 实现中心, 研究中心, 改进中心, 招聘中心")


if __name__ == "__main__":
    asyncio.run(seed_default_org())
