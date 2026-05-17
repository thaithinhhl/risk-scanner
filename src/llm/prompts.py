"""
Prompt Templates for LLM operations.

Templates for:
- Intent analysis (Vietnamese legal domain)
- Clause extraction (T4.2)
- Compliance analysis (T4.4)
- Answer generation (T5.3)
"""
from __future__ import annotations

import re
from typing import Any


class PromptTemplate:
    """
    Prompt template with variable substitution.

    Usage:
        template = PromptTemplate("intent_analysis")
        prompt = template.render(user_input="Điều 17 Luật DN", conversation_history=[])
    """

    # All templates
    TEMPLATES: dict[str, str] = {}

    def __init__(self, name: str) -> None:
        self.name = name
        self._template = self.TEMPLATES.get(name, "")
        if not self._template:
            raise ValueError(f"Unknown template: {name}")

    def render(self, **variables: Any) -> str:
        """Render template with variable substitution."""
        result = self._template
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    @classmethod
    def register(cls, name: str, template: str) -> None:
        """Register a new template."""
        cls.TEMPLATES[name] = template


# ---------------------------------------------------------------------------
# Intent Analysis Template
# ---------------------------------------------------------------------------

PromptTemplate.register("intent_analysis", """Bạn là hệ thống phân tích intent cho câu hỏi pháp lý tiếng Việt.

Câu hỏi: {{user_input}}
Lịch sử hội thoại: {{conversation_history}}

Phân tích và trả về JSON với cấu trúc sau:
- conversation_id: string
- turn_number: số nguyên
- domain: một trong QA, CONTRACT_REVIEW, CONTRACT_QA, EXPLAIN, CHITCHAT
- confidence: số 0-1
- intents: mảng, mỗi phần tử có type (LOOKUP/VALIDITY/COMPARISON/CHECKLIST/NUMERIC/TOPIC/SCENARIO/SEARCH), confidence, query_span [start, end], extracted (object chứa thông tin rút trích như document_name, article_number, year...)
- sub_queries: mảng, mỗi phần tử có intent, query, retrieval_strategy, requires
  - retrieval_strategy chỉ được dùng một trong: direct_lookup, hybrid_search, validity_check, comparison
  - requires chỉ được dùng các token chuẩn: legal_provision, effective_text, document_metadata, conversation_context, contract_context, citation_validation, amendment_history
- context_references: object
- routing: object với primary_pipeline, fallback_pipeline, context_needed

Quy tắc chọn retrieval_strategy:
- Dùng direct_lookup chỉ khi câu hỏi nêu rõ căn cứ cụ thể có thể tra cứu trực tiếp, ví dụ Điều/Khoản/Điểm và tên hoặc số hiệu văn bản: "Điều 17 Luật Doanh nghiệp 2020", "khoản 2 Điều 5 Nghị định 12/2022/NĐ-CP".
- Dùng hybrid_search cho câu hỏi tra cứu quy định chung theo chủ đề, nghĩa vụ, điều kiện, chế độ, mức phạt, thủ tục, quyền lợi, dù intent là LOOKUP. Ví dụ: "quy định về nghĩa vụ đóng bảo hiểm y tế khi ký hợp đồng lao động".
- Dùng validity_check cho câu hỏi hỏi tính hợp pháp/hiệu lực/vi phạm/đúng luật hay không.
- Dùng comparison cho câu hỏi so sánh hai hoặc nhiều quy định/văn bản.

Chỉ trả về JSON, không giải thích.""")


PromptTemplate.register("direct_reference_rewrite", """Bạn là hệ thống chuẩn hóa trích dẫn pháp luật Việt Nam cho truy hồi Neo4j.

Input:
{{query}}

Nhiệm vụ:
- Nếu input có thể quy về một căn cứ cụ thể, chuẩn hóa thành citation dạng: "điểm a khoản 1 Điều 1 Luật Lao động 2019" hoặc "khoản 2 Điều 5 Nghị định 12/2022/NĐ-CP".
- Chỉ trích xuất căn cứ có trong input; không tự bịa số điều/khoản/điểm/văn bản.
- Nếu input chỉ hỏi chủ đề chung và không nêu điều/khoản/điểm cụ thể, trả article=null và confidence thấp.

Trả về duy nhất một JSON object:
{
  "canonical_citation": "citation đã chuẩn hóa hoặc chuỗi rỗng",
  "article": 1,
  "clause": "1",
  "point": "a",
  "document_hint": "Luật Lao động",
  "so_ky_hieu": "45/2019/QH14",
  "year": "2019",
  "confidence": 0.0
}

Quy tắc:
- article là số Điều hoặc null.
- clause là số Khoản dạng string hoặc null.
- point là chữ cái Điểm dạng lowercase hoặc null.
- document_hint là tên văn bản ngắn, ví dụ "Luật Lao động", "Bộ luật Lao động", "Nghị định 12/2022/NĐ-CP".
- so_ky_hieu chỉ điền khi input có số hiệu văn bản rõ ràng.
- Không trả markdown, không giải thích ngoài JSON.
""")

