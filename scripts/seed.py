"""
Development seed data script for ORCA Platform & Care Companion.

Seeds:
1. Applications: care-companion, command-view
2. Countries: Arnova, Belmara, Calduria
3. Users: Alice, Bob, Carol
4. Roles & Permissions for Care Companion
5. User Application Roles & User Country Scopes
   - Alice: case-manager (all permissions), Arnova + Belmara
   - Bob: case-worker (create, read, update), Calduria
   - Carol: viewer (read only), Belmara
"""

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.application import Application
from app.models.country import Country
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_application_role import UserApplicationRole
from app.models.user_country_scope import UserCountryScope


def seed_data(session: Session) -> dict[str, dict]:
    print("Seeding ORCA platform data...")

    # 1. Applications
    apps_data = [
        {"key": "care-companion", "name": "Care Companion"},
        {"key": "command-view", "name": "Command View"},
        {"key": "partner-engage", "name": "Partner Engage"},
    ]
    apps: dict[str, Application] = {}
    for item in apps_data:
        app = session.execute(
            select(Application).where(Application.key == item["key"])
        ).scalar_one_or_none()
        if not app:
            app = Application(key=item["key"], name=item["name"])
            session.add(app)
            session.flush()
        apps[item["key"]] = app

    # 2. Countries
    countries_data = [
        {"code": "ARN", "name": "Arnova"},
        {"code": "BEL", "name": "Belmara"},
        {"code": "CAL", "name": "Calduria"},
    ]
    countries: dict[str, Country] = {}
    for item in countries_data:
        country = session.execute(
            select(Country).where(Country.code == item["code"])
        ).scalar_one_or_none()
        if not country:
            country = Country(code=item["code"], name=item["name"])
            session.add(country)
            session.flush()
        countries[item["code"]] = country

    # 3. Users
    users_data = [
        {"email": "alice@orca.internal", "display_name": "Alice"},
        {"email": "bob@orca.internal", "display_name": "Bob"},
        {"email": "carol@orca.internal", "display_name": "Carol"},
    ]
    users: dict[str, User] = {}
    for item in users_data:
        user = session.execute(
            select(User).where(User.email == item["email"])
        ).scalar_one_or_none()
        if not user:
            user = User(email=item["email"], display_name=item["display_name"])
            session.add(user)
            session.flush()
        users[item["display_name"]] = user

    # 4. Permissions for Care Companion
    care_app = apps["care-companion"]
    permission_keys = [
        ("case:create", "Create new cases"),
        ("case:read", "Read cases within geographic scope"),
        ("case:update", "Update existing cases"),
        ("case:assign", "Assign cases to workers"),
        ("case:close", "Close completed cases"),
        ("case:delete", "Soft delete cases"),
        ("audit:read", "Read application audit logs within geographic scope"),
    ]
    permissions: dict[str, Permission] = {}
    for key, desc in permission_keys:
        perm = session.execute(
            select(Permission).where(
                Permission.owner_app_id == care_app.id,
                Permission.key == key,
            )
        ).scalar_one_or_none()
        if not perm:
            perm = Permission(owner_app_id=care_app.id, key=key, description=desc)
            session.add(perm)
            session.flush()
        permissions[key] = perm

    # 5. Roles for Care Companion
    roles_data = [
        {
            "key": "case-manager",
            "name": "Case Manager",
            "description": "Full access to manage cases in scoped countries",
            "permissions": [
                "case:create",
                "case:read",
                "case:update",
                "case:assign",
                "case:close",
                "case:delete",
                "audit:read",
            ],
        },
        {
            "key": "case-worker",
            "name": "Case Worker",
            "description": "Create, read and update cases in scoped countries",
            "permissions": [
                "case:create",
                "case:read",
                "case:update",
            ],
        },
        {
            "key": "viewer",
            "name": "Viewer",
            "description": "Read-only access to cases in scoped countries",
            "permissions": [
                "case:read",
            ],
        },
    ]
    roles: dict[str, Role] = {}
    for item in roles_data:
        role = session.execute(
            select(Role).where(
                Role.owner_app_id == care_app.id,
                Role.key == item["key"],
            )
        ).scalar_one_or_none()
        if not role:
            role = Role(
                owner_app_id=care_app.id,
                key=item["key"],
                name=item["name"],
                description=item["description"],
            )
            session.add(role)
            session.flush()
        roles[item["key"]] = role

        # Role Permissions link
        for p_key in item["permissions"]:
            perm = permissions[p_key]
            rp = session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            ).scalar_one_or_none()
            if not rp:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))

    session.flush()

    # 6. User Application Roles
    # Alice -> case-manager
    # Bob -> case-worker
    # Carol -> viewer
    assignments = [
        (users["Alice"], roles["case-manager"]),
        (users["Bob"], roles["case-worker"]),
        (users["Carol"], roles["viewer"]),
    ]
    for u, r in assignments:
        uar = session.execute(
            select(UserApplicationRole).where(
                UserApplicationRole.user_id == u.id,
                UserApplicationRole.application_id == care_app.id,
                UserApplicationRole.role_id == r.id,
            )
        ).scalar_one_or_none()
        if not uar:
            session.add(
                UserApplicationRole(
                    user_id=u.id,
                    application_id=care_app.id,
                    role_id=r.id,
                )
            )

    # 7. User Country Scopes for Care Companion
    # Alice -> Arnova, Belmara
    # Bob -> Calduria
    # Carol -> Belmara
    country_scopes = [
        (users["Alice"], countries["ARN"]),
        (users["Alice"], countries["BEL"]),
        (users["Bob"], countries["CAL"]),
        (users["Carol"], countries["BEL"]),
    ]
    for u, c in country_scopes:
        ucs = session.execute(
            select(UserCountryScope).where(
                UserCountryScope.user_id == u.id,
                UserCountryScope.application_id == care_app.id,
                UserCountryScope.country_id == c.id,
            )
        ).scalar_one_or_none()
        if not ucs:
            session.add(
                UserCountryScope(
                    user_id=u.id,
                    application_id=care_app.id,
                    country_id=c.id,
                )
            )

    # 8. Command View App Setup
    cmd_app = apps["command-view"]

    # Command View Permissions
    cmd_perm = session.execute(
        select(Permission).where(
            Permission.owner_app_id == cmd_app.id,
            Permission.key == "case-metrics:read",
        )
    ).scalar_one_or_none()
    if not cmd_perm:
        cmd_perm = Permission(
            owner_app_id=cmd_app.id,
            key="case-metrics:read",
            description="Read aggregated case metrics by country in Command View",
        )
        session.add(cmd_perm)
        session.flush()

    # Command View Roles
    cmd_role = session.execute(
        select(Role).where(
            Role.owner_app_id == cmd_app.id,
            Role.key == "operations-viewer",
        )
    ).scalar_one_or_none()
    if not cmd_role:
        cmd_role = Role(
            owner_app_id=cmd_app.id,
            key="operations-viewer",
            name="Operations Viewer",
            description="Read-only access to operations metrics across allowed countries",
        )
        session.add(cmd_role)
        session.flush()

    # Link role to permission
    cmd_rp = session.execute(
        select(RolePermission).where(
            RolePermission.role_id == cmd_role.id,
            RolePermission.permission_id == cmd_perm.id,
        )
    ).scalar_one_or_none()
    if not cmd_rp:
        session.add(RolePermission(role_id=cmd_role.id, permission_id=cmd_perm.id))

    # User Role in Command View: Alice -> operations-viewer
    cmd_uar = session.execute(
        select(UserApplicationRole).where(
            UserApplicationRole.user_id == users["Alice"].id,
            UserApplicationRole.application_id == cmd_app.id,
            UserApplicationRole.role_id == cmd_role.id,
        )
    ).scalar_one_or_none()
    if not cmd_uar:
        session.add(
            UserApplicationRole(
                user_id=users["Alice"].id,
                application_id=cmd_app.id,
                role_id=cmd_role.id,
            )
        )

    # User Country Scopes in Command View:
    # Alice -> Arnova, Belmara
    # Bob -> Calduria (no role yet, for testing negative role authorization)
    cmd_scopes = [
        (users["Alice"], countries["ARN"]),
        (users["Alice"], countries["BEL"]),
    ]
    for u, c in cmd_scopes:
        ucs = session.execute(
            select(UserCountryScope).where(
                UserCountryScope.user_id == u.id,
                UserCountryScope.application_id == cmd_app.id,
                UserCountryScope.country_id == c.id,
            )
        ).scalar_one_or_none()
        if not ucs:
            session.add(
                UserCountryScope(
                    user_id=u.id,
                    application_id=cmd_app.id,
                    country_id=c.id,
                )
            )

    # 9. Partner Engage App Setup
    partner_app = apps["partner-engage"]

    # Partner Engage Permissions
    partner_perms_data = [
        ("partner:create", "Create partners"),
        ("partner:read", "Read partners within geographic scope"),
        ("partner:update", "Update partner details"),
    ]
    partner_permissions: dict[str, Permission] = {}
    for key, desc in partner_perms_data:
        p = session.execute(
            select(Permission).where(
                Permission.owner_app_id == partner_app.id,
                Permission.key == key,
            )
        ).scalar_one_or_none()
        if not p:
            p = Permission(owner_app_id=partner_app.id, key=key, description=desc)
            session.add(p)
            session.flush()
        partner_permissions[key] = p

    # Partner Engage Role: partner-manager
    partner_role = session.execute(
        select(Role).where(
            Role.owner_app_id == partner_app.id,
            Role.key == "partner-manager",
        )
    ).scalar_one_or_none()
    if not partner_role:
        partner_role = Role(
            owner_app_id=partner_app.id,
            key="partner-manager",
            name="Partner Manager",
            description="Manage partners within allowed country scope",
        )
        session.add(partner_role)
        session.flush()

    for p in partner_permissions.values():
        rp = session.execute(
            select(RolePermission).where(
                RolePermission.role_id == partner_role.id,
                RolePermission.permission_id == p.id,
            )
        ).scalar_one_or_none()
        if not rp:
            session.add(RolePermission(role_id=partner_role.id, permission_id=p.id))

    # Assign demo user (Alice) role and country scope in Partner Engage
    # Alice -> partner-manager in Partner Engage; Arnova only (limited country scope)
    partner_uar = session.execute(
        select(UserApplicationRole).where(
            UserApplicationRole.user_id == users["Alice"].id,
            UserApplicationRole.application_id == partner_app.id,
            UserApplicationRole.role_id == partner_role.id,
        )
    ).scalar_one_or_none()
    if not partner_uar:
        session.add(
            UserApplicationRole(
                user_id=users["Alice"].id,
                application_id=partner_app.id,
                role_id=partner_role.id,
            )
        )

    # Alice Partner Engage country scope: Arnova only
    partner_ucs = session.execute(
        select(UserCountryScope).where(
            UserCountryScope.user_id == users["Alice"].id,
            UserCountryScope.application_id == partner_app.id,
            UserCountryScope.country_id == countries["ARN"].id,
        )
    ).scalar_one_or_none()
    if not partner_ucs:
        session.add(
            UserCountryScope(
                user_id=users["Alice"].id,
                application_id=partner_app.id,
                country_id=countries["ARN"].id,
            )
        )

    session.commit()
    print("Seed complete successfully!")

    return {
        "applications": apps,
        "countries": countries,
        "users": users,
        "roles": roles,
        "permissions": permissions,
    }


if __name__ == "__main__":
    with SessionLocal() as db_session:
        seed_data(db_session)
