"""
Mock LLM Provider — Offline development and testing.

Implements the LLMClient interface with predefined responses for known query patterns.
For unknown queries, returns a generic fallback response.

Usage:
    from src.llm.mock_provider import MockLLMProvider
    client = MockLLMProvider()
    result = await client.chat("Điều 17 Luật Doanh nghiệp")
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Optional

from .client import LLMClient


class MockLLMProvider(LLMClient):
    """
    Mock LLM provider for offline development and testing.

    Returns predefined responses for known query patterns.
    Falls back to generic responses for unknown queries.
    """

    # Predefined intent responses
    INTENT_RESPONSES = {
        "lookup_dieu": {
            "conversation_id": "mock_conv_001",
            "turn_number": 1,
            "domain": "QA",
            "confidence": 0.95,
            "intents": [
                {
                    "type": "LOOKUP",
                    "confidence": 0.95,
                    "query_span": [0, 30],
                    "extracted": {
                        "document_type": "Luật",
                        "document_name": "Luật Doanh nghiệp",
                        "article_number": 17,
                        "year": "2020",
                        "so_ky_hieu": "LT-068-2020",
                    },
                }
            ],
            "sub_queries": [
                {
                    "intent": "LOOKUP",
                    "query": "Điều 17 Luật Doanh nghiệp 2020",
                    "retrieval_strategy": "direct_lookup",
                    "requires": ["legal_provision", "effective_text"],
                }
            ],
            "context_references": {},
            "routing": {
                "primary_pipeline": "qa",
                "fallback_pipeline": "general_qa",
                "context_needed": False,
            },
        },
        "topic_question": {
            "conversation_id": "mock_conv_001",
            "turn_number": 1,
            "domain": "QA",
            "confidence": 0.90,
            "intents": [
                {
                    "type": "TOPIC",
                    "confidence": 0.90,
                    "query_span": [0, 30],
                    "extracted": {
                        "topic": "bảo hiểm xã hội",
                        "aspect": "regulations",
                    },
                }
            ],
            "sub_queries": [
                {
                    "intent": "TOPIC",
                    "query": "Quy định về bảo hiểm xã hội",
                    "retrieval_strategy": "vector_search",
                    "requires": ["legal_provision"],
                }
            ],
            "context_references": {},
            "routing": {
                "primary_pipeline": "qa",
                "fallback_pipeline": "general_qa",
                "context_needed": False,
            },
        },
        "validity_question": {
            "conversation_id": "mock_conv_001",
            "turn_number": 1,
            "domain": "QA",
            "confidence": 0.92,
            "intents": [
                {
                    "type": "VALIDITY",
                    "confidence": 0.92,
                    "query_span": [0, 30],
                    "extracted": {
                        "document_type": "Luật",
                        "document_name": "Luật Đất đai",
                        "year": "2013",
                        "so_ky_hieu": "LT-045-2013",
                    },
                }
            ],
            "sub_queries": [
                {
                    "intent": "VALIDITY",
                    "query": "Luật Đất đai 2013",
                    "retrieval_strategy": "validity_check",
                    "requires": ["legal_provision"],
                }
            ],
            "context_references": {},
            "routing": {
                "primary_pipeline": "qa",
                "fallback_pipeline": "general_qa",
                "context_needed": False,
            },
        },
        "comparison_question": {
            "conversation_id": "mock_conv_001",
            "turn_number": 1,
            "domain": "QA",
            "confidence": 0.88,
            "intents": [
                {
                    "type": "COMPARISON",
                    "confidence": 0.88,
                    "query_span": [0, 40],
                    "extracted": {
                        "documents": [
                            {"document_type": "Luật", "document_name": "Luật Doanh nghiệp", "year": "2014"},
                            {"document_type": "Luật", "document_name": "Luật Doanh nghiệp", "year": "2020"},
                        ],
                        "aspect": "content",
                    },
                }
            ],
            "sub_queries": [
                {
                    "intent": "LOOKUP",
                    "query": "Luật Doanh nghiệp 2014",
                    "retrieval_strategy": "direct_lookup",
                    "requires": ["legal_provision"],
                },
                {
                    "intent": "LOOKUP",
                    "query": "Luật Doanh nghiệp 2020",
                    "retrieval_strategy": "direct_lookup",
                    "requires": ["legal_provision"],
                },
                {
                    "intent": "COMPARISON",
                    "query": "So sánh Luật Doanh nghiệp 2014 và 2020",
                    "retrieval_strategy": "comparison",
                    "requires": ["legal_provision", "effective_text"],
                },
            ],
            "context_references": {},
            "routing": {
                "primary_pipeline": "qa",
                "fallback_pipeline": "general_qa",
                "context_needed": False,
            },
        },
        "contract_review": {
            "conversation_id": "mock_conv_001",
            "turn_number": 1,
            "domain": "CONTRACT_REVIEW",
            "confidence": 0.95,
            "intents": [
                {
                    "type": "CONTRACT_REVIEW",
                    "confidence": 0.95,
                    "query_span": [0, 20],
                    "extracted": {},
                }
            ],
            "sub_queries": [],
            "context_references": {},
            "routing": {
                "primary_pipeline": "contract_review",
                "fallback_pipeline": "qa",
                "context_needed": False,
            },
        },
        "chitchat": {
            "conversation_id": "mock_conv_001",
            "turn_number": 1,
            "domain": "CHITCHAT",
            "confidence": 0.99,
            "intents": [],
            "sub_queries": [],
            "context_references": {},
            "routing": {
                "primary_pipeline": "fallback",
                "fallback_pipeline": "fallback",
                "context_needed": False,
            },
        },
    }

    CLAUSE_EXTRACTION_RESPONSE = [
        {
            "clause_type": "thanh_toán",
            "text_content": "Giá thuê: 50.000.000 VNĐ/tháng. Thanh toán trước ngày 05 hàng tháng.",
            "parties_involved": ["Bên A", "Bên B"],
            "obligations": ["Bên B thanh toán tiền thuê đúng hạn"],
            "amount": "50.000.000 VNĐ/tháng",
            "deadline": "Ngày 05 hàng tháng",
        },
        {
            "clause_type": "phạt",
            "text_content": "Phạt 30% giá trị hợp đồng khi đơn phương chấm dứt trước thời hạn.",
            "parties_involved": ["Bên A", "Bên B"],
            "obligations": ["Không đơn phương chấm dứt hợp đồng"],
            "amount": "30% giá trị hợp đồng",
            "deadline": None,
        },
        {
            "clause_type": "chấm_dứt",
            "text_content": "Hợp đồng chấm dứt khi hết thời hạn hoặc một bên vi phạm nghiêm trọng.",
            "parties_involved": ["Bên A", "Bên B"],
            "obligations": ["Thông báo chấm dứt trước 30 ngày"],
            "amount": None,
            "deadline": "30 ngày thông báo trước",
        },
        {
            "clause_type": "giải_quyết_tranh_chấp",
            "text_content": "Tranh chấp đưa ra Tòa án nhân dân TP. Hồ Chí Minh.",
            "parties_involved": ["Bên A", "Bên B"],
            "obligations": ["Giải quyết qua thương lượng trước"],
            "amount": None,
            "deadline": None,
        },
        {
            "clause_type": "bảo_mật",
            "text_content": "Không tiết lộ thông tin mật của bên kia.",
            "parties_involved": ["Bên A", "Bên B"],
            "obligations": ["Bảo mật thông tin"],
            "amount": None,
            "deadline": None,
        },
    ]

    COMPLIANCE_RESPONSE = {
        "violations": [
            {
                "clause": "Phạt 30% giá trị hợp đồng",
                "description": "Mức phạt 30% vượt quá 8% giá trị phần nghĩa vụ bị vi phạm theo Luật Thương mại 2005",
                "citation": "Điều 301 Luật Thương mại 2005",
                "severity": "high",
            }
        ],
        "risks": [
            "Mức phạt quá cao có thể bị tòa án tuyên vô hiệu",
            "Không có điều khoản về bất khả kháng chi tiết",
        ],
        "suggestions": [
            "Giảm mức phạt xuống tối đa 8% giá trị phần nghĩa vụ bị vi phạm",
            "Bổ sung điều khoản về bất khả kháng theo quy định Bộ luật Dân sự",
        ],
        "citations": [
            {
                "document": "Luật Thương mại 2005",
                "article": "Điều 301",
                "clause": None,
                "point": None,
                "text": "Giá trị phạt vi phạm không vượt quá 8% giá trị phần nghĩa vụ bị vi phạm",
            }
        ],
    }

    ANSWER_RESPONSE = {
        "answer": "Theo Điều 17 Luật Doanh nghiệp 2020, doanh nghiệp có quyền tự do kinh doanh trong những ngành, nghề mà luật không cấm. Cụ thể:\n\n1. Doanh nghiệp có quyền kinh doanh ngành, nghề mà luật không cấm.\n2. Ngành, nghề cấm kinh doanh được quy định tại Điều 6 của Luật này.\n3. Doanh nghiệp phải đáp ứng điều kiện kinh doanh đối với ngành, nghề có điều kiện.",
        "citations": [
            {
                "document": "Luật Doanh nghiệp 2020",
                "article": "Điều 17",
                "clause": None,
                "point": None,
                "text": "Doanh nghiệp có quyền tự do kinh doanh trong những ngành, nghề mà luật không cấm.",
            }
        ],
    }

    FALLBACK_RESPONSE = {
        "conversation_id": "mock_conv_001",
        "turn_number": 1,
        "domain": "QA",
        "confidence": 0.40,
        "intents": [
            {
                "type": "SEARCH",
                "confidence": 0.40,
                "query_span": [0, 10],
                "extracted": {},
            }
        ],
        "sub_queries": [
            {
                "intent": "SEARCH",
                "query": "fallback query",
                "retrieval_strategy": "vector_search",
                "requires": ["legal_provision"],
            }
        ],
        "context_references": {},
        "routing": {
            "primary_pipeline": "qa",
            "fallback_pipeline": "general_qa",
            "context_needed": False,
        },
    }

    FALLBACK_ANSWER = {
        "answer": "Tôi chưa tìm thấy thông tin chính xác cho câu hỏi của bạn. Bạn có thể nói rõ hơn không?",
        "citations": [],
    }

    QUERY_REWRITE_RESPONSE = {
        "original_text": "Phạt 30% giá trị hợp đồng khi đơn phương chấm dứt trước thời hạn.",
        "legal_issue": "mức phạt vi phạm hợp đồng thương mại",
        "search_queries": [
            "mức phạt vi phạm hợp đồng tối đa",
            "phạt vi phạm 8% giá trị phần nghĩa vụ bị vi phạm",
            "đơn phương chấm dứt hợp đồng và phạt vi phạm",
        ],
        "keywords": ["phạt vi phạm", "8%", "nghĩa vụ bị vi phạm", "đơn phương chấm dứt"],
        "expected_domains": ["Luật Thương mại", "Bộ luật Dân sự"],
        "title_hints": ["Luật Thương mại", "Bộ luật Dân sự"],
        "risk_type": "penalty_cap",
        "filters": {"document_types": ["Luật", "Bộ luật"]},
        "confidence": 0.85,
    }

    def _classify_query(self, query: str) -> str:
        """Classify query to select appropriate mock response."""
        q = query.lower()
        if any(w in q for w in ["xin chào", "hello", "hi ", "chào bạn"]):
            return "chitchat"
        if any(w in q for w in ["review", "hợp đồng", "upload"]):
            return "contract_review"
        if any(w in q for w in ["còn hiệu lực", "hết hiệu lực", "validity"]):
            return "validity_question"
        if any(w in q for w in ["so sánh", "khác nhau", "comparison"]):
            return "comparison_question"
        if any(w in q for w in ["quy định về", "như thế nào", "quy định gì"]):
            return "topic_question"
        if "điều" in q and "luật" in q:
            return "lookup_dieu"
        return "fallback"

    async def chat(
        self,
        prompt: str,
        schema: Optional[dict] = None,
        temperature: float = 0.0,
    ) -> dict:
        """Return predefined response based on prompt content."""
        # Determine response type from prompt
        if "trích xuất các điều khoản" in prompt.lower():
            return self.CLAUSE_EXTRACTION_RESPONSE
        if "rewrite query pháp lý" in prompt.lower():
            return self.QUERY_REWRITE_RESPONSE
        if "phân tích tuân thủ" in prompt.lower():
            return self.COMPLIANCE_RESPONSE
        if "trả lời câu hỏi pháp lý" in prompt.lower():
            return self.ANSWER_RESPONSE

        # Intent analysis
        query_match = re.search(r"Câu hỏi:\s*(.+)", prompt)
        if query_match:
            query = query_match.group(1).strip()
        else:
            query = prompt

        response_key = self._classify_query(query)
        return self.INTENT_RESPONSES.get(response_key, self.FALLBACK_RESPONSE)

    async def chat_stream(
        self,
        prompt: str,
        schema: Optional[dict] = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        response = await self.chat(prompt, schema=schema, temperature=temperature)
        content = json.dumps(response, ensure_ascii=False)
        for index in range(0, len(content), 16):
            yield content[index : index + 16]

    async def extract(self, text: str, schema: dict) -> dict:
        """Mock structured extraction."""
        if "clause" in str(schema).lower() or "điều khoản" in text.lower():
            return {"clauses": self.CLAUSE_EXTRACTION_RESPONSE}
        return {"result": text[:100]}

    async def classify(self, text: str, categories: list[str]) -> dict:
        """Mock classification."""
        return {
            "category": categories[0] if categories else "unknown",
            "confidence": 0.85,
        }