# ---------------------------------------------------------------------------
# Clause Extraction Template (T4.2)
# ---------------------------------------------------------------------------

PromptTemplate.register("clause_extraction", """Trích xuất các điều khoản từ hợp đồng sau.

Với mỗi điều khoản, xác định:
- clause_type: Chọn MỘT trong các loại sau:
  + "thanh_toán" — lương, giá thuê, phương thức thanh toán, phụ cấp
  + "phạt_vi_phạm" — phạt tiền, phạt vi phạm hợp đồng
  + "chấm_dứt" — chấm dứt hợp đồng, đơn phương chấm dứt
  + "bảo_mật" — bảo mật thông tin, không tiết lộ
  + "giải_quyết_tranh_chấp" — hòa giải, tòa án, trọng tài
  + "bồi_thường" — bồi thường thiệt hại
  + "bảo_hành" — bảo hành, bảo trì
  + "force_majeure" — bất khả kháng
  + "thời_hạn" — thời hạn hợp đồng, thời hạn thuê
  + "chức_danh" — chức danh, vị trí công việc, mô tả công việc
  + "thời_gio_lam_viec" — thời giờ làm việc, nghỉ phép, nghỉ lễ
  + "bao_hiểm" — BHXH, BHYT, BHTN, bảo hiểm
  + "nghia_vu" — nghĩa vụ các bên, quyền và nghĩa vụ
  + "canh_tranh" — cấm cạnh tranh, không làm việc cho đối thủ
  + "hieu_luc" — hiệu lực hợp đồng, số bản, nơi ký
  + "dat_coc" — đặt cọc, ký quỹ, bảo lãnh
  + "khác" — các loại không thuộc danh sách trên
- text_content: Nội dung điều khoản
- parties_involved: ["Bên A", "Bên B"] (nếu có)
- obligations: Danh sách nghĩa vụ (nếu có)
- amount: Số tiền (nếu có)
- deadline: Thời hạn (nếu có)

Contract text:
{{contract_text}}

Trả về JSON array.
""")

# ---------------------------------------------------------------------------
# Legal Query Rewrite Template (Task 4 Hybrid Retrieval)
# ---------------------------------------------------------------------------

PromptTemplate.register("legal_query_rewrite", """Bạn là hệ thống rewrite query pháp lý cho rà soát hợp đồng.

Nhiệm vụ: chuyển điều khoản hợp đồng thành kế hoạch tìm kiếm pháp luật.

Clause type:
{{clause_type}}

Contract clause:
{{clause_text}}

Trả về duy nhất một JSON object với schema:
{
  "original_text": "điều khoản gốc",
  "legal_issue": "vấn đề pháp lý ngắn gọn",
  "search_queries": ["các truy vấn pháp lý tự nhiên"],
  "keywords": ["cụm từ pháp lý quan trọng"],
  "expected_domains": ["tên luật/nghị định/bộ luật có khả năng liên quan"],
  "title_hints": ["tên văn bản hoặc chủ đề cần boost"],
  "risk_type": "penalty_cap | termination | wage_benefits | confidentiality | dispute_resolution | general",
  "filters": {"document_types": ["Luật", "Bộ luật", "Nghị định", "Thông tư"]},
  "confidence": 0.0
}

Yêu cầu:
- Không phân tích tuân thủ ở bước này.
- Không bịa citation cụ thể.
- Ưu tiên thuật ngữ pháp lý Việt Nam ngắn, dễ search.
- Chỉ trả về JSON, không giải thích.
""")

# ---------------------------------------------------------------------------
# Compliance Analysis Template (T4.4)
# ---------------------------------------------------------------------------

