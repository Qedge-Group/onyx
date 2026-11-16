import unittest
from types import SimpleNamespace as NS

from onyx.context.search.content_policy import (
    contains_excluded,
    excluded_terms,
    filter_sections,
)


class ContentPolicyTests(unittest.TestCase):
    def test_scope_and_topics(self):
        self.assertFalse(excluded_terms(["qedge.ai"]))
        for value in ["科睿哲", "土地房屋征收", "棚改方案", "DEMOLITION"]:
            self.assertTrue(contains_excluded(value, ["www.qedge.cn"]))
            self.assertFalse(contains_excluded(value, ["qedge.ai"]))
        self.assertFalse(
            contains_excluded("Sitecore 数字体验 企业出海", ["www.qedge.cn"])
        )

    def test_exclude_document_siblings(self):
        def section(id, text):
            return NS(
                center_chunk=NS(document_id=id, semantic_identifier="服务"),
                combined_content=text,
            )

        rows = [
            section("a", "系统集成"),
            section("a", "征收拆迁"),
            section("b", "Sitecore"),
        ]
        self.assertEqual(
            [
                s.center_chunk.document_id
                for s in filter_sections(rows, ["www.qedge.cn"])
            ],
            ["b"],
        )
        self.assertEqual(filter_sections(rows, ["qedge.ai"]), rows)

    def test_index_filter_excludes_before_ranking_and_keeps_acl(self):
        from onyx.document_index.interfaces import TenantState
        from onyx.document_index.opensearch.search import DocumentQuery

        def filters(names):
            return DocumentQuery._get_search_filters(
                tenant_state=TenantState(tenant_id="default", multitenant=False),
                include_hidden=False,
                access_control_list=["public"],
                cc_pair_access=None,
                source_types=[],
                tags=[],
                document_sets=names,
                project_id_filter=None,
                persona_id_filter=None,
                created_at_range=None,
                updated_at_range=None,
                min_chunk_index=None,
                max_chunk_index=None,
            )

        import json

        china = json.dumps(filters(["www.qedge.cn"]), ensure_ascii=False)
        other = json.dumps(filters(["qedge.ai"]), ensure_ascii=False)
        self.assertIn("科睿哲", china)
        self.assertIn("must_not", china)
        self.assertIn("public", china)
        self.assertNotIn("科睿哲", other)

    def test_legacy_search_accepts_agent_and_imports_scope_validation(self):
        from ee.onyx.search.process_search_query import stream_search_query
        from ee.onyx.server.query_and_chat.models import SendSearchQueryRequest

        self.assertTrue(callable(stream_search_query))
        self.assertEqual(
            SendSearchQueryRequest(search_query="Sitecore", persona_id=2).persona_id, 2
        )

    def test_legacy_scope_is_enforced_before_search(self):
        from unittest.mock import MagicMock, patch

        from ee.onyx.search.process_search_query import stream_search_query
        from ee.onyx.server.query_and_chat.models import SendSearchQueryRequest
        from onyx.context.search.models import BaseFilters
        from onyx.error_handling.exceptions import OnyxError

        with patch(
            "ee.onyx.search.process_search_query._load_persona",
            return_value=(None, NS(document_set_names=["www.qedge.cn"])),
        ):
            blocked = list(
                stream_search_query(
                    SendSearchQueryRequest(search_query="科睿哲", persona_id=2),
                    MagicMock(),
                    MagicMock(),
                )
            )
            self.assertEqual(blocked[0].search_docs, [])
            with self.assertRaises(OnyxError):
                list(
                    stream_search_query(
                        SendSearchQueryRequest(
                            search_query="Sitecore",
                            persona_id=2,
                            filters=BaseFilters(document_set=["qedge.ai"]),
                        ),
                        MagicMock(),
                        MagicMock(),
                    )
                )
