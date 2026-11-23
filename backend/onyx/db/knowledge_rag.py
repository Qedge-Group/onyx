"""Read deployment-specific retrieval settings without leaking ORM instances."""

from sqlalchemy import and_, or_, select

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.models import (
    ConnectorCredentialPair,
    Document,
    DocumentByConnectorCredentialPair,
    DocumentSet,
    DocumentSet__ConnectorCredentialPair,
    LLMProvider,
)


def get_rerank_credentials() -> tuple[str, str] | None:
    with get_session_with_current_tenant() as session:
        provider = session.scalar(
            select(LLMProvider)
            .where(LLMProvider.api_base.ilike("%siliconflow%"))
            .limit(1)
        )
        if provider and provider.api_base and provider.api_key:
            return (
                provider.api_base.rstrip("/"),
                provider.api_key.get_value(apply_mask=False),
            )
    return None


def get_indexed_case_document_ids() -> list[str]:
    with get_session_with_current_tenant() as session:
        statement = (
            select(Document.id)
            .where(
                or_(
                    Document.id.like("%/portfolios%"),
                    Document.id.like("%/projects%"),
                )
            )
            .order_by(Document.id)
            .limit(48)
        )
        return list(session.scalars(statement).all())


def get_indexed_contact_document_ids(document_sets: list[str]) -> list[str]:
    membership = DocumentSet__ConnectorCredentialPair
    indexed = DocumentByConnectorCredentialPair
    pair = ConnectorCredentialPair
    contact_paths = [
        Document.id.ilike("%/" + slug + suffix)
        for slug in ("contact", "contact-us", "contactus")
        for suffix in ("", "/")
    ]
    with get_session_with_current_tenant() as session:
        statement = (
            select(Document.id)
            .join(indexed, indexed.id == Document.id)
            .join(
                pair,
                and_(
                    pair.connector_id == indexed.connector_id,
                    pair.credential_id == indexed.credential_id,
                ),
            )
            .join(membership, membership.connector_credential_pair_id == pair.id)
            .join(DocumentSet, DocumentSet.id == membership.document_set_id)
            .where(
                DocumentSet.name.in_(document_sets),
                membership.is_current.is_(True),
                indexed.has_been_indexed.is_(True),
                or_(*contact_paths),
            )
            .distinct()
            .order_by(Document.id)
            .limit(12)
        )
        return list(session.scalars(statement).all())