PromptTemplate.register("compliance_analysis", """Bạn là luật sư phân tích tuân thủ pháp luật cho hợp đồng.

Nhiệm vụ: Phân tích CHI TIẾT điều khoản hợp đồng so với quy định pháp luật được cung cấp.
BẮT BUỘC trả về kết quả cho MỌI điều khoản, nhưng CHỈ dựa trên quy định pháp luật thật sự liên quan trực tiếp.

Contract clause:
{{clause_text}}

Matched legal provisions:
{{legal_provisions}}

Amendment history:
{{amendment_history}}

Trả về duy nhất một JSON object với schema:
{
  "compliance_status": "compliant | non_compliant | partially_compliant",
  "summary": "tóm tắt ngắn gọn phân tích (1-2 câu, tiếng Việt)",
  "violations": [
    {
      "clause": "tên hoặc loại điều khoản",
      "description": "mô tả NGẮN GỌN vi phạm (tối đa 1 câu)",
      "citation": "trích dẫn pháp lý dạng dễ đọc",
      "severity": "low | medium | high"
    }
  ],
  "risks": ["rủi ro pháp lý tiềm ẩn"],
  "suggestions": ["đề xuất sửa đổi cụ thể"],
  "citations": [
    {
      "display_text": "Điều/Khoản/Điểm + tên văn bản",
      "uid": "uid của matched provision",
      "document_title": "tên văn bản",
      "article": "số điều hoặc null",
      "clause": "số khoản hoặc null",
      "point": "ký hiệu điểm hoặc null"
    }
  ]
}

Hướng dẫn phân tích BẮT BUỘC:

0. GUARDRAIL VỀ CĂN CỨ PHÁP LÝ:
   - Chỉ dùng Matched legal provisions nếu nội dung văn bản trực tiếp điều chỉnh điều khoản hợp đồng đang xét.
   - Không được dùng điều luật lao động để đánh giá điều khoản thuê nhà, mua bán, dân sự hoặc chủ đề khác nếu điều luật đó không trực tiếp áp dụng.
   - Không được suy diễn vi phạm chỉ vì có matched provision được cung cấp.
   - Nếu tất cả matched provisions không liên quan hoặc không đủ căn cứ: trả về compliance_status="partially_compliant", summary nêu "Không đủ căn cứ pháp lý trực tiếp từ dữ liệu truy xuất để kết luận", violations=[], risks=[], suggestions=[], citations=[].
   - Không được bịa citation, không được dùng uid ngoài danh sách Matched legal provisions.

1. COMPLIANCE_STATUS:
   - "compliant": Điều khoản tuân thủ đầy đủ pháp luật
   - "non_compliant": Điều khoản vi phạm pháp luật
   - "partially_compliant": Điều khoản có vấn đề cần lưu ý

2. SUMMARY (BẮT BUỘC, không được để trống):
   - Tóm tắt ngắn gọn phân tích bằng tiếng Việt
   - Ví dụ compliant: "Điều khoản quy định thời giờ làm việc 8 giờ/ngày phù hợp Điều 105 BLLĐ. Tuy nhiên chưa nêu rõ thời gian nghỉ giữa giờ."
   - Ví dụ non_compliant: "Điều khoản phạt 01 tháng lương vi phạm Điều 127 BLLĐ cấm phạt tiền người lao động."

3. VIOLATIONS:
   - Chỉ báo cáo khi điều khoản TRỰC TIẾP mâu thuẫn với quy định pháp luật
   - Ví dụ: "phạt 01 tháng lương" vi phạm Điều 127 BLLĐ (cấm phạt tiền người lao động)
   - Nếu compliant, trả về []

4. RISKS:
   - Báo cáo rủi ro pháp lý tiềm ẩn — điều khoản mơ hồ, thiếu chi tiết, có thể gây tranh chấp
   - Ví dụ: "Điều khoản ghi '8 giờ/ngày' compliant, nhưng không nêu rõ thời gian nghỉ giữa giờ theo Điều 108 BLLĐ"
   - Nếu không có rủi ro, trả về []

5. SUGGESTIONS:
   - Đề xuất sửa đổi cụ thể để cải thiện điều khoản
   - Ví dụ: "Bổ sung quy định về thời gian nghỉ giữa giờ theo Điều 108 BLLĐ"
   - Nếu không có đề xuất, trả về []

6. CITATIONS:
   - Chỉ trả về matched provisions có liên quan trực tiếp để người dùng đọc
   - Không trả về citation nếu matched provision không trực tiếp áp dụng cho điều khoản
   - Chỉ dùng uid từ Matched legal provisions
   - display_text phải chính xác theo văn bản pháp luật
   - Đây là phần QUAN TRỌNG NHẤT — người dùng cần đọc luật để hiểu căn cứ

7. Không trả về markdown, không giải thích thêm.

Chỉ trả về JSON object.
""")

PromptTemplate.register("contract_clause_compliance_analysis", """Bạn là luật sư rà soát tuân thủ pháp luật lao động Việt Nam cho từng điều khoản hợp đồng.

Nhiệm vụ: phân tích điều khoản hợp đồng dựa DUY NHẤT trên các quy định pháp luật đã truy xuất.

Clause type:
{{clause_type}}

Contract clause:
{{clause_text}}

Retrieved legal provisions:
{{retrieved_provisions}}

Effective text:
{{effective_text}}

Amendment / validity context:
{{amendment_history}}

Trả về duy nhất một JSON object với schema:
{
  "compliance_status": "compliant | non_compliant | partially_compliant",
  "summary": "tóm tắt ngắn gọn bằng tiếng Việt",
  "violations": [
    {
      "clause": "tên hoặc loại điều khoản",
      "description": "mô tả ngắn gọn vi phạm",
      "citation": "trích dẫn pháp lý dễ đọc",
      "severity": "low | medium | high"
    }
  ],
  "risks": ["rủi ro pháp lý tiềm ẩn"],
  "suggestions": ["đề xuất sửa đổi cụ thể"],
  "citations": [
    {
      "display_text": "Điều/Khoản/Điểm + tên văn bản",
      "uid": "uid từ Retrieved legal provisions",
      "document_title": "tên văn bản",
      "article": "số điều hoặc null",
      "clause": "số khoản hoặc null",
      "point": "ký hiệu điểm hoặc null"
    }
  ]
}

Quy tắc bắt buộc:
- Chỉ dùng quy định có trong Retrieved legal provisions.
- Chỉ cite provision trực tiếp liên quan đến điều khoản đang xét.
- Không dùng uid ngoài Retrieved legal provisions.
- Không được suy diễn vi phạm nếu quy định truy xuất không trực tiếp điều chỉnh điều khoản.
- Với điều khoản tiền lương, phải kiểm tra riêng: mức lương tối thiểu vùng, nguyên tắc trả lương đầy đủ đúng hạn, giới hạn chậm trả lương, và nghĩa vụ trả thêm tiền lãi/đền bù nếu trả lương chậm theo quy định được truy xuất.
- Nếu hợp đồng cho phép chậm lương dài hơn giới hạn pháp luật hoặc miễn trả lãi khi pháp luật yêu cầu trả lãi, phải đánh giá là non_compliant nếu Retrieved legal provisions có căn cứ trực tiếp.
- Nếu không đủ căn cứ pháp lý trực tiếp: trả compliance_status="partially_compliant", summary="Không đủ căn cứ pháp lý trực tiếp từ dữ liệu truy xuất để kết luận.", violations=[], risks=[], suggestions=[], citations=[].
- Nếu có vi phạm, mô tả ngắn, cụ thể, và severity phải là low, medium hoặc high.
- Không trả markdown, không giải thích ngoài JSON.
""")

# ---------------------------------------------------------------------------
# Answer Generation Template (T5.3)
# ---------------------------------------------------------------------------

PromptTemplate.register("answer_generation", """Trả lời câu hỏi pháp lý sau dựa trên thông tin đã truy xuất.

Question:
{{question}}

Retrieved provisions:
{{retrieved_provisions}}

Effective text:
{{effective_text}}

Amendment history:
{{amendment_history}}

Trả lời bằng tiếng Việt, kèm trích dẫn chính xác (Điều X khoản Y Luật Z).
Trả về duy nhất một JSON object với schema:
{
  "answer": "câu trả lời tiếng Việt",
  "citations": [
    {
      "display_text": "Điều/Khoản/Điểm + tên văn bản",
      "uid": "uid lấy từ retrieved provisions",
      "document_title": "tên văn bản",
      "article": "số điều hoặc null",
      "clause": "số khoản hoặc null",
      "point": "ký hiệu điểm hoặc null",
      "text": "đoạn căn cứ ngắn"
    }
  ],
  "retrieval_status": "ok",
  "confidence": 0.0,
  "validity": {
    "status": "verified | likely_current | unknown",
    "reason": "lý do ngắn gọn",
    "evidence": []
  }
}

Quy tắc:
- Chỉ dùng citation uid xuất hiện trong Retrieved provisions.
- Nếu validity không chắc chắn, nói rõ là dữ liệu quan hệ chưa đủ để kết luận chắc chắn.
- Không trả về markdown hoặc giải thích ngoài JSON.
""")

PromptTemplate.register("answer_generation_stream", """Trả lời câu hỏi pháp lý sau dựa trên thông tin đã truy xuất.

Question:
{{question}}

Retrieved provisions:
{{retrieved_provisions}}

Effective text:
{{effective_text}}

Amendment history:
{{amendment_history}}

Yêu cầu:
- Chỉ trả lời bằng tiếng Việt tự nhiên, ngắn gọn, rõ ràng.
- Không trả về JSON.
- Không dùng markdown.
- Không liệt kê metadata hay cấu trúc máy đọc.
- Có thể nhắc tới Điều/Khoản/Điểm nếu cần, nhưng vẫn phải là văn phong tự nhiên.
""")
